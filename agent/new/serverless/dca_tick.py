"""
The honest part of Ruqa's proposal: SOMETHING has to remember when each
plan's next buy is due between invocations — you can't have zero state for
a recurring job, only much less of it than a full relational database.

This is that minimum: a flat JSON file of {token, amount_sol, interval_seconds,
next_run_at} rows. Locally it's a file; in production this is exactly the
shape of a Vercel KV / Upstash Redis entry, not a Postgres table with a
connection pool and an in-process scheduler thread.

A real deployment would have Vercel Cron hit this on a fixed tick (e.g. every
minute) instead of running it as a loop. This file simulates that tick loop
locally so it can be tested without deploying anything.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from dca_execute import execute_dca_buy_stateless

STATE_FILE = Path(__file__).resolve().parent / "local_plan_state.json"


def load_plans() -> list[dict[str, Any]]:
    if not STATE_FILE.exists():
        return []
    return json.loads(STATE_FILE.read_text())


def save_plans(plans: list[dict[str, Any]]) -> None:
    STATE_FILE.write_text(json.dumps(plans, indent=2))


def add_plan(token: str, amount_sol: float, interval_seconds: int) -> dict[str, Any]:
    plans = load_plans()
    plan = {
        "id": str(len(plans) + 1),
        "token": token,
        "amount_sol": amount_sol,
        "interval_seconds": interval_seconds,
        "next_run_at": time.time(),
    }
    plans.append(plan)
    save_plans(plans)
    return plan


def tick(dry_run: bool = True) -> list[dict[str, Any]]:
    """Run once: execute any plan whose next_run_at has passed, reschedule it."""
    plans = load_plans()
    now = time.time()
    results = []
    for plan in plans:
        if plan["next_run_at"] > now:
            continue
        if dry_run:
            result = {"status": "dry_run", "would_execute": plan}
        else:
            result = execute_dca_buy_stateless(plan["token"], plan["amount_sol"])
        results.append({"plan_id": plan["id"], "result": result})
        plan["next_run_at"] = now + plan["interval_seconds"]
    save_plans(plans)
    return results
