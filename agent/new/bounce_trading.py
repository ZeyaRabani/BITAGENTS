"""
Entry/exit execution for the Bounce Agent (and other price-signal strategy
agents). This is the only module that actually spends real capital -- every
other piece (signal_watcher.py detection, bounce_ledger.py accounting) is
read-only or pure bookkeeping.

Safety model, deliberate and not accidental:
  - Opening a position (committing new capital) always requires the caller
    to have already gotten explicit human confirmation. This module does
    not decide whether to open a position -- see launch_agent.py's
    CONFIRMATION_REQUIRED_TOOLS gating, which must happen before
    open_position() is ever called.
  - Closing a position on a stop-loss or take-profit does NOT require a
    fresh confirmation each time it fires -- the user already authorized
    exactly that exit condition when they confirmed the entry. This mirrors
    the existing, already-in-production pattern in hedge_fund_paper.py
    (run_horizon_close_cycle), not a new invention.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from db import get_conn, init_db
from dca_agent import SOL_ADDRESS_FULL, resolve_token
from hedge_fund_live import execute_agent_jupiter_swap
from bounce_ledger import (
    AGENT_TYPE,
    check_bounce_can_spend,
    get_bounce_wallet_pubkey,
    record_bounce_credit,
    record_bounce_spend,
)

MIN_POSITION_SOL = 0.005  # below this, fees/slippage dominate the trade


def ensure_bounce_trading_schema() -> None:
    init_db()
    statements = [
        """
        CREATE TABLE IF NOT EXISTS bounce_positions (
            position_id         VARCHAR(40) PRIMARY KEY,
            user_wallet          VARCHAR(64) NOT NULL,
            agent_id             VARCHAR(32),
            watch_id              VARCHAR(40),
            symbol               VARCHAR(16) NOT NULL,
            token_mint           VARCHAR(64) NOT NULL,
            token_decimals       INTEGER NOT NULL,
            entry_sol_amount     DOUBLE PRECISION NOT NULL,
            entry_token_amount   DOUBLE PRECISION NOT NULL,
            entry_price_usd      DOUBLE PRECISION,
            entry_signature      VARCHAR(128),
            stop_price_usd       DOUBLE PRECISION NOT NULL,
            target_price_usd     DOUBLE PRECISION NOT NULL,
            status               VARCHAR(16) NOT NULL DEFAULT 'open',
            close_reason         VARCHAR(32),
            close_sol_amount     DOUBLE PRECISION,
            close_price_usd      DOUBLE PRECISION,
            close_signature      VARCHAR(128),
            created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            closed_at            TIMESTAMPTZ
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_bounce_positions_user ON bounce_positions (user_wallet)",
        "CREATE INDEX IF NOT EXISTS idx_bounce_positions_status ON bounce_positions (status)",
    ]
    with get_conn() as conn:
        with conn.cursor() as cur:
            for stmt in statements:
                cur.execute(stmt)


