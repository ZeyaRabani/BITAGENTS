# BIT Agents payment and fee model

This document describes how platform fees, launch fees, and creator-agent subscription payments move between wallets.

## Wallets

| Wallet | Purpose |
| --- | --- |
| **Per-user agent wallet** (Circle, per agent type: DCA, Yield, Volume, etc.) | Holds the user's deposited capital for that agent. Platform fees from that agent also accrue here until the monthly sweep. |
| **Launch fee wallet** (`LAUNCH_FEE_WALLET`) | Receives 100% of the fee when a user creates/launches a custom agent. |
| **Agent payment wallet** (Circle, one per public paid creator agent) | Receives subscription/purchase payments from buyers of that specific public agent. Same address for every buyer of that agent. |
| **Company treasury wallet** (`COMPANY_TREASURY_WALLET`, falls back to `TREASURY_PUBLIC_KEY`) | Receives monthly platform-fee sweeps. |

Transfer fee buffer used on platform sweeps: **0.000005 SOL**.  
That buffer is subtracted from the platform fee (not charged to the user) so the network transfer cost is effectively paid by the platform.

## 1. Built-in agent platform fees (DCA, Yield, Volume, EasyA, …)

1. User deposits capital into their per-user Circle agent wallet.
2. When the agent charges a platform fee (for example 0.5% on a DCA buy or Yield invest), that fee stays in the **same** agent wallet and is tracked as accrued platform fee.
3. On the **last calendar day of each month at 11:00 GMT**, a scheduler sweeps each fee pot:

   - `send_amount = accrued_platform_fee - 0.000005`
   - If `send_amount <= 0.000002`, **do not sweep** that pot. Leave the balance and try again next month (plus any new fees).
   - Otherwise send `send_amount` SOL from the agent wallet to the **company treasury wallet**.

## 2. Launch fee (creating a custom agent)

1. User pays the launch fee (see `LAUNCH_COST_SOL`; 0 in development mode).
2. **All** of that fee goes to the **launch fee wallet** (`LAUNCH_FEE_WALLET`).
3. Launch fees are not mixed into the monthly platform-fee sweep from agent wallets.

## 3. Public paid creator agents

### Payment wallet

When a creator makes an agent **public** and sets a price (for example 0.01 SOL / month):

1. The platform creates a **unique Circle payment wallet for that agent**.
2. Every subscriber of that agent pays to **the same** payment wallet address.
3. Different creator agents each get their own payment wallet.

### Split on each purchase / subscription

Example: weather agent costs **0.01 SOL**.

1. Buyer sends **0.01 SOL** to the agent's payment wallet.
2. Ledger split inside that wallet:
   - **90%** (0.009 SOL) → creator withdrawable balance
   - **10%** (0.001 SOL) → platform accrued cut (stays in the same payment wallet)
3. The creator can **withdraw their 90% anytime** to their own wallet.
4. The **10% platform cut** is swept on the same monthly schedule as other platform fees:
   - `send_amount = platform_cut_accrued - 0.000005`
   - Skip if `send_amount <= 0.000002`
   - Otherwise send to the **company treasury wallet**

## 4. Monthly sweep rule (summary)

For every fee pot (built-in agent wallets and creator-agent payment wallets):

```
BUFFER = 0.000005 SOL   # covers Solana transfer fee (paid from platform fee)
MIN_NET = 0.000002 SOL  # do not sweep dust that is uneconomical

net = accrued - BUFFER
if net > MIN_NET:
    transfer net SOL → COMPANY_TREASURY_WALLET
    reduce accrued by net (leave BUFFER / remainder in pot)
else:
    skip this month; try again next month with residual + new fees
```

Schedule: **last day of the month, 11:00 GMT**.

## 5. Environment variables

```bash
# Launch fee destination (100% of create-agent fee)
LAUNCH_FEE_WALLET=

# Monthly platform-fee sweeps land here
COMPANY_TREASURY_WALLET=
# TREASURY_PUBLIC_KEY=   # fallback if COMPANY_TREASURY_WALLET is unset

# Optional overrides
# PLATFORM_FEE_TRANSFER_BUFFER_SOL=0.000005
# PLATFORM_FEE_MIN_SWEEP_NET_SOL=0.000002
# PLATFORM_FEE_SWEEP_HOUR_GMT=11
# LAUNCH_PLATFORM_FEE_RATE=0.10   # 10% platform cut on creator-agent subscriptions
```

## 6. Implementation map

| Piece | Location |
| --- | --- |
| Fee pots, accrual, creator balances, monthly sweep | `agent/new/platform_payments.py` |
| Launch fee + subscription payment to agent wallet | `agent/new/launch_agent.py` |
| Built-in fee recording hooks | `deposit_ledger.py` (DCA), `volume_ledger.py`, `easya_trading_ledger.py` |
| Scheduler start | `agent/new/agents_api.py` startup |
| Creator withdraw API | `POST /launch/{agent_id}/withdraw-earnings` (frontend: `/api/agents/launch/[id]/withdraw-earnings`) |
| Manual/admin sweep | `POST /payments/sweep?force=false` (internal key) |
