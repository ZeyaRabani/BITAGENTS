# Handoff notes — `serverless-dca-prototype`

For Harshal. This branch now covers two separate pieces of work:

1. **Volume Agent fixes** (below) — several layers of fixes found by actually running real campaigns end-to-end against live BITAGENTS on mainnet, on top of your merged work.
2. **DCA Agent: per-user wallets + Ruqa's stateless serverless architecture** — see **"Part 2"** further down. This is new since the Volume Agent work below and is a separate track entirely: it's about the DCA agent, not Volume, and about two things Zeya specifically wanted tested — (a) every user getting their own on-chain wallet instead of everyone sharing one pooled agent wallet, and (b) a real test of whether Ruqa's proposal to make the backend stateless/serverless actually works, not just whether it sounds right on paper.

Both pieces were built and tested independently — nothing in Part 2 touches or depends on the Volume Agent code below. Jump straight to **Part 2** if that's what you're here for.

---

## Part 1 — Volume Agent

For Harshal. This branch = `origin/Volume-bot` + your merged fixes (already in, see "Layer 1" below) + several layers of fixes found by actually running real campaigns end-to-end against live BITAGENTS on mainnet. Nothing here duplicates your work — this picks up from exactly where your merge left off. **See Layer 4 at the bottom of Part 1 for the exact test we ran and step-by-step instructions to reproduce it yourself.**

**Branch lineage**, oldest to newest:
```
origin/Volume-bot (7408a25)          ← what's currently pushed/shared
  └─ bbdcbde                          ← ATA rent reclaim + consecutive-failure persistence (prior session)
       └─ 246eeb8                    ← merge of YOUR fixes (4dc3119) with the above
            └─ (this branch's new commit) ← everything below
```

---

## Layer 1 — already in `246eeb8` (your work + earlier fixes, for context)

This is what the code looked like **before** this branch's new changes — i.e. what I pulled and started from today.

- **Meteora pool-creation script** (`scripts/create_dlmm_pool.cjs`): CommonJS port because the ESM build of `@meteora-ag/dlmm` breaks under current Node (`ERR_UNSUPPORTED_DIR_IMPORT`). Also verifies the pool account actually exists on-chain via `getAccountInfo` before reporting success — the original bug where the script said "created" but Solscan/Meteora showed nothing was a discarded `confirmTransaction` result plus no existence check.
- **Swap routing unrestricted** (`volume_agent.py`): removed a hardcoded `"dexes": "Meteora DLMM"` filter on the Jupiter swap request. Real tokens (including BITAGENTS) mostly trade on DAMM v2/DBC pools, not DLMM — the filter made every swap fail with "no routes found."
- **Pool-check recognizes non-DLMM liquidity** (`meteora_dlmm.py`, `check_jupiter_route_exists` + your `ensure_meteora_dlmm_pool`/`meteora_pool_app_url` additions): if Jupiter can already route a pair through any pool type, the agent reuses it instead of creating a redundant new DLMM pool. Your merge added the `/volume/pool/check` and `/volume/pool/ensure` manual endpoints/buttons on top of this.
- **Sell-leg fee bug fixed**: fee was computed from the base-token quantity instead of SOL proceeds, corrupting the ledger by orders of magnitude.
- **Safety rails added**: minimum trade size (`MIN_VOLUME_TRADE_SOL`, default 0.005 SOL — below this an ATA rent cost alone fails the tx), and auto-pause after `MAX_CONSECUTIVE_FAILURES` (default 3) so a broken/underfunded campaign stops retrying instead of burning fees forever.
- **`consecutive_failures`/`last_error` columns** added to `volume_campaigns` (were missing from schema, so every write to them was silently dropped and auto-pause never actually persisted).

All of the above was verified with real on-chain signatures at the time. Layer 2 is what's new.

---

## Layer 2 — new in this branch

Found by actually running a full campaign for BITAGENTS through the UI (not just code review), on the real Neon database, real mainnet RPC.

### 1. Balance check double-counted a campaign's own reservation against itself (`volume_ledger.py`, `volume_agent.py`)

**Symptom**: a freshly-created campaign with exactly enough budget would fail its very first cycle with "Insufficient SOL balance," 3 times in a row, and auto-pause — instantly, silently. Looked like "nothing happens."

