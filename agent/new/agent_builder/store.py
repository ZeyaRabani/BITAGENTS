"""Postgres rows for built agents and their runs."""

from __future__ import annotations

import json
import secrets
from typing import Any, Optional

from db import _iso, get_conn

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS built_agents (
        id            VARCHAR(16) PRIMARY KEY,
        owner_wallet  VARCHAR(64) NOT NULL,
        prompt        TEXT NOT NULL,
        spec          JSONB NOT NULL,
        spec_sha      VARCHAR(16) NOT NULL,
        compose_meta  JSONB NOT NULL DEFAULT '{}'::jsonb,
        app_name      VARCHAR(64) NOT NULL,
        build_status  VARCHAR(16) NOT NULL DEFAULT 'draft',
        build         JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS built_agents_owner ON built_agents (owner_wallet, created_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS built_agent_runs (
        id          VARCHAR(20) PRIMARY KEY,
        agent_id    VARCHAR(16) NOT NULL REFERENCES built_agents(id) ON DELETE CASCADE,
        wallet      VARCHAR(64) NOT NULL,
        caller      VARCHAR(16) NOT NULL,
        built       BOOLEAN NOT NULL,
        decision    JSONB NOT NULL,
        orders      JSONB NOT NULL DEFAULT '[]'::jsonb,
        error       TEXT,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS built_agent_runs_agent ON built_agent_runs (agent_id, created_at DESC)",
    # paper: orders are simulated on mainnet against a paper book. live: orders are staged for signing.
    "ALTER TABLE built_agents ADD COLUMN IF NOT EXISTS mode VARCHAR(8) NOT NULL DEFAULT 'paper'",
    """
    CREATE TABLE IF NOT EXISTS built_agent_paper (
        agent_id    VARCHAR(16) NOT NULL REFERENCES built_agents(id) ON DELETE CASCADE,
        wallet      VARCHAR(64) NOT NULL,
        cash_usd    NUMERIC NOT NULL,
        positions   JSONB NOT NULL DEFAULT '{}'::jsonb,
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (agent_id, wallet)
    )
    """,
]


def init() -> None:
    with get_conn() as conn, conn.cursor() as cur:
        for stmt in SCHEMA:
            cur.execute(stmt)


def _row(r: Optional[dict]) -> Optional[dict[str, Any]]:
    return {k: _iso(v) for k, v in r.items()} if r else None


def create_agent(owner: str, prompt: str, spec: dict, spec_sha: str, meta: dict) -> dict[str, Any]:
    agent_id = "ag" + secrets.token_hex(4)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO built_agents (id, owner_wallet, prompt, spec, spec_sha, compose_meta, app_name)
               VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (agent_id, owner, prompt, json.dumps(spec), spec_sha, json.dumps(meta), f"bit-{agent_id}"),
        )
        return _row(cur.fetchone())


def get_agent(agent_id: str) -> Optional[dict[str, Any]]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM built_agents WHERE id = %s", (agent_id,))
        return _row(cur.fetchone())


def list_agents(owner: Optional[str] = None) -> list[dict[str, Any]]:
    with get_conn() as conn, conn.cursor() as cur:
        if owner:
            cur.execute("SELECT * FROM built_agents WHERE owner_wallet = %s ORDER BY created_at DESC", (owner,))
        else:
            cur.execute("SELECT * FROM built_agents WHERE build_status = 'ready' ORDER BY created_at DESC LIMIT 50")
        return [_row(r) for r in cur.fetchall()]


def set_build(agent_id: str, status: str, build: dict) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE built_agents SET build_status=%s, build=%s, updated_at=NOW() WHERE id=%s",
                    (status, json.dumps(build), agent_id))


def add_run(agent_id: str, wallet: str, caller: str, built: bool, decision: dict, orders: list, error: Optional[str]) -> str:
    run_id = "run" + secrets.token_hex(6)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO built_agent_runs (id, agent_id, wallet, caller, built, decision, orders, error)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (run_id, agent_id, wallet, caller, built, json.dumps(decision), json.dumps(orders), error),
        )
    return run_id


def list_runs(agent_id: str, limit: int = 20) -> list[dict[str, Any]]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT id, wallet, caller, built, decision, orders, error, created_at
               FROM built_agent_runs WHERE agent_id=%s ORDER BY created_at DESC LIMIT %s""",
            (agent_id, limit),
        )
        return [_row(r) for r in cur.fetchall()]


PAPER_START_USD = 100.0


def set_mode(agent_id: str, mode: str) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE built_agents SET mode=%s, updated_at=NOW() WHERE id=%s", (mode, agent_id))


def paper_book(agent_id: str, wallet: str) -> dict[str, Any]:
    """The paper balance of `wallet` for this agent: cash and {mint: {symbol, raw, decimals}}. Starts at $100."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO built_agent_paper (agent_id, wallet, cash_usd) VALUES (%s,%s,%s)
               ON CONFLICT (agent_id, wallet) DO UPDATE SET agent_id = EXCLUDED.agent_id
               RETURNING cash_usd, positions""",
            (agent_id, wallet, PAPER_START_USD),
        )
        r = cur.fetchone()
        return {"cash_usd": float(r["cash_usd"]), "positions": r["positions"], "start_usd": PAPER_START_USD}


def paper_books(agent_id: str) -> list[dict[str, Any]]:
    """Every paper balance of this agent that has traded, most recently updated first."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""SELECT wallet, cash_usd, positions, updated_at FROM built_agent_paper
                       WHERE agent_id=%s AND positions::text <> '{}' ORDER BY updated_at DESC LIMIT 20""", (agent_id,))
        return [{"wallet": r["wallet"], "cash_usd": float(r["cash_usd"]), "positions": r["positions"],
                 "start_usd": PAPER_START_USD, "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None}
                for r in cur.fetchall()]


def save_paper_book(agent_id: str, wallet: str, book: dict[str, Any]) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("UPDATE built_agent_paper SET cash_usd=%s, positions=%s, updated_at=NOW() WHERE agent_id=%s AND wallet=%s",
                    (book["cash_usd"], json.dumps(book["positions"]), agent_id, wallet))


def spent_today_usd(agent_id: str, wallet: str, mode: str) -> float:
    """Buys since UTC midnight from Aomi-app runs: staged for signing (live) or filled in simulation (paper)."""
    key = "stage" if mode == "live" else "paper_fill"
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT COALESCE(SUM((o->>'usd')::numeric), 0) AS usd
               FROM built_agent_runs r, jsonb_array_elements(r.orders) o
               WHERE r.agent_id=%s AND r.wallet=%s AND r.built AND r.caller='app'
                 AND o->>'side'='buy' AND o ? %s
                 AND r.created_at >= date_trunc('day', NOW() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'""",
            (agent_id, wallet, key),
        )
        return float(cur.fetchone()["usd"])
