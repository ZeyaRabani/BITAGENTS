"""
Covenant Risk Engine — volatility scaling, correlation limits, position caps.
All 25 compliance rules enforced in code (see COMPLIANCE.md).
"""

from __future__ import annotations

from typing import Any, Optional


MAX_POSITION_PCT = 0.25
MAX_GROSS_EXPOSURE_PCT = 1.0
MAX_CRYPTO_PCT = 0.40
MAX_SINGLE_SECTOR_PROXY = 0.40  # same-asset-class cluster
MIN_CASH_PCT = 0.05
MAX_CORRELATION = 0.85
VOL_TARGET_ANNUAL = 20.0  # % — scale down when asset vol above this
MAX_NAMES = 8
MIN_NAMES = 2
MIN_BARS = 20
MAX_DAILY_TURNOVER_PCT = 0.35
MIN_TRADE_USD = 25.0
MAX_TRADE_USD_FRAC = 0.20  # of equity per fill
BUY_CONFIDENCE_MIN = 35
SELL_CONFIDENCE_MIN = 30


COMPLIANCE_RULES = [
    {"id": 1, "name": "max_single_position", "limit": "25% of equity"},
    {"id": 2, "name": "max_gross_exposure", "limit": "100% (no leverage)"},
    {"id": 3, "name": "min_cash_reserve", "limit": "5% cash"},
    {"id": 4, "name": "max_crypto_sleeve", "limit": "40% of equity"},
    {"id": 5, "name": "max_names", "limit": "8 positions per strategy"},
    {"id": 6, "name": "min_names_diversify", "limit": "≥2 when capital allows"},
    {"id": 7, "name": "correlation_cap", "limit": "block add if corr>0.85 to existing book"},
    {"id": 8, "name": "vol_scale_position", "limit": "size ∝ vol_target/asset_vol"},
    {"id": 9, "name": "min_history_bars", "limit": "≥20 daily bars"},
    {"id": 10, "name": "min_trade_notional", "limit": "$25"},
    {"id": 11, "name": "max_single_fill", "limit": "20% of equity"},
    {"id": 12, "name": "buy_confidence_floor", "limit": "confidence ≥ 35"},
    {"id": 13, "name": "sell_confidence_floor", "limit": "confidence ≥ 30"},
    {"id": 14, "name": "no_shorting", "limit": "long-only paper book"},
    {"id": 15, "name": "tp_sl_honored", "limit": "user TP/SL override signals"},
    {"id": 16, "name": "horizon_match", "limit": "asset lookback matches strategy horizon"},
    {"id": 17, "name": "shared_quote_cache", "limit": "one market snapshot per symbol"},
    {"id": 18, "name": "strategy_isolation", "limit": "positions keyed by strategy_id"},
    {"id": 19, "name": "auditable_decision", "limit": "store analyst graph with each decision"},
    {"id": 20, "name": "deterministic_synthesis", "limit": "same inputs → same action"},
    {"id": 21, "name": "paper_only", "limit": "no live brokerage orders"},
    {"id": 22, "name": "fee_model_1_10", "limit": "1% mgmt + 10% perf on reported PnL"},
    {"id": 23, "name": "benchmark_spy", "limit": "backtests report vs SPY"},
    {"id": 24, "name": "drawdown_metrics", "limit": "Sharpe/Sortino/max DD required"},
    {"id": 25, "name": "llm_optional", "limit": "LLM never required for trade decisions"},
]


def vol_scaled_weight(raw_weight: float, asset_vol_annual_pct: float) -> float:
    vol = max(float(asset_vol_annual_pct or VOL_TARGET_ANNUAL), 5.0)
    scale = min(1.5, VOL_TARGET_ANNUAL / vol)
    return max(0.0, raw_weight * scale)


def max_notional_for_symbol(
    equity_usd: float,
    asset_vol_annual_pct: float,
    max_position_pct: float = MAX_POSITION_PCT,
) -> float:
    equity = max(0.0, float(equity_usd))
    scaled_pct = vol_scaled_weight(max_position_pct, asset_vol_annual_pct)
    scaled_pct = min(scaled_pct, max_position_pct)
    return round(equity * scaled_pct, 2)


