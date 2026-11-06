"""
Horizon-aware asset selection — no fixed DEFAULT book.

Two-pass rank:
1) Fast price features for the liquid universe
2) Full 18-analyst + news on the top shortlist
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any, Optional

HF_MIN_HORIZON_DAYS = max(1, int(os.environ.get("HF_MIN_HORIZON_DAYS", "3")))

from covenant_analysts import run_all_analysts, synthesize_signals
from covenant_features import closes_from_prices, compute_features
from hedge_fund_learning import symbol_learned_adjustment
from yahoo_market_data import (
    CANDIDATE_UNIVERSE,
    fetch_yahoo_daily_prices,
    fetch_yahoo_news,
    resolve_yahoo_asset,
)

HORIZON_PRESETS = {
    "ultra_short": {"days": 7, "lookback": 60, "prefer": "momentum", "max_names": 4},
    "short": {"days": 30, "lookback": 90, "prefer": "momentum", "max_names": 5},
    "medium": {"days": 90, "lookback": 180, "prefer": "balanced", "max_names": 6},
    "long": {"days": 180, "lookback": 365, "prefer": "value_quality", "max_names": 7},
    "strategic": {"days": 365, "lookback": 400, "prefer": "value_quality", "max_names": 8},
}


def clamp_horizon_days(days: Optional[int]) -> Optional[int]:
    """Finite horizons must run at least HF_MIN_HORIZON_DAYS (default 3). 0/None stay open-ended."""
    if days is None:
        return None
    try:
        d = int(days)
    except (TypeError, ValueError):
        return None
    if d <= 0:
        return None
    return max(HF_MIN_HORIZON_DAYS, d)


def parse_horizon_days(text: str = "", horizon_days: Optional[int] = None) -> Optional[int]:
    """
    Return horizon in days, or None for open-ended (user closes manually).
    Explicit horizon_days <= 0 means open-ended.
    Positive horizons shorter than HF_MIN_HORIZON_DAYS are raised to that minimum.
    """
    if horizon_days is not None:
        try:
            d = int(horizon_days)
        except (TypeError, ValueError):
            d = 0
        return clamp_horizon_days(d)

    import re

    t = text or ""
    if re.search(
        r"\b(no\s+(?:fixed\s+)?(?:time|horizon|duration)|open[- ]?ended|indefinite|"
        r"until\s+i\s+close|no\s+end|manual(?:ly)?\s+close)\b",
        t,
        re.I,
    ):
        return None

    m = re.search(
        r"\b(?:for|over|next|within|horizon|trade(?:\s+for)?|duration)\s+(\d+(?:\.\d+)?)\s*"
        r"(day|days|week|weeks|month|months|year|years)\b",
        t,
        re.I,
    )
    if not m:
        m = re.search(
            r"\b(\d+(?:\.\d+)?)\s*(day|days|week|weeks|month|months|year|years)\b",
            t,
            re.I,
        )
    if m:
        n = float(m.group(1))
        unit = m.group(2).lower()
        if unit.startswith("day"):
            return clamp_horizon_days(int(round(n)))
        if unit.startswith("week"):
            return clamp_horizon_days(int(round(n * 7)))
        if unit.startswith("month"):
            return clamp_horizon_days(int(round(n * 30)))
        if unit.startswith("year"):
            return clamp_horizon_days(int(round(n * 365)))
    # Default: open-ended (user can close anytime)
    return None


def parse_asset_count(text: str = "") -> Optional[int]:
    """
    Extract an explicit "N stocks/tokens/assets/names/coins" count from free text,
    e.g. "choose only 2 stocks" -> 2. Returns None when no count is stated.
    """
    import re

    t = text or ""
    m = re.search(
        r"\b(\d{1,2})\s+(?:stocks?|tokens?|coins?|assets?|names?|tickers?|equities|companies)\b",
        t,
        re.I,
    )
    if not m:
        return None
    n = int(m.group(1))
    if n <= 0:
        return None
    return min(n, 12)


def horizon_days_for_picker(days: Optional[int]) -> int:
    """Asset picker needs a lookback tilt even when strategy is open-ended."""
    return int(days) if days and days > 0 else 90


def horizon_preset(days: int) -> dict[str, Any]:
    if days <= 10:
        key = "ultra_short"
    elif days <= 45:
        key = "short"
    elif days <= 120:
        key = "medium"
    elif days <= 270:
        key = "long"
    else:
        key = "strategic"
    preset = dict(HORIZON_PRESETS[key])
    preset["key"] = key
    preset["horizon_days"] = days
    return preset


def _tilt(features: dict[str, Any], prefer: str) -> float:
    if prefer == "momentum":
        return 0.002 * float(features.get("ret_21d") or 0) + 0.001 * float(features.get("ret_5d") or 0)
    if prefer == "value_quality":
        return -0.002 * float(features.get("distance_from_high_pct") or 0) - 0.001 * max(
            0.0, float(features.get("vol_63") or 40) - 30
        )
    return 0.001 * float(features.get("alpha_21d") or 0)


def parse_asset_class_preference(text: str = "") -> str:
    """Return 'stocks', 'crypto', or 'any' from user wording."""
    import re

    t = text or ""
    if re.search(
        r"\b(only\s+(?:\d+\s+)?stocks?|stocks?\s+only|equit(?:y|ies)\s+only|no\s+crypto|"
        r"stock(?:s)?\s+(?:and\s+)?(?:not|no)\s+crypto|just\s+(?:\d+\s+)?stocks?)\b",
        t,
        re.I,
    ):
        return "stocks"
    if re.search(
        r"\b(only\s+(?:\d+\s+)?crypto|crypto\s+only|no\s+stocks?|just\s+(?:\d+\s+)?crypto|tokens?\s+only)\b",
        t,
        re.I,
    ):
        return "crypto"
    return "any"


# Words the LLM / user may pass that are NOT tickers
MANDATE_NON_TICKERS = frozenset(
    {
        "STOCK",
        "STOCKS",
        "CRYPTO",
        "CRYPTOS",
        "EQUITY",
        "EQUITIES",
        "TOKEN",
        "TOKENS",
        "ASSET",
        "ASSETS",
        "COIN",
        "COINS",
        "SHARE",
        "SHARES",
        "ETF",
        "ETFS",
        "INDEX",
        "INDEXES",
        "INDICES",
        "USDC",
        "USDT",
        "USD",
        "CASH",
        "LIVE",
        "PAPER",
        "MAX",
        "PROFIT",
        "PROFITS",
        "HORIZON",
        "CAPITAL",
        "STRATEGY",
        "FUND",
        "AGENT",
        "PICK",
        "PICKS",
        "ONLY",
        "ANY",
        "BEST",
    }
)


def filter_real_tickers(symbols: Optional[list[str]]) -> list[str]:
    """Drop empty / mandate words so agent pick can run."""
    out: list[str] = []
    for s in symbols or []:
        sym = str(s or "").strip().upper()
        if not sym or sym in MANDATE_NON_TICKERS:
            continue
        if sym in out:
            continue
        out.append(sym)
    return out


def _fallback_book(allow_crypto: bool, crypto_only: bool, n_take: int) -> list[str]:
    """Instant liquid book when Yahoo ranking is empty/slow."""
    crypto = {"BTC", "ETH", "SOL", "XRP", "AVAX", "LINK"}
    equities = [s for s in CANDIDATE_UNIVERSE if s.upper() not in crypto]
    if crypto_only:
        return list(crypto)[: max(2, n_take)]
    if not allow_crypto:
        return equities[: max(2, n_take)]
    # Mixed: mostly stocks + light crypto
    book = equities[: max(2, n_take - 1)]
    for c in ("BTC", "ETH"):
        if len(book) >= n_take:
            break
        book.append(c)
    return book[:n_take]


def select_assets_for_horizon(
    horizon_days: int = 90,
    max_names: Optional[int] = None,
    allow_crypto: bool = True,
    crypto_only: bool = False,
    universe: Optional[list[str]] = None,
    exclude: Optional[list[str]] = None,
    fast: Optional[bool] = None,
) -> dict[str, Any]:
    preset = horizon_preset(horizon_days)
    lookback = int(preset["lookback"])
    n_take = int(max_names or preset["max_names"])
    prefer = preset["prefer"]
    # Short horizons: skip news pass (was ~40s+) so chat agent pick stays responsive
    use_fast = True if fast is None and horizon_days <= 14 else bool(fast)
    exclude_set = {s.upper() for s in (exclude or [])}
    candidates = [c for c in (universe or CANDIDATE_UNIVERSE) if c.upper() not in exclude_set]
    if crypto_only:
        allow_crypto = True
        crypto_set = {"BTC", "ETH", "SOL", "XRP", "AVAX", "LINK"}
        candidates = [c for c in candidates if c.upper() in crypto_set] or list(crypto_set)
    elif not allow_crypto:
        crypto_set = {"BTC", "ETH", "SOL", "XRP", "AVAX", "LINK"}
        candidates = [c for c in candidates if c.upper() not in crypto_set]
    # Fast path: score a liquid core book only (chat must stay under ~10s)
    if use_fast and universe is None:
        core_stocks = [
            "NVDA", "AAPL", "MSFT", "META", "AMZN", "GOOGL", "TSLA", "AMD",
            "AVGO", "JPM", "XOM", "LLY", "PLTR", "UBER", "SPY", "QQQ",
        ]
        core_crypto = ["BTC", "ETH", "SOL", "XRP"]
        if crypto_only:
            candidates = core_crypto
        elif not allow_crypto:
            candidates = [c for c in core_stocks if c not in exclude_set]
        else:
            candidates = [c for c in (core_stocks + core_crypto) if c not in exclude_set]

    end = date.today()
    start = end - timedelta(days=lookback + 5)
    start_s, end_s = start.isoformat(), end.isoformat()

    spy_hist = fetch_yahoo_daily_prices("SPY", start_s, end_s)
    spy_closes = closes_from_prices(spy_hist.get("prices") or []) if not spy_hist.get("error") else []

    # Pass 1 — fast features (no news)
    prelim: list[dict[str, Any]] = []
    errors: list[str] = []
    closes_cache: dict[str, list[float]] = {}
    resolved_cache: dict[str, dict[str, Any]] = {}

    for raw in candidates:
        resolved = resolve_yahoo_asset(raw, probe=False)
        if resolved.get("error"):
            continue
        if crypto_only and resolved.get("asset_class") != "crypto":
            continue
        if not allow_crypto and resolved.get("asset_class") == "crypto":
            continue
        hist = fetch_yahoo_daily_prices(resolved["yahoo_symbol"], start_s, end_s)
        if hist.get("error"):
            errors.append(f"{resolved['symbol']}: {hist['error']}")
            continue
        closes = closes_from_prices(hist["prices"])
        if len(closes) < 10:
            continue
        features = compute_features(closes, spy_closes=spy_closes or None, news_titles=[])
        if features.get("error"):
            continue
        # Cheap composite proxy before full 18-analyst
        proxy = (
            0.3 * (1 if (features.get("ret_21d") or 0) > 0 else -1)
            + 0.2 * (1 if (features.get("rsi_14") or 50) < 45 else (-1 if (features.get("rsi_14") or 50) > 65 else 0))
            + 0.2 * (1 if (features.get("distance_from_high_pct") or 0) < -10 else 0)
            + _tilt(features, prefer)
        )
        sym = resolved["symbol"]
        closes_cache[sym] = closes
        resolved_cache[sym] = resolved
        prelim.append({"symbol": sym, "proxy": proxy, "features": features, "asset_class": resolved.get("asset_class")})

    prelim.sort(key=lambda r: r["proxy"], reverse=True)
    shortlist = prelim[: max(12, n_take * 3)]

    ranked: list[dict[str, Any]] = []
    if use_fast:
        for row in shortlist:
            sym = row["symbol"]
            features = row["features"]
            signals = run_all_analysts(features)
            synthesis = synthesize_signals(signals)
            learned = symbol_learned_adjustment(sym)
            score = float(synthesis["composite_score"]) + _tilt(features, prefer) + learned
            ranked.append(
                {
                    "symbol": sym,
                    "yahoo_symbol": resolved_cache[sym]["yahoo_symbol"],
                    "asset_class": row["asset_class"],
                    "score": round(score, 4),
                    "action": synthesis["action"],
                    "confidence": synthesis["confidence"],
                    "composite_score": synthesis["composite_score"],
                    "learned_adjustment": round(learned, 5),
                    "features_summary": {
                        "ret_21d": features.get("ret_21d"),
                        "vol_63": features.get("vol_63"),
                        "rsi_14": features.get("rsi_14"),
                        "distance_from_high_pct": features.get("distance_from_high_pct"),
                    },
                    "domain_scores": synthesis.get("domain_scores"),
                }
            )
    else:
        # Pass 2 — full 18 analysts + news on shortlist
        for row in shortlist:
            sym = row["symbol"]
            news = fetch_yahoo_news([sym], limit_per_symbol=2)
            titles = [n.get("title") or "" for n in news]
            features = compute_features(closes_cache[sym], spy_closes=spy_closes or None, news_titles=titles)
            signals = run_all_analysts(features)
            synthesis = synthesize_signals(signals)
            learned = symbol_learned_adjustment(sym)
            score = float(synthesis["composite_score"]) + _tilt(features, prefer) + learned
            ranked.append(
                {
                    "symbol": sym,
                    "yahoo_symbol": resolved_cache[sym]["yahoo_symbol"],
                    "asset_class": row["asset_class"],
                    "score": round(score, 4),
                    "action": synthesis["action"],
                    "confidence": synthesis["confidence"],
                    "composite_score": synthesis["composite_score"],
                    "learned_adjustment": round(learned, 5),
                    "features_summary": {
                        "ret_21d": features.get("ret_21d"),
                        "vol_63": features.get("vol_63"),
                        "rsi_14": features.get("rsi_14"),
                        "distance_from_high_pct": features.get("distance_from_high_pct"),
                    },
                    "domain_scores": synthesis.get("domain_scores"),
                }
            )

    ranked.sort(key=lambda r: (r["action"] == "buy", r["score"]), reverse=True)

    selected: list[dict[str, Any]] = []
    crypto_count = 0
    for row in ranked:
        if len(selected) >= n_take:
            break
        if row["asset_class"] == "crypto":
            if crypto_only:
                pass
            elif crypto_count >= max(1, n_take // 3):
                continue
            crypto_count += 1
        if row["action"] == "sell" and len(selected) >= max(2, n_take // 2):
            continue
        selected.append(row)

    if len(selected) < 2:
        for row in ranked:
            if any(s["symbol"] == row["symbol"] for s in selected):
                continue
            selected.append(row)
            if len(selected) >= 2:
                break

    # Hard fallback so agent pick never returns empty
    if len(selected) < 2:
        for sym in _fallback_book(allow_crypto, crypto_only, n_take):
            if any(s["symbol"] == sym for s in selected):
                continue
            selected.append(
                {
                    "symbol": sym,
                    "yahoo_symbol": f"{sym}-USD" if crypto_only or sym in {"BTC", "ETH", "SOL", "XRP", "AVAX", "LINK"} else sym,
                    "asset_class": "crypto" if sym in {"BTC", "ETH", "SOL", "XRP", "AVAX", "LINK"} else "equity",
                    "score": 0.0,
                    "action": "hold",
                    "confidence": 0.4,
                    "composite_score": 0.0,
                    "features_summary": {},
                    "domain_scores": {},
                }
            )
            if len(selected) >= n_take:
                break

    method = "covenant_18_analyst_fast" if use_fast else "covenant_18_analyst_horizon_rank"
    return {
        "horizon_days": horizon_days,
        "preset": preset,
        "selected": selected,
        "symbols": [s["symbol"] for s in selected],
        "ranked_preview": ranked[:12],
        "universe_size": len(candidates),
        "shortlist_size": len(shortlist),
        "errors": errors[:8],
        "method": method,
        "allow_crypto": allow_crypto,
        "crypto_only": crypto_only,
        "note": (
            f"Selected {len(selected)} assets for {horizon_days}d horizon "
            f"({preset['key']}, prefer={prefer}"
            f"{', stocks-only' if not allow_crypto else ''}"
            f"{', crypto-only' if crypto_only else ''}"
            f") via {method}, scores tilted by learned reward from past round-trips."
        ),
    }
