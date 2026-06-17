# BITAGENTS — DCA Agent

**Create DCA bots with AI.**

Tell BITAGENTS what token to buy, how much to spend, and how often. The DCA
Agent turns your message into a structured, recurring on-chain buy plan that you
review and confirm before anything happens.

```
> buy BITAGENTS every 10 minutes with 0.01 SOL
> total budget: 1 SOL
> agent: planning 100 recurring buys
> status: ready for confirmation
```

The agent only automates the instruction you give it. **It never picks tokens
for you, never promises profit, and never recommends trades.** Every real
mainnet transaction requires your wallet signature.

---

## How it works

1. **Describe your buy** in plain English on `/app`.
2. **The agent plans it** — it parses your message into a `DcaPlan` (token,
   per-buy amount, total budget, interval, number of buys, estimated duration).
3. **You confirm.** Nothing is created until you click **Create DCA Agent**.
4. **It runs on-chain** in one of the modes below.

### Network modes

| Mode | When | What happens |
| --- | --- | --- |
| **Mainnet Safe Mode** | **Default.** Mainnet wallet connected (`NEXT_PUBLIC_ENABLE_MAINNET_DCA=true`, the default) | Creates a real **Jupiter Recurring** (time-based) order. You sign the create + cancel transactions. No custody, no server-held keys. |
| **Devnet Demo Mode** | When you flip the toggle to Devnet (or set `NEXT_PUBLIC_DEFAULT_NETWORK=devnet`) | Simulates scheduled executions every ~10s using **real** mainnet reference prices, hashes + timestamps each fill, and clearly labels it `Devnet simulation — no real token purchase`. |
| **Experimental Agent Wallet Mode** | `ENABLE_AGENT_WALLET_MODE=true` + allowlisted user | A server-scheduled, encrypted, capped agent wallet signs swaps for you. **Disabled by default**, behind a flag, with hard caps. Opt-in only. |

