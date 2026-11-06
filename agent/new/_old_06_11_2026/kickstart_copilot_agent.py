"""
EasyA Analysis Agent - Solana token discovery, analytics, and guidance.

Free for users (wallet sign-in required). Token data from EASY Screener (cached 1h per mint).
"""

from __future__ import annotations

import json
import hashlib
import os
import re
import threading
import time
from typing import Any, Optional

import requests

from hosted_llm import CAPIX_MODEL, DEFAULT_LLM_MODEL, call_llm, use_capix
from dca_agent import SOLANA_CLUSTER
from db import (
    add_watchlist_token,
    compare_watchlist_tokens,
    list_watchlist,
    remove_watchlist_token,
)
from easya_screener_client import (
    ATTRIBUTION,
    CACHE_TTL_SECONDS,
    get_allowlist_prompt_block,
    get_token_bundle,
    list_tokens as screener_list_tokens,
    resolve_token as screener_resolve_token,
    screener_configured,
    search_tokens as screener_search,
)
from shared_governance import GOVERNANCE_PROMPT

KICKSTART_MODEL = (
    CAPIX_MODEL
    if use_capix()
    else os.environ.get(
        "KICKSTART_COPILOT_MODEL",
        os.environ.get("DCA_MODEL", os.environ.get("OPEN_ROUTER_MODEL", DEFAULT_LLM_MODEL)),
    )
)

OPERATION_GUIDES: dict[str, dict[str, Any]] = {
    "burn_tokens": {
        "summary": "Permanently destroy tokens from circulation.",
        "benefits": ["Reduces supply", "Can signal commitment to holders"],
        "risks": ["Irreversible", "Wrong amount or token cannot be undone"],
        "steps": [
            "Confirm mint and amount with your team",
            "Use a trusted burn tool or send to a known burn address",
            "Verify supply change on-chain",
        ],
        "tools": ["Solana CLI", "Squads", "EasyA Kickstart burn flow"],
    },
    "lock_liquidity": {
        "summary": "Time-lock LP tokens so liquidity cannot be removed early.",
        "benefits": ["Builds trust", "Reduces rug-pull risk perception"],
        "risks": ["Locked funds are inaccessible until unlock", "Wrong pool or duration"],
        "steps": [
            "Identify LP token mint from your DEX pool",
            "Choose lock duration and provider",
            "Lock LP tokens and publish proof link",
        ],
        "tools": ["Streamflow", "UNCX", "Team Finance", "Solana lock providers"],
    },
    "relock_liquidity": {
        "summary": "Extend or renew an existing liquidity lock before it expires.",
        "benefits": ["Maintains community trust", "Avoids unlock FUD"],
        "risks": ["Missing deadline leaves liquidity unlocked", "Provider fees"],
        "steps": ["Check current lock expiry", "Initiate re-lock with same provider", "Announce new expiry"],
        "tools": ["Streamflow", "Original lock provider dashboard"],
    },
    "migrate_liquidity": {
        "summary": "Move liquidity from one pool/DEX to another.",
        "benefits": ["Better routing", "Consolidated volume", "Upgrade to new token version"],
        "risks": ["Temporary price impact", "User confusion", "Smart contract risk on new pool"],
        "steps": [
            "Communicate migration timeline",
            "Remove/add liquidity on target DEX",
            "Update docs and links",
        ],
        "tools": ["Raydium", "Orca", "Meteora", "Jupiter limit orders"],
    },
    "verify_contract": {
        "summary": "Publish verified source on a block explorer.",
        "benefits": ["Transparency", "Easier audits", "Community trust"],
        "risks": ["Exposes implementation details if not audited", "Verification mismatch breaks trust"],
        "steps": [
            "Build reproducible artifact",
            "Submit to Solscan/SolanaFM verify flow",
            "Match on-chain program ID exactly",
        ],
        "tools": ["Solscan verify", "SolanaFM", "Anchor verify"],
    },
    "transfer_ownership": {
        "summary": "Move admin/upgrade authority to another wallet or multisig.",
        "benefits": ["Operational security", "Multisig governance"],
        "risks": ["Wrong recipient is catastrophic", "Loss of control if multisig misconfigured"],
        "steps": ["Prepare recipient wallet/multisig", "Transfer authority on-chain", "Test admin actions"],
        "tools": ["Squads multisig", "Solana CLI", "Program-specific admin UI"],
    },
    "renounce_ownership": {
        "summary": "Permanently remove admin control (mint/freeze/upgrade where applicable).",
        "benefits": ["Maximum decentralization signal", "No admin key risk"],
        "risks": ["Cannot fix bugs or upgrade", "Irreversible"],
        "steps": ["Audit code thoroughly first", "Renounce mint/freeze/upgrade authorities", "Verify on explorer"],
        "tools": ["Solana CLI", "Squads", "EasyA Kickstart renounce flow"],
    },
    "vesting": {
        "summary": "Schedule token unlocks for team, investors, or contributors.",
        "benefits": ["Aligns incentives", "Reduces sell pressure"],
        "risks": ["Complex schedules confuse community", "Cliff/unlock calendar must be public"],
        "steps": ["Define recipients and schedule", "Deploy vesting contracts", "Publish dashboard link"],
        "tools": ["Streamflow", "Magna", "Sablier-style Solana vesting"],
    },
    "staking": {
        "summary": "Reward holders for locking or delegating tokens.",
        "benefits": ["Retention", "Governance participation", "Yield narrative"],
        "risks": ["Emission dilution", "Smart contract exploit surface", "Mercenary capital"],
        "steps": ["Design emissions and duration", "Deploy staking program", "Audit and launch UI"],
        "tools": ["Marinade-style staking", "Custom Anchor program", "Realms governance"],
    },
    "treasury": {
        "summary": "Manage project funds across wallets and multisigs.",
        "benefits": ["Operational runway", "Transparent grants"],
        "risks": ["Key compromise", "Poor OPSEC", "Concentrated treasury"],
        "steps": ["Use multisig", "Separate hot/cold wallets", "Publish treasury policy"],
        "tools": ["Squads", "Goki", "Realms", "Solana FM portfolio"],
    },
}

TOOL_RECOMMENDATIONS: dict[str, list[str]] = {
    "liquidity_locking": ["Streamflow", "UNCX", "Team Finance"],
    "token_migration": ["Raydium", "Orca", "Meteora", "Jupiter"],
    "vesting": ["Streamflow", "Magna"],
    "contract_verification": ["Solscan", "SolanaFM", "Anchor verify"],
    "explorer": ["Solscan", "SolanaFM", "Solana Explorer"],
    "portfolio_tracking": ["Solana FM", "Step Finance", "Birdeye"],
    "analytics": ["EASY Screener", "Birdeye", "DexScreener"],
    "dex_trading": ["Jupiter", "Raydium", "Orca"],
    "multisig": ["Squads", "Goki"],
    "launch": ["EasyA Kickstart", "Raydium launchlab"],
}


def call_openrouter(messages: list) -> dict[str, Any]:
    return call_llm(
        messages,
        model=KICKSTART_MODEL,
        tools=TOOLS,
        temperature=0.3,
        app_suffix="EasyA Analysis",
    )


def _screener_gate() -> Optional[dict[str, Any]]:
    if screener_configured():
        return None
    return {
        "error": "EZ_API_KEY is not configured. Add it to agent/new/.env to use EASY Screener.",
        "code": "INVALID_KEY",
    }


def _normalize_token_input(token: str) -> str:
    return (token or "").strip().lstrip("$")


def _token_bundle(token: str) -> dict[str, Any]:
    blocked = _screener_gate()
    if blocked:
        return blocked
    return get_token_bundle(_normalize_token_input(token))


def _resolve_screener_token(token: str) -> dict[str, Any]:
    blocked = _screener_gate()
    if blocked:
        return blocked
    result = screener_resolve_token(_normalize_token_input(token))
    if isinstance(result, dict) and result.get("error"):
        return result
    return result if isinstance(result, dict) else {"error": "Token not found on EASY Screener."}


def _row(bundle: dict[str, Any]) -> dict[str, Any]:
    if bundle.get("error"):
        return bundle
    return bundle.get("token") or {}


def list_verified_kickstart_tokens(
    category: Optional[str] = None,
    tag: Optional[str] = None,
    active_only: bool = True,
    query: Optional[str] = None,
) -> dict[str, Any]:
    blocked = _screener_gate()
    if blocked:
        return blocked

    q = (query or "").strip()
    if q:
        result = screener_search(q, limit=20)
        if result.get("error"):
            return result
        tokens = result.get("tokens") or []
    else:
        result = screener_list_tokens(page=0, limit=50, verified_only=active_only)
        if result.get("error"):
            return result
        tokens = result.get("tokens") or []

    tag_q = (tag or category or "").strip().lower()
    if tag_q:
        filtered = []
        for t in tokens:
            tags = [str(x).lower() for x in (t.get("tags") or [])]
            hay = " ".join(
                [str(t.get("symbol") or ""), str(t.get("name") or ""), " ".join(tags)]
            ).lower()
            if tag_q in hay:
                filtered.append(t)
        tokens = filtered

    return {
        "source": "easy_screener",
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
        "count": len(tokens),
        "tokens": tokens,
        "attribution": ATTRIBUTION,
        "note": "Tokens indexed on EASY Screener. Use search_tokens or get_token_overview for any symbol or mint.",
    }


