"""On-chain Solana token research via RPC, Jupiter, and Meteora."""

from __future__ import annotations

import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

from cache_store import cache_backend, cache_stats, clear_prefix, get_json, set_json
from dca_agent import SOLANA_CLUSTER, get_token_price, resolve_token, sol_rpc
from kickstart_copilot_agent import get_top_token_holders
from meteora_dlmm import find_damm_v2_pool, find_dlmm_pool, meteora_pool_app_url

TOKEN_RESEARCH_CACHE_TTL_SECONDS = int(
    os.environ.get("TOKEN_RESEARCH_CACHE_TTL_SECONDS", str(15 * 60))
)

_PROFILE_KEY_PREFIX = "token:profile:"
_ANALYSIS_KEY_PREFIX = "token:analysis:"

RESEARCH_INTENT_RE = re.compile(
    r"\b("
    r"overview|summarize|summary|tell me about|what is|what's|"
    r"research|analysis|token analysis|give me|show me|get|profile|report|"
    r"give me a brief|brief on|look up|lookup|"
    r"analyze|analyse|check|review|assess|vet"
    r")\b",
    re.I,
)

COMPARE_INTENT_RE = re.compile(r"\b(compare|comparison|vs\.?|versus)\b", re.I)

_TOKEN_STOPWORDS = frozenset(
    {
        "ME",
        "MY",
        "THE",
        "THIS",
        "TOKEN",
        "A",
        "AN",
        "FOR",
        "AND",
        "OR",
        "SOL",
        "GIVE",
        "GET",
        "SHOW",
    }
)


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
    if amount >= 0.0001:
        return f"${amount:.6f}"
    return f"${amount:.10g}"


