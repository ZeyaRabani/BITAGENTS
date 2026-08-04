"""
Stateless DCA buy execution — Ruqaiyah's proposal, built literally.

From the Aug 3 "Serverless Migration" meeting: "You only need to pass three
variables into a serverless function... you're not relying on a database...
you should see a speed increase like massively."

This is that function: token, amount, slippage in — a signed Solana
transaction out. No database read, no database write, no ledger, no
session state, no in-process scheduler. It reuses the exact proven
Jupiter swap logic from dca_agent.py (_build_and_execute_swap) — this is
not a reimplementation of the trading logic, only the surrounding
architecture is different.

Deliberately does NOT do: spend-limit checks against a user's deposited
balance, or record the trade to a ledger. Those need persistent state by
definition (you can't know a running balance without remembering it
somewhere) — this file exists to isolate and measure the execution path
Ruqa was actually describing, not to replace the ledger.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dca_agent import (
    HAS_SOLDERS,
    _build_and_execute_swap,
    _is_mainnet,
    _lamports,
    load_keypair,
    resolve_token,
)


def execute_dca_buy_stateless(token: str, amount_sol: float, slippage_bps: int = 100) -> dict[str, Any]:
    """The three variables: token, amount, slippage. Nothing else in, nothing persisted."""
    if not _is_mainnet():
        return {"error": "This prototype targets mainnet execution only (matches the real DCA path)."}

    keypair = load_keypair()
    if not keypair:
        return {"error": "No wallet keypair. Set DCA_WALLET_PRIVATE_KEY."}
    if not HAS_SOLDERS:
        return {"error": "Install solders + base58: pip install solders base58"}

    sol = resolve_token("SOL")
    out = resolve_token(token)
    if "error" in out:
        return out

    wallet_pubkey = str(keypair.pubkey())
    raw_amount = _lamports(float(amount_sol), sol["decimals"])

    return _build_and_execute_swap(
        sol["mint"], out["mint"], raw_amount, wallet_pubkey, keypair, int(slippage_bps)
    )
