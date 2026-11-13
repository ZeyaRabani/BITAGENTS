"""Local UX evidence harness. Real strategy adapter; fixture DB, balances and swaps.

Never mounted by agents_api.py. Never loads a live wallet or starts its schedulers.
"""
import copy
import sys
from pathlib import Path
from unittest.mock import patch

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent/new"))
import dca_agent
import deposit_ledger
from strategy_api import DcaStrategy, create_strategy_router

HERE = Path(__file__).resolve().parent
plans = {}
wallet = "preview-user"


def insert(plan):
    plans[plan["id"]] = copy.deepcopy(plan)


def update(plan_id, values):
    plans[plan_id].update(values)
    return copy.deepcopy(plans[plan_id])


def swap(input_token, output_token, amount, *args, dry_run=False, **kwargs):
    if dry_run:
        return {"status": "dry_run", "fixture": True, "input_amount": amount,
                "estimated_output": round(amount / 150, 6), "price_source": "Fixed preview price: 150 USDC/SOL"}
    return {"status": "success", "fixture": True, "input_amount": amount,
            "output_amount": round(amount / 150, 6), "receipt": "LOCAL-FIXTURE-NOT-ONCHAIN"}


PATCHES = [
    patch.object(dca_agent, "_insert_plan_db", side_effect=insert),
    patch.object(dca_agent, "_find_plan_db", side_effect=lambda p: copy.deepcopy(plans.get(p))),
    patch.object(dca_agent, "_update_plan_db", side_effect=update),
    patch.object(dca_agent, "load_all_plans", side_effect=lambda w: [copy.deepcopy(p) for p in plans.values() if p["user_wallet"] == w]),
    patch.object(dca_agent, "resolve_token", side_effect=lambda s: dict(symbol=s, mint=s + "-fixture-mint", decimals=6 if s == "USDC" else 9)),
    patch.object(dca_agent, "get_wallet_pubkey", return_value="fixture-wallet"),
    patch.object(dca_agent, "execute_swap_buy", side_effect=swap),
    patch.object(deposit_ledger, "check_plan_budget", return_value={}),
    patch.object(deposit_ledger, "get_user_balances", return_value={"balances": [{"token": "USDC", "available": 1000}]}),
    patch.object(deposit_ledger, "check_user_can_spend_dca", return_value={}),
    patch.object(deposit_ledger, "record_dca_platform_fee", return_value={"fee": 0.125}),
]
for item in PATCHES:
    item.start()


def auth(authorization: str | None = Header(default=None)):
    if authorization != "Bearer local-preview":
        raise HTTPException(401, "Local preview session required")
    return wallet


app = FastAPI(title="BIT Agents local experience preview")
app.include_router(create_strategy_router(auth, {"dca": DcaStrategy(dca_agent)}))


@app.get("/")
def index():
    return FileResponse(HERE / "index.html")


@app.get("/bit-agents-logo-transparent.png")
def logo():
    return FileResponse(ROOT / "frontend/public/bit-agents-logo-transparent.png")


@app.get("/preview.js")
def script():
    return FileResponse(HERE / "dist/preview.js", media_type="application/javascript")


@app.post("/demo/tick/{plan_id}")
def tick(plan_id: str, owner: str = Depends(auth)):
    # Test-only time advance: exercise the real run/accounting function with
    # a fixture swap. This endpoint cannot submit an on-chain transaction.
    owned = dca_agent._assert_plan_owner(plan_id, owner)
    if "error" in owned:
        raise HTTPException(404, "Plan not found")
    return dca_agent._run_plan_execution(plan_id)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8766)
