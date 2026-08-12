"""
The actual Ruqa-aligned piece: recurring DCA execution as a function Vercel
Cron invokes on a schedule, not a background thread inside a persistent
server. Each invocation is independent -- it claims whatever's due right
now (via the same SELECT ... FOR UPDATE SKIP LOCKED pattern proven safe
under concurrency earlier), executes it, and exits. Nothing persists
between invocations except the database rows themselves.

This matters for exactly the scenario this whole exercise is about:
Vercel can and does invoke a cron trigger more than once concurrently
(overlapping runs, retries) -- claim_due_dca_plans is what makes that safe
regardless, the same guarantee already proven for the multi-instance
server case.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "agent" / "new"))

from fastapi import FastAPI, Header, HTTPException
import os

import dca_multiwallet
from db import claim_due_dca_plans

app = FastAPI()

CRON_SECRET = os.environ.get("CRON_SECRET", "")


@app.get("/api/cron/tick")
def tick(authorization: str = Header(default=None)) -> dict:
    # Vercel Cron sends this header automatically when CRON_SECRET is set on
    # the project -- rejects anyone else from triggering real executions by
    # hitting this URL directly.
    if CRON_SECRET and authorization != f"Bearer {CRON_SECRET}":
        raise HTTPException(status_code=401, detail="Unauthorized")

    results = []
    for plan in claim_due_dca_plans():
        if plan.get("wallet_mode") != "multiwallet":
            continue  # pooled-mode plans are handled by the existing Render scheduler, not here
        result = dca_multiwallet.execute_plan_now(plan["id"])
        results.append({"plan_id": plan["id"], "result": result})

    return {"claimed_and_executed": len(results), "results": results}
