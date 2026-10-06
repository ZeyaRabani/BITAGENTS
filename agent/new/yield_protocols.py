"""Solana yield comparison for Kamino, Jupiter JLP, MarginFi, Drift, and Save."""

from __future__ import annotations

import time
from typing import Any, Optional

import requests

SOL_MINT = "So11111111111111111111111111111111111111112"
JLP_MINT = "27G8MtK7VtTcCHkpASjSDdkWWYfoqT6ggEuKidVJidD4"
DEFILLAMA_POOLS_URL = "https://yields.llama.fi/pools"
CACHE_TTL_SECONDS = 120

# Live Jupiter swap. Lending, Kamino vaults, and Drift insurance are ranked,
# then left idle because those positions are protocol deposits, not a token swap.
JLP_VENUE = {
    "protocol_id": "jlp",
    "protocol_name": "Jupiter",
    "symbol": "JLP",
    "mint": JLP_MINT,
    "yield_type": "jlp",
    "kind": "jlp",
    "executable": True,
}

YIELD_TYPES = {
    "any": "Best across the supported protocols",
    "lending": "Lending markets",
    "liquidity_vault": "Kamino liquidity vaults",
    "jlp": "Jupiter JLP liquidity provision",
    "insurance": "Drift insurance fund",
}

# project slug -> protocol. Exact slugs avoid liquid-staking lookalikes
# such as drift-staked-sol and save-sol.
PROTOCOL_BY_PROJECT = {
    "kamino-lend": {
        "protocol_id": "kamino",
        "protocol_name": "Kamino Finance",
        "yield_type": "lending",
        "kind": "lending",
    },
    "kamino-liquidity": {
        "protocol_id": "kamino-vault",
        "protocol_name": "Kamino Finance",
        "yield_type": "liquidity_vault",
        "kind": "liquidity_vault",
    },
    "marginfi": {
        "protocol_id": "marginfi",
        "protocol_name": "MarginFi",
        "yield_type": "lending",
        "kind": "lending",
    },
    "drift": {
        "protocol_id": "drift",
        "protocol_name": "Drift Protocol",
        "yield_type": "lending",
        "kind": "lending",
    },
    "drift-insurance": {
        "protocol_id": "drift-insurance",
        "protocol_name": "Drift Protocol",
        "yield_type": "insurance",
        "kind": "insurance",
    },
    "save": {
        "protocol_id": "save",
        "protocol_name": "Save Finance",
        "yield_type": "lending",
        "kind": "lending",
    },
}

_YIELD_TYPE_ALIASES = {
    "any": "any",
    "best": "any",
    "all": "any",
    "lending": "lending",
    "lend": "lending",
    "liquidity": "liquidity_vault",
    "liquidity_vault": "liquidity_vault",
    "liquidity_vaults": "liquidity_vault",
    "vault": "liquidity_vault",
    "vaults": "liquidity_vault",
    "jlp": "jlp",
    "jupiter": "jlp",
    "liquidity_provision": "jlp",
    "insurance": "insurance",
    "insurance_fund": "insurance",
}

_cache: dict[str, Any] = {"ts": 0.0, "pools": []}


def normalize_yield_type(value: Optional[str]) -> str:
    key = (value or "any").strip().lower().replace(" ", "_").replace("-", "_")
    if key not in _YIELD_TYPE_ALIASES:
        allowed = ", ".join(YIELD_TYPES)
        raise ValueError(f"Yield type must be one of: {allowed}.")
    return _YIELD_TYPE_ALIASES[key]


def _fetch_pools() -> list[dict[str, Any]]:
    now = time.time()
    if _cache["pools"] and now - float(_cache["ts"] or 0) < CACHE_TTL_SECONDS:
        return _cache["pools"]
    try:
        # The installed brotli build can't decode DefiLlama's br-compressed
        # response (streaming decode error) -- request gzip/deflate instead.
        res = requests.get(DEFILLAMA_POOLS_URL, timeout=20, headers={"Accept-Encoding": "gzip, deflate"})
        res.raise_for_status()
        data = res.json()
        pools = data.get("data") if isinstance(data, dict) else data
        if not isinstance(pools, list):
            pools = []
    except Exception as exc:
        print(f"  ⚠️  DefiLlama yields fetch failed: {exc}")
        pools = _cache["pools"] or []
    _cache["ts"] = now
    _cache["pools"] = pools
    return pools


def _solana_pools() -> list[dict[str, Any]]:
    out = []
    for pool in _fetch_pools():
        if str(pool.get("chain") or "").lower() != "solana":
            continue
        out.append(pool)
    return out


def _match_protocol(pool: dict[str, Any]) -> Optional[dict[str, Any]]:
    project = str(pool.get("project") or "").strip().lower()
    if project in PROTOCOL_BY_PROJECT:
        return PROTOCOL_BY_PROJECT[project]
    if project.startswith("marginfi"):
        return PROTOCOL_BY_PROJECT["marginfi"]
    symbol = str(pool.get("symbol") or "").strip().upper().replace(" ", "").replace("-", "")
    if symbol == "JLP" and project.startswith("jupiter") and "staked" not in project and "lend" not in project:
        return {
            "protocol_id": "jlp",
            "protocol_name": "Jupiter",
            "yield_type": "jlp",
            "kind": "jlp",
            "mint": JLP_MINT,
        }
    return None


