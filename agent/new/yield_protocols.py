"""Solana yield comparison: DefiLlama pools + executable liquid-staking venues."""

from __future__ import annotations

import time
from typing import Any, Optional

import requests

SOL_MINT = "So11111111111111111111111111111111111111112"
DEFILLAMA_POOLS_URL = "https://yields.llama.fi/pools"
CACHE_TTL_SECONDS = 120

# Jupiter-swappable SOL liquid staking tokens. Lending (Kamino / Marginfi / Save)
# is compared but not auto-executed without those protocol SDKs.
EXECUTABLE_LSTs = {
    "jito": {
        "protocol_id": "jito",
        "protocol_name": "Jito",
        "symbol": "JITOSOL",
        "mint": "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn",
        "project_keys": ("jito",),
        "symbol_keys": ("jitosol", "jitosol", "jito sol"),
    },
    "marinade": {
        "protocol_id": "marinade",
        "protocol_name": "Marinade",
        "symbol": "MSOL",
        "mint": "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",
        "project_keys": ("marinade-finance", "marinade"),
        "symbol_keys": ("msol",),
    },
    "sanctum": {
        "protocol_id": "sanctum",
        "protocol_name": "Sanctum Infinity",
        "symbol": "INF",
        "mint": "5oVNBeEEQvYi1cX3ir8Dx5n1P7pdxydbGF2X4TxVusJm",
        "project_keys": ("sanctum",),
        "symbol_keys": ("inf",),
    },
    "blaze": {
        "protocol_id": "blaze",
        "protocol_name": "BlazeStake",
        "symbol": "BSOL",
        "mint": "bSo13r4TkiE4KumL71LsHTPpL2euBYLFx6h9HP3piy1",
        "project_keys": ("blazestake",),
        "symbol_keys": ("bsol",),
    },
    "jupsol": {
        "protocol_id": "jupsol",
        "protocol_name": "Jupiter Staked SOL",
        "symbol": "JUPSOL",
        "mint": "jupSoLaHXQiZZTSfEWMTRRgpnyFm8f6sZdusvNx5gMJ",
        "project_keys": ("jupiter-staked-sol", "jupiter"),
        "symbol_keys": ("jupsol",),
    },
}

_cache: dict[str, Any] = {"ts": 0.0, "pools": []}


def _fetch_pools() -> list[dict[str, Any]]:
    now = time.time()
    if _cache["pools"] and now - float(_cache["ts"] or 0) < CACHE_TTL_SECONDS:
        return _cache["pools"]
    try:
        res = requests.get(DEFILLAMA_POOLS_URL, timeout=20)
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
        chain = str(pool.get("chain") or "").lower()
        if chain != "solana":
            continue
        out.append(pool)
    return out


def _match_executable(pool: dict[str, Any]) -> Optional[dict[str, Any]]:
    project = str(pool.get("project") or "").strip().lower()
    symbol = str(pool.get("symbol") or "").strip().lower().replace(" ", "")
    for spec in EXECUTABLE_LSTs.values():
        if project in spec["project_keys"]:
            return spec
        if symbol in spec["symbol_keys"] or symbol == spec["symbol"].lower():
            return spec
    return None


