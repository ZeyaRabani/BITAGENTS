# Agent Launchpad — how it works right now, and questions for you

Everything below is on `serverless-dca-prototype`, not `Codex`. Nothing here has been merged
into production or touched anything you're working on. Written so you can review it without
having to reverse-engineer it from the diff.

## The idea, in one line

`/launch` is a pump.fun/EasyA-Kickstart-style feed of agents. `/launch/create` is a chat — no
form — where a "builder" AI has an open-ended conversation with the user and configures a new
agent on their behalf, then launches it. **Agents are not tokens** — no minting, no bonding
curve, nothing on-chain at launch time. This was explicitly decided, not an oversight.

## How it actually works, end to end

1. **User opens `/launch/create`, connects wallet, starts talking.** No fields, no form —
   `AgentBuilderChat.tsx` is a chat console, same shape as the existing agent consoles.

2. **The "builder" is just another agent.** `agent_builder.py` is not a special system — it's a
   normal agent running on the exact same `run_tool_agent()` runtime every other agent uses
   (`agent_tool_runner.py`). Its job is to ask good follow-up questions and progressively fill in
   a draft via tool calls: `set_agent_field`, `set_agent_personality` (it writes the launched
   agent's actual system prompt — the user never writes one), `set_tool_scope`,
   `select_agent_capabilities`, `show_draft`, `finalize_and_launch`.

3. **The draft lives in a new `custom_agents` table** (see `db.py`) from the very first message —
   `status` starts at `draft`. Columns: `name`, `handle` (not a ticker — see below),
   `category`, `description`, `system_prompt`, `model_tier`, `tool_scope`
   (`read_only`/`trading`), `enabled_tools` (JSONB list), `creator_fee_share_pct` (defaults 20%,
   **not actually paid out anywhere yet** — see questions), `status`.

4. **Capabilities come from a fixed catalog, never generated code.** `agent_tool_catalog.py` has
   5 read-only tools, all thin wrappers around functions you already wrote and ship in production
   today: `resolve_token`, `get_onchain_token_profile`, `compare_onchain_tokens`,
   `analyze_wallet_profile`, `get_wallet_recent_activity`. The builder sees descriptions of all 5
   in its system prompt and calls `select_agent_capabilities` with whichever subset fits what the
   user described. **No trading tools exist in the catalog at all** — `tool_scope="trading"` is
   settable but currently grants nothing extra; `get_tool_registry()`/`get_tool_schemas()` only
   return tools tagged `risk_tier="trading"` when explicitly asked for that tier, and there are
   zero registered, so there's no live code path to fund-moving capability yet. Deliberate,
   pending your input (see questions).

5. **Confirm before launch.** The builder proposes the finished draft and only calls
   `finalize_and_launch()` after the user explicitly confirms — same propose/confirm pattern your
   Hedge Fund strategy proposals already use. `finalize_and_launch` flips `status` to `testing` and
   stamps `testing_started_at`.

6. **24h creator-only testing window**, then auto-promote. `db.promote_ready_test_agents()` flips
   `read_only` agents from `testing` → `live` once 24h has passed — **nothing calls this function
   on a schedule yet**. It exists, it's correct, it just needs a cron/scheduler hook (see
   questions — this is the one place I'd want your scheduler pattern, not mine, since you already
   have working cron infra via `api/cron/tick.py` on the multiwallet project).
   `trading`-scope agents are deliberately excluded from auto-promotion — need manual review,
   which doesn't exist yet either.

7. **Launched agent runs on `custom_agent_runtime.py`** — loads the DB row, resolves
   `enabled_tools` + `tool_scope` against the catalog, calls the same `run_tool_agent()` runtime
   with the creator-authored system prompt. `record_custom_agent_run()` bumps `runs`/`volume_usd`
   stats shown on its marketplace card. No fee deduction happens here yet (see questions).

## Where the code actually lives (this tripped me up, flagging it for you too)

Two separate things had to be deployed, and I want you to know both changed:

- **`agent/new/`** — the real source: `db.py`, `agent_builder.py`, `custom_agent_runtime.py`,
  `agent_tool_catalog.py`, plus new routes on `agents_api.py` (`/agents/builder/chat`,
  `/agents/custom`, `/agents/custom/mine`, `/agents/custom/{id}`, `/agents/custom/{id}/chat`).
