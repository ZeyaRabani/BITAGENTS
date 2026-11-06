"""
Covenant pipeline: Yahoo features → 18 analysts → synthesis → risk-sized decision.
Also performance metrics (Sharpe / Sortino / max DD / SPY benchmark).
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any, Optional

from covenant_analysts import run_all_analysts, signals_to_dicts, synthesize_signals
from covenant_features import closes_from_prices, compute_features, returns
from covenant_risk import COMPLIANCE_RULES, check_compliance, size_trade
from yahoo_market_data import fetch_yahoo_daily_prices, fetch_yahoo_news, resolve_yahoo_asset


def _fetch_closes(symbol: str, lookback_days: int = 365) -> tuple[list[float], dict[str, Any]]:
    resolved = resolve_yahoo_asset(symbol)
    if resolved.get("error"):
        return [], resolved
    end = date.today()
    start = end - timedelta(days=lookback_days + 5)
    hist = fetch_yahoo_daily_prices(resolved["yahoo_symbol"], start.isoformat(), end.isoformat())
    if hist.get("error"):
        return [], {"error": hist["error"], **resolved}
    return closes_from_prices(hist["prices"]), resolved


def analyze_yahoo_asset(
    symbol: str,
    lookback_days: int = 365,
    equity_usd: float = 10_000.0,
    cash_usd: float = 10_000.0,
    existing_positions: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Full 18-analyst decision graph for one Yahoo asset (deterministic)."""
    closes, resolved = _fetch_closes(symbol, lookback_days)
    if resolved.get("error") and not closes:
        return {"symbol": symbol, "error": resolved.get("error")}
    spy_closes, _ = _fetch_closes("SPY", lookback_days)
    news = fetch_yahoo_news([resolved.get("symbol") or symbol], limit_per_symbol=3)
    titles = [n.get("title") or "" for n in news]
    features = compute_features(closes, spy_closes=spy_closes or None, news_titles=titles)
    if features.get("error"):
        return {"symbol": resolved.get("symbol") or symbol, "error": features["error"]}

    signals = run_all_analysts(features)
    synthesis = synthesize_signals(signals)
    action = synthesis["action"]
    notional = size_trade(action, equity_usd, cash_usd, features, synthesis)
    crypto_exp = sum(
        float(p.get("market_value_usd") or 0)
        for p in (existing_positions or [])
        if p.get("asset_class") == "crypto"
    )
    compliance = check_compliance(
        action=action,
        symbol=resolved["symbol"],
        notional_usd=notional,
        equity_usd=equity_usd,
        cash_usd=cash_usd,
        confidence=synthesis["confidence"],
        features=features,
        existing_positions=existing_positions,
        asset_class=resolved.get("asset_class") or "equity",
        crypto_exposure_usd=crypto_exp,
    )
    final_action = action
    if action == "buy" and not compliance["ok"]:
        final_action = "hold"
    sized = compliance["adjusted_notional_usd"] if final_action == "buy" else (
        notional if final_action == "sell" else 0.0
    )

    return {
        "symbol": resolved["symbol"],
        "yahoo_symbol": resolved["yahoo_symbol"],
        "asset_class": resolved.get("asset_class"),
        "features": {
            k: features[k]
            for k in (
                "price",
                "ret_1d",
                "ret_5d",
                "ret_21d",
                "ret_63d",
                "vol_21",
                "vol_63",
                "rsi_14",
                "max_drawdown_pct",
                "distance_from_high_pct",
                "alpha_21d",
                "spy_corr_63",
                "news_sentiment",
                "bars",
            )
            if k in features
        },
        "analyst_signals": signals_to_dicts(signals),
        "analyst_count": len(signals),
        "synthesis": synthesis,
        "action": final_action,
        "suggested_notional_usd": sized,
        "compliance": compliance,
        "decision_graph": {
            "inputs": {"symbol": resolved["symbol"], "lookback_days": lookback_days},
            "domains": synthesis.get("domain_scores"),
            "signal_counts": synthesis.get("signal_counts"),
            "composite_score": synthesis.get("composite_score"),
            "action": final_action,
            "violations": compliance.get("violations") or [],
        },
        "llm_required": False,
        "governance": "Covenant 18-analyst deterministic pipeline",
    }


def compute_performance_metrics(
    equity_curve: list[float],
    spy_curve: Optional[list[float]] = None,
    periods_per_year: float = 252.0,
) -> dict[str, Any]:
    """Sharpe, Sortino, max drawdown, and optional SPY benchmark stats."""
    if len(equity_curve) < 3:
        return {"error": "insufficient equity curve"}
    rets = returns(equity_curve)
    if not rets:
        return {"error": "no returns"}
    mean_r = sum(rets) / len(rets)
    # population-ish std
    var = sum((r - mean_r) ** 2 for r in rets) / max(len(rets) - 1, 1)
    std = math.sqrt(var) if var > 0 else 0.0
    downside = [r for r in rets if r < 0]
    dvar = sum(r ** 2 for r in downside) / max(len(downside), 1)
    dstd = math.sqrt(dvar) if dvar > 0 else 0.0
    sharpe = (mean_r / std) * math.sqrt(periods_per_year) if std > 0 else 0.0
    sortino = (mean_r / dstd) * math.sqrt(periods_per_year) if dstd > 0 else 0.0

    peak = equity_curve[0]
    max_dd = 0.0
    for v in equity_curve:
        peak = max(peak, v)
        if peak:
            max_dd = min(max_dd, (v - peak) / peak)

    total_ret = (equity_curve[-1] / equity_curve[0] - 1.0) if equity_curve[0] else 0.0
    out: dict[str, Any] = {
        "total_return_pct": round(total_ret * 100, 2),
        "sharpe": round(sharpe, 3),
        "sortino": round(sortino, 3),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "observations": len(rets),
    }

    if spy_curve and len(spy_curve) >= 3:
        # align lengths
        n = min(len(equity_curve), len(spy_curve))
        e = equity_curve[-n:]
        s = spy_curve[-n:]
        spy_ret = (s[-1] / s[0] - 1.0) if s[0] else 0.0
        out["spy_return_pct"] = round(spy_ret * 100, 2)
        out["alpha_vs_spy_pct"] = round((total_ret - spy_ret) * 100, 2)
        # beta approx
        er = returns(e)
        sr = returns(s)
        m = min(len(er), len(sr))
        if m > 5:
            er, sr = er[-m:], sr[-m:]
            me, ms = sum(er) / m, sum(sr) / m
            cov = sum((er[i] - me) * (sr[i] - ms) for i in range(m)) / (m - 1)
            var_s = sum((x - ms) ** 2 for x in sr) / (m - 1)
            beta = cov / var_s if var_s > 0 else 0.0
            out["beta_vs_spy"] = round(beta, 3)
    return out


def build_equity_curve_from_marks(
    capital: float,
    marks: list[dict[str, Any]],
    end_value: float,
) -> list[float]:
    curve = [float(capital)]
    for m in marks:
        curve.append(float(m.get("portfolio_value_usd") or curve[-1]))
    if not marks or abs(curve[-1] - end_value) > 0.01:
        curve.append(float(end_value))
    return curve


def compliance_summary() -> dict[str, Any]:
    return {"rules": COMPLIANCE_RULES, "count": len(COMPLIANCE_RULES), "llm_required": False}