def search_tokens(
    query: str,
    limit: int = 10,
    verified_only: bool = False,
    tag: Optional[str] = None,
    category: Optional[str] = None,
) -> dict[str, Any]:
    query = (query or "").strip()
    if not query:
        return {"error": "Search query is required.", "tokens": []}

    blocked = _screener_gate()
    if blocked:
        return blocked

    limit = max(1, min(int(limit), 20))
    result = screener_search(query, limit=limit)
    if result.get("error"):
        return result

    tokens = result.get("tokens") or []
    if verified_only:
        tokens = [t for t in tokens if t.get("is_verified")]

    tag_q = (tag or category or "").strip().lower()
    if tag_q:
        filtered = []
        for t in tokens:
            tags = [str(x).lower() for x in (t.get("tags") or [])]
            hay = " ".join(
                [str(t.get("symbol") or ""), str(t.get("name") or ""), " ".join(tags)]
            ).lower()
            if tag_q in hay:
                filtered.append(t)
        tokens = filtered or tokens

    return {
        "query": query,
        "source": "easy_screener",
        "count": min(len(tokens), limit),
        "tokens": tokens[:limit],
        "attribution": ATTRIBUTION,
        "note": "Results from EASY Screener search. Disambiguate by mint or market cap if multiple matches.",
    }


def get_token_overview(token: str) -> dict[str, Any]:
    bundle = _token_bundle(token)
    if bundle.get("error"):
        return bundle
    row = _row(bundle)
    summary = bundle.get("summary") or {}
    description = ""
    if isinstance(summary, dict):
        description = (
            summary.get("summary")
            or summary.get("description")
            or summary.get("text")
            or ""
        )
    return {
        "symbol": row.get("symbol"),
        "name": row.get("name"),
        "mint": row.get("mint"),
        "description": description or row.get("name"),
        "launch_date": row.get("created_at"),
        "blockchain": row.get("chain") or "Solana",
        "cluster": SOLANA_CLUSTER,
        "verified": row.get("is_verified"),
        "price_usd": row.get("price_usd"),
        "market_cap_usd": row.get("market_cap_usd"),
        "liquidity_usd": row.get("liquidity_usd"),
        "fdv_usd": row.get("fdv_usd"),
        "holder_count": row.get("holder_count"),
        "volume_24h_usd": row.get("volume_24h_usd"),
        "tags": row.get("tags") or [],
        "created_at": row.get("created_at"),
        "dex": row.get("dex"),
        "links": {
            "website": row.get("website"),
            "twitter": row.get("twitter"),
            "telegram": row.get("telegram"),
            "github": row.get("github"),
            "explorer": f"https://solscan.io/token/{row.get('mint')}",
        },
        "ai_summary": summary,
        "locked_supply": bundle.get("locked_supply"),
        "attribution": ATTRIBUTION,
    }


def get_token_analytics(token: str) -> dict[str, Any]:
    bundle = _token_bundle(token)
    if bundle.get("error"):
        return bundle
    row = _row(bundle)
    return {
        "symbol": row.get("symbol"),
        "mint": row.get("mint"),
        "price_usd": row.get("price_usd"),
        "market_cap_usd": row.get("market_cap_usd"),
        "liquidity_usd": row.get("liquidity_usd"),
        "fdv_usd": row.get("fdv_usd"),
        "holder_count": row.get("holder_count"),
        "volume_24h_usd": row.get("volume_24h_usd"),
        "price_change_5m_pct": row.get("price_change_5m_pct"),
        "price_change_1h_pct": row.get("price_change_1h_pct"),
        "price_change_6h_pct": row.get("price_change_6h_pct"),
        "price_change_24h_pct": row.get("price_change_24h_pct"),
        "verified": row.get("is_verified"),
        "attribution": ATTRIBUTION,
        "note": "Null numeric fields mean upstream data is missing - do not treat as zero.",
    }


def get_token_performance(token: str, days: int = 7) -> dict[str, Any]:
    bundle = _token_bundle(token)
    if bundle.get("error"):
        return bundle
    row = _row(bundle)
    days = max(1, min(int(days), 30))
    return {
        "symbol": row.get("symbol"),
        "mint": row.get("mint"),
        "lookback_days": days,
        "price_change_5m_pct": row.get("price_change_5m_pct"),
        "price_change_1h_pct": row.get("price_change_1h_pct"),
        "price_change_6h_pct": row.get("price_change_6h_pct"),
        "price_change_24h_pct": row.get("price_change_24h_pct"),
        "liquidity_usd": row.get("liquidity_usd"),
        "volume_24h_usd": row.get("volume_24h_usd"),
        "holder_count": row.get("holder_count"),
        "market_cap_usd": row.get("market_cap_usd"),
        "attribution": ATTRIBUTION,
        "note": "EASY Screener exposes recent price-change windows; summarize trends in plain language.",
    }


def get_top_token_holders(token: str, limit: int = 10) -> dict[str, Any]:
    """Fetch largest SPL token accounts from Solana RPC (real on-chain data)."""
    from dca_agent import resolve_token, sol_rpc

    limit = max(1, min(int(limit), 20))
    bundle = _token_bundle(token)
    if bundle.get("error"):
        resolved = resolve_token(token)
        if "error" in resolved:
            return resolved
        mint = resolved["mint"]
        symbol = resolved["symbol"]
        holder_count_screener = None
    else:
        row = _row(bundle)
        mint = row.get("mint")
        symbol = row.get("symbol")
        holder_count_screener = row.get("holder_count")

    if not mint:
        return {"error": "Could not resolve token mint."}

    largest = sol_rpc("getTokenLargestAccounts", [mint, {"commitment": "confirmed"}])
    accounts = (largest or {}).get("value") or []
    if not accounts:
        return {
            "error": "No holder data returned from Solana RPC for this mint.",
            "symbol": symbol,
            "mint": mint,
        }

    supply = sol_rpc("getTokenSupply", [mint])
    total_ui = float(((supply or {}).get("value") or {}).get("uiAmount") or 0)

    holders: list[dict[str, Any]] = []
    for rank, acct in enumerate(accounts[:limit], start=1):
        token_account = acct.get("address")
        ui_amount = float(acct.get("uiAmount") or 0)
        pct = round((ui_amount / total_ui) * 100, 4) if total_ui > 0 else None
        owner_wallet = None
        if token_account:
            info = sol_rpc(
                "getAccountInfo",
                [token_account, {"encoding": "jsonParsed", "commitment": "confirmed"}],
            )
            parsed = (((info or {}).get("value") or {}).get("data") or {}).get("parsed") or {}
            owner_wallet = (parsed.get("info") or {}).get("owner")
        holders.append(
            {
                "rank": rank,
                "wallet": owner_wallet,
                "token_account": token_account,
                "amount": ui_amount,
                "percent_of_supply": pct,
            }
        )

    return {
        "symbol": symbol,
        "mint": mint,
        "total_supply": total_ui,
        "holder_count_screener": holder_count_screener,
        "top_holders": holders,
        "source": "solana_rpc_getTokenLargestAccounts",
        "attribution": "On-chain holder balances via Solana RPC. Total holder count from EASY Screener when available.",
    }


def _locked_percent(locked: Optional[dict[str, Any]]) -> Optional[float]:
    if not locked:
        return None
    for key in ("percent", "percentLocked", "lockedPercent"):
        value = locked.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return None


def _risks_from_bundle(bundle: dict[str, Any], row: dict[str, Any]) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []

    liq = row.get("liquidity_usd")
    if liq is not None and liq < 5_000:
        risks.append({
            "severity": "medium",
            "title": "Low liquidity",
            "detail": "Large trades may cause high slippage; exit risk elevated.",
        })

    pct_locked = _locked_percent(bundle.get("locked_supply"))
    if pct_locked is not None and pct_locked < 50:
        risks.append({
            "severity": "medium",
            "title": "Low locked supply",
            "detail": f"Only {pct_locked:.1f}% locked per EASY Screener Streamflow data.",
        })

    if row.get("is_verified") is False:
        risks.append({
            "severity": "low",
            "title": "Not verified on EASY Screener",
            "detail": "Extra diligence recommended for unverified listings.",
        })

    summary = bundle.get("summary") or {}
    trust = summary.get("trustScore") or summary.get("githubTrustScore")
    if isinstance(trust, (int, float)) and trust < 35:
        risks.append({
            "severity": "medium",
            "title": "Low EASY Screener trust score",
            "detail": f"Trust score {trust}/100 - review AI + GitHub diligence summary.",
        })

    return risks


def analyze_token_health(token: str) -> dict[str, Any]:
    bundle = _token_bundle(token)
    if bundle.get("error"):
        return bundle
    row = _row(bundle)
    risk_items = _risks_from_bundle(bundle, row)
    summary = bundle.get("summary") or {}

    strengths: list[str] = []
    weaknesses: list[str] = []
    score = 50

    if row.get("is_verified"):
        strengths.append("Verified on EASY Screener")
        score += 10

    liq = row.get("liquidity_usd")
    if liq is not None:
        if liq >= 50_000:
            strengths.append("Meaningful DEX liquidity")
            score += 10
        elif liq < 5_000:
            weaknesses.append("Low liquidity")
            score -= 10

    holders = row.get("holder_count")
    if holders is not None:
        if holders >= 1000:
            strengths.append("Broad holder base")
            score += 8
        elif holders < 100:
            weaknesses.append("Small holder count")
            score -= 8

    trust = summary.get("trustScore") or summary.get("githubTrustScore")
    if isinstance(trust, (int, float)):
        if trust >= 70:
            strengths.append(f"Strong EASY Screener trust score ({trust})")
            score += 8
        elif trust < 40:
            weaknesses.append(f"Low EASY Screener trust score ({trust})")
            score -= 8

    pct_locked = _locked_percent(bundle.get("locked_supply"))
    if pct_locked is not None:
        if pct_locked >= 80:
            strengths.append(f"High locked supply ({pct_locked:.1f}%)")
            score += 8
        elif pct_locked < 20:
            weaknesses.append(f"Low locked supply ({pct_locked:.1f}%)")
            score -= 6

    for r in risk_items:
        if r.get("severity") == "high":
            weaknesses.append(r.get("title", "High severity risk"))
            score -= 12
        elif r.get("severity") == "medium":
            weaknesses.append(r.get("title", "Medium risk"))
            score -= 5

    if not any(r.get("severity") == "high" for r in risk_items):
        strengths.append("No critical red flags in available EASY Screener data")

    vol = row.get("volume_24h_usd")
    if vol is not None and liq is not None and vol < 1_000 and liq > 0:
        weaknesses.append("Low 24h trading volume")

    if not row.get("website"):
        weaknesses.append("Limited public website link on EASY Screener")

    score = max(0, min(100, score))
    return {
        "symbol": row.get("symbol"),
        "mint": row.get("mint"),
        "strengths": strengths or ["Insufficient data for strengths"],
        "weaknesses": weaknesses or ["No major weaknesses flagged from available data"],
        "overall_health_score": score,
        "analytics_snapshot": {
            "price_usd": row.get("price_usd"),
            "market_cap_usd": row.get("market_cap_usd"),
            "liquidity_usd": row.get("liquidity_usd"),
            "volume_24h_usd": row.get("volume_24h_usd"),
            "holder_count": row.get("holder_count"),
            "price_change_24h_pct": row.get("price_change_24h_pct"),
        },
        "easya_summary": summary or None,
        "summary_unavailable": bundle.get("summary_unavailable"),
        "risks": risk_items,
        "attribution": ATTRIBUTION,
    }


