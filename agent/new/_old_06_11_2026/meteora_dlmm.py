"""
Meteora pool helpers: DLMM + DAMM v2 discovery and Jupiter route reuse.

Volume campaigns swap through Jupiter (same path as BITAGENTS Volume).
We never create new DLMM pools from this process.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import requests

METEORA_DLMM_DATAPI = os.environ.get(
    "METEORA_DLMM_DATAPI", "https://dlmm.datapi.meteora.ag"
).rstrip("/")
METEORA_DAMM_V2_DATAPI = os.environ.get(
    "METEORA_DAMM_V2_DATAPI", "https://damm-v2.datapi.meteora.ag"
).rstrip("/")
METEORA_DEFAULT_BIN_STEP = int(os.environ.get("METEORA_DEFAULT_BIN_STEP", "80"))
METEORA_DEFAULT_FEE_BPS = int(os.environ.get("METEORA_DEFAULT_FEE_BPS", "25"))
JUPITER_QUOTE_API = os.environ.get("JUPITER_QUOTE_API", "https://api.jup.ag/swap/v1/quote")
SOL_MINT = "So11111111111111111111111111111111111111112"
NO_ROUTE_MESSAGE = (
    "Jupiter has no swap route for this pair. Volume Agent only runs campaigns on "
    "tokens that already trade (same as BITAGENTS Volume). It does not create new pools."
)


def _route_labels_from_jupiter(data: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    plan = data.get("routePlan") or data.get("routePlans") or []
    if not isinstance(plan, list):
        return labels
    for hop in plan:
        if not isinstance(hop, dict):
            continue
        info = hop.get("swapInfo") if isinstance(hop.get("swapInfo"), dict) else hop
        label = info.get("label") if isinstance(info, dict) else None
        if label:
            labels.append(str(label))
    return labels


def check_jupiter_route_exists(token_mint: str, quote_mint: str = SOL_MINT) -> dict[str, Any]:
    """
    True when Jupiter can already swap this pair (any venue: DLMM, DAMM v2,
    Pump, Raydium, …). Volume campaigns execute through Jupiter, so a quote
    is enough — we must not create a redundant empty DLMM pool.
    """
    token_mint = token_mint.strip()
    quote_mint = (quote_mint or SOL_MINT).strip()

    def _ok(labels: list[str], *, estimated_output: Any = None) -> dict[str, Any]:
        meteora = any("meteora" in (lbl or "").lower() for lbl in labels)
        return {
            "ok": True,
            "source": "meteora (via Jupiter)" if meteora else "jupiter",
            "route_labels": labels,
            "meteora_in_route": meteora,
            "estimated_output": estimated_output,
        }

    try:
        from dca_agent import _jupiter_get, get_jupiter_quote, get_wallet_pubkey
        from volume_ledger import get_volume_wallet_pubkey

        taker = get_volume_wallet_pubkey() or get_wallet_pubkey()
        if taker:
            last_err = None
            for amount_sol in (0.01, 0.001):
                quote = get_jupiter_quote(quote_mint, token_mint, amount_sol, slippage_bps=500, taker=taker)
                if not quote.get("error"):
                    data = quote.get("build_data") if isinstance(quote.get("build_data"), dict) else {}
                    labels = _route_labels_from_jupiter(data)
                    if labels or quote.get("estimated_output"):
                        return _ok(labels, estimated_output=quote.get("estimated_output"))
                last_err = quote.get("error")
            if last_err:
                print(f"  Jupiter v2 route check: {last_err}")

        for amount in ("10000000", "1000000", "100000"):
            resp = _jupiter_get(
                JUPITER_QUOTE_API,
                {
                    "inputMint": quote_mint,
                    "outputMint": token_mint,
                    "amount": amount,
                    "slippageBps": "500",
                },
            )
            if not resp.ok:
                continue
            data = resp.json()
            if not isinstance(data, dict) or data.get("error"):
                continue
            labels = _route_labels_from_jupiter(data)
            if labels or data.get("outAmount") or data.get("routePlan"):
                return _ok(labels, estimated_output=data.get("outAmount"))
    except Exception as exc:
        print(f"  Jupiter route check failed: {exc}")
        return {"ok": False, "error": str(exc)}

    return {"ok": False, "error": "Jupiter has no route for this pair."}


def _normalize_mint_pair(mint_a: str, mint_b: str) -> tuple[str, str]:
    a = mint_a.strip()
    b = mint_b.strip()
    return (a, b) if a < b else (b, a)


def get_pool_creation_cost_sol() -> float:
    """Volume Agent does not create pools; kept for API compatibility."""
    return 0.0


def meteora_pool_app_url(pool_address: str, pool_type: str = "dlmm") -> str:
    """Link to the pool on Meteora's app (on-chain address, not our DB)."""
    address = pool_address.strip()
    if pool_type == "damm_v2":
        return f"https://app.meteora.ag/pools/{address}"
    return f"https://app.meteora.ag/dlmm/{address}"


