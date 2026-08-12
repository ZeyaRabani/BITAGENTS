# What "doing what Ruqa said" actually means — scoping

Written 2026-08-12 on `serverless-dca-prototype`. Builds directly on the
existing `agent/new/serverless/` prototype and benchmark (see `README.md` in
this folder) rather than starting over.

## Reframing the question first, honestly

Ruqa's quote, from the Aug 3 meeting: *"You only need to pass three variables
into a serverless function... you're not relying on a database... you should
see a speed increase like massively"* and *"even if you scale to 10 million,
it won't be any different than one person calling it."*

Two different claims are bundled in there, and they need separating:

1. **"No database" makes a single request faster.** This was already tested,
   honestly, in this same folder — `benchmark.py` found removing the DB call
   from one DCA buy saves about 0.05 seconds. The real cost of one buy is
   over a second waiting on Jupiter's API, identical in both architectures.
   **This claim doesn't hold up.** Worth saying plainly rather than chasing it
   further.

2. **The system as a whole scales to many simultaneous users without you
   provisioning more servers.** This is the real claim, and it's still true
   in spirit even though claim #1 isn't. But it's not actually about having
   *zero* database — BITAGENTS fundamentally needs to remember who deposited
   what and when a DCA plan is next due, and that's persistent state by
   definition, no way around it. **What Ruqa is actually describing is a
   different hosting model**: code that runs as short-lived functions,
   invoked per request or per scheduled tick, that the platform auto-scales
   on demand — instead of one server process you keep running all the time,
   handling every request and running its own background scheduler thread
   in a loop.

That's the real distinction: **not "has a database" vs. "has no database" —
it's "always-on server" vs. "auto-scaling functions."** Both need somewhere
durable to remember state. The difference is whether a persistent process is
sitting there the whole time doing it, or whether the platform spins up
exactly as much compute as there is work to do, right now, and nothing more.

## The good news: this week's scheduler fix already IS the hard part of this

The scheduler rewrite from earlier this week (`db.claim_due_dca_plans`,
`SELECT ... FOR UPDATE SKIP LOCKED`) wasn't built with this in mind — it was
built to make the *current* server safe to run as more than one instance.
But the property it guarantees — many concurrent callers can claim from the
same queue of due work and never claim the same item twice — is *exactly*
what a real serverless deployment needs too. A Vercel Cron trigger, a retry
after a timeout, or the platform simply scaling up under load can all mean
the tick function gets invoked more than once at the same moment. The claim
logic doesn't care whether the callers are threads in one long-lived server
or completely separate, independent function invocations spun up by the
platform — it's correct either way, for the same reason.

**Proved this today**, not just reasoned about it: rewrote `dca_tick.py`
(previously a local JSON file with zero protection — the same class of bug
this week's main fix closed, just never caught here because it only ever
ran as a single local loop) to use the same claim-and-lease pattern against
a small Postgres table. Then fired three simultaneous calls to `tick()` at
once, simulating what real serverless auto-scaling does. Result: all 4 due
test plans were claimed and executed exactly once each, correctly split
across the three simultaneous invocations, zero double-claims.

This means the scheduler-safety work from earlier this week isn't a
separate track from what Ruqa asked for — it's the foundation piece,
already built and already proven to extend to this exact use case.

## What a real move to this model would actually require

1. **The HTTP-facing side** (`agents_api.py`'s chat/deposit/withdraw routes)
   would become individual serverless functions instead of one persistent
   FastAPI process — realistic options are Vercel's Python runtime (the
   frontend is already on Vercel, so this keeps everything on one platform)
   or a comparable provider. This is a genuinely bigger lift than the
   scheduler piece: FastAPI's shared setup (DB pool, cache) would need to
   adapt to a per-invocation lifecycle instead of a long-lived process.

2. **The scheduled side** (DCA/Volume/EasyA due-job execution) becomes a
   cron-triggered function instead of an in-process thread — this is the
   piece just proven above, and the smaller, lower-risk half of this move.

3. **Multi-wallet ties in naturally here, not separately** — per-user
   derived wallets (this week's other workstream) don't care whether the
   code deriving and using them runs in a persistent server or a serverless
   function. If both efforts land, the natural order is multi-wallet first
   (it's further along and closer to real), then wire the stateless
   execution model in underneath it, not the other way around.

## What's still genuinely unresolved, and can't be settled from a laptop

The original prototype's README already flagged this honestly: Ruqa's "10
million users, no different than one" claim is about *behavior under real
concurrent load against real deployed infrastructure* — the current
always-on server (even with this week's fixes) vs. real serverless
functions. That needs an actual load test against something actually
deployed, not a local benchmark. This is the next real checkpoint, and it
needs a decision on where to run it — a small real deployment (Vercel
functions, a KV/Redis-equivalent for the tick state) would need setting up
before that test can happen, which is a bigger step than anything scoped
here so far.

## Recommended next step

Given multi-wallet is further along and was the explicit near-term priority,
suggest: finish that first, then come back to actually standing up a small
real serverless deployment (not just a local prototype) to run the
concurrent-load test that would finally give a real answer to Ruqa's actual
claim — rather than splitting focus across both bigger builds at once.
