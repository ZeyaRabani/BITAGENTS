"""
Per-user agent wallets — Operation Multi-wallet.

Derives one Solana keypair per (user, agent) pair from a single master seed
using standard SLIP-0010 ed25519 derivation, instead of every user sharing one
pooled agent wallet. Nothing here is wired into the live deposit/withdrawal
flow yet — see agent/new/docs/per-user-wallets-scoping.md for the plan.

No private key is ever stored per user: given the master seed and a user's
assigned index (see db.get_or_create_wallet_index), the keypair is always
re-derivable on demand and never needs to be persisted.
"""

from __future__ import annotations

import base64
import os
from typing import Any, Optional

try:
    from solders.hash import Hash
    from solders.keypair import Keypair
    from solders.message import MessageV0
    from solders.pubkey import Pubkey
    from solders.transaction import VersionedTransaction

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


def get_fee_payer_keypair() -> Optional["Keypair"]:
    """One small, separate operational wallet that pays network fees for
    every sponsored transaction. It never holds user funds and never needs
    to scale with user count -- see per-user-wallets-scoping.md."""
    if not HAS_SOLDERS:
        return None
    raw = os.environ.get("MULTI_WALLET_FEE_PAYER_PRIVATE_KEY", "").strip()
    if not raw:
        return None
    import base58

    try:
        if raw.startswith("["):
            import json

            return Keypair.from_bytes(bytes(json.loads(raw)))
        return Keypair.from_bytes(base58.b58decode(raw))
    except Exception:
        return None


def build_sponsored_transaction(
    payer_keypair: "Keypair",
    authority_keypair: "Keypair",
    instructions: list,
    blockhash: "Hash",
) -> "VersionedTransaction":
    """Build and sign a transaction where `payer_keypair` covers the network
    fee but `authority_keypair` is the one authorizing the actual instructions
    (e.g. the token transfer). The two are different accounts on purpose --
    that's the entire point of fee sponsorship. Order matters: solders expects
    signers in the same order the compiled message lists required signers,
    which is payer first (it's always account index 0 in a fee-payer message).
    """
    payer_pubkey = payer_keypair.pubkey()
    msg = MessageV0.try_compile(payer_pubkey, instructions, [], blockhash)
    if authority_keypair.pubkey() == payer_pubkey:
        return VersionedTransaction(msg, [payer_keypair])
    return VersionedTransaction(msg, [payer_keypair, authority_keypair])