def _pair_from_datapi_pool(pair: dict[str, Any], pool_type: str) -> dict[str, Any]:
    token_x = pair.get("token_x") or {}
    token_y = pair.get("token_y") or {}
    x = token_x.get("address") if isinstance(token_x, dict) else str(token_x or "")
    y = token_y.get("address") if isinstance(token_y, dict) else str(token_y or "")
    pool_config = pair.get("pool_config") or {}
    volume = pair.get("volume") or {}
    base_fee_pct = pool_config.get("base_fee_pct")
    base_fee_bps = None
    if base_fee_pct is not None:
        try:
            base_fee_bps = int(round(float(base_fee_pct) * 100))
        except (TypeError, ValueError):
            base_fee_bps = None
    pool_address = pair.get("address") or pair.get("lb_pair")
    return {
        "pool_address": pool_address,
        "pool_type": pool_type,
        "mint_x": x,
        "mint_y": y,
        "bin_step": pool_config.get("bin_step") or pair.get("bin_step"),
        "base_fee_bps": base_fee_bps,
        "name": pair.get("name"),
        "liquidity": pair.get("tvl") or pair.get("liquidity"),
        "trade_volume_24h": volume.get("24h") if isinstance(volume, dict) else pair.get("trade_volume_24h"),
        "meteora_url": meteora_pool_app_url(str(pool_address), pool_type),
        "raw": pair,
    }


def _find_pool_via_datapi(
    api_base: str,
    mint_a: str,
    mint_b: str,
    pool_type: str,
) -> Optional[dict[str, Any]]:
    """
    Query Meteora's indexed pool API. Tries both token_x/token_y orientations because
    on-chain pool orientation does not always match lexicographic mint order.
    """
    orientations = ((mint_a, mint_b), (mint_b, mint_a))
    best: Optional[dict[str, Any]] = None
    best_volume = -1.0

    for token_x, token_y in orientations:
        try:
            resp = requests.get(
                f"{api_base}/pools",
                params={
                    "filter_by": f"token_x={token_x} && token_y={token_y}",
                    "page_size": 5,
                    "sort_by": "volume_24h:desc",
                },
                timeout=25,
            )
            resp.raise_for_status()
            data = resp.json()
            pools = data.get("data") if isinstance(data, dict) else None
            if not pools:
                continue
            candidate = _pair_from_datapi_pool(pools[0], pool_type)
            vol = float(candidate.get("trade_volume_24h") or 0)
            if vol >= best_volume:
                best = candidate
                best_volume = vol
        except Exception as exc:
            print(f"  Meteora {pool_type} lookup failed ({token_x[:6]}…/{token_y[:6]}…): {exc}")

    return best


def find_dlmm_pool(token_mint: str, quote_mint: str = SOL_MINT) -> Optional[dict[str, Any]]:
    """Return Meteora DLMM pair metadata if a pool exists for the mint pair."""
    token_mint = token_mint.strip()
    quote_mint = quote_mint.strip() or SOL_MINT
    mint_x, mint_y = _normalize_mint_pair(token_mint, quote_mint)
    found = _find_pool_via_datapi(METEORA_DLMM_DATAPI, mint_x, mint_y, "dlmm")
    if found and found.get("pool_address"):
        return found
    return None