def compare_solana_yields(limit: int = 12) -> dict[str, Any]:
    """Rank Solana yield venues. Executable = can deploy SOL via Jupiter LST swap."""
    pools = _solana_pools()
    executable: list[dict[str, Any]] = []
    seen: set[str] = set()
    lending: list[dict[str, Any]] = []

    for pool in pools:
        apy = pool.get("apy")
        try:
            apy_f = float(apy) if apy is not None else None
        except (TypeError, ValueError):
            apy_f = None
        if apy_f is None or apy_f <= 0:
            continue
        tvl = float(pool.get("tvlUsd") or 0)
        spec = _match_executable(pool)
        row = {
            "project": pool.get("project"),
            "symbol": pool.get("symbol"),
            "apy": round(apy_f, 3),
            "tvl_usd": round(tvl, 0),
            "pool_id": pool.get("pool"),
        }
        if spec and spec["protocol_id"] not in seen:
            seen.add(spec["protocol_id"])
            executable.append(
                {
                    **row,
                    **{k: spec[k] for k in ("protocol_id", "protocol_name", "mint", "symbol")},
                    "executable": True,
                    "kind": "liquid_staking",
                }
            )
        else:
            project = str(pool.get("project") or "").lower()
            if any(k in project for k in ("kamino", "marginfi", "save", "solend", "drift")):
                lending.append({**row, "executable": False, "kind": "lending"})

    executable.sort(key=lambda r: float(r.get("apy") or 0), reverse=True)
    lending.sort(key=lambda r: float(r.get("apy") or 0), reverse=True)

    for spec in EXECUTABLE_LSTs.values():
        if spec["protocol_id"] in seen:
            continue
        executable.append(
            {
                "protocol_id": spec["protocol_id"],
                "protocol_name": spec["protocol_name"],
                "symbol": spec["symbol"],
                "mint": spec["mint"],
                "apy": None,
                "tvl_usd": None,
                "executable": True,
                "kind": "liquid_staking",
                "note": "APY unavailable from DefiLlama right now",
            }
        )

    best = next((r for r in executable if r.get("apy") is not None), executable[0] if executable else None)
    return {
        "asset": "SOL",
        "executable_venues": executable,
        "lending_compare": lending[:limit],
        "best_executable": best,
        "note": (
            "Live deployment uses Jupiter swaps into liquid-staking tokens (jitoSOL, mSOL, INF, bSOL, jupSOL). "
            "Kamino / Marginfi / Save rates are shown for comparison."
        ),
    }


def get_executable_venue(protocol_id: str) -> Optional[dict[str, Any]]:
    key = (protocol_id or "").strip().lower()
    if key in EXECUTABLE_LSTs:
        spec = EXECUTABLE_LSTs[key]
        return {**spec}
    comparison = compare_solana_yields()
    for row in comparison.get("executable_venues") or []:
        if str(row.get("protocol_id") or "").lower() == key:
            return row
        if str(row.get("symbol") or "").lower() == key:
            return row
    return None


def best_executable_venue(min_apy: Optional[float] = None) -> Optional[dict[str, Any]]:
    comparison = compare_solana_yields()
    for row in comparison.get("executable_venues") or []:
        apy = row.get("apy")
        if apy is None:
            continue
        if min_apy is not None and float(apy) < float(min_apy):
            continue
        return row
    venues = comparison.get("executable_venues") or []
    return venues[0] if venues else None


def _symbol_parts(symbol: str) -> list[str]:
    raw = str(symbol or "").upper().replace("/", "-")
    return [part.strip() for part in raw.split("-") if part.strip()]


def _lst_symbol_match(symbol: str, spec: dict[str, Any]) -> bool:
    compact = symbol.upper().replace(" ", "").replace("-", "")
    keys = {str(key).replace(" ", "").replace("-", "").upper() for key in spec["symbol_keys"]}
    keys.add(str(spec["symbol"]).upper())
    return compact in keys


def _pool_matches_asset(pool: dict[str, Any], asset: str) -> bool:
    """Keep single-asset yield and liquid staking. Skip LP pairs such as WSOL-MEME."""
    symbol = str(pool.get("symbol") or "")
    parts = _symbol_parts(symbol)
    if len(parts) >= 2:
        return False
    compact = symbol.upper().replace(" ", "").replace("-", "")
    spec = _match_executable(pool)
    if spec and _lst_symbol_match(symbol, spec):
        return asset == "SOL"
    if asset == "SOL":
        return compact in {"SOL", "WSOL"}
    return compact == asset or asset in parts


def _capital_usd(asset: str, capital: float) -> float:
    asset = asset.upper()
    if asset in ("USDC", "USDT"):
        return float(capital)
    if asset == "SOL":
        try:
            from dca_agent import get_token_price

            quote = get_token_price("SOL")
            px = float((quote or {}).get("price_usd") or 0)
            if px > 0:
                return float(capital) * px
        except Exception:
            pass
        return float(capital) * 150.0
    return float(capital)


