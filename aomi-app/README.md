# BITAGENTS strategy skills for Aomi

Aomi owns the conversation and agent-management experience. BITAGENTS supplies
strategies through an authenticated service, including its existing scheduler,
deposit ledger and signing service. The first adapter is recurring Solana DCA.

```text
Aomi chat -> BITAGENTS app -> bitagents/dca skill -> /strategies/dca/...
                                                   |
                                       existing Python DCA service
                                                   |
                                       scheduler -> wallet -> history
```

One shared app serves many user agents. A user agent is a persisted strategy
plan, not a compiled copy of the app. Each strategy family has a skill with its
own typed tools and instructions. Adding yield later means adding an adapter,
registering it in `agents_api.py`, and adding its skill; the service contract
and Aomi conversation remain the same.

## Service contract

All `/strategies` routes use the existing `require_wallet_session` dependency:
`Authorization: Bearer <wallet session>` plus the operator's `x-internal-key`.
Ownership always comes from the authenticated session, never model arguments.
The router is mounted in the existing `agents_api.py` process; existing
maintenance, database startup, scheduler and auth behavior still apply.

| Method | Path | Meaning |
| --- | --- | --- |
| GET | `/strategies` | Discover adapters, schemas, fees and unsupported conditions |
| GET | `/strategies/{strategy}/plans` | List the current user's agents |
| POST | `/strategies/{strategy}/plans` | Schedule with `{ "configuration": {...} }` |
| GET | `/strategies/{strategy}/plans/{id}` | Read configuration and status |
| PATCH | `/strategies/{strategy}/plans/{id}` | Change configuration |
| POST | `/strategies/{strategy}/plans/{id}/status` | Pause, resume or cancel |
| GET | `/strategies/{strategy}/plans/{id}/executions` | Read execution history |
| POST | `/strategies/{strategy}/run` | Run a saved plan in supported mode |

`dca` currently accepts `run` with `{ "plan_id": "...", "mode": "preview" }`.
This is a quote, **not** a fork simulation or live submission. Live execution
uses the existing scheduler; this API deliberately has no replayable force-buy
endpoint. Creation activates a schedule, with the first buy after one interval.
Total budget and execution cap are mandatory. Fee and feasibility checks run in
the existing Python implementation. Pausing cannot retract in-flight trades.

Example creation configuration:

```json
{
  "configuration": {
    "name": "Steady SOL",
    "input_token": "USDC",
    "output_token": "SOL",
    "amount_per_buy": 25,
    "interval": "1 day",
    "total_budget": 100.5,
    "max_executions": 4,
    "slippage_bps": 100
  }
}
```

The budget includes the 0.5% platform fee. Network costs also apply. A funded
BITAGENTS deposit balance is required; an Aomi-connected wallet balance is not
a deposit. Price triggers, stop loss, take profit and equities are not DCA
capabilities, and the skill must not silently substitute DCA for them.

## Aomi app

`src/lib.rs` declares the app, user credential and owned DCA skill. `client.rs`
owns transport and authentication. `tool.rs` exposes discovery, wallet setup,
creation, editing, status, previews and history. No arbitrary URL, Python code,
private key or owner is accepted from model arguments. HTTPS is mandatory,
redirects are disabled, and the user session never falls back to a global token.

Configure through Aomi's app secret/credential facilities:

| Name | Owner | Value |
| --- | --- | --- |
| `BITAGENTS_API_URL` | App operator | HTTPS origin of the deployed Python API, without a path |
| `BITAGENTS_INTERNAL_API_KEY` | App operator | Its existing `AGENTS_INTERNAL_API_KEY` |
| `BITAGENTS_SESSION_TOKEN` | Individual user | Existing BITAGENTS wallet-auth session |

The wallet helper may provision a BITAGENTS deposit wallet but never transfers
funds. Operator RPC URLs and wallet-provider diagnostics are not returned to
the model. Wallet keys stay in the existing BITAGENTS signing service.

Deploy the Python change before deploying the app. `.aomi/config.json` discovers
`aomi-app/aomi.toml`. Connect a source fork in Aomi Build, verify the platform's
required SDK version matches the exact `7.0.0` pin, then build and activate the
app. It is private by default and has no production `server_tags`. Use Aomi's
direct app chat to create and manage plans; no BITAGENTS chat model is called.

## Checks

From the repository root:

```sh
python -m venv /tmp/bitagents-tests
/tmp/bitagents-tests/bin/pip install -r aomi-app/preview/requirements.txt
PYTHONPATH=agent/new /tmp/bitagents-tests/bin/python -m unittest discover -s agent/new/tests -v
cargo test --locked --manifest-path aomi-app/Cargo.toml
cargo clippy --locked --manifest-path aomi-app/Cargo.toml --all-targets -- -D warnings
cargo fmt --manifest-path aomi-app/Cargo.toml -- --check
```

Python tests use the real DCA configuration service with fixture persistence,
balances and network calls. They cover owner isolation, bounded configuration,
platform fees, no-write previews and lifecycle transitions. They do not prove
production signing, scheduler concurrency or blockchain confirmation.

## Local experience preview

This is a BIT Agents branded UX proposal, not a deployed UI or a live model demo.
The customer-facing product remains BIT Agents; Aomi provides the app runtime.
The preview follows `frontend/src/app/globals.css` theme tokens and fonts,
`Nav.tsx` branding, `DcaAgentConsole.tsx` command input/Send/example pattern,
and `DcaPlanPanel.tsx` edit fields (amount, interval, max buys, budget, slippage).
It serves the existing BIT Agents logo asset directly. No Aomi branding appears
in the customer-facing preview.
It uses the same router, adapter and DCA service with in-memory persistence,
fixture balances and fixture swaps. Its guided prompt parser accepts the shown
example form; real Aomi uses model-driven typed tool calls instead. The local
`/demo/tick` control calls the Python execution/accounting function with a fixture
swap, not the background claim loop. No key or on-chain RPC is used.

```sh
npm exec --yes --package typescript -- tsc -p aomi-app/preview/tsconfig.json
/tmp/bitagents-tests/bin/python aomi-app/preview/server.py
# Open http://localhost:8766
```

Walkthrough: describe a recurring buy in the persistent conversation, review
and authorize its inline configuration card, then ask “Preview next buy”,
“Simulate a scheduled run”, “How is my strategy doing?”, and “Pause my plan”.
The plan and receipts remain alongside the chat. The guided parser handles
these commands through the same API; it is not a live language model.
Position summaries derive holdings from execution receipts and costs from the
plan ledger. The fixed demo price does not establish real earnings. Editing
limits also opens an inline approval card. The server binds to loopback only and is not mounted in production.

## Before a live pilot

- Configure the actual partner API origin and operator key, then connect a
  user-owned wallet session. Seamless Aomi-to-BITAGENTS wallet sign-in remains
  an integration task; copying session credentials is developer onboarding.
- Deploy and verify the skill in Aomi, including gating, credentials and direct
  chat. The local preview does not exercise Aomi's model, deployment or UI.
- Validate a funded test agent through the real scheduler and confirmation
  path. Existing scheduler retries/concurrency and plan-creation idempotency
  are not redesigned here. On an uncertain create response, inspect existing
  plans before retrying; creating twice makes two schedules.
- Human approval before activation/increased spending is currently an app
  instruction plus the proposed UI. A server-enforced draft/approval protocol
  is needed before treating the agent as unattended high-assurance automation.
- Add additional strategy adapters and price-trigger/exit semantics explicitly;
  do not advertise unsupported strategies or Aomi simulation guarantees.
