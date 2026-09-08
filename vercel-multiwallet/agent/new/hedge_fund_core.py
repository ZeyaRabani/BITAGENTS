"""Covenant-inspired hedge fund core — Solana token portfolio analysis + fee model.

Adapted from https://github.com/asalsali/covenant-hedge-fund (MIT).
Deterministic quant/risk layers + optional LLM macro synthesis in hedge_fund_agent.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional

from solana_token_onchain import get_onchain_token_research
from yahoo_market_data import (
    DEFAULT_STOCK_CRYPTO_BOOK,
    KNOWN_STOCK_TICKERS,
    fetch_yahoo_daily_prices,
    fetch_yahoo_news,
    resolve_yahoo_asset,
)

MANAGEMENT_FEE_RATE = 0.01  # 1% annual (1/10 of classic 2%)
PERFORMANCE_FEE_RATE = 0.10  # 10% of profits (1/2 of classic 20%)

MAX_POSITION_PCT = 0.25
MIN_LIQUIDITY_USD = 5_000.0
BUY_THRESHOLD = 0.30
SELL_THRESHOLD = -0.30


@dataclass
class AnalystSignal:
    analyst: str
    domain: str
    signal: Literal["bullish", "bearish", "neutral"]
    confidence: int
    score: float
    reasoning: str


def _clamp_conf(value: float) -> int:
    return max(0, min(100, int(round(value))))


def _score_to_signal(score: float) -> str:
    if score > 0.15:
        return "bullish"
    if score < -0.15:
        return "bearish"
    return "neutral"


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def liquidity_analyst(profile: dict[str, Any]) -> AnalystSignal:
    pool = profile.get("primary_pool") or {}
    liq = _safe_float(pool.get("liquidity_usd"))
    vol = _safe_float(pool.get("volume_24h_usd"))
    score = 0.0
    reasons: list[str] = []
    if liq >= 100_000:
        score += 0.4
        reasons.append(f"strong TVL ${_fmt(liq)}")
    elif liq >= 25_000:
        score += 0.15
        reasons.append(f"moderate TVL ${_fmt(liq)}")
    elif liq >= MIN_LIQUIDITY_USD:
        score -= 0.1
        reasons.append(f"thin TVL ${_fmt(liq)}")
    else:
        score -= 0.5
        reasons.append("very low liquidity")
    if vol >= 10_000:
        score += 0.2
        reasons.append(f"active 24h vol ${_fmt(vol)}")
    elif vol > 0:
        score += 0.05
    else:
        score -= 0.15
        reasons.append("minimal recent volume")
    return AnalystSignal(
        analyst="liquidity",
        domain="quant",
        signal=_score_to_signal(score),
        confidence=_clamp_conf(abs(score) * 100),
        score=round(score, 3),
        reasoning="; ".join(reasons)[:200] or "liquidity data unavailable",
    )


def safety_analyst(profile: dict[str, Any]) -> AnalystSignal:
    score = 0.0
    reasons: list[str] = []
    if profile.get("mint_authority_renounced"):
        score += 0.35
        reasons.append("mint renounced")
    else:
        score -= 0.45
        reasons.append("active mint authority")
    if profile.get("freeze_authority_renounced"):
        score += 0.25
        reasons.append("freeze renounced")
    else:
        score -= 0.35
        reasons.append("active freeze authority")
    risks = profile.get("risks") or []
    high = sum(1 for r in risks if r.get("severity") == "high")
    if high:
        score -= 0.2 * high
        reasons.append(f"{high} high-severity flags")
    return AnalystSignal(
        analyst="safety",
        domain="quant",
        signal=_score_to_signal(score),
        confidence=_clamp_conf(abs(score) * 90 + 20),
        score=round(score, 3),
        reasoning="; ".join(reasons)[:200],
    )


def concentration_analyst(profile: dict[str, Any]) -> AnalystSignal:
    top3 = profile.get("top3_holder_pct")
    score = 0.0
    reasons: list[str] = []
    if top3 is None:
        return AnalystSignal(
            analyst="concentration",
            domain="quant",
            signal="neutral",
            confidence=20,
            score=0.0,
            reasoning="holder concentration unavailable",
        )
    if top3 < 30:
        score += 0.35
        reasons.append(f"top-3 hold {top3:.1f}% — dispersed")
    elif top3 < 50:
        score += 0.05
        reasons.append(f"top-3 hold {top3:.1f}% — moderate")
    elif top3 < 70:
        score -= 0.25
        reasons.append(f"top-3 hold {top3:.1f}% — concentrated")
    else:
        score -= 0.45
        reasons.append(f"top-3 hold {top3:.1f}% — whale-heavy")
    holders = profile.get("holder_count")
    if holders is not None:
        if holders >= 500:
            score += 0.15
            reasons.append(f"{holders} holders")
        elif holders < 100:
            score -= 0.15
            reasons.append(f"only {holders} holders")
    return AnalystSignal(
        analyst="concentration",
        domain="quant",
        signal=_score_to_signal(score),
        confidence=_clamp_conf(abs(score) * 85 + 25),
        score=round(score, 3),
        reasoning="; ".join(reasons)[:200],
    )


def valuation_analyst(profile: dict[str, Any]) -> AnalystSignal:
    mcap = profile.get("market_cap_usd")
    price = profile.get("price_usd")
    score = 0.0
    reasons: list[str] = []
    if mcap is None or price is None:
        return AnalystSignal(
            analyst="valuation",
            domain="value",
            signal="neutral",
            confidence=15,
            score=0.0,
            reasoning="market cap / price unavailable",
        )
    mcap_f = _safe_float(mcap)
    if 1_000_000 <= mcap_f <= 500_000_000:
        score += 0.2
        reasons.append(f"mid/small cap ${_fmt(mcap_f)}")
    elif mcap_f > 1_000_000_000:
        score += 0.05
        reasons.append(f"large cap ${_fmt(mcap_f)}")
    elif mcap_f < 100_000:
        score -= 0.25
        reasons.append(f"micro cap ${_fmt(mcap_f)} — high idiosyncratic risk")
    change = profile.get("change_24h_pct")
    if change is not None and change != "":
        ch = _safe_float(change)
        if ch > 15:
            score -= 0.2
            reasons.append(f"+{ch:.1f}% 24h — extended")
        elif ch < -15:
            score += 0.1
            reasons.append(f"{ch:.1f}% 24h — potential mean reversion")
    return AnalystSignal(
        analyst="valuation",
        domain="value",
        signal=_score_to_signal(score),
        confidence=_clamp_conf(abs(score) * 70 + 30),
        score=round(score, 3),
        reasoning="; ".join(reasons)[:200],
    )


def run_quant_value_analysts(profile: dict[str, Any]) -> list[AnalystSignal]:
    return [
        liquidity_analyst(profile),
        safety_analyst(profile),
        concentration_analyst(profile),
        valuation_analyst(profile),
    ]


def synthesize_signals(signals: list[AnalystSignal]) -> dict[str, Any]:
    if not signals:
        return {"composite_score": 0.0, "action": "hold", "confidence": 0, "bullish": 0, "bearish": 0, "neutral": 0}
    weighted = 0.0
    weight_sum = 0.0
    counts = {"bullish": 0, "bearish": 0, "neutral": 0}
    for sig in signals:
        counts[sig.signal] = counts.get(sig.signal, 0) + 1
        w = max(sig.confidence, 1)
        weighted += sig.score * w
        weight_sum += w
    composite = weighted / weight_sum if weight_sum else 0.0
    if composite >= BUY_THRESHOLD:
        action = "overweight"
    elif composite <= SELL_THRESHOLD:
        action = "underweight"
    else:
        action = "hold"
    return {
        "composite_score": round(composite, 4),
        "action": action,
        "confidence": _clamp_conf(abs(composite) * 100),
        "signal_counts": counts,
    }


def compute_position_limit(portfolio_value_usd: float, profile: dict[str, Any]) -> dict[str, Any]:
    pool = profile.get("primary_pool") or {}
    liq = _safe_float(pool.get("liquidity_usd"))
    base_pct = MAX_POSITION_PCT
    if liq < MIN_LIQUIDITY_USD:
        final_pct = min(base_pct, 0.05)
        reason = "liquidity below minimum — cap at 5%"
    elif liq < 25_000:
        final_pct = base_pct * 0.5
        reason = "thin liquidity — halved position cap"
    else:
        risks = profile.get("risks") or []
        high_risk = any(r.get("severity") == "high" for r in risks)
        final_pct = base_pct * 0.5 if high_risk else base_pct
        reason = "authority risk — halved cap" if high_risk else "standard risk budget"
    max_notional = _safe_float(portfolio_value_usd) * final_pct
    return {
        "max_allocation_pct": round(final_pct * 100, 2),
        "max_notional_usd": round(max_notional, 2),
        "reason": reason,
    }


def calculate_fees(
    aum_usd: float = 0.0,
    profit_usd: float = 0.0,
    months: float = 12.0,
    high_water_mark: float = 0.0,
) -> dict[str, Any]:
    aum = max(0.0, _safe_float(aum_usd))
    profit = _safe_float(profit_usd)
    months = max(0.0, _safe_float(months, 12.0))
    hwm = max(0.0, _safe_float(high_water_mark))

    management_fee = aum * MANAGEMENT_FEE_RATE * (months / 12.0)
    taxable_profit = max(0.0, profit - hwm)
    performance_fee = taxable_profit * PERFORMANCE_FEE_RATE
    total_fees = management_fee + performance_fee
    net_profit = profit - total_fees

    return {
        "fee_model": "1/10",
        "management_fee_rate_annual_pct": MANAGEMENT_FEE_RATE * 100,
        "performance_fee_rate_pct": PERFORMANCE_FEE_RATE * 100,
        "traditional_comparison": "vs 2/20 (2% mgmt + 20% performance)",
        "aum_usd": round(aum, 2),
        "profit_usd": round(profit, 2),
        "high_water_mark_usd": round(hwm, 2),
        "taxable_profit_usd": round(taxable_profit, 2),
        "management_fee_usd": round(management_fee, 2),
        "performance_fee_usd": round(performance_fee, 2),
        "total_fees_usd": round(total_fees, 2),
        "net_profit_after_fees_usd": round(net_profit, 2),
        "months": months,
    }


def analyze_token_for_portfolio(token: str, portfolio_value_usd: float = 10_000.0) -> dict[str, Any]:
    profile = get_onchain_token_research(token)
    if profile.get("error") or not profile.get("mint"):
        return {"token": token, "error": profile.get("error", "Could not resolve token"), "needs_mint_address": True}

    signals = run_quant_value_analysts(profile)
    synthesis = synthesize_signals(signals)
    limits = compute_position_limit(portfolio_value_usd, profile)
    suggested_usd = limits["max_notional_usd"]
    if synthesis["action"] == "underweight":
        suggested_usd = 0.0
    elif synthesis["action"] == "hold":
        suggested_usd = round(suggested_usd * 0.5, 2)

    return {
        "token": profile.get("symbol") or token,
        "mint": profile.get("mint"),
        "profile_summary": {
            "price_usd": profile.get("price_usd"),
            "market_cap_usd": profile.get("market_cap_usd"),
            "liquidity_usd": (profile.get("primary_pool") or {}).get("liquidity_usd"),
            "holder_count": profile.get("holder_count"),
        },
        "analyst_signals": [s.__dict__ for s in signals],
        "synthesis": synthesis,
        "position_limit": limits,
        "suggested_allocation_usd": suggested_usd,
        "compliance": {
            "max_single_name_pct": MAX_POSITION_PCT * 100,
            "min_liquidity_usd": MIN_LIQUIDITY_USD,
        },
    }


def run_portfolio_analysis(tokens: list[str], capital_usd: float = 10_000.0) -> dict[str, Any]:
    capital = max(100.0, _safe_float(capital_usd, 10_000.0))
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for raw in tokens[:8]:
        row = analyze_token_for_portfolio(raw.strip(), portfolio_value_usd=capital)
        if row.get("error"):
            errors.append(f"{raw}: {row.get('error')}")
        else:
            rows.append(row)

    total_suggested = sum(_safe_float(r.get("suggested_allocation_usd")) for r in rows)
    overweight = [r["token"] for r in rows if r.get("synthesis", {}).get("action") == "overweight"]
    underweight = [r["token"] for r in rows if r.get("synthesis", {}).get("action") == "underweight"]

    return {
        "capital_usd": capital,
        "tokens_analyzed": len(rows),
        "positions": rows,
        "portfolio_summary": {
            "total_suggested_allocation_usd": round(total_suggested, 2),
            "cash_remaining_usd": round(max(0.0, capital - total_suggested), 2),
            "overweight_candidates": overweight,
            "underweight_avoid": underweight,
            "deployment_pct": round((total_suggested / capital) * 100, 2) if capital else 0,
        },
        "fee_structure": get_fee_structure(),
        "errors": errors,
        "governance": "Covenant-inspired: deterministic quant/value signals, code-enforced position limits, LLM macro layer optional.",
    }


def get_fee_structure() -> dict[str, Any]:
    return {
        "name": "BIT Agents Hedge Fund — 1/10 model",
        "management_fee_annual_pct": MANAGEMENT_FEE_RATE * 100,
        "performance_fee_pct": PERFORMANCE_FEE_RATE * 100,
        "traditional_2_20": {"management_pct": 2.0, "performance_pct": 20.0},
        "description": (
            "1% annual management fee on assets under management, plus 10% of net profits "
            "above the high-water mark. Half the cost of the traditional 2/20 hedge fund fee stack."
        ),
        "example_100k_12mo": calculate_fees(100_000, profit_usd=15_000, months=12),
    }


# ─── Mock / historical backtest (Yahoo Finance) ───────────────────────────────


def resolve_backtest_asset(token: str) -> dict[str, Any]:
    return resolve_yahoo_asset(token)


def _price_on_or_after(prices: list[list[float]], target_ms: float) -> Optional[tuple[float, float]]:
    for ts, price in prices:
        if ts >= target_ms:
            return float(ts), float(price)
    if prices:
        return float(prices[-1][0]), float(prices[-1][1])
    return None


def _price_on_or_before(prices: list[list[float]], target_ms: float) -> Optional[tuple[float, float]]:
    chosen = None
    for ts, price in prices:
        if ts <= target_ms:
            chosen = (float(ts), float(price))
        else:
            break
    return chosen or (_price_on_or_after(prices, target_ms) if prices else None)


def _month_starts(start_dt, end_dt) -> list:
    from calendar import monthrange
    from datetime import datetime, timezone

    points = [start_dt]
    y, m = start_dt.year, start_dt.month
    while True:
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
        dt = datetime(y, m, 1, tzinfo=timezone.utc)
        if dt >= end_dt:
            break
        points.append(dt)
    if points[-1].date() != end_dt.date():
        points.append(end_dt)
    return points


def run_mock_backtest(
    tokens: Optional[list[str]] = None,
    start_date: str = "",
    end_date: str = "",
    capital_usd: float = 10_000.0,
    strategy: str = "equal_weight_quarterly_rebalance",
    include_news: bool = True,
) -> dict[str, Any]:
    """Equal-weight mock backtest using Yahoo Finance daily closes + optional news."""
    from datetime import datetime, timezone

    capital = max(100.0, _safe_float(capital_usd, 10_000.0))
    selected = [t.strip() for t in (tokens or []) if t and str(t).strip()]
    if not selected:
        selected = list(DEFAULT_STOCK_CRYPTO_BOOK)
        strategy_note = "Open mandate — selected default stock+crypto book"
    else:
        strategy_note = "User-specified tickers"

    try:
        start_dt = datetime.strptime(start_date[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_dt = datetime.strptime(end_date[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        return {"error": f"Invalid dates: {exc}. Use YYYY-MM-DD."}
    if end_dt <= start_dt:
        return {"error": "end_date must be after start_date."}

    start_ms = start_dt.timestamp() * 1000
    end_ms = end_dt.timestamp() * 1000

    assets: list[dict[str, Any]] = []
    errors: list[str] = []
    for raw in selected[:8]:
        resolved = resolve_yahoo_asset(raw)
        if resolved.get("error"):
            errors.append(resolved["error"])
            continue
        hist = fetch_yahoo_daily_prices(resolved["yahoo_symbol"], start_date[:10], end_date[:10])
        if hist.get("error"):
            errors.append(f"{resolved['symbol']}: {hist['error']}")
            continue
        entry = _price_on_or_after(hist["prices"], start_ms)
        exit_px = _price_on_or_before(hist["prices"], end_ms) or _price_on_or_after(hist["prices"], end_ms)
        if not entry or not exit_px:
            errors.append(f"{resolved['symbol']}: could not locate start/end prices on Yahoo")
            continue
        assets.append(
            {
                "symbol": resolved["symbol"],
                "yahoo_symbol": resolved["yahoo_symbol"],
                "asset_class": resolved.get("asset_class"),
                "prices": hist["prices"],
                "entry_ts": entry[0],
                "entry_price": entry[1],
                "exit_ts": exit_px[0],
                "exit_price": exit_px[1],
            }
        )

    if not assets:
        return {
            "error": "No assets with historical prices on Yahoo Finance.",
            "errors": errors,
            "hint": "Pass stock tickers (AAPL, MSFT, NVDA…) or crypto (BTC, ETH, SOL). Or leave blank for the default book.",
        }

    n = len(assets)
    target_weight = 1.0 / n
    # holdings: units per asset index
    units = [0.0] * n
    trades: list[dict[str, Any]] = []
    buy_count = 0
    sell_count = 0

    # Initial buys
    alloc_each = capital * target_weight
    for i, asset in enumerate(assets):
        u = alloc_each / asset["entry_price"] if asset["entry_price"] else 0.0
        units[i] = u
        buy_count += 1
        trades.append(
            {
                "date": start_dt.date().isoformat(),
                "side": "BUY",
                "symbol": asset["symbol"],
                "notional_usd": round(alloc_each, 2),
                "price_usd": round(asset["entry_price"], 6),
                "units": round(u, 8),
                "note": "Open — equal-weight entry (Yahoo close)",
            }
        )

    # Quarterly rebalance (sell overweight / buy underweight)
    marks = []
    for mark_dt in _month_starts(start_dt, end_dt)[1:]:
        mark_ms = mark_dt.timestamp() * 1000
        prices_now: list[float] = []
        for asset in assets:
            px = _price_on_or_before(asset["prices"], mark_ms) or _price_on_or_after(asset["prices"], mark_ms)
            prices_now.append(px[1] if px else 0.0)
        values = [units[i] * prices_now[i] for i in range(n)]
        total = sum(values)
        marks.append(
            {
                "date": mark_dt.date().isoformat(),
                "portfolio_value_usd": round(total, 2),
                "pnl_usd": round(total - capital, 2),
            }
        )

        # Rebalance only on quarter starts (Feb/May/Aug/Nov already skipped — use month in {1,4,7,10} after start)
        if strategy == "equal_weight_quarterly_rebalance" and mark_dt.month in (1, 4, 7, 10) and mark_dt.date() != end_dt.date():
            if total <= 0:
                continue
            for i, asset in enumerate(assets):
                target_val = total * target_weight
                current_val = values[i]
                delta = target_val - current_val
                if abs(delta) < max(1.0, total * 0.005) or prices_now[i] <= 0:
                    continue
                du = delta / prices_now[i]
                units[i] += du
                side = "BUY" if du > 0 else "SELL"
                if side == "BUY":
                    buy_count += 1
                else:
                    sell_count += 1
                trades.append(
                    {
                        "date": mark_dt.date().isoformat(),
                        "side": side,
                        "symbol": asset["symbol"],
                        "notional_usd": round(abs(delta), 2),
                        "price_usd": round(prices_now[i], 6),
                        "units": round(abs(du), 8),
                        "note": "Quarterly rebalance to equal weight",
                    }
                )

    # Final sells
    positions = []
    end_value = 0.0
    for i, asset in enumerate(assets):
        final_px = asset["exit_price"]
        final_val = units[i] * final_px
        end_value += final_val
        alloc_open = capital * target_weight
        pnl = final_val - alloc_open
        positions.append(
            {
                "symbol": asset["symbol"],
                "yahoo_symbol": asset["yahoo_symbol"],
                "asset_class": asset.get("asset_class"),
                "allocation_pct": round(target_weight * 100, 2),
                "allocation_usd": round(alloc_open, 2),
                "entry_price_usd": round(asset["entry_price"], 6),
                "exit_price_usd": round(final_px, 6),
                "units": round(units[i], 8),
                "end_value_usd": round(final_val, 2),
                "pnl_usd": round(pnl, 2),
                "pnl_pct": round((pnl / alloc_open) * 100, 2) if alloc_open else 0,
            }
        )
        sell_count += 1
        trades.append(
            {
                "date": end_dt.date().isoformat(),
                "side": "SELL",
                "symbol": asset["symbol"],
                "notional_usd": round(final_val, 2),
                "price_usd": round(final_px, 6),
                "units": round(units[i], 8),
                "note": "Close — realize PnL",
            }
        )

    gross_pnl = end_value - capital
    months = max(1.0, (end_dt - start_dt).days / 30.4375)
    fees = calculate_fees(aum_usd=capital, profit_usd=max(0.0, gross_pnl), months=months)
    net_pnl = gross_pnl - fees["total_fees_usd"]

    news = fetch_yahoo_news([a["symbol"] for a in assets]) if include_news else []

    return {
        "strategy": strategy,
        "strategy_note": strategy_note,
        "mode": "mock_backtest",
        "selected_assets": [a["symbol"] for a in assets],
        "start_date": start_dt.date().isoformat(),
        "end_date": end_dt.date().isoformat(),
        "capital_usd": round(capital, 2),
        "allocations": [
            {"symbol": p["symbol"], "allocation_pct": p["allocation_pct"], "allocation_usd": p["allocation_usd"]}
            for p in positions
        ],
        "trade_counts": {
            "buys": buy_count,
            "sells": sell_count,
            "total": buy_count + sell_count,
        },
        "end_value_usd": round(end_value, 2),
        "gross_pnl_usd": round(gross_pnl, 2),
        "gross_pnl_pct": round((gross_pnl / capital) * 100, 2) if capital else 0,
        "fees": fees,
        "net_pnl_usd": round(net_pnl, 2),
        "net_pnl_pct": round((net_pnl / capital) * 100, 2) if capital else 0,
        "positions": positions,
        "monthly_marks": marks,
        "mock_trades": trades,
        "news": news,
        "errors": errors,
        "data_source": "yahoo_finance",
        "disclaimer": "Mock / historical simulation using Yahoo Finance closes — not live trading. Not financial advice.",
    }


def _fmt(value: float) -> str:
    if value >= 1_000_000:
        return f"{value/1_000_000:.2f}M"
    if value >= 1_000:
        return f"{value/1_000:.1f}K"
    return f"{value:.2f}"