def open_position(
    *,
    user_wallet: str,
    agent_id: Optional[str],
    watch_id: Optional[str],
    symbol: str,
    amount_sol: float,
    stop_loss_pct: float,
    take_profit_pct: float,
) -> dict[str, Any]:
    """Spend amount_sol buying `symbol`, recording the position and ledger entry.

    Capital is always deposited and withdrawn as SOL (see bounce_ledger.py) --
    `symbol` is the token this position actually swaps into, and must be a
    different token. Buying "SOL" with SOL capital isn't a real trade, it's
    a same-asset swap with nothing to gain and only fees to lose.

    Caller must have already obtained explicit human confirmation -- this
    function does not ask for it and will execute immediately.
    """
    ensure_bounce_trading_schema()
    amount_sol = round(float(amount_sol), 9)
    if amount_sol < MIN_POSITION_SOL:
        return {"error": f"Position size must be at least {MIN_POSITION_SOL} SOL (fees/slippage dominate below that)."}
    if stop_loss_pct <= 0 or take_profit_pct <= 0:
        return {"error": "stop_loss_pct and take_profit_pct must both be positive percentages."}

    can_spend = check_bounce_can_spend(user_wallet, amount_sol, "SOL")
    if not can_spend.get("ok"):
        return can_spend

    tok = resolve_token(symbol)
    if "error" in tok:
        return tok
    if tok["symbol"].upper() in ("SOL", "WSOL"):
        return {
            "error": (
                "Can't open a SOL position with SOL capital -- that's a self-swap, not a trade. "
                "Pick a different token to swap into (e.g. a stablecoin or another token), "
                "watched for its own dip-then-bounce pattern."
            )
        }

    import signal_watcher as sw

    entry_price = sw.sample_price(tok["symbol"])
    if entry_price is None:
        return {"error": f"Could not get a current price for {tok['symbol']}; aborted before spending anything."}

    swap = execute_agent_jupiter_swap(
        agent_type=AGENT_TYPE,
        input_mint=SOL_ADDRESS_FULL,
        output_mint=tok["mint"],
        amount=amount_sol,
        input_decimals=9,
        user_wallet=user_wallet,
    )
    if swap.get("error") or swap.get("status") != "success":
        return {"error": swap.get("error") or "Buy swap failed.", "swap": swap}

    out_raw = int(swap.get("output_amount_raw") or 0)
    entry_token_amount = out_raw / (10 ** tok["decimals"]) if out_raw > 0 else 0.0
    if entry_token_amount <= 0:
        return {"error": "Swap reported success but no output amount was returned. Not recording a position.", "swap": swap}

    record_bounce_spend(
        user_wallet, amount_sol,
        reference_id=swap.get("signature") or uuid.uuid4().hex,
        signature=swap.get("signature"),
        explorer_url=swap.get("explorer_url"),
    )

    stop_price = entry_price * (1 - stop_loss_pct / 100.0)
    target_price = entry_price * (1 + take_profit_pct / 100.0)
    position_id = f"bp_{uuid.uuid4().hex[:12]}"

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bounce_positions (
                    position_id, user_wallet, agent_id, watch_id, symbol, token_mint, token_decimals,
                    entry_sol_amount, entry_token_amount, entry_price_usd, entry_signature,
                    stop_price_usd, target_price_usd, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'open')
                RETURNING *
                """,
                (
                    position_id, user_wallet.strip(), agent_id, watch_id, tok["symbol"], tok["mint"], tok["decimals"],
                    amount_sol, entry_token_amount, entry_price, swap.get("signature"),
                    stop_price, target_price,
                ),
            )
            row = cur.fetchone()
    return dict(row)


def close_position(position_id: str, *, reason: str) -> dict[str, Any]:
    """Sell the full position back to SOL and record the ledger credit."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM bounce_positions WHERE position_id = %s", (position_id,))
            pos = cur.fetchone()
    if not pos:
        return {"error": "Position not found."}
    pos = dict(pos)
    if pos["status"] != "open":
        return {"error": f"Position is already {pos['status']}."}

    swap = execute_agent_jupiter_swap(
        agent_type=AGENT_TYPE,
        input_mint=pos["token_mint"],
        output_mint=SOL_ADDRESS_FULL,
        amount=pos["entry_token_amount"],
        input_decimals=pos["token_decimals"],
        user_wallet=pos["user_wallet"],
    )
    if swap.get("error") or swap.get("status") != "success":
        return {"error": swap.get("error") or "Sell swap failed. Position left open.", "swap": swap}

    out_raw = int(swap.get("output_amount_raw") or 0)
    sol_received = out_raw / 1e9 if out_raw > 0 else 0.0

    record_bounce_credit(
        pos["user_wallet"], sol_received,
        reference_id=swap.get("signature") or uuid.uuid4().hex,
        signature=swap.get("signature"),
        explorer_url=swap.get("explorer_url"),
    )

    import signal_watcher as sw
    close_price = sw.sample_price(pos["symbol"])

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE bounce_positions
                SET status = 'closed', close_reason = %s, close_sol_amount = %s,
                    close_price_usd = %s, close_signature = %s, closed_at = NOW()
                WHERE position_id = %s
                RETURNING *
                """,
                (reason, sol_received, close_price, swap.get("signature"), position_id),
            )
            row = cur.fetchone()
    return dict(row)


def evaluate_position(position_id: str) -> dict[str, Any]:
    """Check current price against stop/target. Closes and executes the sell
    automatically if either is hit -- no fresh confirmation, see module
    docstring for why that's the correct, pre-authorized behavior."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM bounce_positions WHERE position_id = %s", (position_id,))
            pos = cur.fetchone()
    if not pos:
        return {"error": "Position not found."}
    pos = dict(pos)
    if pos["status"] != "open":
        return {"position_id": position_id, "status": pos["status"]}

    import signal_watcher as sw

    price = sw.sample_price(pos["symbol"])
    if price is None:
        return {"position_id": position_id, "status": "open", "error": "price unavailable"}

    if price <= pos["stop_price_usd"]:
        return close_position(position_id, reason="stop_loss")
    if price >= pos["target_price_usd"]:
        return close_position(position_id, reason="take_profit")
    return {
        "position_id": position_id,
        "status": "open",
        "symbol": pos["symbol"],
        "price_usd": price,
        "stop_price_usd": pos["stop_price_usd"],
        "target_price_usd": pos["target_price_usd"],
        "unrealized_pct": round((price - pos["entry_price_usd"]) / pos["entry_price_usd"] * 100, 4)
        if pos["entry_price_usd"]
        else None,
    }