def find_damm_v2_pool(token_mint: str, quote_mint: str = SOL_MINT) -> Optional[dict[str, Any]]:
    """Return Meteora DAMM v2 pair metadata if a pool exists for the mint pair."""
    token_mint = token_mint.strip()
    quote_mint = quote_mint.strip() or SOL_MINT
    mint_x, mint_y = _normalize_mint_pair(token_mint, quote_mint)
    found = _find_pool_via_datapi(METEORA_DAMM_V2_DATAPI, mint_x, mint_y, "damm_v2")
    if found and found.get("pool_address"):
        return found
    return None


def find_meteora_pool(token_mint: str, quote_mint: str = SOL_MINT) -> Optional[dict[str, Any]]:
    """Prefer DLMM, then DAMM v2 — both queried live from Meteora."""
    dlmm = find_dlmm_pool(token_mint, quote_mint)
    if dlmm:
        return dlmm
    return find_damm_v2_pool(token_mint, quote_mint)


def check_pool_infrastructure(token_mint: str, quote_mint: str = SOL_MINT) -> dict[str, Any]:
    """
    Live liquidity check: Meteora DLMM/DAMM first, then any Jupiter route.

    Volume swaps go through Jupiter, so a quote is sufficient to start a campaign.
    """
    existing = find_meteora_pool(token_mint, quote_mint)
    if existing and existing.get("pool_address"):
        pool_address = existing["pool_address"]
        pool_type = existing.get("pool_type") or "dlmm"
        label = "DLMM" if pool_type == "dlmm" else "DAMM v2"
        return {
            "pool_exists": True,
            "pool_address": pool_address,
            "pool_type": pool_type,
            "action": "reuse_pool",
            "source": "meteora",
            "jupiter_route": True,
            "meteora_url": existing.get("meteora_url") or meteora_pool_app_url(pool_address, pool_type),
            "pool": existing,
            "pool_creation_cost_sol": 0.0,
            "platform_fee_bps": METEORA_DEFAULT_FEE_BPS,
            "message": f"Meteora {label} pool found: {pool_address}",
        }

    jupiter = check_jupiter_route_exists(token_mint, quote_mint)
    if jupiter.get("ok"):
        labels = [str(x) for x in (jupiter.get("route_labels") or []) if x]
        venue = ", ".join(labels[:3])
        source = jupiter.get("source") or "jupiter"
        return {
            "pool_exists": True,
            "pool_address": None,
            "pool_type": None,
            "action": "reuse_existing_liquidity",
            "source": source,
            "jupiter_route": True,
            "route_labels": labels,
            "pool": None,
            "pool_creation_cost_sol": 0.0,
            "platform_fee_bps": METEORA_DEFAULT_FEE_BPS,
            "message": (
                "No dedicated Meteora DLMM/DAMM listing, but Jupiter already routes this pair"
                + (f" via {venue}" if venue else " through existing liquidity")
                + ". Volume swaps use that route; no new DLMM pool is created."
            ),
        }

    return {
        "pool_exists": False,
        "pool_address": None,
        "pool_type": None,
        "action": "no_route",
        "source": "jupiter",
        "jupiter_route": False,
        "pool": None,
        "pool_creation_cost_sol": 0.0,
        "platform_fee_bps": METEORA_DEFAULT_FEE_BPS,
        "bin_step": METEORA_DEFAULT_BIN_STEP,
        "message": NO_ROUTE_MESSAGE,
        "error": NO_ROUTE_MESSAGE,
    }


def ensure_meteora_dlmm_pool(
    token_mint: str,
    quote_mint: str = SOL_MINT,
    *,
    create_if_missing: bool = False,
    quote_amount: float = 0.0,
    token_amount: float = 0.0,
    bin_step: Optional[int] = None,
    fee_bps: Optional[int] = None,
) -> dict[str, Any]:
    """Reuse existing Meteora/Jupiter liquidity. Never creates a new DLMM pool."""
    del create_if_missing, quote_amount, token_amount, bin_step, fee_bps
    checked = check_pool_infrastructure(token_mint, quote_mint)
    if checked.get("pool_exists"):
        return {
            **checked,
            "status": "exists" if checked.get("pool_address") else "jupiter_route",
        }
    return {
        **checked,
        "status": "missing",
        "error": checked.get("error") or NO_ROUTE_MESSAGE,
    }

