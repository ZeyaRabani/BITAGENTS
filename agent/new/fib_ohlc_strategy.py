"""Fibonacci daily OHLC paper trading + backtest.

Rules:
- Use the prior day's open/high/low/close.
- Bias: bullish candle (close >= open) → long; else short.
- Entry at the 61.8% Fibonacci retracement of that day's range.
- Stop at the day extreme (low for longs, high for shorts).
- Take profit at 3R so one win covers three equal losses (risk:reward = 1:3).
- Default asset: BTC.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Optional

from yahoo_market_data import fetch_yahoo_daily_ohlc, resolve_yahoo_asset

FIB_ENTRY = 0.618
REWARD_R = 3.0  # 1 win covers 3 losses
DEFAULT_ASSET = "BTC"
DEFAULT_LOOKBACK = 120
DEFAULT_NOTIONAL = 1000.0

_LOCK = threading.Lock()
_PAPER: dict[str, dict[str, Any]] = {}


def _resolve(asset: Optional[str]) -> dict[str, Any]:
    token = (asset or DEFAULT_ASSET).strip() or DEFAULT_ASSET
    resolved = resolve_yahoo_asset(token)
    if resolved.get("error"):
        return resolved
    return resolved


def _fib_levels(high: float, low: float) -> dict[str, float]:
    span = high - low
    return {
        "0": low,
        "0.236": low + 0.236 * span,
        "0.382": low + 0.382 * span,
        "0.5": low + 0.5 * span,
        "0.618": low + 0.618 * span,
        "0.786": low + 0.786 * span,
        "1": high,
        "range": span,
    }


def build_setup(prior: dict[str, Any]) -> dict[str, Any]:
    high = float(prior["high"])
    low = float(prior["low"])
    open_ = float(prior["open"])
    close = float(prior["close"])
    if high <= low:
        return {"error": "Prior day range is flat; no Fibonacci setup."}

    bullish = close >= open_
    side = "long" if bullish else "short"
    levels = _fib_levels(high, low)

    if side == "long":
        # Retrace from high toward low; enter at 61.8% pullback.
        entry = high - FIB_ENTRY * (high - low)
        stop = low
        risk = entry - stop
        if risk <= 0:
            return {"error": "Invalid long risk distance."}
        take_profit = entry + REWARD_R * risk
    else:
        entry = low + FIB_ENTRY * (high - low)
        stop = high
        risk = stop - entry
        if risk <= 0:
            return {"error": "Invalid short risk distance."}
        take_profit = entry - REWARD_R * risk

    return {
        "side": side,
        "bias": "bullish" if bullish else "bearish",
        "prior": prior,
        "levels": {k: round(v, 8) for k, v in levels.items()},
        "entry": round(entry, 8),
        "stop": round(stop, 8),
        "take_profit": round(take_profit, 8),
        "risk": round(risk, 8),
        "reward": round(abs(take_profit - entry), 8),
        "risk_reward": f"1:{int(REWARD_R)}",
        "fib_entry": FIB_ENTRY,
        "reason": (
            f"Prior day {prior['date']} was {('bullish' if bullish else 'bearish')} "
            f"(O={open_:.4f} H={high:.4f} L={low:.4f} C={close:.4f}). "
            f"{side.upper()} at Fib {FIB_ENTRY:.3f}, stop at day extreme, TP at {int(REWARD_R)}R."
        ),
    }


def _simulate_day(setup: dict[str, Any], day: dict[str, Any]) -> dict[str, Any]:
    """Fill using the session bar. If stop and TP are both possible, stop wins (conservative)."""
    side = setup["side"]
    entry = float(setup["entry"])
    stop = float(setup["stop"])
    tp = float(setup["take_profit"])
    risk = float(setup["risk"])
    o, h, l, c = float(day["open"]), float(day["high"]), float(day["low"]), float(day["close"])

    touched = (l <= entry <= h)
    if not touched:
        return {
            "status": "no_fill",
            "date": day["date"],
            "side": side,
            "entry": entry,
            "pnl_r": 0.0,
            "pnl_usd": 0.0,
            "exit": None,
            "exit_reason": None,
            "bar": day,
        }

    if side == "long":
        stop_hit = l <= stop
        tp_hit = h >= tp
        # Gap through stop
        if o <= stop:
            exit_px, reason = stop, "gap_stop"
        elif stop_hit and tp_hit:
            exit_px, reason = stop, "stop_before_tp"
        elif stop_hit:
            exit_px, reason = stop, "stop"
        elif tp_hit:
            exit_px, reason = tp, "take_profit"
        else:
            exit_px, reason = c, "eod"
        pnl_r = (exit_px - entry) / risk
    else:
        stop_hit = h >= stop
        tp_hit = l <= tp
        if o >= stop:
            exit_px, reason = stop, "gap_stop"
        elif stop_hit and tp_hit:
            exit_px, reason = stop, "stop_before_tp"
        elif stop_hit:
            exit_px, reason = stop, "stop"
        elif tp_hit:
            exit_px, reason = tp, "take_profit"
        else:
            exit_px, reason = c, "eod"
        pnl_r = (entry - exit_px) / risk

    return {
        "status": "filled",
        "date": day["date"],
        "side": side,
        "entry": entry,
        "stop": stop,
        "take_profit": tp,
        "exit": round(exit_px, 8),
        "exit_reason": reason,
        "pnl_r": round(pnl_r, 4),
        "bar": day,
    }


def _load_bars(asset: Optional[str], lookback_days: int) -> dict[str, Any]:
    resolved = _resolve(asset)
    if resolved.get("error"):
        return resolved
    raw = fetch_yahoo_daily_ohlc(resolved["yahoo_symbol"], lookback_days=lookback_days)
    if raw.get("error"):
        return raw
    return {
        "symbol": resolved["symbol"],
        "yahoo_symbol": resolved["yahoo_symbol"],
        "asset_class": resolved.get("asset_class"),
        "bars": raw["bars"],
        "source": raw.get("source"),
    }


def inspect_asset(asset: Optional[str] = None, lookback_days: int = DEFAULT_LOOKBACK) -> dict[str, Any]:
    data = _load_bars(asset, lookback_days)
    if data.get("error"):
        return data
    bars = data["bars"]
    prior = bars[-2]
    latest = bars[-1]
    setup = build_setup(prior)
    if setup.get("error"):
        return setup
    return {
        "symbol": data["symbol"],
        "yahoo_symbol": data["yahoo_symbol"],
        "asset_class": data.get("asset_class"),
        "source": data.get("source"),
        "prior_day": prior,
        "latest_day": latest,
        "setup": setup,
        "note": "Paper/backtest only. Not financial advice.",
    }


def run_paper(
    *,
    wallet: str,
    asset: Optional[str] = None,
    notional_usd: float = DEFAULT_NOTIONAL,
    lookback_days: int = DEFAULT_LOOKBACK,
) -> dict[str, Any]:
    """Open/resolve one paper trade for the latest completed setup against the latest bar."""
    data = _load_bars(asset, lookback_days)
    if data.get("error"):
        return data
    bars = data["bars"]
    prior, latest = bars[-2], bars[-1]
    setup = build_setup(prior)
    if setup.get("error"):
        return setup

    fill = _simulate_day(setup, latest)
    risk = float(setup["risk"])
    entry = float(setup["entry"])
    units = (float(notional_usd) / entry) if entry else 0.0
    pnl_usd = round(float(fill["pnl_r"]) * risk * units, 4) if fill["status"] == "filled" else 0.0
    fill["pnl_usd"] = pnl_usd
    fill["notional_usd"] = float(notional_usd)
    fill["units"] = round(units, 8)

    trade = {
        "id": f"{data['symbol']}-{latest['date']}-{setup['side']}",
        "symbol": data["symbol"],
        "yahoo_symbol": data["yahoo_symbol"],
        "setup": setup,
        "fill": fill,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    with _LOCK:
        book = _PAPER.setdefault(
            wallet,
            {"cash_usd": 10_000.0, "realized_pnl_usd": 0.0, "trades": [], "open": None},
        )
        if fill["status"] == "filled" and fill.get("exit_reason") in {"stop", "take_profit", "gap_stop", "stop_before_tp", "eod"}:
            book["realized_pnl_usd"] = round(float(book["realized_pnl_usd"]) + pnl_usd, 4)
            book["cash_usd"] = round(float(book["cash_usd"]) + pnl_usd, 4)
            book["open"] = None
            book["trades"] = ([trade] + list(book["trades"]))[:50]
        elif fill["status"] == "no_fill":
            book["open"] = {
                "symbol": data["symbol"],
                "setup": setup,
                "waiting_on": latest["date"],
                "note": "Entry level not touched on the latest bar.",
            }
            book["trades"] = ([trade] + list(book["trades"]))[:50]
        else:
            book["trades"] = ([trade] + list(book["trades"]))[:50]

        snapshot = {
            "cash_usd": book["cash_usd"],
            "realized_pnl_usd": book["realized_pnl_usd"],
            "open": book["open"],
            "trades": book["trades"][:10],
        }

    return {
        "mode": "paper",
        "symbol": data["symbol"],
        "yahoo_symbol": data["yahoo_symbol"],
        "prior_day": prior,
        "latest_day": latest,
        "setup": setup,
        "fill": fill,
        "book": snapshot,
        "note": "Paper only. Not financial advice.",
    }


def backtest(
    *,
    asset: Optional[str] = None,
    lookback_days: int = DEFAULT_LOOKBACK,
    notional_usd: float = DEFAULT_NOTIONAL,
) -> dict[str, Any]:
    data = _load_bars(asset, lookback_days)
    if data.get("error"):
        return data
    bars = data["bars"]
    if len(bars) < 3:
        return {"error": "Need at least 3 daily bars to backtest."}

    trades: list[dict[str, Any]] = []
    equity = 0.0
    wins = losses = flats = skips = 0
    for i in range(1, len(bars)):
        setup = build_setup(bars[i - 1])
        if setup.get("error"):
            skips += 1
            continue
        fill = _simulate_day(setup, bars[i])
        if fill["status"] != "filled":
            skips += 1
            continue
        entry = float(setup["entry"])
        risk = float(setup["risk"])
        units = (float(notional_usd) / entry) if entry else 0.0
        pnl_usd = round(float(fill["pnl_r"]) * risk * units, 4)
        fill["pnl_usd"] = pnl_usd
        fill["notional_usd"] = float(notional_usd)
        equity = round(equity + pnl_usd, 4)
        if pnl_usd > 0:
            wins += 1
        elif pnl_usd < 0:
            losses += 1
        else:
            flats += 1
        trades.append({
            "setup_date": bars[i - 1]["date"],
            "trade_date": bars[i]["date"],
            "side": setup["side"],
            "entry": setup["entry"],
            "stop": setup["stop"],
            "take_profit": setup["take_profit"],
            "exit": fill["exit"],
            "exit_reason": fill["exit_reason"],
            "pnl_r": fill["pnl_r"],
            "pnl_usd": pnl_usd,
        })

    filled = wins + losses + flats
    win_rate = (wins / filled * 100.0) if filled else 0.0
    avg_r = (sum(t["pnl_r"] for t in trades) / filled) if filled else 0.0
    return {
        "mode": "backtest",
        "symbol": data["symbol"],
        "yahoo_symbol": data["yahoo_symbol"],
        "asset_class": data.get("asset_class"),
        "source": data.get("source"),
        "params": {
            "fib_entry": FIB_ENTRY,
            "risk_reward": f"1:{int(REWARD_R)}",
            "lookback_days": lookback_days,
            "notional_usd": notional_usd,
            "bars": len(bars),
        },
        "summary": {
            "trades": filled,
            "skips": skips,
            "wins": wins,
            "losses": losses,
            "flats": flats,
            "win_rate_pct": round(win_rate, 2),
            "avg_r": round(avg_r, 4),
            "total_pnl_usd": equity,
            "expectancy_r": round(avg_r, 4),
        },
        "trades": trades[-60:],
        "note": "Historical simulation on Yahoo daily bars. Conservative stop-first if both sides hit. Not financial advice.",
    }


def paper_book(wallet: str) -> dict[str, Any]:
    with _LOCK:
        book = _PAPER.get(wallet)
        if not book:
            return {"cash_usd": 10_000.0, "realized_pnl_usd": 0.0, "open": None, "trades": []}
        return {
            "cash_usd": book["cash_usd"],
            "realized_pnl_usd": book["realized_pnl_usd"],
            "open": book["open"],
            "trades": list(book["trades"][:20]),
        }


_SESSION: dict[str, dict[str, Any]] = {}


def _session(wallet: str) -> dict[str, Any]:
    with _LOCK:
        cur = _SESSION.get(wallet)
        if cur is None:
            cur = {"asset": DEFAULT_ASSET, "lookback_days": DEFAULT_LOOKBACK, "notional_usd": DEFAULT_NOTIONAL}
            _SESSION[wallet] = cur
        return cur


def _parse_asset(text: str) -> Optional[str]:
    import re

    m = re.search(
        r"\b(?:for|on|asset|ticker|symbol)\s+([A-Za-z][A-Za-z0-9.^-]{0,15})\b",
        text,
        re.I,
    )
    if m:
        return m.group(1).upper()
    m = re.search(
        r"\b(BTC|ETH|SOL|XRP|AAPL|MSFT|NVDA|TSLA|SPY|QQQ|[A-Z]{2,6}(?:-USD)?)\b",
        text,
        re.I,
    )
    return m.group(1).upper() if m else None


def _parse_number(text: str, *patterns: str) -> Optional[float]:
    import re

    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                return None
    return None


def _fmt_setup(setup: dict[str, Any], symbol: str) -> str:
    return (
        f"**{symbol}** {setup['side'].upper()} setup ({setup['bias']})\n"
        f"• Entry: `{setup['entry']}`\n"
        f"• Stop: `{setup['stop']}`\n"
        f"• Take profit: `{setup['take_profit']}` ({setup['risk_reward']})\n"
        f"• Risk: `{setup['risk']}`\n\n"
        f"{setup['reason']}\n\n"
        "Paper mode only. Not financial advice."
    )


def _fmt_ohlc(day: dict[str, Any], label: str) -> str:
    return (
        f"{label} `{day['date']}`: "
        f"O={day['open']} H={day['high']} L={day['low']} C={day['close']}"
    )


def run_chat(wallet: str, message: str) -> tuple[str, list[dict[str, Any]]]:
    """Deterministic paper chat for Fib OHLC. No live trading."""
    import re

    text = (message or "").strip()
    actions: list[dict[str, Any]] = []
    if not text:
        return "Say an asset (default BTC), then ask to show the Fib setup, run a paper trade, or backtest.", actions

    sess = _session(wallet)
    asset = _parse_asset(text) or str(sess["asset"])
    lookback = int(_parse_number(text, r"\b(\d+)\s*days?\b", r"\blookback(?:\s*[:=])?\s*(\d+)\b") or sess["lookback_days"])
    notional = float(
        _parse_number(text, r"\$?\s*([0-9]*\.?[0-9]+)\s*(?:usd|notional|size)\b", r"\bnotional(?:\s*[:=])?\s*([0-9]*\.?[0-9]+)\b")
        or sess["notional_usd"]
    )
    lookback = max(20, min(lookback, 500))
    notional = max(1.0, min(notional, 1_000_000.0))
    with _LOCK:
        sess["asset"] = asset
        sess["lookback_days"] = lookback
        sess["notional_usd"] = notional

    low = text.lower()
    if re.search(r"\b(help|what can you|commands)\b", low):
        reply = (
            "I run a **paper** Fibonacci daily OHLC strategy.\n\n"
            "Try:\n"
            "• `Show Fib setup for BTC`\n"
            "• `Run paper trade on ETH`\n"
            "• `Backtest SOL 90 days`\n"
            "• `Show my paper book`\n\n"
            "Default asset is BTC. Risk:reward is 1:3. No live trades."
        )
        return reply, actions

    if re.search(r"\b(book|balance|pnl|positions?)\b", low) and not re.search(r"\b(paper trade|run paper|backtest)\b", low):
        book = paper_book(wallet)
        actions.append({"tool": "paper_book", "args": {}, "result": str(book)})
        open_note = "No open wait." if not book.get("open") else f"Open wait: {book['open']}"
        reply = (
            f"**Paper book**\n"
            f"• Cash: `${book['cash_usd']}`\n"
            f"• Realized PnL: `${book['realized_pnl_usd']}`\n"
            f"• {open_note}\n"
            f"• Trades logged: {len(book.get('trades') or [])}\n\n"
            "Paper mode only. Not financial advice."
        )
        return reply, actions

    if re.search(r"\bbacktest\b", low):
        result = backtest(asset=asset, lookback_days=lookback, notional_usd=notional)
        actions.append({"tool": "backtest", "args": {"asset": asset, "lookback_days": lookback, "notional_usd": notional}, "result": str(result.get("summary") or result)})
        if result.get("error"):
            return f"{result['error']}\n\nPaper mode only. Not financial advice.", actions
        s = result["summary"]
        reply = (
            f"**Backtest {result['symbol']}** ({lookback}d, ${notional:g} notional)\n"
            f"• Trades: {s['trades']} · skips: {s['skips']}\n"
            f"• Wins/losses: {s['wins']}/{s['losses']}\n"
            f"• Win rate: {s['win_rate_pct']}%\n"
            f"• Avg R: {s['avg_r']}\n"
            f"• Total PnL: `${s['total_pnl_usd']}`\n\n"
            "Historical paper simulation. Not financial advice."
        )
        return reply, actions

    wants_paper = bool(
        re.search(r"\b(run paper|paper trade|paper run|execute paper|simulate trade)\b", low)
        or (
            re.search(r"\b(paper|trade|run|execute)\b", low)
            and not re.search(r"\b(setup|inspect|ohlc|levels?|fib|show|backtest)\b", low)
        )
    )
    if wants_paper:
        result = run_paper(wallet=wallet, asset=asset, notional_usd=notional, lookback_days=lookback)
        actions.append({"tool": "paper", "args": {"asset": asset, "notional_usd": notional}, "result": str(result.get("fill") or result)})
        if result.get("error"):
            return f"{result['error']}\n\nPaper mode only. Not financial advice.", actions
        fill = result["fill"]
        book = result["book"]
        reply = (
            f"{_fmt_setup(result['setup'], result['symbol'])}\n\n"
            f"{_fmt_ohlc(result['prior_day'], 'Prior')}\n"
            f"{_fmt_ohlc(result['latest_day'], 'Latest')}\n\n"
            f"**Paper fill:** {fill['status']}"
            + (f" · exit `{fill.get('exit')}` ({fill.get('exit_reason')})" if fill.get("exit") is not None else "")
            + f" · PnL R `{fill.get('pnl_r', 0)}` · USD `${fill.get('pnl_usd', 0)}`\n"
            f"**Book:** cash `${book['cash_usd']}` · realized `${book['realized_pnl_usd']}`\n\n"
            "Paper mode only. Not financial advice."
        )
        return reply, actions

    # Default: inspect / show setup
    result = inspect_asset(asset, lookback_days=lookback)
    actions.append({"tool": "inspect", "args": {"asset": asset, "lookback_days": lookback}, "result": str(result.get("setup") or result)})
    if result.get("error"):
        return f"{result['error']}\n\nPaper mode only. Not financial advice.", actions
    reply = (
        f"{_fmt_setup(result['setup'], result['symbol'])}\n\n"
        f"{_fmt_ohlc(result['prior_day'], 'Prior')}\n"
        f"{_fmt_ohlc(result['latest_day'], 'Latest')}\n\n"
        "Say `run paper trade` to simulate the fill, or `backtest` for history."
    )
    return reply, actions

