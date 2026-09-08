"""Solana token / mint due diligence — built from shared on-chain research cache."""

from __future__ import annotations

from typing import Any, Optional

from dca_agent import SOLANA_CLUSTER
from solana_token_onchain import (
    TOKEN_RESEARCH_CACHE_TTL_SECONDS,
    _fmt_usd,
    extract_token_query,
    format_unresolved_token_reply,
    get_mint_authorities,
    get_onchain_token_research,
    has_min_onchain_data,
)

__all__ = [
    "get_mint_authorities",
    "run_due_diligence_report",
    "build_due_diligence_from_profile",
    "format_due_diligence_reply",
    "extract_diligence_query",
]


def _grade_from_score(score: int) -> str:
    if score >= 80:
        return "A"
    if score >= 65:
        return "B"
    if score >= 50:
        return "C"
    return "D"


def build_due_diligence_from_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Compute diligence score/grade from an on-chain token profile."""
    score = 70
    findings: list[str] = []
    risks = list(profile.get("risks") or [])

    if profile.get("mint_authority_renounced"):
        findings.append("Mint authority renounced (supply cannot be inflated).")
    else:
        score -= 20
        findings.append("Mint authority is still set — supply can be inflated.")

    if profile.get("freeze_authority_renounced"):
        findings.append("Freeze authority renounced.")
    else:
        score -= 15
        findings.append("Freeze authority is still set — accounts could be frozen.")

    pool = profile.get("primary_pool") or {}
    liq = pool.get("liquidity_usd")
    if liq is not None:
        try:
            liq_f = float(liq)
            if liq_f < 10_000:
                score -= 10
                findings.append(f"Limited DEX liquidity (Meteora TVL {_fmt_usd(liq_f)}).")
            else:
                findings.append(f"Meteora pool TVL: {_fmt_usd(liq_f)}.")
        except (TypeError, ValueError):
            pass
    else:
        score -= 5
        findings.append("No indexed Meteora pool found — liquidity data limited.")

    top3 = profile.get("top3_holder_pct")
    if top3 is not None:
        if top3 > 50:
            score -= 10
            findings.append(f"Top 3 holders control ~{top3:.1f}% of supply.")
        else:
            findings.append(f"Top 3 holders: ~{top3:.1f}% of supply.")

    overlay = profile.get("easya_overlay") or {}
    if overlay:
        if overlay.get("verified"):
            score += 5
            findings.append("Verified on EASY Screener.")
        else:
            score -= 5
            findings.append("Not verified on EASY Screener.")

    price = profile.get("price_usd")
    if price is None:
        score -= 5
        findings.append("No Jupiter price available.")

    score = max(0, min(100, score))
    grade = _grade_from_score(score)

    return {
        "symbol": profile.get("symbol"),
        "name": profile.get("name"),
        "mint": profile.get("mint"),
        "due_diligence_score": score,
        "grade": grade,
        "findings": findings,
        "risks": risks,
        "on_chain_profile": profile,
        "authorities": {
            "mint_authority": None if profile.get("mint_authority_renounced") else "active",
            "freeze_authority": None if profile.get("freeze_authority_renounced") else "active",
            "mint_authority_renounced": profile.get("mint_authority_renounced"),
            "freeze_authority_renounced": profile.get("freeze_authority_renounced"),
        },
        "analytics": {
            "price_usd": profile.get("price_usd"),
            "market_cap_usd": profile.get("market_cap_usd"),
            "liquidity_usd": liq,
            "volume_24h_usd": pool.get("volume_24h_usd"),
            "holder_count": profile.get("holder_count"),
        },
        "top_holders": profile.get("top_holders") or [],
        "top3_holder_pct": top3,
        "explorer_url": profile.get("explorer_url"),
        "data_sources": profile.get("data_sources") or ["solana_rpc", "jupiter", "meteora_datapi"],
        "cached": profile.get("cached"),
        "cache_ttl_seconds": profile.get("cache_ttl_seconds") or TOKEN_RESEARCH_CACHE_TTL_SECONDS,
        "cluster": SOLANA_CLUSTER,
        "recommendation": (
            "Proceed with caution and size positions conservatively."
            if score < 65
            else "Fundamentals look acceptable for further research; confirm thesis before trading."
        ),
        "disclaimer": "Informational due diligence only — not a formal audit.",
    }


def run_due_diligence_report(token: str, holder_limit: int = 10) -> dict[str, Any]:
    """Full due diligence report using shared 15-minute on-chain cache per mint."""
    profile = get_onchain_token_research(token, holder_limit=holder_limit)
    if profile.get("error"):
        return {**profile, "query": token, "needs_mint_address": True}
    if not has_min_onchain_data(profile):
        return {
            "error": "On-chain mint data incomplete for this identifier.",
            "query": token,
            "needs_mint_address": True,
            "instruction": "Ask the user for the exact Solana mint address.",
        }
    return build_due_diligence_from_profile(profile)


def format_due_diligence_reply(report: dict[str, Any]) -> str:
    if report.get("error") or report.get("needs_mint_address"):
        query = str(report.get("query") or report.get("symbol") or "this token")
        return format_unresolved_token_reply(query, report)

    profile = report.get("on_chain_profile") or {}
    lines = [
        f"**Due Diligence Report — {report.get('symbol')}**",
        f"Name: {report.get('name') or report.get('symbol')}",
        f"Mint: `{report.get('mint')}`",
        f"Explorer: {report.get('explorer_url')}",
    ]
    if report.get("cached") or profile.get("cached"):
        ttl = int(report.get("cache_ttl_seconds") or TOKEN_RESEARCH_CACHE_TTL_SECONDS)
        lines.append(
            f"_Cached on-chain snapshot (shared across agents, refreshes every {ttl // 60} minutes)._"
        )

    lines.extend(
        [
            "",
            f"**Composite score:** {report.get('due_diligence_score')}/100 · Grade **{report.get('grade')}**",
            "",
            "**Authorities (Solana RPC)**",
            f"- Mint authority renounced: {'yes' if report.get('authorities', {}).get('mint_authority_renounced') else 'no'}",
            f"- Freeze authority renounced: {'yes' if report.get('authorities', {}).get('freeze_authority_renounced') else 'no'}",
        ]
    )

    analytics = report.get("analytics") or {}
    lines.extend(
        [
            "",
            "**Market & liquidity**",
            f"- Price: {_fmt_usd(analytics.get('price_usd'))}",
            f"- Market cap (est.): {_fmt_usd(analytics.get('market_cap_usd'))}",
            f"- Meteora pool TVL: {_fmt_usd(analytics.get('liquidity_usd'))}",
            f"- 24h volume: {_fmt_usd(analytics.get('volume_24h_usd'))}",
            f"- Holders (indexed): {analytics.get('holder_count') if analytics.get('holder_count') is not None else 'see top holders'}",
        ]
    )

    top = report.get("top_holders") or []
    if top:
        lines.extend(["", "**Top holders (Solana RPC)**"])
        for row in top[:5]:
            wallet = row.get("wallet") or row.get("token_account") or "unknown"
            pct = row.get("percent_of_supply")
            pct_s = f"{pct:.2f}%" if pct is not None else "n/a"
            lines.append(f"- {wallet}: {pct_s}")
        if report.get("top3_holder_pct") is not None:
            lines.append(f"- Top 3 wallets: ~{report['top3_holder_pct']:.1f}% of supply")

    findings = report.get("findings") or []
    if findings:
        lines.extend(["", "**Findings**"])
        for item in findings:
            lines.append(f"- {item}")

    risks = report.get("risks") or []
    if risks:
        lines.extend(["", "**Risk flags**"])
        for risk in risks:
            lines.append(f"- [{risk.get('severity', 'info').upper()}] {risk.get('title')}: {risk.get('detail')}")

    lines.extend(
        [
            "",
            f"**Recommendation:** {report.get('recommendation')}",
            "",
            "Data: Solana RPC + Jupiter + Meteora. Not a formal audit.",
            report.get("disclaimer", ""),
            "Not financial advice. DYOR.",
        ]
    )
    return "\n".join(lines)


def extract_diligence_query(user_input: str) -> Optional[str]:
    """Extract token symbol or mint from a due-diligence-style prompt."""
    return extract_token_query(user_input)