def _symbol_parts(symbol: str) -> list[str]:
    raw = str(symbol or "").upper().replace("/", "-")
    return [part.strip() for part in raw.split("-") if part.strip()]


def _matches_asset(pool: dict[str, Any], spec: dict[str, Any], asset: str) -> bool:
    if spec.get("yield_type") == "jlp":
        return True
    parts = _symbol_parts(str(pool.get("symbol") or ""))
    compact = "".join(parts)
    aliases = {asset}
    if asset == "SOL":
        aliases.add("WSOL")
    if spec.get("yield_type") == "liquidity_vault":
        return any(part in aliases for part in parts)
    if len(parts) >= 2:
        return False
    return compact in aliases or (asset == "SOL" and compact in {"SOL", "WSOL"})


def _capital_usd(asset: str, capital: float) -> float:
    try:
        from dca_agent import get_token_price

        quote = get_token_price("SOL")
        px = float((quote or {}).get("price_usd") or 0)
        if px > 0:
            return float(capital) * px
    except Exception:
        pass
    return float(capital) * 150.0


def _coverage(rows: list[dict[str, Any]], yield_type: str = "any") -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[str(row.get("protocol_id"))] = counts.get(str(row.get("protocol_id")), 0) + 1
    catalog = [
        ("kamino", "Kamino Finance", "lending"),
        ("kamino-vault", "Kamino Finance", "liquidity_vault"),
        ("jlp", "Jupiter", "jlp"),
        ("marginfi", "MarginFi", "lending"),
        ("drift", "Drift Protocol", "lending"),
        ("drift-insurance", "Drift Protocol", "insurance"),
        ("save", "Save Finance", "lending"),
    ]
    out = []
    for protocol_id, name, kind in catalog:
        if yield_type != "any" and kind != yield_type:
            continue
        markets = counts.get(protocol_id, 0)
        item = {
            "protocol_id": protocol_id,
            "protocol_name": name,
            "yield_type": kind,
            "markets": markets,
        }
        if markets == 0 and protocol_id == "marginfi":
            item["note"] = "No REST yield API. Docs: https://docs.marginfi.com/ts-sdk"
        elif markets == 0 and protocol_id in ("drift", "drift-insurance"):
            item["note"] = "No deposit API. Docs: https://docs.drift.trade/developers/data-api"
        elif markets == 0 and protocol_id != "jlp":
            item["note"] = "No live pool in the yield feed right now."
        out.append(item)
    return out


def _row_from_pool(pool: dict[str, Any], spec: dict[str, Any], apy: float, duration: int) -> dict[str, Any]:
    tvl = float(pool.get("tvlUsd") or 0)
    il = str(pool.get("ilRisk") or "").lower()
    score = apy
    if spec.get("yield_type") == "liquidity_vault" and duration <= 30 and il == "yes":
        score -= 8
    elif duration <= 30 and il == "yes":
        score -= 4
    mint = spec.get("mint") if spec.get("yield_type") == "jlp" else None
    return {
        "project": pool.get("project"),
        "symbol": pool.get("symbol"),
        "apy": round(apy, 3),
        "tvl_usd": round(tvl, 0),
        "il_risk": pool.get("ilRisk"),
        "stablecoin": bool(pool.get("stablecoin")),
        "executable": bool(mint),
        "protocol_id": spec["protocol_id"],
        "protocol_name": spec["protocol_name"],
        "mint": mint,
        "yield_type": spec["yield_type"],
        "kind": spec.get("kind") or spec["yield_type"],
        "score": round(score, 3),
    }


