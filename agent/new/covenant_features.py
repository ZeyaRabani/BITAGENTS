"""Deterministic market features from Yahoo price series (no LLM)."""

from __future__ import annotations

import math
from typing import Any, Optional


def closes_from_prices(prices: list[list[float]]) -> list[float]:
    return [float(p[1]) for p in prices if p and len(p) >= 2]


def pct_change(a: float, b: float) -> float:
    if not a:
        return 0.0
    return ((b - a) / a) * 100.0


def sma(values: list[float], window: int) -> Optional[float]:
    if len(values) < window or window <= 0:
        return None
    chunk = values[-window:]
    return sum(chunk) / len(chunk)


def stdev(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    var = sum((x - mean) ** 2 for x in values) / (n - 1)
    return math.sqrt(var)


def returns(closes: list[float]) -> list[float]:
    out = []
    for i in range(1, len(closes)):
        if closes[i - 1]:
            out.append((closes[i] - closes[i - 1]) / closes[i - 1])
    return out


def rsi(closes: list[float], period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(-period, 0):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def max_drawdown_pct(closes: list[float]) -> float:
    if not closes:
        return 0.0
    peak = closes[0]
    max_dd = 0.0
    for c in closes:
        peak = max(peak, c)
        if peak:
            max_dd = min(max_dd, (c - peak) / peak)
    return max_dd * 100.0


def correlation(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    if n < 5:
        return 0.0
    a, b = a[-n:], b[-n:]
    ma, mb = sum(a) / n, sum(b) / n
    num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((x - mb) ** 2 for x in b))
    if da == 0 or db == 0:
        return 0.0
    return num / (da * db)


def compute_features(
    closes: list[float],
    spy_closes: Optional[list[float]] = None,
    news_titles: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Build a feature dict used by all 18 Covenant analysts."""
    if len(closes) < 5:
        return {"error": "insufficient_bars", "bars": len(closes)}

    rets = returns(closes)
    last = closes[-1]
    feat: dict[str, Any] = {
        "bars": len(closes),
        "price": last,
        "ret_1d": pct_change(closes[-2], last) if len(closes) >= 2 else 0.0,
        "ret_5d": pct_change(closes[-6], last) if len(closes) >= 6 else pct_change(closes[0], last),
        "ret_21d": pct_change(closes[-22], last) if len(closes) >= 22 else pct_change(closes[0], last),
        "ret_63d": pct_change(closes[-64], last) if len(closes) >= 64 else pct_change(closes[0], last),
        "ret_126d": pct_change(closes[-127], last) if len(closes) >= 127 else pct_change(closes[0], last),
        "ret_252d": pct_change(closes[0], last) if len(closes) >= 2 else 0.0,
        "sma_20": sma(closes, 20),
        "sma_50": sma(closes, min(50, len(closes))),
        "sma_200": sma(closes, min(200, len(closes))) if len(closes) >= 50 else None,
        "rsi_14": rsi(closes, 14),
        "vol_21": stdev(rets[-21:]) * math.sqrt(252) * 100 if len(rets) >= 5 else 0.0,
        "vol_63": stdev(rets[-63:]) * math.sqrt(252) * 100 if len(rets) >= 20 else 0.0,
        "max_drawdown_pct": max_drawdown_pct(closes),
        "distance_from_high_pct": pct_change(max(closes), last),
        "distance_from_low_pct": pct_change(min(closes), last),
    }

    # Trend: price vs SMAs
    if feat["sma_50"]:
        feat["vs_sma50_pct"] = pct_change(feat["sma_50"], last)
    else:
        feat["vs_sma50_pct"] = 0.0
    if feat["sma_20"]:
        feat["vs_sma20_pct"] = pct_change(feat["sma_20"], last)
    else:
        feat["vs_sma20_pct"] = 0.0

    if spy_closes and len(spy_closes) >= 10:
        spy_rets = returns(spy_closes)
        feat["spy_corr_63"] = correlation(rets[-63:], spy_rets[-63:])
        if len(spy_closes) >= 22:
            feat["spy_ret_21d"] = pct_change(spy_closes[-22], spy_closes[-1])
            feat["alpha_21d"] = feat["ret_21d"] - feat["spy_ret_21d"]
        else:
            feat["spy_ret_21d"] = 0.0
            feat["alpha_21d"] = feat["ret_21d"]
    else:
        feat["spy_corr_63"] = 0.0
        feat["spy_ret_21d"] = 0.0
        feat["alpha_21d"] = feat["ret_21d"]

    # Deterministic news sentiment from title keywords
    titles = news_titles or []
    pos_kw = ("surge", "rally", "beat", "record", "growth", "upgrade", "bull", "profit", "gain", "strong")
    neg_kw = ("crash", "plunge", "miss", "fraud", "downgrade", "bear", "loss", "lawsuit", "weak", "cut", "fear")
    pos = neg = 0
    for t in titles:
        low = t.lower()
        pos += sum(1 for k in pos_kw if k in low)
        neg += sum(1 for k in neg_kw if k in low)
    total = pos + neg
    feat["news_count"] = len(titles)
    feat["news_sentiment"] = ((pos - neg) / total) if total else 0.0  # -1..1

    return feat
