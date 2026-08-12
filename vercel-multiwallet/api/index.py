"""
Multi-wallet DCA — real Vercel serverless deployment.

Deliberately NOT a lift-and-shift of agents_api.py. That app starts
in-process background threads at startup (the DCA/Volume schedulers) --
which has no meaning in a serverless function, since there's no persistent
process for a thread to run in between invocations. This is the actual
architectural point of the whole exercise: this file has zero background
threads, zero startup-time state. Every request is a fresh, independent
invocation. The recurring-execution side lives in api/cron/tick.py instead,
triggered by Vercel Cron, not a thread.

Only the multi-wallet DCA feature is exposed here, not the other 14 agents --
scoped deliberately so this stays something that can actually be reasoned
about end-to-end, not a partial port of a much larger app.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# The actual agent code (agent_wallets.py, dca_multiwallet.py, db.py, etc.)
# is bundled alongside this function via vercel.json's includeFiles, at
# agent/new relative to the repo root -- reused as-is, not rewritten, since
# it's already tested.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent" / "new"))

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import agent_wallets
import dca_multiwallet
from dca_agent import SOLANA_CLUSTER
from wallet_auth import create_auth_challenge, resolve_session_token, verify_auth_challenge

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


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "deployment": "vercel-serverless",
        "cluster": SOLANA_CLUSTER,
        "multi_wallet_configured": agent_wallets.multi_wallet_configured(),
    }


@app.get("/api/auth/challenge")
def auth_challenge(user_wallet: str = Query(...)) -> dict[str, Any]:
    result = create_auth_challenge(user_wallet)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


class AuthVerifyRequest(BaseModel):
    user_wallet: str = Field(min_length=32)
    message: str = Field(min_length=8)
    signature: str = Field(min_length=32)


@app.post("/api/auth/verify")
def auth_verify(body: AuthVerifyRequest) -> dict[str, Any]:
    result = verify_auth_challenge(body.user_wallet.strip(), body.message, body.signature)
    if "error" in result:
        raise HTTPException(status_code=401, detail=result["error"])
    return result


@app.get("/api/multi-wallet/dca/balance")
def balance(auth_wallet: str = Depends(require_wallet_session)) -> dict[str, Any]:
    return dca_multiwallet.get_balances(auth_wallet)


class CreatePlanRequest(BaseModel):
    output_token: str = Field(min_length=1)
    amount_per_buy: float = Field(gt=0)
    interval: str = Field(min_length=1)
    max_executions: int = Field(gt=0)


@app.post("/api/multi-wallet/dca/plan")
def create_plan(
    body: CreatePlanRequest, auth_wallet: str = Depends(require_wallet_session)
) -> dict[str, Any]:
    result = dca_multiwallet.create_plan(
        auth_wallet, body.output_token, body.amount_per_buy, body.interval, body.max_executions
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/api/multi-wallet/dca/plans")
def plans(auth_wallet: str = Depends(require_wallet_session)) -> dict[str, Any]:
    from dca_agent import list_dca_plans

    return list_dca_plans(user_wallet=auth_wallet)


class WithdrawRequest(BaseModel):
    token: str = Field(min_length=1)
    amount: float = Field(gt=0)


@app.post("/api/multi-wallet/dca/withdraw")
def withdraw(
    body: WithdrawRequest, auth_wallet: str = Depends(require_wallet_session)
) -> dict[str, Any]:
    result = dca_multiwallet.withdraw(auth_wallet, body.token.strip(), float(body.amount))
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result
