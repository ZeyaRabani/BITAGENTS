# Multi-wallet DCA — Vercel serverless deployment

Live at https://bitagents-multiwallet-test.vercel.app — a completely separate
Vercel project from the main bitagents.app site, its own Neon database branch,
its own environment variables. Real mainnet, not a devnet demo.

## Why this exists

Two things combined into one deployment:

1. **The multi-wallet DCA feature** — real deposits, plan creation, and
   withdrawals through each user's own derived wallet (see
   `agent/new/docs/per-user-wallets-scoping.md` and `agent/new/dca_multiwallet.py`
   in the main repo).
2. **A real test of Ruqa's stateless architecture proposal** — this is not
   `agents_api.py` lifted onto Vercel. That app starts in-process background
   threads at startup for its schedulers, which has no meaning in a serverless
   function (no persistent process for a thread to run in). `api/index.py`
   here has zero background threads. The recurring DCA-execution side
   (`api/cron/tick.py`) is a Vercel Cron-triggered function instead — reuses
   the same `SELECT ... FOR UPDATE SKIP LOCKED` claim pattern already proven
   safe under concurrency, so overlapping/concurrent cron invocations can
   never double-execute the same plan.

## Structure

- `api/index.py` — the HTTP API: health, wallet auth, and the multi-wallet
  DCA endpoints (balance/plan/plans/withdraw). Deployed as a single Vercel
  Python function; `vercel.json` rewrites all `/api/*` traffic to it except
  `/api/cron/tick`.
- `api/cron/tick.py` — claims and executes due multi-wallet DCA plans.
  Requires `Authorization: Bearer $CRON_SECRET` — Vercel's own Cron trigger
  sends this automatically; anything else gets a 401.
- `agent/new/*.py` — a **copy** of the specific backend modules this needs
  (`agent_wallets.py`, `db.py`, `dca_agent.py`, `dca_multiwallet.py`,
  `deposit_ledger.py`, `hosted_llm.py`, `shared_governance.py`,
  `wallet_auth.py`), not a symlink or shared path — `includeFiles` in
  `vercel.json` can only bundle files inside this project's own directory
  tree, not sibling directories in the monorepo. **If those files change in
  the main `agent/new/` directory, re-copy them here before redeploying** —
  they will not update automatically.

## Known limitation: cron frequency

Vercel Hobby accounts only support once-daily cron schedules — `vercel.json`
is set to `0 0 * * *` (midnight UTC) accordingly. For interactive testing,
trigger a tick manually instead of waiting for the schedule:

```bash
curl -H "Authorization: Bearer $CRON_SECRET" https://bitagents-multiwallet-test.vercel.app/api/cron/tick
```

## Environment variables (set on the Vercel project, production)

`DATABASE_URL` (Neon, own branch — not the production database),
`MULTI_WALLET_MASTER_SEED`, `DCA_WALLET_PRIVATE_KEY` (fee collector),
`SOLANA_CLUSTER`, `SOLANA_RPC_URL`, `DB_POOL_MAX_CONNECTIONS` (kept small —
3 — since serverless can multiply concurrent connection pools across many
simultaneous invocations, unlike one long-lived server), `CRON_SECRET`,
`CORS_ALLOW_ORIGINS`.

## Verified, not just deployed

- Real end-to-end auth + balance flow against the live URL (real mainnet
  RPC, real Neon DB, real serverless function — not local).
- 3 concurrent users against the live deployment: 3 genuinely different
  deposit addresses, zero collisions.
- Cron tick endpoint: correctly rejects unauthorized calls (401), correctly
  executes with the right secret, correctly reports zero claimed when
  nothing is due.
