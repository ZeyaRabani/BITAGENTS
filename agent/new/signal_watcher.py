"""
Generic price-pattern signal engine for strategy agents (e.g. the Bounce Agent:
"drop X% from recent high, then bounce Y% off the low").

This is intentionally generic, not hardcoded to SOL/dip-bounce: any future
price-pattern agent (breakout, mean-reversion, etc.) reuses the same sampling
table and state machine by registering a different rule. The dip-then-bounce
rule is the first concrete implementation.

Price source: Binance spot ticker (keyless public REST), sampled every 1s by
default. Yahoo daily bars (yahoo_market_data.py) remain the right tool for
the backtest gate, which needs a year of history, not real-time resolution.

State machine per watched (symbol, rule) pair:

    NEUTRAL
      -> price falls `drop_pct` from the rolling high (over `lookback_minutes`)
    ARMED (tracks the lowest price seen since arming)
      -> price rises `bounce_pct` off that tracked low
    FIRE (caller executes the trade, then calls reset_signal())
      -> reset to NEUTRAL (with a cooldown so it doesn't re-fire on noise)
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import requests

from db import get_conn, init_db
from dca_agent import TOKEN_MINTS

# ─── Threshold profiles ────────────────────────────────────────────────────
# "real" is the actual strategy as described in the Oct 16 handoff meeting.
# "test" is a deliberately tight/fast profile so the whole pipeline (signal
# -> arm -> fire -> execute -> close) can be proven end-to-end within an
# hour instead of waiting days for a genuine 10% move. Never used for an
# agent a real user is relying on -- only for our own pipeline testing.
# All profiles poll Binance every 1 second so bounce detection stays tight.
SIGNAL_PROFILES: dict[str, dict[str, float]] = {
    "real": {"drop_pct": 10.0, "bounce_pct": 5.0, "lookback_minutes": 60, "cooldown_minutes": 60, "sample_interval_seconds": 1},
    "test": {"drop_pct": 0.3, "bounce_pct": 0.2, "lookback_minutes": 15, "cooldown_minutes": 5, "sample_interval_seconds": 1},
    # "fast_test": for proving the full in-and-out pipeline in a couple of
    # minutes. Thresholds are set at roughly SOL's normal noise level over a
    # 2-minute window -- this is NOT a trading edge, it's a pipeline test.
    # Never offer this profile to a real launched agent a user depends on.
    "fast_test": {"drop_pct": 0.05, "bounce_pct": 0.03, "lookback_minutes": 2, "cooldown_minutes": 1, "sample_interval_seconds": 1},
}

DEFAULT_SAMPLE_INTERVAL_SECONDS = int(os.environ.get("SIGNAL_SAMPLE_INTERVAL_SECONDS", "1") or "1")
BINANCE_TICKER_URL = os.environ.get(
    "BINANCE_TICKER_URL",
    "https://api.binance.com/api/v3/ticker/price",
).strip() or "https://api.binance.com/api/v3/ticker/price"

# Map our Solana trade symbols to Binance USDT spot pairs.
BINANCE_SYMBOL_MAP: dict[str, str] = {
    "SOL": "SOLUSDT",
    "WSOL": "SOLUSDT",
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "JUP": "JUPUSDT",
    "BONK": "BONKUSDT",
    "WIF": "WIFUSDT",
    "RAY": "RAYUSDT",
    "ORCA": "ORCAUSDT",
    "PYTH": "PYTHUSDT",
    "JTO": "JTOUSDT",
    "RENDER": "RENDERUSDT",
}

_scheduler_stop = None  # set lazily to a threading.Event in start_sampler()
_scheduler_thread = None


def ensure_signal_schema() -> None:
    init_db()
    statements = [
        """
        CREATE TABLE IF NOT EXISTS price_samples (
            id          BIGSERIAL PRIMARY KEY,
            symbol      VARCHAR(16) NOT NULL,
            price_usd   DOUBLE PRECISION NOT NULL,
            source      VARCHAR(16) NOT NULL DEFAULT 'binance',
            sampled_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_price_samples_symbol_time ON price_samples (symbol, sampled_at DESC)",
        """
        CREATE TABLE IF NOT EXISTS signal_watches (
            watch_id            VARCHAR(40) PRIMARY KEY,
            agent_id            VARCHAR(32),
            symbol              VARCHAR(16) NOT NULL,
            profile              VARCHAR(16) NOT NULL DEFAULT 'real',
            drop_pct            DOUBLE PRECISION NOT NULL,
            bounce_pct          DOUBLE PRECISION NOT NULL,
            lookback_minutes    INTEGER NOT NULL,
            cooldown_minutes    INTEGER NOT NULL,
            sample_interval_seconds INTEGER NOT NULL DEFAULT 1,
            state               VARCHAR(16) NOT NULL DEFAULT 'neutral',
            armed_high_usd      DOUBLE PRECISION,
            armed_low_usd       DOUBLE PRECISION,
            armed_at            TIMESTAMPTZ,
            last_fired_at       TIMESTAMPTZ,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_signal_watches_agent ON signal_watches (agent_id)",
        "ALTER TABLE signal_watches ADD COLUMN IF NOT EXISTS sample_interval_seconds INTEGER NOT NULL DEFAULT 1",
    ]
    with get_conn() as conn:
        with conn.cursor() as cur:
            for stmt in statements:
                cur.execute(stmt)


# ─── Price sampling ─────────────────────────────────────────────────────────

def _binance_pair_for(symbol: str) -> Optional[str]:
    sym = (symbol or "").strip().upper()
    if not sym:
        return None
    if sym in BINANCE_SYMBOL_MAP:
        return BINANCE_SYMBOL_MAP[sym]
    # Allow callers to pass a raw Binance pair (e.g. SOLUSDT).
    if sym.endswith("USDT") and len(sym) > 4:
        return sym
    # Unknown Solana-only tokens (e.g. BITAGENTS) have no Binance spot pair.
    if sym in TOKEN_MINTS:
        return None
    return f"{sym}USDT"


def sample_price(symbol: str) -> Optional[float]:
    """Fetch one spot price from Binance and store it. Returns the price or None."""
    pair = _binance_pair_for(symbol)
    if not pair:
        return None
    try:
        resp = requests.get(BINANCE_TICKER_URL, params={"symbol": pair}, timeout=5)
        if resp.status_code != 200:
            return None
        body = resp.json()
        price = body.get("price") if isinstance(body, dict) else None
        if price is None:
            return None
        price = float(price)
    except Exception:
        return None

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO price_samples (symbol, price_usd, source) VALUES (%s, %s, 'binance')",
                (symbol.upper(), price),
            )
    return price


def rolling_high_low(symbol: str, lookback_minutes: int) -> Optional[dict[str, float]]:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT MAX(price_usd) AS hi, MIN(price_usd) AS lo, COUNT(*) AS n "
                "FROM price_samples WHERE symbol = %s AND sampled_at >= %s",
                (symbol.upper(), cutoff),
            )
            row = cur.fetchone()
    if not row or not row["n"]:
        return None
    return {"high": float(row["hi"]), "low": float(row["lo"]), "samples": int(row["n"])}


# ─── Watch lifecycle ─────────────────────────────────────────────────────────

def create_watch(agent_id: Optional[str], symbol: str, profile: str = "real") -> dict[str, Any]:
    if profile not in SIGNAL_PROFILES:
        return {"error": f"Unknown profile '{profile}'. Use one of {list(SIGNAL_PROFILES)}."}
    ensure_signal_schema()
    cfg = SIGNAL_PROFILES[profile]
    symbol = symbol.upper()

    # Idempotent: reuse an existing non-fired watch for the same (agent,
    # symbol, profile) instead of spawning a duplicate. Found necessary by
    # testing live -- the chat model was asked to check an existing watch and
    # instead kept creating new ones, which is confusing and wastes sampling.
    if agent_id:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM signal_watches
                    WHERE agent_id = %s AND symbol = %s AND profile = %s AND state != 'fired'
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (agent_id, symbol, profile),
                )
                existing = cur.fetchone()
        if existing:
            # Keep sample interval in sync with current profile defaults (1s Binance poll).
            desired_interval = int(cfg.get("sample_interval_seconds", DEFAULT_SAMPLE_INTERVAL_SECONDS))
            if int(existing.get("sample_interval_seconds") or 0) != desired_interval:
                with get_conn() as conn2:
                    with conn2.cursor() as cur2:
                        cur2.execute(
                            """
                            UPDATE signal_watches
                            SET sample_interval_seconds = %s, updated_at = NOW()
                            WHERE watch_id = %s
                            RETURNING *
                            """,
                            (desired_interval, existing["watch_id"]),
                        )
                        updated = cur2.fetchone()
                return dict(updated) if updated else dict(existing)
            return dict(existing)

    watch_id = f"sw_{uuid_hex()}"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO signal_watches
                    (watch_id, agent_id, symbol, profile, drop_pct, bounce_pct, lookback_minutes, cooldown_minutes, sample_interval_seconds)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    watch_id, agent_id, symbol.upper(), profile,
                    cfg["drop_pct"], cfg["bounce_pct"], int(cfg["lookback_minutes"]), int(cfg["cooldown_minutes"]),
                    int(cfg.get("sample_interval_seconds", DEFAULT_SAMPLE_INTERVAL_SECONDS)),
                ),
            )
            row = cur.fetchone()
    return dict(row)


def get_watch(watch_id: str) -> Optional[dict[str, Any]]:
    """Read-only lookup, no sampling -- for a frontend poller or a chat tool
    that just wants the current status without forcing a fresh price pull."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            row = _get_watch(cur, watch_id)
    return row


def list_watches_for_agent(agent_id: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM signal_watches WHERE agent_id = %s ORDER BY created_at DESC",
                (agent_id,),
            )
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def uuid_hex() -> str:
    import uuid as _uuid
    return _uuid.uuid4().hex[:12]


def _get_watch(cur, watch_id: str) -> Optional[dict[str, Any]]:
    cur.execute("SELECT * FROM signal_watches WHERE watch_id = %s", (watch_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def evaluate_watch(watch_id: str) -> dict[str, Any]:
    """
    Pull the latest price, advance the watch's state machine, and return the
    current status. Call this on every sampler tick for every active watch.
    On fired=True, also auto-stages an open_bounce_position proposal if the
    watch's agent has a default strategy configured with auto_trade on (see
    _maybe_auto_stage_trade) -- this still only PROPOSES, same confirmation
    gate as everything else; it just means the user doesn't have to be the
    one to ask for it in chat.
    """
    result = _evaluate_watch_inner(watch_id)
    if result.get("fired"):
        _maybe_auto_stage_trade(watch_id, result)
    return result


def _evaluate_watch_inner(watch_id: str) -> dict[str, Any]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            watch = _get_watch(cur, watch_id)
            if not watch:
                return {"error": "watch not found"}

            now = datetime.now(timezone.utc)
            if watch["state"] == "cooldown" and watch["last_fired_at"]:
                last = watch["last_fired_at"]
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                if (now - last).total_seconds() < watch["cooldown_minutes"] * 60:
                    return {"watch_id": watch_id, "state": "cooldown", "fired": False}
                watch["state"] = "neutral"

            price = sample_price(watch["symbol"])
            if price is None:
                return {"watch_id": watch_id, "state": watch["state"], "fired": False, "error": "price unavailable"}

            hl = rolling_high_low(watch["symbol"], watch["lookback_minutes"])
            if not hl:
                return {"watch_id": watch_id, "state": watch["state"], "fired": False, "error": "no samples yet"}

            fired = False

            if watch["state"] == "neutral":
                drop_from_high = (hl["high"] - price) / hl["high"] * 100 if hl["high"] else 0.0
                if drop_from_high >= watch["drop_pct"]:
                    cur.execute(
                        """
                        UPDATE signal_watches
                        SET state = 'armed', armed_high_usd = %s, armed_low_usd = %s, armed_at = NOW(), updated_at = NOW()
                        WHERE watch_id = %s
                        """,
                        (hl["high"], price, watch_id),
                    )
                    watch["state"] = "armed"
                    watch["armed_low_usd"] = price

            elif watch["state"] == "armed":
                armed_low = min(watch["armed_low_usd"] or price, price)
                bounce_from_low = (price - armed_low) / armed_low * 100 if armed_low else 0.0
                if bounce_from_low >= watch["bounce_pct"]:
                    cur.execute(
                        """
                        UPDATE signal_watches
                        SET state = 'fired', last_fired_at = NOW(), updated_at = NOW()
                        WHERE watch_id = %s
                        """,
                        (watch_id,),
                    )
                    watch["state"] = "fired"
                    fired = True
                elif armed_low != watch["armed_low_usd"]:
                    cur.execute(
                        "UPDATE signal_watches SET armed_low_usd = %s, updated_at = NOW() WHERE watch_id = %s",
                        (armed_low, watch_id),
                    )
                    watch["armed_low_usd"] = armed_low

            return {
                "watch_id": watch_id,
                "symbol": watch["symbol"],
                "state": watch["state"],
                "price_usd": price,
                "rolling_high": hl["high"],
                "rolling_low": hl["low"],
                "armed_low_usd": watch.get("armed_low_usd"),
                "fired": fired,
            }


def _volatility_adjusted_sl_tp(strategy: dict[str, Any], fired_result: dict[str, Any]) -> tuple[float, float]:
    """Size the stop/target off the volatility actually observed in this
    watch's lookback window, instead of applying the configured % blindly --
    a fixed 5% stop is too tight in a genuinely choppy window (stops out on
    noise that isn't a real reversal) and needlessly wide in a calm one.
    Uses the watch's own rolling high/low range (already sampled for the
    signal itself, no extra data needed) as the basis, scaled to preserve
    the stop:target ratio the strategy was configured with, and bounded to
    0.5x-3x the configured stop so a dead-flat or freak-spike window can't
    produce a degenerate size in either direction."""
    base_stop = float(strategy.get("stop_loss_pct") or 0) or 1.0
    base_target = float(strategy.get("take_profit_pct") or 0) or (base_stop * 3)
    reward_ratio = base_target / base_stop if base_stop else 3.0

    price = fired_result.get("price_usd")
    high = fired_result.get("rolling_high")
    low = fired_result.get("rolling_low")
    if not price or not high or not low or high <= low:
        return round(base_stop, 4), round(base_target, 4)

    range_pct = (high - low) / price * 100
    stop_pct = max(base_stop * 0.5, min(range_pct, base_stop * 3.0))
    return round(stop_pct, 4), round(stop_pct * reward_ratio, 4)


def _maybe_auto_stage_trade(watch_id: str, fired_result: dict[str, Any]) -> None:
    """On a watch firing, propose -- or for the `fast_test` diagnostic
    profile, directly execute -- opening a position using the agent's
    preset strategy and its current withdrawable USDC (capped by its
    allocation cap, if any).

    fast_test is documented above (see SIGNAL_PROFILES) as pipeline-test
    only, never offered to a real launched agent a user depends on -- that's
    what makes it safe to skip the human approval step specifically for it:
    it's the one profile where "the agent trades on its own" can't put
    meaningful capital at risk. The `test` and `real` profiles still stage a
    confirmation card for the user to approve or reject, same as before.

    Never raises; a failure here just means no trade happens, the user can
    still ask in chat."""
    try:
        watch = get_watch(watch_id)
        if not watch or not watch.get("agent_id"):
            return
        agent_id = watch["agent_id"]

        import bounce_trading as bt

        strategy = bt.get_agent_strategy(agent_id)
        if not strategy or not strategy.get("auto_trade"):
            return
        if strategy["symbol"] != watch["symbol"] or strategy["profile"] != watch["profile"]:
            return  # this watch doesn't match the agent's configured strategy

        from db import get_launched_agent
        import bounce_ledger as bl

        agent = get_launched_agent(agent_id)
        if not agent:
            return
        user_wallet = agent["user_wallet"]

        balances = bl.get_bounce_user_balances(user_wallet)
        usdc_available = next(
            (b["withdrawable"] for b in balances.get("balances") or [] if b["token"] == "USDC"), 0.0
        )
        cap = bt.get_agent_allocation_cap(agent_id)
        already_committed = bt._capital_in_open_positions(agent_id)
        headroom = (cap - already_committed) if cap is not None else usdc_available
        amount_usdc = round(min(usdc_available, max(0.0, headroom)), 6)
        if amount_usdc < bt.MIN_POSITION_USDC:
            return  # not enough funded (or already at its cap) to propose anything

        stop_loss_pct, take_profit_pct = _volatility_adjusted_sl_tp(strategy, fired_result)
        args = {
            "symbol": strategy["symbol"],
            "amount_usdc": amount_usdc,
            "stop_loss_pct": stop_loss_pct,
            "take_profit_pct": take_profit_pct,
            "watch_id": watch_id,
        }

        import launch_agent as la

        if watch["profile"] == "fast_test":
            bt.start_position_monitor()
            result = bt.open_position(user_wallet=user_wallet, agent_id=agent_id, **args)
            reset_watch(watch_id)
            la._record_bounce_auto_trade(user_wallet, agent_id, args=args, result=result)
            return

        la._stage_bounce_confirmation(user_wallet, agent_id, "open_bounce_position", args)
    except Exception as exc:
        print(f"  warning: auto-stage-on-fire failed for watch {watch_id}: {exc}")


def reset_watch(watch_id: str) -> None:
    """Call this after the caller has executed (or declined) a fired signal."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE signal_watches SET state = 'cooldown', armed_high_usd = NULL, armed_low_usd = NULL, "
                "armed_at = NULL, updated_at = NOW() WHERE watch_id = %s",
                (watch_id,),
            )


# ─── Background sampler (same in-process scheduler-thread pattern already
# proven by DCA/Volume/Hedge Fund/Yield/platform-payments) ──────────────────

_LOOP_TICK_SECONDS = 1  # wake every second so 1s sample intervals can fire on time


def _sampler_loop(stop_event) -> None:
    last_run_at: dict[str, float] = {}
    while not stop_event.is_set():
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT watch_id, sample_interval_seconds FROM signal_watches WHERE state != 'fired'"
                    )
                    due = cur.fetchall()
            now = time.time()
            for row in due:
                wid = row["watch_id"]
                interval = row["sample_interval_seconds"] or DEFAULT_SAMPLE_INTERVAL_SECONDS
                if now - last_run_at.get(wid, 0) >= interval:
                    evaluate_watch(wid)
                    last_run_at[wid] = now
        except Exception as exc:
            print(f"  ⚠️  signal sampler tick failed: {exc}")
        stop_event.wait(_LOOP_TICK_SECONDS)


def start_sampler() -> bool:
    import threading
    global _scheduler_stop, _scheduler_thread
    if _scheduler_thread is not None and _scheduler_thread.is_alive():
        return False
    ensure_signal_schema()
    _scheduler_stop = threading.Event()
    _scheduler_thread = threading.Thread(target=_sampler_loop, args=(_scheduler_stop,), daemon=True)
    _scheduler_thread.start()
    return True


def stop_sampler() -> None:
    if _scheduler_stop is not None:
        _scheduler_stop.set()