def compare_for_requirements(
    *,
    asset: str,
    capital: float,
    duration_days: int,
    limit: int = 8,
) -> dict[str, Any]:
    """Rank Solana pools for an asset, capital size, and how long the user will stay in."""
    asset = (asset or "SOL").strip().upper()
    capital = float(capital or 0)
    duration = max(1, int(duration_days or 30))
    min_tvl = max(25_000.0, _capital_usd(asset, capital) * 20.0)
    ranked: list[dict[str, Any]] = []

    for pool in _solana_pools():
        symbol = str(pool.get("symbol") or "")
        project = str(pool.get("project") or "")
        if not _pool_matches_asset(pool, asset):
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
        il = str(pool.get("ilRisk") or "").lower()
        stable = bool(pool.get("stablecoin"))
        spec = _match_executable(pool)
        if spec:
            compact = symbol.lower().replace("-", "")
            keys = {str(key).replace(" ", "").replace("-", "") for key in spec["symbol_keys"]}
            keys.add(str(spec["symbol"]).lower())
            if compact not in keys and not any(key and key in compact for key in keys):
                spec = None
        score = apy_f
        if duration <= 30:
            if il == "yes":
                score -= 4
            if spec or stable:
                score += 0.4
        elif duration >= 90 and apy_f > 0:
            score += min(apy_f, 15) * 0.05
        ranked.append(
            {
                "project": project,
                "symbol": pool.get("symbol"),
                "apy": round(apy_f, 3),
                "tvl_usd": round(tvl, 0),
                "il_risk": pool.get("ilRisk"),
                "stablecoin": stable,
                "executable": bool(spec),
                "protocol_id": spec["protocol_id"] if spec else project,
                "protocol_name": spec["protocol_name"] if spec else project,
                "mint": spec["mint"] if spec else None,
                "score": round(score, 3),
                "kind": "liquid_staking" if spec else "pool",
            }
        )

    ranked.sort(key=lambda row: float(row.get("score") or 0), reverse=True)
    best_overall = ranked[0] if ranked else None
    best_exec = next((row for row in ranked if row.get("executable") and row.get("mint")), None)
    execute = None
    route = None
    if best_overall and best_overall.get("executable") and best_overall.get("mint"):
        execute = best_overall
        route = "same_asset"
    elif best_exec and best_exec.get("mint"):
        gap = float((best_overall or {}).get("apy") or 0) - float(best_exec.get("apy") or 0)
        if gap <= 1.5:
            execute = best_exec
            route = "same_asset"
    if execute is None and asset == "SOL":
        sol_lst = best_executable_venue()
        if sol_lst and sol_lst.get("mint"):
            execute = {**sol_lst, "executable": True, "kind": "liquid_staking"}
            route = "jupiter_swap_to_lst"
    elif execute is None and asset != "SOL":
        sol_lst = best_executable_venue()
        if sol_lst and sol_lst.get("mint") and sol_lst.get("apy") is not None:
            overall_apy = float((best_overall or {}).get("apy") or 0)
            lst_apy = float(sol_lst.get("apy") or 0)
            if overall_apy <= 0 or lst_apy + 0.25 >= overall_apy:
                execute = {**sol_lst, "executable": True, "kind": "liquid_staking"}
                route = "jupiter_swap_to_lst"

    return {
        "requirements": {
            "asset": asset,
            "capital": capital,
            "duration_days": duration,
            "min_tvl_usd": round(min_tvl, 0),
        },
        "ranked": ranked[:limit],
        "best_overall": best_overall,
        "best_to_execute": execute,
        "execution_route": route,
        "note": (
            "Capital sits in the user's Circle yield wallet. A Jupiter swap stakes it when the "
            "best venue is executable (liquid staking). Lending venues are compared and used "
            "only when their APY is not beaten by an executable venue."
        ),
    }
