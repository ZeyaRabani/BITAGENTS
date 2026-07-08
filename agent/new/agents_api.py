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
from custom_agent import CUSTOM_AGENT_DEFAULT_MODEL, run_custom_agent
from db import (
    append_chat_messages,
    assert_chat_session_access,
    create_user_agent,
    db_configured,
    delete_chat_session,
    delete_user_agent,
    get_platform_metrics,
    get_user_agent,
    init_db,
    list_user_agents,
    list_watchlist,
    load_chat_history,
)
from dca_agent import (
    JUPITER_BUILD_API,
    MODEL,
    OPEN_ROUTER_API,
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
    update_dca_plan_status,
)
from easya_screener_client import CACHE_TTL_SECONDS, screener_configured
from kickstart_copilot_agent import (
    KICKSTART_MODEL,
    list_verified_kickstart_tokens,
    run_kickstart_agent,
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

API_HOST = os.environ.get(
    "AGENTS_API_HOST",
    os.environ.get("DCA_API_HOST", "127.0.0.1"),
)
API_PORT = int(
    os.environ.get(
        "AGENTS_API_PORT",
        os.environ.get("DCA_API_PORT", "8765"),
    )
)

app = FastAPI(title="BIT Agents API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
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


class CreateCustomAgentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: Optional[str] = Field(default=None, max_length=280)
    system_prompt: str = Field(min_length=1, max_length=4000)
    model: Optional[str] = None


class CustomAgentChatRequest(BaseModel):
    message: str = Field(min_length=1)
    history: Optional[list[dict[str, str]]] = None


class CustomAgentChatResponse(BaseModel):
    reply: str


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
    print("  🤖 Agents: DCA, Kickstart Token Copilot")


@app.get("/health")
def health() -> dict[str, Any]:
    wallet = get_wallet_pubkey()
    agent_info = get_agent_wallet_info()
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
                "pricing": "free",
            },
        },
        "llm": "openrouter",
        "dca_model": MODEL,
        "kickstart_model": KICKSTART_MODEL,
        "openrouter_configured": bool(OPEN_ROUTER_API),
        "database": "neon_postgres" if db_configured() else "unconfigured",
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


@app.get("/kickstart/health")
def kickstart_health() -> dict[str, Any]:
    return {
        "status": "ok",
        "agent": "EasyA Analysis Agent",
        "model": KICKSTART_MODEL,
        "pricing": "free",
        "auth_required": True,
        "data_source": "easy_screener",
        "easy_screener_configured": screener_configured(),
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
        "openrouter_configured": bool(OPEN_ROUTER_API),
        "cluster": SOLANA_CLUSTER,
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
            detail="Cannot reach OpenRouter API. Check your network connection.",
        ) from exc
    except requests.exceptions.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"OpenRouter error: {exc}") from exc
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
        )
    except requests.exceptions.ConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail="Cannot reach OpenRouter API. Check your network connection.",
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


# ─── Custom (user-created) agents ──────────────────────────────────────────────

@app.post("/custom/agents", response_model=None)
def create_custom_agent(
    body: CreateCustomAgentRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    result = create_user_agent(
        auth_wallet,
        body.name,
        body.description,
        body.system_prompt,
        body.model,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/custom/agents")
def list_custom_agents(
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    return list_user_agents(auth_wallet)


@app.get("/custom/agents/{agent_id}")
def get_custom_agent(
    agent_id: str,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, Any]:
    agent = get_user_agent(agent_id)
    if not agent or agent["owner_wallet"] != auth_wallet:
        raise HTTPException(status_code=404, detail="Agent not found.")
    return agent


@app.delete("/custom/agents/{agent_id}")
def remove_custom_agent(
    agent_id: str,
    auth_wallet: str = Depends(require_wallet_session),
) -> dict[str, bool]:
    deleted = delete_user_agent(agent_id, auth_wallet)
    if not deleted:
        raise HTTPException(status_code=404, detail="Agent not found.")
    return {"ok": True}


@app.post("/custom/agents/{agent_id}/chat", response_model=CustomAgentChatResponse)
def custom_agent_chat(
    agent_id: str,
    body: CustomAgentChatRequest,
    auth_wallet: str = Depends(require_wallet_session),
) -> CustomAgentChatResponse:
    agent = get_user_agent(agent_id)
    if not agent or agent["owner_wallet"] != auth_wallet:
        raise HTTPException(status_code=404, detail="Agent not found.")

    try:
        reply = run_custom_agent(
            agent["system_prompt"],
            body.message,
            body.history,
            model=agent.get("model") or CUSTOM_AGENT_DEFAULT_MODEL,
        )
    except requests.exceptions.ConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail="Cannot reach OpenRouter API. Check your network connection.",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return CustomAgentChatResponse(reply=reply)


if __name__ == "__main__":
    import uvicorn

    print(f"Starting BIT Agents API on http://{API_HOST}:{API_PORT}")
    uvicorn.run(app, host=API_HOST, port=API_PORT)
