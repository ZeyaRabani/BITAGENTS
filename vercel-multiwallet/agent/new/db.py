"""
Neon PostgreSQL persistence for DCA plans, user deposit ledger, and chat sessions.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import psycopg2
import psycopg2.pool
from psycopg2.extras import Json, RealDictCursor

AGENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = AGENT_DIR.parent.parent


def _load_env_file() -> None:
    """Load .env before reading DATABASE_URL (db may import before dca_agent)."""
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env")
        load_dotenv(REPO_ROOT / ".env.local", override=True)
        load_dotenv(AGENT_DIR / ".env", override=True)
    except ImportError:
        env_file = AGENT_DIR / ".env"
        if not env_file.exists():
            return
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_env_file()


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return ""
    # psycopg2/libpq may reject Neon's channel_binding query param
    if "channel_binding=" in url:
        base, _, query = url.partition("?")
        if query:
            parts = [p for p in query.split("&") if not p.startswith("channel_binding=")]
            url = base + ("?" + "&".join(parts) if parts else "")
    return url

_db_lock = threading.RLock()
_schema_ready = False
_import_done = False

SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS dca_plans (
        id                  VARCHAR(16) PRIMARY KEY,
        user_wallet         VARCHAR(64),
        name                TEXT NOT NULL,
        input_token         VARCHAR(32) NOT NULL,
        output_token        VARCHAR(32) NOT NULL,
        input_mint          VARCHAR(64) NOT NULL,
        output_mint         VARCHAR(64) NOT NULL,
        amount_per_buy      DOUBLE PRECISION NOT NULL,
        interval_label      TEXT NOT NULL,
        interval_minutes    DOUBLE PRECISION NOT NULL,
        total_budget        DOUBLE PRECISION,
        spent_so_far        DOUBLE PRECISION NOT NULL DEFAULT 0,
        max_executions      INTEGER,
        executions_count    INTEGER NOT NULL DEFAULT 0,
        slippage_bps        INTEGER NOT NULL DEFAULT 100,
        status              VARCHAR(20) NOT NULL DEFAULT 'active',
        created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        next_execution_at   TIMESTAMPTZ,
        executions          JSONB NOT NULL DEFAULT '[]'::jsonb,
        wallet_mode         VARCHAR(16) NOT NULL DEFAULT 'pooled'
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_dca_plans_user_wallet ON dca_plans (user_wallet)",
    "CREATE INDEX IF NOT EXISTS idx_dca_plans_status ON dca_plans (status)",
    """
    CREATE INDEX IF NOT EXISTS idx_dca_plans_next_execution ON dca_plans (next_execution_at)
        WHERE status = 'active'
    """,
    """
    CREATE TABLE IF NOT EXISTS user_ledger (
        id              VARCHAR(16) PRIMARY KEY,
        user_wallet     VARCHAR(64) NOT NULL,
        agent_wallet    VARCHAR(64),
        signature       VARCHAR(128),
        token           VARCHAR(32) NOT NULL,
        mint            VARCHAR(64) NOT NULL,
        amount          DOUBLE PRECISION NOT NULL,
        direction       VARCHAR(10) NOT NULL DEFAULT 'deposit',
        reference_type  VARCHAR(32),
        reference_id    VARCHAR(128),
        status          VARCHAR(20) NOT NULL DEFAULT 'confirmed',
        verified_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        explorer_url    TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_user_ledger_user_wallet ON user_ledger (user_wallet)",
    "CREATE INDEX IF NOT EXISTS idx_user_ledger_signature ON user_ledger (signature)",
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_user_ledger_deposit_sig
        ON user_ledger (signature, token, direction)
        WHERE direction = 'deposit' AND signature IS NOT NULL
    """,
    """
    CREATE TABLE IF NOT EXISTS chat_sessions (
        id              UUID PRIMARY KEY,
        user_wallet     VARCHAR(64),
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_wallet ON chat_sessions (user_wallet)",
    """
    CREATE TABLE IF NOT EXISTS chat_messages (
        id              BIGSERIAL PRIMARY KEY,
        session_id      UUID NOT NULL REFERENCES chat_sessions (id) ON DELETE CASCADE,
        role            VARCHAR(20) NOT NULL,
        content         TEXT NOT NULL,
        actions         JSONB,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages (session_id, created_at)",
    """
    CREATE TABLE IF NOT EXISTS wallet_auth_challenges (
        nonce           VARCHAR(64) PRIMARY KEY,
        user_wallet     VARCHAR(64) NOT NULL,
        message         TEXT NOT NULL,
        expires_at      TIMESTAMPTZ NOT NULL,
        used            BOOLEAN NOT NULL DEFAULT FALSE,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_wallet_auth_challenges_wallet ON wallet_auth_challenges (user_wallet)",
    """
    CREATE TABLE IF NOT EXISTS wallet_sessions (
        token_hash      VARCHAR(64) PRIMARY KEY,
        user_wallet     VARCHAR(64) NOT NULL,
        expires_at      TIMESTAMPTZ NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_wallet_sessions_wallet ON wallet_sessions (user_wallet)",
    "CREATE INDEX IF NOT EXISTS idx_wallet_sessions_expires ON wallet_sessions (expires_at)",
    """
    CREATE TABLE IF NOT EXISTS dca_platform_metrics (
        id                  VARCHAR(32) PRIMARY KEY DEFAULT 'global',
        total_plans         INTEGER NOT NULL DEFAULT 0,
        active_plans        INTEGER NOT NULL DEFAULT 0,
        total_users         INTEGER NOT NULL DEFAULT 0,
        total_executions    INTEGER NOT NULL DEFAULT 0,
        successful_swaps    INTEGER NOT NULL DEFAULT 0,
        failed_swaps        INTEGER NOT NULL DEFAULT 0,
        total_volume_sol    DOUBLE PRECISION NOT NULL DEFAULT 0,
        total_deposits      INTEGER NOT NULL DEFAULT 0,
        total_withdrawals   INTEGER NOT NULL DEFAULT 0,
        executions_24h      INTEGER NOT NULL DEFAULT 0,
        updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_watchlists (
        id              BIGSERIAL PRIMARY KEY,
        user_wallet     VARCHAR(64) NOT NULL,
        mint            VARCHAR(64) NOT NULL,
        symbol          VARCHAR(32),
        name            TEXT,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (user_wallet, mint)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_user_watchlists_wallet ON user_watchlists (user_wallet)",
    """
    CREATE TABLE IF NOT EXISTS easya_orders (
        id              VARCHAR(16) PRIMARY KEY,
        user_wallet     VARCHAR(64) NOT NULL,
        order_type      VARCHAR(12) NOT NULL,
        input_token     VARCHAR(32) NOT NULL DEFAULT 'SOL',
        output_token    VARCHAR(32) NOT NULL,
        input_mint      VARCHAR(64) NOT NULL,
        output_mint     VARCHAR(64) NOT NULL,
        amount_input    DOUBLE PRECISION NOT NULL,
        limit_price_usd DOUBLE PRECISION,
        limit_market_cap_usd DOUBLE PRECISION,
        stop_price_usd DOUBLE PRECISION,
        stop_market_cap_usd DOUBLE PRECISION,
        condition_mode    VARCHAR(16) NOT NULL DEFAULT 'price',
        slippage_bps    INTEGER NOT NULL DEFAULT 100,
        status          VARCHAR(20) NOT NULL DEFAULT 'pending',
        platform_fee    DOUBLE PRECISION,
        output_amount   DOUBLE PRECISION,
        signature       VARCHAR(128),
        error_message   TEXT,
        recurring       BOOLEAN NOT NULL DEFAULT FALSE,
        max_executions  INTEGER,
        executions      INTEGER NOT NULL DEFAULT 0,
        total_spent     DOUBLE PRECISION NOT NULL DEFAULT 0,
        check_interval_seconds INTEGER NOT NULL DEFAULT 900,
        last_checked_at TIMESTAMPTZ,
        last_filled_at  TIMESTAMPTZ,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        filled_at       TIMESTAMPTZ,
        cancelled_at    TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS easya_order_executions (
        id              BIGSERIAL PRIMARY KEY,
        order_id        VARCHAR(16) NOT NULL,
        user_wallet     VARCHAR(64) NOT NULL,
        amount_input    DOUBLE PRECISION,
        platform_fee    DOUBLE PRECISION,
        output_amount   DOUBLE PRECISION,
        price_usd       DOUBLE PRECISION,
        signature       VARCHAR(128),
        status          VARCHAR(20) NOT NULL DEFAULT 'success',
        error_message   TEXT,
        executed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_easya_order_exec_order ON easya_order_executions (order_id)",
    "CREATE INDEX IF NOT EXISTS idx_easya_order_exec_wallet ON easya_order_executions (user_wallet)",
    "CREATE INDEX IF NOT EXISTS idx_easya_orders_user ON easya_orders (user_wallet)",
    "CREATE INDEX IF NOT EXISTS idx_easya_orders_status ON easya_orders (status)",
    """
    CREATE INDEX IF NOT EXISTS idx_easya_orders_active_limit ON easya_orders (created_at)
        WHERE status = 'active' AND order_type IN ('limit', 'threshold')
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_easya_orders_due_check ON easya_orders (last_checked_at)
        WHERE status = 'active' AND order_type IN ('limit', 'threshold')
    """,
    """
    CREATE TABLE IF NOT EXISTS cache_kv (
        key         TEXT PRIMARY KEY,
        value       JSONB NOT NULL,
        expires_at  TIMESTAMPTZ NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_cache_kv_expires ON cache_kv (expires_at)",
    """
    CREATE TABLE IF NOT EXISTS agent_wallet_index (
        user_wallet   VARCHAR(64) PRIMARY KEY,
        wallet_index  SERIAL NOT NULL,
        created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
]

MIGRATION_STATEMENTS = [
    "ALTER TABLE dca_plans ADD COLUMN IF NOT EXISTS wallet_mode VARCHAR(16) NOT NULL DEFAULT 'pooled'",
    "ALTER TABLE user_ledger ALTER COLUMN reference_id TYPE VARCHAR(128)",
    "ALTER TABLE user_ledger ALTER COLUMN signature TYPE VARCHAR(128)",
    "ALTER TABLE easya_orders ALTER COLUMN order_type TYPE VARCHAR(12)",
    "ALTER TABLE easya_orders ADD COLUMN IF NOT EXISTS recurring BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE easya_orders ADD COLUMN IF NOT EXISTS max_executions INTEGER",
    "ALTER TABLE easya_orders ADD COLUMN IF NOT EXISTS executions INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE easya_orders ADD COLUMN IF NOT EXISTS total_spent DOUBLE PRECISION NOT NULL DEFAULT 0",
    "ALTER TABLE easya_orders ADD COLUMN IF NOT EXISTS check_interval_seconds INTEGER NOT NULL DEFAULT 900",
    "ALTER TABLE easya_orders ADD COLUMN IF NOT EXISTS last_checked_at TIMESTAMPTZ",
    "ALTER TABLE easya_orders ADD COLUMN IF NOT EXISTS last_filled_at TIMESTAMPTZ",
    "ALTER TABLE easya_orders ADD COLUMN IF NOT EXISTS limit_market_cap_usd DOUBLE PRECISION",
    "ALTER TABLE easya_orders ADD COLUMN IF NOT EXISTS stop_price_usd DOUBLE PRECISION",
    "ALTER TABLE easya_orders ADD COLUMN IF NOT EXISTS stop_market_cap_usd DOUBLE PRECISION",
    "ALTER TABLE easya_orders ADD COLUMN IF NOT EXISTS condition_mode VARCHAR(16) NOT NULL DEFAULT 'price'",
    """
    CREATE TABLE IF NOT EXISTS easya_order_executions (
        id              BIGSERIAL PRIMARY KEY,
        order_id        VARCHAR(16) NOT NULL,
        user_wallet     VARCHAR(64) NOT NULL,
        amount_input    DOUBLE PRECISION,
        platform_fee    DOUBLE PRECISION,
        output_amount   DOUBLE PRECISION,
        price_usd       DOUBLE PRECISION,
        signature       VARCHAR(128),
        status          VARCHAR(20) NOT NULL DEFAULT 'success',
        error_message   TEXT,
        executed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_easya_order_exec_order ON easya_order_executions (order_id)",
    "CREATE INDEX IF NOT EXISTS idx_easya_order_exec_wallet ON easya_order_executions (user_wallet)",
    """
    CREATE TABLE IF NOT EXISTS volume_campaigns (
        id                      VARCHAR(16) PRIMARY KEY,
        user_wallet             VARCHAR(64) NOT NULL,
        name                    TEXT NOT NULL,
        base_token              VARCHAR(32) NOT NULL,
        quote_token             VARCHAR(32) NOT NULL DEFAULT 'SOL',
        base_mint               VARCHAR(64) NOT NULL,
        quote_mint              VARCHAR(64) NOT NULL,
        pool_address            VARCHAR(64),
        pool_exists             BOOLEAN NOT NULL DEFAULT FALSE,
        pool_creation_cost_sol  DOUBLE PRECISION NOT NULL DEFAULT 0.02669,
        trade_amount            DOUBLE PRECISION NOT NULL,
        interval_label          TEXT NOT NULL,
        interval_minutes        DOUBLE PRECISION NOT NULL,
        total_budget            DOUBLE PRECISION,
        spent_so_far            DOUBLE PRECISION NOT NULL DEFAULT 0,
        max_executions          INTEGER NOT NULL,
        executions_count      INTEGER NOT NULL DEFAULT 0,
        slippage_bps            INTEGER NOT NULL DEFAULT 100,
        platform_fee_rate       DOUBLE PRECISION NOT NULL DEFAULT 0.0025,
        status                  VARCHAR(20) NOT NULL DEFAULT 'provisioning',
        created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        next_execution_at       TIMESTAMPTZ,
        executions              JSONB NOT NULL DEFAULT '[]'::jsonb,
        infrastructure          JSONB NOT NULL DEFAULT '{}'::jsonb,
        consecutive_failures    INTEGER NOT NULL DEFAULT 0,
        last_error              JSONB
    )
    """,
    # Migration for tables created before consecutive_failures/last_error existed —
    # CREATE TABLE IF NOT EXISTS above won't retroactively add columns.
    "ALTER TABLE volume_campaigns ADD COLUMN IF NOT EXISTS consecutive_failures INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE volume_campaigns ADD COLUMN IF NOT EXISTS last_error JSONB",
    "CREATE INDEX IF NOT EXISTS idx_volume_campaigns_user ON volume_campaigns (user_wallet)",
    "CREATE INDEX IF NOT EXISTS idx_volume_campaigns_status ON volume_campaigns (status)",
    """
    CREATE INDEX IF NOT EXISTS idx_volume_campaigns_next_execution ON volume_campaigns (next_execution_at)
        WHERE status = 'active'
    """,
    """
    CREATE TABLE IF NOT EXISTS custom_agents (
        id                      UUID PRIMARY KEY,
        creator_wallet          VARCHAR(64) NOT NULL,
        name                    TEXT,
        handle                  VARCHAR(40),
        category                VARCHAR(20),
        description             TEXT,
        system_prompt           TEXT,
        model_tier              VARCHAR(20) NOT NULL DEFAULT 'balanced',
        tool_scope              VARCHAR(20) NOT NULL DEFAULT 'read_only',
        creator_fee_share_pct   DOUBLE PRECISION NOT NULL DEFAULT 20.0,
        enabled_tools           JSONB NOT NULL DEFAULT '[]'::jsonb,
        status                  VARCHAR(20) NOT NULL DEFAULT 'draft',
        builder_session_id      UUID,
        runs                    INTEGER NOT NULL DEFAULT 0,
        volume_usd              DOUBLE PRECISION NOT NULL DEFAULT 0,
        testing_started_at      TIMESTAMPTZ,
        created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "ALTER TABLE custom_agents ADD COLUMN IF NOT EXISTS enabled_tools JSONB NOT NULL DEFAULT '[]'::jsonb",
    "CREATE INDEX IF NOT EXISTS idx_custom_agents_status ON custom_agents (status)",
    "CREATE INDEX IF NOT EXISTS idx_custom_agents_creator ON custom_agents (creator_wallet)",
]


def db_configured() -> bool:
    return bool(get_database_url())


def _require_db() -> None:
    if not get_database_url():
        raise RuntimeError(
            "DATABASE_URL is not set. Add your Neon connection string to agent/new/.env"
        )


# minconn connections are opened eagerly the moment the pool is first created
# (not at import time — the pool itself is created lazily on first get_conn()),
# so this is also the steady-state number of open connections to Neon per
# instance. Kept modest by default since this multiplies by instance count
# once running more than one instance — raise it based on the actual Neon
# plan's connection limit, not guesswork.
DB_POOL_MAX_CONNECTIONS = int(os.environ.get("DB_POOL_MAX_CONNECTIONS", "10"))
# psycopg2's pool only keeps up to `minconn` idle connections around on putconn() —
# anything returned above that is closed and reopened next time, not reused. So
# minconn needs to equal maxconn for this to behave like an actual reusable pool,
# not a size range (unlike most other connection pool implementations).
DB_POOL_MIN_CONNECTIONS = int(os.environ.get("DB_POOL_MIN_CONNECTIONS", str(DB_POOL_MAX_CONNECTIONS)))
DB_POOL_CHECKOUT_TIMEOUT_SECONDS = float(os.environ.get("DB_POOL_CHECKOUT_TIMEOUT_SECONDS", "5"))

_pool: Optional["psycopg2.pool.ThreadedConnectionPool"] = None
_pool_lock = threading.Lock()


def _get_pool() -> "psycopg2.pool.ThreadedConnectionPool":
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = psycopg2.pool.ThreadedConnectionPool(
                    DB_POOL_MIN_CONNECTIONS,
                    DB_POOL_MAX_CONNECTIONS,
                    get_database_url(),
                    cursor_factory=RealDictCursor,
                    connect_timeout=15,
                )
    return _pool


def _checkout_conn(pool: "psycopg2.pool.ThreadedConnectionPool"):
    """pool.getconn() raises PoolError immediately when exhausted instead of
    waiting — under a real traffic burst that turns transient saturation into
    hard request failures. Retry briefly instead; connections free up in
    milliseconds once in-flight queries finish, so a short bounded wait
    smooths over bursts instead of failing the instant every slot is busy.
    """
    deadline = time.monotonic() + DB_POOL_CHECKOUT_TIMEOUT_SECONDS
    delay = 0.05
    while True:
        try:
            return pool.getconn()
        except psycopg2.pool.PoolError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 0.5)


@contextmanager
def get_conn():
    """A pooled connection instead of opening a fresh TCP+TLS connection per call.

    Previously every get_conn() call did a full psycopg2.connect() (new TCP
    handshake + TLS + auth against Neon) and closed it on exit — at high
    request volume this adds real per-call latency and risks hitting Neon's
    connection limit as traffic grows. A pool reuses live connections instead.
    Broken connections (dead socket, etc.) are discarded rather than returned
    to the pool, so one bad connection doesn't poison future checkouts.
    """
    _require_db()
    pool = _get_pool()
    conn = _checkout_conn(pool)
    broken = False
    try:
        yield conn
        conn.commit()
    except psycopg2.OperationalError:
        broken = True
        raise
    except Exception:
        try:
            conn.rollback()
        except psycopg2.OperationalError:
            broken = True
        raise
    finally:
        pool.putconn(conn, close=broken)


def _iso(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return value


def _plan_row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    executions = row.get("executions") or []
    if isinstance(executions, str):
        executions = json.loads(executions)
    return {
        "id": row["id"],
        "name": row["name"],
        "input_token": row["input_token"],
        "output_token": row["output_token"],
        "input_mint": row["input_mint"],
        "output_mint": row["output_mint"],
        "amount_per_buy": float(row["amount_per_buy"]),
        "interval": row["interval_label"],
        "interval_minutes": float(row["interval_minutes"]),
        "total_budget": float(row["total_budget"]) if row.get("total_budget") is not None else None,
        "spent_so_far": float(row.get("spent_so_far") or 0),
        "max_executions": row.get("max_executions"),
        "executions_count": int(row.get("executions_count") or 0),
        "slippage_bps": int(row.get("slippage_bps") or 100),
        "status": row["status"],
        "user_wallet": row.get("user_wallet"),
        "created_at": _iso(row.get("created_at")),
        "next_execution_at": _iso(row.get("next_execution_at")),
        "executions": executions,
        "wallet_mode": row.get("wallet_mode") or "pooled",
    }


def _ledger_row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "user_wallet": row["user_wallet"],
        "agent_wallet": row.get("agent_wallet"),
        "signature": row.get("signature"),
        "token": row["token"],
        "mint": row["mint"],
        "amount": float(row["amount"]),
        "direction": row.get("direction") or "deposit",
        "reference_type": row.get("reference_type"),
        "reference_id": row.get("reference_id"),
        "status": row.get("status") or "confirmed",
        "verified_at": _iso(row.get("verified_at")),
        "explorer_url": row.get("explorer_url"),
    }


def init_db() -> None:
    global _schema_ready, _import_done
    if not get_database_url():
        raise RuntimeError("DATABASE_URL is not set.")
    with _db_lock:
        if _schema_ready:
            return
        with get_conn() as conn:
            with conn.cursor() as cur:
                for stmt in SCHEMA_STATEMENTS:
                    cur.execute(stmt)
                for stmt in MIGRATION_STATEMENTS:
                    cur.execute(stmt)
        _schema_ready = True

    if _import_done:
        return
    with _db_lock:
        if _import_done:
            return
        _import_json_if_empty()
        _import_done = True


def _import_json_if_empty() -> None:
    """One-time import from legacy JSON files when DB tables are empty."""
    plans_file = Path(os.environ.get("DCA_PLANS_FILE", str(AGENT_DIR / "dca_plans.json")))
    deposits_file = Path(
        os.environ.get("DCA_DEPOSITS_FILE", str(AGENT_DIR / "user_deposits.json"))
    )

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM dca_plans")
            plan_count = int(cur.fetchone()["n"])
            cur.execute("SELECT COUNT(*) AS n FROM user_ledger")
            ledger_count = int(cur.fetchone()["n"])

    if plan_count == 0 and plans_file.exists():
        try:
            plans = json.loads(plans_file.read_text(encoding="utf-8"))
            if isinstance(plans, list):
                for plan in plans:
                    insert_plan(plan)
                print(f"  📦 Imported {len(plans)} DCA plan(s) from {plans_file.name}")
        except Exception as exc:
            print(f"  ⚠️  Could not import plans JSON: {exc}")

    if ledger_count == 0 and deposits_file.exists():
        try:
            rows = json.loads(deposits_file.read_text(encoding="utf-8"))
            if isinstance(rows, list):
                for row in rows:
                    insert_ledger_entry(row)
                print(f"  📦 Imported {len(rows)} ledger row(s) from {deposits_file.name}")
        except Exception as exc:
            print(f"  ⚠️  Could not import deposits JSON: {exc}")


# ─── DCA plans ────────────────────────────────────────────────────────────────

def load_all_plans(user_wallet: Optional[str] = None) -> list[dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            if user_wallet:
                cur.execute(
                    "SELECT * FROM dca_plans WHERE user_wallet = %s ORDER BY created_at ASC",
                    (user_wallet.strip(),),
                )
            else:
                cur.execute("SELECT * FROM dca_plans ORDER BY created_at ASC")
            rows = cur.fetchall()
    return [_plan_row_to_dict(row) for row in rows]


def claim_due_dca_plans(limit: int = 25, lease_seconds: int = 180) -> list[dict[str, Any]]:
    """Atomically claim up to `limit` due, active plans for execution.

    Uses SELECT ... FOR UPDATE SKIP LOCKED so multiple scheduler instances can
    poll the same table concurrently without ever claiming the same plan twice.
    Claiming pushes next_execution_at forward by lease_seconds as a lease —
    if this worker crashes mid-execution, the plan becomes claimable again once
    the lease expires instead of being stuck forever. A successful execution
    overwrites next_execution_at with the real next run time; a failed one
    naturally retries after the lease window instead of hot-looping every poll.
    """
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id FROM dca_plans
                WHERE status = 'active' AND next_execution_at <= NOW()
                ORDER BY next_execution_at ASC
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
                UPDATE dca_plans
                SET next_execution_at = NOW() + (%s || ' seconds')::interval
                WHERE id = ANY(%s)
                RETURNING *
                """,
                (lease_seconds, claimed_ids),
            )
            rows = cur.fetchall()
    return [_plan_row_to_dict(row) for row in rows]


def find_plan(plan_id: str) -> Optional[dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM dca_plans WHERE id = %s", (plan_id,))
            row = cur.fetchone()
    return _plan_row_to_dict(row) if row else None


def insert_plan(plan: dict[str, Any]) -> dict[str, Any]:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dca_plans (
                    id, user_wallet, name, input_token, output_token,
                    input_mint, output_mint, amount_per_buy, interval_label,
                    interval_minutes, total_budget, spent_so_far, max_executions,
                    executions_count, slippage_bps, status, created_at,
                    next_execution_at, executions, wallet_mode
                ) VALUES (
                    %(id)s, %(user_wallet)s, %(name)s, %(input_token)s, %(output_token)s,
                    %(input_mint)s, %(output_mint)s, %(amount_per_buy)s, %(interval)s,
                    %(interval_minutes)s, %(total_budget)s, %(spent_so_far)s, %(max_executions)s,
                    %(executions_count)s, %(slippage_bps)s, %(status)s, %(created_at)s,
                    %(next_execution_at)s, %(executions)s, %(wallet_mode)s
                )
                """,
                {
                    **plan,
                    "interval": plan.get("interval"),
                    "executions": Json(plan.get("executions") or []),
                    "wallet_mode": plan.get("wallet_mode") or "pooled",
                },
            )
    return plan


def update_plan(plan_id: str, updates: dict[str, Any]) -> Optional[dict[str, Any]]:
    init_db()
    plan = find_plan(plan_id)
    if not plan:
        return None

    merged = {**plan, **updates}
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE dca_plans SET
                    user_wallet = %(user_wallet)s,
                    name = %(name)s,
                    input_token = %(input_token)s,
                    output_token = %(output_token)s,
                    input_mint = %(input_mint)s,
                    output_mint = %(output_mint)s,
                    amount_per_buy = %(amount_per_buy)s,
                    interval_label = %(interval)s,
                    interval_minutes = %(interval_minutes)s,
                    total_budget = %(total_budget)s,
                    spent_so_far = %(spent_so_far)s,
                    max_executions = %(max_executions)s,
                    executions_count = %(executions_count)s,
                    slippage_bps = %(slippage_bps)s,
                    status = %(status)s,
                    created_at = %(created_at)s,
                    next_execution_at = %(next_execution_at)s,
                    executions = %(executions)s
                WHERE id = %(id)s
                """,
                {
                    "id": plan_id,
                    "user_wallet": merged.get("user_wallet"),
                    "name": merged["name"],
                    "input_token": merged["input_token"],
                    "output_token": merged["output_token"],
                    "input_mint": merged["input_mint"],
                    "output_mint": merged["output_mint"],
                    "amount_per_buy": merged["amount_per_buy"],
                    "interval": merged["interval"],
                    "interval_minutes": merged["interval_minutes"],
                    "total_budget": merged.get("total_budget"),
                    "spent_so_far": merged.get("spent_so_far", 0),
                    "max_executions": merged.get("max_executions"),
                    "executions_count": merged.get("executions_count", 0),
                    "slippage_bps": merged.get("slippage_bps", 100),
                    "status": merged.get("status", "active"),
                    "created_at": merged.get("created_at"),
                    "next_execution_at": merged.get("next_execution_at"),
                    "executions": Json(merged.get("executions") or []),
                },
            )
    return find_plan(plan_id)


# ─── User ledger ──────────────────────────────────────────────────────────────

def load_all_ledger_entries() -> list[dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM user_ledger ORDER BY verified_at ASC")
            rows = cur.fetchall()
    return [_ledger_row_to_dict(row) for row in rows]


def load_user_balance_data(user_wallet: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load ledger rows and plans for one user in a single DB round trip."""
    init_db()
    user_wallet = user_wallet.strip()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM user_ledger
                WHERE user_wallet = %s
                ORDER BY verified_at ASC
                """,
                (user_wallet,),
            )
            ledger_rows = [_ledger_row_to_dict(row) for row in cur.fetchall()]
            cur.execute(
                "SELECT * FROM dca_plans WHERE user_wallet = %s ORDER BY created_at ASC",
                (user_wallet,),
            )
            plan_rows = [_plan_row_to_dict(row) for row in cur.fetchall()]
    return ledger_rows, plan_rows


def load_ledger_for_user(user_wallet: str, limit: Optional[int] = None) -> list[dict[str, Any]]:
    init_db()
    query = """
        SELECT * FROM user_ledger
        WHERE user_wallet = %s
        ORDER BY verified_at DESC
    """
    params: list[Any] = [user_wallet.strip()]
    if limit is not None:
        query += " LIMIT %s"
        params.append(limit)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
    return [_ledger_row_to_dict(row) for row in rows]


def deposit_exists(signature: str) -> bool:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM user_ledger
                WHERE signature = %s AND direction = 'deposit'
                LIMIT 1
                """,
                (signature.strip(),),
            )
            return cur.fetchone() is not None


def find_deposit_by_signature(signature: str) -> Optional[dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM user_ledger
                WHERE signature = %s AND direction = 'deposit'
                ORDER BY verified_at ASC
                LIMIT 1
                """,
                (signature.strip(),),
            )
            row = cur.fetchone()
    return _ledger_row_to_dict(row) if row else None


def insert_ledger_entry(record: dict[str, Any]) -> bool:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_ledger (
                    id, user_wallet, agent_wallet, signature, token, mint,
                    amount, direction, reference_type, reference_id,
                    status, verified_at, explorer_url
                ) VALUES (
                    %(id)s, %(user_wallet)s, %(agent_wallet)s, %(signature)s, %(token)s, %(mint)s,
                    %(amount)s, %(direction)s, %(reference_type)s, %(reference_id)s,
                    %(status)s, %(verified_at)s, %(explorer_url)s
                )
                ON CONFLICT DO NOTHING
                """,
                {
                    "id": record.get("id") or uuid.uuid4().hex[:16],
                    "user_wallet": record["user_wallet"],
                    "agent_wallet": record.get("agent_wallet"),
                    "signature": record.get("signature"),
                    "token": record["token"],
                    "mint": record["mint"],
                    "amount": float(record["amount"]),
                    "direction": record.get("direction") or "deposit",
                    "reference_type": record.get("reference_type"),
                    "reference_id": record.get("reference_id"),
                    "status": record.get("status") or "confirmed",
                    "verified_at": record.get("verified_at") or datetime.now(timezone.utc).isoformat(),
                    "explorer_url": record.get("explorer_url"),
                },
            )
            return cur.rowcount > 0


# ─── Chat sessions ────────────────────────────────────────────────────────────

def ensure_chat_session(session_id: str, user_wallet: Optional[str] = None) -> str:
    init_db()
    sid = session_id.strip()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO chat_sessions (id, user_wallet)
                VALUES (%s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    user_wallet = COALESCE(EXCLUDED.user_wallet, chat_sessions.user_wallet),
                    updated_at = NOW()
                """,
                (sid, user_wallet.strip() if user_wallet else None),
            )
    return sid


def get_chat_session_owner(session_id: str) -> Optional[str]:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_wallet FROM chat_sessions WHERE id = %s",
                (session_id.strip(),),
            )
            row = cur.fetchone()
    if not row:
        return None
    return row.get("user_wallet")


def assert_chat_session_access(session_id: str, user_wallet: str) -> Optional[str]:
    """Return error message if the wallet may not access this chat session."""
    owner = get_chat_session_owner(session_id.strip())
    if owner and owner != user_wallet.strip():
        return "This chat session belongs to another wallet."
    return None


def load_chat_history(session_id: str) -> list[dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT role, content FROM chat_messages
                WHERE session_id = %s
                ORDER BY created_at ASC, id ASC
                """,
                (session_id,),
            )
            rows = cur.fetchall()
    return [{"role": row["role"], "content": row["content"]} for row in rows]


def append_chat_messages(
    session_id: str,
    user_content: str,
    assistant_content: str,
    actions: Optional[list[dict[str, Any]]] = None,
    user_wallet: Optional[str] = None,
) -> None:
    init_db()
    ensure_chat_session(session_id, user_wallet)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO chat_messages (session_id, role, content)
                VALUES (%s, 'user', %s)
                """,
                (session_id, user_content),
            )
            cur.execute(
                """
                INSERT INTO chat_messages (session_id, role, content, actions)
                VALUES (%s, 'assistant', %s, %s)
                """,
                (session_id, assistant_content, Json(actions or [])),
            )
            cur.execute(
                "UPDATE chat_sessions SET updated_at = NOW(), user_wallet = COALESCE(%s, user_wallet) WHERE id = %s",
                (user_wallet.strip() if user_wallet else None, session_id),
            )


def delete_chat_session(session_id: str) -> bool:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM chat_sessions WHERE id = %s", (session_id,))
            return cur.rowcount > 0


# ─── Custom agents (marketplace launchpad) ────────────────────────────────────

def _custom_agent_row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    d = dict(row)
    d["id"] = str(d["id"])
    if d.get("builder_session_id"):
        d["builder_session_id"] = str(d["builder_session_id"])
    d["created_at"] = _iso(d.get("created_at"))
    d["updated_at"] = _iso(d.get("updated_at"))
    d["testing_started_at"] = _iso(d.get("testing_started_at"))
    return d


def create_draft_agent(creator_wallet: str, builder_session_id: str) -> dict[str, Any]:
    init_db()
    agent_id = str(uuid.uuid4())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO custom_agents (id, creator_wallet, builder_session_id, status)
                VALUES (%s, %s, %s, 'draft')
                RETURNING *
                """,
                (agent_id, creator_wallet.strip(), builder_session_id),
            )
            row = cur.fetchone()
    return _custom_agent_row_to_dict(row)


def get_draft_agent_by_session(builder_session_id: str) -> Optional[dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM custom_agents WHERE builder_session_id = %s ORDER BY created_at DESC LIMIT 1",
                (builder_session_id,),
            )
            row = cur.fetchone()
    return _custom_agent_row_to_dict(row) if row else None


def update_custom_agent_fields(agent_id: str, **fields: Any) -> Optional[dict[str, Any]]:
    """Patch arbitrary allowed columns on a draft/testing agent."""
    if not fields:
        return get_custom_agent(agent_id)
    init_db()
    allowed = {
        "name", "handle", "category", "description", "system_prompt",
        "model_tier", "tool_scope", "creator_fee_share_pct", "status",
        "testing_started_at", "enabled_tools",
    }
    sets = []
    values: list[Any] = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        sets.append(f"{key} = %s")
        values.append(Json(value) if key == "enabled_tools" else value)
    if not sets:
        return get_custom_agent(agent_id)
    sets.append("updated_at = NOW()")
    values.append(agent_id)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE custom_agents SET {', '.join(sets)} WHERE id = %s RETURNING *",
                values,
            )
            row = cur.fetchone()
    return _custom_agent_row_to_dict(row) if row else None


def get_custom_agent(agent_id: str) -> Optional[dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM custom_agents WHERE id = %s", (agent_id,))
            row = cur.fetchone()
    return _custom_agent_row_to_dict(row) if row else None


def list_custom_agents(status: Optional[str] = None, creator_wallet: Optional[str] = None) -> list[dict[str, Any]]:
    init_db()
    clauses = []
    values: list[Any] = []
    if status:
        clauses.append("status = %s")
        values.append(status)
    if creator_wallet:
        clauses.append("creator_wallet = %s")
        values.append(creator_wallet.strip())
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM custom_agents {where} ORDER BY created_at DESC LIMIT 200",
                values,
            )
            rows = cur.fetchall()
    return [_custom_agent_row_to_dict(r) for r in rows]


def record_custom_agent_run(agent_id: str, volume_usd: float = 0.0) -> None:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE custom_agents
                SET runs = runs + 1, volume_usd = volume_usd + %s, updated_at = NOW()
                WHERE id = %s
                """,
                (volume_usd, agent_id),
            )


def finalize_custom_agent(agent_id: str) -> Optional[dict[str, Any]]:
    """Move a draft agent into the 24h testing window, creator-only access."""
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE custom_agents
                SET status = 'testing', testing_started_at = NOW(), updated_at = NOW()
                WHERE id = %s AND status = 'draft'
                RETURNING *
                """,
                (agent_id,),
            )
            row = cur.fetchone()
    return _custom_agent_row_to_dict(row) if row else None


def promote_ready_test_agents(testing_hours: float = 24.0) -> list[str]:
    """Flip read_only agents from testing -> live once the testing window has elapsed."""
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE custom_agents
                SET status = 'live', updated_at = NOW()
                WHERE status = 'testing'
                  AND tool_scope = 'read_only'
                  AND testing_started_at IS NOT NULL
                  AND testing_started_at <= NOW() - (%s || ' hours')::interval
                RETURNING id
                """,
                (testing_hours,),
            )
            rows = cur.fetchall()
    return [str(r["id"]) for r in rows]


# ─── Platform metrics ─────────────────────────────────────────────────────────

def compute_platform_metrics() -> dict[str, Any]:
    """Aggregate live stats from plans and ledger."""
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM dca_plans")
            total_plans = int(cur.fetchone()["n"])
            cur.execute("SELECT COUNT(*) AS n FROM dca_plans WHERE status = 'active'")
            active_plans = int(cur.fetchone()["n"])
            cur.execute(
                "SELECT COUNT(DISTINCT user_wallet) AS n FROM dca_plans WHERE user_wallet IS NOT NULL"
            )
            total_users = int(cur.fetchone()["n"])
            cur.execute("SELECT COALESCE(SUM(executions_count), 0) AS n FROM dca_plans")
            total_executions = int(cur.fetchone()["n"])
            cur.execute(
                """
                SELECT COALESCE(SUM(spent_so_far), 0) AS n
                FROM dca_plans WHERE UPPER(input_token) = 'SOL'
                """
            )
            total_volume_sol = float(cur.fetchone()["n"])
            cur.execute("SELECT COUNT(*) AS n FROM user_ledger WHERE direction = 'deposit'")
            total_deposits = int(cur.fetchone()["n"])
            cur.execute("SELECT COUNT(*) AS n FROM user_ledger WHERE direction = 'withdraw'")
            total_withdrawals = int(cur.fetchone()["n"])
            cur.execute(
                """
                SELECT COUNT(*) AS n FROM user_ledger
                WHERE direction = 'spend' AND reference_type = 'swap'
                  AND verified_at >= NOW() - INTERVAL '24 hours'
                """
            )
            executions_24h = int(cur.fetchone()["n"])
            cur.execute(
                """
                SELECT COUNT(*) AS n FROM user_ledger
                WHERE direction = 'spend' AND reference_type = 'swap'
                """
            )
            successful_swaps = int(cur.fetchone()["n"])
    failed_swaps = max(0, total_executions - successful_swaps)
    return {
        "total_plans": total_plans,
        "active_plans": active_plans,
        "total_users": total_users,
        "total_executions": total_executions,
        "successful_swaps": successful_swaps,
        "failed_swaps": failed_swaps,
        "total_volume_sol": round(total_volume_sol, 9),
        "total_deposits": total_deposits,
        "total_withdrawals": total_withdrawals,
        "executions_24h": executions_24h,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def upsert_platform_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dca_platform_metrics (
                    id, total_plans, active_plans, total_users, total_executions,
                    successful_swaps, failed_swaps, total_volume_sol,
                    total_deposits, total_withdrawals, executions_24h, updated_at
                ) VALUES (
                    'global', %(total_plans)s, %(active_plans)s, %(total_users)s,
                    %(total_executions)s, %(successful_swaps)s, %(failed_swaps)s,
                    %(total_volume_sol)s, %(total_deposits)s, %(total_withdrawals)s,
                    %(executions_24h)s, NOW()
                )
                ON CONFLICT (id) DO UPDATE SET
                    total_plans = EXCLUDED.total_plans,
                    active_plans = EXCLUDED.active_plans,
                    total_users = EXCLUDED.total_users,
                    total_executions = EXCLUDED.total_executions,
                    successful_swaps = EXCLUDED.successful_swaps,
                    failed_swaps = EXCLUDED.failed_swaps,
                    total_volume_sol = EXCLUDED.total_volume_sol,
                    total_deposits = EXCLUDED.total_deposits,
                    total_withdrawals = EXCLUDED.total_withdrawals,
                    executions_24h = EXCLUDED.executions_24h,
                    updated_at = NOW()
                RETURNING *
                """,
                metrics,
            )
            row = cur.fetchone()
    return {
        "total_plans": int(row["total_plans"]),
        "active_plans": int(row["active_plans"]),
        "total_users": int(row["total_users"]),
        "total_executions": int(row["total_executions"]),
        "successful_swaps": int(row["successful_swaps"]),
        "failed_swaps": int(row["failed_swaps"]),
        "total_volume_sol": float(row["total_volume_sol"]),
        "total_deposits": int(row["total_deposits"]),
        "total_withdrawals": int(row["total_withdrawals"]),
        "executions_24h": int(row["executions_24h"]),
        "updated_at": _iso(row["updated_at"]),
    }


def get_platform_metrics(refresh: bool = False) -> dict[str, Any]:
    init_db()
    if refresh:
        return upsert_platform_metrics(compute_platform_metrics())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM dca_platform_metrics WHERE id = 'global'")
            row = cur.fetchone()
    if not row:
        return upsert_platform_metrics(compute_platform_metrics())
    return {
        "total_plans": int(row["total_plans"]),
        "active_plans": int(row["active_plans"]),
        "total_users": int(row["total_users"]),
        "total_executions": int(row["total_executions"]),
        "successful_swaps": int(row["successful_swaps"]),
        "failed_swaps": int(row["failed_swaps"]),
        "total_volume_sol": float(row["total_volume_sol"]),
        "total_deposits": int(row["total_deposits"]),
        "total_withdrawals": int(row["total_withdrawals"]),
        "executions_24h": int(row["executions_24h"]),
        "updated_at": _iso(row["updated_at"]),
    }


# ─── User watchlists (Kickstart Copilot) ──────────────────────────────────────

def add_watchlist_token(
    user_wallet: str,
    mint: str,
    symbol: Optional[str] = None,
    name: Optional[str] = None,
) -> dict[str, Any]:
    init_db()
    wallet = user_wallet.strip()
    mint = mint.strip()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_watchlists (user_wallet, mint, symbol, name)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_wallet, mint) DO UPDATE SET
                    symbol = COALESCE(EXCLUDED.symbol, user_watchlists.symbol),
                    name = COALESCE(EXCLUDED.name, user_watchlists.name)
                RETURNING id, symbol, name, created_at
                """,
                (wallet, mint, symbol, name),
            )
            row = cur.fetchone()
    return {
        "status": "added",
        "user_wallet": wallet,
        "mint": mint,
        "symbol": row["symbol"] if row else symbol,
        "name": row["name"] if row else name,
    }


def remove_watchlist_token(user_wallet: str, mint: str) -> dict[str, Any]:
    init_db()
    wallet = user_wallet.strip()
    mint = mint.strip()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM user_watchlists WHERE user_wallet = %s AND mint = %s",
                (wallet, mint),
            )
            removed = cur.rowcount > 0
    if not removed:
        return {"error": "Token not on watchlist.", "mint": mint}
    return {"status": "removed", "user_wallet": wallet, "mint": mint}


def list_watchlist(user_wallet: str) -> dict[str, Any]:
    init_db()
    wallet = user_wallet.strip()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT mint, symbol, name, created_at
                FROM user_watchlists
                WHERE user_wallet = %s
                ORDER BY created_at DESC
                """,
                (wallet,),
            )
            rows = cur.fetchall()
    watchlist = [
        {
            "mint": row["mint"],
            "symbol": row["symbol"],
            "name": row["name"],
            "added_at": _iso(row["created_at"]),
        }
        for row in rows
    ]
    return {"user_wallet": wallet, "count": len(watchlist), "watchlist": watchlist}


def compare_watchlist_tokens(user_wallet: str) -> dict[str, Any]:
    return list_watchlist(user_wallet)


# ─── Volume campaigns ─────────────────────────────────────────────────────────

def _volume_campaign_row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    if not row:
        return {}
    out = dict(row)
    out["interval"] = out.pop("interval_label", out.get("interval"))
    out["created_at"] = _iso(out.get("created_at"))
    out["next_execution_at"] = _iso(out.get("next_execution_at"))
    if isinstance(out.get("executions"), str):
        try:
            out["executions"] = json.loads(out["executions"])
        except Exception:
            out["executions"] = []
    if isinstance(out.get("infrastructure"), str):
        try:
            out["infrastructure"] = json.loads(out["infrastructure"])
        except Exception:
            out["infrastructure"] = {}
    return out


def load_all_volume_campaigns(user_wallet: Optional[str] = None) -> list[dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            if user_wallet:
                cur.execute(
                    "SELECT * FROM volume_campaigns WHERE user_wallet = %s ORDER BY created_at ASC",
                    (user_wallet.strip(),),
                )
            else:
                cur.execute("SELECT * FROM volume_campaigns ORDER BY created_at ASC")
            rows = cur.fetchall()
    return [_volume_campaign_row_to_dict(row) for row in rows]


def claim_due_volume_campaigns(limit: int = 25, lease_seconds: int = 180) -> list[dict[str, Any]]:
    """Same claim-and-lease pattern as claim_due_dca_plans, for active volume cycles."""
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id FROM volume_campaigns
                WHERE status = 'active' AND next_execution_at <= NOW()
                ORDER BY next_execution_at ASC
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
                UPDATE volume_campaigns
                SET next_execution_at = NOW() + (%s || ' seconds')::interval
                WHERE id = ANY(%s)
                RETURNING *
                """,
                (lease_seconds, claimed_ids),
            )
            rows = cur.fetchall()
    return [_volume_campaign_row_to_dict(row) for row in rows]


