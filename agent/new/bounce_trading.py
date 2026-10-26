"""
Entry/exit execution for the Bounce Agent (and other price-signal strategy
agents). This is the only module that actually spends real capital -- every
other piece (signal_watcher.py detection, bounce_ledger.py accounting) is
read-only or pure bookkeeping.

Capital is USDC (see bounce_ledger.BASE_TOKEN) -- the user deposits native
SOL, which gets auto-converted on arrival, so a position always swaps
USDC -> target token on entry and back to USDC on exit. This is also why
SOL is a valid, even expected, target token here: it's no longer the same
asset as the capital it's bought with.

Safety model, deliberate and not accidental:
  - Opening a position (committing new capital) always requires the caller
    to have already gotten explicit human confirmation. This module does
    not decide whether to open a position -- see launch_agent.py's
    BOUNCE_CONFIRMATION_REQUIRED_TOOLS gating, which must happen before
    open_position() is ever called.
  - Closing a position on a stop-loss or take-profit does NOT require a
    fresh confirmation each time it fires -- the user already authorized
    exactly that exit condition when they confirmed the entry. This mirrors
    the existing, already-in-production pattern in hedge_fund_paper.py
    (run_horizon_close_cycle), not a new invention.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from db import get_conn, init_db
from dca_agent import TOKEN_MINTS, resolve_token
from hedge_fund_live import execute_agent_jupiter_swap
from bounce_ledger import (
    AGENT_TYPE,
    BASE_TOKEN,
    check_bounce_can_spend,
    record_bounce_credit,
    record_bounce_spend,
)

USDC_MINT = TOKEN_MINTS["USDC"]["mint"]
USDC_DECIMALS = TOKEN_MINTS["USDC"]["decimals"]
MIN_POSITION_USDC = 1.0  # below this, Jupiter's multi-hop routing gets unreliable
# (confirmed live: a 0.1 USDC trade twice failed on-chain with Jupiter's own
# Custom:6024 InsufficientFunds -- not a balance problem, a routing one. At
# that size Jupiter sometimes picks a thin multi-hop path whose on-chain
# reserves don't match the quote by execution time; a plain quote for the
# same pair/amount seconds later came back as one direct hop with no issue.
# 1.0 USDC routes as a single hop far more consistently.


def set_agent_allocation_cap(agent_id: str, max_allocation_usdc: Optional[float]) -> dict[str, Any]:
    """None/0 or a negative number clears the cap (full wallet balance available)."""
    ensure_bounce_trading_schema()
    agent_id = (agent_id or "").strip()
    if not agent_id:
        return {"error": "agent_id is required"}
    cap = float(max_allocation_usdc) if max_allocation_usdc is not None else None
    if cap is not None and cap <= 0:
        cap = None
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bounce_agent_limits (agent_id, max_allocation_usdc, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (agent_id) DO UPDATE SET max_allocation_usdc = EXCLUDED.max_allocation_usdc, updated_at = NOW()
                RETURNING *
                """,
                (agent_id, cap),
            )
            row = cur.fetchone()
    return dict(row)


def get_agent_allocation_cap(agent_id: str) -> Optional[float]:
    ensure_bounce_trading_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT max_allocation_usdc FROM bounce_agent_limits WHERE agent_id = %s", ((agent_id or "").strip(),))
            row = cur.fetchone()
    return float(row["max_allocation_usdc"]) if row and row["max_allocation_usdc"] is not None else None


