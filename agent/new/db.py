"""
Neon PostgreSQL persistence for DCA plans, user deposit ledger, and chat sessions.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import psycopg2
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
        executions          JSONB NOT NULL DEFAULT '[]'::jsonb
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
]

MIGRATION_STATEMENTS = [
    "ALTER TABLE user_ledger ALTER COLUMN reference_id TYPE VARCHAR(128)",
    "ALTER TABLE user_ledger ALTER COLUMN signature TYPE VARCHAR(128)",
    """
    CREATE TABLE IF NOT EXISTS schema_repairs (
        id          VARCHAR(64) PRIMARY KEY,
        applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        notes       TEXT
    )
    """,
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
    # ── Hedge Fund paper trading ──────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS hf_market_snapshots (
        symbol              VARCHAR(32) PRIMARY KEY,
        yahoo_symbol        VARCHAR(32) NOT NULL,
        asset_class         VARCHAR(16) NOT NULL DEFAULT 'equity',
        price_usd           DOUBLE PRECISION,
        change_24h_pct      DOUBLE PRECISION,
        volume              DOUBLE PRECISION,
        raw                 JSONB NOT NULL DEFAULT '{}'::jsonb,
        fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS hf_paper_portfolios (
        id                  VARCHAR(16) PRIMARY KEY,
        user_wallet         VARCHAR(64) NOT NULL,
        name                TEXT NOT NULL DEFAULT 'Paper Book',
        cash_usd            DOUBLE PRECISION NOT NULL DEFAULT 10000,
        starting_capital    DOUBLE PRECISION NOT NULL DEFAULT 10000,
        status              VARCHAR(20) NOT NULL DEFAULT 'active',
        created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_hf_paper_portfolios_user ON hf_paper_portfolios (user_wallet)",
    """
    CREATE TABLE IF NOT EXISTS hf_strategies (
        id                  VARCHAR(16) PRIMARY KEY,
        portfolio_id        VARCHAR(16) NOT NULL REFERENCES hf_paper_portfolios(id) ON DELETE CASCADE,
        user_wallet         VARCHAR(64) NOT NULL,
        name                TEXT NOT NULL,
        mode                VARCHAR(24) NOT NULL DEFAULT 'agent',
        status              VARCHAR(20) NOT NULL DEFAULT 'active',
        symbols             JSONB NOT NULL DEFAULT '[]'::jsonb,
        allocation_pct      JSONB NOT NULL DEFAULT '{}'::jsonb,
        rules               JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_by          VARCHAR(16) NOT NULL DEFAULT 'agent',
        horizon_days        INTEGER,
        horizon_label       VARCHAR(32),
        created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        last_evaluated_at   TIMESTAMPTZ
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_hf_strategies_user ON hf_strategies (user_wallet)",
    "CREATE INDEX IF NOT EXISTS idx_hf_strategies_status ON hf_strategies (status)",
    """
    CREATE TABLE IF NOT EXISTS hf_paper_positions (
        id                  VARCHAR(16) PRIMARY KEY,
        portfolio_id        VARCHAR(16) NOT NULL REFERENCES hf_paper_portfolios(id) ON DELETE CASCADE,
        strategy_id         VARCHAR(16) REFERENCES hf_strategies(id) ON DELETE SET NULL,
        symbol              VARCHAR(32) NOT NULL,
        units               DOUBLE PRECISION NOT NULL DEFAULT 0,
        avg_entry_usd       DOUBLE PRECISION NOT NULL DEFAULT 0,
        mark_price_usd      DOUBLE PRECISION,
        updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_hf_paper_positions_portfolio ON hf_paper_positions (portfolio_id)",
    "CREATE INDEX IF NOT EXISTS idx_hf_paper_positions_strategy ON hf_paper_positions (strategy_id)",
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_hf_pos_portfolio_strategy_symbol
        ON hf_paper_positions (portfolio_id, strategy_id, symbol)
    """,
    """
    CREATE TABLE IF NOT EXISTS hf_paper_trades (
        id                  VARCHAR(16) PRIMARY KEY,
        portfolio_id        VARCHAR(16) NOT NULL,
        strategy_id         VARCHAR(16),
        user_wallet         VARCHAR(64) NOT NULL,
        symbol              VARCHAR(32) NOT NULL,
        side                VARCHAR(8) NOT NULL,
        units               DOUBLE PRECISION NOT NULL,
        price_usd           DOUBLE PRECISION NOT NULL,
        notional_usd        DOUBLE PRECISION NOT NULL,
        reason              TEXT,
        decision            VARCHAR(16),
        created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_hf_paper_trades_portfolio ON hf_paper_trades (portfolio_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_hf_paper_trades_user ON hf_paper_trades (user_wallet, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_hf_paper_trades_strategy ON hf_paper_trades (strategy_id, created_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS hf_decisions (
        id                  VARCHAR(16) PRIMARY KEY,
        strategy_id         VARCHAR(16) NOT NULL,
        portfolio_id        VARCHAR(16) NOT NULL,
        user_wallet         VARCHAR(64) NOT NULL,
        symbol              VARCHAR(32) NOT NULL,
        action              VARCHAR(16) NOT NULL,
        confidence          DOUBLE PRECISION,
        rationale           TEXT,
        price_usd           DOUBLE PRECISION,
        executed            BOOLEAN NOT NULL DEFAULT FALSE,
        trade_id            VARCHAR(16),
        signals             JSONB NOT NULL DEFAULT '[]'::jsonb,
        decision_graph      JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_hf_decisions_strategy ON hf_decisions (strategy_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_hf_decisions_user ON hf_decisions (user_wallet, created_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS hf_backtest_runs (
        id                  VARCHAR(16) PRIMARY KEY,
        strategy_id         VARCHAR(16),
        user_wallet         VARCHAR(64) NOT NULL,
        period_label        VARCHAR(16) NOT NULL,
        start_date          DATE NOT NULL,
        end_date            DATE NOT NULL,
        symbols             JSONB NOT NULL DEFAULT '[]'::jsonb,
        rules               JSONB NOT NULL DEFAULT '{}'::jsonb,
        result              JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_hf_backtest_runs_user ON hf_backtest_runs (user_wallet, created_at DESC)",
    # Retrofit existing Neon DBs
    "ALTER TABLE hf_strategies ADD COLUMN IF NOT EXISTS horizon_days INTEGER",
    "ALTER TABLE hf_strategies ADD COLUMN IF NOT EXISTS horizon_label VARCHAR(32)",
    "ALTER TABLE hf_strategies ADD COLUMN IF NOT EXISTS trading_mode VARCHAR(16) DEFAULT 'paper'",
    """
    CREATE TABLE IF NOT EXISTS hf_live_positions (
        id                  VARCHAR(16) PRIMARY KEY,
        strategy_id         VARCHAR(16) NOT NULL REFERENCES hf_strategies(id) ON DELETE CASCADE,
        user_wallet         VARCHAR(64) NOT NULL,
        symbol              VARCHAR(32) NOT NULL,
        mint                VARCHAR(64) NOT NULL,
        units               DOUBLE PRECISION NOT NULL DEFAULT 0,
        avg_entry_usd       DOUBLE PRECISION NOT NULL DEFAULT 0,
        cost_basis_usd      DOUBLE PRECISION NOT NULL DEFAULT 0,
        updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (strategy_id, mint)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_hf_live_positions_strategy ON hf_live_positions (strategy_id)",
    "CREATE INDEX IF NOT EXISTS idx_hf_live_positions_user ON hf_live_positions (user_wallet)",
    """
    CREATE TABLE IF NOT EXISTS hf_live_trades (
        id                  VARCHAR(16) PRIMARY KEY,
        strategy_id         VARCHAR(16) NOT NULL,
        user_wallet         VARCHAR(64) NOT NULL,
        symbol              VARCHAR(32) NOT NULL,
        mint                VARCHAR(64),
        side                VARCHAR(8) NOT NULL,
        units               DOUBLE PRECISION NOT NULL,
        price_usd           DOUBLE PRECISION,
        notional_usd        DOUBLE PRECISION NOT NULL,
        fee_usd             DOUBLE PRECISION NOT NULL DEFAULT 0,
        input_mint          VARCHAR(64),
        output_mint         VARCHAR(64),
        signature           TEXT,
        explorer_url        TEXT,
        reason              TEXT,
        created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_hf_live_trades_strategy ON hf_live_trades (strategy_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_hf_live_trades_user ON hf_live_trades (user_wallet, created_at DESC)",
    "ALTER TABLE hf_decisions ADD COLUMN IF NOT EXISTS signals JSONB NOT NULL DEFAULT '[]'::jsonb",
    "ALTER TABLE hf_decisions ADD COLUMN IF NOT EXISTS decision_graph JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE hf_paper_positions DROP CONSTRAINT IF EXISTS hf_paper_positions_portfolio_id_symbol_key",
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_hf_pos_portfolio_strategy_symbol
        ON hf_paper_positions (portfolio_id, strategy_id, symbol)
    """,
    """
    CREATE TABLE IF NOT EXISTS dca_user_agent_wallets (
        user_wallet             VARCHAR(64) PRIMARY KEY,
        agent_wallet_address    VARCHAR(64) NOT NULL,
        circle_wallet_id        VARCHAR(64) NOT NULL,
        circle_wallet_set_id    VARCHAR(64),
        blockchain              VARCHAR(32) NOT NULL,
        created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_dca_user_agent_wallets_circle ON dca_user_agent_wallets (circle_wallet_id)",
    """
    CREATE TABLE IF NOT EXISTS user_agent_wallets (
        user_wallet             VARCHAR(64) NOT NULL,
        agent_type              VARCHAR(32) NOT NULL,
        agent_wallet_address    VARCHAR(64) NOT NULL,
        circle_wallet_id        VARCHAR(64) NOT NULL,
        circle_wallet_set_id    VARCHAR(64),
        blockchain              VARCHAR(32) NOT NULL,
        created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (user_wallet, agent_type)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_user_agent_wallets_circle ON user_agent_wallets (circle_wallet_id)",
    "CREATE INDEX IF NOT EXISTS idx_user_agent_wallets_type ON user_agent_wallets (agent_type)",
    # Migrate legacy DCA Circle rows into the multi-agent table.
    """
    INSERT INTO user_agent_wallets (
        user_wallet, agent_type, agent_wallet_address, circle_wallet_id,
        circle_wallet_set_id, blockchain, created_at
    )
    SELECT
        user_wallet, 'dca', agent_wallet_address, circle_wallet_id,
        circle_wallet_set_id, blockchain, created_at
    FROM dca_user_agent_wallets
    ON CONFLICT (user_wallet, agent_type) DO NOTHING
    """,
]


def db_configured() -> bool:
    return bool(get_database_url())


def _require_db() -> None:
    if not get_database_url():
        raise RuntimeError(
            "DATABASE_URL is not set. Add your Neon connection string to agent/new/.env"
        )


@contextmanager
def get_conn():
    _require_db()
    conn = psycopg2.connect(
        get_database_url(),
        cursor_factory=RealDictCursor,
        connect_timeout=15,
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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
            _repair_bitagents_decimal_scale(conn)
            # _repair_dca_circle_ledger_migration(conn)  # Migration completed 2026-09-10
        _schema_ready = True

    if _import_done:
        return
    with _db_lock:
        if _import_done:
            return
        _import_json_if_empty()
        _import_done = True


def _repair_bitagents_decimal_scale(conn) -> None:
    """
    BITAGENTS decimal repair guard + automatic reverse of the bad v1 multiply.

    v1 (`bitagents_decimals_9_to_6_v1`) wrongly multiplied live amounts x1000
    on 2026-09-10. That multiply path must never run again.

    When v1 notes show it actually scaled rows (`user_ledger=`), this applies
    `bitagents_decimals_9_to_6_v1_revert` once: divide the same tables by 1000.
    """
    mint = "iu3A7azWTm3zQSk81SUC1JctB4zPYnxLmcmqq71EASY"
    scale = 1000.0  # 10 ** (9 - 6)
    repair_id_v1 = "bitagents_decimals_9_to_6_v1"
    repair_id_revert = "bitagents_decimals_9_to_6_v1_revert"

    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_repairs (
                id          VARCHAR(64) PRIMARY KEY,
                applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                notes       TEXT
            )
            """
        )
        cur.execute(
            "SELECT id, notes FROM schema_repairs WHERE id IN (%s, %s)",
            (repair_id_v1, repair_id_revert),
        )
        rows = {str(r["id"]): str(r.get("notes") or "") for r in cur.fetchall()}

        # If v1 never ran on this DB, insert a SKIPPED marker so the old
        # multiply code path can never fire on a fresh deploy.
        if repair_id_v1 not in rows:
            cur.execute(
                """
                INSERT INTO schema_repairs (id, notes)
                VALUES (%s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    repair_id_v1,
                    "SKIPPED: original x1000 repair was incorrect for live data; "
                    "marker only so it cannot run.",
                ),
            )
            print("  BITAGENTS x1000 repair skipped (marker only).")
            return

        if repair_id_revert in rows:
            return

        notes_v1 = rows.get(repair_id_v1, "")
        # Do not reverse marker-only / already-clean DBs.
        if "SKIPPED" in notes_v1 or "user_ledger=" not in notes_v1:
            return

        cur.execute(
            """
            UPDATE user_ledger
            SET amount = amount / %s
            WHERE mint = %s AND amount IS NOT NULL AND amount <> 0
            """,
            (scale, mint),
        )
        ledger_n = cur.rowcount

        cur.execute(
            """
            UPDATE easya_orders
            SET output_amount = output_amount / %s
            WHERE output_mint = %s
              AND output_amount IS NOT NULL
              AND output_amount <> 0
            """,
            (scale, mint),
        )
        orders_n = cur.rowcount

        cur.execute(
            """
            UPDATE easya_order_executions e
            SET output_amount = e.output_amount / %s
            FROM easya_orders o
            WHERE e.order_id = o.id
              AND o.output_mint = %s
              AND e.output_amount IS NOT NULL
              AND e.output_amount <> 0
            """,
            (scale, mint),
        )
        exec_n = cur.rowcount

        cur.execute(
            """
            INSERT INTO schema_repairs (id, notes)
            VALUES (%s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                repair_id_revert,
                f"Reverted BITAGENTS x{scale:g} inflation "
                f"(user_ledger={ledger_n}, easya_orders={orders_n}, executions={exec_n})",
            ),
        )
        print(
            f"  Reverted BITAGENTS decimal inflation /{scale:g}: "
            f"ledger={ledger_n}, orders={orders_n}, executions={exec_n}"
        )


def _repair_dca_circle_ledger_migration(conn) -> None:
    """
    [COMPLETED 2026-09-10] Circle DCA wallet ledger migration.
    
    This migration has been successfully completed and should NOT be run again.
    Moved 30 transfers (60 ledger rows) from shared -> Circle wallets.
    
    Original purpose:
    Move ledger credits from shared DCA wallet -> Circle wallets for completed
    on-chain migration transfers (idempotent by signature).

    Without this, the UI shows the Circle address but still credits old shared
    (and cross-agent) ledger rows — e.g. SOL/USDC that were never migrated.
    """
    repair_id = "dca_circle_ledger_migration_v1"
    env_path = os.environ.get("DCA_CIRCLE_MIGRATION_LEDGER_FILE", "").strip()
    candidates = []
    if env_path:
        candidates.append(Path(env_path))
    candidates.extend(
        [
            AGENT_DIR / "migrations" / "dca_transfers_final.json",
            REPO_ROOT / "temp" / "wallet_migration" / "dca_transfers_final.json",
        ]
    )
    path = next((p for p in candidates if p.is_file()), None)

    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_repairs (
                id          VARCHAR(64) PRIMARY KEY,
                applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                notes       TEXT
            )
            """
        )
        cur.execute("SELECT 1 FROM schema_repairs WHERE id = %s", (repair_id,))
        if cur.fetchone():
            return

        if path is None:
            print(
                "  [skip] DCA Circle ledger migration file missing "
                f"(checked {[str(p) for p in candidates]})"
            )
            return

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  [warn] Could not read {path}: {exc}")
            return

        shared = str(payload.get("from") or "").strip()
        transfers = payload.get("transfers") or []
        if not shared or not isinstance(transfers, list):
            print(f"  [warn] Invalid migration ledger file: {path}")
            return

        # circle address -> user wallet
        cur.execute(
            """
            SELECT agent_wallet_address, user_wallet
            FROM user_agent_wallets
            WHERE agent_type = 'dca'
            """
        )
        circle_to_user = {
            str(r["agent_wallet_address"]).strip(): str(r["user_wallet"]).strip()
            for r in cur.fetchall()
            if r.get("agent_wallet_address") and r.get("user_wallet")
        }

        moved = 0
        already = 0
        pending_unmapped = 0
        invalid = 0
        now = datetime.now(timezone.utc).isoformat()

        for t in transfers:
            if not isinstance(t, dict):
                invalid += 1
                continue
            circle = str(t.get("to") or "").strip()
            token = str(t.get("token") or "").strip().upper()
            mint = str(t.get("mint") or "").strip() or None
            trx = str(t.get("trx") or "").strip()
            try:
                amount = float(t.get("amount") or 0)
            except (TypeError, ValueError):
                amount = 0.0
            if not circle or not token or amount <= 0 or not trx:
                invalid += 1
                continue
            user = circle_to_user.get(circle)
            if not user:
                pending_unmapped += 1
                continue

            # Keep under VARCHAR(128); Solana sigs are ~88 chars.
            sig_in = f"{trx}:c-in"
            sig_out = f"{trx}:s-out"
            cur.execute(
                "SELECT 1 FROM user_ledger WHERE signature = %s LIMIT 1",
                (sig_in,),
            )
            if cur.fetchone():
                already += 1
                continue

            # Debit shared wallet liability
            cur.execute(
                """
                INSERT INTO user_ledger (
                    id, user_wallet, agent_wallet, signature, token, mint,
                    amount, direction, reference_type, reference_id,
                    status, verified_at, explorer_url
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, 'withdraw', 'circle_migration', %s,
                    'confirmed', %s, %s
                )
                """,
                (
                    str(uuid.uuid4())[:8],
                    user,
                    shared,
                    sig_out,
                    token,
                    mint,
                    amount,
                    trx[:120],
                    now,
                    f"https://explorer.solana.com/tx/{trx}",
                ),
            )
            # Credit Circle wallet (acquire keeps withdrawable semantics for SPL)
            direction_in = "deposit" if token == "SOL" else "acquire"
            cur.execute(
                """
                INSERT INTO user_ledger (
                    id, user_wallet, agent_wallet, signature, token, mint,
                    amount, direction, reference_type, reference_id,
                    status, verified_at, explorer_url
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, 'circle_migration', %s,
                    'confirmed', %s, %s
                )
                """,
                (
                    str(uuid.uuid4())[:8],
                    user,
                    circle,
                    sig_in,
                    token,
                    mint,
                    amount,
                    direction_in,
                    trx[:120],
                    now,
                    f"https://explorer.solana.com/tx/{trx}",
                ),
            )
            moved += 1

        # Do not seal the repair while Circle rows are still missing — retry next boot.
        if pending_unmapped > 0:
            print(
                f"  DCA Circle ledger migration pending: moved={moved} "
                f"already={already} unmapped={pending_unmapped} invalid={invalid} "
                f"from {path.name} (will retry)"
            )
            return

        cur.execute(
            """
            INSERT INTO schema_repairs (id, notes)
            VALUES (%s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                repair_id,
                f"Moved {moved} transfer(s) shared->Circle ledger "
                f"(already={already}, invalid={invalid}, file={path.name})",
            ),
        )
        print(
            f"  DCA Circle ledger migration: moved={moved} already={already} "
            f"invalid={invalid} from {path.name}"
        )


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
                    next_execution_at, executions
                ) VALUES (
                    %(id)s, %(user_wallet)s, %(name)s, %(input_token)s, %(output_token)s,
                    %(input_mint)s, %(output_mint)s, %(amount_per_buy)s, %(interval)s,
                    %(interval_minutes)s, %(total_budget)s, %(spent_so_far)s, %(max_executions)s,
                    %(executions_count)s, %(slippage_bps)s, %(status)s, %(created_at)s,
                    %(next_execution_at)s, %(executions)s
                )
                """,
                {
                    **plan,
                    "interval": plan.get("interval"),
                    "executions": Json(plan.get("executions") or []),
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
                    "SELECT * FROM volume_campaigns WHERE user_wallet = %s ORDER BY created_at DESC",
                    (user_wallet.strip(),),
                )
            else:
                cur.execute("SELECT * FROM volume_campaigns ORDER BY created_at DESC")
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


def get_user_agent_wallet(user_wallet: str, agent_type: str) -> Optional[dict[str, Any]]:
    init_db()
    wallet = (user_wallet or "").strip()
    agent = (agent_type or "").strip().lower()
    if not wallet or not agent:
        return None
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_wallet, agent_type, agent_wallet_address, circle_wallet_id,
                       circle_wallet_set_id, blockchain, created_at
                FROM user_agent_wallets
                WHERE user_wallet = %s AND agent_type = %s
                """,
                (wallet, agent),
            )
            row = cur.fetchone()
    if not row:
        return None
    return {
        "user_wallet": row["user_wallet"],
        "agent_type": row["agent_type"],
        "agent_wallet_address": row["agent_wallet_address"],
        "circle_wallet_id": row["circle_wallet_id"],
        "circle_wallet_set_id": row.get("circle_wallet_set_id"),
        "blockchain": row["blockchain"],
        "created_at": _iso(row.get("created_at")),
    }


def save_user_agent_wallet(record: dict[str, Any]) -> dict[str, Any]:
    init_db()
    wallet = (record.get("user_wallet") or "").strip()
    agent_type = (record.get("agent_type") or "dca").strip().lower()
    if not wallet:
        raise ValueError("user_wallet is required")
    if not agent_type:
        raise ValueError("agent_type is required")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_agent_wallets (
                    user_wallet, agent_type, agent_wallet_address, circle_wallet_id,
                    circle_wallet_set_id, blockchain
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_wallet, agent_type) DO UPDATE SET
                    agent_wallet_address = EXCLUDED.agent_wallet_address,
                    circle_wallet_id = EXCLUDED.circle_wallet_id,
                    circle_wallet_set_id = COALESCE(
                        EXCLUDED.circle_wallet_set_id, user_agent_wallets.circle_wallet_set_id
                    ),
                    blockchain = EXCLUDED.blockchain
                """,
                (
                    wallet,
                    agent_type,
                    record["agent_wallet_address"],
                    record["circle_wallet_id"],
                    record.get("circle_wallet_set_id"),
                    record.get("blockchain") or "SOL-DEVNET",
                ),
            )
            # Keep legacy DCA table in sync for older readers.
            if agent_type == "dca":
                cur.execute(
                    """
                    INSERT INTO dca_user_agent_wallets (
                        user_wallet, agent_wallet_address, circle_wallet_id,
                        circle_wallet_set_id, blockchain
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (user_wallet) DO UPDATE SET
                        agent_wallet_address = EXCLUDED.agent_wallet_address,
                        circle_wallet_id = EXCLUDED.circle_wallet_id,
                        circle_wallet_set_id = COALESCE(
                            EXCLUDED.circle_wallet_set_id, dca_user_agent_wallets.circle_wallet_set_id
                        ),
                        blockchain = EXCLUDED.blockchain
                    """,
                    (
                        wallet,
                        record["agent_wallet_address"],
                        record["circle_wallet_id"],
                        record.get("circle_wallet_set_id"),
                        record.get("blockchain") or "SOL-DEVNET",
                    ),
                )
    saved = get_user_agent_wallet(wallet, agent_type)
    if not saved:
        raise RuntimeError("Failed to persist user agent wallet.")
    return saved


def get_dca_user_agent_wallet(user_wallet: str) -> Optional[dict[str, Any]]:
    return get_user_agent_wallet(user_wallet, "dca")


def save_dca_user_agent_wallet(record: dict[str, Any]) -> dict[str, Any]:
    payload = dict(record)
    payload["agent_type"] = "dca"
    return save_user_agent_wallet(payload)
