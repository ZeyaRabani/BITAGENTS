# BITAGENTS on Aomi (Rust) + Python strategy API

From now on, marketplace agents are built as Aomi apps. DCA is the first:

```text
Aomi chat (Rust skill bitagents/dca)
        |
        v
Python agents_api.py  -->  /strategies/dca/...
        |
        +--> deposits, Circle wallets, scheduler
        +--> aomi_pipeline swap gate --> Circle sign --> Solana
```

| Process | Role |
| --- | --- |
| **Rust `aomi-app`** | Agent conversation and typed tools on Aomi |
| **Python `agent/new`** | Auth, deposits, `/strategies`, scheduler, signing |
| **Next.js `/agents/dca`** | Fund wallet, copy session token, inspect plans |

## Local dual-server

### 1. Python strategy API

```bash
cd agent/new
python agents_api.py
```

Serves `http://127.0.0.1:8765` including `/strategies` and wallet auth.

If `aomi-run` is in WSL and Python is on Windows, `http://127.0.0.1:8765` from WSL will not reach Windows. Either run Python inside the same WSL session, or set `BITAGENTS_API_URL` to `http://<windows-host-ip>:8765/` (from WSL: `grep nameserver /etc/resolv.conf`).

### 2. Rust Aomi app (local chat)

```bash
cargo install aomi-sdk --locked --features cli,dev-runtime
cd aomi-app
copy .env.example .env
# set BITAGENTS_API_URL=http://127.0.0.1:8765/
# set BITAGENTS_INTERNAL_API_KEY=...
# set BITAGENTS_SESSION_TOKEN=... (from Next.js after wallet sign-in)
cargo test
cargo build --release
```

Plugin filename depends on the OS you built on:

| OS | Path |
| --- | --- |
| Linux / WSL | `target/release/libbitagents.so` |
| macOS | `target/release/libbitagents.dylib` |
| Windows | `target/release/bitagents.dll` |

Then (Linux / WSL example):

```bash
aomi-run --env-file .env --provider openrouter target/release/libbitagents.so
```

`aomi-run` defaults to Anthropic (`ANTHROPIC_API_KEY`). For OpenRouter you must pass `--provider openrouter` and set `OPENROUTER_API_KEY` in `.env`. Optional model:

```bash
aomi-run --env-file .env --provider openrouter --model meta-llama/llama-3.3-70b-instruct target/release/libbitagents.so
```

Production uses `https://aomi.chat` after `aomi-build deploy` + activate.

Loopback `http://127.0.0.1` / `http://localhost` is allowed only for local `aomi-run`. Production `BITAGENTS_API_URL` must stay HTTPS.

### 3. Next.js marketplace shell

```bash
cd frontend
npm run dev
```

Open `/agents/dca`, sign in, deposit SOL, copy the session token into Aomi credentials, then chat in Aomi.

## Service contract

| Method | Path | Meaning |
| --- | --- | --- |
| GET | `/strategies` | Catalog |
| GET/POST | `/strategies/dca/plans` | List / create |
| GET/PATCH | `/strategies/dca/plans/{id}` | Read / update |
| POST | `/strategies/dca/plans/{id}/status` | pause / resume / cancel |
| GET | `/strategies/dca/plans/{id}/executions` | History |
| POST | `/strategies/dca/run` | preview quote only |

Auth: `Authorization: Bearer <wallet session>` + `x-internal-key`.

## Aomi credentials

| Name | Owner | Value |
| --- | --- | --- |
| `BITAGENTS_API_URL` | Operator | HTTPS API origin (no path), or loopback HTTP for local run |
| `BITAGENTS_INTERNAL_API_KEY` | Operator | `AGENTS_INTERNAL_API_KEY` |
| `BITAGENTS_SESSION_TOKEN` | User | Session from `/auth/verify` |

## Production

1. Deploy Python with `/strategies` reachable over HTTPS.
2. Set operator secrets on the Aomi app.
3. `aomi-build deploy` + activate from this repo (`.aomi/config.json` points here).
4. Users set `BITAGENTS_SESSION_TOKEN` in Aomi credentials and chat with `bitagents/dca`.
