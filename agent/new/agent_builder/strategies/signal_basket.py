"""signal_basket@1 — the hedge-fund strategy, as a reusable template.

For each symbol: daily closes and headlines from Yahoo Finance, the 18 rule-based
analysts in covenant_analysts, then synthesize_signals. A buy signal buys the
tokenized stock with the quote token; a sell signal sells the whole position.
No LLM is involved in the decision.
"""

from __future__ import annotations

import threading
import time
from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel, Field, field_validator

from covenant_analysts import run_all_analysts, signals_to_dicts, synthesize_signals
from covenant_features import closes_from_prices, compute_features
from yahoo_market_data import fetch_yahoo_daily_prices, fetch_yahoo_news

from .. import market
from ..contract import Context, Decision, Order

_CACHE: dict[tuple, tuple[float, dict[str, Any]]] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL = 600  # daily bars: ten minutes is plenty


class Params(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=8, description="Stock tickers, e.g. NVDA")
    per_symbol_usd: float = Field(gt=0, le=10_000, description="USD to buy per symbol on a buy signal")
    buy_threshold: float = Field(default=0.22, ge=0.05, le=0.9)
    sell_threshold: float = Field(default=-0.22, le=-0.05, ge=-0.9)
    lookback_days: int = Field(default=365, ge=60, le=730)

    @field_validator("symbols")
    @classmethod
    def _upper(cls, v: list[str]) -> list[str]:
        out = [s.strip().upper().removesuffix("X") if s.strip().upper().endswith("X") and len(s.strip()) > 3 else s.strip().upper() for s in v]
        if len(set(out)) != len(out):
            raise ValueError("symbols must be unique")
        return out


def _closes(yahoo_symbol: str, lookback_days: int) -> list[float]:
    end = date.today()
    start = end - timedelta(days=lookback_days + 5)
    hist = fetch_yahoo_daily_prices(yahoo_symbol, start.isoformat(), end.isoformat())
    if hist.get("error"):
        raise RuntimeError(hist["error"])
    return closes_from_prices(hist["prices"])


def analyze(symbol: str, p: Params) -> dict[str, Any]:
    key = (symbol, p.lookback_days, p.buy_threshold, p.sell_threshold)
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit and time.time() - hit[0] < _CACHE_TTL:
            return hit[1]
    closes = _closes(symbol, p.lookback_days)
    spy = _closes("SPY", p.lookback_days)
    titles = [n.get("title") or "" for n in fetch_yahoo_news([symbol], limit_per_symbol=3)]
    features = compute_features(closes, spy_closes=spy, news_titles=titles)
    if features.get("error"):
        raise RuntimeError(f"{symbol}: {features['error']}")
    signals = run_all_analysts(features)
    syn = synthesize_signals(signals, buy_threshold=p.buy_threshold, sell_threshold=p.sell_threshold)
    out = {
        "symbol": symbol,
        "price": features["price"],
        "bars": features["bars"],
        "action": syn["action"],
        "composite_score": syn["composite_score"],
        "confidence": syn["confidence"],
        "signal_counts": syn["signal_counts"],
        "analysts": signals_to_dicts(signals),
        "headlines": titles,
        "data_source": "yahoo_finance",
        "as_of": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with _CACHE_LOCK:
        _CACHE[key] = (time.time(), out)
    return out


class SignalBasket:
    name = "signal_basket@1"
    title = "Analyst signal basket"
    summary = (
        "Runs 18 rule-based analysts on daily prices and headlines for a basket of stock tickers. "
        "Buys the tokenized stock (xStock) on a buy signal, sells the position on a sell signal."
    )
    Params = Params

    def evaluate(self, ctx: Context, params: Params, limits: dict[str, Any]) -> Decision:
        held = {h.mint: h for h in ctx.holdings}
        orders: list[Order] = []
        signals: list[dict[str, Any]] = []
        notes: list[str] = []
        cash = ctx.cash_usd
        day_room = max(0.0, float(limits["max_daily_usd"]) - ctx.spent_today_usd)
        for sym in params.symbols:
            row = analyze(sym, params)
            token = market.resolve_xstock(sym)
            row = {**row, "token": token}
            signals.append(row)
            if token.get("error"):
                notes.append(f"{sym}: {token['error']}")
                continue
            pos = held.get(token["mint"])
            if row["action"] == "buy":
                usd = min(params.per_symbol_usd, float(limits["max_trade_usd"]), day_room)
                if usd < 1:
                    notes.append(f"{sym}: buy signal, but the daily limit is used up")
                elif cash < usd:
                    notes.append(f"{sym}: buy signal, but the wallet holds ${cash:.2f} of {limits['quote']} and the order needs ${usd:.2f}")
                else:
                    orders.append(Order("buy", sym, token["symbol"], token["mint"], round(usd, 2),
                                        f"score {row['composite_score']:+.2f} ≥ {params.buy_threshold}"))
                    cash -= usd
                    day_room -= usd
            elif row["action"] == "sell" and pos and pos.amount > 0:
                usd = pos.value_usd or pos.amount * row["price"]
                orders.append(Order("sell", sym, token["symbol"], token["mint"], round(usd, 2),
                                    f"score {row['composite_score']:+.2f} ≤ {params.sell_threshold}"))
        return Decision(orders=orders, signals=signals, notes=notes)
