# BITAGENTS — Demo Script

This is the exact golden-path demo. It takes ~3 minutes and uses **Solana
devnet only** — no mainnet funds are ever at risk.

## 0. Prerequisites

- Node.js ≥ 18.18
- [Phantom](https://phantom.app) browser extension
- A little devnet SOL (see "Fund a devnet wallet" below)

## 1. Start the app

```bash
npm install
npm --prefix frontend install
npm run dev:frontend          # http://localhost:3000
```

Optional — accept real devnet payments by adding a treasury to `.env.local`:

```bash
NEXT_PUBLIC_SOLANA_NETWORK=devnet
TREASURY_WALLET=<your devnet wallet public key>
```

If you skip this, the demo still works — every task runs as a **free demo**.

## 2. Fund a devnet wallet

1. Open Phantom → switch the network to **Devnet**.
2. Copy your address and request devnet SOL at <https://faucet.solana.com>
   (or `solana airdrop 2 <ADDRESS> --url https://api.devnet.solana.com`).

## 3. Golden path — Wallet Watcher with a devnet payment

1. Open <http://localhost:3000>. Confirm the nav toggle reads **Devnet Demo** (default).
2. Click **Launch App** → you land on `/app`.
3. Click the wallet button and **connect Phantom**.
4. Select the **Wallet Watcher** agent.
5. Enter a Solana wallet address (or click **use example**).
6. Click **Pay 0.001 SOL & run**.
7. Approve the transaction in Phantom.
8. Watch the lifecycle advance: **created → paid → assigned → computing → completed**.
9. Read the result: SOL balance, token-account count, latest 5 signatures, an
   AI summary, and risk/behavior notes.
10. Click the **devnet payment** link to view the transaction on Solana Explorer.

## 4. Try the other agents

- **Token Research** — enter a mint address (example:
  `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v`) or a project name. Get an
  overview, supply/authorities, bull/bear case, risks, and a disclaimer.
- **Market Research** — enter a keyword like `DePIN`, `RWA`, or `restaking`.
  Get a definition, use cases, opportunities, risks, and what to monitor.

## 5. Mainnet read-only

Flip the nav toggle to **Mainnet Read**. Run Wallet Watcher on a real mainnet
address to fetch live mainnet data. Payments are disabled in this mode (tasks
run free) — mainnet is read-only by design.

## 6. Compute marketplace

1. Go to `/compute`.
2. Connect a wallet, enter a provider name, choose a compute type (CPU / GPU
   simulated / LLM), set a price, and click **Sign & register**.
3. Approve the message signature in Phantom (no funds move).
4. Your provider appears in the marketplace with wallet, type, price, status,
   tasks completed, and reputation.

## 7. Tasks & history

Open `/tasks` to see every run: task ID, agent, requester wallet, provider,
status, devnet tx signature, runtime, result, and timestamp. Expand any row for
the full result.

## 8. Utility & roadmap

Open `/utility` for token utility (carefully worded — no promises of returns)
and the six-phase roadmap.

---

### Free demo (no wallet)

On `/app` or `/agents`, skip connecting a wallet and click **Run free demo**.
The agent runs the exact same real computation without a payment step.
