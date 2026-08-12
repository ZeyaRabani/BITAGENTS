"""
The honest part of Ruqa's proposal: SOMETHING has to remember when each
plan's next buy is due between invocations — you can't have zero state for
a recurring job, only much less of it than a full relational database.

Originally this was a flat local JSON file. Updated 2026-08-12: that version
had the exact same bug this week's main-app scheduler fix closed — no
protection against being invoked more than once at the same time. For a
local loop that never mattered. For a real serverless deployment it would:
Vercel Cron, retries-on-timeout, and platform auto-scaling can all mean the
same tick fires more than once concurrently, and a plan due for exactly one
buy could fire twice. This version uses the same claim-and-lease pattern
already proven this week in db.claim_due_dca_plans — a tiny Postgres table
standing in for a Vercel KV row, claimed with SELECT ... FOR UPDATE SKIP
LOCKED so two concurrent tick invocations can never both grab the same plan.

This is still a much smaller footprint than the current architecture: one
small table, no connection pool kept warm, no in-process scheduler thread —
just a claim, an execution, done. The point isn't "no state," it's "no
persistent server sitting there holding it."
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dca_execute import execute_dca_buy_stateless
from db import get_conn, init_db

SCHEMA = """
CREATE TABLE IF NOT EXISTS serverless_tick_plans (
    id               VARCHAR(16) PRIMARY KEY,
    token            VARCHAR(32) NOT NULL,
    amount_sol       DOUBLE PRECISION NOT NULL,
    interval_seconds INTEGER NOT NULL,
    next_run_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""


def _ensure_schema() -> None:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA)


def add_plan(token: str, amount_sol: float, interval_seconds: int) -> dict[str, Any]:
    _ensure_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS n FROM serverless_tick_plans",
            )
            n = cur.fetchone()["n"]
            plan_id = str(n + 1)
            cur.execute(
                """
                INSERT INTO serverless_tick_plans (id, token, amount_sol, interval_seconds, next_run_at)
                VALUES (%s, %s, %s, %s, NOW())
                RETURNING *
                """,
                (plan_id, token, amount_sol, interval_seconds),
            )
            row = cur.fetchone()
    return dict(row)


def claim_due_plans(limit: int = 25, lease_seconds: int = 60) -> list[dict[str, Any]]:
    """Same claim-and-lease shape as db.claim_due_dca_plans, applied here."""
    _ensure_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id FROM serverless_tick_plans
                WHERE next_run_at <= NOW()
                ORDER BY next_run_at ASC
                LIMIT %s
                FOR UPDATE SKIP LOCKED
                """,
                (limit,),
            )
            claimed_ids = [row["id"] for row in cur.fetchall()]
            if not claimed_ids:
                return []
            cur.execute(
                """
                UPDATE serverless_tick_plans
                SET next_run_at = NOW() + (%s || ' seconds')::interval
                WHERE id = ANY(%s)
                RETURNING *
                """,
                (lease_seconds, claimed_ids),
            )
            rows = cur.fetchall()
    return [dict(row) for row in rows]


def tick(dry_run: bool = True) -> list[dict[str, Any]]:
    """One invocation: claim whatever's due right now, execute it, reschedule.

    This is the whole function a Vercel Cron trigger (or equivalent) would
    call. It doesn't loop, doesn't hold a connection open between calls, and
    doesn't care whether it's the only thing calling itself at this moment
    or one of several -- that's the point of the claim.
    """
    results = []
    for plan in claim_due_plans():
        if dry_run:
            result = {"status": "dry_run", "would_execute": plan}
        else:
            result = execute_dca_buy_stateless(plan["token"], plan["amount_sol"])
        results.append({"plan_id": plan["id"], "result": result})
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE serverless_tick_plans
                    SET next_run_at = NOW() + (%s || ' seconds')::interval
                    WHERE id = %s
                    """,
                    (plan["interval_seconds"], plan["id"]),
                )
    return results