**Root cause**: `check_user_can_spend_volume` computes `available = deposited − spent − reserved_for_other_campaigns`. But `_reserved_for_campaigns` counted **every** active/provisioning/paused campaign, including the one currently trying to spend — so a campaign would reserve its entire remaining budget against itself, then check if it could afford its own next cycle against a balance that already had that same budget subtracted. A campaign needing 0.2005 SOL total, with 0.24 SOL deposited and 0.035 already spent from earlier tests, would see `0.24 − 0.035 − 0.2005 (itself) ≈ 0.0042 SOL available` — nowhere near enough for even one 0.02 SOL cycle.

**Fix**: `_reserved_for_campaigns`, `get_volume_user_balances`, and `check_user_can_spend_volume` now all take an optional `exclude_campaign_id`. The two call sites that check a specific campaign's own affordability (`_run_volume_execution`'s per-cycle check, and `provision_campaign_infrastructure`'s pool-cost check) now pass their own campaign id so a campaign's own reservation never blocks its own spend.

**Verified**: re-ran the same campaign after the fix — it correctly saw the full available balance and completed all 10 cycles.

### 2. Sell-leg proceeds were never credited back to the user's ledger (`volume_ledger.py`, `volume_agent.py`)

**Symptom**: the campaign's own `spent_so_far`/`total_budget` tracking said 100% of budget spent, but that's expected — the real problem is the user-facing **available balance** dropped by the full buy amount every cycle and never got the sell proceeds back, overstating real cost by roughly **20x**.

**Root cause**: each cycle does buy (SOL→BITAGENTS) then sell (BITAGENTS→SOL) — the sell leg puts SOL back into the *same* agent wallet. `_run_volume_execution` recorded `record_user_spend_volume` for the buy and `record_volume_platform_fee` for both legs' fees, but nothing ever recorded the sell leg's SOL proceeds as a credit. That SOL was genuinely sitting back in the wallet, but the user's ledger balance had no entry for it — so it looked spent forever.

**Fix**: added `record_user_credit_volume()` (`volume_ledger.py`) — inserts a `direction="deposit"`, `reference_type="volume_sell_return"` ledger row. Does **not** re-verify an on-chain transfer (unlike the real-deposit path) because the agent itself already executed and confirmed the swap; this just reflects funds that are already confirmed to have landed back in the shared wallet. Wired into `_run_volume_execution` right after the sell-fee is recorded (`volume_agent.py`).

**One-time backfill (already run against production, not a repeatable script)**: 16 sell legs across 3 already-completed campaigns on the live wallet had this gap. Manually replayed `record_user_credit_volume` for each from the campaigns' stored `executions` history — restored **0.124852 SOL** to the real user's available balance (confirmed before/after via `get_volume_user_balances`). This was a one-off data fix on the shared Neon DB, not something this branch runs automatically — if any other wallet had run campaigns before this fix landed, the same backfill logic would need to be re-applied for them (check `SELECT DISTINCT user_wallet FROM volume_campaigns` — at the time of this fix, only one wallet had ever used it).

### 3. New simplified UI: `/agents/volume2`

New page + component (`frontend/src/app/agents/volume2/page.tsx`, `frontend/src/components/agents/VolumeAgentSimpleConsole.tsx`). Same wallet-connect/deposit/campaign-status machinery as the original `/agents/volume` page (reuses `VolumeAgentDeposit`, `VolumeCampaignPanel`, `useVolumeWalletAuth` unchanged) — the difference is purely the campaign-creation UI:

- BITAGENTS mint (`iu3A7azWTm3zQSk81SUC1JctB4zPYnxLmcmqq71EASY`) and SOL are hardcoded — no token fields.
- No manual "Check on Meteora" / "Create on Meteora" widget (not needed for BITAGENTS, and it was a source of confusing errors — see below).
- Three preset buttons instead of a manual form: Quick test (~0.2 SOL), Standard (~1 SOL), Full day (~3 SOL).

This exists specifically because Zeya found the original page too complex for day-to-day use as CEO, not because the original page is being deprecated.

### 4. Failed campaigns now show why (`VolumeCampaignPanel.tsx`, `volumePlanClient.ts`)