def get_improvement_suggestions(token: str) -> dict[str, Any]:
    health = analyze_token_health(token)
    if health.get("error"):
        return health
    suggestions = []
    for w in health.get("weaknesses") or []:
        wl = w.lower()
        if "liquidity" in wl:
            suggestions.append("Add or deepen DEX liquidity and publish lock proof on EASY Screener.")
        if "holder" in wl:
            suggestions.append("Run community campaigns and improve token utility to grow holders.")
        if "volume" in wl:
            suggestions.append("Increase market making visibility, DEX incentives, or partnerships.")
        if "website" in wl or "documentation" in wl:
            suggestions.append("Publish docs and verified social links on your Kickstart profile.")
        if "lock" in wl:
            suggestions.append("Increase Streamflow lock coverage and link proof on EASY Screener.")
        if "trust" in wl:
            suggestions.append("Improve GitHub activity and transparency to raise EASY Screener trust score.")
    if not suggestions:
        suggestions.append("Maintain transparency: keep liquidity locked, docs updated, and metrics public.")
    return {
        "symbol": health.get("symbol"),
        "mint": health.get("mint"),
        "health_score": health.get("overall_health_score"),
        "suggestions": list(dict.fromkeys(suggestions)),
        "attribution": ATTRIBUTION,
    }


def detect_token_risks(token: str) -> dict[str, Any]:
    bundle = _token_bundle(token)
    if bundle.get("error"):
        return bundle
    row = _row(bundle)
    return {
        "symbol": row.get("symbol"),
        "mint": row.get("mint"),
        "risks": _risks_from_bundle(bundle, row),
        "attribution": ATTRIBUTION,
    }


def compare_tokens(tokens: list[str]) -> dict[str, Any]:
    if not tokens or len(tokens) < 2:
        return {"error": "Provide at least two EasyA Kickstart tokens to compare (symbols or mints)."}
    rows = []
    for t in tokens[:5]:
        overview = get_token_overview(t)
        if overview.get("error"):
            return overview
        rows.append(overview)
    return {"count": len(rows), "comparison": rows, "attribution": ATTRIBUTION}


def get_operation_guide(operation: str) -> dict[str, Any]:
    key = (operation or "").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "burn": "burn_tokens",
        "lock": "lock_liquidity",
        "relock": "relock_liquidity",
        "migrate": "migrate_liquidity",
        "verify": "verify_contract",
        "ownership": "transfer_ownership",
        "renounce": "renounce_ownership",
        "vesting": "vesting",
        "stake": "staking",
        "staking": "staking",
        "treasury": "treasury",
    }
    key = aliases.get(key, key)
    guide = OPERATION_GUIDES.get(key)
    if not guide:
        return {
            "error": f"Unknown operation '{operation}'.",
            "available": sorted(OPERATION_GUIDES.keys()),
        }
    return {"operation": key, **guide}


def recommend_tools(task: str) -> dict[str, Any]:
    task_key = (task or "").strip().lower().replace(" ", "_")
    matches = []
    for category, tools in TOOL_RECOMMENDATIONS.items():
        if task_key in category or category in task_key:
            matches.append({"category": category, "tools": tools})
    if not matches:
        for category, tools in TOOL_RECOMMENDATIONS.items():
            if any(word in category for word in task_key.split("_") if len(word) > 3):
                matches.append({"category": category, "tools": tools})
    if not matches:
        return {
            "task": task,
            "recommendations": [
                {"category": k, "tools": v} for k, v in list(TOOL_RECOMMENDATIONS.items())[:5]
            ],
            "note": "No exact match; showing common Kickstart tool categories.",
        }
    return {"task": task, "recommendations": matches}


def answer_token_faq(token: str, question: Optional[str] = None) -> dict[str, Any]:
    bundle = _token_bundle(token)
    if bundle.get("error"):
        return bundle
    row = _row(bundle)
    locked = bundle.get("locked_supply") or {}
    summary = bundle.get("summary") or {}
    pct_locked = _locked_percent(locked)
    faq = {
        "listed_on_easy_screener": row.get("is_verified"),
        "liquidity_locked": (
            f"{pct_locked}% locked (Streamflow via EASY Screener)"
            if pct_locked is not None
            else "See locked_supply in EASY Screener response"
        ),
        "documentation": row.get("website"),
        "contact_team": {
            "twitter": row.get("twitter"),
            "telegram": row.get("telegram"),
            "github": row.get("github"),
        },
        "ai_diligence_summary": summary,
        "explorer": f"https://solscan.io/token/{row.get('mint')}",
    }
    return {
        "symbol": row.get("symbol"),
        "mint": row.get("mint"),
        "question": question,
        "faq": faq,
        "attribution": ATTRIBUTION,
    }


def add_to_watchlist(token: str, user_wallet: str) -> dict[str, Any]:
    tok = _resolve_screener_token(token)
    if tok.get("error"):
        return tok
    return add_watchlist_token(
        user_wallet,
        tok["mint"],
        tok.get("symbol"),
        tok.get("name"),
    )


def remove_from_watchlist(token: str, user_wallet: str) -> dict[str, Any]:
    tok = _resolve_screener_token(token)
    if tok.get("error"):
        return tok
    return remove_watchlist_token(user_wallet, tok["mint"])


def get_watchlist(user_wallet: str) -> dict[str, Any]:
    return list_watchlist(user_wallet)


def compare_watchlist(user_wallet: str) -> dict[str, Any]:
    items = compare_watchlist_tokens(user_wallet)
    if items.get("error"):
        return items
    tokens = [row.get("mint") or row.get("symbol") for row in items.get("watchlist", [])]
    if len(tokens) < 2:
        return {"error": "Add at least two tokens to your watchlist to compare.", "watchlist": items}
    return compare_tokens(tokens)


def get_easya_trading_wallet(user_wallet: str = "") -> dict[str, Any]:
    from easya_trading_ledger import get_easya_agent_wallet_info, get_easya_user_balances

    info = get_easya_agent_wallet_info()
    if user_wallet and user_wallet.strip():
        info["balances"] = get_easya_user_balances(user_wallet.strip()).get("balances", [])
    return info


def get_easya_trading_balance(user_wallet: str) -> dict[str, Any]:
    from easya_trading_ledger import get_easya_user_balances

    return get_easya_user_balances(user_wallet)


def place_market_buy(user_wallet: str, token: str, amount_sol: float, slippage_bps: int = 100) -> dict[str, Any]:
    from easya_trading import place_market_buy_order

    return place_market_buy_order(user_wallet, token, float(amount_sol), int(slippage_bps))


def place_limit_buy(
    user_wallet: str,
    token: str,
    amount_sol: float,
    limit_price_usd: Optional[float] = None,
    limit_market_cap_usd: Optional[float] = None,
    condition_mode: Optional[str] = None,
    slippage_bps: int = 100,
) -> dict[str, Any]:
    from easya_trading import place_limit_buy_order

    return place_limit_buy_order(
        user_wallet,
        token,
        float(amount_sol),
        limit_price_usd=limit_price_usd,
        limit_market_cap_usd=limit_market_cap_usd,
        condition_mode=condition_mode,
        slippage_bps=int(slippage_bps),
    )


def place_threshold_buy(
    user_wallet: str,
    token: str,
    amount_sol: float,
    limit_price_usd: Optional[float] = None,
    limit_market_cap_usd: Optional[float] = None,
    stop_price_usd: Optional[float] = None,
    stop_market_cap_usd: Optional[float] = None,
    condition_mode: Optional[str] = None,
    slippage_bps: int = 100,
    max_executions: Optional[int] = None,
    check_interval_seconds: Optional[int] = None,
) -> dict[str, Any]:
    from easya_trading import place_threshold_buy_order

    return place_threshold_buy_order(
        user_wallet,
        token,
        float(amount_sol),
        limit_price_usd=limit_price_usd,
        limit_market_cap_usd=limit_market_cap_usd,
        stop_price_usd=stop_price_usd,
        stop_market_cap_usd=stop_market_cap_usd,
        condition_mode=condition_mode,
        slippage_bps=int(slippage_bps),
        max_executions=max_executions,
        check_interval_seconds=check_interval_seconds,
    )


def list_trading_orders(user_wallet: str, active_only: bool = False) -> dict[str, Any]:
    from easya_trading import list_easya_orders

    return list_easya_orders(user_wallet, active_only=active_only)


def cancel_trading_order(user_wallet: str, order_id: str) -> dict[str, Any]:
    from easya_trading import cancel_easya_order

    return cancel_easya_order(user_wallet, order_id)