def _fmt_num(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return str(value)
    if amount >= 1_000_000_000:
        return f"{amount:,.0f}"
    if amount >= 1_000_000:
        return f"{amount:,.2f}"
    if amount >= 1:
        return f"{amount:,.4f}"
    return f"{amount:.6f}"


def _cache_key(mint: str, holder_limit: int) -> str:
    return f"{mint.strip()}:{int(holder_limit)}"


def _profile_cache_key(mint: str, holder_limit: int) -> str:
    return f"{_PROFILE_KEY_PREFIX}{_cache_key(mint, holder_limit)}"


def _analysis_cache_key(mint: str, holder_limit: int) -> str:
    return f"{_ANALYSIS_KEY_PREFIX}{_cache_key(mint, holder_limit)}"


def _cache_get(mint: str, holder_limit: int) -> Optional[dict[str, Any]]:
    return get_json(_profile_cache_key(mint, holder_limit))


def _cache_set(mint: str, holder_limit: int, profile: dict[str, Any]) -> None:
    set_json(_profile_cache_key(mint, holder_limit), profile, TOKEN_RESEARCH_CACHE_TTL_SECONDS)


def cache_get_analysis(mint: str, holder_limit: int = 10) -> Optional[str]:
    value = get_json(_analysis_cache_key(mint, holder_limit))
    return value if isinstance(value, str) else None


def cache_set_analysis(mint: str, holder_limit: int, analysis: str) -> None:
    set_json(_analysis_cache_key(mint, holder_limit), analysis, TOKEN_RESEARCH_CACHE_TTL_SECONDS)


def clear_token_research_cache() -> None:
    clear_prefix(_PROFILE_KEY_PREFIX)
    clear_prefix(_ANALYSIS_KEY_PREFIX)


def get_token_research_cache_stats() -> dict[str, Any]:
    stats = cache_stats(_PROFILE_KEY_PREFIX, TOKEN_RESEARCH_CACHE_TTL_SECONDS)
    stats["backend"] = cache_backend()
    return stats


def _best_meteora_pool(mint: str) -> Optional[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for finder in (find_damm_v2_pool, find_dlmm_pool):
        pool = finder(mint)
        if pool:
            candidates.append(pool)
    if not candidates:
        return None
    return max(candidates, key=lambda p: float(p.get("liquidity") or 0))


def _pool_market_snapshot(pool: dict[str, Any]) -> dict[str, Any]:
    raw = pool.get("raw") or {}
    token_x = raw.get("token_x") if isinstance(raw.get("token_x"), dict) else {}
    return {
        "pool_address": pool.get("pool_address"),
        "pool_type": pool.get("pool_type"),
        "name": pool.get("name"),
        "liquidity_usd": pool.get("liquidity"),
        "volume_24h_usd": pool.get("trade_volume_24h"),
        "meteora_url": pool.get("meteora_url") or meteora_pool_app_url(
            str(pool.get("pool_address") or ""), str(pool.get("pool_type") or "dlmm")
        ),
        "price_usd": token_x.get("price"),
        "market_cap_usd": token_x.get("market_cap"),
        "holder_count_indexed": token_x.get("holders"),
        "launchpad": raw.get("launchpad"),
    }


def get_mint_authorities(token: str) -> dict[str, Any]:
    resolved = resolve_token(token)
    if "error" in resolved:
        return resolved
    mint = resolved["mint"]
    info = sol_rpc(
        "getAccountInfo",
        [mint, {"encoding": "jsonParsed", "commitment": "confirmed"}],
    )
    value = (info or {}).get("value")
    if not value:
        return {"error": "Mint account not found on-chain.", "mint": mint}
    parsed = ((value.get("data") or {}).get("parsed") or {}).get("info") or {}
    mint_authority = parsed.get("mintAuthority")
    freeze_authority = parsed.get("freezeAuthority")
    supply = parsed.get("supply")
    decimals = parsed.get("decimals")
    flags: list[str] = []
    if mint_authority:
        flags.append("mint_authority_active")
    else:
        flags.append("mint_authority_renounced")
    if freeze_authority:
        flags.append("freeze_authority_active")
    else:
        flags.append("freeze_authority_renounced")
    return {
        "symbol": resolved.get("symbol"),
        "mint": mint,
        "mint_authority": mint_authority,
        "freeze_authority": freeze_authority,
        "supply": supply,
        "decimals": decimals,
        "flags": flags,
        "cluster": SOLANA_CLUSTER,
        "source": "solana_rpc",
    }


def get_onchain_mint_info(token: str) -> dict[str, Any]:
    resolved = resolve_token(token)
    if "error" in resolved:
        return {**resolved, "query": token, "needs_mint_address": True}
    mint = resolved["mint"]
    supply_resp = sol_rpc("getTokenSupply", [mint, {"commitment": "confirmed"}])
    supply_value = (supply_resp or {}).get("value") or {}
    authorities = get_mint_authorities(token)
    return {
        "symbol": resolved.get("symbol"),
        "name": resolved.get("name"),
        "mint": mint,
        "decimals": resolved.get("decimals") or supply_value.get("decimals"),
        "total_supply": supply_value.get("uiAmount"),
        "total_supply_raw": supply_value.get("amount"),
        "mint_authority": authorities.get("mint_authority"),
        "freeze_authority": authorities.get("freeze_authority"),
        "mint_authority_renounced": not bool(authorities.get("mint_authority")),
        "freeze_authority_renounced": not bool(authorities.get("freeze_authority")),
        "cluster": SOLANA_CLUSTER,
        "source": "solana_rpc",
    }


def _fetch_onchain_token_research(token: str, holder_limit: int = 10) -> dict[str, Any]:
    """Fetch fresh on-chain research (no cache). Parallelizes independent I/O."""
    resolved = resolve_token(token)
    if "error" in resolved:
        return {**resolved, "query": token, "needs_mint_address": True}

    mint = resolved["mint"]

    mint_info: dict[str, Any] = {}
    price: dict[str, Any] = {}
    holders: dict[str, Any] = {}
    pool: Optional[dict[str, Any]] = None
    easya_overlay = None

    def _load_mint_info() -> dict[str, Any]:
        return get_onchain_mint_info(token)

    def _load_price() -> dict[str, Any]:
        return get_token_price(token)

    def _load_holders() -> dict[str, Any]:
        return get_top_token_holders(token, limit=holder_limit)

    def _load_pool() -> Optional[dict[str, Any]]:
        return _best_meteora_pool(mint)

    def _load_easya() -> Optional[dict[str, Any]]:
        try:
            from easya_screener_client import get_token_bundle, screener_configured

            if not screener_configured():
                return None
            bundle = get_token_bundle(token)
            if bundle.get("error"):
                return None
            row = bundle.get("token") or {}
            return {
                "verified": row.get("is_verified"),
                "liquidity_usd": row.get("liquidity_usd"),
                "volume_24h_usd": row.get("volume_24h_usd"),
                "holder_count": row.get("holder_count"),
                "tags": row.get("tags") or [],
                "note": "Supplementary EASY Screener data — prefer on-chain fields above when they conflict.",
            }
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=5) as pool_exec:
        futures = {
            pool_exec.submit(_load_mint_info): "mint_info",
            pool_exec.submit(_load_price): "price",
            pool_exec.submit(_load_holders): "holders",
            pool_exec.submit(_load_pool): "pool",
            pool_exec.submit(_load_easya): "easya",
        }
        for fut in as_completed(futures):
            label = futures[fut]
            try:
                result = fut.result()
            except Exception as exc:
                if label == "mint_info":
                    return {"error": f"On-chain mint fetch failed: {exc}", "query": token, "needs_mint_address": True}
                continue
            if label == "mint_info":
                mint_info = result or {}
            elif label == "price":
                price = result or {}
            elif label == "holders":
                holders = result or {}
            elif label == "pool":
                pool = result
            elif label == "easya":
                easya_overlay = result

    if mint_info.get("error"):
        return mint_info

    pool_snapshot = _pool_market_snapshot(pool) if pool else None

    price_usd = price.get("price_usd")
    if price_usd is None and pool_snapshot:
        price_usd = pool_snapshot.get("price_usd")

    total_supply = mint_info.get("total_supply")
    market_cap_usd = None
    if price_usd is not None and total_supply is not None:
        try:
            market_cap_usd = float(price_usd) * float(total_supply)
        except (TypeError, ValueError):
            market_cap_usd = pool_snapshot.get("market_cap_usd") if pool_snapshot else None
    elif pool_snapshot:
        market_cap_usd = pool_snapshot.get("market_cap_usd")

    holder_count = None
    if pool_snapshot and pool_snapshot.get("holder_count_indexed") is not None:
        holder_count = pool_snapshot.get("holder_count_indexed")
    if holder_count is None and easya_overlay and easya_overlay.get("holder_count") is not None:
        holder_count = easya_overlay.get("holder_count")

    top_holders = holders.get("top_holders") or []
    top3_pct = None
    if top_holders:
        try:
            top3_pct = sum(float(h.get("percent_of_supply") or 0) for h in top_holders[:3])
        except (TypeError, ValueError):
            top3_pct = None

    risks: list[dict[str, str]] = []
    if not mint_info.get("mint_authority_renounced"):
        risks.append(
            {
                "severity": "high",
                "title": "Active mint authority",
                "detail": "Supply can still be increased unless mint authority is renounced.",
            }
        )
    if not mint_info.get("freeze_authority_renounced"):
        risks.append(
            {
                "severity": "high",
                "title": "Active freeze authority",
                "detail": "Token accounts could be frozen by the authority holder.",
            }
        )
    liq = (pool_snapshot or {}).get("liquidity_usd")
    if liq is not None and float(liq) < 10_000:
        risks.append(
            {
                "severity": "medium",
                "title": "Limited DEX liquidity",
                "detail": f"Primary Meteora pool TVL is {_fmt_usd(liq)} — large trades may have high impact.",
            }
        )
    if top3_pct is not None and top3_pct > 50:
        risks.append(
            {
                "severity": "medium",
                "title": "Concentrated top holders",
                "detail": f"Top 3 wallets hold ~{top3_pct:.1f}% of supply (on-chain snapshot).",
            }
        )

    fetched_at = time.time()
    return {
        "symbol": resolved.get("symbol"),
        "name": resolved.get("name") or mint_info.get("name"),
        "mint": mint,
        "cluster": SOLANA_CLUSTER,
        "price_usd": price_usd,
        "price_source": price.get("source"),
        "change_24h_pct": price.get("change_24h_pct"),
        "market_cap_usd": market_cap_usd,
        "total_supply": total_supply,
        "decimals": mint_info.get("decimals"),
        "holder_count": holder_count,
        "top_holders": top_holders,
        "top3_holder_pct": top3_pct,
        "mint_authority_renounced": mint_info.get("mint_authority_renounced"),
        "freeze_authority_renounced": mint_info.get("freeze_authority_renounced"),
        "primary_pool": pool_snapshot,
        "risks": risks,
        "easya_overlay": easya_overlay,
        "explorer_url": f"https://solscan.io/token/{mint}",
        "data_sources": ["solana_rpc", "jupiter", "meteora_datapi"],
        "attribution": "On-chain data via Solana RPC; price via Jupiter; pool metrics via Meteora datapi.",
        "fetched_at_unix": fetched_at,
        "cache_ttl_seconds": TOKEN_RESEARCH_CACHE_TTL_SECONDS,
    }


def get_onchain_token_research(token: str, holder_limit: int = 10) -> dict[str, Any]:
    """Primary research bundle with 15-minute in-memory cache keyed by mint."""
    resolved = resolve_token(token)
    if "error" in resolved:
        return {**resolved, "query": token, "needs_mint_address": True}

    mint = resolved["mint"]
    cached = _cache_get(mint, holder_limit)
    if cached is not None:
        return {**cached, "cached": True}

    profile = _fetch_onchain_token_research(token, holder_limit=holder_limit)
    if not profile.get("error") and has_min_onchain_data(profile):
        _cache_set(mint, holder_limit, profile)
        profile = {**profile, "cached": False}
    return profile


def _looks_like_mint(value: str) -> bool:
    value = (value or "").strip()
    return 32 <= len(value) <= 44 and bool(re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]+", value))


def extract_token_query(user_input: str) -> Optional[str]:
    text = (user_input or "").strip()
    if not text:
        return None

    mint_match = re.search(r"\b([1-9A-HJ-NP-Za-km-z]{32,44})\b", text)
    if mint_match:
        return mint_match.group(1)

    patterns = [
        r"\b(?:due diligence|diligence)\s+(?:for|on|of)\s+\$?([A-Za-z][A-Za-z0-9]{1,24})\b",
        r"\b(?:token\s+)?(?:analysis|research|overview|profile|report)\s+(?:for|of|on)\s+\$?([A-Za-z][A-Za-z0-9]{1,24})\b",
        r"\b(?:of|for|about|on)\s+\$?([A-Za-z][A-Za-z0-9]{1,24})\b",
        r"\b(?:research|analyze|analyse|check|review|assess)\s+\$?([A-Za-z][A-Za-z0-9]{1,24})\b",
        r"\b(?:research|analyze|analyse|check|review|assess)\s+\$?([A-Za-z][A-Za-z0-9]{1,24})\s+token\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            candidate = match.group(1).upper()
            if candidate not in _TOKEN_STOPWORDS:
                return candidate

    tickers = re.findall(r"\$([A-Za-z][A-Za-z0-9]{1,20})\b", text)
    if tickers:
        return tickers[-1].upper()

    trailing = re.search(r"\b([A-Za-z][A-Za-z0-9]{2,24})\s*[?.!]?\s*$", text)
    if trailing:
        candidate = trailing.group(1).upper()
        if candidate not in _TOKEN_STOPWORDS and RESEARCH_INTENT_RE.search(text):
            return candidate
    return None


def has_min_onchain_data(data: dict[str, Any]) -> bool:
    if data.get("error"):
        return False
    mint = str(data.get("mint") or "")
    if not _looks_like_mint(mint):
        return False
    if data.get("total_supply") is None:
        return False
    return True


def format_unresolved_token_reply(query: str, data: Optional[dict[str, Any]] = None) -> str:
    detail = ""
    if isinstance(data, dict):
        detail = str(data.get("error") or data.get("message") or "").strip()
    return "\n".join(
        [
            f"I couldn't resolve **{query}** to a Solana token mint, so I don't have reliable on-chain data yet.",
            "",
            "Please paste the **token mint address** (32–44 character base58 string) for a precise analysis.",
            "Example for BITAGENTS: `iu3A7azWTm3zQSk81SUC1JctB4zPYnxLmcmqq71EASY`",
            "",
            "You can find the mint on [Solscan](https://solscan.io) or your wallet's token details.",
            *( [f"", f"_Detail: {detail}_"] if detail else [] ),
            "",
            "Once you provide the mint, I'll fetch supply, authorities, holders, price, and pool liquidity from Solana RPC.",
        ]
    )


def format_onchain_research_reply(data: dict[str, Any]) -> str:
    if data.get("error"):
        query = str(data.get("query") or data.get("symbol") or "this token")
        return format_unresolved_token_reply(query, data)
    if not has_min_onchain_data(data):
        query = str(data.get("symbol") or data.get("mint") or "this token")
        return format_unresolved_token_reply(
            query,
            {
                "error": "On-chain mint data was incomplete. Provide the exact mint address for a full analysis.",
            },
        )

    lines = [
        f"**Token Research Brief — {data.get('symbol')}**",
        f"Name: {data.get('name') or data.get('symbol')}",
        f"Mint: `{data.get('mint')}`",
        f"Explorer: {data.get('explorer_url')}",
    ]
    if data.get("cached"):
        ttl = int(data.get("cache_ttl_seconds") or TOKEN_RESEARCH_CACHE_TTL_SECONDS)
        lines.append(f"_Cached on-chain snapshot (shared across users, refreshes every {ttl // 60} minutes)._")
    lines.extend(
        [
        "",
        "**On-chain metrics**",
        f"- Price (USD): {_fmt_usd(data.get('price_usd'))} ({data.get('price_source') or 'jupiter/rpc'})",
        f"- Market cap (est.): {_fmt_usd(data.get('market_cap_usd'))}",
        f"- Total supply: {_fmt_num(data.get('total_supply'))}",
        f"- Holders (indexed): {data.get('holder_count') if data.get('holder_count') is not None else 'see top holders below'}",
        f"- Mint authority renounced: {'yes' if data.get('mint_authority_renounced') else 'no'}",
        f"- Freeze authority renounced: {'yes' if data.get('freeze_authority_renounced') else 'no'}",
        ]
    )

    pool = data.get("primary_pool") or {}
    if pool.get("pool_address"):
        lines.extend(
            [
                "",
                "**Primary Meteora pool**",
                f"- Pool: `{pool.get('pool_address')}` ({pool.get('pool_type')})",
                f"- TVL: {_fmt_usd(pool.get('liquidity_usd'))}",
                f"- 24h volume: {_fmt_usd(pool.get('volume_24h_usd'))}",
                f"- Meteora: {pool.get('meteora_url')}",
            ]
        )

    top = data.get("top_holders") or []
    if top:
        lines.extend(["", "**Top holders (Solana RPC)**"])
        for row in top[:5]:
            wallet = row.get("wallet") or row.get("token_account") or "unknown"
            pct = row.get("percent_of_supply")
            pct_s = f"{pct:.2f}%" if pct is not None else "n/a"
            lines.append(f"- {wallet}: {_fmt_num(row.get('amount'))} ({pct_s})")
        if data.get("top3_holder_pct") is not None:
            lines.append(f"- Top 3 wallets: ~{data['top3_holder_pct']:.1f}% of supply")

    risks = data.get("risks") or []
    if risks:
        lines.extend(["", "**Risks**"])
        for risk in risks:
            lines.append(f"- [{risk.get('severity', 'info').upper()}] {risk.get('title')}: {risk.get('detail')}")

    overlay = data.get("easya_overlay")
    if overlay:
        lines.extend(
            [
                "",
                "**EASY Screener (supplementary)**",
                f"- Verified: {overlay.get('verified')}",
                f"- Liquidity: {_fmt_usd(overlay.get('liquidity_usd'))}",
                f"- 24h volume: {_fmt_usd(overlay.get('volume_24h_usd'))}",
            ]
        )

    lines.extend(["", data.get("attribution", ""), "", "Not financial advice. DYOR."])
    return "\n".join(lines)