> **Why two modes?** Jupiter Recurring is **mainnet-only** and enforces a
> minimum order value (≈ **50 USDC per buy** at the time of writing). Small
> buys like `0.01 SOL` are rejected, so the agent falls back to Devnet Demo
> Mode (or asks you to increase the order size). See
> [Jupiter limitations](#jupiter-limitations).

---

## Install

Requirements: Node `>= 18.18`, npm.

```bash
git clone https://github.com/ZeyaRabani/BITAGENTS.git
cd BITAGENTS
npm install
npm --prefix frontend install
npm --prefix workers/provider-worker install   # optional remote worker
cp .env.example .env.local                      # all keys optional for the demo
```

## Run locally

```bash
npm run dev:frontend     # Next.js app on http://localhost:3000
```

Open http://localhost:3000 → **Launch DCA Agent**. The app defaults to
**Mainnet Safe Mode** (real Jupiter Recurring orders you sign in your wallet).
Flip the network toggle to **Devnet Demo** to simulate the full flow with no
wallet, RPC, or API keys — the deterministic parser handles the example prompts
out of the box.

To advance Devnet Demo plans automatically while developing, run the local
scheduler in a second terminal:

```bash
npm run dca:worker       # polls POST /api/cron/dca every 10s
```

## Verify

```bash
npm run typecheck        # shared + frontend + worker
npm run lint
npm run build
npm test                 # vitest: parser, plan math, Jupiter, scheduler
```

---

## Environment variables

Everything is optional for the demo. See [`.env.example`](.env.example) for the
full annotated list. The most important ones:

| Variable | Purpose |
| --- | --- |
| `NEXT_PUBLIC_DEFAULT_NETWORK` | `mainnet` (default) or `devnet` for the initial UI network. |
| `NEXT_PUBLIC_ENABLE_MAINNET_DCA` | Allow real Jupiter Recurring orders. Default `true`; set `false` to force Devnet Demo Mode. |
| `NEXT_PUBLIC_BITAGENTS_MINT` / `NEXT_PUBLIC_BITAGENTS_SYMBOL` | The `BITAGENTS` token alias used by the parser. |
| `JUPITER_API_KEY` / `JUPITER_API_BASE` | Blank = free `lite-api.jup.ag` (no key). A key switches to the pro host. |
| `OPENROUTER_API_KEY`, `OLLAMA_BASE_URL`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` | Optional LLM parsing. Tried OpenRouter → Ollama → OpenAI → Anthropic → deterministic fallback. |
| `CRON_SECRET` | Secures `/api/cron/dca` in production. |
| `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN` | Use Upstash Redis instead of the local JSON store (recommended on Vercel). |
| `NEXT_PUBLIC_ENABLE_AGENT_WALLET_MODE` / `ENABLE_AGENT_WALLET_MODE`, `AGENT_WALLET_*`, `MAX_AGENT_WALLET_*`, `MIN_INTERVAL_SECONDS` | Experimental agent wallet mode + its caps/encryption/allowlist. |

### Configure a Jupiter API key (optional)

The free **lite** host (`https://lite-api.jup.ag`) needs no key and is used by
default. For higher rate limits, create a key at
[portal.jup.ag](https://portal.jup.ag) and set `JUPITER_API_KEY` — the app then
automatically targets the pro host `https://api.jup.ag`.

---

## Mainnet Safe Mode (Jupiter Recurring)

1. Connect a **mainnet** Phantom wallet (Mainnet Safe Mode is the default; `NEXT_PUBLIC_ENABLE_MAINNET_DCA=true`).
2. Describe a buy whose **per-order value is ≥ ~50 USDC** (the Jupiter minimum).
3. Confirm the plan. The server calls Jupiter `recurring/v1/createOrder` and
   returns an **unsigned** transaction.
4. Your wallet signs it; the server submits it via `recurring/v1/execute`.
5. Jupiter's own keepers execute the recurring buys on-chain on schedule.
6. Cancel any time from **My Plans** — that produces another transaction **you
   sign**.

BITAGENTS never holds your keys and never moves mainnet funds without your
signature in this mode.

### Jupiter limitations

- **Minimum order value ≈ 50 USDC per buy.** A `0.01 SOL` order (~$0.74) is
  rejected with `Each order valued at … USDC, minimum is 50.00 USDC`. The UI
  detects this and offers: increase the order size, switch to Devnet Demo Mode,
  or (if enabled) use Experimental Agent Wallet Mode.
- **Mainnet only** — there is no Jupiter Recurring on devnet, which is why
  Devnet Demo Mode simulates instead.
- **No integrator fee.** Jupiter charges a 0.1% protocol fee and does **not**
  let integrators add their own fee, so BITAGENTS takes **no** fee on recurring
  orders. The business model is a separate subscription / agent-service fee
  (see `/utility`).
- The **BITAGENTS mint** (`iu3A7azWTm3zQSk81SUC1JctB4zPYnxLmcmqq71EASY`) **is
  routeable** on Jupiter (Meteora DAMM v2), so plans build fine — they are only
  rejected on the order-size minimum, not on routing.

## Devnet Demo Mode

When mainnet DCA is off (the default), confirming a plan:

1. Creates an `active` plan stored in the database.
2. The scheduler executes one simulated order per tick (Vercel Cron or the local
   `dca:worker`), spaced by the plan interval.
3. Each execution fetches **real** mainnet reference prices to derive a realistic
   fill, hashes the result (SHA-256), records runtime + timestamp, and labels it
   `Devnet simulation — no real token purchase`.
4. Watch progress, execution history, and cancel from **My Plans**.

No real tokens are ever purchased in this mode.

## Why Agent Wallet Mode is disabled by default

Agent Wallet Mode lets the server sign swaps without per-buy user approval,
which requires holding an (encrypted) private key. That is powerful but riskier,
so it ships **off**: it is gated behind `ENABLE_AGENT_WALLET_MODE`, restricted to
an `AGENT_WALLET_ALLOWED_USERS` allowlist, capped
(`MAX_AGENT_WALLET_TOTAL_SOL`, `MAX_AGENT_WALLET_ORDERS`, `MIN_INTERVAL_SECONDS`),
and refuses to start without `AGENT_WALLET_ENCRYPTION_KEY`. Keys are encrypted
with AES-256-GCM and never logged.

---

## Scheduling

The scheduler advances Devnet Demo (and agent-wallet) plans. Jupiter Recurring
plans are **not** driven here — Jupiter's keepers run those on-chain.

- **Local:** `npm run dca:worker` polls `POST /api/cron/dca` every
  `INTERVAL_MS` (default 10s).
- **Vercel Cron:** add a cron to `vercel.json` that hits `/api/cron/dca` and set
  `CRON_SECRET` (Vercel sends it as a Bearer token). Example:

  ```json
  {
    "crons": [{ "path": "/api/cron/dca", "schedule": "* * * * *" }]
  }
  ```

  > Sub-daily cron schedules require a paid Vercel plan; Hobby runs daily. For
  > frequent demo execution, run the local worker or trigger the endpoint
  > manually: `curl -X POST $URL/api/cron/dca -H "Authorization: Bearer $CRON_SECRET"`.

## Database

The store is pluggable (`frontend/src/server/dca/store.ts`):

- `UPSTASH_REDIS_REST_URL` (+ token) → Upstash Redis (serverless-safe).
- `DATABASE_URL` → Postgres (documented extension point; no driver bundled, so
  it currently falls back to JSON and logs a warning).
- otherwise → local JSON file (`./.data/bitagents-dca.json`).

On Vercel the JSON file lives in an ephemeral temp dir, so use **Upstash** for
durable plan history in production.

---

## Project layout

```
frontend/                 Next.js 14 app (UI + API routes + server compute)
  src/app/                /, /app, /plans, /utility, /docs, /api/*
  src/components/dca/     DcaAgent, PlanPreview, PlanCard, MyPlans
  src/server/dca/         parse, plan, jupiter, scheduler, store, agentWallet, config
  src/_archive/           legacy MVP pages (not routed, excluded from build)
shared/                   @bitagents/shared — DcaPlan types + math helpers
workers/provider-worker/  optional remote worker (not required)
```

The previous multi-agent marketplace pages (agents, compute, tasks, vaults) are
**archived** under `frontend/src/_archive/` — kept for reference, removed from
navigation, and excluded from TypeScript + ESLint + the build.

---

## Testing

`npm test` runs Vitest over the pure logic that matters:

- prompt parsing (the three example prompts, intervals, slippage),
- plan math (number of buys, per-order amount, duration),
- validation + execution-mode selection,
- Jupiter request construction + minimum-order rejection + cancel,
- the Devnet Demo plan lifecycle and scheduler idempotency.

See [`DEMO.md`](DEMO.md) for a step-by-step walkthrough of the four demos.
