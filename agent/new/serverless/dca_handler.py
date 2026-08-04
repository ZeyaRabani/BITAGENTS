"""
HTTP entry point for the stateless DCA executor — what actually gets deployed
as the serverless function. A tiny FastAPI app with exactly one route, so it
can run locally with uvicorn for testing, or be adapted to Vercel's Python
function runtime later with no change to the underlying logic.

Local run:
  cd agent/new/serverless && python3 -m uvicorn dca_handler:app --port 8766
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from dca_execute import execute_dca_buy_stateless

app = FastAPI(title="DCA Stateless Executor (prototype)")


class BuyRequest(BaseModel):
    token: str = Field(min_length=1)
    amount_sol: float = Field(gt=0)
    slippage_bps: int = Field(default=100, ge=1, le=5000)


@app.post("/execute")
def execute(body: BuyRequest) -> dict:
    return execute_dca_buy_stateless(body.token, body.amount_sol, body.slippage_bps)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "stateless": True, "db_calls": 0}