def claim_provisioning_volume_campaigns(limit: int = 10, lease_seconds: int = 120) -> list[dict[str, Any]]:
    """Claim campaigns stuck in 'provisioning' so only one worker retries pool setup for each.

    'provisioning' rows don't use next_execution_at for scheduling, so it's free to
    reuse here purely as a claim lease (same reasoning as claim_due_dca_plans) —
    without it, the row lock from FOR UPDATE releases as soon as this function's
    transaction commits, before the actual (slow, on-chain) provisioning call runs,
    so a second poll could grab the same campaign and double-create a pool.
    """
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id FROM volume_campaigns
                WHERE status = 'provisioning'
                  AND (next_execution_at IS NULL OR next_execution_at <= NOW())
                ORDER BY created_at ASC
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
                UPDATE volume_campaigns
                SET next_execution_at = NOW() + (%s || ' seconds')::interval
                WHERE id = ANY(%s)
                RETURNING *
                """,
                (lease_seconds, claimed_ids),
            )
            rows = cur.fetchall()
    return [_volume_campaign_row_to_dict(row) for row in rows]


def claim_due_easya_orders(limit: int = 25) -> list[dict[str, Any]]:
    """Claim-and-lease active limit/threshold orders due for a fill check.

    Limit orders have no check interval (order_type = 'limit' bypasses the
    last_checked_at gate below) — they're checked every poll, same as before.
    Threshold orders keep their existing check_interval_seconds semantics.
    Bumping last_checked_at inside the same FOR UPDATE SKIP LOCKED transaction
    doubles as both the due-check and the claim lease, so two scheduler
    instances can never both pick up the same order in the same window.
    """
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id FROM easya_orders
                WHERE status = 'active'
                  AND order_type IN ('limit', 'threshold')
                  AND (
                    order_type = 'limit'
                    OR last_checked_at IS NULL
                    OR last_checked_at <= NOW() - (check_interval_seconds || ' seconds')::interval
                  )
                ORDER BY last_checked_at ASC NULLS FIRST
                LIMIT %s
                FOR UPDATE SKIP LOCKED
                """,
                (limit,),
            )
            claimed_ids = [row["id"] for row in cur.fetchall()]
            if not claimed_ids:
                return []
            cur.execute(
                "UPDATE easya_orders SET last_checked_at = NOW() WHERE id = ANY(%s) RETURNING *",
                (claimed_ids,),
            )
            rows = cur.fetchall()
    return [dict(row) for row in rows]


