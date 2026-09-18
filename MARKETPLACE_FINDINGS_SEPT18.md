# Marketplace: what we fixed today, and what we found testing it live

For Harshal — everything below was verified directly against the database and
code, not just observed in the chat UI. Branch: `fix-agent-creation` (cut from
`Marketplace`).

## 1. Fixed: agent creation was silently not saving

The builder chat would confidently say "I've launched your agent" while the
database row stayed an empty draft — `name: None`, `enabled_tools: []`. Root
cause: `agent_builder.py` requests `openai/gpt-4o-mini`, but
`resolve_capix_model()` in `hosted_llm.py` always overrides any requested
model to the platform-locked model (`CAPIX_MODEL`, currently
`meta-llama/llama-3.1-8b-instruct`) — and that model doesn't reliably call
the tools that actually persist the draft (`set_agent_field`,
`select_agent_capabilities`, `finalize_and_launch`). It narrates success in
prose instead of calling anything.

**Fix**: `agent_builder.py` now calls `call_openrouter` directly
(`agent_tool_runner.py` gained an `llm_call` override param for exactly this),
bypassing CapIX for this one agent only. Every other agent — DCA, Volume,
Hedge Fund — is untouched and still goes through CapIX exactly as before.
Also tightened the builder's system prompt to explicitly require a tool call
in the same turn a field is mentioned, and to require `finalize_and_launch`
the moment the user confirms rather than asking another question.

Verified end-to-end, twice: a full 4-turn conversation (describe → answer →
confirm → confirm) now produces a real DB row with `status` going
`draft` → `testing`, non-empty `name`/`handle`/`enabled_tools`.

## 2. Built: proof that background execution is possible

Nothing today lets a launched agent keep working after its chat session
ends — everything only "thinks" while a user is actively typing. Built a
minimal, stateless Bitcoin price-alert mechanism (`btc_price_alert.py`) to
prove the pattern: each check is a fresh, disposable call that trusts only
what's in the database (same shape as `vercel-multiwallet/api/cron/tick.py`'s
`claim_due_dca_plans()`), fetches the real price, compares to a stored
baseline, and exits. No memory held between calls, no open tab, no live
process. Verified across genuinely separate process invocations.

This isn't wired into anything yet — no cron trigger, no UI. It's a
standalone proof, exposed via 4 test-only HTTP endpoints
(`/btc-alert/create`, `/btc-alert/{id}`, `/btc-alert/{id}/check`,
`/btc-alert/{id}/log`) so it could be tested without needing this to be a
real product feature yet.

## 3. Found by testing the real thing end-to-end (not fixed yet)

Zeya launched a real agent through the actual `/launch` chat UI today
("Whale Watcher" — monitors a wallet, alerts on big moves). Three things
surfaced that the comparison experiment (BITAGENTS vs GrokBot vs Eve) will
immediately expose if we don't address them first:

**a. There is no email tool, anywhere.** The agent offered to "alert you via
email" and never asked which address to send to — not because it skipped a
step, but because grepping the entire tool catalog
(`agent_tool_catalog.py`) turns up nothing email-related. It fully
hallucinated a capability with zero backing code. This is the same
"talking about a thing ≠ doing it" failure mode as bug #1, just on the
runtime side, and there's nothing to wire up yet since the tool doesn't
exist at all.

**b. A launched agent's `model_tier` is decorative.** `custom_agent_runtime.py`
picks a model from `CUSTOM_AGENT_MODEL_BY_TIER` based on the agent's stored
tier (e.g. `balanced` → `openai/gpt-4o-mini`), but calls the default
`call_llm`, not `call_openrouter` — so it goes through CapIX, which
overrides it to the same locked `meta-llama/llama-3.1-8b-instruct` regardless
of tier. Every launched agent runs on the same small model today, no matter
what a user (or the builder) picked.

**c. A launched agent becomes invisible to its creator.** `finalize_and_launch`
moves a draft into `status = 'testing'` for the mandatory 24h window. Two
gaps compound here:
   - `promote_ready_test_agents()` (`db.py`) is the function meant to flip
     `testing` → `live` after 24h — nothing calls it. No cron, no scheduled
     job. An agent will sit in `testing` forever once created.
   - There's no page in the frontend that shows a user their own agents at
     all (live or testing) — the API (`GET /agents/custom/mine`) exists but
     nothing calls it. Right now, after creating an agent, a user has no way
     to find it again in the product.

## Suggested next step

Before running the GrokBot/Eve/BITAGENTS comparison on an email-alert agent
specifically (which is the exact test Zeya wants to run), (b) and (c) above
should get fixed and a real `send_email` tool should exist — otherwise the
comparison isn't testing BITAGENTS' actual ceiling, it's testing a feature
gap we already know about.
