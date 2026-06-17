# BITAGENTS

**Run crypto AI agents without setup.**

BITAGENTS is a crypto AI agent platform. Connect a Solana wallet, choose an
agent, submit a task, watch it run real computation, and get a useful on-chain
result — no infrastructure, API keys, or boilerplate required.

The MVP ships three working agents, a compute-provider marketplace, a full task
lifecycle, and a Solana **devnet** payment flow.

- **Mainnet is read-only.** It is used only to fetch public on-chain data.
- **Devnet handles everything that moves funds** — task fees, payments, and
  provider registration. The UI labels this **Devnet Demo Mode** (the default).

---

## What BITAGENTS is

| Agent | Input | Output |
| --- | --- | --- |
| **Wallet Watcher** | Solana wallet address | SOL balance, token-account count, latest 5 signatures, AI summary, risk/behavior notes |
| **Token Research** | Token mint address or project name | On-chain overview, supply/authorities, holder/liquidity notes, bull/bear case, risks, disclaimer |
| **Market Research** | Keyword, ticker, or narrative | What it means, crypto use cases, opportunities, risks, things to monitor |

Every run performs **real work**: Solana RPC fetches, data normalization,
deterministic scoring, report generation, result hashing (SHA-256),
timestamping, and runtime measurement. If an LLM is configured (Ollama,
OpenAI, or Anthropic) it enriches the narrative; otherwise agents fall back to
deterministic local generation. **No paid API is required.**

---

## Tech stack

- **Frontend:** Next.js 14 (App Router), TypeScript, Tailwind CSS v4
- **Wallet:** `@solana/wallet-adapter` (Phantom)
- **Chain:** `@solana/web3.js`, `@solana/spl-token`
- **Compute:** server-side modules in `frontend/src/server/agents` (runs on Vercel — no separate worker needed)
- **Storage:** local JSON database (`.data/bitagents.json`)
- **Shared types:** `@bitagents/shared`

```
frontend/                 Next.js app (UI + API routes + server-side compute)
  src/app                 pages: / /app /agents /compute /tasks /utility + /api/*
  src/server/agents       real agent compute (solana, llm, walletWatcher, …)
shared/                   shared TypeScript types
workers/provider-worker   OPTIONAL remote provider heartbeat (not required)
```

---

## Install

Requires **Node.js ≥ 18.18** (Node 20/22 recommended).

```bash
git clone https://github.com/ZeyaRabani/BITAGENTS.git
cd BITAGENTS
npm install            # root
npm --prefix frontend install
npm --prefix workers/provider-worker install   # optional
```

---

## Run locally

```bash
cp .env.example .env.local     # optional — defaults work out of the box
npm run dev:frontend           # http://localhost:3000
```

`npm run dev:frontend` is all you need. (`npm run dev` also starts the optional
provider worker.)

Useful scripts (run from the repo root):

```bash
npm run typecheck     # shared + frontend + worker
npm run lint          # frontend ESLint
npm run build         # production build of all packages
```

---

## Configure devnet

The app defaults to **Devnet Demo Mode**. To accept real devnet payments, set a
treasury wallet in `.env.local`:

```bash
NEXT_PUBLIC_SOLANA_NETWORK=devnet
TREASURY_WALLET=<your devnet wallet public key>
```

If `TREASURY_WALLET` is blank, every task simply runs as a **free demo** — the
app stays fully functional.

### Fund a devnet wallet

1. Install Phantom and switch it to **Devnet** (Settings → Developer Settings → Testnet Mode / Change Network → Devnet).
2. Copy your wallet address.
3. Airdrop devnet SOL:
   - Web faucet: <https://faucet.solana.com> (paste your address, pick Devnet), or
   - CLI: `solana airdrop 2 <ADDRESS> --url https://api.devnet.solana.com`
4. You now have devnet SOL to pay the 0.001 SOL task fee.

To create a treasury wallet:

```bash
solana-keygen new --no-bip39-passphrase --outfile treasury.json
solana address -k treasury.json      # paste this into TREASURY_WALLET
```

---

## How to run each agent

1. Open <http://localhost:3000> and click **Launch App** (or go to `/agents`).
2. Pick an agent and enter its input (or click **use example**):
   - **Wallet Watcher** → a Solana wallet address
   - **Token Research** → a token mint address or project name
   - **Market Research** → a keyword, ticker, or narrative (e.g. `DePIN`)
3. Choose how to run:
   - **Pay 0.001 SOL & run** — requires a connected wallet, Devnet Demo Mode, and a configured treasury.
   - **Run free demo** — no wallet/payment needed.
4. Watch the task move through its lifecycle and read the result.

Switch the **Devnet Demo / Mainnet Read** toggle in the nav to choose which
network the agent reads from. Mainnet is read-only; payments only happen on
devnet.

---

## How devnet payment works

1. You submit a task → the API creates it with status `created` and assigns a
   provider (or the built-in **BITAGENTS Local Compute** fallback).
2. The app sends a **0.001 SOL devnet transfer** from your wallet to
   `TREASURY_WALLET` using the wallet adapter (connection is hard-pinned to
   devnet for safety).
3. The signature is saved and the task moves to `paid`. A **Solana Explorer
   (devnet)** link is shown.
4. The task runs (`computing` → `completed`) and the hashed, timestamped result
   is stored and displayed.

Task statuses: `created → paid → assigned → computing → completed` (or `failed`).

---

## How compute provider registration works

Open `/compute`:

1. Connect a wallet.
2. Enter a provider name, pick a compute type (**CPU**, **GPU (simulated)**, or
   **LLM endpoint**), set a price per task, and a status (online/offline).
3. Click **Sign & register** — the wallet signs a registration message proving
   ownership (no funds move). The provider is upserted into the local DB and
   appears in the marketplace with wallet, type, price, status, tasks
   completed, and a reputation score.

When a task is created, an online provider is selected (cheapest first);
otherwise the built-in local provider handles it so the demo always works. The
optional `workers/provider-worker` process can register a remote provider and
keep it online via heartbeat.

---

## Demo script

See [DEMO.md](./DEMO.md) for the exact click-by-click golden path.

---

## Deploy to Vercel

- Root directory: `frontend`
- Build command: `npm run build` (default)
- Set the same environment variables from `.env.example` in the Vercel project.

**Known limitation:** the local JSON DB is **ephemeral** on Vercel/serverless
(it writes to the OS temp dir, which is not persisted across invocations). The
deployed demo is fully functional per request, but task/provider history is not
durable. For persistence, swap `frontend/src/server/db.ts` for a real database
(e.g. Postgres, Upstash Redis, or Vercel KV).

---

## Known limitations

- Devnet payments only; mainnet is read-only by design.
- JSON file storage is not durable on serverless (see above).
- Token/holder/liquidity data is limited to what public RPC exposes; the agent
  always returns a useful structured report regardless.
- LLM narrative is optional; without it, output is deterministic.

## Disclaimer

BITAGENTS provides research and educational tooling only. Nothing in the app or
its token utility is financial advice or a promise of returns.