def find_volume_campaign(campaign_id: str) -> Optional[dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM volume_campaigns WHERE id = %s", (campaign_id,))
            row = cur.fetchone()
    return _volume_campaign_row_to_dict(row) if row else None


def insert_volume_campaign(campaign: dict[str, Any]) -> dict[str, Any]:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO volume_campaigns (
                    id, user_wallet, name, base_token, quote_token, base_mint, quote_mint,
                    pool_address, pool_exists, pool_creation_cost_sol, trade_amount,
                    interval_label, interval_minutes, total_budget, spent_so_far,
                    max_executions, executions_count, slippage_bps, platform_fee_rate,
                    status, created_at, next_execution_at, executions, infrastructure
                ) VALUES (
                    %(id)s, %(user_wallet)s, %(name)s, %(base_token)s, %(quote_token)s,
                    %(base_mint)s, %(quote_mint)s, %(pool_address)s, %(pool_exists)s,
                    %(pool_creation_cost_sol)s, %(trade_amount)s, %(interval)s,
                    %(interval_minutes)s, %(total_budget)s, %(spent_so_far)s,
                    %(max_executions)s, %(executions_count)s, %(slippage_bps)s,
                    %(platform_fee_rate)s, %(status)s, %(created_at)s, %(next_execution_at)s,
                    %(executions)s, %(infrastructure)s
                )
                """,
                {
                    **campaign,
                    "interval": campaign.get("interval"),
                    "executions": Json(campaign.get("executions") or []),
                    "infrastructure": Json(campaign.get("infrastructure") or {}),
                },
            )
    return campaign


def update_volume_campaign(campaign_id: str, updates: dict[str, Any]) -> Optional[dict[str, Any]]:
    init_db()
    campaign = find_volume_campaign(campaign_id)
    if not campaign:
        return None
    merged = {**campaign, **updates}
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE volume_campaigns SET
                    user_wallet = %(user_wallet)s,
                    name = %(name)s,
                    base_token = %(base_token)s,
                    quote_token = %(quote_token)s,
                    base_mint = %(base_mint)s,
                    quote_mint = %(quote_mint)s,
                    pool_address = %(pool_address)s,
                    pool_exists = %(pool_exists)s,
                    pool_creation_cost_sol = %(pool_creation_cost_sol)s,
                    trade_amount = %(trade_amount)s,
                    interval_label = %(interval)s,
                    interval_minutes = %(interval_minutes)s,
                    total_budget = %(total_budget)s,
                    spent_so_far = %(spent_so_far)s,
                    max_executions = %(max_executions)s,
                    executions_count = %(executions_count)s,
                    slippage_bps = %(slippage_bps)s,
                    platform_fee_rate = %(platform_fee_rate)s,
                    status = %(status)s,
                    created_at = %(created_at)s,
                    next_execution_at = %(next_execution_at)s,
                    executions = %(executions)s,
                    infrastructure = %(infrastructure)s,
                    consecutive_failures = %(consecutive_failures)s,
                    last_error = %(last_error)s
                WHERE id = %(id)s
                """,
                {
                    "id": campaign_id,
                    "user_wallet": merged.get("user_wallet"),
                    "name": merged["name"],
                    "base_token": merged["base_token"],
                    "quote_token": merged.get("quote_token", "SOL"),
                    "base_mint": merged["base_mint"],
                    "quote_mint": merged["quote_mint"],
                    "pool_address": merged.get("pool_address"),
                    "pool_exists": bool(merged.get("pool_exists")),
                    "pool_creation_cost_sol": merged.get("pool_creation_cost_sol", 0.02669),
                    "trade_amount": merged["trade_amount"],
                    "interval": merged["interval"],
                    "interval_minutes": merged["interval_minutes"],
                    "total_budget": merged.get("total_budget"),
                    "spent_so_far": merged.get("spent_so_far", 0),
                    "max_executions": merged.get("max_executions"),
                    "executions_count": merged.get("executions_count", 0),
                    "slippage_bps": merged.get("slippage_bps", 100),
                    "platform_fee_rate": merged.get("platform_fee_rate", 0.0025),
                    "status": merged.get("status", "provisioning"),
                    "created_at": merged.get("created_at"),
                    "next_execution_at": merged.get("next_execution_at"),
                    "executions": Json(merged.get("executions") or []),
                    "infrastructure": Json(merged.get("infrastructure") or {}),
                    "consecutive_failures": merged.get("consecutive_failures") or 0,
                    "last_error": Json(merged["last_error"]) if merged.get("last_error") is not None else None,
                },
            )
    return find_volume_campaign(campaign_id)


