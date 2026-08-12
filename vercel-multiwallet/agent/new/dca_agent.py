"""
Solana DCA (Dollar-Cost Averaging) Agent
Independent agent - run directly: python dca_agent.py

Schedules recurring token buys on Solana via Jupiter v2 build API (mainnet)
or SOL transfers (devnet). Powered by hosted Ollama (or OpenRouter fallback) for natural-language plan management.
"""

import base64
import hashlib
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

from hosted_llm import (
    CAPIX_API_URL,
    CAPIX_MODEL,
    HOSTED_OLLAMA_API_KEY,
    HOSTED_OLLAMA_BASE_URL,
    DEFAULT_LLM_MODEL,
    OPEN_ROUTER_API,
    OPEN_ROUTER_API_URL,
    OPEN_ROUTER_APP_NAME,
    OPEN_ROUTER_SITE_URL,
    call_llm,
    llm_configured,
    llm_provider,
    use_capix,
    use_hosted_ollama,
)

# ─── Config ───────────────────────────────────────────────────────────────────

MODEL = CAPIX_MODEL if use_capix() else os.environ.get(
    "DCA_MODEL",
    os.environ.get("OPEN_ROUTER_MODEL", DEFAULT_LLM_MODEL),
)

SOLANA_RPC = os.environ.get(
    "SOLANA_RPC_URL",
    os.environ.get("NEXT_PUBLIC_SOLANA_RPC_URL", "https://api.devnet.solana.com"),
)
SOLANA_CLUSTER = os.environ.get(
    "SOLANA_CLUSTER",
    os.environ.get("NEXT_PUBLIC_SOLANA_CLUSTER", "devnet"),
)

# ── Jupiter v2 build API (replaces deprecated quote-api.jup.ag/v6) ────────────
JUPITER_API_KEY    = os.environ.get("JUPITER_API_KEY", "")
JUPITER_BUILD_API  = os.environ.get("JUPITER_BUILD_API", "https://api.jup.ag/swap/v2/build")
JUPITER_TOKENS_API = os.environ.get("JUPITER_TOKENS_API", "https://api.jup.ag/tokens/v2")
JUPITER_PRICE_API  = os.environ.get("JUPITER_PRICE_API", "https://api.jup.ag/price/v3")

COINGECKO_API = "https://api.coingecko.com/api/v3"

_plans_path = os.environ.get("DCA_PLANS_FILE", "").strip()
PLANS_FILE = Path(_plans_path) if _plans_path else AGENT_DIR / "dca_plans.json"  # legacy import only
SCHEDULER_POLL_SECONDS = int(os.environ.get("DCA_SCHEDULER_POLL_SECONDS", "30"))
HEADERS = {"User-Agent": "SolanaDCAAgent/1.0", "Content-Type": "application/json"}

SOL_ADDRESS_SHORT = "11111111111111111111111111111111"
SOL_ADDRESS_FULL  = "So11111111111111111111111111111111111111112"

INTERVAL_PRESETS = {
    "every_30_seconds": 0.5,
    "every_minute":     1,
    "every_5_minutes":  5,
    "every_15_minutes": 15,
    "hourly":           60,
    "every_4_hours":    240,
    "every_12_hours":   720,
    "daily":            1440,
    "weekly":           10080,
    "biweekly":         20160,
    "monthly":          43200,
}

