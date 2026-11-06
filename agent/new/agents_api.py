"""
BIT Agents API.

Live agents: DCA, Hedge Fund, and Sniper. Each Jupiter swap is simulated on Aomi
before that agent's Circle wallet signs. Chat uses OpenRouter.

Run locally:
  cd agent/new
  python agents_api.py

Default: http://127.0.0.1:8765
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit, urlunsplit

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

import requests
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from aomi_pipeline import aomi_configured
from circle_dca_wallets import circle_dca_enabled
from db import (
    append_chat_messages,
    assert_chat_session_access,
    db_configured,
    delete_chat_session,
    get_custom_instructions,
    get_platform_metrics,
    init_db,
    load_chat_history,
    save_custom_instructions,
)
from dca_agent import (
    DCA_LLM_PROVIDER,
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
from market_agents import AGENTS, run_market_agent, wallet_status
from deposit_ledger import (
    get_agent_wallet_info,
    get_user_balances,
    get_user_dca_executions,
    list_user_deposits,
    list_user_ledger_history,
    verify_and_record_deposit,
    withdraw_user_tokens,
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
    if os.environ.get("PORT"):
        return "0.0.0.0"
    return "127.0.0.1"


def _resolve_api_port() -> int:
    if os.environ.get("PORT"):
        return int(os.environ["PORT"])
    return int(os.environ.get("AGENTS_API_PORT", os.environ.get("DCA_API_PORT", "8765")))


def _cors_allow_origins() -> list[str]:
    defaults = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    raw = (os.environ.get("CORS_ALLOW_ORIGINS") or "").strip()
    if not raw:
        return defaults
    extra = [origin.strip() for origin in raw.split(",") if origin.strip()]
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


_MAINTENANCE_START_UTC = datetime(2026, 9, 10, 7, 30, 0, tzinfo=timezone.utc)
_MAINTENANCE_END_UTC = datetime(2026, 9, 10, 10, 0, 0, tzinfo=timezone.utc)
_MAINTENANCE_ALLOW_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}


def _maintenance_active() -> bool:
    if os.environ.get("MAINTENANCE_FORCE", "").strip() in ("1", "true", "True", "yes"):
        return True
    now = datetime.now(timezone.utc)
    return _MAINTENANCE_START_UTC <= now < _MAINTENANCE_END_UTC


@app.middleware("http")
async def maintenance_gate(request, call_next):
    path = request.url.path or "/"
    if _maintenance_active() and path not in _MAINTENANCE_ALLOW_PATHS:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=503,
            content={
                "error": (
                    "BIT Agents is under scheduled maintenance "
                    "(1:00-3:30 PM IST, 10 Sep 2026). Please try again shortly."
                ),
                "maintenance": True,
                "until_ist": "2026-09-10T15:30:00+05:30",
            },
            headers={"Retry-After": "9000"},
        )
    return await call_next(request)


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


class CustomInstructionsRequest(BaseModel):
    agent_type: str = Field(min_length=1, max_length=32)
    instructions: str = Field(max_length=10000)


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
    print("  database ready")
    if internal_api_configured():
        print("  internal API key enabled")
    else:
        print("  AGENTS_INTERNAL_API_KEY not set (optional for local dev)")
    if start_scheduler():
        print(f"  DCA scheduler started (every {SCHEDULER_POLL_SECONDS}s)")
    if start_metrics_scheduler():
        print("  platform metrics scheduler started")
    print(f"  live agents: DCA, Hedge Fund, Sniper via {DCA_LLM_PROVIDER} ({MODEL})")


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "agents": {
            "dca": {
                "path_prefix": "/",
                "chat": "/chat",
                "llm": DCA_LLM_PROVIDER,
                "model": MODEL,
                "execution": "jupiter build, aomi simulate, circle sign",
            },
            "hedge-fund": {
                "chat": "/hedge-fund/chat",
                "wallet": "/hedge-fund/wallet",
                "llm": DCA_LLM_PROVIDER,
                "model": MODEL,
                "execution": "jupiter build, aomi simulate, circle sign",
            },
            "sniper": {
                "chat": "/sniper/chat",
                "wallet": "/sniper/wallet",
                "llm": DCA_LLM_PROVIDER,
                "model": MODEL,
                "execution": "jupiter build, aomi simulate, circle sign",
            },
        },
        "aomi_configured": aomi_configured(),
        "database": "neon_postgres" if db_configured() else "unconfigured",
        "auth": "wallet_signature",
        "internal_api_key_required": internal_api_configured(),
        "model": MODEL,
        "llm": DCA_LLM_PROVIDER,
        "llm_configured": True,
        "cluster": SOLANA_CLUSTER,
        "rpc": _redact_rpc_url(SOLANA_RPC),
        "wallet": get_wallet_pubkey(),
        "wallet_configured": bool(get_wallet_pubkey()),
        "circle_configured": circle_dca_enabled(),
    }


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
def wallet_agent(auth_wallet: str = Depends(require_wallet_session)) -> dict[str, Any]:
    return get_agent_wallet_info(auth_wallet)


@app.get("/wallet/balance")
def wallet_balance(auth_wallet: str = Depends(require_wallet_session)) -> dict[str, Any]:
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
        status = 403 if result.get("status") == "rejected" else 400
        raise HTTPException(status_code=status, detail=result["error"])
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
def get_plan(plan_id: str, auth_wallet: str = Depends(require_wallet_session)) -> dict[str, Any]:
    result = get_dca_plan(plan_id, user_wallet=auth_wallet)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/plans/{plan_id}/executions")
def plan_executions(plan_id: str, auth_wallet: str = Depends(require_wallet_session)) -> dict[str, Any]:
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
        raise HTTPException(status_code=503, detail="Cannot reach OpenRouter.") from exc
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
    return {"ok": delete_chat_session(session_id)}


def _market_chat(slug: str, body: ChatRequest, auth_wallet: str) -> ChatResponse:
    if slug not in AGENTS:
        raise HTTPException(status_code=404, detail="Unknown agent.")
    session_id = body.session_id or str(uuid.uuid4())
    access_error = assert_chat_session_access(session_id, auth_wallet)
    if access_error:
        raise HTTPException(status_code=403, detail=access_error)
    history = load_chat_history(session_id)
    user_message = body.message.strip()
    try:
        reply, _history, actions = run_market_agent(
            slug,
            user_message,
            history,
            user_wallet=auth_wallet,
            session_id=session_id,
        )
    except requests.exceptions.ConnectionError as exc:
        raise HTTPException(status_code=503, detail="Cannot reach OpenRouter.") from exc
    except requests.exceptions.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"LLM error: {exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    append_chat_messages(session_id, user_message, reply, actions, user_wallet=auth_wallet)
    return ChatResponse(reply=reply, session_id=session_id, actions=actions)


@app.get("/hedge-fund/health")
def hedge_fund_health() -> dict[str, Any]:
    return {"status": "ok", "agent": "hedge-fund", "model": MODEL, "cluster": SOLANA_CLUSTER, "execution": "aomi"}


@app.get("/hedge-fund/wallet")
def hedge_fund_wallet(auth_wallet: str = Depends(require_wallet_session)) -> dict[str, Any]:
    return wallet_status("hedge-fund", auth_wallet)


@app.post("/hedge-fund/chat", response_model=ChatResponse)
def hedge_fund_chat(
    body: ChatRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> ChatResponse:
    return _market_chat("hedge-fund", body, auth_wallet)


@app.get("/sniper/health")
def sniper_health() -> dict[str, Any]:
    return {"status": "ok", "agent": "sniper", "model": MODEL, "cluster": SOLANA_CLUSTER, "execution": "aomi"}


@app.get("/sniper/wallet")
def sniper_wallet(auth_wallet: str = Depends(require_wallet_session)) -> dict[str, Any]:
    return wallet_status("sniper", auth_wallet)


@app.post("/sniper/chat", response_model=ChatResponse)
def sniper_chat(
    body: ChatRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> ChatResponse:
    return _market_chat("sniper", body, auth_wallet)


@app.get("/v1/custom-instructions/{agent_type}")
def get_user_custom_instructions(
    agent_type: str,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    instructions = get_custom_instructions(auth_wallet, agent_type)
    return {"agent_type": agent_type, "instructions": instructions or ""}


@app.post("/v1/custom-instructions")
def save_user_custom_instructions(
    req: CustomInstructionsRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    result = save_custom_instructions(auth_wallet, req.agent_type, req.instructions)
    return {
        "success": True,
        "agent_type": req.agent_type,
        "instructions": result.get("instructions", ""),
    }


if __name__ == "__main__":
    import uvicorn

    print(f"Starting BIT Agents API on http://{API_HOST}:{API_PORT}")
    uvicorn.run(app, host=API_HOST, port=API_PORT)