The campaign list showed `status: failed` with zero explanation — `last_error` was already being written to the DB (Layer 1's auto-pause work) but never read by the frontend. Added `last_error`/`consecutive_failures` to the `VolumeCampaignSummary` type and a warning block on failed campaigns showing the actual error (e.g. "Stopped after 3 failed attempts: Insufficient SOL balance...").

---

## Layer 3 — new-token pool creation now actually seeds liquidity

This directly answers what Harshal reported in the "Swaps Infrastructure and DNS Handoff" call (Jul 23): *"it is not creating the pool for the new tokens, and for the existing tokens, it is not depositing the funds."*

**Root cause, confirmed by reading the script line by line**: `create_dlmm_pool.cjs` built a payload including `tokenAmount`/`quoteAmount` (clearly intended as "how much liquidity to seed with"), but the script never read either field — it only created an **empty pool shell** via `createCustomizablePermissionlessLbPair` and stopped. There is no liquidity-provisioning code anywhere else in the repo either. An empty DLMM pool can't fill any swap, so a newly "created" pool looked broken the moment anyone tried to trade against it. This is one bug, not two — both halves of Harshal's report are the same missing feature.

**Fix** (`scripts/create_dlmm_pool.cjs`, `meteora_dlmm.py`, `volume_agent.py`):
- After the pool-creation transaction is verified on-chain (Layer 1's check), the script now does a second step: opens a DLMM position and deposits real `tokenAmount` + `quoteAmount` liquidity into it (Meteora's `initializePositionAndAddLiquidityByStrategy`, Spot strategy, ±10 bins around the starting price — narrow and simple, since our own trade sizes are small). Same "verify on-chain before reporting success" pattern as the pool-creation check itself: it reads the position back after confirming, and fails loudly if the position doesn't actually exist.
- `provision_campaign_infrastructure` now reads the campaign's `seed_token_amount` (already existed as a stored field, was never wired to anything) and passes it through as the base-token side of the deposit.
- **A pool is no longer marked ready to trade unless liquidity actually landed.** If seeding fails, the whole provisioning is marked `failed` (same auto-pause path as any other failure) instead of silently leaving behind a pool address that looks fine but can't fill orders.
- **Accounting fix to match**: the SOL/token amounts are only charged to the user's ledger if the deposit actually succeeded — previously the full estimated pool cost was charged unconditionally regardless of whether anything real happened on-chain.

**Important, easy to miss**: `seed_token_amount` has to be set to something meaningful when creating a campaign for a genuinely new token. If it's left at 0, the pool creates fine but has no base-token liquidity to sell to buyers — the first buy attempt will fail with no liquidity on that side. This isn't validated in code (kept deliberately simple); it's on whoever creates the campaign to size it sensibly relative to their planned trade volume.

### The 2% fee concern — checked against live data, not guessed

Pulled a live Jupiter quote for BITAGENTS directly: `routePlan[0].swapInfo.label` = **"Meteora DAMM v2"**, `platformFee: null`. Two things this confirms:

1. **BITAGENTS is already trading through a real Meteora pool** — Jupiter's "no dedicated DLMM pool" fallback label was just a detection gap in our own code (see below), not a sign it was avoiding Meteora.
2. **Jupiter itself charges nothing extra on top.** The `platformFee` field is null because we don't set one, and Jupiter doesn't add its own by default. So switching "to Meteora" wouldn't change BITAGENTS's economics at all — it's already there.

The real number worth watching: a 0.01 SOL test quote showed **~1.35% price impact** — that's the pool's actual depth (~$19.6K TVL at the time), not a fee. That's the correct lever for the "50 cycles" concern: **pool depth**, not which venue routes the trade. This is exactly what the seeding fix above addresses for brand-new pools — seed them with enough real liquidity relative to planned trade sizes and price impact per cycle stays small. For BITAGENTS's *own* existing pool specifically, adding more liquidity to reduce that 1.35% further would require topping up a live DAMM v2 pool — a different Meteora program/SDK than the DLMM pools this branch creates, and a separate, larger task not included here.

**Also fixed** (`meteora_dlmm.py`, `check_jupiter_route_exists`): now reports which venue Jupiter actually routed through and whether it's Meteora, instead of a flat `"source": "jupiter"` label that made it look like Meteora wasn't involved at all. `check_pool_infrastructure` now reports `"source": "meteora (via Jupiter)"` when that's what's actually happening.

---

## Operational note: local backend vs. a real deployment

Worth flagging since it came up directly: **there is currently no deployed backend.** `frontend/.env.local` points `AGENTS_API_URL` at `http://127.0.0.1:8765` — every campaign so far (including the real on-chain test runs referenced above) has been executed by a Python process running on Zeya's own laptop, connecting out to the real Neon DB, real Jupiter, and real Solana mainnet RPC over his home internet.

This explains an oddity Zeya noticed: turning his WiFi off mid-campaign made everything stop (no DB reads, no RPC calls possible), and turning it back on resumed it correctly. That's expected for the *current* local setup, not a bug — but it also means, right now, **the entire Volume Agent depends on Zeya's laptop being on, connected, and this process still running.** No campaign for any user executes if that machine is off or asleep.

For a real deployment, the backend needs to run on an always-on host (the `.env.local.example` has a placeholder line for a Render service URL, but nothing is actually deployed there yet). Once that's live, campaigns keep running on the server's own connection regardless of anyone's local machine — that's the main practical reason to prioritize actually standing up that deployment before onboarding anyone beyond internal testing.

---

## What's still open for you

1. **No production deployment exists yet** (see above) — this is probably the single biggest blocker to this being usable by anyone but us.
2. **`VOLUME_AGENT_WALLET_PRIVATE_KEY`** needs to be set wherever the backend does end up deployed — generate a fresh dedicated key, don't reuse the local test key.
3. **`npm install` in `agent/new/scripts`** needs to happen in the deployed environment (Meteora pool-creation script's `node_modules` isn't committed).
4. **Ledger backfill scope**: if anyone besides Zeya's test wallet ran volume campaigns before this branch, they need the same sell-proceeds backfill (see Layer 2, #2) — check `volume_campaigns` for other `user_wallet` values.
5. **Fee collection is still purely bookkeeping**: the "0.25% per leg" platform fee is recorded in the ledger (reduces a user's available balance) but nothing actually moves it to a separate BITAGENTS-controlled wallet — all deposited/spent/fee SOL sits in one shared agent wallet. Worth a product decision on when/how to actually sweep fees out as real revenue.
6. **`.mjs` cleanup**: `create_dlmm_pool.mjs` is superseded by the `.cjs` version and unused — safe to delete once you've confirmed the `.cjs` version works in your environment too.
7. **Adding liquidity to BITAGENTS's own existing pool** (not new-pool creation, topping up the live one) is a separate, larger task — that pool is Meteora DAMM v2, a different program/SDK than the DLMM pools this branch creates and seeds. Not started.
8. **Orca was explicitly ruled out** for this round (Zeya's call) — the branch stays Meteora-only. Don't spend time on the "Ecura"/Orca idea from the Jul 23 call unless that changes.

## How this was tested

Full campaign (10 cycles, 0.01 SOL/leg) run against the live BITAGENTS/SOL pair on mainnet through the actual `/agents/volume2` UI, using Zeya's real deposited SOL on the real Neon production database (not a local test DB — there was no safe way to test the reservation/accounting bugs without the real ledger state that caused them). Every cycle's buy and sell signature was independently checked against Solana mainnet RPC directly (`getTransaction`, confirming `err: null`), not just trusted from this app's own database. The sell-proceeds backfill was verified by comparing `get_volume_user_balances` output before and after.

---

## Layer 4 — the exact end-to-end test we ran, and how to reproduce it yourself

This is specifically for you, Harshal, to independently confirm all of the above rather than take our word for it. Same principle we've held everything else to: don't trust the app's own database, check Solana and Dexscreener directly.

### What we ran

A 20-cycle campaign against the real BITAGENTS/SOL pair on mainnet, sized so the whole thing needed ~1 SOL:

- **trade_amount**: 0.025 SOL per leg
- **interval**: 1 minute
- **max_executions**: 20
- **total_budget** (auto-computed): 1.0025 SOL (0.025 × 1.0025 platform fee × 2 legs × 20 cycles)

Deposited 0.85 SOL on top of an existing balance to bring available SOL to 1.0747 — comfortably above the 1.0025 needed.

### Results — verified independently, not just from our DB

**Execution**: 20/20 cycles completed, `consecutive_failures: 0`, zero errors. Spot-checked the *last* cycle's buy and sell signatures directly against Solana mainnet RPC (`getTransaction`), not our own database — both confirmed with `err: null`.

**SOL balance**:
| | Before | After |
|---|---|---|
| Available SOL | 1.0747 | 1.0524 |

Net cost: 0.0223 SOL out of 1.0025 SOL used — **97.8% retained**. This is the direct answer to your "2% fee, unsustainable after 50 cycles" concern from the Jul 23 call: at this trade size, on this pool, the real cost across an entire 20-cycle campaign was ~2.2% *total*, not per cycle.

**Dexscreener, before vs. ~25 minutes later (after)**:
| | Before | After |
|---|---|---|
| 1h volume | $19.22 | $73.55 |
| 1h transactions | 1 buy / 0 sells | 20 buys / 20 sells |
| Market cap | $27,083 | $27,047 (−0.13%) |

Volume and transaction count moved exactly in line with our 20 cycles; price barely moved. That's the whole point of the agent working correctly — real visible volume, minimal price disruption.

### How to reproduce this yourself

**Option A — through the UI** (closest to how a real user would do it):
1. Go to `/agents/volume2`, connect your wallet, deposit SOL (the page shows exactly how much you need for whichever preset, or see Option B below for a custom size like ours).
2. Press one of the preset buttons, or for the *exact* test we ran, use the original `/agents/volume` page's "Quick create" form instead — it lets you set `trade_amount`, `interval`, and `max_executions` directly (0.025 / "1 minute" / 20).
3. Watch the campaign under "Volume campaigns" — it polls every 30s, so cycles should start appearing within a minute.

**Option B — direct backend call** (what we actually did, useful if you want to skip the UI and verify the backend logic in isolation):
```python
from volume_agent import create_volume_campaign
result = create_volume_campaign(
    base_token="iu3A7azWTm3zQSk81SUC1JctB4zPYnxLmcmqq71EASY",  # BITAGENTS mint
    quote_token="SOL",
    trade_amount=0.025,
    interval="1 minute",
    max_executions=20,
    user_wallet="<your wallet address>",
    name="Reproduction test",
)
```
Requires your wallet to already have enough SOL deposited (check first with `volume_ledger.get_volume_user_balances("<your wallet>")`).

**Verifying independently, don't trust our DB**:
- Pull the campaign's `executions` array (via `/volume/campaigns/{id}/executions` or straight from the `volume_campaigns` table) and check any signature directly against Solana: `getTransaction` via `https://api.mainnet-beta.solana.com` RPC, confirm `err` is `null`.
- Check `volume_ledger.get_volume_user_balances("<wallet>")` before and after for the real available-SOL delta.
- Check `https://api.dexscreener.com/latest/dex/tokens/iu3A7azWTm3zQSk81SUC1JctB4zPYnxLmcmqq71EASY` before and after for volume/mcap/price impact.

---
---

# Part 2 — DCA Agent: per-user wallets + Ruqa's serverless architecture

For Harshal, from Zeya's testing session. Two goals drove this, both explicit asks:

1. **"Operation Multi-wallet"** — today, every user of the DCA agent deposits into the *same* shared pooled wallet. Zeya wanted each user to get their **own** wallet instead, so one user's funds are never sitting in the same address as anyone else's.
2. **A real test of Ruqa's proposal** — Ruqa suggested making the backend stateless/serverless so BITAGENTS can scale faster. Rather than just discuss it, Zeya wanted it actually built and proven end-to-end on real infrastructure (real mainnet, real database, real serverless functions) — not a design doc.

Both are done, deployed, and tested with real money on mainnet. They also turned out to be one deployment, not two — see "Why these ended up combined" below.

**Everything in Part 2 is on a brand-new, completely separate deployment** — a different Vercel project, a different Neon database branch, from the main bitagents.app site and from wherever the pooled DCA agent currently runs. Nothing here can affect the production site. Live URLs:
- Frontend: `https://bitagents-multiwallet-frontend.vercel.app`
- Backend: `https://bitagents-multiwallet-test.vercel.app`

---

## 2.1 — Why per-user wallets, and how it works

**The problem with the pooled model**: every user's deposit goes into one shared agent wallet (`DCA_WALLET_PRIVATE_KEY`). The app's own database is the only thing keeping track of "whose money is whose" inside that wallet. If that bookkeeping is ever wrong — a bug, a race condition, an exploit — there's no on-chain separation protecting one user's funds from another's.

**The fix**: `agent_wallets.py` derives a unique Solana keypair per user, per agent, using SLIP-0010/BIP44 HD derivation from a single master seed:
```python
path = f"m/44'/501'/{agent_slot}'/{wallet_index}'"
Keypair.from_seed_and_derivation_path(master_seed, path)
```
`agent_slot` is fixed per agent (DCA=0, Volume=1, EasyA=2), `wallet_index` is a sequential per-user counter assigned on first use (`db.py`'s `get_or_create_wallet_index`, a `SERIAL` column — race-tested under concurrent signups). This means:
- Every user's DCA deposit address is **mathematically unique and different from every other user's**, and different from the same user's Volume/EasyA wallet.
- No private keys are stored per user — they're re-derived on demand from the one master seed (`MULTI_WALLET_MASTER_SEED` env var) whenever needed.
- The real balance the app ever trusts is **what's actually on-chain in that specific address**, checked fresh via RPC before every action — never a ledger sum. This was a deliberate reaction to how fragile the pooled model's ledger-as-source-of-truth approach is (see the withdrawal race fix below).

**One explicit product decision from Zeya**: no fee-payer wallet. Early drafts had BITAGENTS pre-funding each new derived wallet with a little SOL so users wouldn't need to hold SOL themselves. Zeya rejected this — users must deposit their own SOL to activate their wallet; BITAGENTS funding wallets was ruled out. `agent_wallets.MIN_SOL_TO_ACTIVATE_LAMPORTS` reflects this.

**Platform fee, redesigned**: under the pooled model, the 0.5% DCA fee was pure bookkeeping — there was nowhere else for it to go, it just stayed in the one shared wallet. That doesn't work anymore once funds are spread across many separate wallets. Now every successful buy does a **second, real on-chain transfer** of the fee out of the user's own wallet to a collector address — and the old pooled agent wallet is reused for this, deliberately: it stops holding user funds and becomes purely the platform's fee wallet. See `dca_multiwallet.execute_plan_now`.

**New code**: `agent_wallets.py` (derivation), `dca_multiwallet.py` (deposits/balance/create-plan/execute/withdraw, all real on-chain, no ledger trust), `db.py` additions (`wallet_mode` column on `dca_plans`, `agent_wallet_index` table). `dca_agent.py`'s scheduler now dispatches by `wallet_mode`: `'multiwallet'` plans execute through `dca_multiwallet`, `'pooled'` plans (the default, unchanged) execute through the existing pooled path — old and new coexist, nothing about the pooled agent changed behaviorally.

### A real bug this surfaced: the LLM was hallucinating successful plans

While testing multi-wallet through the actual chat UI, a plan came back as "created and running" in the chat reply — but no database row existed and no on-chain transaction happened. **Root cause**: `_parse_create_dca_request` (the deterministic, guaranteed-to-actually-execute parser that stages a plan for confirmation) only matched raw Solana mint addresses and required an explicit interval count ("every **3** hours"). A message phrased the more natural way — a ticker symbol ("...into BITAGENTS every minute", no count) — didn't match, silently fell through to the free-text LLM loop, and the model just *described* success in plain English without ever calling a tool that would make it real.

**Fixed**: symbol phrasing now falls back to `resolve_token()`, and a bare "every minute" now correctly defaults the count to 1 instead of requiring "every 1 minute" verbatim. Verified live by replaying the exact failing message against a throwaway wallet — it now correctly returns "Insufficient SOL balance" (a real check) instead of fabricating a plan. This fix applies to **both** the pooled and multi-wallet chat paths equally, since it's the same shared parser.

### Also cleaned up while testing

- **A real cross-instance fund-drain race** in withdrawals (pooled and multi-wallet both call `withdraw_user_tokens`/`dca_multiwallet.withdraw`): two concurrent withdraw requests could both read "sufficient balance" before either wrote its debit, double-spending the same funds if two server instances (or two overlapping requests) hit at once. Fixed with `pg_advisory_xact_lock` scoped to `(user_wallet, token)` in `deposit_ledger.py`, `volume_ledger.py`, `easya_trading_ledger.py` — same pattern applied everywhere withdrawals happen. Proven under real concurrent `threading.Thread` requests racing against a live server, not just reasoned about.
- **Stale test data**: found ~295 rows of 3-week-old Volume Agent test data in the shared local Postgres tied to Zeya's real wallet, making old balances look current. Confirmed the real on-chain balance was negligible before cleaning it up — this was a data hygiene issue, not a code bug.

---

## 2.2 — Ruqa's serverless proposal, actually tested

**Why this matters**: the current backend (wherever it's deployed — Render, a laptop, etc.) is a single long-running Python process. Its DCA/Volume/EasyA schedulers are background *threads* inside that one process. That model doesn't scale horizontally in the way Ruqa described — you can't just spin up more of it on demand, and if that one process goes down, everything stops (see Part 1's "Operational note" above — this exact failure mode already happened once with the Volume Agent).

**What "stateless serverless" actually requires, concretely**: no code can assume it's still running when the *next* request comes in. Specifically, nothing can be a background thread, because a serverless function has no persistent process for a thread to live in between invocations.

### What was built: `vercel-multiwallet/`

A new, completely separate deployment (not `agents_api.py` lifted onto Vercel — it's a from-scratch minimal app) with genuinely zero background threads:

- **`api/index.py`** — the HTTP API. Every request is a fresh, independent invocation; nothing is kept in memory between requests.
- **`api/cron/tick.py`** — this is the actual Ruqa-shaped piece. Recurring DCA execution as a **function Vercel Cron invokes on a schedule**, not a thread. Each invocation independently claims whatever's due right now and executes it, using the same `SELECT ... FOR UPDATE SKIP LOCKED` claim-and-lease pattern already proven safe under concurrency for the withdrawal race fix above — so even if Vercel invokes overlapping/concurrent ticks (which it does, in practice), a plan can never be double-executed.
- Its own Neon database branch (not production), its own env vars, its own mainnet RPC connection.

### Verified on real infrastructure, not simulated

- Real end-to-end auth + balance flow against the live deployed URL (real mainnet RPC, real Neon DB, real serverless function).
- 3 concurrent users tested against the live deployment: 3 genuinely different deposit addresses, zero collisions.
- Cron tick endpoint: correctly rejects unauthorized calls (401), correctly executes with the right secret, correctly reports zero claimed when nothing is due.
- **Real mainnet DCA executions fired through this exact architecture**, e.g. tx [`484bvyJ...`](https://explorer.solana.com/tx/484bvyJeKSDZgfgXYsSBrg3feNtZviGbfZg1xDYum372ToTfyvKw792dyyMPkqLVYdytBm81T9htW1HrvhY3auoe?cluster=mainnet) and [`5pGfjr...`](https://explorer.solana.com/tx/5pGfjrtCCdoEGA5xguRgJEEJKGSphbd1xXct1nQoQ9cMC4fzaT5PT9ucoD4uGmprLDPgCLzyznhg9qastG7b2LmZ?cluster=mainnet), each with its own platform-fee transfer, both claimed and executed by `api/cron/tick.py` against real user plans.

### Why these ended up combined into one deployment

Zeya asked for both to be built and tested on mainnet at the same time ("I want to do all of it at the same time to see if it works"). They turned out to compose naturally: the multi-wallet feature needed *some* backend to run on, and the serverless architecture needed *something real* to execute recurring, not a toy example — so the multi-wallet DCA feature became the real workload proving the serverless architecture, rather than two separate exercises.

### The original DCA UI now runs unmodified against this new backend

Initially this had a brand-new custom page (`/multi-wallet-dca`, still live, unchanged). Zeya then asked for the **exact same UI** as the existing DCA agent instead, at the same path (`/agents/dca`), with the LLM chat still working. Rather than rebuild the UI, the backend was extended to expose the **same route shapes** the existing `DcaAgentConsole`/`DcaAgentDeposit`/`DcaPlanPanel` components already call (`/chat`, `/wallet/agent`, `/wallet/balance`, `/wallet/deposit/verify`, `/wallet/withdraw`, `/plans`, etc.) — so those components run completely unmodified, just pointed at this backend instead of the pooled one. Underneath, every one of those routes is backed by `dca_multiwallet`, not the pooled wallet.

Two small, backward-compatible changes were needed in the shared frontend code (`frontend/`) to make this work, since they also affect the pooled deployment if this branch merges:
- `dca_agent.py`: `run_agent_with_actions`/`execute_tool` now take a `wallet_mode` parameter. In `"multiwallet"` mode, `create_dca_plan`, `withdraw_user_tokens`, `get_user_deposit_balance`, `execute_dca_now`, and `get_agent_wallet` are transparently swapped for `dca_multiwallet`-backed versions instead of the pooled functions — same tool names, same LLM-facing behavior, different execution underneath. Pooled mode (the default) is untouched.
- `wallet/agent` (the "what address do I deposit to" lookup) used to be answerable the same for everyone, with no login required — that doesn't work once every user has a different address. `fetchAgentWallet()`, its Next.js proxy route, and `DcaAgentDeposit.tsx` now pass the auth token through once the user signs in, and refetch when it becomes available. Backward compatible: the pooled backend ignores the token and answers exactly as before.

**Chat/LLM confirmed working end-to-end** against the live deployment with a throwaway keypair: real sign-in, real per-user deposit address returned, real chat reply, and a real natural-language "DCA into BONK" request correctly staged for confirmation and then correctly rejected for insufficient real on-chain balance (not hallucinated) — same anti-hallucination guarantee as the pooled agent, now proven on the multi-wallet path too.

### Known limitation, open for you: recurring execution needs a real heartbeat

Vercel's free (Hobby) plan only allows cron schedules to run **once daily** — `vercel.json`'s cron is set to `0 0 * * *` accordingly. In practice this was tested by triggering `api/cron/tick.py` manually (`curl` with the `CRON_SECRET`), which works correctly but obviously isn't a real unattended solution. This is the direct tradeoff of "stateless serverless": a long-running thread (like your pooled scheduler) gives itself a heartbeat for free; a stateless function has none, so *something* external has to call it on a schedule.

**Options discussed with Zeya, not yet decided**:
1. Upgrade the Vercel project to Pro (~$20/mo) for native frequent cron.
2. A free external pinger (e.g. cron-job.org) hitting the tick endpoint every 1–5 min — free, but external cron services generally don't go faster than ~1 min, and it's one more third-party dependency.
3. **What Zeya asked about last**: add a small always-on worker to the **existing Render account** (the same one your pooled scheduler already runs on) that loops every ~10s and calls the tick endpoint — same free-tier pattern you already use, just for this new backend too. Needs a Render API token to deploy; not yet done.

Whichever you land on, the tick endpoint itself is already correct and safe to call as often as you like (idempotent claim pattern, rejects unauthorized calls) — this is purely about *who* calls it, not a code change.

### Environment / operational notes for `vercel-multiwallet/`

- `agent/new/*.py` inside `vercel-multiwallet/` is a **copy**, not a symlink, of the specific modules it needs from the real `agent/new/` (this file's directory) — Vercel's `includeFiles` can't reach outside the deployed project's own directory tree. **If you change any of `agent_wallets.py`, `db.py`, `dca_agent.py`, `dca_multiwallet.py`, `deposit_ledger.py`, `hosted_llm.py`, `shared_governance.py`, `wallet_auth.py` here, re-copy them into `vercel-multiwallet/agent/new/` before redeploying** — they do not update automatically. See `vercel-multiwallet/README.md` for the full deploy process.
- Env vars live on the Vercel project directly (not in a committed `.env`): `DATABASE_URL` (separate Neon branch), `MULTI_WALLET_MASTER_SEED`, `DCA_WALLET_PRIVATE_KEY` (fee collector), `SOLANA_CLUSTER`, `SOLANA_RPC_URL`, `CRON_SECRET`, `CORS_ALLOW_ORIGINS`, `DB_POOL_MAX_CONNECTIONS` (kept small — serverless can multiply connection pools across concurrent invocations, unlike one long-lived server), and now `CAPIX_API_KEY` (added this session — chat/LLM had no key configured on this backend until now).

### What's still open for you (Part 2)

1. **Recurring execution's heartbeat isn't solved yet** — pick one of the three options above. Given the pooled scheduler already runs on Render, option 3 is the most consistent with what you've already built, but needs your Render access to wire up.
2. **Ledger/history routes are best-effort, not fully re-derived for multi-wallet**: `/wallet/ledger` shows real entries (swap outputs, withdrawals are written to it), but the "deposited/reserved/spent" breakdown shown in the balance UI is flattened to a single live on-chain number for multi-wallet users, since there's no ledger reservation system in this model — intentional, but worth a product look if you want that breakdown to mean something more specific.
3. This is still a **test deployment on a separate Neon branch** — nothing here is wired to production data, and it should stay that way until you and Zeya are ready to actually migrate users off the pooled wallet.
4. Fee collector address currently reuses the pooled `DCA_WALLET_PRIVATE_KEY`. Same open question as Part 1's Volume Agent fees: worth a product decision on when/how fees actually get swept into a dedicated BITAGENTS revenue wallet.