def get_or_create_wallet_index(user_wallet: str) -> int:
    """Return this user's per-user agent-wallet derivation index, assigning one
    on first use. Safe under concurrency: the index comes from a Postgres SERIAL
    (atomic fetch-and-increment, no locking needed) and the insert uses
    ON CONFLICT DO NOTHING, so two simultaneous first-time calls for the same
    user can never end up with two different indices, and two different users
    can never end up with the same one.
    """
    init_db()
    user_wallet = user_wallet.strip()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT wallet_index FROM agent_wallet_index WHERE user_wallet = %s",
                (user_wallet,),
            )
            row = cur.fetchone()
            if row:
                return int(row["wallet_index"])
            cur.execute(
                """
                INSERT INTO agent_wallet_index (user_wallet)
                VALUES (%s)
                ON CONFLICT (user_wallet) DO NOTHING
                RETURNING wallet_index
                """,
                (user_wallet,),
            )
            row = cur.fetchone()
            if row:
                return int(row["wallet_index"])
    # Someone else's insert won the race between our SELECT and INSERT above --
    # re-select outside that transaction to read the winning row.
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT wallet_index FROM agent_wallet_index WHERE user_wallet = %s",
                (user_wallet,),
            )
            row = cur.fetchone()
    if not row:
        raise RuntimeError(f"Failed to assign a wallet index for {user_wallet}")
    return int(row["wallet_index"])