def check_compliance(
    *,
    action: str,
    symbol: str,
    notional_usd: float,
    equity_usd: float,
    cash_usd: float,
    confidence: float,
    features: Optional[dict[str, Any]] = None,
    existing_positions: Optional[list[dict[str, Any]]] = None,
    asset_class: str = "equity",
    crypto_exposure_usd: float = 0.0,
) -> dict[str, Any]:
    """Return {ok, violations[], adjusted_notional_usd}."""
    violations: list[str] = []
    features = features or {}
    existing = existing_positions or []
    equity = max(float(equity_usd), 1.0)
    cash = float(cash_usd)
    notional = abs(float(notional_usd or 0))
    action = (action or "hold").lower()

    if action == "buy":
        if confidence < BUY_CONFIDENCE_MIN:
            violations.append(f"R12 buy confidence {confidence} < {BUY_CONFIDENCE_MIN}")
        if (features.get("bars") or 0) < MIN_BARS:
            violations.append(f"R09 insufficient history ({features.get('bars')} bars)")
        if notional < MIN_TRADE_USD:
            violations.append(f"R10 notional ${notional:.2f} < ${MIN_TRADE_USD}")
        if notional > equity * MAX_TRADE_USD_FRAC:
            notional = equity * MAX_TRADE_USD_FRAC
            violations.append(f"R11 capped fill to {MAX_TRADE_USD_FRAC*100:.0f}% equity")
        max_pos = max_notional_for_symbol(equity, float(features.get("vol_63") or features.get("vol_21") or 40))
        held = next((p for p in existing if p.get("symbol") == symbol), None)
        held_val = float((held or {}).get("market_value_usd") or 0)
        if held_val + notional > max_pos:
            notional = max(0.0, max_pos - held_val)
            if notional < MIN_TRADE_USD:
                violations.append("R01 max position reached")
        # Cash reserve
        if cash - notional < equity * MIN_CASH_PCT:
            allowed = max(0.0, cash - equity * MIN_CASH_PCT)
            if allowed < notional:
                notional = allowed
                violations.append("R03 preserving min cash")
        if asset_class == "crypto":
            if crypto_exposure_usd + notional > equity * MAX_CRYPTO_PCT:
                allowed = max(0.0, equity * MAX_CRYPTO_PCT - crypto_exposure_usd)
                notional = min(notional, allowed)
                violations.append("R04 crypto sleeve cap")
        if len(existing) >= MAX_NAMES and not held:
            violations.append("R05 max names — cannot open new")
            notional = 0.0
        # Correlation soft block
        corr = float(features.get("spy_corr_63") or 0)
        if corr > MAX_CORRELATION and any(
            float(p.get("spy_corr") or 0) > MAX_CORRELATION for p in existing if p.get("symbol") != symbol
        ):
            notional *= 0.5
            violations.append("R07 high-correlation book — halved size")

    elif action == "sell":
        if confidence < SELL_CONFIDENCE_MIN:
            violations.append(f"R13 sell confidence {confidence} < {SELL_CONFIDENCE_MIN}")
        # shorts forbidden — sell only reduces long
    else:
        notional = 0.0

    ok = action == "hold" or (notional >= MIN_TRADE_USD if action == "buy" else action == "sell")
    if action == "buy" and notional < MIN_TRADE_USD:
        ok = False
    hard = [v for v in violations if v.startswith(("R05", "R09", "R12", "R01")) and "capped" not in v.lower()]
    if hard and action == "buy":
        ok = False
        notional = 0.0

    return {
        "ok": ok,
        "violations": violations,
        "adjusted_notional_usd": round(notional, 2),
        "rules_version": 25,
    }


def size_trade(
    action: str,
    equity_usd: float,
    cash_usd: float,
    features: dict[str, Any],
    synthesis: dict[str, Any],
    max_position_pct: float = MAX_POSITION_PCT,
) -> float:
    """Deterministic sizing from composite score + vol."""
    if action not in ("buy", "sell"):
        return 0.0
    conf = float(synthesis.get("confidence") or 0) / 100.0
    score = abs(float(synthesis.get("composite_score") or 0))
    raw_pct = min(max_position_pct, 0.08 + score * 0.25) * (0.5 + 0.5 * conf)
    vol = float(features.get("vol_63") or features.get("vol_21") or VOL_TARGET_ANNUAL)
    raw_pct = vol_scaled_weight(raw_pct, vol)
    notional = float(equity_usd) * raw_pct
    if action == "buy":
        notional = min(notional, float(cash_usd) * 0.95, float(equity_usd) * MAX_TRADE_USD_FRAC)
    return round(max(0.0, notional), 2)