def list_positions_for_user(user_wallet: str, *, status: Optional[str] = None) -> list[dict[str, Any]]:
    ensure_bounce_trading_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            if status:
                cur.execute(
                    "SELECT * FROM bounce_positions WHERE user_wallet = %s AND status = %s ORDER BY created_at DESC",
                    (user_wallet.strip(), status),
                )
            else:
                cur.execute(
                    "SELECT * FROM bounce_positions WHERE user_wallet = %s ORDER BY created_at DESC",
                    (user_wallet.strip(),),
                )
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def get_agent_breakdown(user_wallet: str) -> list[dict[str, Any]]:
    """Per-agent view into the one shared Bounce wallet: how much capital each
    individual launched agent currently has tied up in open positions, and
    its realized profit/loss from closed ones. Organizational visibility
    without needing a separate wallet per agent -- see the Oct 22 discussion
    on why per-instance wallets weren't worth the added complexity."""
    ensure_bounce_trading_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COALESCE(agent_id, 'unknown') AS agent_id,
                    COUNT(*) FILTER (WHERE status = 'open') AS open_positions,
                    COUNT(*) FILTER (WHERE status = 'closed') AS closed_positions,
                    COALESCE(SUM(entry_sol_amount) FILTER (WHERE status = 'open'), 0) AS capital_in_open_positions,
                    COALESCE(SUM(close_sol_amount - entry_sol_amount) FILTER (WHERE status = 'closed'), 0) AS realized_pnl_sol
                FROM bounce_positions
                WHERE user_wallet = %s
                GROUP BY agent_id
                ORDER BY agent_id
                """,
                (user_wallet.strip(),),
            )
            rows = cur.fetchall()
    return [dict(r) for r in rows]


# ─── Background exit monitor (same in-process scheduler pattern already
# proven by signal_watcher.py / DCA / Hedge Fund) ───────────────────────────

_scheduler_stop = None
_scheduler_thread = None
_POSITION_CHECK_SECONDS = 15


def _monitor_loop(stop_event) -> None:
    while not stop_event.is_set():
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT position_id FROM bounce_positions WHERE status = 'open'")
                    open_ids = [r["position_id"] for r in cur.fetchall()]
            for pid in open_ids:
                evaluate_position(pid)
        except Exception as exc:
            print(f"  warning: bounce position monitor tick failed: {exc}")
        stop_event.wait(_POSITION_CHECK_SECONDS)


def start_position_monitor() -> bool:
    import threading
    global _scheduler_stop, _scheduler_thread
    if _scheduler_thread is not None and _scheduler_thread.is_alive():
        return False
    ensure_bounce_trading_schema()
    _scheduler_stop = threading.Event()
    _scheduler_thread = threading.Thread(target=_monitor_loop, args=(_scheduler_stop,), daemon=True)
    _scheduler_thread.start()
    return True


def stop_position_monitor() -> None:
    if _scheduler_stop is not None:
        _scheduler_stop.set()
