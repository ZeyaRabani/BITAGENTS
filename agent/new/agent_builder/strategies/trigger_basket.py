"""trigger_basket@1 — when one stock moves, buy a basket.

"When NVIDIA goes up 2% in an hour, buy the Magnificent Seven." The move is read
from the tokenized stock's own on-chain price (Jupiter's 5 minute, 1 hour, 6 hour
and 24 hour change), which trades around the clock. When the trigger fires, each
basket stock the wallet does not already hold is bought once. No LLM decides.
"""

from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .. import market
from ..contract import Context, Decision, Order

WINDOWS = {5: "stats5m", 60: "stats1h", 360: "stats6h", 1440: "stats24h"}


def _tickers(v: list[str]) -> list[str]:
    out = [s.strip().upper() for s in v]
    if len(set(out)) != len(out):
        raise ValueError("symbols must be unique")
    return out


class Params(BaseModel):
    trigger_symbol: str = Field(min_length=1, max_length=8, description="Stock ticker whose move is watched, e.g. NVDA")
    trigger_pct: float = Field(ge=0.01, le=50, description="Percent rise over the window that fires the trigger, e.g. 2 for +2%")
    window_minutes: Literal[5, 60, 360, 1440] = Field(default=60, description="Window of the move: 5, 60, 360 or 1440 minutes")
    symbols: list[str] = Field(min_length=1, max_length=8, description="Stock tickers to buy when the trigger fires")
    per_symbol_usd: float = Field(gt=0, le=10_000, description="USD to buy of each basket stock")

    @field_validator("trigger_symbol")
    @classmethod
    def _trigger(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("symbols")
    @classmethod
    def _symbols(cls, v: list[str]) -> list[str]:
        return _tickers(v)


class TriggerBasket:
    name = "trigger_basket@1"
    title = "Price trigger basket"
    summary = (
        "Watches one stock's tokenized price. When it rises by a set percent within 5 minutes, 1 hour, 6 hours or "
        "24 hours, buys a basket of tokenized stocks (xStocks), once each. Example: NVDA up 2% in 1 hour buys the "
        "Magnificent Seven (AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA). It does not sell."
    )
    Params = Params

    def evaluate(self, ctx: Context, params: Params, limits: dict[str, Any]) -> Decision:
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        watched = market.xstock_live(params.trigger_symbol)
        if watched.get("error"):
            return Decision(orders=[], signals=[], notes=[f"{params.trigger_symbol}: {watched['error']}; nothing was evaluated"])
        change = watched["change_pct"].get(params.window_minutes)
        if change is None:
            return Decision(orders=[], signals=[], notes=[f"Jupiter has no {params.window_minutes}-minute change for {watched['symbol']}"])
        fired = change >= params.trigger_pct
        signals: list[dict[str, Any]] = [{
            "kind": "trigger", "symbol": params.trigger_symbol, "price": watched["usd_price"], "token": watched,
            "action": "buy" if fired else "hold", "change_pct": change, "threshold_pct": params.trigger_pct,
            "window_minutes": params.window_minutes, "fired": fired, "data_source": "jupiter token price", "as_of": now,
        }]
        notes = [f"{params.trigger_symbol} moved {change:+.2f}% in {params.window_minutes} min; "
                 f"the trigger is +{params.trigger_pct:g}%, so it {'fired' if fired else 'did not fire'}"]
        orders: list[Order] = []
        held = {h.mint for h in ctx.holdings if h.amount > 0}
        cash = ctx.cash_usd
        day_room = max(0.0, float(limits["max_daily_usd"]) - ctx.spent_today_usd)
        for sym in params.symbols:
            token = watched if sym == params.trigger_symbol else market.xstock_live(sym)
            row = {"kind": "basket", "symbol": sym, "price": token.get("usd_price"), "token": token, "action": "hold",
                   "change_pct": (token.get("change_pct") or {}).get(params.window_minutes),
                   "window_minutes": params.window_minutes, "data_source": "jupiter token price", "as_of": now}
            signals.append(row)
            if token.get("error"):
                notes.append(f"{sym}: {token['error']}")
            elif not fired:
                continue
            elif token["mint"] in held:
                notes.append(f"{sym}: already held, not bought again")
            else:
                usd = min(params.per_symbol_usd, float(limits["max_trade_usd"]), day_room)
                if usd < 1:
                    notes.append(f"{sym}: the daily limit is used up")
                elif cash < usd:
                    notes.append(f"{sym}: the wallet holds ${cash:.2f} of {limits['quote']} and the order needs ${usd:.2f}")
                else:
                    row["action"] = "buy"
                    orders.append(Order("buy", sym, token["symbol"], token["mint"], round(usd, 2),
                                        f"{params.trigger_symbol} {change:+.2f}% in {params.window_minutes} min ≥ +{params.trigger_pct:g}%"))
                    cash -= usd
                    day_room -= usd
        return Decision(orders=orders, signals=signals, notes=notes)
