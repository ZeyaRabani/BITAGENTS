"""
Covenant Framework — 18 deterministic analysts (zero LLM dependency).

Quant (5): Technicals, Fundamentals, Valuation, Growth, Sentiment
Value (6): Buffett, Graham, Munger, Pabrai, Fisher, Damodaran
Macro (7): Druckenmiller, Burry, Wood, Lynch, Ackman, Taleb, News Sentiment

Each returns uniform {analyst, domain, signal, confidence, score, reasoning}.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal, Optional


SignalName = Literal["bullish", "bearish", "neutral"]


@dataclass
class AnalystSignal:
    analyst: str
    domain: str
    signal: SignalName
    confidence: int
    score: float
    reasoning: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clamp_conf(value: float) -> int:
    return max(0, min(100, int(round(value))))


def _to_signal(score: float) -> SignalName:
    if score > 0.15:
        return "bullish"
    if score < -0.15:
        return "bearish"
    return "neutral"


def _sig(name: str, domain: str, score: float, reasons: list[str], conf_base: float = 55) -> AnalystSignal:
    score = max(-1.0, min(1.0, score))
    return AnalystSignal(
        analyst=name,
        domain=domain,
        signal=_to_signal(score),
        confidence=_clamp_conf(abs(score) * 70 + conf_base * 0.3),
        score=round(score, 4),
        reasoning="; ".join(reasons)[:220] or "insufficient data",
    )


# ─── Quant domain (5) ─────────────────────────────────────────────────────────

def analyst_technicals(f: dict[str, Any]) -> AnalystSignal:
    score = 0.0
    reasons: list[str] = []
    rsi = f.get("rsi_14")
    if rsi is not None:
        if rsi < 30:
            score += 0.45
            reasons.append(f"RSI {rsi:.0f} oversold")
        elif rsi > 70:
            score -= 0.4
            reasons.append(f"RSI {rsi:.0f} overbought")
        else:
            reasons.append(f"RSI {rsi:.0f} neutral")
    vs20 = f.get("vs_sma20_pct") or 0
    if vs20 > 3:
        score += 0.2
        reasons.append(f"above SMA20 +{vs20:.1f}%")
    elif vs20 < -3:
        score -= 0.15
        reasons.append(f"below SMA20 {vs20:.1f}%")
    mom = f.get("ret_21d") or 0
    if mom > 8:
        score += 0.15
    elif mom < -8:
        score -= 0.15
    return _sig("Technicals", "quant", score, reasons)


def analyst_fundamentals(f: dict[str, Any]) -> AnalystSignal:
    """Price-proxy fundamentals: stability, drawdown quality, vol regime."""
    score = 0.0
    reasons: list[str] = []
    vol = f.get("vol_63") or f.get("vol_21") or 0
    if vol < 25:
        score += 0.35
        reasons.append(f"stable vol {vol:.0f}%")
    elif vol > 60:
        score -= 0.35
        reasons.append(f"elevated vol {vol:.0f}%")
    else:
        reasons.append(f"vol {vol:.0f}%")
    dd = abs(f.get("max_drawdown_pct") or 0)
    if dd < 15:
        score += 0.25
        reasons.append(f"shallow DD {dd:.0f}%")
    elif dd > 40:
        score -= 0.3
        reasons.append(f"deep DD {dd:.0f}%")
    return _sig("Fundamentals", "quant", score, reasons)


def analyst_valuation_q(f: dict[str, Any]) -> AnalystSignal:
    score = 0.0
    reasons: list[str] = []
    from_high = f.get("distance_from_high_pct") or 0  # negative if below high
    if from_high < -20:
        score += 0.35
        reasons.append(f"{from_high:.0f}% off highs — cheaper entry")
    elif from_high > -5:
        score -= 0.2
        reasons.append("near highs — rich")
    alpha = f.get("alpha_21d") or 0
    if alpha < -5:
        score += 0.15
        reasons.append(f"lagging SPY {alpha:.1f}pp (mean-revert)")
    elif alpha > 10:
        score -= 0.1
        reasons.append(f"extended vs SPY +{alpha:.1f}pp")
    return _sig("Valuation", "quant", score, reasons)


def analyst_growth(f: dict[str, Any]) -> AnalystSignal:
    score = 0.0
    reasons: list[str] = []
    r63 = f.get("ret_63d") or 0
    r21 = f.get("ret_21d") or 0
    if r63 > 15 and r21 > 0:
        score += 0.4
        reasons.append(f"growth trend +{r63:.0f}% / 63d")
    elif r63 < -15:
        score -= 0.35
        reasons.append(f"growth stall {r63:.0f}% / 63d")
    else:
        reasons.append(f"63d {r63:.0f}%")
    if (f.get("vs_sma50_pct") or 0) > 0 and r21 > 0:
        score += 0.15
        reasons.append("above SMA50 with positive month")
    return _sig("Growth", "quant", score, reasons)


def analyst_sentiment_q(f: dict[str, Any]) -> AnalystSignal:
    score = 0.0
    reasons: list[str] = []
    r1 = f.get("ret_1d") or 0
    r5 = f.get("ret_5d") or 0
    if r5 > 5:
        score += 0.25
        reasons.append(f"5d momentum +{r5:.1f}%")
    elif r5 < -5:
        score -= 0.25
        reasons.append(f"5d pressure {r5:.1f}%")
    ns = f.get("news_sentiment") or 0
    score += ns * 0.35
    if ns:
        reasons.append(f"headline bias {ns:+.2f}")
    if abs(r1) > 4:
        score -= 0.1 if r1 > 0 else -0.05
        reasons.append(f"1d spike {r1:+.1f}%")
    return _sig("Sentiment", "quant", score, reasons or ["price sentiment balanced"])


# ─── Value domain (6) ─────────────────────────────────────────────────────────

def analyst_buffett(f: dict[str, Any]) -> AnalystSignal:
    score = 0.0
    reasons: list[str] = []
    vol = f.get("vol_63") or 40
    dd = abs(f.get("max_drawdown_pct") or 0)
    if vol < 30 and dd < 25:
        score += 0.4
        reasons.append("durable / low-drama price path")
    elif vol > 55:
        score -= 0.35
        reasons.append("too speculative for Buffett lens")
    from_high = f.get("distance_from_high_pct") or 0
    if from_high < -15 and vol < 45:
        score += 0.25
        reasons.append("margin of safety vs highs")
    return _sig("Buffett", "value", score, reasons, 60)


def analyst_graham(f: dict[str, Any]) -> AnalystSignal:
    score = 0.0
    reasons: list[str] = []
    from_high = f.get("distance_from_high_pct") or 0
    rsi = f.get("rsi_14")
    if from_high < -25:
        score += 0.45
        reasons.append(f"deep discount {from_high:.0f}% from peak")
    elif from_high > -8:
        score -= 0.3
        reasons.append("little margin of safety")
    if rsi is not None and rsi < 35:
        score += 0.2
        reasons.append("Graham-style oversold")
    return _sig("Graham", "value", score, reasons, 58)


def analyst_munger(f: dict[str, Any]) -> AnalystSignal:
    score = 0.0
    reasons: list[str] = []
    # Prefer quality: trend intact, not chaos
    vs50 = f.get("vs_sma50_pct") or 0
    vol = f.get("vol_21") or 0
    if vs50 > 0 and vol < 40:
        score += 0.35
        reasons.append("quality uptrend, contained vol")
    if vol > 70:
        score -= 0.4
        reasons.append("too hard — high vol")
    alpha = f.get("alpha_21d") or 0
    if -3 <= alpha <= 8:
        score += 0.1
        reasons.append("sensible relative performance")
    return _sig("Munger", "value", score, reasons, 55)


def analyst_pabrai(f: dict[str, Any]) -> AnalystSignal:
    score = 0.0
    reasons: list[str] = []
    from_high = f.get("distance_from_high_pct") or 0
    r63 = f.get("ret_63d") or 0
    # Dhandho: asymmetric — beaten down but stabilizing
    if from_high < -30 and r63 > -5:
        score += 0.5
        reasons.append("beaten-down + stabilizing (heads I win)")
    elif from_high < -20:
        score += 0.25
        reasons.append("discounted entry")
    if (f.get("vol_63") or 0) > 80:
        score -= 0.25
        reasons.append("tails too fat")
    return _sig("Pabrai", "value", score, reasons, 55)


def analyst_fisher(f: dict[str, Any]) -> AnalystSignal:
    score = 0.0
    reasons: list[str] = []
    r126 = f.get("ret_126d") or f.get("ret_63d") or 0
    r21 = f.get("ret_21d") or 0
    if r126 > 20 and (f.get("vs_sma50_pct") or 0) > 0:
        score += 0.4
        reasons.append("scuttlebutt growth: sustained advance")
    elif r126 < -20:
        score -= 0.3
        reasons.append("growth story broken")
    if r21 > 0 and r126 > 0:
        score += 0.15
        reasons.append("positive intermediate trend")
    return _sig("Fisher", "value", score, reasons, 55)


def analyst_damodaran(f: dict[str, Any]) -> AnalystSignal:
    score = 0.0
    reasons: list[str] = []
    # Story + numbers: risk vs expected return
    vol = f.get("vol_63") or 40
    r63 = f.get("ret_63d") or 0
    expected = r63  # realized as proxy
    if expected > vol * 0.3:
        score += 0.3
        reasons.append("return justifies risk")
    elif expected < -vol * 0.2:
        score -= 0.35
        reasons.append("risk not compensated")
    from_high = f.get("distance_from_high_pct") or 0
    if -35 < from_high < -10:
        score += 0.2
        reasons.append("valuation reset without distress wipeout")
    return _sig("Damodaran", "value", score, reasons, 55)


# ─── Macro / contrarian domain (7) ────────────────────────────────────────────

def analyst_druckenmiller(f: dict[str, Any]) -> AnalystSignal:
    score = 0.0
    reasons: list[str] = []
    r21 = f.get("ret_21d") or 0
    r5 = f.get("ret_5d") or 0
    if r21 > 5 and r5 > 0:
        score += 0.45
        reasons.append("ride the trend — strong month")
    elif r21 < -8:
        score -= 0.35
        reasons.append("cut losers — weak month")
    alpha = f.get("alpha_21d") or 0
    if alpha > 5:
        score += 0.15
        reasons.append(f"alpha {alpha:+.1f}pp")
    return _sig("Druckenmiller", "macro", score, reasons, 58)


def analyst_burry(f: dict[str, Any]) -> AnalystSignal:
    score = 0.0
    reasons: list[str] = []
    from_high = f.get("distance_from_high_pct") or 0
    rsi = f.get("rsi_14")
    corr = f.get("spy_corr_63") or 0
    if from_high < -35:
        score += 0.4
        reasons.append("deep value / neglected")
    if rsi is not None and rsi > 75 and from_high > -5:
        score -= 0.45
        reasons.append("bubble-ish extension")
    if corr > 0.85 and (f.get("spy_ret_21d") or 0) > 8:
        score -= 0.15
        reasons.append("crowded beta")
    return _sig("Burry", "macro", score, reasons, 55)


def analyst_wood(f: dict[str, Any]) -> AnalystSignal:
    score = 0.0
    reasons: list[str] = []
    vol = f.get("vol_63") or 0
    r63 = f.get("ret_63d") or 0
    if vol > 40 and r63 > 10:
        score += 0.4
        reasons.append("disruptive momentum")
    elif vol > 40 and r63 < -15:
        score -= 0.2
        reasons.append("innovation drawdown — wait")
    if r63 > 25:
        score += 0.2
        reasons.append("explosive growth print")
    return _sig("Wood", "macro", score, reasons, 50)


def analyst_lynch(f: dict[str, Any]) -> AnalystSignal:
    score = 0.0
    reasons: list[str] = []
    r126 = f.get("ret_126d") or f.get("ret_63d") or 0
    vs50 = f.get("vs_sma50_pct") or 0
    # Tenbagger scent: strong intermediate, not overextended short-term
    if r126 > 30 and (f.get("rsi_14") or 50) < 70:
        score += 0.4
        reasons.append("growth compounding without blow-off")
    elif vs50 < -10 and r126 > 0:
        score += 0.2
        reasons.append("dip in longer uptrend — shop")
    if r126 < -25:
        score -= 0.3
        reasons.append("story deteriorating")
    return _sig("Lynch", "macro", score, reasons, 55)


def analyst_ackman(f: dict[str, Any]) -> AnalystSignal:
    score = 0.0
    reasons: list[str] = []
    # Concentrated conviction: clear directional edge
    alpha = f.get("alpha_21d") or 0
    r63 = f.get("ret_63d") or 0
    if abs(alpha) > 8 or abs(r63) > 20:
        score += 0.25 if (alpha > 0 or r63 > 0) else -0.25
        reasons.append("activism-style directional edge")
    dd = abs(f.get("max_drawdown_pct") or 0)
    if dd > 45 and (f.get("ret_21d") or 0) > 3:
        score += 0.25
        reasons.append("catalyst bounce after deep DD")
    return _sig("Ackman", "macro", score, reasons or ["no clear catalyst"], 52)


def analyst_taleb(f: dict[str, Any]) -> AnalystSignal:
    score = 0.0
    reasons: list[str] = []
    vol = f.get("vol_21") or 0
    r1 = abs(f.get("ret_1d") or 0)
    # Prefer antifragile setups: avoid fragile crowded longs near highs
    from_high = f.get("distance_from_high_pct") or 0
    if from_high > -5 and vol < 20:
        score -= 0.35
        reasons.append("fragile calm near highs")
    if vol > 50 and from_high < -20:
        score += 0.3
        reasons.append("optionality after stress")
    if r1 > 6:
        score -= 0.15
        reasons.append("jump risk elevated")
    return _sig("Taleb", "macro", score, reasons or ["tail risk acceptable"], 55)


def analyst_news_sentiment(f: dict[str, Any]) -> AnalystSignal:
    ns = f.get("news_sentiment") or 0.0
    n = f.get("news_count") or 0
    score = ns * 0.8
    reasons = []
    if n == 0:
        return _sig("News Sentiment", "macro", 0.0, ["no recent headlines"], 25)
    if ns > 0.2:
        reasons.append(f"constructive headlines ({n})")
    elif ns < -0.2:
        reasons.append(f"negative headline skew ({n})")
    else:
        reasons.append(f"mixed headlines ({n})")
    return _sig("News Sentiment", "macro", score, reasons, 50)


ALL_ANALYSTS = [
    analyst_technicals,
    analyst_fundamentals,
    analyst_valuation_q,
    analyst_growth,
    analyst_sentiment_q,
    analyst_buffett,
    analyst_graham,
    analyst_munger,
    analyst_pabrai,
    analyst_fisher,
    analyst_damodaran,
    analyst_druckenmiller,
    analyst_burry,
    analyst_wood,
    analyst_lynch,
    analyst_ackman,
    analyst_taleb,
    analyst_news_sentiment,
]


def run_all_analysts(features: dict[str, Any]) -> list[AnalystSignal]:
    if features.get("error"):
        return [
            AnalystSignal(
                analyst="System",
                domain="quant",
                signal="neutral",
                confidence=10,
                score=0.0,
                reasoning=str(features.get("error")),
            )
        ]
    return [fn(features) for fn in ALL_ANALYSTS]


def synthesize_signals(
    signals: list[AnalystSignal],
    buy_threshold: float = 0.22,
    sell_threshold: float = -0.22,
) -> dict[str, Any]:
    """Confidence-weighted scoring — same inputs ⇒ same decision."""
    if not signals:
        return {
            "composite_score": 0.0,
            "action": "hold",
            "confidence": 0,
            "signal_counts": {"bullish": 0, "bearish": 0, "neutral": 0},
            "domain_scores": {},
        }
    weighted = 0.0
    weight_sum = 0.0
    counts = {"bullish": 0, "bearish": 0, "neutral": 0}
    domain_acc: dict[str, list[tuple[float, float]]] = {}
    for sig in signals:
        counts[sig.signal] = counts.get(sig.signal, 0) + 1
        w = max(sig.confidence, 1)
        weighted += sig.score * w
        weight_sum += w
        domain_acc.setdefault(sig.domain, []).append((sig.score, w))

    composite = weighted / weight_sum if weight_sum else 0.0
    if composite >= buy_threshold:
        action = "buy"
    elif composite <= sell_threshold:
        action = "sell"
    else:
        action = "hold"

    domain_scores = {}
    for domain, pairs in domain_acc.items():
        tw = sum(w for _, w in pairs) or 1
        domain_scores[domain] = round(sum(s * w for s, w in pairs) / tw, 4)

    return {
        "composite_score": round(composite, 4),
        "action": action,
        "confidence": _clamp_conf(abs(composite) * 100),
        "signal_counts": counts,
        "domain_scores": domain_scores,
        "buy_threshold": buy_threshold,
        "sell_threshold": sell_threshold,
    }


def signals_to_dicts(signals: list[AnalystSignal]) -> list[dict[str, Any]]:
    return [s.to_dict() for s in signals]
