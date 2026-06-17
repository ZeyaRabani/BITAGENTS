"""
Solana DCA (Dollar-Cost Averaging) Agent
Independent agent — run directly: python dca_agent.py

Schedules recurring token buys on Solana via Jupiter (mainnet) or SOL transfers (devnet).
Powered by Ollama for natural-language plan management.
"""

import base64
import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

import requests

try:
    import base58
    from solders.keypair import Keypair
    from solders.message import to_bytes_versioned
    from solders.pubkey import Pubkey
    from solders.transaction import VersionedTransaction
    HAS_SOLDERS = True
except ImportError:
    HAS_SOLDERS = False

AGENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = AGENT_DIR.parent.parent


def _load_env() -> None:
    """Load agent/new/.env (and optional repo .env) before reading config."""
    try:
        from dotenv import load_dotenv
        load_dotenv(REPO_ROOT / ".env")
        load_dotenv(REPO_ROOT / ".env.local", override=True)
        load_dotenv(AGENT_DIR / ".env", override=True)
    except ImportError:
        env_file = AGENT_DIR / ".env"
        if not env_file.exists():
            return
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_env()

# ─── Config ───────────────────────────────────────────────────────────────────

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/chat")
MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1")

SOLANA_RPC = os.environ.get(
    "SOLANA_RPC_URL",
    os.environ.get("NEXT_PUBLIC_SOLANA_RPC_URL", "https://api.devnet.solana.com"),
)
SOLANA_CLUSTER = os.environ.get(
    "SOLANA_CLUSTER",
    os.environ.get("NEXT_PUBLIC_SOLANA_CLUSTER", "devnet"),
)
JUPITER_QUOTE_API = os.environ.get("JUPITER_QUOTE_API", "https://lite-api.jup.ag/swap/v1/quote")
JUPITER_SWAP_API = os.environ.get("JUPITER_SWAP_API", "https://lite-api.jup.ag/swap/v1/swap")
COINGECKO_API = "https://api.coingecko.com/api/v3"

_plans_path = os.environ.get("DCA_PLANS_FILE", "").strip()
PLANS_FILE = Path(_plans_path) if _plans_path else AGENT_DIR / "dca_plans.json"
SCHEDULER_POLL_SECONDS = int(os.environ.get("DCA_SCHEDULER_POLL_SECONDS", "30"))
HEADERS = {"User-Agent": "SolanaDCAAgent/1.0", "Content-Type": "application/json"}

INTERVAL_PRESETS = {
    "every_30_seconds": 0.5,   # 0.5 minutes
    "every_minute": 1,
    "every_5_minutes": 5,
    "every_15_minutes": 15,
    "hourly": 60,
    "every_4_hours": 240,
    "every_12_hours": 720,
    "daily": 1440,
    "weekly": 10080,
    "biweekly": 20160,
    "monthly": 43200,
}

