"""
Meteora pool helpers: DLMM + DAMM v2 discovery, creation cost, and pool reuse checks.

Uses Meteora's indexed APIs (not our database):
- DLMM:  https://dlmm.datapi.meteora.ag/pools
- DAMM:  https://damm-v2.datapi.meteora.ag/pools
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Optional

import requests

METEORA_DLMM_DATAPI = os.environ.get(
    "METEORA_DLMM_DATAPI", "https://dlmm.datapi.meteora.ag"
).rstrip("/")
METEORA_DAMM_V2_DATAPI = os.environ.get(
    "METEORA_DAMM_V2_DATAPI", "https://damm-v2.datapi.meteora.ag"
).rstrip("/")
METEORA_POOL_CREATION_SOL = float(os.environ.get("METEORA_POOL_CREATION_SOL", "0.02669"))
METEORA_DEFAULT_BIN_STEP = int(os.environ.get("METEORA_DEFAULT_BIN_STEP", "80"))
METEORA_DEFAULT_FEE_BPS = int(os.environ.get("METEORA_DEFAULT_FEE_BPS", "25"))
METEORA_POOL_SCRIPT = Path(__file__).resolve().parent / "scripts" / "create_dlmm_pool.cjs"
SOL_MINT = "So11111111111111111111111111111111111111112"


def _normalize_mint_pair(mint_a: str, mint_b: str) -> tuple[str, str]:
    a = mint_a.strip()
    b = mint_b.strip()
    return (a, b) if a < b else (b, a)


def get_pool_creation_cost_sol() -> float:
    return METEORA_POOL_CREATION_SOL


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
    """Live Meteora lookup for the mint pair (DLMM first, then DAMM v2)."""
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
            "meteora_url": existing.get("meteora_url") or meteora_pool_app_url(pool_address, pool_type),
            "pool": existing,
            "pool_creation_cost_sol": 0.0,
            "platform_fee_bps": METEORA_DEFAULT_FEE_BPS,
            "message": f"Meteora {label} pool found: {pool_address}",
        }

    return {
        "pool_exists": False,
        "pool_address": None,
        "pool_type": None,
        "action": "create_pool",
        "source": "meteora",
        "pool": None,
        "pool_creation_cost_sol": get_pool_creation_cost_sol(),
        "platform_fee_bps": METEORA_DEFAULT_FEE_BPS,
        "bin_step": METEORA_DEFAULT_BIN_STEP,
        "message": (
            f"No Meteora DLMM or DAMM v2 pool for this pair. DLMM creation requires "
            f"~{get_pool_creation_cost_sol()} SOL plus seed liquidity."
        ),
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
    """
    Check Meteora for an existing pool (DLMM or DAMM v2). Optionally create a DLMM pool.
    """
    existing = find_meteora_pool(token_mint, quote_mint)
    if existing and existing.get("pool_address"):
        pool_address = existing["pool_address"]
        pool_type = existing.get("pool_type") or "dlmm"
        label = "DLMM" if pool_type == "dlmm" else "DAMM v2"
        return {
            "status": "exists",
            "pool_exists": True,
            "pool_address": pool_address,
            "pool_type": pool_type,
            "source": "meteora",
            "meteora_url": existing.get("meteora_url") or meteora_pool_app_url(pool_address, pool_type),
            "pool": existing,
            "message": f"Meteora {label} pool already exists: {pool_address}",
        }

    if not create_if_missing:
        return {
            "status": "missing",
            "pool_exists": False,
            "pool_address": None,
            "source": "meteora",
            "pool_creation_cost_sol": get_pool_creation_cost_sol(),
            "message": "No Meteora pool for this pair.",
        }

    created = create_dlmm_pool(
        token_mint=token_mint,
        quote_mint=quote_mint,
        fee_bps=fee_bps or METEORA_DEFAULT_FEE_BPS,
        bin_step=bin_step,
        quote_amount=quote_amount,
        token_amount=token_amount,
    )
    if created.get("error"):
        return created

    pool_address = created.get("pool_address") or (created.get("pool") or {}).get("pool_address")
    if not pool_address:
        return {"error": "Pool creation finished but no Meteora pool address was returned.", "raw": created}

    verified = find_dlmm_pool(token_mint, quote_mint)
    if verified and verified.get("pool_address"):
        pool_address = verified["pool_address"]

    return {
        "status": created.get("status") or "created",
        "pool_exists": True,
        "pool_address": pool_address,
        "pool_type": "dlmm",
        "source": "meteora",
        "meteora_url": meteora_pool_app_url(pool_address, "dlmm"),
        "signature": created.get("signature"),
        "explorer_url": created.get("explorer_url"),
        "verified_pool": verified,
        "liquidity": created.get("liquidity") or {"status": "skipped"},
        "message": f"Meteora DLMM pool created: {pool_address}",
    }


def create_dlmm_pool(
    *,
    token_mint: str,
    quote_mint: str = SOL_MINT,
    initial_price: float = 1.0,
    bin_step: Optional[int] = None,
    fee_bps: Optional[int] = None,
    token_amount: float = 0.0,
    quote_amount: float = 0.0,
) -> dict[str, Any]:
    """
    Create a Meteora DLMM pool via the Node helper script when available.
    Falls back to a clear error if the script is not installed.
    """
    existing = find_dlmm_pool(token_mint, quote_mint)
    if existing and existing.get("pool_address"):
        return {
            "status": "exists",
            "pool_address": existing["pool_address"],
            "pool_type": "dlmm",
            "pool": existing,
            "meteora_url": existing.get("meteora_url"),
            "message": "DLMM pool already exists; reusing it.",
        }

    if not METEORA_POOL_SCRIPT.exists():
        return {
            "error": (
                "Meteora pool creation script missing. Install with: "
                "cd agent/new/scripts && npm install"
            ),
            "script": str(METEORA_POOL_SCRIPT),
        }

    payload = {
        "tokenMint": token_mint.strip(),
        "quoteMint": (quote_mint or SOL_MINT).strip(),
        "initialPrice": float(initial_price),
        "binStep": int(bin_step or METEORA_DEFAULT_BIN_STEP),
        "feeBps": int(fee_bps or METEORA_DEFAULT_FEE_BPS),
        "tokenAmount": float(token_amount),
        "quoteAmount": float(quote_amount),
    }

    try:
        proc = subprocess.run(
            ["node", str(METEORA_POOL_SCRIPT), json.dumps(payload)],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        if proc.returncode != 0:
            return {
                "error": stderr or stdout or f"Pool creation script failed ({proc.returncode})",
            }
        try:
            result = json.loads(stdout)
        except json.JSONDecodeError:
            return {"error": f"Invalid pool creation output: {stdout[:300]}"}

        if result.get("error"):
            return result

        pool_address = result.get("pool_address") or result.get("lbPair")
        if pool_address:
            time.sleep(2)
            verified = find_dlmm_pool(token_mint, quote_mint)
            return {
                "status": "created",
                "pool_address": pool_address,
                "pool_type": "dlmm",
                "signature": result.get("signature"),
                "explorer_url": result.get("explorer_url"),
                "verified_pool": verified,
                "liquidity": result.get("liquidity") or {"status": "skipped"},
                "meteora_url": meteora_pool_app_url(pool_address, "dlmm"),
                "message": f"Meteora DLMM pool created at {pool_address}.",
            }
        return {"error": "Pool creation script returned no pool address.", "raw": result}
    except FileNotFoundError:
        return {"error": "Node.js is not installed. Install Node 18+ to create Meteora pools."}
    except subprocess.TimeoutExpired:
        return {"error": "Meteora pool creation timed out after 180s."}
    except Exception as exc:
        return {"error": str(exc)}