TOOLS = [
    {"type": "function", "function": {"name": "list_verified_kickstart_tokens", "description": "List tokens from EASY Screener (verified Kickstart sample or search by query).", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "category": {"type": "string"}, "tag": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {"name": "search_tokens", "description": "Search EASY Screener for tokens by name, symbol, or keyword.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}, "verified_only": {"type": "boolean"}, "tag": {"type": "string"}, "category": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "get_token_overview", "description": "Full verified token summary.", "parameters": {"type": "object", "properties": {"token": {"type": "string"}}, "required": ["token"]}}},
    {"type": "function", "function": {"name": "get_token_analytics", "description": "Live price, mcap, liquidity, volume, holders, buy/sell ratio.", "parameters": {"type": "object", "properties": {"token": {"type": "string"}}, "required": ["token"]}}},
    {"type": "function", "function": {"name": "get_top_token_holders", "description": "Top wallet holders by on-chain balance (Solana RPC). Never invent holder lists.", "parameters": {"type": "object", "properties": {"token": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["token"]}}},
    {"type": "function", "function": {"name": "get_token_performance", "description": "Historical performance over N days.", "parameters": {"type": "object", "properties": {"token": {"type": "string"}, "days": {"type": "integer"}}, "required": ["token"]}}},
    {"type": "function", "function": {"name": "analyze_token_health", "description": "Strengths, weaknesses, and health score /100.", "parameters": {"type": "object", "properties": {"token": {"type": "string"}}, "required": ["token"]}}},
    {"type": "function", "function": {"name": "get_improvement_suggestions", "description": "Actionable recommendations for a token project.", "parameters": {"type": "object", "properties": {"token": {"type": "string"}}, "required": ["token"]}}},
    {"type": "function", "function": {"name": "detect_token_risks", "description": "Flag whale concentration, mint authority, liquidity risks, etc.", "parameters": {"type": "object", "properties": {"token": {"type": "string"}}, "required": ["token"]}}},
    {"type": "function", "function": {"name": "compare_tokens", "description": "Side-by-side comparison of 2-5 tokens.", "parameters": {"type": "object", "properties": {"tokens": {"type": "array", "items": {"type": "string"}}}, "required": ["tokens"]}}},
    {"type": "function", "function": {"name": "get_operation_guide", "description": "Explain token ops: burn, lock liquidity, vesting, etc.", "parameters": {"type": "object", "properties": {"operation": {"type": "string"}}, "required": ["operation"]}}},
    {"type": "function", "function": {"name": "recommend_tools", "description": "Recommend tools for a task.", "parameters": {"type": "object", "properties": {"task": {"type": "string"}}, "required": ["task"]}}},
    {"type": "function", "function": {"name": "answer_token_faq", "description": "Answer common FAQ for a token.", "parameters": {"type": "object", "properties": {"token": {"type": "string"}, "question": {"type": "string"}}, "required": ["token"]}}},
    {"type": "function", "function": {"name": "add_to_watchlist", "description": "Add token to user watchlist.", "parameters": {"type": "object", "properties": {"token": {"type": "string"}, "user_wallet": {"type": "string"}}, "required": ["token"]}}},
    {"type": "function", "function": {"name": "remove_from_watchlist", "description": "Remove token from watchlist.", "parameters": {"type": "object", "properties": {"token": {"type": "string"}, "user_wallet": {"type": "string"}}, "required": ["token"]}}},
    {"type": "function", "function": {"name": "get_watchlist", "description": "List user watchlist tokens.", "parameters": {"type": "object", "properties": {"user_wallet": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {"name": "compare_watchlist", "description": "Compare all tokens on user watchlist.", "parameters": {"type": "object", "properties": {"user_wallet": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {"name": "get_easya_trading_wallet", "description": "Deposit address and SOL balance for Jupiter trading (0.1% fee per fill).", "parameters": {"type": "object", "properties": {"user_wallet": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {"name": "get_easya_trading_balance", "description": "User SOL balance deposited for EasyA trading.", "parameters": {"type": "object", "properties": {"user_wallet": {"type": "string"}}, "required": []}}},
    {"type": "function", "function": {"name": "place_market_buy", "description": "Market buy token with deposited SOL via Jupiter (one-time, 0.1% fee). REQUIRES explicit user confirmation in their latest message before calling.", "parameters": {"type": "object", "properties": {"user_wallet": {"type": "string"}, "token": {"type": "string"}, "amount_sol": {"type": "number"}, "slippage_bps": {"type": "integer"}}, "required": ["token", "amount_sol"]}}},
    {"type": "function", "function": {"name": "place_limit_buy", "description": "One-time buy when custom conditions met. Use limit_price_usd for TOKEN PRICE (e.g. $0.02), limit_market_cap_usd for MARKET CAP (e.g. 46000). Set one or both (condition_mode: price|market_cap|both). REQUIRES confirmation.", "parameters": {"type": "object", "properties": {"user_wallet": {"type": "string"}, "token": {"type": "string"}, "amount_sol": {"type": "number"}, "limit_price_usd": {"type": "number"}, "limit_market_cap_usd": {"type": "number"}, "condition_mode": {"type": "string"}, "slippage_bps": {"type": "integer"}}, "required": ["token", "amount_sol"]}}},
    {"type": "function", "function": {"name": "place_threshold_buy", "description": "Recurring threshold buy. Use limit_market_cap_usd for market cap triggers (NOT limit_price_usd). Optional stop_market_cap_usd/stop_price_usd to end when metric rises above threshold. check_interval_seconds min 60 (use 60 for every minute). Continues until SOL runs out. REQUIRES confirmation.", "parameters": {"type": "object", "properties": {"user_wallet": {"type": "string"}, "token": {"type": "string"}, "amount_sol": {"type": "number"}, "limit_price_usd": {"type": "number"}, "limit_market_cap_usd": {"type": "number"}, "stop_price_usd": {"type": "number"}, "stop_market_cap_usd": {"type": "number"}, "condition_mode": {"type": "string"}, "slippage_bps": {"type": "integer"}, "max_executions": {"type": "integer"}, "check_interval_seconds": {"type": "integer"}}, "required": ["token", "amount_sol"]}}},
    {"type": "function", "function": {"name": "list_trading_orders", "description": "List user's market/limit buy orders.", "parameters": {"type": "object", "properties": {"user_wallet": {"type": "string"}, "active_only": {"type": "boolean"}}, "required": []}}},
    {"type": "function", "function": {"name": "cancel_trading_order", "description": "Cancel a pending/active limit order. REQUIRES explicit user confirmation before calling.", "parameters": {"type": "object", "properties": {"user_wallet": {"type": "string"}, "order_id": {"type": "string"}}, "required": ["order_id"]}}},
]

TOOL_MAP = {
    "list_verified_kickstart_tokens": list_verified_kickstart_tokens,
    "search_tokens": search_tokens,
    "get_token_overview": get_token_overview,
    "get_token_analytics": get_token_analytics,
    "get_top_token_holders": get_top_token_holders,
    "get_token_performance": get_token_performance,
    "analyze_token_health": analyze_token_health,
    "get_improvement_suggestions": get_improvement_suggestions,
    "detect_token_risks": detect_token_risks,
    "compare_tokens": compare_tokens,
    "get_operation_guide": get_operation_guide,
    "recommend_tools": recommend_tools,
    "answer_token_faq": answer_token_faq,
    "add_to_watchlist": add_to_watchlist,
    "remove_from_watchlist": remove_from_watchlist,
    "get_watchlist": get_watchlist,
    "compare_watchlist": compare_watchlist,
    "get_easya_trading_wallet": get_easya_trading_wallet,
    "get_easya_trading_balance": get_easya_trading_balance,
    "place_market_buy": place_market_buy,
    "place_limit_buy": place_limit_buy,
    "place_threshold_buy": place_threshold_buy,
    "list_trading_orders": list_trading_orders,
    "cancel_trading_order": cancel_trading_order,
}

WALLET_SCOPED = {
    "add_to_watchlist",
    "remove_from_watchlist",
    "get_watchlist",
    "compare_watchlist",
    "get_easya_trading_wallet",
    "get_easya_trading_balance",
    "place_market_buy",
    "place_limit_buy",
    "place_threshold_buy",
    "list_trading_orders",
    "cancel_trading_order",
}

SYSTEM_PROMPT = """You are **EasyA Analysis Agent** on Solana - free token research powered by **EASY Screener**.

## Data source
- All token data from **EASY Screener** (easyscreener.xyz) - lookup by symbol, mint, or search.
- Token bundles are cached server-side for 1 hour per mint - reuse tool results within a conversation.
- **Attribute EASY Screener** when publishing derived market analysis.
- Numeric nulls mean missing upstream data - never treat null as zero.

## Pricing
- **Analysis:** free for authenticated users (wallet sign-in required).
- **Trading:** deposit SOL to the EasyA Analysis Agent wallet; market/limit buys via Jupiter.
- **Platform fee:** 0.1% on each successful buy (swap amount + fee debited from deposit).

## Trading (Jupiter)
- Users must deposit SOL first (`get_easya_trading_wallet` shows the address).
- **Market buy:** `place_market_buy(token, amount_sol)` — executes immediately (one-time).
- **Limit buy (one-time):** `place_limit_buy(token, amount_sol, limit_price_usd?, limit_market_cap_usd?)` — fills once when conditions met.
- **Threshold buy (recurring):** `place_threshold_buy(...)` — repeats while conditions hold. Use **limit_market_cap_usd** for market cap (e.g. 46000), **limit_price_usd** for token price (e.g. 0.02). Never put market cap in limit_price_usd.
- **Stop conditions:** `stop_market_cap_usd` / `stop_price_usd` end the order when metric rises above that level (e.g. stop_market_cap_usd=46000 when user says stop if mcap goes above 46000).
- **Check interval:** `check_interval_seconds` (min 60). Use 60 when user says every minute; default 900 (15 min).
- **Both conditions:** set limit_price_usd AND limit_market_cap_usd with condition_mode `both` (buy only when price AND market cap triggers pass).
- Use `list_trading_orders` / `cancel_trading_order` for active orders. Orders show execution counts like DCA plans.
- **Confirmation required:** before `place_market_buy`, `place_limit_buy`, `place_threshold_buy`, or `cancel_trading_order`, summarize the order (from/to tokens, SOL per buy, limit/trigger, executions, check interval, 0.1% fee) and ask the user to confirm.
- Always confirm deposit balance before placing orders. Never invent tx signatures.

## Order confirmation flow
Mutating trading actions **cannot run** until the user explicitly confirms in their **latest message** (e.g. "yes", "confirm", "proceed").
When proposing a limit or market buy, say:
"Please confirm before I proceed: [exact order details including SOL → token, amount, limit/trigger, **1 execution**, 0.1% fee]. Reply **yes** to proceed or **no** to cancel."
If the tool returns `confirmation_required`, show that message and wait — do not retry in the same turn.

## Scope
- Analyze any token indexed on EASY Screener (use get_token_overview, search_tokens, or list_verified_kickstart_tokens).
- If a token is NOT_FOUND, use search_tokens to find the correct ticker or ask the user for the mint address.
- Do not invent data for tokens not on EASY Screener.

## Capabilities
- Discovery (list_verified_kickstart_tokens, search_tokens)
- Overview, analytics, performance, health, risks, improvements, FAQ
- Operations guidance & tool recommendations
- Watchlist helpers

## Rules
- **Always call tools** - never invent prices, holder counts, or trust scores.
- After tool results, write a **detailed human-readable analysis** (headings, bullets, numbers). Never reply with only the disclaimer.
- Summarize trends in plain language.
- End with: "Not financial advice. DYOR."
""" + GOVERNANCE_PROMPT

DISCLAIMER = "Not financial advice. DYOR."
OVERVIEW_INTENT_RE = re.compile(
    r"\b(overview|summarize|summary|tell me about|what is|what's|give me an overview of)\b",
    re.I,
)
HEALTH_INTENT_RE = re.compile(
    r"\b(health|health score|risk profile|token health|how healthy)\b",
    re.I,
)
TOP_HOLDERS_INTENT_RE = re.compile(
    r"\b(top\s*\d*\s*holders?|who\s+are\s+the\s+(?:top\s+)?holders?|holder\s+breakdown|largest\s+holders?|biggest\s+holders?)\b",
    re.I,
)
ANALYZE_INTENT_RE = re.compile(r"\b(analyze|analyse|check|review|assess)\b", re.I)


def _fmt_usd(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if amount >= 1_000_000:
        return f"${amount:,.0f}"
    if amount >= 1:
        return f"${amount:,.2f}"
    return f"${amount:.8g}"


def _fmt_pct(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):+.2f}%"
    except (TypeError, ValueError):
        return "n/a"


def _format_token_overview_reply(data: dict[str, Any]) -> str:
    if data.get("error"):
        return str(data["error"])

    lines = [
        f"**{data.get('name')} ({data.get('symbol')})**",
        "",
        (data.get("description") or "No project description available.").strip(),
        "",
        "**Market snapshot**",
        f"- Price: {_fmt_usd(data.get('price_usd'))}",
        f"- Market cap: {_fmt_usd(data.get('market_cap_usd'))}",
        f"- Liquidity: {_fmt_usd(data.get('liquidity_usd'))}",
        f"- 24h volume: {_fmt_usd(data.get('volume_24h_usd'))}",
        f"- Holders: {data.get('holder_count') if data.get('holder_count') is not None else 'n/a'}",
        f"- DEX: {data.get('dex') or 'n/a'}",
        f"- Mint: `{data.get('mint')}`",
    ]

    launch = data.get("launch_date") or data.get("created_at")
    if launch:
        lines.append(f"- Launch: {launch}")

    links = data.get("links") or {}
    link_bits = []
    for key, label in (("website", "Website"), ("twitter", "Twitter"), ("telegram", "Telegram")):
        if links.get(key):
            link_bits.append(f"{label}: {links[key]}")
    if link_bits:
        lines.extend(["", "**Links**", *[f"- {bit}" for bit in link_bits]])

    locked = data.get("locked_supply") or {}
    pct = _locked_percent(locked)
    if pct is not None:
        lines.extend(["", f"**Locked supply:** {pct:.1f}% (Streamflow via EASY Screener)"])

    summary = data.get("ai_summary") or {}
    if isinstance(summary, dict) and summary:
        trust = summary.get("trustScore") or summary.get("githubTrustScore")
        if trust is not None:
            lines.extend(["", f"**EASY Screener trust score:** {trust}/100"])

    lines.extend(["", "_Live market data from EASY Screener (easyscreener.xyz)._", "", DISCLAIMER])
    return "\n".join(lines)


def _extract_token_query(user_input: str) -> Optional[str]:
    patterns = [
        r"\b(?:of|for|about)\s+\$?([A-Za-z][A-Za-z0-9]{1,24})\b",
        r"\b(?:analyze|analyse|check|review|assess)\s+\$?([A-Za-z][A-Za-z0-9]{1,24})\b",
        r"\b(?:analyze|analyse|check|review|assess)\s+\$?([A-Za-z][A-Za-z0-9]{1,24})\s+token\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, user_input, re.I)
        if match:
            return match.group(1).upper()

    tickers = re.findall(r"\$([A-Za-z][A-Za-z0-9]{1,20})\b", user_input)
    if tickers:
        return tickers[-1].upper()
    return None


def _extract_token_from_context(
    user_input: str,
    conversation_history: Optional[list] = None,
) -> Optional[str]:
    token = _extract_token_query(user_input)
    if token:
        return token
    for msg in reversed(conversation_history or []):
        content = str(msg.get("content") or "")
        mint_match = re.search(r"Mint:\s*`([1-9A-HJ-NP-Za-km-z]{32,44})`", content)
        if mint_match:
            return mint_match.group(1)
        sym_match = re.search(r"\(([A-Za-z][A-Za-z0-9]{1,24})\)", content)
        if sym_match:
            return sym_match.group(1).upper()
        sym_match = re.search(r"\*\*([A-Za-z][A-Za-z0-9]+)\s*\(", content)
        if sym_match:
            return sym_match.group(1).upper()
    return None


def _format_top_holders_reply(data: dict[str, Any]) -> str:
    if data.get("error"):
        return str(data["error"])

    lines = [
        f"**Top holders — {data.get('symbol')}**",
        f"Mint: `{data.get('mint')}`",
    ]
    if data.get("holder_count_screener") is not None:
        lines.append(f"Total holders (EASY Screener): **{data['holder_count_screener']}**")
    lines.append("")

    for row in data.get("top_holders") or []:
        wallet = row.get("wallet") or row.get("token_account") or "unknown"
        amount = row.get("amount")
        pct = row.get("percent_of_supply")
        pct_label = f" ({pct}%)" if pct is not None else ""
        lines.append(f"{row.get('rank')}. `{wallet}` — {amount:,.4f} tokens{pct_label}")

    lines.extend([
        "",
        "_On-chain balances via Solana RPC (`getTokenLargestAccounts`)._",
        "",
        DISCLAIMER,
    ])
    return "\n".join(lines)


def _try_top_holders_shortcut(
    user_input: str,
    conversation_history: Optional[list] = None,
) -> Optional[tuple[str, list[dict[str, Any]]]]:
    if not TOP_HOLDERS_INTENT_RE.search(user_input):
        return None
    token = _extract_token_from_context(user_input, conversation_history)
    if not token:
        return None
    limit_match = re.search(r"\btop\s+(\d+)\s+holders?\b", user_input, re.I)
    limit = int(limit_match.group(1)) if limit_match else 10
    result = get_top_token_holders(token, limit=limit)
    reply = _format_top_holders_reply(result)
    actions = [{
        "tool": "get_top_token_holders",
        "args": {"token": token, "limit": limit},
        "result": json.dumps(result, indent=2),
    }]
    return reply, actions


def _format_health_reply(data: dict[str, Any]) -> str:
    if data.get("error"):
        return str(data["error"])

    lines = [
        f"**{data.get('symbol')} token health: {data.get('overall_health_score')}/100**",
        "",
        "**Strengths**",
        *[f"- {s}" for s in (data.get("strengths") or [])],
        "",
        "**Weaknesses**",
        *[f"- {w}" for w in (data.get("weaknesses") or [])],
    ]

    risks = data.get("risks") or []
    if risks:
        lines.extend(["", "**Risks flagged**"])
        for risk in risks:
            lines.append(f"- ({risk.get('severity', 'info')}) {risk.get('title')}: {risk.get('detail')}")

    snapshot = data.get("analytics_snapshot") or {}
    if snapshot:
        lines.extend([
            "",
            "**Market context**",
            f"- Price: {_fmt_usd(snapshot.get('price_usd'))}",
            f"- Market cap: {_fmt_usd(snapshot.get('market_cap_usd'))}",
            f"- Liquidity: {_fmt_usd(snapshot.get('liquidity_usd'))}",
            f"- 24h volume: {_fmt_usd(snapshot.get('volume_24h_usd'))}",
            f"- Holders: {snapshot.get('holder_count') if snapshot.get('holder_count') is not None else 'n/a'}",
            f"- 24h change: {_fmt_pct(snapshot.get('price_change_24h_pct'))}",
        ])

    if data.get("summary_unavailable"):
        lines.extend(["", f"_Note: {data['summary_unavailable']}_"])

    lines.extend(["", "_Analysis uses EASY Screener market + lock data (easyscreener.xyz)._", "", DISCLAIMER])
    return "\n".join(lines)


def _is_weak_reply(reply: str) -> bool:
    text = (reply or "").strip()
    if not text:
        return True
    without = re.sub(r"not financial advice\.?\s*dyor\.?", "", text, flags=re.I).strip()
    return len(without) < 50


def _synthesize_reply_from_actions(actions: list[dict[str, Any]]) -> Optional[str]:
    if not actions:
        return None
    last = actions[-1]
    tool = last.get("tool")
    try:
        data = json.loads(last.get("result") or "{}")
    except json.JSONDecodeError:
        return None
    if tool == "get_token_overview":
        return _format_token_overview_reply(data)
    if tool == "analyze_token_health" and not data.get("error"):
        return _format_health_reply(data)
    if tool == "get_token_analytics" and not data.get("error"):
        lines = [
            f"**{data.get('symbol')} live analytics**",
            "",
            f"- Price: {_fmt_usd(data.get('price_usd'))}",
            f"- Market cap: {_fmt_usd(data.get('market_cap_usd'))}",
            f"- Liquidity: {_fmt_usd(data.get('liquidity_usd'))}",
            f"- 24h volume: {_fmt_usd(data.get('volume_24h_usd'))}",
            f"- Holders: {data.get('holder_count') if data.get('holder_count') is not None else 'n/a'}",
            f"- 24h change: {_fmt_pct(data.get('price_change_24h_pct'))}",
            "",
            "_Live market data from EASY Screener (easyscreener.xyz)._",
            "",
            DISCLAIMER,
        ]
        return "\n".join(lines)
    return None


def _try_health_shortcut(user_input: str) -> Optional[tuple[str, list[dict[str, Any]]]]:
    if not HEALTH_INTENT_RE.search(user_input) and not (
        ANALYZE_INTENT_RE.search(user_input) and "health" in user_input.lower()
    ):
        return None
    token = _extract_token_query(user_input)
    if not token:
        return None
    result = analyze_token_health(token)
    reply = _format_health_reply(result)
    actions = [{
        "tool": "analyze_token_health",
        "args": {"token": token},
        "result": json.dumps(result, indent=2),
    }]
    return reply, actions


def _try_overview_shortcut(user_input: str) -> Optional[tuple[str, list[dict[str, Any]]]]:
    if not OVERVIEW_INTENT_RE.search(user_input):
        return None
    token = _extract_token_query(user_input)
    if not token:
        return None
    result = get_token_overview(token)
    reply = _format_token_overview_reply(result)
    actions = [{
        "tool": "get_token_overview",
        "args": {"token": token},
        "result": json.dumps(result, indent=2),
    }]
    return reply, actions


def build_system_prompt() -> str:
    return SYSTEM_PROMPT + "\n\n" + get_allowlist_prompt_block()


CONFIRMATION_REQUIRED_TOOLS = frozenset({
    "place_market_buy",
    "place_limit_buy",
    "place_threshold_buy",
    "cancel_trading_order",
})

_CONFIRMATION_LOCK = threading.Lock()
_pending_confirmations: dict[str, dict[str, Any]] = {}

_CONFIRM_PHRASES = (
    r"\byes\b",
    r"\byep\b",
    r"\byeah\b",
    r"\bconfirm\b",
    r"\bproceed\b",
    r"\bgo ahead\b",
    r"\bdo it\b",
    r"\bapproved?\b",
    r"\bsure\b",
    r"\bok(?:ay)?\b",
    r"\bi confirm\b",
    r"\bplease proceed\b",
    r"\bthat(?:'s| is) correct\b",
    r"\blooks good\b",
)

_DECLINE_PHRASES = (
    r"\bno\b",
    r"\bcancel\b",
    r"\bstop\b",
    r"\babort\b",
    r"\bdon't\b",
    r"\bdont\b",
    r"\bnevermind\b",
    r"\bnever mind\b",
)


def _confirmation_key(user_wallet: Optional[str], session_id: Optional[str]) -> str:
    wallet = (user_wallet or "").strip() or "anonymous"
    session = (session_id or "").strip() or "default"
    return f"{wallet}:{session}"


def _user_confirmed(user_input: Optional[str]) -> bool:
    text = (user_input or "").strip().lower()
    if not text:
        return False
    return any(re.search(pattern, text) for pattern in _CONFIRM_PHRASES)


def _user_declined(user_input: Optional[str]) -> bool:
    text = (user_input or "").strip().lower()
    if not text:
        return False
    return any(re.search(pattern, text) for pattern in _DECLINE_PHRASES)


def _resolve_trading_token(token: str) -> dict[str, Any]:
    from easya_trading import resolve_output_token

    resolved = resolve_output_token(token)
    if "error" in resolved:
        return {"symbol": str(token).strip().upper(), "mint": None}
    return {"symbol": resolved.get("symbol"), "mint": resolved.get("mint")}


def _token_with_mint(symbol: Optional[str], mint: Optional[str]) -> str:
    if symbol and mint:
        return f"**{symbol}** (`{mint}`)"
    if symbol:
        return f"**{symbol}**"
    return "**?**"


def _float_arg(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_check_interval(seconds: int) -> str:
    if seconds < 60:
        return f"every **{seconds}s**"
    if seconds % 60 == 0:
        mins = seconds // 60
        return f"every **{mins} min**" if mins > 1 else "every **1 min**"
    return f"every **{seconds}s**"


def _build_trigger_preview(out: dict[str, Any], args: dict) -> dict[str, Any]:
    from easya_trading import (
        MIN_CHECK_INTERVAL_SECONDS,
        THRESHOLD_CHECK_INTERVAL_SECONDS,
        _format_stop_summary,
        _format_trigger_summary,
        _infer_condition_mode,
        _token_metrics,
    )

    limit_price = _float_arg(args.get("limit_price_usd"))
    limit_mcap = _float_arg(args.get("limit_market_cap_usd"))
    stop_price = _float_arg(args.get("stop_price_usd"))
    stop_mcap = _float_arg(args.get("stop_market_cap_usd"))
    mode = _infer_condition_mode(
        limit_price_usd=limit_price,
        limit_market_cap_usd=limit_mcap,
        condition_mode=args.get("condition_mode"),
    )
    metrics = _token_metrics(out.get("symbol") or "")
    interval = int(args.get("check_interval_seconds") or THRESHOLD_CHECK_INTERVAL_SECONDS)
    interval = max(MIN_CHECK_INTERVAL_SECONDS, interval)
    preview = {
        "output_token": out.get("symbol"),
        "limit_price_usd": limit_price,
        "limit_market_cap_usd": limit_mcap,
        "stop_price_usd": stop_price,
        "stop_market_cap_usd": stop_mcap,
        "condition_mode": mode,
    }
    return {
        "limit_price_usd": limit_price,
        "limit_market_cap_usd": limit_mcap,
        "stop_price_usd": stop_price,
        "stop_market_cap_usd": stop_mcap,
        "condition_mode": mode,
        "current_price_usd": metrics.get("price_usd"),
        "current_market_cap_usd": metrics.get("market_cap_usd"),
        "trigger_condition": _format_trigger_summary(preview),
        "stop_condition": _format_stop_summary(preview),
        "check_interval_seconds": interval,
        "check_interval_minutes": interval / 60,
    }


def _pending_action_details(tool_name: str, args: dict) -> dict[str, Any]:
    from easya_trading_ledger import easya_execution_total_cost, easya_platform_fee

    if tool_name == "place_limit_buy":
        out = _resolve_trading_token(str(args.get("token") or ""))
        amount = float(args.get("amount_sol") or 0)
        preview = _build_trigger_preview(out, args)
        fee = easya_platform_fee(amount) if amount > 0 else 0
        return {
            "action": tool_name,
            "order_type": "limit",
            "input_token": "SOL",
            "output_token": out.get("symbol"),
            "output_mint": out.get("mint"),
            "amount_sol": amount,
            **preview,
            "executions": 1,
            "max_executions": 1,
            "slippage_bps": args.get("slippage_bps", 100),
            "platform_fee": fee,
            "total_cost": easya_execution_total_cost(amount) if amount > 0 else None,
            "fee_rate": 0.001,
        }

    if tool_name == "place_threshold_buy":
        out = _resolve_trading_token(str(args.get("token") or ""))
        amount = float(args.get("amount_sol") or 0)
        max_exec = args.get("max_executions")
        preview = _build_trigger_preview(out, args)
        fee = easya_platform_fee(amount) if amount > 0 else 0
        return {
            "action": tool_name,
            "order_type": "threshold",
            "input_token": "SOL",
            "output_token": out.get("symbol"),
            "output_mint": out.get("mint"),
            "amount_sol": amount,
            **preview,
            "executions": None,
            "max_executions": int(max_exec) if max_exec is not None else None,
            "until_balance_depleted": max_exec is None,
            "slippage_bps": args.get("slippage_bps", 100),
            "platform_fee": fee,
            "total_cost_per_buy": easya_execution_total_cost(amount) if amount > 0 else None,
            "fee_rate": 0.001,
        }

    if tool_name == "place_market_buy":
        out = _resolve_trading_token(str(args.get("token") or ""))
        amount = float(args.get("amount_sol") or 0)
        fee = easya_platform_fee(amount) if amount > 0 else 0
        return {
            "action": tool_name,
            "order_type": "market",
            "input_token": "SOL",
            "output_token": out.get("symbol"),
            "output_mint": out.get("mint"),
            "amount_sol": amount,
            "trigger_condition": "executes immediately at market price",
            "executions": 1,
            "slippage_bps": args.get("slippage_bps", 100),
            "platform_fee": fee,
            "total_cost": easya_execution_total_cost(amount) if amount > 0 else None,
            "fee_rate": 0.001,
        }

    if tool_name == "cancel_trading_order":
        return {
            "action": tool_name,
            "order_id": args.get("order_id"),
            "order_type": "cancel",
        }

    return {"action": tool_name, "args": args}


def _summarize_pending_action(tool_name: str, args: dict) -> str:
    if tool_name == "place_limit_buy":
        out = _resolve_trading_token(str(args.get("token") or ""))
        preview = _build_trigger_preview(out, args)
        return (
            f"Place **one-time limit buy**: spend **{args.get('amount_sol')} SOL** "
            f"→ {_token_with_mint(out.get('symbol'), out.get('mint'))} "
            f"when {preview['trigger_condition'].replace('Buy when ', '')} "
            f"(**1 execution**, 0.1% platform fee)"
        )

    if tool_name == "place_threshold_buy":
        out = _resolve_trading_token(str(args.get("token") or ""))
        preview = _build_trigger_preview(out, args)
        max_label = (
            f"max **{args.get('max_executions')}** buys"
            if args.get("max_executions") is not None
            else "until **SOL runs out**"
        )
        interval_label = _format_check_interval(int(preview["check_interval_seconds"]))
        stop_note = ""
        if preview.get("stop_condition") and "Stop when" in preview["stop_condition"]:
            stop_note = f", stops when {preview['stop_condition'].replace('Stop when ', '')}"
        return (
            f"Place **threshold buy**: spend **{args.get('amount_sol')} SOL** "
            f"→ {_token_with_mint(out.get('symbol'), out.get('mint'))} "
            f"each time {preview['trigger_condition'].replace('Buy when ', '')} "
            f"(checks {interval_label}, {max_label}{stop_note}, 0.1% fee per buy)"
        )

    if tool_name == "place_market_buy":
        out = _resolve_trading_token(str(args.get("token") or ""))
        return (
            f"Place **market buy**: spend **{args.get('amount_sol')} SOL** "
            f"→ {_token_with_mint(out.get('symbol'), out.get('mint'))} "
            f"immediately (**1 execution**, 0.1% platform fee)"
        )

    if tool_name == "cancel_trading_order":
        return f"**Cancel** limit order `{args.get('order_id')}`"

    return f"{tool_name}({args})"


def _action_fingerprint(tool_name: str, args: dict) -> str:
    payload = json.dumps({"tool": tool_name, "args": args}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _merge_tool_args(stored: dict, current: dict) -> dict:
    merged = dict(stored or {})
    for key, value in (current or {}).items():
        if key == "user_wallet":
            continue
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if key not in merged or merged[key] is None:
            merged[key] = value
    return merged


def _check_action_confirmation(
    tool_name: str,
    args: dict,
    user_input: Optional[str],
    user_wallet: Optional[str],
    session_id: Optional[str],
    skip_confirmation: bool = False,
) -> tuple[Optional[str], dict]:
    if skip_confirmation or tool_name not in CONFIRMATION_REQUIRED_TOOLS:
        return None, args

    key = _confirmation_key(user_wallet, session_id)
    summary = _summarize_pending_action(tool_name, args)

    if _user_declined(user_input):
        with _CONFIRMATION_LOCK:
            pending = _pending_confirmations.pop(key, None)
        if pending:
            return json.dumps(
                {
                    "status": "cancelled",
                    "message": "Order cancelled. No changes were made.",
                    "cancelled_action": pending.get("summary") or summary,
                },
                indent=2,
            ), args

    if _user_confirmed(user_input):
        with _CONFIRMATION_LOCK:
            pending = _pending_confirmations.pop(key, None)
        if pending and pending.get("tool") == tool_name:
            args = _merge_tool_args(pending.get("args") or {}, args)
        return None, args

    with _CONFIRMATION_LOCK:
        _pending_confirmations[key] = {
            "tool": tool_name,
            "args": args,
            "summary": summary,
            "details": _pending_action_details(tool_name, args),
        }

    details = _pending_action_details(tool_name, args)
    return json.dumps(
        {
            "status": "confirmation_required",
            "message": (
                f"Please confirm before I proceed: {summary}. "
                "Reply **yes** or **confirm** to proceed, or **no** to cancel."
            ),
            "pending_action": summary,
            "confirmation_details": details,
            "tool": tool_name,
        },
        indent=2,
    ), args


def _try_execute_pending_confirmation(
    user_wallet: Optional[str],
    session_id: Optional[str],
    user_input: Optional[str],
    conversation_history: Optional[list] = None,
) -> Optional[tuple[str, dict, str]]:
    if not user_wallet or not _user_confirmed(user_input) or _user_declined(user_input):
        return None

    key = _confirmation_key(user_wallet, session_id)
    with _CONFIRMATION_LOCK:
        pending = _pending_confirmations.pop(key, None)
    if not pending and conversation_history:
        recovered = _recover_trading_order_from_history(conversation_history)
        if recovered:
            pending = {
                "tool": recovered["tool"],
                "args": {**recovered["args"], "user_wallet": user_wallet.strip()},
            }
    if not pending:
        return None

    tool_name = pending["tool"]
    args = dict(pending.get("args") or {})
    result = execute_tool(
        tool_name,
        args,
        user_wallet=user_wallet,
        user_input=user_input,
        session_id=session_id,
        skip_confirmation=True,
    )
    return tool_name, args, result


def _json_compact(data: Any) -> str:
    return json.dumps(data, separators=(",", ":"), default=str)


def _parse_trading_order_request(user_input: str) -> Optional[dict[str, Any]]:
    """Parse natural-language EasyA buy orders without relying on LLM tool calls."""
    text = (user_input or "").strip()
    lower = text.lower()
    if not text or _user_confirmed(text) or _user_declined(text):
        return None
    if not re.search(r"\b(buy|swap|limit|threshold|market)\b", lower):
        return None

    amount_match = re.search(r"(\d+(?:\.\d+)?)\s*sol\b", lower)
    if not amount_match:
        return None
    amount_sol = float(amount_match.group(1))

    token: Optional[str] = None
    for pattern in (
        r"\b(?:of|into)\s+\$?([A-Za-z][A-Za-z0-9]{1,20})\b",
        r"\bbuy\s+\$?([A-Za-z][A-Za-z0-9]{1,20})\b",
    ):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        candidate = match.group(1).strip()
        if candidate.upper() in {
            "SOL", "TIME", "TIMES", "MARKET", "CAP", "PRICE", "WHEN", "BELOW", "UNDER",
            "EVERY", "MINUTE", "MINUTES", "SECOND", "SECONDS",
        }:
            continue
        token = candidate
        break
    if not token:
        mint_match = re.search(r"[1-9A-HJ-NP-Za-km-z]{32,44}", text)
        if mint_match:
            token = mint_match.group(0)
    if not token:
        return None

    mcap_match = re.search(
        r"market\s*caps?\s*(?:is\s*)?(?:below|under|<=|<|at\s+or\s+below)\s*\$?\s*([\d,]+(?:\.\d+)?)",
        lower,
    )
    price_match = re.search(
        r"(?:token\s+)?price\s*(?:is\s*)?(?:below|under|<=|<|at\s+or\s+below|drops?\s+to|falls?\s+to)\s*\$?\s*([\d.]+)",
        lower,
    )
    if not price_match:
        price_match = re.search(r"\bat\s+\$\s*([\d.]+)\b", lower)

    once = bool(re.search(r"\b(?:once|one[- ]time|1[- ]time|for\s+1\s+times?)\b", lower))
    max_match = re.search(r"(?:for\s+)?(\d+)\s*(?:times?|buys?|executions?)\b", lower)
    max_executions = 1 if once else (int(max_match.group(1)) if max_match else None)

    interval_match = re.search(
        r"every\s+(\d+)\s*(seconds?|secs?|s|minutes?|mins?|m)\b",
        lower,
    )
    check_interval_seconds = None
    if interval_match:
        count = int(interval_match.group(1))
        unit = interval_match.group(2)
        if unit.startswith("m"):
            check_interval_seconds = count * 60
        else:
            check_interval_seconds = count

    wants_market = bool(
        re.search(r"\b(market\s+buy|buy\s+now|immediately|right\s+now)\b", lower)
    ) and not mcap_match and not price_match

    if wants_market:
        return {
            "tool": "place_market_buy",
            "args": {"token": token, "amount_sol": amount_sol},
        }

    if not mcap_match and not price_match:
        return None

    args: dict[str, Any] = {"token": token, "amount_sol": amount_sol}
    if mcap_match:
        args["limit_market_cap_usd"] = float(mcap_match.group(1).replace(",", ""))
        args["condition_mode"] = "market_cap"
    if price_match:
        args["limit_price_usd"] = float(price_match.group(1))
        args["condition_mode"] = "both" if mcap_match else "price"

    recurring = bool(
        max_executions is not None and max_executions > 1
        or check_interval_seconds is not None
        or re.search(r"\b(until|recurring|threshold|keeps?\s+buying)\b", lower)
    )
    if recurring and not once:
        if max_executions is not None:
            args["max_executions"] = max_executions
        if check_interval_seconds is not None:
            args["check_interval_seconds"] = check_interval_seconds
        return {"tool": "place_threshold_buy", "args": args}

    return {"tool": "place_limit_buy", "args": args}


def _recover_trading_order_from_history(conversation_history: list) -> Optional[dict[str, Any]]:
    for msg in reversed(conversation_history or []):
        if msg.get("role") != "user":
            continue
        content = str(msg.get("content") or "")
        if content.startswith("[Connected user wallet:"):
            content = content.split("\n", 1)[-1]
        if content.startswith("[Instruction:"):
            continue
        parsed = _parse_trading_order_request(content)
        if parsed:
            return parsed
    return None


def _try_stage_trading_order_confirmation(
    user_wallet: Optional[str],
    session_id: Optional[str],
    user_input: str,
) -> Optional[str]:
    if not user_wallet or _user_confirmed(user_input) or _user_declined(user_input):
        return None
    parsed = _parse_trading_order_request(user_input)
    if not parsed:
        return None

    tool_name = parsed["tool"]
    args = {**parsed["args"], "user_wallet": user_wallet.strip()}
    key = _confirmation_key(user_wallet, session_id)
    summary = _summarize_pending_action(tool_name, args)
    details = _pending_action_details(tool_name, args)
    with _CONFIRMATION_LOCK:
        _pending_confirmations[key] = {
            "tool": tool_name,
            "args": args,
            "summary": summary,
            "details": details,
        }
    message = (
        f"Please confirm before I proceed: {summary}. "
        "Reply **yes** or **confirm** to proceed, or **no** to cancel."
    )
    return _json_compact(
        {
            "status": "confirmation_required",
            "message": message,
            "pending_action": summary,
            "confirmation_details": details,
            "tool": tool_name,
        }
    )


def _format_trading_tool_reply(tool_name: str, result: str) -> str:
    try:
        data = json.loads(result)
    except json.JSONDecodeError:
        return result

    if data.get("status") == "confirmation_required":
        return str(data.get("message") or result)
    if data.get("status") == "cancelled":
        return str(data.get("message") or "Action cancelled.")
    if data.get("error"):
        return f"Could not complete the action: {data['error']}"

    if tool_name in {"place_limit_buy", "place_threshold_buy", "place_market_buy"}:
        msg = str(data.get("message") or "Order submitted.")
        order_id = data.get("id")
        if order_id:
            msg = f"{msg}\n\nOrder ID: `{order_id}` · status: **{data.get('status', 'active')}**"
        sig = data.get("signature") or (data.get("immediate_fill") or {}).get("signature")
        if sig:
            msg += f"\nOn-chain tx: `{sig}`"
        msg += "\n\nNot financial advice. DYOR."
        return msg

    if tool_name == "cancel_trading_order":
        return str(data.get("message") or f"Order cancelled. Status: {data.get('status')}")

    if tool_name == "list_trading_orders":
        orders = data.get("orders") or data if isinstance(data, list) else []
        if isinstance(data, dict):
            orders = data.get("orders") or []
        if not orders:
            return "You have no EasyA trading orders yet."
        lines = [f"**{len(orders)} trading order(s):**"]
        for order in orders[:20]:
            lines.append(
                f"- `{order.get('id')}` · {order.get('order_type')} · "
                f"{order.get('pair') or order.get('output_token')} · **{order.get('status')}**"
            )
        return "\n".join(lines)

    return data.get("message") or result


def execute_tool(
    tool_name: str,
    tool_args: dict,
    user_wallet: Optional[str] = None,
    user_input: Optional[str] = None,
    session_id: Optional[str] = None,
    skip_confirmation: bool = False,
) -> str:
    func = TOOL_MAP.get(tool_name)
    if not func:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    try:
        args = dict(tool_args or {})
        if tool_name in WALLET_SCOPED:
            if not user_wallet:
                return json.dumps({"error": "Wallet authentication required for watchlist actions."})
            claimed = (args.get("user_wallet") or "").strip()
            if claimed and claimed != user_wallet.strip():
                return json.dumps({"error": "Forbidden: user_wallet does not match authenticated wallet."})
            args["user_wallet"] = user_wallet

        blocked, args = _check_action_confirmation(
            tool_name,
            args,
            user_input=user_input,
            user_wallet=user_wallet,
            session_id=session_id,
            skip_confirmation=skip_confirmation,
        )
        if blocked:
            return blocked

        return json.dumps(func(**args), indent=2)
    except TypeError as exc:
        return json.dumps({"error": str(exc), "received_args": tool_args})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def run_kickstart_agent(
    user_input: str,
    conversation_history: list,
    user_wallet: Optional[str] = None,
    session_id: Optional[str] = None,
) -> tuple[str, list, list[dict[str, Any]]]:
    actions: list[dict[str, Any]] = []
    prompt = user_input.strip()

    pending = _try_execute_pending_confirmation(
        user_wallet, session_id, prompt, conversation_history
    )
    if pending:
        tool_name, args, result = pending
        actions.append({"tool": tool_name, "args": args, "result": result})
        reply = _format_trading_tool_reply(tool_name, result)
        conversation_history.append({"role": "user", "content": prompt})
        conversation_history.append({"role": "assistant", "content": reply})
        return reply, conversation_history, actions

    if user_wallet and not _user_confirmed(prompt) and not _user_declined(prompt):
        staged_payload = _try_stage_trading_order_confirmation(user_wallet, session_id, prompt)
        if staged_payload:
            try:
                staged_data = json.loads(staged_payload)
                staged_reply = str(staged_data.get("message") or staged_payload)
            except json.JSONDecodeError:
                staged_reply = staged_payload
            parsed = _parse_trading_order_request(prompt) or {}
            actions.append({
                "tool": parsed.get("tool") or "place_limit_buy",
                "args": parsed.get("args") or {},
                "result": staged_payload,
            })
            conversation_history.append({"role": "user", "content": prompt})
            conversation_history.append({"role": "assistant", "content": staged_reply})
            return staged_reply, conversation_history, actions

    shortcut = (
        _try_health_shortcut(prompt)
        or _try_overview_shortcut(prompt)
        or _try_top_holders_shortcut(prompt, conversation_history)
    )
    if shortcut:
        reply, actions = shortcut
        conversation_history.append({"role": "user", "content": prompt})
        conversation_history.append({"role": "assistant", "content": reply})
        return reply, conversation_history, actions

    if _user_confirmed(prompt) and not _user_declined(prompt):
        prompt_for_llm = (
            prompt
            + "\n[Instruction: the user confirmed. Call the pending trading tool now "
            "(place_limit_buy / place_threshold_buy / place_market_buy) with the prior parameters. "
            "Do not invent transaction hashes.]"
        )
    else:
        prompt_for_llm = prompt

    if user_wallet:
        prompt_for_llm = f"[Connected user wallet: {user_wallet}]\n{prompt_for_llm}"
    conversation_history.append({"role": "user", "content": prompt_for_llm})
    messages = [{"role": "system", "content": build_system_prompt()}] + conversation_history

    for i in range(12):
        response = call_openrouter(messages)
        message = response.get("message") or {}
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            if _user_confirmed(user_input) and user_wallet:
                recovered = _try_execute_pending_confirmation(
                    user_wallet, session_id, user_input, conversation_history
                )
                if recovered:
                    tool_name, args, result = recovered
                    actions.append({"tool": tool_name, "args": args, "result": result})
                    reply = _format_trading_tool_reply(tool_name, result)
                    conversation_history.append({"role": "assistant", "content": reply})
                    return reply, conversation_history, actions

            reply = (message.get("content") or "").strip()
            # Models invent fake "Transaction Executed" + nonsense hashes without tool_calls.
            if user_wallet and re.search(
                r"\b(transaction executed|transaction hash|tx hash|order (?:placed|created)|signature)\b",
                reply,
                flags=re.IGNORECASE,
            ):
                recovered_order = _recover_trading_order_from_history(conversation_history)
                if recovered_order and _user_confirmed(user_input):
                    result = execute_tool(
                        recovered_order["tool"],
                        {**recovered_order["args"], "user_wallet": user_wallet.strip()},
                        user_wallet=user_wallet,
                        user_input=user_input,
                        session_id=session_id,
                        skip_confirmation=True,
                    )
                    reply = _format_trading_tool_reply(recovered_order["tool"], result)
                    actions.append({
                        "tool": recovered_order["tool"],
                        "args": recovered_order["args"],
                        "result": result,
                    })
                    conversation_history.append({"role": "assistant", "content": reply})
                    return reply, conversation_history, actions
                if recovered_order:
                    staged_payload = _try_stage_trading_order_confirmation(
                        user_wallet,
                        session_id,
                        (
                            f"Buy {recovered_order['args'].get('amount_sol')} SOL of "
                            f"{recovered_order['args'].get('token')}"
                            + (
                                f" when market cap is below "
                                f"${recovered_order['args'].get('limit_market_cap_usd')}"
                                if recovered_order["args"].get("limit_market_cap_usd") is not None
                                else ""
                            )
                            + (
                                f" at ${recovered_order['args'].get('limit_price_usd')}"
                                if recovered_order["args"].get("limit_price_usd") is not None
                                else ""
                            )
                            + " for 1 time"
                        ),
                    )
                    if staged_payload:
                        try:
                            staged_data = json.loads(staged_payload)
                            staged = str(staged_data.get("message") or staged_payload)
                        except json.JSONDecodeError:
                            staged = staged_payload
                        actions.append({
                            "tool": recovered_order["tool"],
                            "args": recovered_order["args"],
                            "result": staged_payload,
                        })
                        conversation_history.append({"role": "assistant", "content": staged})
                        return staged, conversation_history, actions
                reply = (
                    "I could not verify a real trading order (no tool result). "
                    "Please restate the order "
                    "(e.g. \"Buy 0.0001 SOL of BITAGENTS when market cap is below $46000 for 1 time\") "
                    "and confirm with yes."
                )
            elif _is_weak_reply(reply) and actions:
                synthesized = _synthesize_reply_from_actions(actions)
                if synthesized:
                    reply = synthesized
            conversation_history.append({"role": "assistant", "content": reply})
            return reply, conversation_history, actions

        sanitized_tool_calls: list[dict[str, Any]] = []
        parsed_calls: list[tuple[str, dict[str, Any], dict[str, Any]]] = []

        for idx, tc in enumerate(tool_calls):
            fn = tc.get("function") or {}
            name = fn.get("name", "")
            raw_args = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except json.JSONDecodeError:
                args = {}
            if not isinstance(args, dict):
                args = {}
            call_id = tc.get("id") or f"call_{idx}"
            sanitized_tool_calls.append({
                "id": call_id,
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(args, separators=(",", ":")),
                },
            })
            parsed_calls.append((name, args, tc))

        results_this_round: list[tuple[str, dict[str, Any], str]] = []
        for name, args, tc in parsed_calls:
            result = execute_tool(
                name,
                args,
                user_wallet=user_wallet,
                user_input=prompt,
                session_id=session_id,
            )
            actions.append({"tool": name, "args": args, "result": result})
            results_this_round.append((name, args, result))

        # Always format trading/mutating tool results locally (no second LLM turn).
        if any(name in CONFIRMATION_REQUIRED_TOOLS or name == "list_trading_orders" for name, _, _ in results_this_round):
            reply_parts = [
                _format_trading_tool_reply(name, result)
                for name, _, result in results_this_round
            ]
            reply = "\n\n".join(part for part in reply_parts if part)
            conversation_history.append({"role": "assistant", "content": reply})
            return reply, conversation_history, actions

        messages.append({
            "role": "assistant",
            "content": message.get("content") or "",
            "tool_calls": sanitized_tool_calls,
        })
        for (name, _, result), (_, _, tc) in zip(results_this_round, parsed_calls):
            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id", f"call_{i}"),
                "tool_name": name,
                "content": result,
            })

    reply = "I hit the tool loop limit. Please narrow your question and try again."
    conversation_history.append({"role": "assistant", "content": reply})
    return reply, conversation_history, actions