# Mainnet mints (Jupiter). Devnet uses SOL-only execution.
TOKEN_MINTS = {
    "SOL":  {"mint": "So11111111111111111111111111111111111111112", "decimals": 9,  "coingecko_id": "solana"},
    "WSOL": {"mint": "So11111111111111111111111111111111111111112", "decimals": 9,  "coingecko_id": "solana"},
    "USDC": {"mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "decimals": 6,  "coingecko_id": "usd-coin"},
    "USDT": {"mint": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB", "decimals": 6,  "coingecko_id": "tether"},
    "JUP":  {"mint": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",  "decimals": 6,  "coingecko_id": "jupiter-exchange-solana"},
    "BONK": {"mint": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", "decimals": 5,  "coingecko_id": "bonk"},
    "WIF":  {"mint": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",  "decimals": 6,  "coingecko_id": "dogwifcoin"},
    "RAY":  {"mint": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",  "decimals": 6,  "coingecko_id": "raydium"},
    "ORCA": {"mint": "orcaEKTdK7LKz57vaAYr9QeNs490PNsTPTvJaq2qDz8",  "decimals": 6,  "coingecko_id": "orca"},
    "PYTH": {"mint": "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3",  "decimals": 6,  "coingecko_id": "pyth-network"},
    "JTO":  {"mint": "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL",  "decimals": 9,  "coingecko_id": "jito-governance-token"},
    "RENDER": {"mint": "rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHBof", "decimals": 8, "coingecko_id": "render-token"},
    "BITAGENTS": {"mint": "iu3A7azWTm3zQSk81SUC1JctB4zPYnxLmcmqq71EASY", "decimals": 6, "coingecko_id": None},
}

# A base58 Solana mint/contract address (no 0, O, I, l), 32-44 chars.
_MINT_ADDRESS_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
_mint_decimals_cache: dict = {}

_scheduler_lock = threading.Lock()
_scheduler_running = False


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _coerce_nullable_float(val) -> Optional[float]:
    """Convert string 'null'/'none'/'' to None, otherwise float."""
    if val is None:
        return None
    if isinstance(val, str):
        if val.strip().lower() in ("null", "none", ""):
            return None
        return float(val)
    return float(val)


def _coerce_nullable_int(val) -> Optional[int]:
    """Convert string 'null'/'none'/'' to None, otherwise int."""
    if val is None:
        return None
    if isinstance(val, str):
        if val.strip().lower() in ("null", "none", ""):
            return None
        return int(val)
    return int(val)


def _coerce_bool(val) -> bool:
    """Convert string 'true'/'false'/'1'/'0' to bool."""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes")
    return bool(val)


# ─── Wallet & RPC ─────────────────────────────────────────────────────────────

def _is_mainnet() -> bool:
    cluster = SOLANA_CLUSTER.lower()
    if cluster in ("mainnet", "mainnet-beta"):
        return True
    return "mainnet" in SOLANA_RPC.lower() and "devnet" not in SOLANA_RPC.lower()


def load_keypair() -> Optional["Keypair"]:
    if not HAS_SOLDERS:
        return None
    raw = os.environ.get("DCA_WALLET_PRIVATE_KEY") or os.environ.get("SOLANA_PRIVATE_KEY")
    if not raw:
        return None
    try:
        raw = raw.strip()
        if raw.startswith("["):
            return Keypair.from_bytes(bytes(json.loads(raw)))
        return Keypair.from_bytes(base58.b58decode(raw))
    except Exception:
        return None


def get_wallet_pubkey() -> Optional[str]:
    kp = load_keypair()
    return str(kp.pubkey()) if kp else None


def sol_rpc(method: str, params: list, timeout: int = 30) -> Any:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    r = requests.post(SOLANA_RPC, json=payload, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"])))
    return data.get("result")


def _fetch_mint_decimals(mint: str) -> int:
    """Read an SPL mint's decimals from chain. Falls back to 6 on RPC error."""
    if mint in _mint_decimals_cache:
        return _mint_decimals_cache[mint]
    decimals = 6
    try:
        resp = sol_rpc("getTokenSupply", [mint])
        decimals = int(resp["value"]["decimals"])
    except Exception:
        pass
    _mint_decimals_cache[mint] = decimals
    return decimals


def resolve_token(symbol: str) -> dict:
    raw = symbol.strip()
    sym = raw.upper()
    if sym in TOKEN_MINTS:
        return {"symbol": sym, **TOKEN_MINTS[sym]}
    # Accept any raw base58 mint address (e.g. a token's contract address).
    if _MINT_ADDRESS_RE.match(raw):
        return {
            "symbol": raw,
            "mint": raw,
            "decimals": _fetch_mint_decimals(raw),
            "coingecko_id": None,
        }
    return {
        "error": f"Unknown token '{symbol}'. Supported: {', '.join(sorted(TOKEN_MINTS))} "
                 f"(or paste a token's mint/contract address)."
    }


def _lamports(amount: float, decimals: int) -> int:
    return int(round(amount * (10 ** decimals)))


def _fmt_ts(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


# ─── Plan persistence ─────────────────────────────────────────────────────────

def _load_plans() -> list:
    if not PLANS_FILE.exists():
        return []
    try:
        return json.loads(PLANS_FILE.read_text())
    except Exception:
        return []


def _save_plans(plans: list) -> None:
    PLANS_FILE.write_text(json.dumps(plans, indent=2))


def _find_plan(plan_id: str) -> Optional[dict]:
    for p in _load_plans():
        if p["id"] == plan_id:
            return p
    return None


def _update_plan(plan_id: str, updates: dict) -> Optional[dict]:
    plans = _load_plans()
    for i, p in enumerate(plans):
        if p["id"] == plan_id:
            plans[i] = {**p, **updates}
            _save_plans(plans)
            return plans[i]
    return None


# ─── Solana reads ─────────────────────────────────────────────────────────────

def get_wallet_status() -> dict:
    """Return wallet pubkey, SOL balance, cluster, and whether signing is available."""
    pubkey = get_wallet_pubkey()
    if not pubkey:
        return {
            "wallet_configured": False,
            "cluster": SOLANA_CLUSTER,
            "rpc_url": SOLANA_RPC,
            "mainnet": _is_mainnet(),
            "note": "Set DCA_WALLET_PRIVATE_KEY (base58 or JSON array) to enable live swaps.",
        }
    try:
        resp = sol_rpc("getBalance", [pubkey])
        lamports = resp.get("value", 0) if isinstance(resp, dict) else resp
        balance = lamports / 1e9
        return {
            "wallet_configured": True,
            "pubkey": pubkey,
            "sol_balance": round(balance, 6),
            "cluster": SOLANA_CLUSTER,
            "rpc_url": SOLANA_RPC,
            "mainnet": _is_mainnet(),
            "jupiter_swaps": _is_mainnet(),
            "solders_installed": HAS_SOLDERS,
        }
    except Exception as e:
        return {"wallet_configured": True, "pubkey": pubkey, "error": str(e)}


def get_token_price(symbol: str) -> dict:
    """Fetch USD price and 24h change from CoinGecko."""
    tok = resolve_token(symbol)
    if "error" in tok:
        return tok
    if not tok.get("coingecko_id"):
        return {
            "symbol": tok["symbol"],
            "price_usd": None,
            "note": "No CoinGecko price feed for this token; execution uses live Jupiter quotes.",
            "fetched_at": _fmt_ts(datetime.now(timezone.utc)),
        }
    try:
        r = requests.get(
            f"{COINGECKO_API}/simple/price",
            params={
                "ids": tok["coingecko_id"],
                "vs_currencies": "usd",
                "include_24hr_change": "true",
            },
            headers=HEADERS,
            timeout=15,
        )
        data = r.json().get(tok["coingecko_id"], {})
        return {
            "symbol": tok["symbol"],
            "price_usd": data.get("usd"),
            "change_24h_pct": data.get("usd_24h_change"),
            "fetched_at": _fmt_ts(datetime.now(timezone.utc)),
        }
    except Exception as e:
        return {"error": str(e)}


def get_jupiter_quote(
    input_token: str,
    output_token: str,
    amount: float,
    slippage_bps: int = 100,
) -> dict:
    """Get a Jupiter swap quote (mainnet only)."""
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return {"error": "Amount must be a number greater than 0."}
    # Small LLMs sometimes omit/null slippage; fall back to a sane default.
    try:
        slippage_bps = int(slippage_bps) if slippage_bps is not None else 100
    except (TypeError, ValueError):
        slippage_bps = 100
    if amount <= 0:
        return {"error": "Amount must be greater than 0."}

    if not _is_mainnet():
        return {
            "error": "Jupiter quotes require mainnet RPC. Current cluster is devnet.",
            "hint": "Set SOLANA_RPC_URL to a mainnet endpoint for token swaps.",
        }
    inp = resolve_token(input_token)
    out = resolve_token(output_token)
    if "error" in inp:
        return inp
    if "error" in out:
        return out
    try:
        params = {
            "inputMint": inp["mint"],
            "outputMint": out["mint"],
            "amount": str(_lamports(amount, inp["decimals"])),
            "slippageBps": str(slippage_bps),
        }
        r = requests.get(JUPITER_QUOTE_API, params=params, headers=HEADERS, timeout=20)
        quote = r.json()
        if "error" in quote:
            return {"error": quote["error"]}
        out_amt = int(quote.get("outAmount", 0)) / (10 ** out["decimals"])
        impact = quote.get("priceImpactPct")
        return {
            "input_token": inp["symbol"],
            "output_token": out["symbol"],
            "input_amount": amount,
            "estimated_output": round(out_amt, 8),
            "price_impact_pct": impact,
            "slippage_bps": slippage_bps,
            "route_plan_steps": len(quote.get("routePlan", [])),
            "quote": quote,
        }
    except Exception as e:
        return {"error": str(e)}


def _send_signed_tx(encoded_tx: str) -> str:
    result = sol_rpc(
        "sendTransaction",
        [encoded_tx, {"encoding": "base64", "skipPreflight": False, "maxRetries": 3}],
    )
    return result


def _sign_jupiter_tx(swap_b64: str, keypair: "Keypair") -> str:
    raw_tx = VersionedTransaction.from_bytes(base64.b64decode(swap_b64))
    signature = keypair.sign_message(to_bytes_versioned(raw_tx.message))
    signed_tx = VersionedTransaction.populate(raw_tx.message, [signature])
    return base64.b64encode(bytes(signed_tx)).decode("utf-8")


def _execute_jupiter_swap(quote: dict, slippage_bps: int = 100) -> dict:
    keypair = load_keypair()
    if not keypair:
        return {"error": "No wallet keypair. Set DCA_WALLET_PRIVATE_KEY."}
    if not HAS_SOLDERS:
        return {"error": "Install solders + base58: pip install solders base58"}
    if not _is_mainnet():
        return {"error": "Jupiter swaps require mainnet RPC."}

    pubkey = str(keypair.pubkey())
    try:
        swap_resp = requests.post(
            JUPITER_SWAP_API,
            json={
                "quoteResponse": quote,
                "userPublicKey": pubkey,
                "wrapAndUnwrapSol": True,
                "dynamicComputeUnitLimit": True,
                "prioritizationFeeLamports": "auto",
            },
            headers=HEADERS,
            timeout=30,
        ).json()
        if "error" in swap_resp:
            return {"error": swap_resp["error"]}

        swap_tx = swap_resp.get("swapTransaction")
        if not swap_tx:
            return {"error": "No swapTransaction in Jupiter response"}

        encoded = _sign_jupiter_tx(swap_tx, keypair)
        sig = _send_signed_tx(encoded)
        explorer = f"https://explorer.solana.com/tx/{sig}?cluster=mainnet"
        return {"status": "success", "signature": sig, "explorer_url": explorer}
    except Exception as e:
        return {"error": str(e)}


def _execute_devnet_sol_transfer(amount_sol: float) -> dict:
    """Devnet fallback: small SOL transfer to self as proof-of-execution."""
    keypair = load_keypair()
    if not keypair or not HAS_SOLDERS:
        return {"error": "Wallet + solders required for devnet execution."}

    try:
        from solders.system_program import TransferParams, transfer
        from solders.message import MessageV0
        from solders.hash import Hash

        pubkey = keypair.pubkey()
        lamports = int(float(amount_sol) * 1e9)
        if lamports < 5000:
            lamports = 5000

        blockhash_resp = sol_rpc("getLatestBlockhash", [{"commitment": "finalized"}])
        blockhash = Hash.from_string(blockhash_resp["value"]["blockhash"])

        ix = transfer(TransferParams(from_pubkey=pubkey, to_pubkey=pubkey, lamports=lamports))
        msg = MessageV0.try_compile(pubkey, [ix], [], blockhash)
        tx = VersionedTransaction(msg, [keypair])
        encoded = base64.b64encode(bytes(tx)).decode("utf-8")
        sig = _send_signed_tx(encoded)
        explorer = f"https://explorer.solana.com/tx/{sig}?cluster=devnet"
        return {
            "status": "success",
            "mode": "devnet_sol_self_transfer",
            "signature": sig,
            "explorer_url": explorer,
            "note": "Devnet cannot use Jupiter. Executed SOL self-transfer as scheduled tx proof.",
        }
    except Exception as e:
        return {"error": str(e)}


def execute_swap_buy(
    input_token: str,
    output_token: str,
    amount: float,
    slippage_bps: int = 100,
    dry_run: bool = False,
) -> dict:
    """Execute one DCA buy: Jupiter swap on mainnet, SOL transfer on devnet."""
    amount = float(amount)
    slippage_bps = int(slippage_bps)
    dry_run = _coerce_bool(dry_run)

    if dry_run:
        quote = get_jupiter_quote(input_token, output_token, amount, slippage_bps)
        if "error" in quote and _is_mainnet():
            return quote
        return {
            "status": "dry_run",
            "would_buy": f"{amount} {input_token.upper()} -> {output_token.upper()}",
            "quote_preview": {k: v for k, v in quote.items() if k != "quote"} if isinstance(quote, dict) else quote,
        }

    if _is_mainnet():
        quote_data = get_jupiter_quote(input_token, output_token, amount, slippage_bps)
        if "error" in quote_data:
            return quote_data
        result = _execute_jupiter_swap(quote_data["quote"], slippage_bps)
        if result.get("status") == "success":
            result["input_token"] = input_token.upper()
            result["output_token"] = output_token.upper()
            result["input_amount"] = amount
            result["estimated_output"] = quote_data.get("estimated_output")
        return result

    return _execute_devnet_sol_transfer(min(amount, 0.001))


# ─── DCA plan management ──────────────────────────────────────────────────────

def _parse_interval(interval: str) -> float:
    """Return interval in minutes (float to support sub-minute presets)."""
    key = interval.lower().replace(" ", "_").replace("-", "_")
    if key in INTERVAL_PRESETS:
        return INTERVAL_PRESETS[key]
    # Support "30 seconds", "30s", "30sec"
    m = re.match(r"^(\d+)\s*(s|sec|secs|second|seconds)$", key)
    if m:
        return int(m.group(1)) / 60.0
    m = re.match(r"^(\d+)\s*(m|min|mins|minute|minutes|h|hr|hour|hours|d|day|days|w|week|weeks)?$", key)
    if m:
        n = int(m.group(1))
        unit = (m.group(2) or "m").lower()
        if unit.startswith("h"):
            return n * 60
        if unit.startswith("d"):
            return n * 1440
        if unit.startswith("w"):
            return n * 10080
        return float(n)
    raise ValueError(f"Unknown interval '{interval}'. Try: daily, hourly, every_15_minutes, '30 seconds', or '30 minutes'.")


def create_dca_plan(
    name: str,
    input_token: str,
    output_token: str,
    amount_per_buy: float,
    interval: str,
    total_budget: Optional[float] = None,
    max_executions: Optional[int] = None,
    slippage_bps: int = 100,
    start_immediately: bool = False,
) -> dict:
    """Create a recurring DCA plan."""
    # Coerce — Ollama sometimes passes numeric/bool values as strings
    amount_per_buy = float(amount_per_buy)
    slippage_bps = int(slippage_bps)
    total_budget = _coerce_nullable_float(total_budget)
    max_executions = _coerce_nullable_int(max_executions)
    start_immediately = _coerce_bool(start_immediately)

    inp = resolve_token(input_token)
    out = resolve_token(output_token)
    if "error" in inp:
        return inp
    if "error" in out:
        return out
    try:
        interval_minutes = _parse_interval(interval)
    except ValueError as e:
        return {"error": str(e)}

    now = datetime.now(timezone.utc)
    next_run = now if start_immediately else now + timedelta(minutes=interval_minutes)

    plan = {
        "id": str(uuid.uuid4())[:8],
        "name": name,
        "input_token": inp["symbol"],
        "output_token": out["symbol"],
        "input_mint": inp["mint"],
        "output_mint": out["mint"],
        "amount_per_buy": amount_per_buy,
        "interval": interval,
        "interval_minutes": interval_minutes,
        "total_budget": total_budget,
        "spent_so_far": 0.0,
        "max_executions": max_executions,
        "executions_count": 0,
        "slippage_bps": slippage_bps,
        "status": "active",
        "created_at": now.isoformat(),
        "next_execution_at": next_run.isoformat(),
        "executions": [],
    }

    plans = _load_plans()
    plans.append(plan)
    _save_plans(plans)

    return {
        "status": "created",
        "plan": {
            k: plan[k]
            for k in (
                "id", "name", "input_token", "output_token", "amount_per_buy",
                "interval", "interval_minutes", "total_budget", "max_executions",
                "status", "next_execution_at",
            )
        },
        "wallet": get_wallet_pubkey(),
        "cluster": SOLANA_CLUSTER,
    }


def list_dca_plans(status: Optional[str] = None) -> dict:
    """List all DCA plans, optionally filtered by status."""
    plans = _load_plans()
    if status:
        plans = [p for p in plans if p.get("status") == status.lower()]
    summary = []
    for p in plans:
        summary.append({
            "id": p["id"],
            "name": p["name"],
            "pair": f"{p['input_token']} -> {p['output_token']}",
            "amount_per_buy": p["amount_per_buy"],
            "interval": p["interval"],
            "status": p["status"],
            "executions": p["executions_count"],
            "spent": p["spent_so_far"],
            "next_execution_at": p.get("next_execution_at"),
        })
    return {"plans": summary, "count": len(summary)}


def get_dca_plan(plan_id: str) -> dict:
    """Get full details for one DCA plan."""
    plan = _find_plan(plan_id)
    if not plan:
        return {"error": f"Plan '{plan_id}' not found."}
    return plan


def update_dca_plan_status(plan_id: str, action: str) -> dict:
    """Pause, resume, or cancel a DCA plan."""
    action = action.lower()
    valid = {"pause": "paused", "resume": "active", "cancel": "cancelled"}
    if action not in valid:
        return {"error": f"Unknown action '{action}'. Use: pause, resume, cancel."}
    plan = _find_plan(plan_id)
    if not plan:
        return {"error": f"Plan '{plan_id}' not found."}
    return _update_plan(plan_id, {"status": valid[action]}) or {"error": "Update failed."}


def execute_dca_now(plan_id: str, dry_run: bool = False) -> dict:
    """Force-run one DCA execution for a plan."""
    dry_run = _coerce_bool(dry_run)
    return _run_plan_execution(plan_id, dry_run=dry_run, force=True)


def get_dca_history(plan_id: str) -> dict:
    """Return execution history for a plan."""
    plan = _find_plan(plan_id)
    if not plan:
        return {"error": f"Plan '{plan_id}' not found."}
    return {
        "plan_id": plan_id,
        "name": plan["name"],
        "executions_count": plan["executions_count"],
        "spent_so_far": plan["spent_so_far"],
        "executions": plan.get("executions", []),
    }


def analyze_dca_timing(output_token: str, lookback_days: int = 7) -> dict:
    """Price trend analysis to help decide DCA frequency and timing."""
    lookback_days = int(lookback_days)
    tok = resolve_token(output_token)
    if "error" in tok:
        return tok
    try:
        r = requests.get(
            f"{COINGECKO_API}/coins/{tok['coingecko_id']}/market_chart",
            params={"vs_currency": "usd", "days": lookback_days},
            headers=HEADERS,
            timeout=20,
        )
        prices = [p[1] for p in r.json().get("prices", [])]
        if len(prices) < 2:
            return {"error": "Insufficient price data."}

        current = prices[-1]
        low = min(prices)
        high = max(prices)
        avg = sum(prices) / len(prices)
        change_pct = ((current / prices[0]) - 1) * 100
        drawdown = ((current / high) - 1) * 100 if high else 0
        dist_from_low = ((current / low) - 1) * 100 if low else 0

        if change_pct > 5:
            trend = "uptrend"
        elif change_pct < -5:
            trend = "downtrend"
        else:
            trend = "sideways"

        return {
            "token": tok["symbol"],
            "lookback_days": lookback_days,
            "current_price_usd": round(current, 6),
            "period_low_usd": round(low, 6),
            "period_high_usd": round(high, 6),
            "period_avg_usd": round(avg, 6),
            "period_change_pct": round(change_pct, 2),
            "drawdown_from_high_pct": round(drawdown, 2),
            "above_period_low_pct": round(dist_from_low, 2),
            "trend": trend,
            "dca_note": (
                "Regular DCA smooths volatility — frequency depends on your horizon, not short-term trend."
            ),
        }
    except Exception as e:
        return {"error": str(e)}


def _run_plan_execution(plan_id: str, dry_run: bool = False, force: bool = False) -> dict:
    plan = _find_plan(plan_id)
    if not plan:
        return {"error": f"Plan '{plan_id}' not found."}
    if plan["status"] != "active" and not force:
        return {"error": f"Plan is {plan['status']}, not active."}

    # Coerce stored values — guards against plans saved with string fields
    amount = float(plan["amount_per_buy"])
    spent = float(plan.get("spent_so_far", 0))
    budget = _coerce_nullable_float(plan.get("total_budget"))
    max_exec = _coerce_nullable_int(plan.get("max_executions"))
    executions_count = int(plan.get("executions_count", 0))
    interval_minutes = float(plan.get("interval_minutes", 1440))

    if budget is not None and spent + amount > budget:
        _update_plan(plan_id, {"status": "completed"})
        return {"error": "Budget exhausted. Plan marked completed.", "plan_id": plan_id}

    if max_exec is not None and executions_count >= max_exec:
        _update_plan(plan_id, {"status": "completed"})
        return {"error": "Max executions reached. Plan marked completed.", "plan_id": plan_id}

    result = execute_swap_buy(
        plan["input_token"],
        plan["output_token"],
        amount,
        int(plan.get("slippage_bps", 100)),
        dry_run=dry_run,
    )

    now = datetime.now(timezone.utc)
    exec_record = {
        "at": now.isoformat(),
        "amount": amount,
        "input_token": plan["input_token"],
        "output_token": plan["output_token"],
        "result": {k: v for k, v in result.items() if k != "quote"},
        "dry_run": dry_run,
    }

    if dry_run:
        return {"plan_id": plan_id, "dry_run": True, "preview": result}

    if result.get("status") == "success" or result.get("status") == "dry_run":
        next_run = now + timedelta(minutes=interval_minutes)
        executions = plan.get("executions", []) + [exec_record]
        _update_plan(plan_id, {
            "executions_count": executions_count + 1,
            "spent_so_far": round(spent + amount, 8),
            "next_execution_at": next_run.isoformat(),
            "executions": executions[-50:],
        })
        result["plan_id"] = plan_id
        result["next_execution_at"] = next_run.isoformat()
        return result

    exec_record["result"] = result
    executions = plan.get("executions", []) + [exec_record]
    _update_plan(plan_id, {"executions": executions[-50:]})
    return {"plan_id": plan_id, "execution_failed": True, **result}


def _scheduler_loop(poll_seconds: int = SCHEDULER_POLL_SECONDS) -> None:
    global _scheduler_running
    while _scheduler_running:
        try:
            now = datetime.now(timezone.utc)
            for plan in _load_plans():
                if plan.get("status") != "active":
                    continue
                next_at = plan.get("next_execution_at")
                if not next_at:
                    continue
                due = datetime.fromisoformat(next_at)
                if due.tzinfo is None:
                    due = due.replace(tzinfo=timezone.utc)
                if due <= now:
                    print(f"\n  ⏰ DCA due: {plan['name']} ({plan['id']})")
                    result = _run_plan_execution(plan["id"])
                    if result.get("status") == "success":
                        print(f"  ✅ Tx: {result.get('signature', 'ok')}")
                    else:
                        print(f"  ⚠️  {result.get('error', result)}")
        except Exception as e:
            print(f"  ⚠️  Scheduler error: {e}")
        time.sleep(poll_seconds)


def start_scheduler() -> bool:
    """Start background DCA scheduler thread."""
    global _scheduler_running
    with _scheduler_lock:
        if _scheduler_running:
            return False
        _scheduler_running = True
        t = threading.Thread(target=_scheduler_loop, daemon=True, name="dca-scheduler")
        t.start()
        return True


def stop_scheduler() -> None:
    global _scheduler_running
    _scheduler_running = False


# ─── Ollama tools ─────────────────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_wallet_status",
            "description": "Check if a Solana wallet is configured, SOL balance, cluster (devnet/mainnet), and swap capability.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_token_price",
            "description": "Get current USD price and 24h change for a supported token (SOL, USDC, JUP, BONK, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Token symbol e.g. SOL, JUP, BONK"},
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_jupiter_quote",
            "description": "Preview a Jupiter swap quote on mainnet before executing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "input_token": {"type": "string"},
                    "output_token": {"type": "string"},
                    "amount": {"type": "number", "description": "Amount of input token"},
                    "slippage_bps": {"type": "integer", "description": "Slippage in basis points (100 = 1%)"},
                },
                "required": ["input_token", "output_token", "amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_dca_plan",
            "description": "Create a recurring DCA plan. Buys output_token with input_token on a schedule.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "input_token": {"type": "string", "description": "Token to spend e.g. USDC or SOL"},
                    "output_token": {"type": "string", "description": "Token to accumulate e.g. JUP, BONK"},
                    "amount_per_buy": {"type": "number"},
                    "interval": {"type": "string", "description": "daily, hourly, every_15_minutes, weekly, every_30_seconds, or '30 minutes'"},
                    "total_budget": {"type": "number", "description": "Optional max total input to spend"},
                    "max_executions": {"type": "integer", "description": "Optional max number of buys"},
                    "slippage_bps": {"type": "integer"},
                    "start_immediately": {"type": "boolean"},
                },
                "required": ["name", "input_token", "output_token", "amount_per_buy", "interval"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dca_plans",
            "description": "List all DCA plans.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "Filter: active, paused, cancelled, completed"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_dca_plan",
            "description": "Get full details for one plan by ID.",
            "parameters": {
                "type": "object",
                "properties": {"plan_id": {"type": "string"}},
                "required": ["plan_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_dca_plan_status",
            "description": "Pause, resume, or cancel a DCA plan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_id": {"type": "string"},
                    "action": {"type": "string", "enum": ["pause", "resume", "cancel"]},
                },
                "required": ["plan_id", "action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_dca_now",
            "description": "Force-run the next buy for a plan immediately.",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_id": {"type": "string"},
                    "dry_run": {"type": "boolean", "description": "Preview without sending tx"},
                },
                "required": ["plan_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_swap_buy",
            "description": "Execute a one-off swap buy (not tied to a plan).",
            "parameters": {
                "type": "object",
                "properties": {
                    "input_token": {"type": "string"},
                    "output_token": {"type": "string"},
                    "amount": {"type": "number"},
                    "slippage_bps": {"type": "integer"},
                    "dry_run": {"type": "boolean"},
                },
                "required": ["input_token", "output_token", "amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_dca_history",
            "description": "Show past executions for a DCA plan.",
            "parameters": {
                "type": "object",
                "properties": {"plan_id": {"type": "string"}},
                "required": ["plan_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_dca_timing",
            "description": "Analyze recent price trend for a token to discuss DCA frequency.",
            "parameters": {
                "type": "object",
                "properties": {
                    "output_token": {"type": "string"},
                    "lookback_days": {"type": "integer"},
                },
                "required": ["output_token"],
            },
        },
    },
]

TOOL_MAP = {
    "get_wallet_status": get_wallet_status,
    "get_token_price": get_token_price,
    "get_jupiter_quote": get_jupiter_quote,
    "create_dca_plan": create_dca_plan,
    "list_dca_plans": list_dca_plans,
    "get_dca_plan": get_dca_plan,
    "update_dca_plan_status": update_dca_plan_status,
    "execute_dca_now": execute_dca_now,
    "execute_swap_buy": execute_swap_buy,
    "get_dca_history": get_dca_history,
    "analyze_dca_timing": analyze_dca_timing,
}

SYSTEM_PROMPT = """You are a Solana DCA (Dollar-Cost Averaging) agent. You help users set up recurring token buys on Solana.

## Capabilities
- Create DCA plans: spend input_token (USDC/SOL) to buy output_token (JUP/BONK/etc.) on a schedule
- List, pause, resume, cancel plans
- Execute buys immediately or on schedule (background scheduler runs automatically)
- Preview Jupiter quotes on mainnet
- Analyze price trends for DCA timing discussions

## Intervals
Use: hourly, daily, weekly, every_15_minutes, every_5_minutes, every_30_seconds, or custom like "30 minutes" or "30 seconds".

## Network
- **Mainnet**: real Jupiter token swaps (requires DCA_WALLET_PRIVATE_KEY + mainnet RPC)
- **Devnet** (default): scheduled SOL self-transfers as tx proof; Jupiter unavailable

## Workflow for new DCA
1. get_wallet_status — confirm wallet and cluster
2. get_token_price / analyze_dca_timing — optional context
3. get_jupiter_quote — preview if mainnet
4. BEFORE calling create_dca_plan, confirm the exact details with the user:
   "I'll set up: buy {amount} {output_token} with {input_token} every {interval}. Shall I proceed?"
   Use EXACTLY the tokens the user specified — do not substitute or infer different tokens.
5. create_dca_plan — only after confirmation or when the user's intent is completely unambiguous

## Safety
- Always warn: DCA does not guarantee profit; crypto is volatile
- For live execution, confirm amount, interval, and budget
- Use dry_run=true when user wants to preview without sending txs
- NEVER change the user's requested interval to a different one (e.g. do not change "30 seconds" to "every_15_minutes")
- End with: "Not financial advice. DYOR."

Supported tokens: SOL, USDC, USDT, JUP, BONK, WIF, RAY, ORCA, PYTH, JTO, RENDER
"""


def call_ollama(messages: list) -> Any:
    payload = {"model": MODEL, "messages": messages, "tools": TOOLS, "stream": False}
    resp = requests.post(OLLAMA_URL, json=payload, timeout=180)
    resp.raise_for_status()
    return resp.json()


def execute_tool(tool_name: str, tool_args: dict) -> str:
    func = TOOL_MAP.get(tool_name)
    if not func:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    try:
        return json.dumps(func(**tool_args), indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


def run_agent(user_input: str, conversation_history: list) -> tuple[str, list]:
    conversation_history.append({"role": "user", "content": user_input})
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + conversation_history

    for i in range(12):
        response = call_ollama(messages)
        message = response["message"]
        tool_calls = message.get("tool_calls", [])

        if not tool_calls:
            reply = message.get("content", "")
            conversation_history.append({"role": "assistant", "content": reply})
            return reply, conversation_history

        print(f"\n  🔧 [{i + 1}] Tools: {[tc['function']['name'] for tc in tool_calls]}")
        messages.append({
            "role": "assistant",
            "content": message.get("content", ""),
            "tool_calls": tool_calls,
        })

        for tc in tool_calls:
            name = tc["function"]["name"]
            args = tc["function"].get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            print(f"  📡 {name}({args})")
            result = execute_tool(name, args)
            print("  ✅ Done")
            messages.append({"role": "tool", "content": result})

    return "Agent reached max iterations.", conversation_history


BANNER = r"""
╔══════════════════════════════════════════════════════════════╗
║   💰  Solana DCA Agent                                       ║
║   Recurring buys · Jupiter swaps · Ollama-powered             ║
╚══════════════════════════════════════════════════════════════╝
"""


def main():
    print(BANNER)
    print(f"  Model   : {MODEL}")
    print(f"  RPC     : {SOLANA_RPC}")
    print(f"  Cluster : {SOLANA_CLUSTER} ({'Jupiter swaps' if _is_mainnet() else 'devnet mode'})")
    wallet = get_wallet_pubkey()
    print(f"  Wallet  : {wallet or 'not configured (set DCA_WALLET_PRIVATE_KEY)'}")
    print()

    env_path = AGENT_DIR / ".env"
    print(f"  Env     : {env_path if env_path.exists() else '(no .env — copy .env.example)'}")
    if start_scheduler():
        print(f"  ⏱️  Background scheduler started (every {SCHEDULER_POLL_SECONDS}s)")
    print()
    print("  Example prompts:")
    print("  • Check my wallet status")
    print("  • DCA $10 USDC into JUP every day, budget $300")
    print("  • Buy 0.05 SOL worth of BONK every 4 hours")
    print("  • Buy 0.0001 SOL worth of USDC every 30 seconds")
    print("  • List my DCA plans")
    print("  • Pause plan abc12345")
    print("  • Execute plan abc12345 now (dry run)")
    print("  • Analyze JUP for DCA timing")
    print()
    print("  Commands: clear | quit")
    print("─" * 64)

    history = []
    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Goodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() == "quit":
            print("👋 Goodbye!")
            break
        if user_input.lower() == "clear":
            history = []
            print("🔄 Conversation cleared.")
            continue

        print("\n  🤔 Working...\n")
        try:
            reply, history = run_agent(user_input, history)
            print(f"\n{'─' * 64}")
            print(reply)
            print(f"{'─' * 64}")
        except requests.exceptions.ConnectionError:
            print("  ❌ Cannot connect to Ollama. Run: ollama serve")
        except Exception as e:
            print(f"  ❌ Error: {e}")


if __name__ == "__main__":
    main()
