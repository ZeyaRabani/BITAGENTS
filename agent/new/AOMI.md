# How the DCA agent uses Aomi

Aomi is the safety check in front of a live DCA buy. It does not hold keys, it does not sign, and it does not broadcast. Jupiter builds the swap, Aomi stages and simulates that exact transaction, and Circle signs only after Aomi commits.

This is Phase 1 and it applies to the DCA agent only. Chat still uses OpenRouter. Wallet login, deposits, and plan storage stay on BIT Agents.

## What a buy does

1. The signed-in user already has a Circle agent wallet. That address is the Jupiter fee payer.
2. Circle signs a short Aomi sign-in for that same address. The session lasts about 30 minutes and is cached in `agent/new/.aomi-wallet-sessions.json` (gitignored). A new user does not sign into Aomi.
3. `aomi_pipeline.gate_swap` sends the unsigned transaction to `POST /v1/pipeline/svm/stage`.
4. Simulate runs that staged build on a fork: `POST /v1/pipeline/svm/simulate` with body `{ "build": <staged build> }`.
5. The fork result is checked against the plan. In `gate` mode a failed fork, a spend above the plan amount, the wrong output mint, or too little output skips the buy. `log` mode records the mismatch and still continues.
6. Commit revalidates the simulated build: `POST /v1/pipeline/svm/commit` with body `{ "build": <simulated build> }`. Commit does not broadcast.
7. Circle signs the unsigned transaction Aomi returns. BIT Agents sends it to Solana and waits for confirmation.

If stage, simulate, or commit fails, the buy is skipped. Circle never signs that attempt. An HTTP 502 on `/v1/pipeline/svm/stage` is Aomi's server failing the request, so that buy is not sent.

## Why each Circle wallet has its own session

Aomi accepts a venue-built transaction only when the fee payer is the Solana wallet on the session. The device-login token in `.env` is one account, and its connected wallet is whichever browser wallet approved that login. It is not the fee payer for every user.

The pipeline stage body has no field that switches the payer. Naming another address with `userState`, `transaction.payer`, or `Aomi-Svm-Address` does not change the check. The session itself has to be that user's Circle address.

`circle_sign_message` signs the Sign-In With Solana message. Aomi verifies it at `POST /api/auth/widget/siws/verify` and returns a widget bearer (`aomi_wst_...`). Pipeline calls send that bearer plus `Origin: https://chat.aomi.dev`. When the token is inside a minute of expiry, the agent wallet signs a new one.

The device-login values `AOMI_ACCESS_TOKEN` and `AOMI_REFRESH_TOKEN` remain for a buy that has no Circle wallet id. They are not used as the signer for a Circle-paid swap.

## Where it lives

| Piece | Role |
| --- | --- |
| `aomi_pipeline.py` | Session cache, stage, simulate, plan check, commit |
| `dca_agent.py` | Builds the Jupiter swap, calls `gate_swap`, then Circle-signs and broadcasts |
| `circle_dca_wallets.py` | Creates the per-user Circle wallet and signs the Aomi message and the transaction |
| `.env.example` | `AOMI_API_URL`, `AOMI_DCA_MODE`, `AOMI_OAUTH_CLIENT_ID`, and the device-login token names |

Default API host is `https://chat.aomi.dev`. Default mode is `gate`.

## Hedge Fund and Sniper

These agents use the same gate. Each one has its own Circle wallet, so the Aomi session for a hedge-fund swap is not the DCA wallet and not the sniper wallet.

`market_agents.execute_market_swap` builds the Jupiter swap for that wallet and calls the same `gate_swap`. Circle signs only after Aomi commits. A stage, simulate, or commit failure skips the swap.

The Sniper agent adds two checks before that gate: the buy must be SOL and at or under the user's max size, and the output mint must not still have a mint or freeze authority. The Hedge Fund agent can buy with SOL or sell a token amount back to SOL.
