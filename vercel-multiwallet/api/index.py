"""
Multi-wallet DCA — real Vercel serverless deployment.

Deliberately NOT a lift-and-shift of agents_api.py. That app starts
in-process background threads at startup (the DCA/Volume schedulers), which
has no meaning in a serverless function, since there's no persistent
process for a thread to run in between invocations. This is the actual
architectural point of the whole exercise: this file has zero background
threads, zero startup-time state. Every request is a fresh, independent
invocation. The recurring-execution side lives in api/cron/tick.py instead,
triggered by Vercel Cron, not a thread.

Two route surfaces are exposed:
  - /api/multi-wallet/dca/*: the original minimal REST surface (used by
    the standalone MultiWalletDcaConsole page).
  - Everything else (/api/chat, /api/wallet/*, /api/plans/*, /api/auth/*):
    the SAME path shape the pooled DCA agent's frontend (DcaAgentConsole /
    DcaAgentDeposit / DcaPlanPanel) already calls, so that UI can be reused
    here completely unmodified, pointed at this backend instead. Same
    shape, different implementation underneath: every mutating call goes
    through dca_multiwallet, which reads/writes each user's own derived
    wallet on-chain instead of the pooled agent wallet.

Only the DCA agent is exposed here, not the other 14 agents. This is
scoped deliberately so this stays something that can actually be reasoned
about end-to-end, not a partial port of a much larger app.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

# The actual agent code (agent_wallets.py, dca_multiwallet.py, dca_agent.py,
# db.py, etc.) is bundled alongside this function via vercel.json's
# includeFiles, at agent/new relative to the repo root, reused as-is, not
# rewritten, since it's already tested.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent" / "new"))

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import agent_wallets
import dca_multiwallet
from dca_agent import (
    MODEL,
    SOLANA_CLUSTER,
    get_dca_history,
    get_dca_plan,
    list_dca_plans,
    resolve_token,
    run_agent_with_actions,
    sol_rpc,
    update_dca_plan_status,
)
from db import append_chat_messages, assert_chat_session_access, load_chat_history
from deposit_ledger import get_user_dca_executions, list_user_ledger_history
from wallet_auth import (
    create_auth_challenge,
    get_session_info,
    resolve_session_token,
    verify_auth_challenge,
)

app = FastAPI(title="BIT Agents — Multi-wallet DCA (serverless)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("CORS_ALLOW_ORIGINS", "*").split(",") if o.strip()] or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def require_wallet_session(authorization: str = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Wallet sign-in required.")
    token = authorization.removeprefix("Bearer ").strip()
    wallet = resolve_session_token(token)
    if not wallet:
        raise HTTPException(status_code=401, detail="Invalid or expired session. Sign in again.")
    return wallet


# ─── Health / auth ──────────────────────────────────────────────────────────

@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "deployment": "vercel-serverless",
        "cluster": SOLANA_CLUSTER,
        "wallet": None,
        "wallet_configured": True,
        "multi_wallet_configured": agent_wallets.multi_wallet_configured(),
        "dca_model": MODEL,
        "llm_configured": True,
        "agent_wallet": None,
        "any_spl_token": True,
        "common_tokens": ["SOL", "USDC", "JUP", "BONK"],
    }


@app.get("/api/auth/challenge")
def auth_challenge(user_wallet: str = Query(..., min_length=32)) -> dict[str, Any]:
    result = create_auth_challenge(user_wallet.strip())
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


class AuthVerifyRequest(BaseModel):
    user_wallet: str = Field(min_length=32)
    message: str = Field(min_length=8)
    signature: str = Field(min_length=32)


@app.post("/api/auth/verify")
def auth_verify(body: AuthVerifyRequest) -> dict[str, Any]:
    result = verify_auth_challenge(body.user_wallet.strip(), body.message, body.signature.strip())
    if "error" in result:
        raise HTTPException(status_code=401, detail=result["error"])
    return result


@app.get("/api/auth/me")
def auth_me(authorization: Optional[str] = Header(default=None)) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing session token.")
    info = get_session_info(authorization.removeprefix("Bearer ").strip())
    if not info:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")
    return info


# ─── Chat (LLM, deterministic-first — see dca_agent.py's anti-hallucination
#     parser and _multiwallet_tool_overrides) ───────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: Optional[str] = None


@app.post("/api/chat")
def chat(body: ChatRequest, auth_wallet: str = Depends(require_wallet_session)) -> dict[str, Any]:
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
            wallet_mode="multiwallet",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    append_chat_messages(session_id, user_message, reply, actions, user_wallet=auth_wallet)
    return {"reply": reply, "session_id": session_id, "actions": actions}


# ─── Wallet (pooled-shaped, multi-wallet-backed) ───────────────────────────

def _balance_payload(auth_wallet: str) -> dict[str, Any]:
    plans = list_dca_plans(user_wallet=auth_wallet).get("plans") or []
    extra_tokens = sorted({p["output_mint"] for p in plans if p.get("output_mint")})
    raw = dca_multiwallet.get_balances(auth_wallet, extra_tokens=extra_tokens)
    rows = []
    for b in raw.get("balances", []):
        bal = float(b.get("balance") or 0)
        rows.append({
            "token": b.get("token"),
            "mint": b.get("mint"),
            "deposited": bal,
            "acquired_from_dca": 0,
            "withdrawn": 0,
            "reserved_for_plans": 0,
            "spent_in_plans": 0,
            "available": bal,
            "withdrawable": bal,
        })
    return {"user_wallet": auth_wallet, "agent_wallet": raw.get("deposit_address"), "balances": rows}


@app.get("/api/wallet/agent")
def wallet_agent(auth_wallet: str = Depends(require_wallet_session)) -> dict[str, Any]:
    # No single shared deposit address here (unlike the pooled agent):
    # every signed-in user gets their own, so this route requires auth.
    return {
        "agent_wallet": dca_multiwallet.get_deposit_address(auth_wallet),
        "configured": agent_wallets.multi_wallet_configured(),
        "any_spl_token": True,
        "common_tokens": ["SOL", "USDC", "JUP", "BONK"],
    }


@app.get("/api/wallet/balance")
def wallet_balance(auth_wallet: str = Depends(require_wallet_session)) -> dict[str, Any]:
    return _balance_payload(auth_wallet)


class DepositVerifyRequest(BaseModel):
    signature: str = Field(min_length=32)


@app.post("/api/wallet/deposit/verify")
def wallet_deposit_verify(
    body: DepositVerifyRequest, auth_wallet: str = Depends(require_wallet_session)
) -> dict[str, Any]:
    # Multi-wallet balances are read live on-chain, not credited to a ledger,
    # so "verifying" a deposit here just confirms the transfer landed and
    # hands back the now-current balance, instead of writing a deposit row.
    tx = sol_rpc(
        "getTransaction",
        [body.signature.strip(), {"commitment": "confirmed", "maxSupportedTransactionVersion": 0}],
    )
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found yet. Wait for confirmation and try again.")
    return {
        "status": "verified",
        "message": "Deposit confirmed on-chain.",
        "balances": _balance_payload(auth_wallet),
    }


class WithdrawRequest(BaseModel):
    token: str = Field(min_length=1)
    amount: float = Field(gt=0)


@app.post("/api/wallet/withdraw")
def wallet_withdraw(body: WithdrawRequest, auth_wallet: str = Depends(require_wallet_session)) -> dict[str, Any]:
    result = dca_multiwallet.withdraw(auth_wallet, body.token.strip(), float(body.amount))
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    result["balances"] = _balance_payload(auth_wallet)
    return result


@app.get("/api/wallet/ledger")
def wallet_ledger(auth_wallet: str = Depends(require_wallet_session), limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    return list_user_ledger_history(auth_wallet, limit)


@app.get("/api/wallet/dca-executions")
def wallet_dca_executions(
    auth_wallet: str = Depends(require_wallet_session), limit: int = Query(100, ge=1, le=200)
) -> dict[str, Any]:
    return get_user_dca_executions(auth_wallet, limit)


@app.get("/api/tokens/resolve")
def resolve_token_info(query: str = Query(..., min_length=2)) -> dict[str, Any]:
    result = resolve_token(query.strip())
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {
        "symbol": result["symbol"],
        "mint": result["mint"],
        "decimals": result["decimals"],
        "name": result.get("name"),
    }


# ─── Plans (pooled-shaped) ──────────────────────────────────────────────────

@app.get("/api/plans")
def plans(
    auth_wallet: str = Depends(require_wallet_session),
    active_only: bool = Query(False),
    status: Optional[str] = Query(None),
) -> dict[str, Any]:
    result = list_dca_plans(status=status, user_wallet=auth_wallet, active_only=active_only)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/api/plans/{plan_id}")
def plan_detail(plan_id: str, auth_wallet: str = Depends(require_wallet_session)) -> dict[str, Any]:
    result = get_dca_plan(plan_id, user_wallet=auth_wallet)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/api/plans/{plan_id}/executions")
def plan_executions(plan_id: str, auth_wallet: str = Depends(require_wallet_session)) -> dict[str, Any]:
    result = get_dca_history(plan_id, user_wallet=auth_wallet)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


class PlanStatusRequest(BaseModel):
    action: str = Field(min_length=1)


@app.post("/api/plans/{plan_id}/status")
def plan_status(
    plan_id: str, body: PlanStatusRequest, auth_wallet: str = Depends(require_wallet_session)
) -> dict[str, Any]:
    result = update_dca_plan_status(plan_id, body.action.strip(), user_wallet=auth_wallet)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ─── Original minimal multi-wallet REST surface (MultiWalletDcaConsole) ────

class CreatePlanRequest(BaseModel):
    output_token: str = Field(min_length=1)
    amount_per_buy: float = Field(gt=0)
    interval: str = Field(min_length=1)
    max_executions: int = Field(gt=0)


@app.get("/api/multi-wallet/dca/balance")
def multi_wallet_balance(auth_wallet: str = Depends(require_wallet_session)) -> dict[str, Any]:
    return dca_multiwallet.get_balances(auth_wallet)


@app.post("/api/multi-wallet/dca/plan")
def multi_wallet_create_plan(
    body: CreatePlanRequest, auth_wallet: str = Depends(require_wallet_session)
) -> dict[str, Any]:
    result = dca_multiwallet.create_plan(
        auth_wallet, body.output_token, body.amount_per_buy, body.interval, body.max_executions
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/api/multi-wallet/dca/plans")
def multi_wallet_plans(auth_wallet: str = Depends(require_wallet_session)) -> dict[str, Any]:
    return list_dca_plans(user_wallet=auth_wallet)


class MultiWalletWithdrawRequest(BaseModel):
    token: str = Field(min_length=1)
    amount: float = Field(gt=0)


@app.post("/api/multi-wallet/dca/withdraw")
def multi_wallet_withdraw(
    body: MultiWalletWithdrawRequest, auth_wallet: str = Depends(require_wallet_session)
) -> dict[str, Any]:
    result = dca_multiwallet.withdraw(auth_wallet, body.token.strip(), float(body.amount))
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result