def set_agent_strategy(
    agent_id: str, *, symbol: str, profile: str = "real",
    stop_loss_pct: float, take_profit_pct: float, auto_trade: bool = True,
) -> dict[str, Any]:
    """Default strategy for an agent instance -- set once, not re-asked per
    user. Drives both what signal_watcher watches and the trade proposal
    auto-staged when it fires (see signal_watcher.py)."""
    ensure_bounce_trading_schema()
    agent_id = (agent_id or "").strip()
    if not agent_id:
        return {"error": "agent_id is required"}
    if stop_loss_pct <= 0 or take_profit_pct <= 0:
        return {"error": "stop_loss_pct and take_profit_pct must both be positive percentages."}
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bounce_agent_strategy (agent_id, symbol, profile, stop_loss_pct, take_profit_pct, auto_trade, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (agent_id) DO UPDATE SET
                    symbol = EXCLUDED.symbol, profile = EXCLUDED.profile,
                    stop_loss_pct = EXCLUDED.stop_loss_pct, take_profit_pct = EXCLUDED.take_profit_pct,
                    auto_trade = EXCLUDED.auto_trade, updated_at = NOW()
                RETURNING *
                """,
                (agent_id, symbol.strip().upper(), profile.strip().lower(), stop_loss_pct, take_profit_pct, auto_trade),
            )
            row = cur.fetchone()
    return dict(row)


def get_agent_strategy(agent_id: str) -> Optional[dict[str, Any]]:
    ensure_bounce_trading_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM bounce_agent_strategy WHERE agent_id = %s", ((agent_id or "").strip(),))
            row = cur.fetchone()
    return dict(row) if row else None


def _capital_in_open_positions(agent_id: str) -> float:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(SUM(entry_usdc_amount), 0) AS total FROM bounce_positions WHERE agent_id = %s AND status = 'open'",
                ((agent_id or "").strip(),),
            )
            row = cur.fetchone()
    return float(row["total"]) if row else 0.0


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
            entry_usdc_amount    DOUBLE PRECISION NOT NULL,
            entry_token_amount   DOUBLE PRECISION NOT NULL,
            entry_price_usd      DOUBLE PRECISION,
            entry_signature      VARCHAR(128),
            stop_price_usd       DOUBLE PRECISION NOT NULL,
            target_price_usd     DOUBLE PRECISION NOT NULL,
            status               VARCHAR(16) NOT NULL DEFAULT 'open',
            close_reason         VARCHAR(32),
            close_usdc_amount    DOUBLE PRECISION,
            close_price_usd      DOUBLE PRECISION,
            close_signature      VARCHAR(128),
            created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            closed_at            TIMESTAMPTZ
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_bounce_positions_user ON bounce_positions (user_wallet)",
        "CREATE INDEX IF NOT EXISTS idx_bounce_positions_status ON bounce_positions (status)",
        # Per-agent spending cap. A separate table, not a column on
        # launched_agents -- that table's own comment warns that an ALTER at
        # request time can deadlock under concurrent access. Default: no cap,
        # full wallet balance available, same as before this existed.
        """
        CREATE TABLE IF NOT EXISTS bounce_agent_limits (
            agent_id            VARCHAR(32) PRIMARY KEY,
            max_allocation_usdc DOUBLE PRECISION,
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        # Per-agent default strategy, set once (by whoever configures the
        # agent), so a user picking it up only ever answers "how much" --
        # not which token, what thresholds, what stop/target. See
        # set_agent_strategy / get_agent_strategy and signal_watcher.py's
        # auto-stage-on-fire hook, which reads this.
        """
        CREATE TABLE IF NOT EXISTS bounce_agent_strategy (
            agent_id         VARCHAR(32) PRIMARY KEY,
            symbol           VARCHAR(16) NOT NULL,
            profile          VARCHAR(16) NOT NULL DEFAULT 'real',
            stop_loss_pct    DOUBLE PRECISION NOT NULL,
            take_profit_pct  DOUBLE PRECISION NOT NULL,
            auto_trade       BOOLEAN NOT NULL DEFAULT TRUE,
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
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
    amount_usdc: float,
    stop_loss_pct: float,
    take_profit_pct: float,
) -> dict[str, Any]:
    """Spend amount_usdc buying `symbol`, recording the position and ledger entry.

    Capital is always deposited (as SOL, auto-converted) and withdrawn as
    USDC -- see bounce_ledger.py. `symbol` is the token this position
    actually swaps into, and must be a different token than USDC itself.

    Caller must have already obtained explicit human confirmation -- this
    function does not ask for it and will execute immediately.
    """
    ensure_bounce_trading_schema()
    amount_usdc = round(float(amount_usdc), 6)
    if amount_usdc < MIN_POSITION_USDC:
        return {"error": f"Position size must be at least {MIN_POSITION_USDC} USDC (fees/slippage dominate below that)."}
    if stop_loss_pct <= 0 or take_profit_pct <= 0:
        return {"error": "stop_loss_pct and take_profit_pct must both be positive percentages."}

    can_spend = check_bounce_can_spend(user_wallet, amount_usdc, BASE_TOKEN)
    if not can_spend.get("ok"):
        return can_spend

    cap = get_agent_allocation_cap(agent_id) if agent_id else None
    if cap is not None:
        already_committed = _capital_in_open_positions(agent_id)
        if already_committed + amount_usdc > cap + 1e-9:
            return {
                "error": (
                    f"This would commit {already_committed + amount_usdc:.4f} USDC to agent {agent_id}, "
                    f"over its {cap} USDC allocation cap ({already_committed:.4f} USDC already in open positions). "
                    "Close a position first, raise the cap, or use a smaller amount."
                ),
                "allocation_cap_usdc": cap,
                "already_committed_usdc": already_committed,
            }

    tok = resolve_token(symbol)
    if "error" in tok:
        return tok
    if tok["symbol"].upper() in ("USDC",):
        return {"error": "Can't open a USDC position with USDC capital -- that's a self-swap, not a trade."}

    import signal_watcher as sw

    entry_price = sw.sample_price(tok["symbol"])
    if entry_price is None:
        return {"error": f"Could not get a current price for {tok['symbol']}; aborted before spending anything."}

    swap = execute_agent_jupiter_swap(
        agent_type=AGENT_TYPE,
        input_mint=USDC_MINT,
        output_mint=tok["mint"],
        amount=amount_usdc,
        input_decimals=USDC_DECIMALS,
        user_wallet=user_wallet,
        # Buying with USDC still needs SOL headroom: a new destination ATA
        # (e.g. wrapped SOL, if buying SOL) costs real rent, paid in SOL --
        # let execute_agent_jupiter_swap apply its default reserve.
    )
    if swap.get("error") or swap.get("status") != "success":
        return {"error": swap.get("error") or "Buy swap failed.", "swap": swap}

    out_raw = int(swap.get("output_amount_raw") or 0)
    entry_token_amount = out_raw / (10 ** tok["decimals"]) if out_raw > 0 else 0.0
    if entry_token_amount <= 0:
        return {"error": "Swap reported success but no output amount was returned. Not recording a position.", "swap": swap}

    record_bounce_spend(
        user_wallet, amount_usdc,
        reference_id=swap.get("signature") or uuid.uuid4().hex,
        token=BASE_TOKEN,
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
                    entry_usdc_amount, entry_token_amount, entry_price_usd, entry_signature,
                    stop_price_usd, target_price_usd, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'open')
                RETURNING *
                """,
                (
                    position_id, user_wallet.strip(), agent_id, watch_id, tok["symbol"], tok["mint"], tok["decimals"],
                    amount_usdc, entry_token_amount, entry_price, swap.get("signature"),
                    stop_price, target_price,
                ),
            )
            row = cur.fetchone()
    return dict(row)


def close_position(position_id: str, *, reason: str) -> dict[str, Any]:
    """Sell the full position back to USDC and record the ledger credit."""
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
        output_mint=USDC_MINT,
        amount=pos["entry_token_amount"],
        input_decimals=pos["token_decimals"],
        user_wallet=pos["user_wallet"],
        # Selling back to USDC still needs SOL headroom for tx/priority fees
        # (and ATA rent if USDC isn't already held) -- use the default reserve.
    )
    if swap.get("error") or swap.get("status") != "success":
        return {"error": swap.get("error") or "Sell swap failed. Position left open.", "swap": swap}

    out_raw = int(swap.get("output_amount_raw") or 0)
    usdc_received = out_raw / (10 ** USDC_DECIMALS) if out_raw > 0 else 0.0

    record_bounce_credit(
        pos["user_wallet"], usdc_received,
        reference_id=swap.get("signature") or uuid.uuid4().hex,
        token=BASE_TOKEN,
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
                SET status = 'closed', close_reason = %s, close_usdc_amount = %s,
                    close_price_usd = %s, close_signature = %s, closed_at = NOW()
                WHERE position_id = %s
                RETURNING *
                """,
                (reason, usdc_received, close_price, swap.get("signature"), position_id),
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
                    COALESCE(SUM(entry_usdc_amount) FILTER (WHERE status = 'open'), 0) AS capital_in_open_positions,
                    COALESCE(SUM(close_usdc_amount - entry_usdc_amount) FILTER (WHERE status = 'closed'), 0) AS realized_pnl_usdc
                FROM bounce_positions
                WHERE user_wallet = %s
                GROUP BY agent_id
                ORDER BY agent_id
                """,
                (user_wallet.strip(),),
            )
            rows = cur.fetchall()
    result = [dict(r) for r in rows]
    for r in result:
        r["allocation_cap_usdc"] = get_agent_allocation_cap(r["agent_id"])
    return result


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
