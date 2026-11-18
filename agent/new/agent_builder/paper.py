"""Paper trading: run an order's real swap on mainnet state without spending anything.

The agent wallet's own Jupiter swap instructions are simulated by the cluster
(`simulateTransaction`, never broadcast). Because a paper wallet holds nothing,
the simulated transaction first moves the order's input amount, and a little SOL
for rent, into the wallet from large public holders. Signatures are not checked
in simulation, so nobody's funds can move; the result is what the swap would
have filled at this slot.
"""

from __future__ import annotations

import base64
import os
import struct
import threading
import time
from typing import Any

from dca_agent import _fetch_lookup_tables, sol_rpc

SYSTEM = "11111111111111111111111111111111"
ATA_PROGRAM = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
COMPUTE_BUDGET = "ComputeBudget111111111111111111111111111111"
SOL_FLOOR = 0.02   # the wallet is topped up to this inside the simulation
# Wallets tried as a source when a mint is too widely held for getTokenLargestAccounts (USDC).
LENDERS = [w for w in os.environ.get(
    "PAPER_LENDERS",
    "H8sMJSCQxfKiFTCfDR3DUMLPwcRbM61LGFJ8N4dK3WjS,7ANWqbfHRqRr4Y7KgZguXJXoPk3HFoWLqq6ET8e9HRmb",
).split(",") if w]
_SOURCES: dict[str, tuple[float, dict[str, Any]]] = {}
_LOCK = threading.Lock()


def _ata(owner: str, mint: str, program: str) -> str:
    from solders.pubkey import Pubkey
    pk = Pubkey.from_string
    return str(Pubkey.find_program_address([bytes(pk(owner)), bytes(pk(program)), bytes(pk(mint))], pk(ATA_PROGRAM))[0])


def _ix(program: str, accounts: list[tuple[str, bool, bool]], data: bytes) -> dict[str, Any]:
    return {"program_id": program, "data_base64": base64.b64encode(data).decode(),
            "accounts": [{"pubkey": p, "is_signer": s, "is_writable": w} for p, s, w in accounts]}


def _token_source(mint: str, raw: int) -> dict[str, Any]:
    """A token account holding at least `raw` of `mint`, and its owner."""
    with _LOCK:
        hit = _SOURCES.get(mint)
        if hit and time.time() - hit[0] < 600 and hit[1]["raw"] >= raw:
            return hit[1]
    found: list[dict[str, Any]] = []
    try:
        top = sol_rpc("getTokenLargestAccounts", [mint, {"commitment": "confirmed"}])["value"][:10]
        infos = sol_rpc("getMultipleAccounts", [[a["address"] for a in top], {"encoding": "jsonParsed"}])["value"]
        for a, info in zip(top, infos):
            parsed = info["data"]["parsed"]["info"]
            if parsed.get("state") == "initialized":
                found.append({"account": a["address"], "owner": parsed["owner"], "raw": int(a["amount"])})
    except Exception:
        for w in LENDERS:
            for acc in sol_rpc("getTokenAccountsByOwner", [w, {"mint": mint}, {"encoding": "jsonParsed"}])["value"]:
                found.append({"account": acc["pubkey"], "owner": w,
                              "raw": int(acc["account"]["data"]["parsed"]["info"]["tokenAmount"]["amount"])})
    found = [f for f in found if f["raw"] >= raw]
    if not found:
        raise RuntimeError(f"no public holder of {mint} found to lend {raw} in simulation")
    best = max(found, key=lambda f: f["raw"])
    with _LOCK:
        _SOURCES[mint] = (time.time(), best)
    return best


def _sol_source() -> str:
    for w in LENDERS:
        if sol_rpc("getBalance", [w])["value"] > 2_000_000_000:
            return w
    raise RuntimeError("no SOL lender available for simulation")


def _raw_balance(account: dict[str, Any] | None) -> int:
    if not account:
        return 0
    return int(account["data"]["parsed"]["info"]["tokenAmount"]["amount"])