TOKEN_MINTS = {
    "SOL":    {"mint": SOL_ADDRESS_FULL,                                    "decimals": 9,  "coingecko_id": "solana"},
    "WSOL":   {"mint": SOL_ADDRESS_FULL,                                    "decimals": 9,  "coingecko_id": "solana"},
    "USDC":   {"mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",    "decimals": 6,  "coingecko_id": "usd-coin"},
    "USDT":   {"mint": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",    "decimals": 6,  "coingecko_id": "tether"},
    "JUP":    {"mint": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",     "decimals": 6,  "coingecko_id": "jupiter-exchange-solana"},
    "BONK":   {"mint": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",   "decimals": 5,  "coingecko_id": "bonk"},
    "WIF":    {"mint": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",   "decimals": 6,  "coingecko_id": "dogwifcoin"},
    "RAY":    {"mint": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",   "decimals": 6,  "coingecko_id": "raydium"},
    "ORCA":   {"mint": "orcaEKTdK7LKz57vaAYr9QeNs490PNsTPTvJaq2qDz8",    "decimals": 6,  "coingecko_id": "orca"},
    "PYTH":   {"mint": "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3",   "decimals": 6,  "coingecko_id": "pyth-network"},
    "JTO":    {"mint": "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL",    "decimals": 9,  "coingecko_id": "jito-governance-token"},
    "RENDER": {"mint": "rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHBof",    "decimals": 8,  "coingecko_id": "render-token"},
}

MINT_TO_SYMBOL = {info["mint"]: sym for sym, info in TOKEN_MINTS.items() if sym != "WSOL"}
_RESOLVED_TOKEN_CACHE: dict[str, dict] = {}

_scheduler_lock    = threading.Lock()
_scheduler_running = False
_metrics_lock      = threading.Lock()
_metrics_running   = False

# Plan feasibility limits
MIN_INTERVAL_SECONDS = 10
MAX_MAX_EXECUTIONS = 10_000
MAX_PLAN_DURATION_DAYS = 730
MIN_TOKEN_AMOUNTS: dict[str, float] = {
    "SOL": 0.000001,
    "WSOL": 0.000001,
    "USDC": 0.01,
    "USDT": 0.01,
}
DEFAULT_MIN_TOKEN_AMOUNT = 0.000001
METRICS_REFRESH_SECONDS = int(os.environ.get("DCA_METRICS_REFRESH_SECONDS", str(24 * 3600)))

# Rate-limit state (mirrors jupiterFetch in Node.js)
_last_jupiter_call_at: float = 0.0
_jupiter_lock = threading.Lock()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _coerce_nullable_float(val) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, str):
        if val.strip().lower() in ("null", "none", ""):
            return None
        return float(val)
    return float(val)


def _coerce_nullable_int(val) -> Optional[int]:
    if val is None:
        return None
    if isinstance(val, str):
        if val.strip().lower() in ("null", "none", ""):
            return None
        return int(val)
    return int(val)


def _coerce_bool(val) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes")
    return bool(val)


def _jupiter_headers() -> dict:
    """Build Jupiter request headers, including API key when configured."""
    h = {**HEADERS}
    if JUPITER_API_KEY:
        h["x-api-key"] = JUPITER_API_KEY
    return h


def _jupiter_get(url: str, params: dict, max_retries: int = 4) -> requests.Response:
    """
    GET wrapper for Jupiter API with:
      • 1-second minimum spacing between calls (mirrors lastApiCallAt logic)
      • Exponential back-off on 429 Too Many Requests
    """
    global _last_jupiter_call_at
    with _jupiter_lock:
        wait = 1.0 - (time.time() - _last_jupiter_call_at)
        if wait > 0:
            time.sleep(wait)

    backoff = 1.0
    for attempt in range(1, max_retries + 1):
        resp = requests.get(url, params=params, headers=_jupiter_headers(), timeout=30)
        with _jupiter_lock:
            _last_jupiter_call_at = time.time()
        if resp.status_code != 429:
            return resp
        retry_after = resp.headers.get("Retry-After")
        wait_ms = (int(retry_after) if retry_after else backoff)
        print(f"  ⚠️  429 Too Many Requests. Retrying after {wait_ms:.1f}s (attempt {attempt}/{max_retries})...")
        time.sleep(wait_ms)
        backoff = min(backoff * 2, 16.0)

    # Final attempt after exhausting retries
    resp = requests.get(url, params=params, headers=_jupiter_headers(), timeout=30)
    with _jupiter_lock:
        _last_jupiter_call_at = time.time()
    return resp


def _jupiter_post(url: str, payload: dict, max_retries: int = 4) -> requests.Response:
    """
    POST wrapper for Jupiter API with the same rate-limit / back-off logic.
    """
    global _last_jupiter_call_at
    with _jupiter_lock:
        wait = 1.0 - (time.time() - _last_jupiter_call_at)
        if wait > 0:
            time.sleep(wait)

    backoff = 1.0
    for attempt in range(1, max_retries + 1):
        resp = requests.post(url, json=payload, headers=_jupiter_headers(), timeout=30)
        with _jupiter_lock:
            _last_jupiter_call_at = time.time()
        if resp.status_code != 429:
            return resp
        retry_after = resp.headers.get("Retry-After")
        wait_ms = (int(retry_after) if retry_after else backoff)
        print(f"  ⚠️  429 Too Many Requests. Retrying after {wait_ms:.1f}s (attempt {attempt}/{max_retries})...")
        time.sleep(wait_ms)
        backoff = min(backoff * 2, 16.0)

    resp = requests.post(url, json=payload, headers=_jupiter_headers(), timeout=30)
    with _jupiter_lock:
        _last_jupiter_call_at = time.time()
    return resp


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


def _rpc_u64(value: Any) -> int:
    """Normalize Solana RPC numeric results (plain int or {value: int})."""
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    if isinstance(value, dict):
        for key in ("value", "amount", "lamports"):
            if key in value:
                return _rpc_u64(value[key])
    return 0


def _short_mint(mint: str) -> str:
    if len(mint) <= 12:
        return mint
    return f"{mint[:4]}...{mint[-4:]}"


def _looks_like_mint(value: str) -> bool:
    value = value.strip()
    if len(value) < 32 or len(value) > 44:
        return False
    if not HAS_SOLDERS:
        return bool(re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]+", value))
    try:
        return len(base58.b58decode(value)) == 32
    except Exception:
        return False


def _cache_token_result(raw: str, result: dict, *, cache_symbol: bool = True) -> dict:
    if "error" in result:
        return result
    _RESOLVED_TOKEN_CACHE[raw] = result
    _RESOLVED_TOKEN_CACHE[result["mint"]] = result
    if cache_symbol:
        _RESOLVED_TOKEN_CACHE[result["symbol"]] = result
    return result


def _fetch_mint_decimals_rpc(mint: str) -> Optional[int]:
    try:
        result = sol_rpc("getAccountInfo", [mint, {"encoding": "jsonParsed"}])
        if not result or not result.get("value"):
            return None
        data = result["value"].get("data")
        if not isinstance(data, dict):
            return None
        parsed = data.get("parsed") or {}
        if parsed.get("type") != "mint":
            return None
        decimals = parsed.get("info", {}).get("decimals")
        return int(decimals) if decimals is not None else None
    except Exception:
        return None


def _fetch_token_from_jupiter(query: str) -> Optional[dict]:
    try:
        resp = _jupiter_get(f"{JUPITER_TOKENS_API}/search", {"query": query})
        if resp.status_code != 200:
            return None
        items = resp.json()
        if not isinstance(items, list) or not items:
            return None
        query_stripped = query.strip()

        # Mint lookups must match exactly - never guess with items[0].
        if _looks_like_mint(query_stripped):
            for item in items:
                if item.get("id") == query_stripped:
                    return item
            return None

        for item in items:
            if item.get("id") == query_stripped:
                return item
        query_upper = query_stripped.upper()
        for item in items:
            if str(item.get("symbol", "")).upper() == query_upper:
                return item
        return items[0]
    except Exception:
        return None


def _resolve_by_mint(mint: str) -> dict:
    mint = mint.strip()
    cached = _RESOLVED_TOKEN_CACHE.get(mint)
    if cached and cached.get("mint") == mint:
        return cached

    known_sym = MINT_TO_SYMBOL.get(mint)
    if known_sym:
        result = {"symbol": known_sym, **TOKEN_MINTS[known_sym], "mint": mint}
        return _cache_token_result(mint, result, cache_symbol=True)

    jup = _fetch_token_from_jupiter(mint)
    if jup and jup.get("id") == mint:
        result = {
            "symbol": str(jup.get("symbol") or _short_mint(mint)).upper(),
            "mint": mint,
            "decimals": int(jup.get("decimals", 0)),
            "coingecko_id": None,
            "name": jup.get("name"),
            "usd_price": jup.get("usdPrice"),
        }
        return _cache_token_result(mint, result, cache_symbol=False)

    decimals = _fetch_mint_decimals_rpc(mint)
    if decimals is None:
        return {"error": f"Unknown token mint '{mint}'. Could not resolve decimals on-chain."}

    result = {
        "symbol": _short_mint(mint).upper(),
        "mint": mint,
        "decimals": decimals,
        "coingecko_id": None,
    }
    return _cache_token_result(mint, result, cache_symbol=False)


def resolve_token(symbol_or_mint: str) -> dict:
    raw = (symbol_or_mint or "").strip()
    if not raw:
        return {"error": "Token symbol or mint address is required."}

    cached = _RESOLVED_TOKEN_CACHE.get(raw) or _RESOLVED_TOKEN_CACHE.get(raw.upper())
    if cached:
        return cached

    sym = raw.upper()
    if sym in TOKEN_MINTS:
        return _cache_token_result(raw, {"symbol": sym, **TOKEN_MINTS[sym]})

    if _looks_like_mint(raw):
        return _resolve_by_mint(raw)

    jup = _fetch_token_from_jupiter(raw)
    if jup and jup.get("id"):
        result = {
            "symbol": str(jup.get("symbol") or sym).upper(),
            "mint": jup["id"],
            "decimals": int(jup.get("decimals", 0)),
            "coingecko_id": None,
            "name": jup.get("name"),
            "usd_price": jup.get("usdPrice"),
        }
        return _cache_token_result(raw, result)

    common = ", ".join(sorted(k for k in TOKEN_MINTS if k != "WSOL"))
    return {
        "error": (
            f"Unknown token '{symbol_or_mint}'. "
            f"Pass a token symbol, mint address, or a common token ({common})."
        )
    }


def _lamports(amount: float, decimals: int) -> int:
    return int(round(amount * (10 ** decimals)))


def _fmt_ts(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


# ─── ATA check (mirrors ataExists in Node.js) ─────────────────────────────────

def _ata_exists(wallet_pubkey: str, mint_address: str) -> bool:
    """Return True if the wallet already has a token account for this mint."""
    if mint_address in (SOL_ADDRESS_FULL, SOL_ADDRESS_SHORT):
        return True  # Native SOL never needs an ATA
    try:
        result = sol_rpc(
            "getTokenAccountsByOwner",
            [
                wallet_pubkey,
                {"mint": mint_address},
                {"encoding": "jsonParsed"},
            ],
        )
        return bool(result and result.get("value"))
    except Exception:
        return False


# ─── Plan persistence (Neon PostgreSQL) ───────────────────────────────────────

from db import claim_due_dca_plans
from db import find_plan as _find_plan_db
from db import insert_plan as _insert_plan_db
from db import load_all_plans
from db import update_plan as _update_plan_db


def _load_plans(user_wallet: Optional[str] = None) -> list:
    return load_all_plans(user_wallet)


def _find_plan(plan_id: str) -> Optional[dict]:
    return _find_plan_db(plan_id)


def _assert_plan_owner(plan_id: str, user_wallet: str) -> dict:
    plan = _find_plan(plan_id)
    if not plan:
        return {"error": f"Plan '{plan_id}' not found."}
    owner = (plan.get("user_wallet") or "").strip()
    if owner and owner != user_wallet.strip():
        return {"error": "Forbidden: this plan belongs to another wallet."}
    if not owner:
        return {"error": "Forbidden: plan has no owner wallet."}
    return plan


def _update_plan(plan_id: str, updates: dict) -> Optional[dict]:
    return _update_plan_db(plan_id, updates)


# ─── Solana reads ─────────────────────────────────────────────────────────────

def get_wallet_status() -> dict:
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
        lamports = _rpc_u64(sol_rpc("getBalance", [pubkey]))
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
    tok = resolve_token(symbol)
    if "error" in tok:
        return tok
    fetched_at = _fmt_ts(datetime.now(timezone.utc))
    if tok.get("coingecko_id"):
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
                "mint": tok["mint"],
                "price_usd": data.get("usd"),
                "change_24h_pct": data.get("usd_24h_change"),
                "source": "coingecko",
                "fetched_at": fetched_at,
            }
        except Exception as e:
            return {"error": str(e)}

    if tok.get("usd_price") is not None:
        return {
            "symbol": tok["symbol"],
            "mint": tok["mint"],
            "price_usd": tok["usd_price"],
            "source": "jupiter",
            "fetched_at": fetched_at,
        }

    try:
        resp = _jupiter_get(JUPITER_PRICE_API, {"ids": tok["mint"]})
        if resp.status_code == 200:
            data = resp.json().get("data", {}).get(tok["mint"]) or resp.json().get(tok["mint"])
            if isinstance(data, dict) and data.get("price") is not None:
                return {
                    "symbol": tok["symbol"],
                    "mint": tok["mint"],
                    "price_usd": float(data["price"]),
                    "source": "jupiter",
                    "fetched_at": fetched_at,
                }
    except Exception:
        pass

    return {
        "symbol": tok["symbol"],
        "mint": tok["mint"],
        "price_usd": None,
        "note": "Price unavailable for this token; swaps still work via Jupiter.",
        "fetched_at": fetched_at,
    }


# ─── Jupiter v2 build API (replaces /v6/quote + /v6/swap) ─────────────────────

def get_jupiter_quote(
    input_token: str,
    output_token: str,
    amount: float,
    slippage_bps: int = 100,
    taker: Optional[str] = None,
) -> dict:
    """
    Preview a swap using the Jupiter v2 build API.

    Jupiter v2 requires a taker wallet address even for quote previews.
    Defaults to the configured AI Agent wallet pubkey.
    """
    amount = float(amount)
    slippage_bps = int(slippage_bps)

    if not _is_mainnet():
        return {
            "error": "Jupiter quotes require mainnet RPC. Current cluster is devnet.",
            "hint": "Set SOLANA_RPC_URL to a mainnet endpoint for token swaps.",
        }

    wallet_pubkey = (taker or get_wallet_pubkey() or "").strip()
    if not wallet_pubkey:
        return {
            "error": "AI Agent wallet not configured. Set DCA_WALLET_PRIVATE_KEY for Jupiter quotes.",
        }

    inp = resolve_token(input_token)
    out = resolve_token(output_token)
    if "error" in inp:
        return inp
    if "error" in out:
        return out

    raw_amount = _lamports(amount, inp["decimals"])

    params = {
        "inputMint":                  inp["mint"],
        "outputMint":                 out["mint"],
        "amount":                     str(raw_amount),
        "taker":                      wallet_pubkey,
        "payer":                      wallet_pubkey,
        "slippageBps":                str(slippage_bps),
        "wrapAndUnwrapSol":           "true",
        "computeUnitPricePercentile": "high",
        "maxAccounts":                "54",
        "skipUserAccountsRpcCalls":   "true",
    }

    try:
        resp = _jupiter_get(JUPITER_BUILD_API, params)
        if not resp.ok:
            err = {}
            try:
                err = resp.json()
            except Exception:
                pass
            return {"error": f"Jupiter /build HTTP {resp.status_code}: {err}"}

        data = resp.json()
        if "error" in data:
            return {"error": data["error"]}

        out_amount_raw = int(data.get("outAmount", 0))
        out_amount     = out_amount_raw / (10 ** out["decimals"])

        return {
            "input_token":       inp["symbol"],
            "output_token":      out["symbol"],
            "input_amount":      amount,
            "estimated_output":  round(out_amount, 8),
            "price_impact_pct":  data.get("priceImpactPct"),
            "slippage_bps":      slippage_bps,
            "build_data":        data,   # retained for _execute_jupiter_swap
        }
    except Exception as e:
        return {"error": str(e)}


def _confirm_transaction(sig: str, timeout_s: int = 60, poll_s: float = 2.0) -> dict:
    """
    Poll the RPC for signature confirmation - mirrors the polling loop
    in executeSwap() in the Node.js collateral-swap script.
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(poll_s)
        try:
            result = sol_rpc(
                "getSignatureStatuses",
                [[sig], {"searchTransactionHistory": False}],
            )
            info = result["value"][0] if result and result.get("value") else None
            if info:
                if info.get("err"):
                    return {"confirmed": False, "error": info["err"]}
                status = info.get("confirmationStatus", "")
                if status in ("confirmed", "finalized"):
                    return {"confirmed": True}
        except Exception:
            pass  # RPC hiccup - keep polling

    return {"confirmed": False, "error": f"Confirmation timed out after {timeout_s}s"}


def _to_instruction(ix_data: dict):
    """
    Convert a Jupiter instruction dict to a solders AccountMeta + instruction tuple.

    Mirrors toTxInstruction() in the Node.js script.
    ix_data keys: programId, accounts [{pubkey, isWritable, isSigner}], data (base64)
    """
    from solders.instruction import Instruction, AccountMeta
    from solders.pubkey import Pubkey as SPubkey

    program_id = SPubkey.from_string(ix_data["programId"])
    accounts = [
        AccountMeta(
            pubkey=SPubkey.from_string(a["pubkey"]),
            is_writable=a["isWritable"],
            is_signer=a["isSigner"],
        )
        for a in ix_data.get("accounts", [])
    ]
    data = base64.b64decode(ix_data["data"])
    return Instruction(program_id, data, accounts)


def _fetch_lookup_tables(addresses_by_table: Optional[dict]) -> list:
    """
    Fetch Address Lookup Table accounts from the RPC.

    Mirrors fetchLookupTables() in the Node.js script.
    addresses_by_table: { tableAddress: [addr, ...], ... }
    Returns list of dicts: {key, addresses} for use with MessageV0.try_compile.
    """
    if not addresses_by_table:
        return []

    table_keys = list(addresses_by_table.keys())
    if not table_keys:
        return []

    try:
        result = sol_rpc(
            "getMultipleAccounts",
            [table_keys, {"encoding": "base64", "commitment": "confirmed"}],
        )
        accounts = result.get("value", []) if result else []
    except Exception as e:
        print(f"  ⚠️  Failed to fetch LUTs: {e}")
        return []

    from solders.pubkey import Pubkey as SPubkey
    from solders.address_lookup_table_account import AddressLookupTableAccount

    luts = []
    for i, key in enumerate(table_keys):
        acct = accounts[i] if i < len(accounts) else None
        if not acct or not acct.get("data"):
            print(f"  ⚠️  LUT not found on-chain: {key[:10]}...")
            continue
        try:
            raw = base64.b64decode(acct["data"][0])
            luts.append(
                AddressLookupTableAccount(
                    key=SPubkey.from_string(key),
                    addresses=[SPubkey.from_string(a) for a in addresses_by_table[key]],
                )
            )
        except Exception as e:
            print(f"  ⚠️  Failed to parse LUT {key[:10]}...: {e}")

    return luts


def _execute_jupiter_swap_v2(build_data: dict, wallet_pubkey: str, keypair: "Keypair") -> dict:
    """
    Assemble, sign, and send a Jupiter v2 swap transaction.

    The /swap/v2/build endpoint returns raw instructions (NOT a pre-built tx blob):
      - computeBudgetInstructions  (list)
      - setupInstructions          (list)
      - swapInstruction            (single)
      - cleanupInstruction         (single, optional)
      - otherInstructions          (list)
      - addressesByLookupTableAddress  (dict of LUT key → [addresses])

    This mirrors the full flow in executeSwap() in the Node.js collateral script:
      1. Convert each instruction dict → solders Instruction
      2. Fetch Address Lookup Table accounts from RPC
      3. Get latest blockhash
      4. Compile MessageV0 with LUTs
      5. Sign VersionedTransaction
      6. Send via RPC sendTransaction (skipPreflight=True)
      7. Poll for confirmation
    """
    if not HAS_SOLDERS:
        return {"error": "Install solders + base58: pip install solders base58"}

    try:
        from solders.message import MessageV0
        from solders.hash import Hash
        from solders.pubkey import Pubkey as SPubkey
    except ImportError as e:
        return {"error": f"solders import failed: {e}"}

    # ── 1. Collect all instructions in order (mirrors Node.js) ────────────────
    try:
        instructions = []

        for ix in build_data.get("computeBudgetInstructions") or []:
            instructions.append(_to_instruction(ix))

        for ix in build_data.get("setupInstructions") or []:
            instructions.append(_to_instruction(ix))

        swap_ix = build_data.get("swapInstruction")
        if not swap_ix:
            return {"error": "No swapInstruction in Jupiter v2 build response", "keys": list(build_data.keys())}
        instructions.append(_to_instruction(swap_ix))

        cleanup_ix = build_data.get("cleanupInstruction")
        if cleanup_ix:
            instructions.append(_to_instruction(cleanup_ix))

        for ix in build_data.get("otherInstructions") or []:
            instructions.append(_to_instruction(ix))

    except Exception as e:
        return {"error": f"Instruction assembly failed: {e}"}

    # ── 2. Fetch Address Lookup Tables ─────────────────────────────────────────
    luts = _fetch_lookup_tables(build_data.get("addressesByLookupTableAddress"))

    # ── 3. Get latest blockhash ────────────────────────────────────────────────
    try:
        bh_result = sol_rpc("getLatestBlockhash", [{"commitment": "finalized"}])
        blockhash = Hash.from_string(bh_result["value"]["blockhash"])
    except Exception as e:
        return {"error": f"Failed to fetch blockhash: {e}"}

    # ── 4. Compile MessageV0 with LUTs + sign ──────────────────────────────────
    try:
        payer = SPubkey.from_string(wallet_pubkey)
        msg   = MessageV0.try_compile(payer, instructions, luts, blockhash)
        tx    = VersionedTransaction(msg, [keypair])
        encoded = base64.b64encode(bytes(tx)).decode("utf-8")
    except Exception as e:
        return {"error": f"Transaction compilation/signing failed: {e}"}

    # ── 5. Send via RPC (skipPreflight mirrors Node.js) ───────────────────────
    try:
        sig = sol_rpc(
            "sendTransaction",
            [encoded, {
                "encoding":            "base64",
                "skipPreflight":       True,   # preflight uses stale state; real errors surface on-chain
                "preflightCommitment": "confirmed",
                "maxRetries":          3,
            }],
        )
    except Exception as e:
        return {"error": f"sendTransaction failed: {e}"}

    print(f"    Signature: {sig}")

    # ── 6. Poll for confirmation ───────────────────────────────────────────────
    confirm = _confirm_transaction(sig)
    if not confirm["confirmed"]:
        err     = confirm.get("error", "unknown")
        err_str = json.dumps(err)
        if "'Custom':1" in err_str or (isinstance(err, dict) and err.get("InstructionError")):
            print("    ↳ Custom:1 usually means insufficient SOL for ATA rent (~0.002 SOL per new token account)")
        return {"status": "failed", "signature": sig, "error": err}

    print("    Status: ✅ Success")
    explorer_cluster = "mainnet" if _is_mainnet() else "devnet"
    return {
        "status":       "success",
        "signature":    sig,
        "explorer_url": f"https://explorer.solana.com/tx/{sig}?cluster={explorer_cluster}",
    }


def _build_and_execute_swap(
    input_mint: str,
    output_mint: str,
    raw_amount: int,
    wallet_pubkey: str,
    keypair: "Keypair",
    slippage_bps: int = 100,
    retries: int = 2,
) -> dict:
    """
    Build + sign + send a swap via Jupiter v2.

    Mirrors executeSwap() in the Node.js script - one call to /build,
    then sign and submit via the Solana RPC.

    Retry logic:
      • Expired / timed-out → retry up to `retries` times
      • Transaction too large → retry once with higher slippage (200 bps)
    """
    for attempt in range(1, retries + 1):
        params = {
            "inputMint":                  input_mint,
            "outputMint":                 output_mint,
            "amount":                     str(raw_amount),
            "taker":                      wallet_pubkey,
            "payer":                      wallet_pubkey,
            "slippageBps":                str(slippage_bps),
            "wrapAndUnwrapSol":           "true",
            "computeUnitPricePercentile": "high",
            "maxAccounts":                "54",
            "skipUserAccountsRpcCalls":   "true",
        }

        try:
            resp = _jupiter_get(JUPITER_BUILD_API, params)

            if not resp.ok:
                err = {}
                try:
                    err = resp.json()
                except Exception:
                    pass
                msg = f"/build HTTP {resp.status_code}: {err}"

                # "Transaction too large" can appear as an HTTP error body
                if "too large" in str(err).lower() or "too large" in str(resp.text).lower():
                    if slippage_bps < 200:
                        print("    ↳ Transaction too large, retrying with higher slippage for simpler route...")
                        return _build_and_execute_swap(
                            input_mint, output_mint, raw_amount,
                            wallet_pubkey, keypair, slippage_bps=200, retries=1,
                        )
                    print("    ↳ Transaction too large even with higher slippage, skipping")
                    return {"status": "failed", "error": msg}

                raise RuntimeError(msg)

            build_data = resp.json()
            if "error" in build_data:
                raise RuntimeError(f"/build error: {build_data['error']}")

            result = _execute_jupiter_swap_v2(build_data, wallet_pubkey, keypair)

            if result.get("status") == "success":
                out_raw = int(build_data.get("outAmount") or 0)
                if out_raw > 0:
                    result["output_amount_raw"] = out_raw

            if result.get("status") == "failed":
                err_str = str(result.get("error", ""))
                is_expiry = any(k in err_str.lower() for k in ("block height exceeded", "expired", "timed out"))
                is_too_large = "too large" in err_str.lower()

                if is_too_large:
                    if slippage_bps < 200:
                        print("    ↳ Transaction too large, retrying with higher slippage for simpler route...")
                        return _build_and_execute_swap(
                            input_mint, output_mint, raw_amount,
                            wallet_pubkey, keypair, slippage_bps=200, retries=1,
                        )
                    print("    ↳ Transaction too large even with higher slippage, skipping")
                    return result

                if is_expiry and attempt < retries:
                    print(f"    ↳ Transaction expired, retrying (attempt {attempt}/{retries})...")
                    time.sleep(1)
                    continue

            return result

        except Exception as e:
            msg = str(e)
            is_expiry = any(k in msg.lower() for k in ("block height exceeded", "expired", "timed out"))
            if is_expiry and attempt < retries:
                print(f"    ↳ Transaction expired, retrying (attempt {attempt}/{retries})...")
                time.sleep(1)
                continue
            return {"status": "failed", "error": msg}

    return {"status": "failed", "error": "Max retries reached"}


def execute_swap_buy(
    input_token: str,
    output_token: str,
    amount: float,
    slippage_bps: int = 100,
    dry_run: bool = False,
    user_wallet: Optional[str] = None,
) -> dict:
    """Execute one DCA buy: Jupiter v2 swap on mainnet, SOL self-transfer on devnet."""
    amount       = float(amount)
    slippage_bps = int(slippage_bps)
    dry_run      = _coerce_bool(dry_run)

    if dry_run:
        if user_wallet:
            from deposit_ledger import check_user_can_spend

            spend_check = check_user_can_spend(user_wallet, input_token, amount)
            if "error" in spend_check:
                return spend_check

        quote = get_jupiter_quote(input_token, output_token, amount, slippage_bps)
        preview = {k: v for k, v in quote.items() if k != "build_data"} if isinstance(quote, dict) else quote
        return {
            "status":       "dry_run",
            "would_buy":    f"{amount} {input_token.upper()} -> {output_token.upper()}",
            "quote_preview": preview,
        }

    from deposit_ledger import check_user_can_spend

    spend_check = check_user_can_spend(user_wallet or "", input_token, amount)
    if "error" in spend_check:
        return spend_check

    if _is_mainnet():
        inp = resolve_token(input_token)
        out = resolve_token(output_token)
        if "error" in inp:
            return inp
        if "error" in out:
            return out

        keypair = load_keypair()
        if not keypair:
            return {"error": "No wallet keypair. Set DCA_WALLET_PRIVATE_KEY."}
        if not HAS_SOLDERS:
            return {"error": "Install solders + base58: pip install solders base58"}

        wallet_pubkey = str(keypair.pubkey())
        raw_amount    = _lamports(amount, inp["decimals"])

        # Warn about missing ATAs (mirrors checkBalance in Node.js)
        if not _ata_exists(wallet_pubkey, out["mint"]):
            print(f"  ⚠️  ATA missing for {out['symbol']} - ~0.002 SOL needed for account creation")

        result = _build_and_execute_swap(
            inp["mint"], out["mint"], raw_amount,
            wallet_pubkey, keypair, slippage_bps,
        )

        if result.get("status") == "success":
            result["input_token"]  = inp["symbol"]
            result["output_token"] = out["symbol"]
            result["input_amount"] = amount
            out_raw = int(result.get("output_amount_raw") or 0)
            if out_raw > 0:
                result["output_amount"] = round(out_raw / (10 ** out["decimals"]), 9)
            if user_wallet:
                from deposit_ledger import record_user_acquire, record_user_spend

                record_user_spend(
                    user_wallet,
                    inp["symbol"],
                    amount,
                    reference_type="swap",
                    reference_id=(result.get("signature") or "swap")[:128],
                    signature=result.get("signature"),
                )
                if out_raw > 0:
                    record_user_acquire(
                        user_wallet,
                        out["symbol"],
                        result["output_amount"],
                        reference_type="swap",
                        reference_id=(result.get("signature") or "swap")[:128],
                        signature=result.get("signature"),
                    )

        return result

    # ── Devnet fallback ────────────────────────────────────────────────────────
    return _execute_devnet_sol_transfer(min(amount, 0.001))


def _execute_devnet_sol_transfer(amount_sol: float) -> dict:
    """Devnet fallback: small SOL self-transfer as proof-of-execution."""
    keypair = load_keypair()
    if not keypair or not HAS_SOLDERS:
        return {"error": "Wallet + solders required for devnet execution."}

    try:
        from solders.system_program import TransferParams, transfer
        from solders.message import MessageV0
        from solders.hash import Hash

        pubkey   = keypair.pubkey()
        lamports = max(int(float(amount_sol) * 1e9), 5000)

        blockhash_resp = sol_rpc("getLatestBlockhash", [{"commitment": "finalized"}])
        blockhash      = Hash.from_string(blockhash_resp["value"]["blockhash"])

        ix  = transfer(TransferParams(from_pubkey=pubkey, to_pubkey=pubkey, lamports=lamports))
        msg = MessageV0.try_compile(pubkey, [ix], [], blockhash)
        tx  = VersionedTransaction(msg, [keypair])
        encoded = base64.b64encode(bytes(tx)).decode("utf-8")
        sig = sol_rpc(
            "sendTransaction",
            [encoded, {"encoding": "base64", "skipPreflight": False, "maxRetries": 3}],
        )
        return {
            "status":       "success",
            "mode":         "devnet_sol_self_transfer",
            "signature":    sig,
            "explorer_url": f"https://explorer.solana.com/tx/{sig}?cluster=devnet",
            "note":         "Devnet cannot use Jupiter. Executed SOL self-transfer as scheduled tx proof.",
        }
    except Exception as e:
        return {"error": str(e)}


ASSOCIATED_TOKEN_PROGRAM_ID = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM_ID = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
SYSTEM_PROGRAM_ID = SOL_ADDRESS_SHORT


def _resolve_token_program_for_mint(mint_address: str) -> str:
    """Return SPL Token or Token-2022 program id for a mint."""
    try:
        result = sol_rpc("getAccountInfo", [mint_address, {"encoding": "jsonParsed"}])
        owner = (result or {}).get("value", {}).get("owner")
        if owner == TOKEN_2022_PROGRAM_ID:
            return TOKEN_2022_PROGRAM_ID
    except Exception:
        pass
    return TOKEN_PROGRAM_ID


def _associated_token_address(
    owner: "Pubkey",
    mint: "Pubkey",
    token_program_id: str = TOKEN_PROGRAM_ID,
) -> "Pubkey":
    token_program = Pubkey.from_string(token_program_id)
    ata_program = Pubkey.from_string(ASSOCIATED_TOKEN_PROGRAM_ID)
    addr, _ = Pubkey.find_program_address(
        [bytes(owner), bytes(token_program), bytes(mint)],
        ata_program,
    )
    return addr


def _spl_transfer_instruction(
    source: "Pubkey",
    dest: "Pubkey",
    owner: "Pubkey",
    amount: int,
    token_program_id: str = TOKEN_PROGRAM_ID,
):
    import struct

    from solders.instruction import AccountMeta, Instruction

    data = bytes([3]) + struct.pack("<Q", amount)
    return Instruction(
        Pubkey.from_string(token_program_id),
        data,
        [
            AccountMeta(source, False, True),
            AccountMeta(dest, False, True),
            AccountMeta(owner, True, False),
        ],
    )


def _create_ata_instruction(
    payer: "Pubkey",
    owner: "Pubkey",
    mint: "Pubkey",
    token_program_id: str = TOKEN_PROGRAM_ID,
    idempotent: bool = True,
):
    from solders.instruction import AccountMeta, Instruction

    ata = _associated_token_address(owner, mint, token_program_id)
    # CreateIdempotent (1) succeeds even if the ATA already exists.
    data = bytes([1]) if idempotent else bytes([])
    return Instruction(
        Pubkey.from_string(ASSOCIATED_TOKEN_PROGRAM_ID),
        data,
        [
            AccountMeta(payer, True, True),
            AccountMeta(ata, False, True),
            AccountMeta(owner, False, False),
            AccountMeta(mint, False, False),
            AccountMeta(Pubkey.from_string(SYSTEM_PROGRAM_ID), False, False),
            AccountMeta(Pubkey.from_string(token_program_id), False, False),
        ],
    )


def _normalize_rpc_pubkey(value: Any) -> Optional[str]:
    if isinstance(value, str) and len(value.strip()) >= 32:
        return value.strip()
    if isinstance(value, dict):
        for key in ("pubkey", "address", "value"):
            nested = value.get(key)
            if isinstance(nested, str) and len(nested.strip()) >= 32:
                return nested.strip()
    return None


def _parse_token_account_entry(entry: dict) -> tuple[Optional[str], int, str]:
    """Parse getTokenAccountsByOwner entry -> (pubkey, raw_amount, token_program_id)."""
    pubkey = _normalize_rpc_pubkey(entry.get("pubkey"))
    account = entry.get("account") or {}
    program_id = account.get("owner") or TOKEN_PROGRAM_ID
    raw = 0
    data = account.get("data")
    if isinstance(data, dict):
        parsed = data.get("parsed") or {}
        info = parsed.get("info") or {}
        token_amount = info.get("tokenAmount") or {}
        raw = int(token_amount.get("amount") or 0)
    return pubkey, raw, program_id


def _associated_token_account_exists(
    owner_wallet: str,
    mint_address: str,
    token_program_id: str,
) -> bool:
    """True when the wallet's associated token account is already on-chain."""
    try:
        owner = Pubkey.from_string(owner_wallet)
        mint = Pubkey.from_string(mint_address)
        ata = str(_associated_token_address(owner, mint, token_program_id))
        info = sol_rpc("getAccountInfo", [ata, {"encoding": "base64"}])
        return bool(info and info.get("value"))
    except Exception:
        return False


def _find_wallet_token_account(
    wallet_pubkey: str,
    mint_address: str,
    min_raw_amount: int = 1,
) -> Optional[tuple[str, str]]:
    """
    Locate a token account owned by wallet_pubkey with enough balance.
    Returns (token_account_pubkey, token_program_id).
    """
    best: Optional[tuple[str, int, str]] = None

    try:
        result = sol_rpc(
            "getTokenAccountsByOwner",
            [wallet_pubkey, {"mint": mint_address}, {"encoding": "jsonParsed"}],
        )
        for entry in (result or {}).get("value") or []:
            if not isinstance(entry, dict):
                continue
            pubkey, raw, program_id = _parse_token_account_entry(entry)
            if not pubkey or raw < min_raw_amount:
                continue
            if best is None or raw > best[1]:
                best = (pubkey, raw, program_id)
    except Exception:
        pass

    if best:
        return best[0], best[2]

    token_program_id = _resolve_token_program_for_mint(mint_address)
    programs_to_try = []
    for program_id in (token_program_id, TOKEN_PROGRAM_ID, TOKEN_2022_PROGRAM_ID):
        if program_id not in programs_to_try:
            programs_to_try.append(program_id)

    try:
        owner = Pubkey.from_string(wallet_pubkey)
        mint = Pubkey.from_string(mint_address)
    except Exception:
        return None

    for program_id in programs_to_try:
        try:
            derived = str(_associated_token_address(owner, mint, program_id))
            balance = sol_rpc("getTokenAccountBalance", [derived])
            raw = int(((balance or {}).get("value") or {}).get("amount") or 0)
            if raw >= min_raw_amount:
                return derived, program_id
        except Exception:
            continue

    return None


def _wallet_token_account_for_mint(
    wallet_pubkey: str,
    mint_address: str,
    token_program_id: Optional[str] = None,
    min_raw_amount: int = 1,
) -> Optional[str]:
    """Find an existing token account for wallet+mint (legacy or Token-2022)."""
    found = _find_wallet_token_account(wallet_pubkey, mint_address, min_raw_amount)
    if found:
        return found[0]
    return None


def _send_signed_transaction(keypair: "Keypair", instructions: list) -> dict:
    """Compile, sign, send, and confirm a versioned transaction."""
    try:
        from solders.hash import Hash
        from solders.message import MessageV0
    except ImportError as e:
        return {"error": f"solders import failed: {e}"}

    pubkey = keypair.pubkey()
    blockhash_resp = sol_rpc("getLatestBlockhash", [{"commitment": "finalized"}])
    blockhash = Hash.from_string(blockhash_resp["value"]["blockhash"])
    msg = MessageV0.try_compile(pubkey, instructions, [], blockhash)
    tx = VersionedTransaction(msg, [keypair])
    encoded = base64.b64encode(bytes(tx)).decode("utf-8")
    sig = sol_rpc(
        "sendTransaction",
        [encoded, {"encoding": "base64", "skipPreflight": False, "maxRetries": 3}],
    )
    confirm = _confirm_transaction(sig)
    if not confirm["confirmed"]:
        return {"status": "failed", "signature": sig, "error": confirm.get("error", "unknown")}
    explorer_cluster = "mainnet" if _is_mainnet() else "devnet"
    return {
        "status": "success",
        "signature": sig,
        "explorer_url": f"https://explorer.solana.com/tx/{sig}?cluster={explorer_cluster}",
    }


def send_tokens_to_user(
    user_wallet: str,
    mint_address: str,
    amount: float,
    decimals: int,
    signing_keypair: Optional["Keypair"] = None,
) -> dict:
    """Transfer SOL or SPL tokens from the agent wallet to a user wallet."""
    user_wallet = user_wallet.strip()
    if not user_wallet:
        return {"error": "User wallet address is required."}

    keypair = signing_keypair or load_keypair()
    if not keypair:
        return {"error": "AI Agent wallet is not configured on the server."}
    if not HAS_SOLDERS:
        return {"error": "Install solders + base58: pip install solders base58"}

    amount = float(amount)
    if amount <= 0:
        return {"error": "Transfer amount must be greater than zero."}

    try:
        recipient = Pubkey.from_string(user_wallet)
    except Exception:
        return {"error": "Invalid user wallet address."}

    mint_address = mint_address.strip()
    is_sol = mint_address in (SOL_ADDRESS_FULL, SOL_ADDRESS_SHORT)

    if is_sol:
        try:
            from solders.system_program import TransferParams, transfer

            lamports = _lamports(amount, 9)
            ix = transfer(
                TransferParams(
                    from_pubkey=keypair.pubkey(),
                    to_pubkey=recipient,
                    lamports=lamports,
                )
            )
            return _send_signed_transaction(keypair, [ix])
        except Exception as e:
            return {"error": str(e)}

    try:
        mint = Pubkey.from_string(mint_address)
    except Exception:
        return {"error": "Invalid token mint address."}

    raw_amount = _lamports(amount, decimals)
    if raw_amount <= 0:
        return {"error": "Amount is too small for this token's decimals."}

    agent_owner = keypair.pubkey()
    found = _find_wallet_token_account(str(agent_owner), mint_address, raw_amount)
    if not found:
        return {
            "error": (
                f"The agent wallet has no on-chain token account with enough "
                f"{mint_address} to send {amount}. "
                "Your ledger balance may include tokens that are not yet settled on-chain, "
                "or the agent may need SOL for rent when receiving this token. "
                "Try again after the DCA swap confirms, or contact support."
            ),
            "mint": mint_address,
            "requested_amount": amount,
        }

    source_account, token_program_id = found
    source_ata = Pubkey.from_string(source_account)
    dest_ata = _associated_token_address(recipient, mint, token_program_id)

    instructions = []
    if not _associated_token_account_exists(user_wallet, mint_address, token_program_id):
        instructions.append(
            _create_ata_instruction(agent_owner, recipient, mint, token_program_id)
        )
    instructions.append(
        _spl_transfer_instruction(
            source_ata,
            dest_ata,
            agent_owner,
            raw_amount,
            token_program_id,
        )
    )

    try:
        result = _send_signed_transaction(keypair, instructions)
        if result.get("status") == "success":
            result["created_user_ata"] = len(instructions) > 1
        return result
    except Exception as e:
        return {"error": str(e)}


# ─── DCA plan management ──────────────────────────────────────────────────────

def _duration_to_minutes(amount: float, unit: str) -> float:
    u = unit.lower().rstrip(".")
    if u in ("s", "sec", "secs", "second", "seconds"):
        return amount / 60.0
    if u in ("m", "min", "mins", "minute", "minutes"):
        return amount
    if u in ("h", "hr", "hrs", "hour", "hours"):
        return amount * 60.0
    if u in ("d", "day", "days"):
        return amount * 1440.0
    if u in ("w", "week", "weeks"):
        return amount * 10080.0
    raise ValueError(f"Unknown time unit '{unit}'.")


def _parse_interval(interval: str) -> float:
    """Parse a human interval string into minutes (supports fractional minutes)."""
    key = re.sub(r"[\s_-]+", " ", interval.strip().lower()).strip()
    if not key:
        raise ValueError("Interval is required.")

    preset_key = key.replace(" ", "_")
    if preset_key in INTERVAL_PRESETS:
        return INTERVAL_PRESETS[preset_key]

    aliases = {
        "daily": 1440.0,
        "hourly": 60.0,
        "weekly": 10080.0,
        "biweekly": 20160.0,
        "monthly": 43200.0,
    }
    if key in aliases:
        return aliases[key]

    duration_pattern = (
        r"(\d+(?:\.\d+)?)\s*"
        r"(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h|days?|d|weeks?|w)"
    )

    m = re.fullmatch(rf"every\s+{duration_pattern}", key)
    if m:
        return _duration_to_minutes(float(m.group(1)), m.group(2))

    m = re.fullmatch(duration_pattern, key)
    if m:
        return _duration_to_minutes(float(m.group(1)), m.group(2))

    m = re.fullmatch(r"(\d+(?:\.\d+)?)", key)
    if m:
        return float(m.group(1))

    raise ValueError(
        f"Unknown interval '{interval}'. Examples: '11 seconds', '12 minutes', "
        "'every 4 hours', 'daily', or 'every_30_seconds'."
    )


def _normalize_tool_args(func, tool_args: dict) -> dict:
    """Keep only valid parameters; drop unknown keys from model output."""
    import inspect

    if not isinstance(tool_args, dict):
        return {}
    allowed = set(inspect.signature(func).parameters)
    return {k: v for k, v in tool_args.items() if k in allowed}


def _min_amount_for_token(token_info: dict) -> float:
    symbol = str(token_info.get("symbol", "")).upper()
    floor = MIN_TOKEN_AMOUNTS.get(symbol, DEFAULT_MIN_TOKEN_AMOUNT)
    decimals = int(token_info.get("decimals") or 9)
    unit = 10 ** (-decimals)
    return max(floor, unit)


def validate_dca_plan_feasibility(
    inp: dict,
    out: dict,
    amount_per_buy: float,
    interval_minutes: float,
    total_budget: Optional[float],
    max_executions: Optional[int],
    user_wallet: str,
) -> Optional[dict]:
    """Return an error dict if the plan is impossible or unsafe to create."""
    from deposit_ledger import check_plan_budget, dca_execution_total_cost, get_user_balances

    if amount_per_buy <= 0:
        return {"error": "Amount per buy must be greater than zero."}

    min_buy = _min_amount_for_token(inp)
    if amount_per_buy < min_buy:
        return {
            "error": (
                f"Amount per buy ({amount_per_buy} {inp['symbol']}) is below the minimum "
                f"({min_buy} {inp['symbol']}). Swaps this small cannot execute on Solana/Jupiter."
            )
        }

    interval_seconds = interval_minutes * 60
    if interval_seconds < MIN_INTERVAL_SECONDS:
        return {
            "error": (
                f"Interval is too short ({interval_seconds:.0f}s). "
                f"Minimum interval is {MIN_INTERVAL_SECONDS} seconds."
            )
        }

    if max_executions is not None:
        if max_executions <= 0:
            return {"error": "max_executions must be at least 1 when specified."}
        if max_executions > MAX_MAX_EXECUTIONS:
            return {
                "error": (
                    f"max_executions ({max_executions}) exceeds the limit of {MAX_MAX_EXECUTIONS}."
                )
            }
        required = dca_execution_total_cost(amount_per_buy) * max_executions
        if total_budget is not None and total_budget + 1e-12 < required:
            return {
                "error": (
                    f"Budget ({total_budget} {inp['symbol']}) is less than "
                    f"{max_executions} buys × {dca_execution_total_cost(amount_per_buy)} "
                    f"(swap + 0.5% fee) = {required} {inp['symbol']}."
                )
            }
        duration_days = (max_executions * interval_minutes) / (60 * 24)
        if duration_days > MAX_PLAN_DURATION_DAYS:
            return {
                "error": (
                    f"Plan would run for ~{duration_days:.0f} days "
                    f"({max_executions} buys every {interval_minutes} min), "
                    f"which exceeds the {MAX_PLAN_DURATION_DAYS}-day limit."
                )
            }

    if total_budget is not None and total_budget < dca_execution_total_cost(amount_per_buy):
        return {
            "error": (
                f"Total budget ({total_budget} {inp['symbol']}) is less than one buy "
                f"({dca_execution_total_cost(amount_per_buy)} {inp['symbol']} including 0.5% fee)."
            )
        }

    budget_check = check_plan_budget(
        user_wallet,
        inp["symbol"],
        total_budget,
        amount_per_buy,
        max_executions,
    )
    if "error" in budget_check:
        return budget_check

    balances = get_user_balances(user_wallet)
    needed = total_budget
    if needed is None:
        if max_executions is not None:
            needed = dca_execution_total_cost(amount_per_buy) * max_executions
        else:
            needed = dca_execution_total_cost(amount_per_buy)
    available = 0.0
    for row in balances.get("balances") or []:
        if str(row.get("token", "")).upper() == inp["symbol"].upper():
            available = float(row.get("available") or 0)
            break
    if needed is not None and available + 1e-12 < needed:
        return {
            "error": (
                f"Insufficient {inp['symbol']} balance. Need up to {needed}, "
                f"but only {available} is available after plan reservations."
            )
        }

    if inp["mint"] == out["mint"]:
        return {"error": "Input and output token cannot be the same."}

    return None


def create_dca_plan(
    input_token: str,
    output_token: str,
    amount_per_buy: float,
    interval: str,
    name: Optional[str] = None,
    user_wallet: Optional[str] = None,
    total_budget: Optional[float] = None,
    max_executions: Optional[int] = None,
    slippage_bps: int = 100,
    start_immediately: bool = False,
) -> dict:
    amount_per_buy  = float(amount_per_buy)
    slippage_bps    = int(slippage_bps)
    total_budget    = _coerce_nullable_float(total_budget)
    max_executions  = _coerce_nullable_int(max_executions)
    start_immediately = _coerce_bool(start_immediately)

    inp = resolve_token(input_token)
    out = resolve_token(output_token)
    if "error" in inp:
        return inp
    if "error" in out:
        return out

    if not user_wallet or not str(user_wallet).strip():
        return {"error": "user_wallet is required. User must connect wallet and authenticate first."}

    if not name or not str(name).strip():
        mint_tail = out["mint"][-4:]
        sym = out["symbol"]
        if _looks_like_mint(str(output_token).strip()):
            name = f"{inp['symbol']} -> {sym} ({mint_tail}) DCA"
        else:
            name = f"{inp['symbol']} -> {sym} DCA"

    try:
        interval_minutes = _parse_interval(interval)
    except ValueError as e:
        return {"error": str(e)}

    feasibility = validate_dca_plan_feasibility(
        inp,
        out,
        amount_per_buy,
        interval_minutes,
        total_budget,
        max_executions,
        user_wallet.strip(),
    )
    if feasibility:
        return feasibility

    now      = datetime.now(timezone.utc)
    next_run = now if start_immediately else now + timedelta(minutes=interval_minutes)

    plan = {
        "id":                str(uuid.uuid4())[:8],
        "name":              name,
        "input_token":       inp["symbol"],
        "output_token":      out["symbol"],
        "input_mint":        inp["mint"],
        "output_mint":       out["mint"],
        "amount_per_buy":    amount_per_buy,
        "interval":          interval,
        "interval_minutes":  interval_minutes,
        "total_budget":      total_budget,
        "spent_so_far":      0.0,
        "max_executions":    max_executions,
        "executions_count":  0,
        "slippage_bps":      slippage_bps,
        "status":            "active",
        "user_wallet":       user_wallet.strip() if user_wallet else None,
        "created_at":        now.isoformat(),
        "next_execution_at": next_run.isoformat(),
        "executions":        [],
    }

    _insert_plan_db(plan)

    return {
        "status": "created",
        "plan": {k: plan[k] for k in (
            "id", "name", "input_token", "output_token", "input_mint", "output_mint",
            "amount_per_buy", "interval", "interval_minutes", "total_budget", "max_executions",
            "status", "next_execution_at", "user_wallet",
        )},
        "wallet":  get_wallet_pubkey(),
        "cluster": SOLANA_CLUSTER,
    }


def list_dca_plans(
    status: Optional[str] = None,
    user_wallet: Optional[str] = None,
    active_only: bool = False,
) -> dict:
    if not user_wallet or not str(user_wallet).strip():
        return {"error": "user_wallet is required.", "plans": [], "count": 0}

    plans = _load_plans(user_wallet.strip())
    if active_only and not status:
        plans = [p for p in plans if p.get("status") == "active"]
    elif status:
        plans = [p for p in plans if p.get("status") == status.lower()]
    summary = []
    for p in plans:
        summary.append({
            "id":               p["id"],
            "name":             p["name"],
            "pair":             f"{p['input_token']} -> {p['output_token']}",
            "input_mint":       p.get("input_mint"),
            "output_mint":      p.get("output_mint"),
            "amount_per_buy":   p["amount_per_buy"],
            "interval":         p["interval"],
            "status":           p["status"],
            "executions":       p["executions_count"],
            "max_executions":   p.get("max_executions"),
            "total_budget":     p.get("total_budget"),
            "slippage_bps":     p.get("slippage_bps", 100),
            "spent":            p["spent_so_far"],
            "next_execution_at": p.get("next_execution_at"),
        })
    return {
        "plans": summary,
        "count": len(summary),
        "user_wallet": user_wallet.strip(),
        "active_only": active_only,
    }


def get_dca_plan(plan_id: str, user_wallet: Optional[str] = None) -> dict:
    if user_wallet:
        owned = _assert_plan_owner(plan_id, user_wallet)
        if "error" in owned:
            return owned
        return owned
    plan = _find_plan(plan_id)
    if not plan:
        return {"error": f"Plan '{plan_id}' not found."}
    return plan


def update_dca_plan_status(plan_id: str, action: str, user_wallet: Optional[str] = None) -> dict:
    if user_wallet:
        owned = _assert_plan_owner(plan_id, user_wallet)
        if "error" in owned:
            return owned
    action = action.lower()
    valid  = {"pause": "paused", "resume": "active", "cancel": "cancelled"}
    if action not in valid:
        return {"error": f"Unknown action '{action}'. Use: pause, resume, cancel."}
    plan = _find_plan(plan_id)
    if not plan:
        return {"error": f"Plan '{plan_id}' not found."}
    return _update_plan(plan_id, {"status": valid[action]}) or {"error": "Update failed."}


def update_dca_plan(
    plan_id: str,
    user_wallet: str,
    *,
    amount_per_buy: Optional[float] = None,
    interval: Optional[str] = None,
    max_executions: Optional[int] = None,
    total_budget: Optional[float] = None,
    slippage_bps: Optional[int] = None,
) -> dict:
    owned = _assert_plan_owner(plan_id, user_wallet)
    if "error" in owned:
        return owned
    plan = owned

    if plan.get("status") not in ("active", "paused"):
        return {"error": f"Plan is {plan.get('status')} and cannot be edited."}

    updates: dict[str, Any] = {}
    inp = resolve_token(plan["input_token"])
    out = resolve_token(plan["output_token"])
    if "error" in inp:
        return inp
    if "error" in out:
        return out

    next_amount = float(amount_per_buy) if amount_per_buy is not None else float(plan["amount_per_buy"])
    next_interval_label = interval.strip() if interval else plan["interval"]
    next_interval_minutes = float(plan.get("interval_minutes") or 1440)
    if interval:
        try:
            next_interval_minutes = _parse_interval(interval)
        except ValueError as exc:
            return {"error": str(exc)}
    next_max_exec = (
        _coerce_nullable_int(max_executions) if max_executions is not None else plan.get("max_executions")
    )
    next_budget = (
        _coerce_nullable_float(total_budget) if total_budget is not None else plan.get("total_budget")
    )
    next_slippage = int(slippage_bps) if slippage_bps is not None else int(plan.get("slippage_bps") or 100)

    if next_max_exec is not None and next_max_exec < int(plan.get("executions_count") or 0):
        return {
            "error": (
                f"max_executions ({next_max_exec}) cannot be less than completed buys "
                f"({plan.get('executions_count')})."
            )
        }
    if next_budget is not None and next_budget + 1e-12 < float(plan.get("spent_so_far") or 0):
        return {
            "error": (
                f"total_budget ({next_budget}) cannot be less than already spent "
                f"({plan.get('spent_so_far')})."
            )
        }
    if next_slippage < 1 or next_slippage > 5000:
        return {"error": "slippage_bps must be between 1 and 5000."}

    feasibility = validate_dca_plan_feasibility(
        inp,
        out,
        next_amount,
        next_interval_minutes,
        next_budget,
        next_max_exec,
        user_wallet.strip(),
    )
    if feasibility:
        return feasibility

    if amount_per_buy is not None:
        updates["amount_per_buy"] = next_amount
    if interval is not None:
        updates["interval"] = next_interval_label
        updates["interval_minutes"] = next_interval_minutes
    if max_executions is not None:
        updates["max_executions"] = next_max_exec
    if total_budget is not None:
        updates["total_budget"] = next_budget
    if slippage_bps is not None:
        updates["slippage_bps"] = next_slippage

    if not updates:
        return {"error": "No fields to update."}

    updated = _update_plan(plan_id, updates)
    if not updated:
        return {"error": "Update failed."}
    return {"status": "updated", "plan": updated}


def execute_dca_now(plan_id: str, dry_run: bool = False, user_wallet: Optional[str] = None) -> dict:
    if user_wallet:
        owned = _assert_plan_owner(plan_id, user_wallet)
        if "error" in owned:
            return owned
    dry_run = _coerce_bool(dry_run)
    return _run_plan_execution(plan_id, dry_run=dry_run, force=True)


def get_dca_history(plan_id: str, user_wallet: Optional[str] = None) -> dict:
    if user_wallet:
        owned = _assert_plan_owner(plan_id, user_wallet)
        if "error" in owned:
            return owned
        plan = owned
    else:
        plan = _find_plan(plan_id)
        if not plan:
            return {"error": f"Plan '{plan_id}' not found."}
    return {
        "plan_id":          plan_id,
        "name":             plan["name"],
        "executions_count": plan["executions_count"],
        "spent_so_far":     plan["spent_so_far"],
        "executions":       plan.get("executions", []),
    }


def analyze_dca_timing(output_token: str, lookback_days: int = 7) -> dict:
    lookback_days = int(lookback_days)
    tok = resolve_token(output_token)
    if "error" in tok:
        return tok
    if not tok.get("coingecko_id"):
        return {
            "token": tok["symbol"],
            "mint": tok["mint"],
            "lookback_days": lookback_days,
            "note": (
                "Historical timing analysis is unavailable for custom tokens. "
                "You can still create a DCA plan; Jupiter will route the swap."
            ),
        }
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

        current      = prices[-1]
        low          = min(prices)
        high         = max(prices)
        avg          = sum(prices) / len(prices)
        change_pct   = ((current / prices[0]) - 1) * 100
        drawdown     = ((current / high) - 1) * 100 if high else 0
        dist_from_low = ((current / low) - 1) * 100 if low else 0

        if change_pct > 5:
            trend = "uptrend"
        elif change_pct < -5:
            trend = "downtrend"
        else:
            trend = "sideways"

        return {
            "token":                 tok["symbol"],
            "lookback_days":         lookback_days,
            "current_price_usd":     round(current, 6),
            "period_low_usd":        round(low, 6),
            "period_high_usd":       round(high, 6),
            "period_avg_usd":        round(avg, 6),
            "period_change_pct":     round(change_pct, 2),
            "drawdown_from_high_pct": round(drawdown, 2),
            "above_period_low_pct":  round(dist_from_low, 2),
            "trend":                 trend,
            "dca_note":              "Regular DCA smooths volatility - frequency depends on your horizon, not short-term trend.",
        }
    except Exception as e:
        return {"error": str(e)}


def _run_plan_execution(plan_id: str, dry_run: bool = False, force: bool = False) -> dict:
    from deposit_ledger import (
        check_user_can_spend_dca,
        dca_execution_total_cost,
        dca_platform_fee,
        record_dca_platform_fee,
    )

    plan = _find_plan(plan_id)
    if not plan:
        return {"error": f"Plan '{plan_id}' not found."}
    if plan["status"] != "active" and not force:
        return {"error": f"Plan is {plan['status']}, not active."}

    amount           = float(plan["amount_per_buy"])
    fee              = dca_platform_fee(amount)
    total_cost       = dca_execution_total_cost(amount)
    spent            = float(plan.get("spent_so_far", 0))
    budget           = _coerce_nullable_float(plan.get("total_budget"))
    max_exec         = _coerce_nullable_int(plan.get("max_executions"))
    executions_count = int(plan.get("executions_count", 0))
    interval_minutes = float(plan.get("interval_minutes", 1440))

    if budget is not None and spent + total_cost > budget + 1e-12:
        _update_plan(plan_id, {"status": "completed"})
        return {"error": "Budget exhausted. Plan marked completed.", "plan_id": plan_id}

    if max_exec is not None and executions_count >= max_exec:
        _update_plan(plan_id, {"status": "completed"})
        return {"error": "Max executions reached. Plan marked completed.", "plan_id": plan_id}

    plan_user = (plan.get("user_wallet") or "").strip()
    if not dry_run:
        spend_check = check_user_can_spend_dca(plan_user, plan["input_token"], amount)
        if "error" in spend_check:
            spend_check["plan_id"] = plan_id
            return spend_check
    elif plan_user:
        spend_check = check_user_can_spend_dca(plan_user, plan["input_token"], amount)
        if "error" in spend_check:
            spend_check["plan_id"] = plan_id
            return spend_check

    result = execute_swap_buy(
        plan["input_token"],
        plan["output_token"],
        amount,
        int(plan.get("slippage_bps", 100)),
        dry_run=dry_run,
        user_wallet=plan_user or None,
    )

    now         = datetime.now(timezone.utc)
    exec_record = {
        "at":            now.isoformat(),
        "amount":        amount,
        "platform_fee":  fee,
        "total_cost":    total_cost,
        "input_token":   plan["input_token"],
        "output_token":  plan["output_token"],
        "result":        {k: v for k, v in result.items() if k not in ("build_data", "quote")},
        "dry_run":       dry_run,
    }

    if dry_run:
        preview = dict(result) if isinstance(result, dict) else {"preview": result}
        preview["platform_fee"] = fee
        preview["platform_fee_token"] = plan["input_token"]
        preview["total_cost"] = total_cost
        preview["fee_rate"] = 0.005
        return {"plan_id": plan_id, "dry_run": True, "preview": preview}

    success = result.get("status") == "success"
    if success:
        if plan_user and fee > 0:
            fee_record = record_dca_platform_fee(
                plan_user,
                plan["input_token"],
                amount,
                reference_id=(result.get("signature") or plan_id)[:128],
                signature=result.get("signature"),
                plan_id=plan_id,
            )
            if "error" in fee_record:
                exec_record["fee_error"] = fee_record["error"]
            else:
                exec_record["fee_recorded"] = fee_record.get("fee", fee)

        result["platform_fee"] = fee
        result["platform_fee_token"] = plan["input_token"]
        result["total_cost"] = total_cost
        result["fee_rate"] = 0.005

        next_run   = now + timedelta(minutes=interval_minutes)
        executions = plan.get("executions", []) + [exec_record]
        _update_plan(plan_id, {
            "executions_count":  executions_count + 1,
            "spent_so_far":      round(spent + total_cost, 8),
            "next_execution_at": next_run.isoformat(),
            "executions":        executions[-50:],
        })
        result["plan_id"]            = plan_id
        result["next_execution_at"]  = next_run.isoformat()
        return result

    exec_record["result"] = result
    executions = plan.get("executions", []) + [exec_record]
    _update_plan(plan_id, {"executions": executions[-50:]})
    return {"plan_id": plan_id, "execution_failed": True, **result}


# ─── Scheduler ────────────────────────────────────────────────────────────────

def _scheduler_loop(poll_seconds: int = SCHEDULER_POLL_SECONDS) -> None:
    global _scheduler_running
    while _scheduler_running:
        try:
            for plan in claim_due_dca_plans():
                owner = (plan.get("user_wallet") or "unknown")[:8]
                mode = plan.get("wallet_mode") or "pooled"
                print(f"\n  ⏰ DCA due: {plan['name']} ({plan['id']}) · user {owner}… [{mode}]")
                if mode == "multiwallet":
                    # Deferred import: dca_multiwallet imports from this module,
                    # so this must not be a top-level import (circular).
                    import dca_multiwallet
                    result = dca_multiwallet.execute_plan_now(plan["id"])
                else:
                    result = _run_plan_execution(plan["id"])
                if result.get("status") == "success":
                    print(f"  ✅ Tx: {result.get('signature', 'ok')}")
                else:
                    print(f"  ⚠️  {result.get('error', result)}")
        except Exception as e:
            print(f"  ⚠️  Scheduler error: {e}")
        time.sleep(poll_seconds)


def start_scheduler() -> bool:
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


def _metrics_loop(refresh_seconds: int = METRICS_REFRESH_SECONDS) -> None:
    global _metrics_running
    from db import compute_platform_metrics, upsert_platform_metrics

    while _metrics_running:
        try:
            metrics = compute_platform_metrics()
            upsert_platform_metrics(metrics)
            print(f"  📊 Platform metrics refreshed ({metrics.get('executions_24h', 0)} swaps · 24h)")
        except Exception as exc:
            print(f"  ⚠️  Metrics refresh error: {exc}")
        slept = 0
        while slept < refresh_seconds and _metrics_running:
            time.sleep(min(60, refresh_seconds - slept))
            slept += min(60, refresh_seconds - slept)


def start_metrics_scheduler() -> bool:
    global _metrics_running
    with _metrics_lock:
        if _metrics_running:
            return False
        _metrics_running = True
        from db import compute_platform_metrics, upsert_platform_metrics

        try:
            upsert_platform_metrics(compute_platform_metrics())
        except Exception as exc:
            print(f"  ⚠️  Initial metrics refresh failed: {exc}")
        t = threading.Thread(target=_metrics_loop, daemon=True, name="dca-metrics")
        t.start()
        return True


def stop_metrics_scheduler() -> None:
    global _metrics_running
    _metrics_running = False


# ─── User deposit ledger (AI Agent wallet) ───────────────────────────────────

def get_agent_wallet() -> dict:
    from deposit_ledger import get_agent_wallet_info
    return get_agent_wallet_info()


def get_user_deposit_balance(user_wallet: str) -> dict:
    from deposit_ledger import get_user_balances
    return get_user_balances(user_wallet)


def verify_user_deposit(signature: str, user_wallet: str) -> dict:
    from deposit_ledger import verify_and_record_deposit
    return verify_and_record_deposit(signature, user_wallet)


def list_user_deposit_history(user_wallet: str, limit: int = 10) -> dict:
    from deposit_ledger import list_user_deposits
    return list_user_deposits(user_wallet, int(limit))


def withdraw_user_tokens(user_wallet: str, token: str, amount: float) -> dict:
    from deposit_ledger import withdraw_user_tokens as _withdraw
    return _withdraw(user_wallet, token, amount)


# ─── Ollama tools ─────────────────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_agent_wallet",
            "description": "Return the AI Agent custodial wallet address where users deposit tokens for DCA.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_deposit_balance",
            "description": "Show a user's verified deposit balance available for DCA (deposited, reserved, spent, available per token).",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_wallet": {"type": "string", "description": "User's Solana wallet public key"},
                },
                "required": ["user_wallet"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verify_user_deposit",
            "description": "Verify an on-chain deposit tx into the AI Agent wallet and record credited balance for a user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "signature": {"type": "string", "description": "Solana transaction signature / hash"},
                    "user_wallet": {"type": "string", "description": "Depositor wallet public key"},
                },
                "required": ["signature", "user_wallet"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_user_deposit_history",
            "description": "List verified deposit records for a user wallet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_wallet": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["user_wallet"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "withdraw_user_tokens",
            "description": (
                "Withdraw unused deposited tokens or DCA-acquired output tokens back to the user's wallet. "
                "REQUIRES explicit user confirmation before calling. "
                "Cannot withdraw amounts reserved for active DCA plans."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_wallet": {"type": "string", "description": "User's Solana wallet public key"},
                    "token": {"type": "string", "description": "Token symbol or mint to withdraw"},
                    "amount": {"type": "number", "description": "Amount to withdraw"},
                },
                "required": ["user_wallet", "token", "amount"],
            },
        },
    },
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
            "description": "Get current USD price for any SPL token by symbol or mint address.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Token symbol or mint address"},
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
                    "input_token":  {"type": "string"},
                    "output_token": {"type": "string"},
                    "amount":       {"type": "number", "description": "Amount of input token"},
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
            "description": (
                "Create a recurring DCA plan. REQUIRES explicit user confirmation in their latest "
                "message before calling - summarize the plan and wait for yes/confirm first."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name":             {"type": "string", "description": "Optional label; auto-generated if omitted"},
                    "user_wallet":      {"type": "string", "description": "User's wallet - must have deposited sufficient input_token to the AI Agent wallet"},
                    "input_token":      {"type": "string", "description": "Token to spend - symbol or mint address"},
                    "output_token":     {"type": "string", "description": "Token to accumulate - symbol or mint address"},
                    "amount_per_buy":   {"type": "number"},
                    "interval":         {"type": "string", "description": "Any duration e.g. '11 seconds', '12 minutes', 'every 4 hours', daily"},
                    "total_budget":     {"type": "number",  "description": "Optional max total input to spend"},
                    "max_executions":   {"type": "integer", "description": "Optional max number of buys"},
                    "slippage_bps":     {"type": "integer"},
                    "start_immediately": {"type": "boolean"},
                },
                "required": ["user_wallet", "input_token", "output_token", "amount_per_buy", "interval"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dca_plans",
            "description": (
                "List DCA plans for the authenticated user. ALWAYS call this tool when the user "
                "asks to list/show their plans - never guess from memory."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Filter: active, paused, cancelled, completed",
                    },
                    "active_only": {
                        "type": "boolean",
                        "description": "If true, return only active plans (use when user asks for active plans)",
                    },
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
            "description": (
                "Pause, resume, or cancel a DCA plan. REQUIRES explicit user confirmation "
                "before calling."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_id": {"type": "string"},
                    "action":  {"type": "string", "enum": ["pause", "resume", "cancel"]},
                },
                "required": ["plan_id", "action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_dca_now",
            "description": (
                "Force-run the next buy for a plan immediately. Live runs REQUIRE user "
                "confirmation; dry_run previews do not."
            ),
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
            "description": (
                "Execute a one-off swap buy (not tied to a plan). Live swaps REQUIRE user "
                "confirmation; dry_run previews do not."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "user_wallet":  {"type": "string", "description": "User's wallet - spend is capped by their verified deposits"},
                    "input_token":  {"type": "string"},
                    "output_token": {"type": "string"},
                    "amount":       {"type": "number"},
                    "slippage_bps": {"type": "integer"},
                    "dry_run":      {"type": "boolean"},
                },
                "required": ["user_wallet", "input_token", "output_token", "amount"],
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
    "get_agent_wallet":         get_agent_wallet,
    "get_user_deposit_balance": get_user_deposit_balance,
    "verify_user_deposit":      verify_user_deposit,
    "list_user_deposit_history": list_user_deposit_history,
    "withdraw_user_tokens":     withdraw_user_tokens,
    "get_wallet_status":      get_wallet_status,
    "get_token_price":        get_token_price,
    "get_jupiter_quote":      get_jupiter_quote,
    "create_dca_plan":        create_dca_plan,
    "list_dca_plans":         list_dca_plans,
    "get_dca_plan":           get_dca_plan,
    "update_dca_plan_status": update_dca_plan_status,
    "execute_dca_now":        execute_dca_now,
    "execute_swap_buy":       execute_swap_buy,
    "get_dca_history":        get_dca_history,
    "analyze_dca_timing":     analyze_dca_timing,
}

SYSTEM_PROMPT = """You are a Solana DCA (Dollar-Cost Averaging) agent. You help users set up recurring token buys on Solana.

## AI Agent wallet (custodial deposits)
- Users deposit tokens to the **AI Agent wallet** before running DCA.
- Always call get_agent_wallet to show the deposit address when asked.
- After a user deposits, they (or the frontend) provide a tx signature - call verify_user_deposit(signature, user_wallet) to record on-chain proof.
- Before create_dca_plan, call get_user_deposit_balance(user_wallet) and ensure available balance covers total_budget (or amount_per_buy × max_executions **including the 0.5% platform fee per buy**).
- **Platform fee**: each **successful scheduled DCA buy** charges **0.5% of the swap amount in the input token** (e.g. SOL→USDC fee is in SOL; TokenA→TokenB fee is in TokenA). One-off execute_swap_buy previews are fee-free; plan executions are not.
- create_dca_plan **requires user_wallet** - never create a plan without it.
- Each user's DCA spend is limited to their verified deposit balance for that input token.
- The agent wallet is shared on-chain, but the ledger tracks deposits **per user wallet**. User A cannot spend User B's deposits.
- execute_swap_buy requires user_wallet; swaps and plan executions are rejected if deposited − already spent is less than the requested amount.
- withdraw_user_tokens sends unused deposits and DCA-acquired tokens back to the user's wallet (not amounts reserved for active plans).
- Users must authenticate with a wallet signature before chat, deposits, or plan actions. Never access another user's plans or balances.
- list_dca_plans only returns the authenticated user's plans.
- When the user asks to list/show DCA plans, **always call list_dca_plans** and report exactly what it returns. Never invent plan counts or IDs.
- Unless the user explicitly asks for **active** plans only, call list_dca_plans **without** active_only (show active, paused, completed, cancelled). Short test plans (e.g. 3 buys) finish quickly and become **completed** - do not report "no plans" when completed plans exist.
- When the user gives a token **mint address**, pass that exact mint as output_token to create_dca_plan. Do not substitute a different token or symbol.
- Multiple plans can share a symbol (e.g. two meme coins both named CPX) - always distinguish plans by **plan id** and **output_mint** from list_dca_plans.

## Capabilities
- Create DCA plans: spend input_token (USDC/SOL) to buy output_token (JUP/BONK/etc.) on a schedule
- List, pause, resume, cancel plans
- Execute buys immediately or on schedule (background scheduler runs automatically)
- Preview Jupiter quotes on mainnet
- Analyze price trends for DCA timing discussions

## Intervals
Use any interval the user requests: seconds, minutes, hours, days (e.g. "11 seconds", "12 min", "every 4 hours"). Presets like daily/hourly still work.

## Network
- **Mainnet**: real Jupiter v2 token swaps (requires DCA_WALLET_PRIVATE_KEY + mainnet RPC)
- **Devnet** (default): scheduled SOL self-transfers as tx proof; Jupiter unavailable

## Confirmation required (mandatory - enforced by the server)
Mutating actions **cannot run** until the user explicitly confirms in their **latest message** (e.g. "yes", "confirm", "proceed", "go ahead").

**Always ask first** with a clear summary:
"Please confirm before I proceed: [exact action details]. Reply **yes** to proceed or **no** to cancel."

Applies to:
- **create_dca_plan** - new DCA schedules
- **update_dca_plan_status** - pause, resume, or cancel a plan
- **execute_dca_now** - live buys (dry_run previews do not need confirmation)
- **execute_swap_buy** - one-off live swaps (dry_run previews do not need confirmation)
- **withdraw_user_tokens** - sending tokens back to the user's wallet

Workflow:
1. User requests an action → summarize every parameter (tokens/mints, amounts, interval, plan id, max executions, budget).
2. Ask: "Please confirm before I proceed."
3. Wait for the user's next message. Only call the mutating tool after they confirm.
4. If the tool returns `confirmation_required`, show that message to the user and wait - do not retry the tool in the same turn.
5. If they say no/cancel, acknowledge and do not execute.

Read-only tools (list plans, quotes, balances, history, dry runs) never need confirmation.

## Workflow for new DCA
1. get_wallet_status - confirm wallet and cluster
2. get_token_price / analyze_dca_timing - optional context
3. get_jupiter_quote - preview if mainnet
4. Summarize the plan and ask: "Please confirm before I proceed: …"
5. create_dca_plan - **only after** the user confirms in a follow-up message
   (name is optional; omit it unless the user gives a plan title)
   Use EXACTLY the tokens the user specified - do not substitute or infer different tokens.

## Safety
- Always warn: DCA does not guarantee profit; crypto is volatile
- For live execution, confirm amount, interval, and budget
- Use dry_run=true when user wants to preview without sending txs
- NEVER change the user's requested interval to a different one (e.g. do not change "30 seconds" to "every_15_minutes")
- End with: "Not financial advice. DYOR."

Tokens: accept any SPL token by symbol or mint address (e.g. JUP or a full mint).
Common tokens: SOL, USDC, USDT, JUP, BONK, WIF, RAY, ORCA, PYTH, JTO, RENDER
"""

from shared_governance import GOVERNANCE_PROMPT

SYSTEM_PROMPT = SYSTEM_PROMPT + GOVERNANCE_PROMPT


def call_openrouter(messages: list) -> dict[str, Any]:
    """Call configured LLM (hosted Ollama or OpenRouter fallback) with tool support."""
    return call_llm(messages, model=MODEL, tools=TOOLS, temperature=0.2)


CONFIRMATION_REQUIRED_TOOLS = frozenset({
    "create_dca_plan",
    "update_dca_plan_status",
    "execute_dca_now",
    "execute_swap_buy",
    "withdraw_user_tokens",
})

_CONFIRMATION_LOCK = threading.Lock()
_pending_confirmations: dict[str, dict[str, Any]] = {}

_CONFIRM_PHRASES = (
    r"\byes\b",
    r"\byep\b",
    r"\byeah\b",
    r"\bconfirm\b",
    r"\bproceed\b",
    r"\bgo ahead\b",
    r"\bdo it\b",
    r"\bapproved?\b",
    r"\bsure\b",
    r"\bok(?:ay)?\b",
    r"\bi confirm\b",
    r"\bplease proceed\b",
    r"\bthat(?:'s| is) correct\b",
    r"\blooks good\b",
)

_DECLINE_PHRASES = (
    r"\bno\b",
    r"\bcancel\b",
    r"\bstop\b",
    r"\babort\b",
    r"\bdon't\b",
    r"\bdont\b",
    r"\bnevermind\b",
    r"\bnever mind\b",
)


def _confirmation_key(user_wallet: Optional[str], session_id: Optional[str]) -> str:
    wallet = (user_wallet or "").strip() or "anonymous"
    session = (session_id or "").strip() or "default"
    return f"{wallet}:{session}"


def _canonicalize_confirm_value(key: str, value: Any) -> Any:
    if value is None:
        return None
    if key in {"start_immediately", "dry_run", "active_only"}:
        return _coerce_bool(value)
    if key in {"max_executions", "slippage_bps"}:
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    if key in {"amount_per_buy", "total_budget", "amount"} or isinstance(value, float):
        try:
            return round(float(value), 12)
        except (TypeError, ValueError):
            return value
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if key in {"input_token", "output_token", "token", "interval", "action", "plan_id", "name"}:
            if _looks_like_mint(stripped):
                return stripped
            return stripped.upper()
        try:
            return round(float(stripped), 12)
        except ValueError:
            return stripped
    return value


def _normalize_confirmation_args(tool_name: str, args: dict) -> dict:
    normalized: dict[str, Any] = {}
    for key, value in (args or {}).items():
        if key == "user_wallet":
            continue
        if tool_name in {"execute_dca_now", "execute_swap_buy"} and key == "dry_run":
            continue
        normalized[key] = _canonicalize_confirm_value(key, value)
    return normalized


def _action_fingerprint(tool_name: str, args: dict) -> str:
    payload = json.dumps(
        {"tool": tool_name, "args": _normalize_confirmation_args(tool_name, args)},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _user_confirmed(user_input: Optional[str]) -> bool:
    text = (user_input or "").strip().lower()
    if not text:
        return False
    return any(re.search(pattern, text) for pattern in _CONFIRM_PHRASES)


def _user_declined(user_input: Optional[str]) -> bool:
    text = (user_input or "").strip().lower()
    if not text:
        return False
    return any(re.search(pattern, text) for pattern in _DECLINE_PHRASES)


def _tool_requires_confirmation(tool_name: str, args: dict) -> bool:
    if tool_name not in CONFIRMATION_REQUIRED_TOOLS:
        return False
    if tool_name in {"execute_dca_now", "execute_swap_buy"} and _coerce_bool(args.get("dry_run")):
        return False
    return True


def _resolve_token_brief(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {"symbol": "?", "mint": None}
    text = str(raw).strip()
    if not text:
        return {"symbol": "?", "mint": None}
    resolved = resolve_token(text)
    if "error" in resolved:
        if _looks_like_mint(text):
            return {"symbol": text[:6] + "…", "mint": text}
        return {"symbol": text.upper(), "mint": None}
    return {"symbol": resolved["symbol"], "mint": resolved["mint"]}


def _token_with_mint(raw: Any) -> str:
    info = _resolve_token_brief(raw)
    symbol = info.get("symbol") or "?"
    mint = info.get("mint")
    if mint:
        return f"**{symbol}** (`{mint}`)"
    return f"**{symbol}**"


def _pending_action_details(tool_name: str, args: dict) -> dict[str, Any]:
    if tool_name == "create_dca_plan":
        from deposit_ledger import dca_execution_total_cost, dca_platform_fee

        inp = _resolve_token_brief(args.get("input_token"))
        out = _resolve_token_brief(args.get("output_token"))
        amount = float(args.get("amount_per_buy") or 0)
        fee = dca_platform_fee(amount) if amount > 0 else 0
        return {
            "action": tool_name,
            "input_token": inp.get("symbol"),
            "input_mint": inp.get("mint"),
            "output_token": out.get("symbol"),
            "output_mint": out.get("mint"),
            "amount_per_buy": args.get("amount_per_buy"),
            "platform_fee_per_buy": fee,
            "platform_fee_token": inp.get("symbol"),
            "total_cost_per_buy": dca_execution_total_cost(amount) if amount > 0 else None,
            "fee_rate": 0.005,
            "interval": args.get("interval"),
            "max_executions": args.get("max_executions"),
            "total_budget": args.get("total_budget"),
            "start_immediately": args.get("start_immediately"),
        }
    if tool_name == "execute_swap_buy":
        inp = _resolve_token_brief(args.get("input_token"))
        out = _resolve_token_brief(args.get("output_token"))
        return {
            "action": tool_name,
            "input_token": inp.get("symbol"),
            "input_mint": inp.get("mint"),
            "output_token": out.get("symbol"),
            "output_mint": out.get("mint"),
            "amount": args.get("amount"),
        }
    if tool_name == "withdraw_user_tokens":
        tok = _resolve_token_brief(args.get("token"))
        return {
            "action": tool_name,
            "token": tok.get("symbol"),
            "mint": tok.get("mint"),
            "amount": args.get("amount"),
        }
    if tool_name == "update_dca_plan_status":
        return {
            "action": tool_name,
            "plan_id": args.get("plan_id"),
            "status_action": args.get("action"),
        }
    if tool_name == "execute_dca_now":
        return {"action": tool_name, "plan_id": args.get("plan_id")}
    return {"action": tool_name, "args": args}


def _summarize_pending_action(tool_name: str, args: dict) -> str:
    if tool_name == "create_dca_plan":
        parts = [
            f"buy {_token_with_mint(args.get('input_token'))} "
            f"amount **{args.get('amount_per_buy')}**",
            f"→ {_token_with_mint(args.get('output_token'))}",
            f"every **{args.get('interval')}**",
        ]
        if args.get("max_executions") is not None:
            parts.append(f"max **{args.get('max_executions')}** buys")
        if args.get("total_budget") is not None:
            parts.append(f"budget **{args.get('total_budget')} {args.get('input_token')}**")
        if args.get("start_immediately"):
            parts.append("start immediately")
        parts.append("**0.5% platform fee per successful buy (charged in input token)**")
        return "Create DCA plan: " + ", ".join(parts)

    if tool_name == "update_dca_plan_status":
        action = str(args.get("action", "update")).lower()
        return f"**{action.title()}** DCA plan `{args.get('plan_id')}`"

    if tool_name == "execute_dca_now":
        return (
            f"Execute next **live buy** for plan `{args.get('plan_id')}` "
            f"(includes **0.5% platform fee** in the plan input token)"
        )

    if tool_name == "execute_swap_buy":
        return (
            f"Execute **live swap**: **{args.get('amount')}** "
            f"{_token_with_mint(args.get('input_token'))} "
            f"→ {_token_with_mint(args.get('output_token'))}"
        )

    if tool_name == "withdraw_user_tokens":
        return (
            f"Withdraw **{args.get('amount')}** "
            f"{_token_with_mint(args.get('token'))} to your wallet"
        )

    return f"{tool_name}({args})"


def _merge_tool_args(stored: dict, current: dict) -> dict:
    """Prefer stored pending args; fill gaps from the current tool call."""
    merged = dict(stored or {})
    for key, value in (current or {}).items():
        if key == "user_wallet":
            continue
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if key not in merged or merged[key] is None:
            merged[key] = value
    return merged


def _json_compact(value: Any) -> str:
    """Compact JSON safe for Ollama tool-call argument strings."""

    def _default(obj: Any) -> Any:
        if isinstance(obj, float):
            text = format(obj, ".12f").rstrip("0").rstrip(".")
            return text if text else "0"
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

    return json.dumps(value, separators=(",", ":"), default=_default)


def _format_pending_execution_reply(tool_name: str, result: str) -> str:
    try:
        data = json.loads(result)
    except json.JSONDecodeError:
        return result

    if data.get("status") == "confirmation_required":
        return str(data.get("message") or result)
    if data.get("status") == "cancelled":
        return str(data.get("message") or "Action cancelled.")
    if "error" in data:
        return f"Could not complete the action: {data['error']}"

    if tool_name == "list_dca_plans":
        return _format_dca_plans_reply(data)

    if tool_name == "get_user_deposit_balance" and isinstance(data.get("balances"), list):
        lines = ["**Your deposit balances**"]
        for row in data["balances"]:
            token = row.get("token", "?")
            available = row.get("available", 0)
            deposited = row.get("deposited", 0)
            lines.append(f"- **{token}**: {available} available ({deposited} deposited)")
        if not data["balances"]:
            lines.append("- No verified deposits yet.")
        lines.append("\nNot financial advice. DYOR.")
        return "\n".join(lines)

    if tool_name == "create_dca_plan" and data.get("status") == "created":
        plan = data.get("plan") or {}
        parts = [
            f"DCA plan **{plan.get('name', 'created')}** is live (ID `{plan.get('id')}`).",
            f"Buying **{plan.get('amount_per_buy')} {plan.get('input_token')}** "
            f"→ **{plan.get('output_token')}** every **{plan.get('interval')}**.",
        ]
        if plan.get("max_executions") is not None:
            parts.append(f"Max buys: **{plan.get('max_executions')}**.")
        if plan.get("total_budget") is not None:
            parts.append(f"Budget: **{plan.get('total_budget')} {plan.get('input_token')}**.")
        parts.append("Each successful buy includes a **0.5% platform fee** in the input token.")
        parts.append("\nNot financial advice. DYOR.")
        return " ".join(parts)

    if tool_name == "update_dca_plan_status" and "status" in data:
        return f"Plan updated. New status: **{data['status']}**.\n\nNot financial advice. DYOR."

    if tool_name in {"execute_dca_now", "execute_swap_buy"}:
        msg = data.get("message") or data.get("status") or "Swap executed."
        if data.get("platform_fee"):
            msg += (
                f" Platform fee: **{data.get('platform_fee')} "
                f"{data.get('platform_fee_token', '')}**."
            )
        return f"{msg}\n\nNot financial advice. DYOR."

    if tool_name == "withdraw_user_tokens":
        sig = data.get("signature") or data.get("tx_signature")
        if sig:
            return f"Withdrawal sent. Signature: `{sig}`\n\nNot financial advice. DYOR."
        return f"{data.get('message', 'Withdrawal submitted.')}\n\nNot financial advice. DYOR."

    return result


def _try_execute_pending_confirmation(
    user_wallet: Optional[str],
    session_id: Optional[str],
    user_input: Optional[str],
    conversation_history: Optional[list] = None,
) -> Optional[tuple[str, dict, str, str]]:
    """When the user confirms, run the stored pending action immediately."""
    if not user_wallet or not _user_confirmed(user_input) or _user_declined(user_input):
        return None

    key = _confirmation_key(user_wallet, session_id)
    with _CONFIRMATION_LOCK:
        pending = _pending_confirmations.pop(key, None)
    if not pending and conversation_history:
        recovered = _recover_create_dca_from_history(conversation_history)
        if recovered:
            pending = {
                "tool": "create_dca_plan",
                "args": {**recovered, "user_wallet": user_wallet.strip()},
            }
    if not pending:
        return None

    tool_name = pending["tool"]
    args = dict(pending.get("args") or {})
    result = execute_tool(
        tool_name,
        args,
        user_wallet=user_wallet,
        user_input=user_input,
        session_id=session_id,
        skip_confirmation=True,
    )
    reply = _format_pending_execution_reply(tool_name, result)
    return tool_name, args, result, reply


def _check_action_confirmation(
    tool_name: str,
    args: dict,
    user_input: Optional[str],
    user_wallet: Optional[str],
    session_id: Optional[str],
    skip_confirmation: bool = False,
) -> tuple[Optional[str], dict]:
    if skip_confirmation or not _tool_requires_confirmation(tool_name, args):
        return None, args

    key = _confirmation_key(user_wallet, session_id)
    summary = _summarize_pending_action(tool_name, args)

    if _user_declined(user_input):
        with _CONFIRMATION_LOCK:
            pending = _pending_confirmations.pop(key, None)
        if pending:
            return _json_compact(
                {
                    "status": "cancelled",
                    "message": "Action cancelled. No changes were made.",
                    "cancelled_action": pending.get("summary") or summary,
                }
            ), args
        # No pending action - treat "no" as not confirmed and require confirmation.

    if _user_confirmed(user_input):
        with _CONFIRMATION_LOCK:
            pending = _pending_confirmations.pop(key, None)
        if pending and pending.get("tool") == tool_name:
            args = _merge_tool_args(pending.get("args") or {}, args)
        return None, args

    with _CONFIRMATION_LOCK:
        _pending_confirmations[key] = {
            "tool": tool_name,
            "args": args,
            "summary": summary,
            "details": _pending_action_details(tool_name, args),
        }

    details = _pending_action_details(tool_name, args)
    return _json_compact(
        {
            "status": "confirmation_required",
            "message": (
                f"Please confirm before I proceed: {summary}. "
                "Reply **yes** or **confirm** to proceed, or **no** to cancel."
            ),
            "pending_action": summary,
            "confirmation_details": details,
            "tool": tool_name,
        }
    ), args


def execute_tool(
    tool_name: str,
    tool_args: dict,
    user_wallet: Optional[str] = None,
    user_input: Optional[str] = None,
    session_id: Optional[str] = None,
    skip_confirmation: bool = False,
) -> str:
    func = TOOL_MAP.get(tool_name)
    if not func:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    try:
        args = _normalize_tool_args(func, tool_args or {})
        auth_wallet = user_wallet.strip() if user_wallet else None

        wallet_scoped_tools = {
            "create_dca_plan",
            "execute_swap_buy",
            "get_user_deposit_balance",
            "list_user_deposit_history",
            "verify_user_deposit",
            "withdraw_user_tokens",
            "list_dca_plans",
            "get_dca_plan",
            "update_dca_plan_status",
            "execute_dca_now",
            "get_dca_history",
        }

        if tool_name in wallet_scoped_tools:
            if not auth_wallet:
                return json.dumps({"error": "Wallet authentication required for this action."})
            if tool_name in {"create_dca_plan", "execute_swap_buy"}:
                claimed = (args.get("user_wallet") or "").strip()
                if claimed and claimed != auth_wallet:
                    return json.dumps({"error": "Forbidden: user_wallet does not match authenticated wallet."})
                args["user_wallet"] = auth_wallet
            elif tool_name in {
                "get_user_deposit_balance",
                "list_user_deposit_history",
                "verify_user_deposit",
                "withdraw_user_tokens",
            }:
                claimed = (args.get("user_wallet") or "").strip()
                if claimed and claimed != auth_wallet:
                    return json.dumps({"error": "Forbidden: user_wallet does not match authenticated wallet."})
                args["user_wallet"] = auth_wallet
            elif tool_name == "list_dca_plans":
                args["user_wallet"] = auth_wallet
            elif tool_name in {"get_dca_plan", "update_dca_plan_status", "execute_dca_now", "get_dca_history"}:
                args["user_wallet"] = auth_wallet

        blocked, args = _check_action_confirmation(
            tool_name,
            args,
            user_input=user_input,
            user_wallet=auth_wallet,
            session_id=session_id,
            skip_confirmation=skip_confirmation,
        )
        if blocked:
            return blocked

        return json.dumps(func(**args), separators=(",", ":"), default=lambda o: format(o, ".12f").rstrip("0").rstrip(".") if isinstance(o, float) else str(o))
    except TypeError as e:
        return json.dumps({"error": str(e), "received_args": tool_args})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _parse_create_dca_request(user_input: str) -> Optional[dict[str, Any]]:
    """Parse natural-language DCA / swap schedules without relying on LLM tool calls."""
    text = (user_input or "").strip()
    lower = text.lower()
    if not text or _user_confirmed(text) or _user_declined(text):
        return None
    if not re.search(r"\b(swap|dca|buy|every|recurring|schedule|trx|transaction)\b", lower):
        return None

    mint_match = re.search(r"[1-9A-HJ-NP-Za-km-z]{32,44}", text)
    if mint_match:
        output_token = mint_match.group(0)
    else:
        # No raw mint address in the message -- by far the more common case is
        # a ticker symbol ("...into BITAGENTS every minute"), which the UI's own
        # deposit form explicitly supports ("ANY SPL TOKEN - SYMBOL OR MINT
        # ADDRESS"). Missing this meant every symbol-phrased request silently
        # fell through to the free-text LLM loop instead of this deterministic,
        # guaranteed-to-actually-execute path -- confirmed live: the model
        # described a plan as created and running without ever calling the
        # tool that would make that real (no DB row, no on-chain transaction).
        symbol_match = re.search(r"\b(?:into|of)\s+([a-zA-Z][a-zA-Z0-9]{1,14})\b", text)
        if not symbol_match:
            return None
        candidate = symbol_match.group(1)
        if candidate.upper() == "SOL":
            return None
        resolved = resolve_token(candidate)
        if "error" in resolved:
            return None
        output_token = candidate

    amount_match = re.search(r"\b(\d+(?:\.\d+)?)\s*sol\b", lower)
    if not amount_match:
        amount_match = re.search(r"\b(?:swap|buy|spend)\s+(\d+(?:\.\d+)?)\b", lower)
    if not amount_match:
        return None
    amount_per_buy = float(amount_match.group(1))

    interval_match = re.search(
        r"every\s+(\d+)?\s*(second|seconds|sec|secs|s|minute|minutes|min|mins|m|hour|hours|h|day|days|d)\b",
        lower,
    )
    if not interval_match:
        return None
    count, unit = interval_match.groups()
    count = count or "1"  # "every minute" means "every 1 minute", not a missing count
    unit = unit.rstrip(".")
    unit_aliases = {
        "sec": "seconds",
        "secs": "seconds",
        "s": "seconds",
        "min": "minutes",
        "mins": "minutes",
        "m": "minutes",
        "h": "hours",
        "d": "days",
    }
    interval = f"{count} {unit_aliases.get(unit, unit)}"

    max_match = re.search(
        r"(?:for\s+)?(?:next\s+)?(\d+)\s*(?:trx|transactions?|buys?|times?|executions?)\b",
        lower,
    )
    if not max_match:
        max_match = re.search(r"\b(\d+)\s*(?:trx|transactions?|buys?)\b", lower)
    max_executions = int(max_match.group(1)) if max_match else None

    return {
        "input_token": "SOL",
        "output_token": output_token,
        "amount_per_buy": amount_per_buy,
        "interval": interval,
        "max_executions": max_executions,
    }


def _recover_create_dca_from_history(conversation_history: list) -> Optional[dict[str, Any]]:
    for msg in reversed(conversation_history or []):
        if msg.get("role") != "user":
            continue
        content = str(msg.get("content") or "")
        if content.startswith("[Connected user wallet:"):
            content = content.split("\n", 1)[-1]
        if content.startswith("[Instruction:"):
            continue
        parsed = _parse_create_dca_request(content)
        if parsed:
            return parsed
    return None


def _try_stage_dca_plan_confirmation(
    user_wallet: Optional[str],
    session_id: Optional[str],
    user_input: str,
) -> Optional[str]:
    if not user_wallet or _user_confirmed(user_input) or _user_declined(user_input):
        return None
    parsed = _parse_create_dca_request(user_input)
    if not parsed:
        return None
    if parsed.get("max_executions") is None:
        return None

    args = {**parsed, "user_wallet": user_wallet.strip()}
    key = _confirmation_key(user_wallet, session_id)
    with _CONFIRMATION_LOCK:
        _pending_confirmations[key] = {
            "tool": "create_dca_plan",
            "args": args,
            "summary": _summarize_pending_action("create_dca_plan", parsed),
            "details": _pending_action_details("create_dca_plan", parsed),
        }
    return (
        f"Please confirm before I proceed: {_summarize_pending_action('create_dca_plan', parsed)}. "
        "Reply **yes** or **confirm** to proceed, or **no** to cancel."
    )


def _detect_plan_list_intent(user_input: str) -> Optional[dict[str, Any]]:
    lower = user_input.lower()
    if re.search(r"\b(detail|details|history|execution|executions|pause|resume|cancel)\b", lower):
        return None
    wants_plans = (
        (re.search(r"\b(list|show|view|see)\b", lower) and re.search(r"\bplan", lower))
        or re.search(r"\bmy\b.*\bdca\b", lower)
        or re.search(r"\bdca\b.*\bplan", lower)
    )
    if not wants_plans:
        return None
    active_only = bool(re.search(r"\bactive\b", lower))
    status = None
    for s in ("paused", "completed", "cancelled", "active"):
        if re.search(rf"\b{s}\b", lower):
            status = s
            break
    return {"active_only": active_only, "status": status}


def _format_dca_plans_reply(result: dict) -> str:
    if result.get("error"):
        return f"Could not list plans: {result['error']}"
    plans = result.get("plans") or []
    count = int(result.get("count") or 0)
    if count == 0:
        return (
            "You have **no DCA plans** yet. "
            "Ask me to create one (e.g. \"DCA 10 USDC into JUP daily\")."
        )
    lines = [f"**{count} DCA plan(s)** for your wallet:\n"]
    for p in plans:
        max_exec = p.get("max_executions")
        max_label = max_exec if max_exec is not None else "∞"
        lines.append(
            f"- **{p.get('name', 'Plan')}** (`{p.get('id')}`)\n"
            f"  Pair: {p.get('pair')} | Status: **{p.get('status')}**\n"
            f"  Buys: {p.get('executions', 0)}/{max_label} | Spent: {p.get('spent', 0)}\n"
            f"  Mints: {p.get('input_mint')} → {p.get('output_mint')}"
        )
    lines.append("\nNot financial advice. DYOR.")
    return "\n".join(lines)


def run_agent_with_actions(
    user_input: str,
    conversation_history: list,
    user_wallet: Optional[str] = None,
    session_id: Optional[str] = None,
) -> tuple[str, list, list[dict[str, Any]]]:
    """Run one user turn; returns reply, updated history, and tool action trace."""
    actions: list[dict[str, Any]] = []

    pending_execution = _try_execute_pending_confirmation(
        user_wallet, session_id, user_input, conversation_history
    )
    if pending_execution:
        tool_name, args, result, reply = pending_execution
        actions.append({"tool": tool_name, "args": args, "result": result})
        conversation_history.append({"role": "user", "content": user_input.strip()})
        conversation_history.append({"role": "assistant", "content": reply})
        return reply, conversation_history, actions

    if user_wallet and not _user_confirmed(user_input) and not _user_declined(user_input):
        staged_reply = _try_stage_dca_plan_confirmation(user_wallet, session_id, user_input)
        if staged_reply:
            actions.append({
                "tool": "create_dca_plan",
                "args": _parse_create_dca_request(user_input) or {},
                "result": json.dumps({"status": "confirmation_required", "message": staged_reply}),
            })
            conversation_history.append({"role": "user", "content": user_input.strip()})
            conversation_history.append({"role": "assistant", "content": staged_reply})
            return staged_reply, conversation_history, actions

    plan_intent = _detect_plan_list_intent(user_input) if user_wallet else None
    if plan_intent:
        list_args = {
            "user_wallet": user_wallet,
            "active_only": plan_intent["active_only"] and not plan_intent.get("status"),
            "status": plan_intent.get("status"),
        }
        result = list_dca_plans(**list_args)
        reply = _format_dca_plans_reply(result)
        actions.append({
            "tool": "list_dca_plans",
            "args": list_args,
            "result": json.dumps(result, indent=2),
        })
        conversation_history.append({"role": "user", "content": user_input.strip()})
        conversation_history.append({"role": "assistant", "content": reply})
        return reply, conversation_history, actions

    prompt = user_input.strip()
    lower = prompt.lower()
    if re.search(r"\b(list|show|view|see)\b", lower) and re.search(r"\bplan", lower):
        active_only = bool(re.search(r"\bactive\b", lower))
        prompt += (
            "\n[Instruction: call list_dca_plans for this user before answering. "
            f"Use active_only={str(active_only).lower()}. "
            "Do not guess plan counts or IDs.]"
        )
    if re.search(r"\bbalance", lower) and re.search(
        r"\b(check|show|view|see|my|wallet|deposit|available)\b", lower
    ):
        prompt += (
            "\n[Instruction: call get_user_deposit_balance(user_wallet) once for the connected user. "
            "Summarize deposited, available, withdrawable, and reserved amounts per token. "
            "Do not retry tools in a loop if one call succeeds. get_wallet_status is optional.]"
        )
    if _user_confirmed(user_input) and not _user_declined(user_input):
        prompt += (
            "\n[Instruction: the user confirmed the pending action. "
            "Do not ask for confirmation again. Execute the confirmed mutating tool "
            "with the same parameters as before. Do not call list_dca_plans unless they asked.]"
        )
    if user_wallet:
        prompt = f"[Connected user wallet: {user_wallet}]\n{prompt}"
    conversation_history.append({"role": "user", "content": prompt})
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + conversation_history

    for i in range(12):
        print(f"\n  🤖 LLM call [{i + 1}/12] via {llm_provider()} · model {MODEL} …")
        started = time.time()
        response   = call_openrouter(messages)
        print(f"  ⏱️  LLM responded in {time.time() - started:.1f}s")
        message    = response["message"]
        tool_calls = message.get("tool_calls") or []

        if not tool_calls:
            if _user_confirmed(user_input) and user_wallet:
                recovered = _try_execute_pending_confirmation(
                    user_wallet, session_id, user_input, conversation_history
                )
                if recovered:
                    tool_name, args, result, reply = recovered
                    actions.append({"tool": tool_name, "args": args, "result": result})
                    conversation_history.append({"role": "assistant", "content": reply})
                    return reply, conversation_history, actions
            reply = message.get("content", "")
            conversation_history.append({"role": "assistant", "content": reply})
            return reply, conversation_history, actions

        print(f"\n  🔧 [{i + 1}] Tools: {[tc['function']['name'] for tc in tool_calls]}")
        sanitized_tool_calls: list[dict[str, Any]] = []
        parsed_calls: list[tuple[str, dict[str, Any], dict[str, Any]]] = []

        for idx, tc in enumerate(tool_calls):
            name = tc["function"]["name"]
            args = tc["function"].get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            if not isinstance(args, dict):
                args = {}
            call_id = tc.get("id") or f"call_{idx}"
            sanitized_tool_calls.append({
                "id": call_id,
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": _json_compact(args),
                },
            })
            parsed_calls.append((name, args, tc))

        results_this_round: list[tuple[str, dict[str, Any], str]] = []
        for name, args, tc in parsed_calls:
            print(f"  📡 {name}({args})")
            result = execute_tool(
                name,
                args,
                user_wallet=user_wallet,
                user_input=user_input,
                session_id=session_id,
            )
            print("  ✅ Done")
            actions.append({"tool": name, "args": args, "result": result})
            results_this_round.append((name, args, result))

        # CapIX / hosted Ollama: format tool results locally instead of a second LLM turn.
        if (use_hosted_ollama() or use_capix()) and results_this_round:
            reply_parts = [
                _format_pending_execution_reply(name, result)
                for name, _, result in results_this_round
            ]
            reply = "\n\n".join(part for part in reply_parts if part)
            conversation_history.append({"role": "assistant", "content": reply})
            return reply, conversation_history, actions

        messages.append({
            "role": "assistant",
            "content": message.get("content") or "",
            "tool_calls": sanitized_tool_calls,
        })

        for (_, _, _), (_, _, result) in zip(parsed_calls, results_this_round):
            messages.append({"role": "tool", "content": result})

    reply = "Agent reached max iterations."
    conversation_history.append({"role": "assistant", "content": reply})
    return reply, conversation_history, actions


def run_agent(user_input: str, conversation_history: list) -> tuple[str, list]:
    reply, history, _ = run_agent_with_actions(user_input, conversation_history)
    return reply, history


BANNER = r"""
╔══════════════════════════════════════════════════════════════╗
║   💰  Solana DCA Agent                                       ║
║   Recurring buys · Jupiter v2 swaps · hosted LLM                ║
╚══════════════════════════════════════════════════════════════╝
"""


def main():
    print(BANNER)
    if not db_configured():
        print("  ❌ DATABASE_URL is not set. Add your Neon connection string to .env")
        return
    from db import init_db

    init_db()
    print("  🗄️  Neon database ready")
    print(f"  LLM        : {llm_provider()} ({MODEL})")
    if use_capix():
        print(f"  CapIX URL  : {CAPIX_API_URL}")
        print(f"  CapIX model: {CAPIX_MODEL}")
    elif use_hosted_ollama():
        print(f"  Ollama URL : {HOSTED_OLLAMA_BASE_URL}")
        print(
            f"  Ollama key : "
            f"{'configured' if HOSTED_OLLAMA_API_KEY else 'missing - set HOSTED_MODEL_API_KEY in .env'}"
        )
    else:
        print(
            f"  OpenRouter : "
            f"{'configured' if OPEN_ROUTER_API else 'missing - set CAPIX_API_KEY, HOSTED_MODEL_API_KEY, or OPEN_ROUTER_API in .env'}"
        )
    print(f"  RPC        : {SOLANA_RPC}")
    print(f"  Cluster    : {SOLANA_CLUSTER} ({'Jupiter v2 swaps' if _is_mainnet() else 'devnet mode'})")
    print(f"  Jupiter API: {JUPITER_BUILD_API}")
    wallet = get_wallet_pubkey()
    print(f"  Wallet     : {wallet or 'not configured (set DCA_WALLET_PRIVATE_KEY)'}")
    print()

    env_path = AGENT_DIR / ".env"
    print(f"  Env     : {env_path if env_path.exists() else '(no .env - copy .env.example)'}")
    if start_scheduler():
        print(f"  ⏱️  Background scheduler started (every {SCHEDULER_POLL_SECONDS}s)")
    print()
    print("  Example prompts:")
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
        except RuntimeError as e:
            print(f"  ❌ Groq error: {e}")
        except Exception as e:
            print(f"  ❌ Error: {e}")


if __name__ == "__main__":
    main()