def _with_protocol_apis(rows: list[dict[str, Any]], yield_type: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Prefer Kamino and Save API rows over DefiLlama for the same protocol."""
    from yield_protocol_apis import fetch_protocol_markets

    payload = fetch_protocol_markets()
    api_rows = []
    for row in payload.get("markets") or []:
        if yield_type != "any" and row.get("yield_type") != yield_type:
            continue
        api_rows.append(row)
    replaced = {str(row.get("protocol_id")) for row in api_rows}
    kept = [row for row in rows if str(row.get("protocol_id")) not in replaced]
    merged = api_rows + kept
    merged.sort(key=lambda row: float(row.get("score") or row.get("apy") or 0), reverse=True)
    return merged, payload


def compare_solana_yields(limit: int = 12, yield_type: str = "any") -> dict[str, Any]:
    """Rank the supported protocols. Kamino deposits use its API. JLP uses Jupiter."""
    ytype = normalize_yield_type(yield_type)
    markets: list[dict[str, Any]] = []
    jlp_apy = None
    for pool in _solana_pools():
        spec = _match_protocol(pool)
        if not spec:
            continue
        if ytype != "any" and spec["yield_type"] != ytype:
            continue
        try:
            apy_f = float(pool.get("apy"))
        except (TypeError, ValueError):
            continue
        if apy_f <= 0:
            continue
        if spec["yield_type"] == "jlp":
            jlp_apy = apy_f if jlp_apy is None else max(jlp_apy, apy_f)
        markets.append(_row_from_pool(pool, spec, apy_f, 30))
    markets.sort(key=lambda row: float(row.get("score") or 0), reverse=True)
    markets, api_payload = _with_protocol_apis(markets, ytype)
    jlp = {**JLP_VENUE, "apy": round(jlp_apy, 3) if jlp_apy is not None else None}
    executable_rows = [row for row in markets if row.get("executable")]
    executable_venues = executable_rows + [jlp]
    best_executable = max(
        executable_venues,
        key=lambda row: float(row.get("score") or row.get("apy") or 0),
        default=jlp,
    )
    return {
        "yield_type": ytype,
        "yield_types": [{"id": key, "label": label} for key, label in YIELD_TYPES.items()],
        "markets": markets[:limit],
        "executable_venues": executable_venues,
        "best_executable": best_executable,
        "coverage": _coverage(markets, ytype),
        "protocol_apis": (api_payload or {}).get("status"),
        "protocol_api_errors": (api_payload or {}).get("errors") or {},
        "note": (
            "Kamino lending and liquidity vaults deposit through https://api.kamino.finance. "
            "Save rates come from https://api.save.finance. "
            "Jupiter JLP is still a Jupiter swap. "
            "MarginFi has no REST API (https://docs.marginfi.com/ts-sdk). "
            "Drift's data API does not build deposits (https://docs.drift.trade/developers/data-api)."
        ),
    }


def get_executable_venue(protocol_id: str) -> Optional[dict[str, Any]]:
    key = (protocol_id or "").strip().lower()
    if key in ("jlp", "jupiter"):
        return {**JLP_VENUE}
    return None


def best_executable_venue(min_apy: Optional[float] = None) -> Optional[dict[str, Any]]:
    comparison = compare_solana_yields()
    venue = comparison.get("best_executable") or {**JLP_VENUE}
    apy = venue.get("apy")
    if min_apy is not None and apy is not None and float(apy) < float(min_apy):
        return None
    return venue


def compare_for_requirements(
    *,
    asset: str,
    capital: float,
    duration_days: int,
    yield_type: str = "any",
    limit: int = 8,
) -> dict[str, Any]:
    """Rank supported markets for an asset, capital, duration, and optional yield type."""
    asset = (asset or "SOL").strip().upper()
    if asset != "SOL":
        raise ValueError("The Yield Agent accepts SOL only.")
    ytype = normalize_yield_type(yield_type)
    capital = float(capital or 0)
    duration = max(1, int(duration_days or 30))
    min_tvl = max(25_000.0, _capital_usd(asset, capital) * 20.0)
    ranked: list[dict[str, Any]] = []
    jlp_apy = None

    for pool in _solana_pools():
        spec = _match_protocol(pool)
        if not spec:
            continue
        if ytype != "any" and spec["yield_type"] != ytype:
            continue
        if not _matches_asset(pool, spec, asset):
            continue
        try:
            apy_f = float(pool.get("apy"))
        except (TypeError, ValueError):
            continue
        if apy_f <= 0:
            continue
        tvl = float(pool.get("tvlUsd") or 0)
        if tvl < min_tvl:
            continue
        if spec["yield_type"] == "jlp":
            jlp_apy = apy_f if jlp_apy is None else max(jlp_apy, apy_f)
        ranked.append(_row_from_pool(pool, spec, apy_f, duration))

    ranked.sort(key=lambda row: float(row.get("score") or 0), reverse=True)
    ranked, api_payload = _with_protocol_apis(ranked, ytype)
    best_overall = next((row for row in ranked if row.get("apy") is not None), None)
    jlp = {**JLP_VENUE, "apy": round(jlp_apy, 3) if jlp_apy is not None else None, "score": jlp_apy or 0}
    execute = None
    route = None
    if ytype == "jlp":
        execute = jlp
        route = "jupiter_swap_to_jlp"
    elif best_overall and best_overall.get("deposit_route"):
        execute = best_overall
        route = str(best_overall.get("deposit_route"))
    elif ytype == "any" and best_overall and best_overall.get("executable") and best_overall.get("mint"):
        execute = best_overall
        route = "jupiter_swap_to_jlp"

    return {
        "requirements": {
            "asset": asset,
            "capital": capital,
            "duration_days": duration,
            "yield_type": ytype,
            "min_tvl_usd": round(min_tvl, 0),
        },
        "ranked": ranked[:limit],
        "best_overall": best_overall,
        "best_to_execute": execute,
        "execution_route": route,
        "coverage": _coverage(ranked, ytype),
        "protocol_apis": (api_payload or {}).get("status"),
        "protocol_api_errors": (api_payload or {}).get("errors") or {},
        "note": compare_solana_yields(limit=1, yield_type=ytype).get("note"),
    }
