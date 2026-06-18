---
name: testing-bitagents-mvp
description: Test the BITAGENTS crypto AI agent MVP end-to-end. Use when verifying the landing page, the 3 agents (Wallet Watcher / Token Research / Market Research), network toggle, devnet payment flow, compute marketplace, or tasks history.
---

# Testing BITAGENTS MVP

BITAGENTS is a Next.js 14 (App Router) + Tailwind v4 crypto AI agent platform. Users connect a Solana wallet, pick an agent, submit a task, and get a real result. Payments are devnet-only; mainnet is read-only.

## Run the app locally (preferred test target)

```bash
npm install && npm --prefix frontend install
BITAGENTS_DATA_DIR=/home/ubuntu/.bitagents-test npm run dev:frontend   # http://localhost:3000
```

- Test **locally**, not on the Vercel preview. The JSON DB is file-based; on Vercel it falls back to an ephemeral `/tmp` dir **per serverless invocation**, so a create→run pair can hit different instances and the run step may 404. Locally it's a single process so the DB persists across the two API calls.
- Set `BITAGENTS_DATA_DIR` to a writable, persistent path to keep task history across restarts. Default local path is `frontend/.data/bitagents.json` (or repo `.data`).
- Works with **zero config / no API keys** — the deterministic fallback generates all reports. Optional LLM via `OLLAMA_BASE_URL` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`.
- De-risk before recording UI: smoke-test the backend first with curl, e.g. `POST /api/tasks` (body `{type,input,network,free:true}`) then `POST /api/tasks/:id/run`, and confirm the task reaches `completed`.

## Golden path (the core thing to prove)

1. Landing page (`/`) → click **Launch App** → `/app`.
2. Confirm the network toggle reads **Devnet Demo** (safe default).
3. Pick an agent, click **use example** to auto-fill a valid input, then **Run free demo**.
4. Watch status go creating → computing → **completed** and verify the result panel + compute-meta row (`engine`, `runtime`ms > 0, `network`, 16-hex `hash`).

Agent example inputs (from `frontend/src/lib/agents.ts`):
- Wallet Watcher: `So11111111111111111111111111111111111111112` (wrapped SOL)
- Token Research: `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v` (USDC mint)
- Market Research: `DePIN`

## Prove the RPC data is real (not canned)

Run Wallet Watcher on **Devnet Demo**, note SOL balance + token-account count, then flip the top toggle to **Mainnet Read** and re-run the **same** address. The numbers should DIFFER (e.g. devnet ~1441 SOL / 121 tokens vs mainnet ~1534 SOL / 425 tokens — these change over time). Identical numbers across networks would mean the data is faked.

## Other pages to check

- `/compute`: registration form (name, CPU/GPU/LLM, price, online/offline). Clicking **Connect wallet to register** should open the **Phantom wallet-select modal** — that proves the @solana wallet adapter is wired even without a funded wallet.
- `/tasks`: every run is listed; expanding a row shows task id, provider, fee, runtime, lifecycle timeline, and the full result.
- `/utility`: token-utility cards must use hedged wording ("designed to", "planned", "may", "future versions") and explicitly disclaim revenue share / guaranteed returns; 6-phase roadmap present.

## Known constraints / gotchas

- **Real on-chain devnet payment** (the "Pay 0.001 SOL & run" path) needs a Phantom browser extension loaded with a **funded devnet wallet**. This generally can't be self-provisioned in a fresh session, so the **free-demo path** is the fallback — it runs the *same* server-side compute and full lifecycle. If a funded devnet wallet seed is available, you can also script Phantom via Playwright over CDP to exercise the real payment + Solana Explorer tx link.
- The wallet adapter's `ConnectionProvider` is pinned to **devnet** regardless of the toggle; the toggle only changes the server-side **read** RPC and the task's `network` field. So payments are always devnet-safe.
- If `TREASURY_WALLET` is unset, the "Pay & run" button is hidden and only "Run free demo" shows — that's expected, not a bug.
- Market Research is deterministic local logic (not network-sensitive), so it returns the same content on devnet and mainnet — don't use it for the RPC-is-real check; use Wallet Watcher.

## Recording tips

- Maximize the window first: `sudo apt-get install -y wmctrl 2>/dev/null; wmctrl -r :ACTIVE: -b add,maximized_vert,maximized_horz`.
- One continuous take: T1 landing → Launch App → Wallet Watcher devnet → Mainnet re-run → Token Research → Market Research → /compute (open wallet modal) → /tasks → /utility. Annotate each test_start + a consolidated pass/fail assertion.

## Devin Secrets Needed

- **None required** for the default end-to-end test (free-demo path works with zero config).
- To test the **real devnet payment** path: a funded **devnet** wallet seed/private key (e.g. `BITAGENTS_DEVNET_WALLET_SECRET`) to import into Phantom, plus optionally `TREASURY_WALLET` (a devnet address to receive the 0.001 SOL fee). Never use a mainnet wallet with funds.
- Optional LLM keys to test the non-deterministic narrative path: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `OLLAMA_BASE_URL`.
