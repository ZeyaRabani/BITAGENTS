# BITAGENTS

## Aomi strategy integration

The [Aomi app and strategy service](aomi-app/README.md) expose the Python DCA
strategy as an Aomi skill. Aomi handles agent configuration and chat; BITAGENTS
keeps the schedule, wallet service and execution history. The same directory
includes a local, explicitly simulated experience preview.

BITAGENTS is an AI Agent Marketplace powered by a decentralized compute marketplace.

The MVP proves the full loop on Solana devnet:

1. A compute provider registers available compute.
2. A user requests an AI agent task.
3. The user pays the task fee in devnet SOL to a treasury wallet.
4. The backend assigns the paid task to an online provider.
5. A provider worker polls, claims, and runs real local computation.
6. The result is returned to the user interface.
7. A provider payout transaction is recorded and shown on Solana Explorer.

## Architecture

```text
+------------------+          +---------------------+
| Phantom wallet   |          | Provider worker     |
| user/admin       |          | Node.js process     |
+--------+---------+          +----------+----------+
         |                               |
         | devnet SOL transfer          | poll/claim/result
         v                               v
+--------+------------------------------------------------+
| frontend                                                |
| Next.js 14 UI + API routes                              |
| - /marketplace shows compute listings and cGPU orders   |
| - /vaults and /agents show vault and agent dashboards    |
| - /dashboard creates tasks and records payment sigs      |
| - local JSON DB stores providers/tasks                  |
+--------+------------------------------------------------+
         |
         | @solana/web3.js
         v
+--------+---------+
| Solana devnet    |
| payment/payout   |
+------------------+
```

## Repository layout

This repository intentionally avoids an npm-workspace monorepo setup. Each major app/package has its own folder, package file, dependencies, and code.

```text
/frontend                 Next.js app, API routes, wallet UI, marketplace, vaults, agents, analytics
/workers/provider-worker  Node worker that polls tasks and runs provider computation
/shared                   Shared task/provider/result types and helpers used by the apps
.env.example              Environment template
```

The root `package.json` only provides convenience scripts for running the separate folders together.

## Agent task types

### Wallet Watcher Agent

Input: Solana wallet address.

The worker uses Solana devnet RPC to fetch:

- SOL balance
- SPL token account count
- latest 5 signatures
- a concise computed summary

### Research Agent

Input: keyword or project name.

The worker runs deterministic local text analysis:

- word count
- unique term count
- sentiment score from local term sets
- SHA-256 keyword hash
- structured summary, risks, and next questions

### Compute Benchmark Agent

Input: matrix size from 12 to 220.

The worker runs real CPU work:

- deterministic matrix multiplication
- runtime measurement
- checksum
- SHA-256 result hash

## Install

Install the lightweight root orchestration dependencies, then install each standalone package folder:

```bash
npm install
npm --prefix shared install
npm --prefix frontend install
npm --prefix workers/provider-worker install
```

Each folder now keeps its own `package.json` and `package-lock.json`.

## Environment

Copy the example file:

```bash
cp .env.example .env.local
```

Set at least these values:

```bash
NEXT_PUBLIC_TREASURY_PUBLIC_KEY=YOUR_DEVNET_TREASURY_PUBLIC_KEY
PROVIDER_WALLET=YOUR_REGISTERED_PROVIDER_PUBLIC_KEY
```

`NEXT_PUBLIC_SOLANA_RPC_URL` and `SOLANA_RPC_URL` default to `https://api.devnet.solana.com`.

## Create and fund devnet wallets

Install the Solana CLI if you do not already have it, then create a treasury keypair:

```bash
solana-keygen new --outfile treasury.json
solana-keygen pubkey treasury.json
solana airdrop 2 YOUR_TREASURY_PUBLIC_KEY --url devnet
```

You can also use Phantom:

1. Open Phantom settings.
2. Enable developer settings.
3. Switch network to Devnet.
4. Copy the wallet address into the app or `.env.local`.
5. Fund it with a devnet faucet or the Solana CLI.

## Run the MVP

Run the frontend and worker together from the repository root:

```bash
npm run dev
```

Or run each standalone folder separately:

```bash
npm --prefix frontend run dev
npm --prefix workers/provider-worker run dev
```

You can also `cd` into `frontend`, `workers/provider-worker`, or `shared` and use that folder's own `package.json` scripts directly.

The web app runs at:

```text
http://localhost:3000
```

The API is served by the same Next.js app through `/api/*` routes.

## Register a provider

1. Go to `http://localhost:3000/provider`.
2. Connect Phantom on devnet or paste a provider wallet address.
3. Enter provider name, compute type, price per task, and status `online`.
4. Save the provider.
5. Put the same wallet address into `.env.local` as `PROVIDER_WALLET`.
6. Start or restart the provider worker.

## Create a task

1. Go to `http://localhost:3000/dashboard`.
2. Connect Phantom on devnet.
3. Select Wallet Watcher, Research, or Benchmark.
4. Fill the input.
5. Click `Create and pay task`.
6. Approve the devnet SOL transfer to the treasury wallet.
7. The API records the payment signature and assigns the task to an online provider.

## Complete the task through the worker

The worker polls:

```text
GET /api/worker/tasks?providerWallet=...
```

When it finds an assigned task it calls:

```text
POST /api/tasks/:taskId/claim
POST /api/tasks/:taskId/result
```

The UI polls the API, so the task should move from `assigned` to `computing` to `completed` automatically.

## Provider payout

Go to `http://localhost:3000/demo` after a task is completed.

For the browser payout flow:

1. Connect the treasury/admin wallet in Phantom.
2. Click `Pay provider` on a completed task.
3. Approve the devnet SOL transfer to the provider wallet.
4. The payout signature is stored and linked to Solana Explorer.

Optional API payout:

Set `TREASURY_SECRET_KEY` in `.env.local` to a devnet keypair secret. The API route `/api/tasks/:taskId/payout` can then send payout when called with `{ "serverPayout": true }`.

## View Solana devnet transactions

The UI links payment and payout signatures to Solana Explorer with `?cluster=devnet`.

Manual format:

```text
https://explorer.solana.com/tx/YOUR_SIGNATURE?cluster=devnet
```

## Local data

The MVP stores providers and tasks in:

```text
.data/bitagents.json
```

Set `BITAGENTS_DATA_DIR` to use another local directory.

## Hackathon demo script

## Build and checks

From the repository root:

```bash
npm run typecheck
npm run build
```

Or run checks inside a single folder:

```bash
npm --prefix frontend run typecheck
npm --prefix workers/provider-worker run typecheck
npm --prefix shared run typecheck
```

## Notes

- The MVP uses SOL on Solana devnet for hackathon simplicity.
- The code is structured so a future Anchor escrow program can replace direct Web3.js transfers.
- Core computation is not faked: wallet data comes from devnet RPC, research is deterministic local analysis, and benchmark tasks run CPU work.
