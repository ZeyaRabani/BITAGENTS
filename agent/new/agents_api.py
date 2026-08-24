"""
Unified HTTP API for BIT Agents AI agents (DCA, Kickstart Copilot, future agents).

Run locally:
  cd agent/new
  pip install -r requirements.txt
  python agents_api.py

Default: http://127.0.0.1:8765

Legacy entry point `python dca_api.py` still works (imports this app).
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit, urlunsplit

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

import requests
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from deposit_ledger import (
    get_agent_wallet_info,
    get_user_balances,
    get_user_dca_executions,
    list_user_deposits,
    list_user_ledger_history,
    verify_and_record_deposit,
    withdraw_user_tokens,
)
from db import (
    append_chat_messages,
    assert_chat_session_access,
    db_configured,
    delete_chat_session,
    get_platform_metrics,
    init_db,
    list_watchlist,
    load_chat_history,
)
from hosted_llm import (
    CAPIX_API_URL,
    CAPIX_MAX_RETRIES,
    CAPIX_MODEL,
    CAPIX_READ_TIMEOUT_SECONDS,
    HOSTED_OLLAMA_BASE_URL,
    HOSTED_OLLAMA_MODEL,
    llm_configured,
    llm_provider,
    ping_llm as _ping_llm,
    use_capix,
    use_hosted_ollama,
)
from dca_agent import (
    JUPITER_BUILD_API,
    MODEL,
    SCHEDULER_POLL_SECONDS,
    SOLANA_CLUSTER,
    SOLANA_RPC,
    get_dca_history,
    get_dca_plan,
    get_wallet_pubkey,
    list_dca_plans,
    resolve_token,
    run_agent_with_actions,
    start_metrics_scheduler,
    start_scheduler,
    update_dca_plan,
    update_dca_plan_status,
)
from easya_screener_client import CACHE_TTL_SECONDS, screener_configured
from easya_trading import (
    EASYA_ORDER_POLL_SECONDS,
    cancel_easya_order,
    get_easya_order_executions,
    list_easya_orders,
    place_limit_buy_order,
    place_market_buy_order,
    place_threshold_buy_order,
    start_easya_order_scheduler,
    update_easya_limit_order,
)
from easya_trading_ledger import (
    get_easya_agent_wallet_info,
    get_easya_user_balances,
    get_easya_wallet_pubkey,
    verify_and_record_easya_deposit,
    withdraw_easya_tokens,
)
from kickstart_copilot_agent import (
    KICKSTART_MODEL,
    list_verified_kickstart_tokens,
    run_kickstart_agent,
)
from whale_tracking_agent import WHALE_MODEL, run_whale_tracking_agent
from solana_token_onchain import TOKEN_RESEARCH_CACHE_TTL_SECONDS, get_token_research_cache_stats
from token_research_agent import TOKEN_RESEARCH_MODEL, run_token_research_agent
from solana_wallet_tools import WALLET_SNAPSHOT_CACHE_TTL_SECONDS
from wallet_monitoring_agent import (
    WALLET_MONITORING_MODEL,
    get_wallet_monitoring_cache_stats,
    run_wallet_monitoring_agent,
)
from due_diligence_agent import (
    DUE_DILIGENCE_MODEL,
    get_due_diligence_cache_stats,
    run_due_diligence_agent,
)
from cache_store import cache_backend
from hedge_fund_agent import HEDGE_FUND_MODEL, run_hedge_fund_agent
from hedge_fund_core import get_fee_structure
from hedge_fund_ledger import (
    get_hf_agent_wallet_info,
    get_hf_user_balances,
    get_hf_wallet_pubkey,
    list_hf_user_ledger,
    verify_and_record_hf_deposit,
    withdraw_hf_tokens,
)
from hedge_fund_live import list_live_trades as hf_list_live_trades
from hedge_fund_paper import (
    HF_MAX_STRATEGY_USDC,
    HF_MIN_HORIZON_DAYS,
    HF_MONITOR_INTERVAL_SECONDS,
    HF_SCHEDULER_POLL_SECONDS,
    add_capital_to_strategy as hf_add_capital,
    analyze_live_asset as hf_analyze_live_asset,
    confirm_strategy as hf_confirm_strategy,
    create_strategy as hf_create_strategy,
    dismiss_strategy as hf_dismiss_strategy,
    list_strategies as hf_list_strategies,
    liquidate_strategy as hf_liquidate_strategy,
    monitor_cycle as hf_monitor_cycle,
    paper_dashboard as hf_paper_dashboard,
    retry_strategy_deploy as hf_retry_strategy_deploy,
    run_strategy_backtest as hf_run_strategy_backtest,
    scheduler_status as hf_scheduler_status,
    start_hedge_fund_scheduler,
    strategy_live_pnl as hf_strategy_live_pnl,
    update_strategy_rules as hf_update_strategy_rules,
)
from meteora_dlmm import check_pool_infrastructure, get_pool_creation_cost_sol
from volume_agent import (
    VOLUME_MODEL,
    VOLUME_SCHEDULER_POLL_SECONDS,
    create_volume_campaign,
    ensure_volume_meteora_pool,
    get_volume_history,
    list_volume_campaigns,
    provision_campaign_infrastructure,
    run_volume_agent_with_actions,
    start_volume_scheduler,
    update_volume_campaign_status,
)
from volume_ledger import (
    VOLUME_PLATFORM_FEE_RATE,
    get_volume_agent_wallet_info,
    get_volume_user_balances,
    get_volume_wallet_pubkey,
    list_volume_user_ledger,
    verify_and_record_volume_deposit,
    withdraw_volume_tokens,
)
from wallet_auth import (
    create_auth_challenge,
    get_session_info,
    internal_api_configured,
    resolve_session_token,
    revoke_session_token,
    verify_auth_challenge,
    verify_internal_api_key,
)

def _resolve_api_host() -> str:
    explicit = os.environ.get("AGENTS_API_HOST") or os.environ.get("DCA_API_HOST")
    if explicit:
        return explicit
    # Render (and similar) inject PORT — bind all interfaces in that case.
    if os.environ.get("PORT"):
        return "0.0.0.0"
    return "127.0.0.1"


def _resolve_api_port() -> int:
    if os.environ.get("PORT"):
        return int(os.environ["PORT"])
    return int(
        os.environ.get(
            "AGENTS_API_PORT",
            os.environ.get("DCA_API_PORT", "8765"),
        )
    )


def _cors_allow_origins() -> list[str]:
    defaults = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    raw = (os.environ.get("CORS_ALLOW_ORIGINS") or "").strip()
    if not raw:
        return defaults
    extra = [o.strip() for o in raw.split(",") if o.strip()]
    # Preserve order, dedupe
    seen: set[str] = set()
    out: list[str] = []
    for origin in defaults + extra:
        if origin not in seen:
            seen.add(origin)
            out.append(origin)
    return out


API_HOST = _resolve_api_host()
API_PORT = _resolve_api_port()

app = FastAPI(title="BIT Agents API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AuthChallengeResponse(BaseModel):
    user_wallet: str
    message: str
    nonce: str
    expires_at: str


class AuthVerifyRequest(BaseModel):
    user_wallet: str = Field(min_length=32)
    message: str = Field(min_length=8)
    signature: str = Field(min_length=32)


class AuthVerifyResponse(BaseModel):
    status: str
    token: str
    user_wallet: str
    expires_at: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: Optional[str] = None


class KickstartChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: Optional[str] = None
    history: Optional[list[dict[str, str]]] = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    actions: list[dict[str, Any]]


class DepositVerifyRequest(BaseModel):
    signature: str = Field(min_length=32)


class WithdrawRequest(BaseModel):
    token: str = Field(min_length=1)
    amount: float = Field(gt=0)


class PlanStatusRequest(BaseModel):
    action: str = Field(min_length=3)


class UpdateDcaPlanRequest(BaseModel):
    amount_per_buy: Optional[float] = Field(default=None, gt=0)
    interval: Optional[str] = Field(default=None, min_length=1)
    max_executions: Optional[int] = Field(default=None, ge=1)
    total_budget: Optional[float] = Field(default=None, gt=0)
    slippage_bps: Optional[int] = Field(default=None, ge=1, le=5000)


def _redact_rpc_url(rpc_url: str) -> str:
    parts = urlsplit(rpc_url)
    if not parts.query:
        return rpc_url
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "api-key=REDACTED", parts.fragment))


def _normalize_chat_history(history: Optional[list[dict[str, str]]]) -> list[dict[str, str]]:
    if not history:
        return []
    normalized: list[dict[str, str]] = []
    for msg in history[-20:]:
        role = (msg.get("role") or "").strip()
        content = (msg.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            normalized.append({"role": role, "content": content})
    return normalized


def require_internal_key(x_internal_key: Optional[str] = Header(default=None)) -> None:
    if not verify_internal_api_key(x_internal_key):
        raise HTTPException(status_code=403, detail="Invalid internal API key.")


def require_wallet_session(
    authorization: Optional[str] = Header(default=None),
    _: None = Depends(require_internal_key),
) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Wallet sign-in required. Connect your wallet and authenticate.",
        )
    token = authorization.removeprefix("Bearer ").strip()
    wallet = resolve_session_token(token)
    if not wallet:
        raise HTTPException(status_code=401, detail="Invalid or expired session. Sign in again.")
    return wallet


@app.on_event("startup")
def _startup() -> None:
    if not db_configured():
        raise RuntimeError("DATABASE_URL is not set. Add your Neon connection string to agent/new/.env")
    try:
        init_db()
    except Exception as exc:
        raise RuntimeError(f"Neon database init failed: {exc}") from exc
    print("  🗄️  Neon database ready")
    if internal_api_configured():
        print("  🔐 Internal API key enabled")
    else:
        print("  ⚠️  AGENTS_INTERNAL_API_KEY not set (optional for local dev)")
    if start_scheduler():
        print(f"  ⏱️  DCA scheduler started (every {SCHEDULER_POLL_SECONDS}s)")
    if start_metrics_scheduler():
        print("  📊 Platform metrics scheduler started (refresh every 24h)")
    if start_easya_order_scheduler():
        print(f"  📈 EasyA limit-order scheduler started (every {EASYA_ORDER_POLL_SECONDS}s)")
    if start_volume_scheduler():
        print(f"  📊 Volume Agent scheduler started (every {VOLUME_SCHEDULER_POLL_SECONDS}s)")
    if start_hedge_fund_scheduler():
        print(
            f"  📈 Hedge Fund paper monitor started "
            f"(every {HF_MONITOR_INTERVAL_SECONDS // 3600}h, close-poll {HF_SCHEDULER_POLL_SECONDS // 60}m)"
        )
    print(f"  🗄️  Cache backend: {cache_backend()}")
    print("  🤖 Agents: DCA, Kickstart Token Copilot, Volume Agent, Hedge Fund")


@app.get("/health")
def health(ping_llm: bool = Query(False)) -> dict[str, Any]:
    wallet = get_wallet_pubkey()
    agent_info = get_agent_wallet_info()
    llm_ping = _ping_llm() if ping_llm and llm_configured() else None
    return {
        "status": "ok",
        "agents": {
            "dca": {
                "path_prefix": "/",
                "chat": "/chat",
                "pricing": "0.5% per successful DCA execution",
            },
            "kickstart-copilot": {
                "path_prefix": "/kickstart",
                "chat": "/kickstart/chat",
                "pricing": "free analysis · 0.1% per Jupiter buy",
            },
            "volume": {
                "path_prefix": "/volume",
                "chat": "/volume/chat",
                "pricing": "0.25% per swap leg · Meteora DLMM",
            },
        },
        "llm": llm_provider(),
        "llm_configured": llm_configured(),
        "llm_reachable": llm_ping.get("ok") if llm_ping else None,
        "llm_ping": llm_ping,
        "capix_url": CAPIX_API_URL if use_capix() else None,
        "capix_model": CAPIX_MODEL if use_capix() else None,
        "capix_read_timeout_seconds": CAPIX_READ_TIMEOUT_SECONDS if use_capix() else None,
        "capix_max_retries": CAPIX_MAX_RETRIES if use_capix() else None,
        "hosted_ollama_url": HOSTED_OLLAMA_BASE_URL if use_hosted_ollama() else None,
        "hosted_ollama_model": HOSTED_OLLAMA_MODEL if use_hosted_ollama() else None,
        "dca_model": MODEL,
        "kickstart_model": KICKSTART_MODEL,
        "database": "neon_postgres" if db_configured() else "unconfigured",
        "cache_backend": cache_backend(),
        "auth": "wallet_signature",
        "internal_api_key_required": internal_api_configured(),
        "cluster": SOLANA_CLUSTER,
        "rpc": _redact_rpc_url(SOLANA_RPC),
        "jupiter_api": JUPITER_BUILD_API,
        "wallet": wallet or None,
        "wallet_configured": bool(wallet),
        "agent_wallet": agent_info.get("agent_wallet"),
        "any_spl_token": agent_info.get("any_spl_token", True),
        "common_tokens": agent_info.get("common_tokens", []),
    }


@app.get("/health/llm")
def health_llm() -> dict[str, Any]:
    if not llm_configured():
        return {
            "ok": False,
            "provider": llm_provider(),
            "error": "CAPIX_API_KEY, HOSTED_MODEL_API_KEY, or OPEN_ROUTER_API is not set",
        }
    result = _ping_llm()
    return {"provider": llm_provider(), **result}


@app.get("/kickstart/health")
def kickstart_health() -> dict[str, Any]:
    easya_wallet = get_easya_wallet_pubkey()
    return {
        "status": "ok",
        "agent": "EasyA Analysis Agent",
        "model": KICKSTART_MODEL,
        "llm": llm_provider(),
        "llm_configured": llm_configured(),
        "capix_url": CAPIX_API_URL if use_capix() else None,
        "capix_model": CAPIX_MODEL if use_capix() else None,
        "hosted_ollama_url": HOSTED_OLLAMA_BASE_URL if use_hosted_ollama() else None,
        "pricing": "free analysis · 0.1% per successful Jupiter buy",
        "auth_required": True,
        "data_source": "easy_screener",
        "easy_screener_configured": screener_configured(),
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
        "cluster": SOLANA_CLUSTER,
        "trading_wallet_configured": bool(easya_wallet),
        "trading_wallet": easya_wallet,
        "platform_fee_rate": 0.001,
    }


# ─── Shared auth ──────────────────────────────────────────────────────────────

@app.get("/auth/challenge", response_model=AuthChallengeResponse)
def auth_challenge(
    user_wallet: str = Query(..., min_length=32),
    _: None = Depends(require_internal_key),
) -> dict[str, Any]:
    result = create_auth_challenge(user_wallet.strip())
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/auth/verify", response_model=AuthVerifyResponse)
def auth_verify(
    body: AuthVerifyRequest,
    _: None = Depends(require_internal_key),
) -> dict[str, Any]:
    result = verify_auth_challenge(body.user_wallet.strip(), body.message, body.signature.strip())
    if "error" in result:
        raise HTTPException(status_code=401, detail=result["error"])
    return result


@app.get("/auth/me")
def auth_me(
    authorization: Optional[str] = Header(default=None),
    _: None = Depends(require_internal_key),
) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing session token.")
    info = get_session_info(authorization.removeprefix("Bearer ").strip())
    if not info:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")
    return info


@app.post("/auth/logout")
def auth_logout(
    authorization: Optional[str] = Header(default=None),
    _: None = Depends(require_internal_key),
) -> dict[str, bool]:
    if authorization and authorization.startswith("Bearer "):
        revoke_session_token(authorization.removeprefix("Bearer ").strip())
    return {"ok": True}


# ─── DCA agent routes ─────────────────────────────────────────────────────────

@app.get("/tokens/resolve")
def resolve_token_info(
    query: str = Query(..., min_length=2),
    _: None = Depends(require_internal_key),
) -> dict[str, Any]:
    result = resolve_token(query.strip())
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {
        "symbol": result["symbol"],
        "mint": result["mint"],
        "decimals": result["decimals"],
        "name": result.get("name"),
    }


@app.get("/wallet/agent")
def wallet_agent(_: None = Depends(require_internal_key)) -> dict[str, Any]:
    return get_agent_wallet_info()


@app.get("/wallet/balance")
def wallet_balance(
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    return get_user_balances(auth_wallet)


@app.get("/wallet/deposits")
def wallet_deposits(
    auth_wallet: str = Depends(require_wallet_session),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    return list_user_deposits(auth_wallet, limit)


@app.post("/wallet/deposit/verify")
def wallet_deposit_verify(
    body: DepositVerifyRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    result = verify_and_record_deposit(body.signature.strip(), auth_wallet)
    if "error" in result:
        if result.get("status") == "already_recorded":
            return result
        detail = result["error"]
        status = 403 if result.get("status") == "rejected" else 400
        raise HTTPException(status_code=status, detail=detail)
    return result


@app.post("/wallet/withdraw")
def wallet_withdraw(
    body: WithdrawRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    try:
        result = withdraw_user_tokens(auth_wallet, body.token.strip(), float(body.amount))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Withdrawal failed: {exc}") from exc
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/plans")
def list_plans(
    auth_wallet: str = Depends(require_wallet_session),
    active_only: bool = Query(False),
    status: Optional[str] = Query(None),
) -> dict[str, Any]:
    result = list_dca_plans(status=status, user_wallet=auth_wallet, active_only=active_only)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/plans/{plan_id}")
def get_plan(
    plan_id: str,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    result = get_dca_plan(plan_id, user_wallet=auth_wallet)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/plans/{plan_id}/executions")
def plan_executions(
    plan_id: str,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    result = get_dca_history(plan_id, user_wallet=auth_wallet)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.patch("/plans/{plan_id}")
def update_plan(
    plan_id: str,
    body: UpdateDcaPlanRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    result = update_dca_plan(
        plan_id,
        auth_wallet,
        amount_per_buy=body.amount_per_buy,
        interval=body.interval,
        max_executions=body.max_executions,
        total_budget=body.total_budget,
        slippage_bps=body.slippage_bps,
    )
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/plans/{plan_id}/status")
def plan_status(
    plan_id: str,
    body: PlanStatusRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    result = update_dca_plan_status(plan_id, body.action.strip(), user_wallet=auth_wallet)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/wallet/ledger")
def wallet_ledger(
    auth_wallet: str = Depends(require_wallet_session),
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    return list_user_ledger_history(auth_wallet, limit)


@app.get("/wallet/dca-executions")
def wallet_dca_executions(
    auth_wallet: str = Depends(require_wallet_session),
    limit: int = Query(100, ge=1, le=200),
) -> dict[str, Any]:
    return get_user_dca_executions(auth_wallet, limit)


@app.get("/metrics")
def platform_metrics(
    refresh: bool = Query(False),
    _: None = Depends(require_internal_key),
) -> dict[str, Any]:
    return get_platform_metrics(refresh=refresh)


@app.post("/chat", response_model=ChatResponse)
def dca_chat(
    body: ChatRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> ChatResponse:
    session_id = body.session_id or str(uuid.uuid4())
    access_error = assert_chat_session_access(session_id, auth_wallet)
    if access_error:
        raise HTTPException(status_code=403, detail=access_error)

    history = load_chat_history(session_id)
    user_message = body.message.strip()

    try:
        reply, history, actions = run_agent_with_actions(
            user_message,
            history,
            user_wallet=auth_wallet,
            session_id=session_id,
        )
    except requests.exceptions.ConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail="Cannot reach LLM API. Check CAPIX_API_URL or HOSTED_OLLAMA_URL and network.",
        ) from exc
    except requests.exceptions.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"LLM error: {exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    append_chat_messages(session_id, user_message, reply, actions, user_wallet=auth_wallet)
    return ChatResponse(reply=reply, session_id=session_id, actions=actions)


@app.delete("/chat/{session_id}")
def clear_dca_session(
    session_id: str,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, bool]:
    access_error = assert_chat_session_access(session_id, auth_wallet)
    if access_error:
        raise HTTPException(status_code=403, detail=access_error)
    deleted = delete_chat_session(session_id)
    return {"ok": deleted}


# ─── Kickstart Copilot routes ─────────────────────────────────────────────────

@app.post("/kickstart/chat", response_model=ChatResponse)
def kickstart_chat(
    body: KickstartChatRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> ChatResponse:
    session_id = body.session_id or str(uuid.uuid4())
    history = _normalize_chat_history(body.history)
    user_message = body.message.strip()

    try:
        reply, _, actions = run_kickstart_agent(
            user_message,
            history,
            user_wallet=auth_wallet,
            session_id=session_id,
        )
    except requests.exceptions.ConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail="Cannot reach LLM API. Check CAPIX_API_URL or HOSTED_OLLAMA_URL and network.",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ChatResponse(reply=reply, session_id=session_id, actions=actions)


@app.delete("/kickstart/chat/{session_id}")
def clear_kickstart_session(
    session_id: str,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, bool]:
    # Kickstart chat is stateless - nothing persisted in the database.
    return {"ok": True}


@app.get("/kickstart/watchlist")
def kickstart_watchlist(
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    return list_watchlist(auth_wallet)


@app.get("/kickstart/tokens")
def kickstart_verified_tokens(
    query: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    _: None = Depends(require_internal_key),
) -> dict[str, Any]:
    """Tokens from EASY Screener (cached up to 1h per token on server)."""
    return list_verified_kickstart_tokens(
        category=category,
        tag=tag,
        active_only=True,
        query=query,
    )


class EasyaDepositVerifyRequest(BaseModel):
    signature: str = Field(min_length=32)


class EasyaWithdrawRequest(BaseModel):
    token: str = Field(min_length=1)
    amount: float = Field(gt=0)


class EasyaMarketOrderRequest(BaseModel):
    token: str = Field(min_length=1)
    amount_sol: float = Field(gt=0)
    slippage_bps: int = Field(default=100, ge=1, le=5000)


class EasyaLimitOrderRequest(BaseModel):
    token: str = Field(min_length=1)
    amount_sol: float = Field(gt=0)
    limit_price_usd: Optional[float] = Field(default=None, gt=0)
    limit_market_cap_usd: Optional[float] = Field(default=None, gt=0)
    condition_mode: Optional[str] = Field(default=None)
    slippage_bps: int = Field(default=100, ge=1, le=5000)


class EasyaThresholdOrderRequest(BaseModel):
    token: str = Field(min_length=1)
    amount_sol: float = Field(gt=0)
    limit_price_usd: Optional[float] = Field(default=None, gt=0)
    limit_market_cap_usd: Optional[float] = Field(default=None, gt=0)
    stop_price_usd: Optional[float] = Field(default=None, gt=0)
    stop_market_cap_usd: Optional[float] = Field(default=None, gt=0)
    condition_mode: Optional[str] = Field(default=None)
    slippage_bps: int = Field(default=100, ge=1, le=5000)
    max_executions: Optional[int] = Field(default=None, ge=1)
    check_interval_seconds: Optional[int] = Field(default=None, ge=60)


class EasyaUpdateLimitOrderRequest(BaseModel):
    amount_sol: Optional[float] = Field(default=None, gt=0)
    limit_price_usd: Optional[float] = Field(default=None, gt=0)
    limit_market_cap_usd: Optional[float] = Field(default=None, gt=0)
    stop_price_usd: Optional[float] = Field(default=None, gt=0)
    stop_market_cap_usd: Optional[float] = Field(default=None, gt=0)
    slippage_bps: Optional[int] = Field(default=None, ge=1, le=5000)


@app.get("/kickstart/wallet/agent")
def kickstart_wallet_agent(_: None = Depends(require_internal_key)) -> dict[str, Any]:
    return get_easya_agent_wallet_info()


@app.get("/kickstart/wallet/balance")
def kickstart_wallet_balance(
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    return get_easya_user_balances(auth_wallet)


@app.post("/kickstart/wallet/deposit/verify")
def kickstart_deposit_verify(
    body: EasyaDepositVerifyRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    result = verify_and_record_easya_deposit(body.signature.strip(), auth_wallet)
    if result.get("error") and result.get("status") != "already_recorded":
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/kickstart/wallet/withdraw")
def kickstart_wallet_withdraw(
    body: EasyaWithdrawRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    result = withdraw_easya_tokens(auth_wallet, body.token.strip(), body.amount)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/kickstart/orders")
def kickstart_list_orders(
    auth_wallet: str = Depends(require_wallet_session),
    active_only: bool = Query(False),
    refresh_metrics: bool = Query(False),
) -> dict[str, Any]:
    return list_easya_orders(auth_wallet, active_only=active_only, refresh_metrics=refresh_metrics)


@app.get("/kickstart/orders/{order_id}/executions")
def kickstart_order_executions(
    order_id: str,
    auth_wallet: str = Depends(require_wallet_session),
    limit: int = Query(50, ge=1, le=100),
) -> dict[str, Any]:
    result = get_easya_order_executions(auth_wallet, order_id, limit=limit)
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.post("/kickstart/orders/market")
def kickstart_market_order(
    body: EasyaMarketOrderRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    result = place_market_buy_order(
        auth_wallet,
        body.token.strip(),
        body.amount_sol,
        body.slippage_bps,
    )
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/kickstart/orders/limit")
def kickstart_limit_order(
    body: EasyaLimitOrderRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    result = place_limit_buy_order(
        auth_wallet,
        body.token.strip(),
        body.amount_sol,
        limit_price_usd=body.limit_price_usd,
        limit_market_cap_usd=body.limit_market_cap_usd,
        condition_mode=body.condition_mode,
        slippage_bps=body.slippage_bps,
    )
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/kickstart/orders/threshold")
def kickstart_threshold_order(
    body: EasyaThresholdOrderRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    result = place_threshold_buy_order(
        auth_wallet,
        body.token.strip(),
        body.amount_sol,
        limit_price_usd=body.limit_price_usd,
        limit_market_cap_usd=body.limit_market_cap_usd,
        stop_price_usd=body.stop_price_usd,
        stop_market_cap_usd=body.stop_market_cap_usd,
        condition_mode=body.condition_mode,
        slippage_bps=body.slippage_bps,
        max_executions=body.max_executions,
        check_interval_seconds=body.check_interval_seconds,
    )
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/kickstart/orders/{order_id}/cancel")
def kickstart_cancel_order(
    order_id: str,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    result = cancel_easya_order(auth_wallet, order_id)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.patch("/kickstart/orders/{order_id}")
def kickstart_update_order(
    order_id: str,
    body: EasyaUpdateLimitOrderRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    result = update_easya_limit_order(
        auth_wallet,
        order_id,
        amount_sol=body.amount_sol,
        limit_price_usd=body.limit_price_usd,
        limit_market_cap_usd=body.limit_market_cap_usd,
        stop_price_usd=body.stop_price_usd,
        stop_market_cap_usd=body.stop_market_cap_usd,
        slippage_bps=body.slippage_bps,
    )
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ─── Volume Agent ─────────────────────────────────────────────────────────────


class VolumeChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: Optional[str] = None


class CreateVolumeCampaignRequest(BaseModel):
    base_token: str = Field(min_length=1)
    quote_token: str = Field(default="SOL", min_length=1)
    trade_amount: float = Field(gt=0)
    interval: str = Field(min_length=1)
    max_executions: int = Field(ge=1)
    name: Optional[str] = None
    total_budget: Optional[float] = Field(default=None, gt=0)
    slippage_bps: int = Field(default=100, ge=1, le=5000)
    seed_token_amount: float = Field(default=0.0, ge=0)


class VolumeCampaignStatusRequest(BaseModel):
    action: str = Field(min_length=3)


class VolumePoolEnsureRequest(BaseModel):
    base_token: str = Field(min_length=1)
    quote_token: str = Field(default="SOL", min_length=1)
    create_if_missing: bool = False


@app.get("/volume/health")
def volume_health() -> dict[str, Any]:
    volume_wallet = get_volume_wallet_pubkey()
    return {
        "status": "ok",
        "agent": "Volume Agent",
        "model": VOLUME_MODEL,
        "llm": llm_provider(),
        "llm_configured": llm_configured(),
        "capix_url": CAPIX_API_URL if use_capix() else None,
        "capix_model": CAPIX_MODEL if use_capix() else None,
        "hosted_ollama_url": HOSTED_OLLAMA_BASE_URL if use_hosted_ollama() else None,
        "pricing": "0.25% per swap leg (buy and sell)",
        "auth_required": True,
        "cluster": SOLANA_CLUSTER,
        "trading_wallet_configured": bool(volume_wallet),
        "trading_wallet": volume_wallet,
        "platform_fee_rate": VOLUME_PLATFORM_FEE_RATE,
        "pool_creation_cost_sol": get_pool_creation_cost_sol(),
        "scheduler_poll_seconds": VOLUME_SCHEDULER_POLL_SECONDS,
    }


@app.post("/volume/chat", response_model=ChatResponse)
def volume_chat(
    body: VolumeChatRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> ChatResponse:
    session_id = body.session_id or str(uuid.uuid4())
    access_error = assert_chat_session_access(session_id, auth_wallet)
    if access_error:
        raise HTTPException(status_code=403, detail=access_error)

    history = load_chat_history(session_id)
    user_message = body.message.strip()
    reply, history, actions = run_volume_agent_with_actions(
        user_message,
        history,
        user_wallet=auth_wallet,
        session_id=session_id,
    )
    append_chat_messages(session_id, user_message, reply, actions, user_wallet=auth_wallet)
    return ChatResponse(reply=reply, session_id=session_id, actions=actions)


@app.get("/volume/wallet/agent")
def volume_wallet_agent(_: None = Depends(require_internal_key)) -> dict[str, Any]:
    return get_volume_agent_wallet_info()


@app.get("/volume/wallet/balance")
def volume_wallet_balance(
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    return get_volume_user_balances(auth_wallet)


@app.post("/volume/wallet/deposit/verify")
def volume_deposit_verify(
    body: DepositVerifyRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    result = verify_and_record_volume_deposit(body.signature.strip(), auth_wallet)
    if result.get("error") and result.get("status") != "already_recorded":
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/volume/wallet/withdraw")
def volume_wallet_withdraw(
    body: WithdrawRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    result = withdraw_volume_tokens(auth_wallet, body.token.strip(), body.amount)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/volume/wallet/ledger")
def volume_wallet_ledger(
    auth_wallet: str = Depends(require_wallet_session),
    limit: int = Query(50, ge=1, le=100),
) -> dict[str, Any]:
    entries = list_volume_user_ledger(auth_wallet, limit=limit)
    return {"user_wallet": auth_wallet, "entries": entries, "count": len(entries)}


@app.get("/volume/pool/check")
def volume_pool_check(
    base_token: str = Query(..., min_length=1, description="Base token symbol or mint"),
    quote_token: str = Query(default="SOL", min_length=1, description="Quote token symbol or mint"),
    _: None = Depends(require_internal_key),
) -> dict[str, Any]:
    base = resolve_token(base_token.strip())
    quote = resolve_token(quote_token.strip())
    if "error" in base:
        raise HTTPException(status_code=400, detail=base["error"])
    if "error" in quote:
        raise HTTPException(status_code=400, detail=quote["error"])
    result = check_pool_infrastructure(base["mint"], quote["mint"])
    return {
        **result,
        "base_token": base["symbol"],
        "quote_token": quote["symbol"],
        "base_mint": base["mint"],
        "quote_mint": quote["mint"],
        "pair": f"{base['symbol']}/{quote['symbol']}",
    }


@app.post("/volume/pool/ensure")
def volume_pool_ensure(
    body: VolumePoolEnsureRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    result = ensure_volume_meteora_pool(
        base_token=body.base_token.strip(),
        quote_token=body.quote_token.strip(),
        user_wallet=auth_wallet,
        create_if_missing=body.create_if_missing,
    )
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/volume/campaigns")
def volume_list_campaigns(
    auth_wallet: str = Depends(require_wallet_session),
    active_only: bool = Query(False),
    status: Optional[str] = Query(None),
) -> dict[str, Any]:
    result = list_volume_campaigns(auth_wallet, active_only=active_only, status=status)
    return {**result, "user_wallet": auth_wallet}


@app.post("/volume/campaigns")
def volume_create_campaign(
    body: CreateVolumeCampaignRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    result = create_volume_campaign(
        base_token=body.base_token.strip(),
        quote_token=body.quote_token.strip(),
        trade_amount=body.trade_amount,
        interval=body.interval.strip(),
        max_executions=body.max_executions,
        user_wallet=auth_wallet,
        name=body.name.strip() if body.name else None,
        total_budget=body.total_budget,
        slippage_bps=body.slippage_bps,
        seed_token_amount=body.seed_token_amount,
    )
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/volume/campaigns/{campaign_id}")
def volume_get_campaign(
    campaign_id: str,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    from volume_agent import _assert_campaign_owner

    campaign = _assert_campaign_owner(campaign_id, auth_wallet)
    if "error" in campaign:
        raise HTTPException(status_code=404, detail=campaign["error"])
    return {"campaign": campaign}


@app.get("/volume/campaigns/{campaign_id}/executions")
def volume_campaign_executions(
    campaign_id: str,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    result = get_volume_history(campaign_id, auth_wallet)
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.post("/volume/campaigns/{campaign_id}/status")
def volume_campaign_status(
    campaign_id: str,
    body: VolumeCampaignStatusRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    result = update_volume_campaign_status(campaign_id, body.action, auth_wallet)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/volume/campaigns/{campaign_id}/provision")
def volume_campaign_provision(
    campaign_id: str,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    from volume_agent import _assert_campaign_owner

    owned = _assert_campaign_owner(campaign_id, auth_wallet)
    if "error" in owned:
        raise HTTPException(status_code=404, detail=owned["error"])
    result = provision_campaign_infrastructure(campaign_id)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ─── Research agents (Whale, Token Research, Wallet Monitoring, Due Diligence) ─

def _run_research_chat(
    runner,
    body: KickstartChatRequest,
    auth_wallet: str,
) -> ChatResponse:
    session_id = body.session_id or str(uuid.uuid4())
    history = _normalize_chat_history(body.history)
    user_message = body.message.strip()
    try:
        reply, _, actions = runner(
            user_message,
            history,
            user_wallet=auth_wallet,
            session_id=session_id,
        )
    except requests.exceptions.ConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail="Cannot reach LLM API. Check CAPIX_API_URL or HOSTED_OLLAMA_URL and network.",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ChatResponse(reply=reply, session_id=session_id, actions=actions)


@app.get("/whale-tracking/health")
def whale_tracking_health() -> dict[str, Any]:
    return {
        "status": "ok",
        "agent": "Whale Tracking Agent",
        "model": WHALE_MODEL,
        "llm": llm_provider(),
        "llm_configured": llm_configured(),
        "auth_required": True,
        "cluster": SOLANA_CLUSTER,
        "pricing": "free · wallet sign-in required",
    }


@app.post("/whale-tracking/chat", response_model=ChatResponse)
def whale_tracking_chat(
    body: KickstartChatRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> ChatResponse:
    return _run_research_chat(run_whale_tracking_agent, body, auth_wallet)


@app.get("/token-research/health")
def token_research_health() -> dict[str, Any]:
    return {
        "status": "ok",
        "agent": "Token Research Agent",
        "model": TOKEN_RESEARCH_MODEL,
        "llm": llm_provider(),
        "llm_configured": llm_configured(),
        "auth_required": True,
        "data_source": "solana_rpc + jupiter + meteora_datapi",
        "easy_screener_configured": screener_configured(),
        "metrics_cache_ttl_seconds": TOKEN_RESEARCH_CACHE_TTL_SECONDS,
        "metrics_cache": get_token_research_cache_stats(),
        "cluster": SOLANA_CLUSTER,
        "pricing": "free · wallet sign-in required",
    }


@app.post("/token-research/chat", response_model=ChatResponse)
def token_research_chat(
    body: KickstartChatRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> ChatResponse:
    return _run_research_chat(run_token_research_agent, body, auth_wallet)


@app.get("/wallet-monitoring/health")
def wallet_monitoring_health() -> dict[str, Any]:
    return {
        "status": "ok",
        "agent": "Wallet Monitoring Agent",
        "model": WALLET_MONITORING_MODEL,
        "llm": llm_provider(),
        "llm_configured": llm_configured(),
        "auth_required": True,
        "data_source": "solana_rpc + jupiter",
        "metrics_cache_ttl_seconds": WALLET_SNAPSHOT_CACHE_TTL_SECONDS,
        "metrics_cache": get_wallet_monitoring_cache_stats(),
        "cluster": SOLANA_CLUSTER,
        "pricing": "free · wallet sign-in required",
    }


@app.post("/wallet-monitoring/chat", response_model=ChatResponse)
def wallet_monitoring_chat(
    body: KickstartChatRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> ChatResponse:
    return _run_research_chat(run_wallet_monitoring_agent, body, auth_wallet)


@app.get("/due-diligence/health")
def due_diligence_health() -> dict[str, Any]:
    return {
        "status": "ok",
        "agent": "Due Diligence Agent",
        "model": DUE_DILIGENCE_MODEL,
        "llm": llm_provider(),
        "llm_configured": llm_configured(),
        "auth_required": True,
        "data_source": "solana_rpc + jupiter + meteora_datapi",
        "easy_screener_configured": screener_configured(),
        "metrics_cache_ttl_seconds": TOKEN_RESEARCH_CACHE_TTL_SECONDS,
        "metrics_cache": get_due_diligence_cache_stats(),
        "cluster": SOLANA_CLUSTER,
        "pricing": "free · wallet sign-in required",
    }


@app.post("/due-diligence/chat", response_model=ChatResponse)
def due_diligence_chat(
    body: KickstartChatRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> ChatResponse:
    return _run_research_chat(run_due_diligence_agent, body, auth_wallet)


class HfPaperStrategyCreate(BaseModel):
    tokens: Optional[list[str]] = None
    name: str = ""
    mode: str = "agent"
    take_profit_pct: Optional[float] = 15.0
    stop_loss_pct: Optional[float] = 8.0
    capital_usd: Optional[float] = None
    notes: str = ""
    horizon_days: Optional[int] = None
    allocation_pct: Optional[dict[str, float]] = None
    trading_mode: str = "live"
    funding_token: str = "USDC"
    mint_overrides: Optional[dict[str, str]] = None
    max_names: Optional[int] = None


class HfPaperStrategyUpdate(BaseModel):
    take_profit_pct: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    tokens: Optional[list[str]] = None
    name: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    allocation_pct: Optional[dict[str, float]] = None
    horizon_days: Optional[int] = None
    add_capital_usd: Optional[float] = None


class HfPaperConfirmRequest(BaseModel):
    capital_usd: Optional[float] = None
    horizon_days: Optional[int] = None
    funding_token: Optional[str] = None
    mint_overrides: Optional[dict[str, str]] = None


class HfPaperBacktestRequest(BaseModel):
    period: str = "6m"
    strategy_id: Optional[str] = None
    tokens: Optional[list[str]] = None
    capital_usd: float = 100.0


class HfPaperAnalyzeRequest(BaseModel):
    symbol: str
    equity_usd: Optional[float] = None


@app.get("/hedge-fund/wallet/agent")
def hedge_fund_wallet_agent(_: None = Depends(require_internal_key)) -> dict[str, Any]:
    return get_hf_agent_wallet_info()


@app.get("/hedge-fund/wallet/balance")
def hedge_fund_wallet_balance(
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    return get_hf_user_balances(auth_wallet)


@app.post("/hedge-fund/wallet/deposit/verify")
def hedge_fund_deposit_verify(
    body: DepositVerifyRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    result = verify_and_record_hf_deposit(body.signature.strip(), auth_wallet)
    if result.get("error") and result.get("status") != "already_recorded":
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/hedge-fund/wallet/withdraw")
def hedge_fund_wallet_withdraw(
    body: WithdrawRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    result = withdraw_hf_tokens(auth_wallet, body.token.strip(), body.amount)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/hedge-fund/wallet/ledger")
def hedge_fund_wallet_ledger(
    auth_wallet: str = Depends(require_wallet_session),
    limit: int = Query(50, ge=1, le=100),
) -> dict[str, Any]:
    entries = list_hf_user_ledger(auth_wallet, limit=limit)
    return {"user_wallet": auth_wallet, "entries": entries, "count": len(entries)}


@app.get("/hedge-fund/health")
def hedge_fund_health() -> dict[str, Any]:
    return {
        "status": "ok",
        "agent": "Hedge Fund Agent",
        "model": HEDGE_FUND_MODEL,
        "trading_wallet_configured": bool(get_hf_wallet_pubkey()),
        "trading_wallet": get_hf_wallet_pubkey(),
        "llm": llm_provider(),
        "llm_configured": llm_configured(),
        "auth_required": True,
        "fee_model": "1/10",
        "management_fee_annual_pct": 1.0,
        "performance_fee_pct": 10.0,
        "cluster": SOLANA_CLUSTER,
        "pricing": "1% AUM + 10% performance (vs 2/20)",
        "governance": "Covenant 18-analyst deterministic (LLM optional)",
        "paper_trading": True,
        "live_trading": True,
        "deposits_required": True,
        "max_strategy_usdc": HF_MAX_STRATEGY_USDC,
        "min_horizon_days": HF_MIN_HORIZON_DAYS,
        "management_fee_on_start_pct": 1.0,
        "performance_fee_on_profit_pct": 10.0,
        "allowed_deposit_tokens": ["USDC"],
        "analysts": 18,
        "llm_required_for_trades": False,
        "monitor_interval_seconds": HF_MONITOR_INTERVAL_SECONDS,
        "scheduler": hf_scheduler_status(),
    }


@app.get("/hedge-fund/fees")
def hedge_fund_fees() -> dict[str, Any]:
    return get_fee_structure()


@app.post("/hedge-fund/chat", response_model=ChatResponse)
def hedge_fund_chat(
    body: KickstartChatRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> ChatResponse:
    return _run_research_chat(run_hedge_fund_agent, body, auth_wallet)


@app.get("/hedge-fund/paper/dashboard")
def hedge_fund_paper_dashboard(
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    return hf_paper_dashboard(auth_wallet)


@app.get("/hedge-fund/paper/strategies")
def hedge_fund_paper_strategies(
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    return {"strategies": hf_list_strategies(auth_wallet)}


@app.post("/hedge-fund/paper/strategies")
def hedge_fund_paper_create_strategy(
    body: HfPaperStrategyCreate,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    tokens = body.tokens
    created_by = "user" if tokens else "agent"
    mode = body.mode if body.mode in ("agent", "user", "hybrid") else ("user" if tokens else "agent")
    rules = {
        "take_profit_pct": body.take_profit_pct if body.take_profit_pct is not None else 15,
        "stop_loss_pct": body.stop_loss_pct if body.stop_loss_pct is not None else 8,
        "notes": body.notes or "",
        "objective": "max_profit",
    }
    return hf_create_strategy(
        user_wallet=auth_wallet,
        symbols=tokens,
        name=body.name or "",
        mode=mode,
        rules=rules,
        allocation_pct=body.allocation_pct,
        capital_usd=body.capital_usd,
        created_by=created_by,
        horizon_days=body.horizon_days,
        horizon_text=body.notes or "",
        trading_mode=body.trading_mode or "live",
        funding_token=body.funding_token or "USDC",
        mint_overrides=body.mint_overrides,
        max_names=body.max_names,
    )


@app.patch("/hedge-fund/paper/strategies/{strategy_id}")
def hedge_fund_paper_update_strategy(
    strategy_id: str,
    body: HfPaperStrategyUpdate,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    rules: dict[str, Any] = {}
    if body.take_profit_pct is not None:
        rules["take_profit_pct"] = body.take_profit_pct
    if body.stop_loss_pct is not None:
        rules["stop_loss_pct"] = body.stop_loss_pct
    if body.notes is not None:
        rules["notes"] = body.notes
    return hf_update_strategy_rules(
        strategy_id=strategy_id,
        user_wallet=auth_wallet,
        rules=rules or None,
        symbols=body.tokens,
        allocation_pct=body.allocation_pct,
        name=body.name,
        status=body.status,
        horizon_days=body.horizon_days,
        add_capital_usd=body.add_capital_usd,
    )


@app.post("/hedge-fund/paper/monitor")
def hedge_fund_paper_monitor(
    force: bool = Query(False),
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    # Auth-gated manual trigger (shared market refresh + all active strategies)
    _ = auth_wallet
    return hf_monitor_cycle(force_prices=force)


@app.post("/hedge-fund/paper/strategies/{strategy_id}/confirm")
def hedge_fund_paper_confirm_strategy(
    strategy_id: str,
    auth_wallet: str = Depends(require_wallet_session),
    body: HfPaperConfirmRequest = HfPaperConfirmRequest(),
) -> dict[str, Any]:
    return hf_confirm_strategy(
        strategy_id,
        auth_wallet,
        capital_usd=body.capital_usd,
        horizon_days=body.horizon_days,
        mint_overrides=body.mint_overrides,
        funding_token=body.funding_token,
    )


@app.get("/hedge-fund/paper/strategies/{strategy_id}/pnl")
def hedge_fund_paper_strategy_pnl(
    strategy_id: str,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    return hf_strategy_live_pnl(strategy_id, auth_wallet)


@app.get("/hedge-fund/paper/strategies/{strategy_id}/live-trades")
def hedge_fund_live_trades(
    strategy_id: str,
    auth_wallet: str = Depends(require_wallet_session),
    limit: int = Query(100, ge=1, le=200),
) -> dict[str, Any]:
    strategy = next((s for s in hf_list_strategies(auth_wallet) if s.get("id") == strategy_id), None)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    trades = hf_list_live_trades(strategy_id, limit=limit)
    return {
        "strategy_id": strategy_id,
        "trading_mode": strategy.get("trading_mode") or (strategy.get("rules") or {}).get("trading_mode"),
        "trades": trades,
        "count": len(trades),
    }


@app.post("/hedge-fund/paper/strategies/{strategy_id}/liquidate")
def hedge_fund_paper_liquidate(
    strategy_id: str,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    return hf_liquidate_strategy(strategy_id, auth_wallet)


class HfRetryDeployBody(BaseModel):
    replace: Optional[dict[str, str]] = None
    mint_overrides: Optional[dict[str, str]] = None


@app.post("/hedge-fund/paper/strategies/{strategy_id}/retry")
def hedge_fund_paper_retry(
    strategy_id: str,
    body: Optional[HfRetryDeployBody] = None,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    body = body or HfRetryDeployBody()
    return hf_retry_strategy_deploy(strategy_id, auth_wallet, replace=body.replace, mint_overrides=body.mint_overrides)


@app.post("/hedge-fund/paper/strategies/{strategy_id}/dismiss")
def hedge_fund_paper_dismiss(
    strategy_id: str,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    result = hf_dismiss_strategy(strategy_id, auth_wallet)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/hedge-fund/paper/strategies/{strategy_id}/add-capital")
def hedge_fund_paper_add_capital(
    strategy_id: str,
    body: HfPaperConfirmRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    if body.capital_usd is None:
        return {"error": "capital_usd required"}
    return hf_add_capital(strategy_id, auth_wallet, float(body.capital_usd))


@app.post("/hedge-fund/paper/analyze")
def hedge_fund_paper_analyze(
    body: HfPaperAnalyzeRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    _ = auth_wallet
    return hf_analyze_live_asset(body.symbol, equity_usd=body.equity_usd or HF_MAX_STRATEGY_USDC)


@app.post("/hedge-fund/paper/backtest")
def hedge_fund_paper_backtest(
    body: HfPaperBacktestRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    return hf_run_strategy_backtest(
        user_wallet=auth_wallet,
        period=body.period,
        strategy_id=body.strategy_id,
        symbols=body.tokens,
        capital_usd=min(float(body.capital_usd or HF_MAX_STRATEGY_USDC), HF_MAX_STRATEGY_USDC),
    )


@app.get("/hedge-fund/paper/scheduler")
def hedge_fund_paper_scheduler() -> dict[str, Any]:
    return hf_scheduler_status()


if __name__ == "__main__":
    import uvicorn

    print(f"Starting BIT Agents API on http://{API_HOST}:{API_PORT}")
    uvicorn.run(app, host=API_HOST, port=API_PORT)