- **`vercel-multiwallet/api/index.py`** — I added the *same* 5 routes here too (under `/api/...`
  prefix), because that's the only backend actually deployed anywhere reachable from the live
  frontend right now. **I also full-synced `agent/new/ → vercel-multiwallet/agent/new/`** (its
  own bundled copy, per how that project already worked before I touched it) rather than
  cherry-picking imports — the dependency chain went deep enough (`agent_tool_catalog` →
  `token_research_agent` → `kickstart_copilot_agent` → ...) that partial-copying risked a
  production `ImportError`. `.env` was excluded from the sync.
- Frontend's `AGENTS_API_URL` on Vercel was an **empty string** (not unset — I checked), which
  silently broke every chat feature on that deployment, not just this one. I pointed it at
  `https://bitagents-multiwallet-test.vercel.app/api`, which is the serverless backend above, not
  wherever your "real" production backend actually is (I don't know if `zeya-bitagents.onrender.com`
  is still your staging box, or if there's a different one now — genuinely don't know, ask below).

## Known, real problem I couldn't fix myself

Every agent on the platform — not just this one — is hard-locked to one model. From
`hosted_llm.py`:

```python
def resolve_capix_model(_requested):
    """Always use the configured CapIX model (default: meta-llama/llama-3.1-8b-instruct).
    Agent-local MODEL tags are ignored so CapIX cannot route tool calls to a different
    upstream model."""
    return CAPIX_MODEL
```

`agent_builder.py`'s `BUILDER_MODEL = "openai/gpt-4o-mini"` has **never actually taken effect** —
this function ignores whatever's passed in. In live testing, the builder started narrating tool
calls as literal text (`set_agent_field(name="Whale Watcher", ...)` printed into the chat, and a
hallucinated `set_agent_personality(proactive=True)` — that parameter doesn't exist in my schema
at all) instead of making real structured function calls. My read: the 8B model this forces
everyone onto isn't reliable enough for a task this open-ended (infer category from free
conversation, write a whole system prompt, pick tools from a catalog in one pass). I didn't touch
`resolve_capix_model` since it's shared infra every agent depends on — not mine to change
unilaterally.

## Questions for you

**On the model lock:**
1. Why does `resolve_capix_model` hard-ignore the requested model — was this a fix for a specific
   incident, or just the simplest thing that worked at the time?
2. Is there any config path to get a stronger model (even just for this one agent) — a different
   CapIX model string that's actually been tested with tool-calling, or do we need an OpenRouter
   key added? I checked `.env` — no `OPEN_ROUTER_API`/`OPENROUTER_API_KEY` currently set.
3. If neither is viable soon, is it worth me rewriting the builder to need less from the model per
   turn (smaller, more constrained tool set, more rigid conversation structure) so it works
   within what the 8B model can actually do reliably?

**On wallet provisioning (ties directly to your migration work):**
4. When a `trading`-scope custom agent eventually needs a real wallet, can the wallet-provisioning
   function you're building for the Circle migration accept an arbitrary `agent_id`, not just the
   fixed set of existing agent types? That's the one dependency this whole feature has on your
   current work — I don't need anything from you now, just want the interface to stay generic so
   this can plug in later without you re-touching it.
5. Where are you at on that migration right now — still blocked on the Volume Agent RPC issue from
   the wallet-migration meeting, or has that moved?

**On persistent memory (also yours):**
6. Are you using `chat_sessions`/`chat_messages` for persistent memory, or something new? I built
   the launchpad chat on those existing tables — if you're about to change their shape, tell me
   before I build more on top of them.

**On product decisions I made assumptions about — correct me if wrong:**
7. Creator fee-share: I added `creator_fee_share_pct` (defaults 20%) to the schema, but **nothing
   actually pays it out** — no fee-deduction code exists for custom agents at all yet. What split
   did you and Zeya actually agree on, and do you want to build the payout logic or should I?
8. Should `promote_ready_test_agents()` (the 24h auto-promotion) run on your existing cron
   pattern from `api/cron/tick.py`, or somewhere else?
9. Is 5 read-only tools the right starting catalog, or are there specific capabilities you'd
   rather I prioritize wrapping next?

**On deployment / cleanup:**
10. Is `zeya-bitagents.onrender.com` still your real staging backend? If so, should
    `AGENTS_API_URL` point there instead of the Vercel serverless one I used?
11. Should this whole feature move to `Codex` at some point, or stay on
    `serverless-dca-prototype` until it's further along?
12. I (via Zeya's Vercel access) accidentally created a stray, unrelated Vercel project called
    `frontend` while fixing a deploy command from the wrong directory — it has one failed
    deployment in it and nothing else. Fine to just delete it, or is anyone using it?
