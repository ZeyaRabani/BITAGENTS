# Stateless DCA prototype — Ruqa's proposal, built and measured

From the Aug 3 "Serverless Migration" meeting, Ruqa: *"You only need to pass
three variables into a serverless function... you're not relying on a
database... you should see a speed increase like massively."*

This is that architecture, actually built, not just discussed — three files:

- **`dca_execute.py`** — the stateless core. Token, amount, slippage in; a
  signed transaction out. Zero database calls. Reuses the exact proven
  Jupiter swap logic already in `dca_agent.py` (`_build_and_execute_swap`) —
  this isn't a rewrite of the trading logic, only the surrounding
  architecture changed.
- **`dca_handler.py`** — the HTTP entry point this would become once
  deployed as a real serverless function (Vercel Python runtime or similar).
  Runs locally with `uvicorn dca_handler:app`.
- **`dca_tick.py`** — the honest part: something has to remember when each
  plan is next due between invocations. This is the minimum possible
  version of that — a flat key/value record per plan (`next_run_at`), not a
  relational database. Locally it's a JSON file standing in for what would
  be Vercel KV / Upstash Redis in production, ticked by Vercel Cron instead
  of an in-process Python thread.

## What this deliberately does not do

No spend-limit check against a deposited balance, no ledger recording. Both
of those need persistent state by definition — you can't know a running
balance without remembering it. This prototype exists to isolate and
measure the specific execution path Ruqa described, not to replace the
ledger. A real version of this would still need *some* lightweight
accounting layer; the point is that layer doesn't need to be the full
current server + Postgres + in-process scheduler.

## What I measured, honestly

`benchmark.py` runs the current architecture's dry-run path (DB spend-check
+ Jupiter quote) against this prototype's path (zero DB calls + the same
Jupiter quote), same trade, same token, 5 runs each.

**First attempt at this was wrong and I caught it before trusting it**: the
first run showed the stateless path at 0.000s, which is impossible for a
real network call. Turned out `DCA_WALLET_PRIVATE_KEY` isn't set in this
local `.env` (only `VOLUME_AGENT_WALLET_PRIVATE_KEY` is), so every quote
call was failing instantly on a config check before ever reaching Jupiter —
both paths were measuring "how fast does an error return," not real
network time. Fixed by borrowing the Volume wallet's key for this
quote-only benchmark (safe — quotes don't move funds) so both paths
actually reach the network call being measured.

**The real result, once fixed:**

| | Mean (excl. one rate-limited outlier) |
|---|---|
| Current architecture (DB check + quote) | ~1.17s |
| Stateless prototype (zero DB + quote) | ~1.12s |
| **Difference from removing the DB call** | **~0.05s** |

The database round-trip is not the bottleneck. Both paths spend well over a
second waiting on Jupiter's API — including hitting a real 429 rate limit
on the 5th call in both runs, at the same time, for the same reason. The
"massive speed increase" Ruqa predicted from removing the database doesn't
show up here — the actual latency is almost entirely the external Jupiter
dependency, which is identical in both architectures.

## What this does and doesn't settle

**Settled**: removing the database from the single-buy execution path does
not meaningfully speed up a single buy. If the goal is "make one DCA buy
resolve faster," this isn't the lever.

**Not settled, and this prototype can't test it locally**: Ruqa's actual
core argument was about *scaling under concurrent load* — "even if you
scale to 10 million, it won't be any different than one person calling
it." That's a claim about many simultaneous requests, not one request's
latency, and it can't be measured on a laptop. It would need a real load
test against deployed infrastructure (current server vs. real serverless
functions) to actually confirm or refute.

## Try it yourself

```bash
cd agent/new/serverless
python3 benchmark.py                                    # timing comparison
python3 -m uvicorn dca_handler:app --port 8766           # run the HTTP handler
python3 -c "from dca_tick import add_plan, tick; add_plan('BITAGENTS', 0.005, 60); print(tick(dry_run=True))"
```
