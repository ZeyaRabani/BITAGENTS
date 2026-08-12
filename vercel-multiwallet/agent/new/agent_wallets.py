"""
Per-user agent wallets — Operation Multi-wallet.

Derives one Solana keypair per (user, agent) pair from a single master seed
using standard SLIP-0010 ed25519 derivation, instead of every user sharing one
pooled agent wallet. Nothing here is wired into the live deposit/withdrawal
flow yet — see agent/new/docs/per-user-wallets-scoping.md for the plan.

No private key is ever stored per user: given the master seed and a user's
assigned index (see db.get_or_create_wallet_index), the keypair is always
re-derivable on demand and never needs to be persisted.

No fee-payer wallet: each user's derived wallet pays its own network fees
out of its own SOL balance, same as any ordinary Solana wallet. That means a
wallet needs some SOL in it before it can do anything — a hard requirement,
communicated to the user up front, not something the platform silently
covers for them. See MIN_SOL_TO_ACTIVATE_LAMPORTS below.
"""

from __future__ import annotations

import base64
import os
from typing import Optional

try:
    from solders.keypair import Keypair

    HAS_SOLDERS = True
except ImportError:
    HAS_SOLDERS = False

from db import get_or_create_wallet_index

# Solana's registered SLIP-44 coin type. Same convention Phantom/Solflare use,
# so a derived wallet here is a completely ordinary Solana wallet -- nothing
# about it is BITAGENTS-specific except which seed generated it.
_SOLANA_SLIP44_COIN_TYPE = 501

# One slot per agent under the same master seed, so a bug touching one agent's
# wallet handling can't reach another agent's funds for the same user.
_AGENT_SLOTS = {"dca": 0, "volume": 1, "easya": 2}

# What we tell the user they need to deposit before their wallet can do
# anything. A single signature costs 5,000 lamports on Solana today -- this
# is deliberately higher than that bare minimum so a wallet can cover a few
# real operations (not just exactly one) before running dry. Every action
# that spends from a user's wallet must always leave at least one fee's
# worth of SOL behind for whichever transaction spends it -- "withdraw all"
# means "all except the fee for this transaction," never literally zero.
MIN_SOL_TO_ACTIVATE_LAMPORTS = int(
    os.environ.get("MULTI_WALLET_MIN_SOL_LAMPORTS", "1000000")  # 0.001 SOL
)
SOLANA_BASE_FEE_LAMPORTS = 5000


def _load_seed_from_env(env_var: str) -> Optional[bytes]:
    """A master seed is 32-64 raw bytes, provided base64-encoded in the env
    (analogous to how DCA_WALLET_PRIVATE_KEY is base58-encoded today)."""
    raw = os.environ.get(env_var, "").strip()
    if not raw:
        return None
    try:
        seed = base64.b64decode(raw)
    except Exception:
        return None
    if len(seed) < 32:
        return None
    return seed


def get_master_seed() -> Optional[bytes]:
    """MULTI_WALLET_MASTER_SEED is intentionally separate from every other
    wallet env var in this codebase -- it must never be reused for anything
    else, since it can derive every user's wallet across every agent."""
    return _load_seed_from_env("MULTI_WALLET_MASTER_SEED")


def multi_wallet_configured() -> bool:
    return HAS_SOLDERS and get_master_seed() is not None


def derive_user_keypair(master_seed: bytes, agent: str, wallet_index: int) -> "Keypair":
    """Deterministic: the same (seed, agent, index) always yields the same
    keypair. Different agent -> different wallet for the same user. Different
    wallet_index -> different wallet for a different user. Never store the
    result -- re-derive it each time it's needed."""
    if agent not in _AGENT_SLOTS:
        raise ValueError(f"Unknown agent '{agent}'. Expected one of {sorted(_AGENT_SLOTS)}.")
    if wallet_index < 0:
        raise ValueError("wallet_index must be non-negative.")
    agent_slot = _AGENT_SLOTS[agent]
    path = f"m/44'/{_SOLANA_SLIP44_COIN_TYPE}'/{agent_slot}'/{wallet_index}'"
    return Keypair.from_seed_and_derivation_path(master_seed, path)


def get_user_wallet_keypair(agent: str, user_wallet: str) -> "Keypair":
    """The main entry point: given a user's connected wallet address and
    which agent this is for, return their dedicated derived keypair,
    assigning them an index on first use if they don't have one yet."""
    seed = get_master_seed()
    if not seed:
        raise RuntimeError("MULTI_WALLET_MASTER_SEED is not configured on the server.")
    wallet_index = get_or_create_wallet_index(user_wallet.strip())
    return derive_user_keypair(seed, agent, wallet_index)


def get_user_wallet_pubkey(agent: str, user_wallet: str) -> str:
    return str(get_user_wallet_keypair(agent, user_wallet).pubkey())


def max_spendable_lamports(current_balance_lamports: int) -> int:
    """How much of a wallet's SOL balance can actually be sent/withdrawn right
    now, reserving enough for this transaction's own fee. Applies whether
    the wallet holds SOL as the asset being moved (spending SOL itself) or
    just needs SOL to cover the fee for moving some other token."""
    return max(0, current_balance_lamports - SOLANA_BASE_FEE_LAMPORTS)


def is_wallet_active(balance_lamports: int) -> bool:
    """Whether this wallet has enough SOL to do anything at all yet."""
    return balance_lamports >= MIN_SOL_TO_ACTIVATE_LAMPORTS