def simulate_swap(*, wallet: str, swap: dict[str, Any], input_mint: str, output_mint: str, raw_in: int) -> dict[str, Any]:
    """Simulate `swap` (from market.build_swap) for `wallet` on mainnet, lending it the input first."""
    from solders.hash import Hash
    from solders.instruction import AccountMeta, Instruction
    from solders.message import MessageV0
    from solders.pubkey import Pubkey
    from solders.signature import Signature
    from solders.transaction import VersionedTransaction

    mints = sol_rpc("getMultipleAccounts", [[input_mint, output_mint], {"encoding": "jsonParsed"}])["value"]
    in_prog, out_prog = mints[0]["owner"], mints[1]["owner"]
    in_dec = int(mints[0]["data"]["parsed"]["info"]["decimals"])
    in_ata, out_ata = _ata(wallet, input_mint, in_prog), _ata(wallet, output_mint, out_prog)
    before = sol_rpc("getMultipleAccounts", [[in_ata, out_ata], {"encoding": "jsonParsed"}])["value"]
    have_in, have_out = _raw_balance(before[0]), _raw_balance(before[1])
    sol = sol_rpc("getBalance", [wallet])["value"]

    lend_raw = max(0, raw_in - have_in)
    lend_lamports = max(0, int(SOL_FLOOR * 1e9) - sol)
    sol_from = _sol_source()
    pre: list[dict[str, Any]] = [_ix(COMPUTE_BUDGET, [], b"\x02" + struct.pack("<I", 1_400_000))]
    if lend_lamports:
        pre.append(_ix(SYSTEM, [(sol_from, True, True), (wallet, False, True)], struct.pack("<IQ", 2, lend_lamports)))
    if lend_raw:
        src = _token_source(input_mint, lend_raw)
        pre.append(_ix(ATA_PROGRAM, [(sol_from, True, True), (in_ata, False, True), (wallet, False, False),
                                     (input_mint, False, False), (SYSTEM, False, False), (in_prog, False, False)], b"\x01"))
        pre.append(_ix(in_prog, [(src["account"], False, True), (input_mint, False, False), (in_ata, False, True),
                                 (src["owner"], True, False)], b"\x0c" + struct.pack("<QB", lend_raw, in_dec)))

    def to_ix(i: dict[str, Any]) -> Instruction:
        return Instruction(Pubkey.from_string(i["program_id"]), base64.b64decode(i["data_base64"]),
                           [AccountMeta(Pubkey.from_string(a["pubkey"]), a["is_signer"], a["is_writable"]) for a in i["accounts"]])

    luts = _fetch_lookup_tables(swap["lookup_table_contents"])
    msg = MessageV0.try_compile(Pubkey.from_string(sol_from), [to_ix(i) for i in [*pre, *swap["instructions"]]], luts, Hash.default())
    tx = VersionedTransaction.populate(msg, [Signature.default()] * msg.header.num_required_signatures)
    wire = bytes(tx)
    res = sol_rpc("simulateTransaction", [base64.b64encode(wire).decode(), {
        "sigVerify": False, "replaceRecentBlockhash": True, "encoding": "base64", "commitment": "confirmed",
        "accounts": {"encoding": "jsonParsed", "addresses": [in_ata, out_ata]},
    }])
    value = res["value"]
    after = value.get("accounts") or [None, None]
    ok = value.get("err") is None
    return {
        "ok": ok,
        "backend": "mainnet simulateTransaction (not broadcast)",
        "slot": res.get("context", {}).get("slot"),
        "error": None if ok else value.get("err"),
        "units_consumed": value.get("unitsConsumed"),
        "tx_bytes": len(wire),
        "lent_in_simulation": {"input_raw": lend_raw, "sol": lend_lamports / 1e9},
        "in_spent_raw": (have_in + lend_raw - _raw_balance(after[0])) if ok else 0,
        "out_received_raw": (_raw_balance(after[1]) - have_out) if ok else 0,
        "logs_tail": (value.get("logs") or [])[-6:],
    }
