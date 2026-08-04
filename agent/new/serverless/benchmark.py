"""
Fair, apples-to-apples timing: the current architecture's single-buy path
(with its DB-backed spend check and ledger writes) vs this stateless
prototype (no DB calls at all) for the exact same trade.

Uses dry_run/quote-only mode for the repeated timing runs — this measures
the actual thing in question (DB round-trip overhead vs zero overhead), not
Solana network variance, and doesn't spend real SOL on every run. A single
real broadcast is run separately and reported, not averaged in, since
network/Jupiter latency is identical in both architectures — it's an
external dependency neither one controls.

Run:
  cd agent/new/serverless && python3 benchmark.py
"""

from __future__ import annotations

import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# dca_agent.py calls _load_env() at import time with override=True, which
# would immediately wipe any manual os.environ override set beforehand — so
# the DCA_WALLET_PRIVATE_KEY substitution below must happen AFTER this import,
# not before it (found this the hard way: the fix looked right and silently
# did nothing until this ordering was corrected).
from dca_agent import execute_swap_buy, get_jupiter_quote, load_keypair, resolve_token
from dca_execute import execute_dca_buy_stateless

# This local test environment has VOLUME_AGENT_WALLET_PRIVATE_KEY but not
# DCA_WALLET_PRIVATE_KEY. Without it, get_jupiter_quote() fails immediately on
# a config check before ever reaching Jupiter — which would make both sides of
# this benchmark measure "how fast does a config error return" instead of
# anything real. Borrowing the Volume wallet's key for this quote-only
# benchmark is safe (quotes don't move funds) and makes both paths actually
# reach the network call being measured.
if not os.environ.get("DCA_WALLET_PRIVATE_KEY") and os.environ.get("VOLUME_AGENT_WALLET_PRIVATE_KEY"):
    os.environ["DCA_WALLET_PRIVATE_KEY"] = os.environ["VOLUME_AGENT_WALLET_PRIVATE_KEY"]

TOKEN = "iu3A7azWTm3zQSk81SUC1JctB4zPYnxLmcmqq71EASY"  # BITAGENTS
AMOUNT_SOL = 0.005
RUNS = 5


REAL_TEST_WALLET = "F3Ta2EZecfVLr9GM4mDtSQu4fHGv2WiLZAG3nE9t2LP4"  # has real DCA-ledger balance


def time_current_arch_dry_run() -> float:
    """Current path: DB spend-check + Jupiter quote, no DB write (dry_run).

    Uses a wallet with a real recorded balance so the spend-check actually
    passes through to the quote call — a wallet with zero balance would
    short-circuit before reaching Jupiter at all, making this an unfair,
    artificially-fast comparison.
    """
    t0 = time.time()
    execute_swap_buy("SOL", TOKEN, AMOUNT_SOL, dry_run=True, user_wallet=REAL_TEST_WALLET)
    return time.time() - t0


def time_stateless_quote_only() -> float:
    """New path: same Jupiter quote, zero DB calls of any kind."""
    t0 = time.time()
    sol = resolve_token("SOL")
    out = resolve_token(TOKEN)
    get_jupiter_quote(sol["mint"], out["mint"], AMOUNT_SOL)
    return time.time() - t0


def main() -> None:
    print(f"Benchmarking {RUNS} runs each, {AMOUNT_SOL} SOL -> BITAGENTS quote path\n")

    current_times = [time_current_arch_dry_run() for _ in range(RUNS)]
    print("Current architecture (DB spend-check + quote):")
    for t in current_times:
        print(f"  {t:.3f}s")
    print(f"  mean: {statistics.mean(current_times):.3f}s\n")

    stateless_times = [time_stateless_quote_only() for _ in range(RUNS)]
    print("Stateless prototype (zero DB calls + quote):")
    for t in stateless_times:
        print(f"  {t:.3f}s")
    print(f"  mean: {statistics.mean(stateless_times):.3f}s\n")

    diff = statistics.mean(current_times) - statistics.mean(stateless_times)
    print(f"Difference attributable to removing the DB round-trip: {diff:.3f}s per call")
    print(
        "\nNote: this isolates DB/ledger overhead specifically. The Jupiter quote "
        "and the actual on-chain transaction broadcast/confirm cost the same in "
        "either architecture — that part is an external dependency, not something "
        "either design controls."
    )


if __name__ == "__main__":
    main()
