"""Reinforcement-learning-style feedback loop for the Hedge Fund agent.

Not deep RL — a bandit-style credit-assignment layer. Past round-trips (a BUY
matched FIFO against a later SELL, across both paper and live trades) are
turned into a per-symbol reward via an exponentially-weighted moving average
of realized PnL%. That reward is a small, confidence-scaled, bounded tilt fed
into covenant_picker's ranking score — symbols that have actually made the
fund money get nudged up in future asset selection, symbols that have lost
money get nudged down. Confidence ramps in with sample count so a single
lucky/unlucky trade can't swing the picker.
"""

from __future__ import annotations

import math
import time
from collections import defaultdict, deque
from typing import Any

from db import get_conn, init_db

_CACHE_TTL_SECONDS = 900
_cache: dict[str, Any] = {"at": 0.0, "rewards": {}}

REWARD_DECAY = 0.85  # EWMA weight kept from prior round-trips; higher = longer memory
MAX_ADJUSTMENT = 0.12  # cap on how much learning can move a picker score
CONFIDENCE_SAMPLES = 5.0  # round-trips needed before a symbol's reward is fully trusted
MIN_CONFIDENCE = 0.2  # even a single sample nudges the score a little


def _fetch_fills() -> list[dict[str, Any]]:
    init_db()
    rows: list[dict[str, Any]] = []
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT symbol, side, units, price_usd, created_at
                FROM hf_paper_trades
                ORDER BY symbol, created_at ASC
                """
            )
            rows.extend({**r, "venue": "paper"} for r in cur.fetchall())
            cur.execute(
                """
                SELECT symbol, side, units, price_usd, created_at
                FROM hf_live_trades
                WHERE price_usd IS NOT NULL
                ORDER BY symbol, created_at ASC
                """
            )
            rows.extend({**r, "venue": "live"} for r in cur.fetchall())
    return rows


def _round_trip_pnl_pcts(rows: list[dict[str, Any]]) -> dict[str, list[tuple[Any, float]]]:
    """FIFO-match BUY lots against SELL fills (per symbol+venue) into closed round-trips."""
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        sym = str(r.get("symbol") or "").upper()
        if not sym:
            continue
        grouped[(sym, r.get("venue") or "paper")].append(r)

    out: dict[str, list[tuple[Any, float]]] = defaultdict(list)
    for (symbol, _venue), trades in grouped.items():
        trades.sort(key=lambda t: t["created_at"])
        lots: deque = deque()  # each item: [units_remaining, entry_price]
        for t in trades:
            side = str(t.get("side") or "").upper()
            units = float(t.get("units") or 0)
            price = float(t.get("price_usd") or 0)
            if units <= 0 or price <= 0:
                continue
            if side == "BUY":
                lots.append([units, price])
            elif side == "SELL":
                remaining = units
                while remaining > 1e-9 and lots:
                    lot_units, lot_price = lots[0]
                    matched = min(lot_units, remaining)
                    pnl_pct = ((price - lot_price) / lot_price) * 100.0
                    out[symbol].append((t["created_at"], pnl_pct))
                    lot_units -= matched
                    remaining -= matched
                    if lot_units <= 1e-9:
                        lots.popleft()
                    else:
                        lots[0][0] = lot_units
    return out


def _ewma_reward(pnl_pcts: list[tuple[Any, float]]) -> dict[str, Any]:
    ordered = [p for _, p in sorted(pnl_pcts, key=lambda x: x[0])]
    n = len(ordered)
    if n == 0:
        return {"reward": 0.0, "n": 0, "avg_pnl_pct": 0.0, "ewma_pnl_pct": 0.0, "win_rate": 0.0}
    ewma = ordered[0]
    for v in ordered[1:]:
        ewma = REWARD_DECAY * ewma + (1 - REWARD_DECAY) * v
    win_rate = sum(1 for v in ordered if v > 0) / n
    confidence = max(MIN_CONFIDENCE, min(1.0, n / CONFIDENCE_SAMPLES))
    reward = math.tanh(ewma / 20.0) * MAX_ADJUSTMENT * confidence
    return {
        "reward": round(reward, 5),
        "n": n,
        "avg_pnl_pct": round(sum(ordered) / n, 3),
        "ewma_pnl_pct": round(ewma, 3),
        "win_rate": round(win_rate, 3),
        "confidence": round(confidence, 3),
    }


def get_symbol_rewards(force_refresh: bool = False) -> dict[str, dict[str, Any]]:
    """Cached (15 min TTL) per-symbol learned reward, computed from closed round-trips."""
    now = time.time()
    if not force_refresh and _cache["rewards"] and (now - _cache["at"]) < _CACHE_TTL_SECONDS:
        return _cache["rewards"]
    try:
        rows = _fetch_fills()
        by_symbol = _round_trip_pnl_pcts(rows)
    except Exception:
        # Never let a DB hiccup break asset selection — fall back to last-known rewards.
        return _cache["rewards"] or {}
    rewards = {symbol: _ewma_reward(pnls) for symbol, pnls in by_symbol.items()}
    _cache["rewards"] = rewards
    _cache["at"] = now
    return rewards


def symbol_learned_adjustment(symbol: str) -> float:
    """Bounded score tilt (+/- MAX_ADJUSTMENT) for use in covenant_picker ranking."""
    try:
        rewards = get_symbol_rewards()
    except Exception:
        return 0.0
    row = rewards.get(str(symbol or "").upper())
    return float(row.get("reward") or 0.0) if row else 0.0


def learning_snapshot(top_n: int = 15) -> dict[str, Any]:
    """Human-readable view of what the picker has learned from past trades."""
    rewards = get_symbol_rewards(force_refresh=True)
    with_samples = {s: r for s, r in rewards.items() if r["n"] > 0}
    ranked = sorted(with_samples.items(), key=lambda kv: kv[1]["reward"], reverse=True)
    return {
        "symbols_tracked": len(with_samples),
        "top_performers": [{"symbol": s, **r} for s, r in ranked[:top_n]],
        "bottom_performers": [{"symbol": s, **r} for s, r in ranked[-top_n:]][::-1] if ranked else [],
        "method": "ewma_round_trip_pnl_bandit",
        "decay": REWARD_DECAY,
        "max_adjustment": MAX_ADJUSTMENT,
        "confidence_samples_for_full_weight": CONFIDENCE_SAMPLES,
        "note": (
            "Learned from realized round-trip PnL% on past paper + live trades "
            "(exponentially-weighted — recent trades count more). Feeds into asset "
            f"selection as a bounded, confidence-scaled tilt (+/- {MAX_ADJUSTMENT}) on the "
            "picker's composite score — it does not override the deterministic "
            "quant/value/safety analysts, only nudges ranking among candidates."
        ),
    }
