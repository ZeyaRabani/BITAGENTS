# BITAGENTS DCA Agent — Demo Script

Four short demos that show the product end to end. Demos 1, 2 and 4 need **no
wallet and no API keys**. Demo 3 needs a mainnet wallet and a deliberately large
order (Jupiter's minimum is ≈ 50 USDC per buy).

Setup:

```bash
npm install && npm --prefix frontend install
npm run dev:frontend            # http://localhost:3000
# optional second terminal, makes Devnet Demo plans advance every ~10s:
npm run dca:worker
```

Open http://localhost:3000 and click **Launch DCA Agent** (`/app`).

---

## Demo 1 — Natural-language → DCA plan

**Goal:** show the agent turning a sentence into a structured plan you must confirm.

1. In the chat box type (or click the first example button):

   ```
   Buy BITAGENTS every 10 minutes with 0.01 SOL using 1 SOL total
   ```

2. The agent replies with a **plan preview** on the right:
   - Buy token: **BITAGENTS**, Pay with: **SOL**
   - Per buy: **0.01 SOL**, Total budget: **1 SOL**
   - Number of buys: **100** (1 SOL ÷ 0.01 SOL)
   - Every: **10m**, Est. duration: **16h 40m** (100 × 600s = 60,000s)
   - Risk warnings are listed.

3. **Nothing has been created yet.** Creation only happens when you click
   **Create DCA Agent**. This is the core safety property.

Try the other examples too:
- `Buy SOL every day with 10 USDC for 30 days` → 30 buys, daily.
- `Buy iu3A7azWTm3zQSk81SUC1JctB4zPYnxLmcmqq71EASY every hour with 0.05 SOL for 10 buys`
  → a pasted mint address, 10 hourly buys.

---

## Demo 2 — Devnet Demo Mode (end to end, no wallet)

**Goal:** show a full plan lifecycle with real compute and zero risk.

1. Flip the network toggle to **Devnet Demo** (the deployment defaults to Mainnet Safe Mode).
2. Submit `Buy BITAGENTS every 10 minutes with 0.01 SOL using 1 SOL total`.
3. Click **Create DCA Agent**. A demo wallet is generated locally if you have no
   wallet connected, so the plan is created immediately.
4. The plan appears under **active** with status `active`. With `dca:worker`
   running (or by POSTing `/api/cron/dca`), executions stream in every ~10s:
   - each row shows the simulated fill, a SHA-256 result hash, runtime, and the
     label **“Devnet simulation — no real token purchase.”**
   - progress, “buys done”, and “spent” update as it runs.
5. Open **My Plans** (`/plans`) to see the same plan with full history, and use
   **Cancel** to stop it.

---

## Demo 3 — Mainnet Safe Mode (real Jupiter Recurring)

**Goal:** show the safest real on-chain path — user-signed, no custody.

Prerequisites: Mainnet Safe Mode (the default; `NEXT_PUBLIC_ENABLE_MAINNET_DCA=true`),
a Phantom wallet on **mainnet**, and an order **≥ ~50 USDC per buy**.

1. The toggle already reads **Mainnet Safe** by default — connect your wallet.
2. Submit a large enough order, e.g.:

   ```
   Buy BITAGENTS every day with 60 USDC for 7 days
   ```

3. Confirm. BITAGENTS calls Jupiter `recurring/v1/createOrder` and returns an
   **unsigned** transaction; your wallet prompts you to sign.
4. After you sign, the server submits it via `recurring/v1/execute`. The plan
   shows the **order account**, the **create signature**, and a **Solana
   Explorer** link. Jupiter's keepers then execute the recurring buys on-chain.
5. In **My Plans**, click **Cancel** → you sign one more transaction to close the
   order. BITAGENTS never holds your keys or moves funds without your signature.

---

## Demo 4 — Failure handling (small-order fallback)

**Goal:** show what happens when Jupiter rejects an order, and that the app
degrades gracefully.

1. In **Mainnet Safe** mode, submit a small order that violates the minimum:

   ```
   Buy BITAGENTS every 10 minutes with 0.01 SOL using 1 SOL total
   ```

2. On confirm, Jupiter rejects it:
   `Each order valued at 0.74 USDC, minimum is 50.00 USDC`.
3. The agent **keeps your parsed plan** and explains the options:
   - increase the per-buy size to ≥ ~50 USDC, or
   - **Try in Devnet Demo Mode** (one click), or
   - use Experimental Agent Wallet Mode (if enabled).
4. Click **Try in Devnet Demo Mode** to run the very same plan safely — this is
   why the BITAGENTS demo always works even when mainnet constraints don't allow
   a tiny recurring order.

---

## What to highlight

- The agent **parses → previews → waits for confirmation** — it never trades on
  its own and never picks the token for you.
- **Devnet Demo Mode** runs real compute (live prices, hashing, timestamps)
  without spending anything.
- **Mainnet Safe Mode** is non-custodial: every transaction is user-signed.
- The **BITAGENTS mint is routeable**; the only mainnet blocker for tiny orders
  is Jupiter's ≈ 50 USDC minimum, which the UI handles explicitly.
