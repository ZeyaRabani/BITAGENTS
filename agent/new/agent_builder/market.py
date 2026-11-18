"""Chain and venue access for strategies: holdings, token lookup, unsigned swaps.

Nothing here signs. `build_swap` returns Jupiter's instructions for a payer the
caller names (the user's Aomi agent wallet); Aomi stages, simulates and signs them.
"""

from __future__ import annotations

import base64
import threading
import time
from typing import Any

from dca_agent import (
    JUPITER_BUILD_API,
    JUPITER_TOKENS_API,
    TOKEN_MINTS,
    _fetch_lookup_tables,
    _jupiter_get,
    _to_instruction,
    _unsigned_versioned_tx_b64,
    sol_rpc,
)

from .contract import Holding

TOKEN_PROGRAMS = (
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
)
USDC = TOKEN_MINTS["USDC"]
_TOKENS: dict[str, tuple[float, dict[str, Any]]] = {}
_LOCK = threading.Lock()


def resolve_xstock(symbol: str) -> dict[str, Any]:
    """NVDA -> the verified NVDAx mint, from Jupiter's token search."""
    want = f"{symbol.upper()}x"
    with _LOCK:
        hit = _TOKENS.get(want)
        if hit and time.time() - hit[0] < 3600:
            return hit[1]
    resp = _jupiter_get(f"{JUPITER_TOKENS_API}/search", {"query": want})
    if not resp.ok:
        return {"error": f"Jupiter token search failed ({resp.status_code})"}
    for t in resp.json():
        if t.get("symbol") == want and t.get("isVerified"):
            out = {"symbol": want, "mint": t["id"], "decimals": int(t["decimals"]),
                   "name": t.get("name"), "usd_price": t.get("usdPrice"), "icon": t.get("icon")}
            with _LOCK:
                _TOKENS[want] = (time.time(), out)
            return out
    return {"error": f"no verified {want} token on Jupiter"}


_LIVE: dict[str, tuple[float, dict[str, Any]]] = {}


def xstock_live(symbol: str) -> dict[str, Any]:
    """The verified xStock for a ticker with its current price and percent change over 5, 60, 360 and 1440 minutes."""
    want = f"{symbol.upper()}x"
    with _LOCK:
        hit = _LIVE.get(want)
        if hit and time.time() - hit[0] < 20:
            return hit[1]
    resp = None
    for wait in (0, 1.5, 4):
        time.sleep(wait)
        resp = _jupiter_get(f"{JUPITER_TOKENS_API}/search", {"query": want})
        if resp.ok:
            break
    if not resp.ok:
        return {"error": f"Jupiter token search failed ({resp.status_code})"}
    for t in resp.json():
        if t.get("symbol") == want and t.get("isVerified"):
            out = {"symbol": want, "mint": t["id"], "decimals": int(t["decimals"]), "name": t.get("name"),
                   "usd_price": t.get("usdPrice"), "icon": t.get("icon"),
                   "change_pct": {m: (t.get(k) or {}).get("priceChange")
                                  for m, k in ((5, "stats5m"), (60, "stats1h"), (360, "stats6h"), (1440, "stats24h"))}}
            with _LOCK:
                _LIVE[want] = (time.time(), out)
                _TOKENS[want] = (time.time(), {k: v for k, v in out.items() if k != "change_pct"})
            return out
    return {"error": f"no verified {want} token on Jupiter"}


def holdings(wallet: str) -> tuple[list[Holding], float]:
    """SPL balances of `wallet`, and its SOL balance."""
    out: list[Holding] = []
    for program in TOKEN_PROGRAMS:
        res = sol_rpc("getTokenAccountsByOwner", [wallet, {"programId": program}, {"encoding": "jsonParsed"}])
        for acc in res["value"]:
            info = acc["account"]["data"]["parsed"]["info"]
            amt = info["tokenAmount"]
            if int(amt["amount"]) == 0:
                continue
            out.append(Holding(mint=info["mint"], symbol="", amount=float(amt["uiAmountString"]), decimals=int(amt["decimals"])))
    return out, sol_rpc("getBalance", [wallet])["value"] / 1e9


def price_holdings(items: list[Holding]) -> None:
    """Fill symbol and USD value from Jupiter, in place."""
    if not items:
        return
    resp = _jupiter_get(f"{JUPITER_TOKENS_API}/search", {"query": ",".join(h.mint for h in items[:100])})
    if not resp.ok:
        return
    by_mint = {t["id"]: t for t in resp.json()}
    for h in items:
        t = by_mint.get(h.mint)
        if t:
            h.symbol = t.get("symbol") or ""
            if t.get("usdPrice") is not None:
                h.value_usd = h.amount * float(t["usdPrice"])


def build_swap(*, payer: str, input_mint: str, output_mint: str, raw_amount: int, slippage_bps: int) -> dict[str, Any]:
    """Unsigned Jupiter swap for `payer`: instruction list, lookup tables, and the same thing as one tx."""
    from solders.message import MessageV0
    from solders.hash import Hash
    from solders.pubkey import Pubkey

    resp = _jupiter_get(JUPITER_BUILD_API, {
        "inputMint": input_mint, "outputMint": output_mint, "amount": str(raw_amount),
        "taker": payer, "payer": payer, "slippageBps": str(slippage_bps),
        "wrapAndUnwrapSol": "true", "computeUnitPricePercentile": "high", "maxAccounts": "54",
    })
    if not resp.ok:
        raise RuntimeError(f"Jupiter build failed ({resp.status_code}): {resp.text[:300]}")
    b = resp.json()
    raw = [*(b.get("computeBudgetInstructions") or []), *(b.get("setupInstructions") or []), b["swapInstruction"]]
    if b.get("cleanupInstruction"):
        raw.append(b["cleanupInstruction"])
    raw += b.get("otherInstructions") or []

    luts = _fetch_lookup_tables(b.get("addressesByLookupTableAddress"))
    bh = sol_rpc("getLatestBlockhash", [{"commitment": "confirmed"}])
    msg = MessageV0.try_compile(Pubkey.from_string(payer), [_to_instruction(i) for i in raw], luts,
                                Hash.from_string(bh["value"]["blockhash"]))
    tx_b64 = _unsigned_versioned_tx_b64(msg)
    return {
        "payer": payer,
        "in_amount": b.get("inAmount"), "out_amount": b.get("outAmount"),
        "other_amount_threshold": b.get("otherAmountThreshold"),
        "price_impact_pct": b.get("priceImpactPct"), "slippage_bps": slippage_bps,
        # Shape of Aomi's svm_stage_ix. The compute-budget instructions are left to Aomi's commit.
        "instructions": [
            {"program_id": i["programId"],
             "accounts": [{"pubkey": a["pubkey"], "is_signer": a["isSigner"], "is_writable": a["isWritable"]} for a in i["accounts"]],
             "data_base64": i["data"]}
            for i in raw if i["programId"] != "ComputeBudget111111111111111111111111111111"
        ],
        "address_lookup_tables": list((b.get("addressesByLookupTableAddress") or {}).keys()),
        "lookup_table_contents": b.get("addressesByLookupTableAddress") or {},
        "unsigned_tx_base64": tx_b64,
        "tx_bytes": len(base64.b64decode(tx_b64)),
    }
