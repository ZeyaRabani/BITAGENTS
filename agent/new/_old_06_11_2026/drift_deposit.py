"""Build a Drift SOL lending deposit for the Circle yield wallet.

Drift has no REST transaction API. This module derives the spot-market accounts
and instructions in-process, then the caller signs them with Circle.
"""

from __future__ import annotations

import base64
import hashlib
import struct
from typing import Any

from solders.instruction import AccountMeta, Instruction
from solders.pubkey import Pubkey
from solders.system_program import TransferParams, transfer

DRIFT_PROGRAM_ID = Pubkey.from_string("dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH")
WSOL_MINT = Pubkey.from_string("So11111111111111111111111111111111111111112")
TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
RENT_SYSVAR = Pubkey.from_string("SysvarRent111111111111111111111111111111111")
SYSTEM_PROGRAM_ID = Pubkey.from_string("11111111111111111111111111111111")
COMPUTE_BUDGET_PROGRAM_ID = Pubkey.from_string("ComputeBudget111111111111111111111111111111")

SOL_SPOT_MARKET_INDEX = 1
USER_ACCOUNT_SIZE = 4376
USER_STATS_ACCOUNT_SIZE = 240
TOKEN_ACCOUNT_SIZE = 165
COMPUTE_UNIT_LIMIT = 600_000
COMPUTE_UNIT_PRICE = 10_000


def _anchor_discriminator(name: str) -> bytes:
    return hashlib.sha256(f"global:{name}".encode()).digest()[:8]


def _pda(*seeds: bytes) -> Pubkey:
    address, _bump = Pubkey.find_program_address(list(seeds), DRIFT_PROGRAM_ID)
    return address


def _u16(value: int) -> bytes:
    return int(value).to_bytes(2, "little")


def _account_data(address: str) -> bytes | None:
    from dca_agent import sol_rpc

    info = sol_rpc("getAccountInfo", [address, {"encoding": "base64"}])
    value = (info or {}).get("value") if isinstance(info, dict) else None
    if not value:
        return None
    data = value.get("data")
    if not isinstance(data, list) or not data:
        return None
    return base64.b64decode(data[0])


def _rent_lamports(size: int) -> int:
    from dca_agent import _rpc_u64, sol_rpc

    return _rpc_u64(sol_rpc("getMinimumBalanceForRentExemption", [int(size)]))


def _compute_budget_instructions() -> list[Instruction]:
    limit = Instruction(
        COMPUTE_BUDGET_PROGRAM_ID,
        bytes([2]) + struct.pack("<I", COMPUTE_UNIT_LIMIT),
        [],
    )
    price = Instruction(
        COMPUTE_BUDGET_PROGRAM_ID,
        bytes([3]) + struct.pack("<Q", COMPUTE_UNIT_PRICE),
        [],
    )
    return [limit, price]


def _sync_native_instruction(token_account: Pubkey) -> Instruction:
    return Instruction(
        TOKEN_PROGRAM_ID,
        bytes([17]),
        [AccountMeta(token_account, False, True)],
    )


def _initialize_user_stats_instruction(
    user_stats: Pubkey,
    state: Pubkey,
    authority: Pubkey,
) -> Instruction:
    return Instruction(
        DRIFT_PROGRAM_ID,
        _anchor_discriminator("initialize_user_stats"),
        [
            AccountMeta(user_stats, False, True),
            AccountMeta(state, False, True),
            AccountMeta(authority, False, False),
            AccountMeta(authority, True, True),
            AccountMeta(RENT_SYSVAR, False, False),
            AccountMeta(SYSTEM_PROGRAM_ID, False, False),
        ],
    )


def _initialize_user_instruction(
    user: Pubkey,
    user_stats: Pubkey,
    state: Pubkey,
    authority: Pubkey,
    sub_account_id: int = 0,
) -> Instruction:
    data = _anchor_discriminator("initialize_user") + _u16(sub_account_id) + bytes(32)
    return Instruction(
        DRIFT_PROGRAM_ID,
        data,
        [
            AccountMeta(user, False, True),
            AccountMeta(user_stats, False, True),
            AccountMeta(state, False, True),
            AccountMeta(authority, False, False),
            AccountMeta(authority, True, True),
            AccountMeta(RENT_SYSVAR, False, False),
            AccountMeta(SYSTEM_PROGRAM_ID, False, False),
        ],
    )


def _deposit_instruction(
    *,
    state: Pubkey,
    user: Pubkey,
    user_stats: Pubkey,
    authority: Pubkey,
    vault: Pubkey,
    user_token_account: Pubkey,
    market_index: int,
    amount_lamports: int,
) -> Instruction:
    data = (
        _anchor_discriminator("deposit")
        + _u16(market_index)
        + struct.pack("<Q", int(amount_lamports))
        + bytes([0])
    )
    return Instruction(
        DRIFT_PROGRAM_ID,
        data,
        [
            AccountMeta(state, False, False),
            AccountMeta(user, False, True),
            AccountMeta(user_stats, False, True),
            AccountMeta(authority, True, False),
            AccountMeta(vault, False, True),
            AccountMeta(user_token_account, False, True),
            AccountMeta(TOKEN_PROGRAM_ID, False, False),
        ],
    )


def prepare_drift_sol_deposit(authority_address: str, amount_sol: float) -> dict[str, Any]:
    """Return unsigned instructions for a SOL spot deposit, plus rent the first account needs."""
    from dca_agent import _associated_token_address, _create_ata_instruction

    try:
        authority = Pubkey.from_string(authority_address)
    except Exception:
        return {"error": "Yield wallet address is not a valid Solana public key."}
    lamports = int(round(float(amount_sol) * 1_000_000_000))
    if lamports <= 0:
        return {"error": "Drift deposit amount is too small."}

    state = _pda(b"drift_state")
    user_stats = _pda(b"user_stats", bytes(authority))
    user = _pda(b"user", bytes(authority), _u16(0))
    spot_market = _pda(b"spot_market", _u16(SOL_SPOT_MARKET_INDEX))
    market_raw = _account_data(str(spot_market))
    if not market_raw or len(market_raw) < 136:
        return {"error": "Could not read the Drift SOL spot market."}
    mint = Pubkey.from_bytes(market_raw[72:104])
    vault = Pubkey.from_bytes(market_raw[104:136])
    if mint != WSOL_MINT:
        return {"error": "Drift spot market 1 is not the SOL market."}
    if _account_data(str(vault)) is None:
        return {"error": "Drift SOL vault account was not found."}

    ata = _associated_token_address(authority, WSOL_MINT, str(TOKEN_PROGRAM_ID))
    user_exists = _account_data(str(user)) is not None
    stats_exist = _account_data(str(user_stats)) is not None
    ata_exists = _account_data(str(ata)) is not None

    extra = 0
    if not stats_exist:
        extra += _rent_lamports(USER_STATS_ACCOUNT_SIZE)
    if not user_exists:
        extra += _rent_lamports(USER_ACCOUNT_SIZE)
    if not ata_exists:
        extra += _rent_lamports(TOKEN_ACCOUNT_SIZE)

    instructions: list[Instruction] = list(_compute_budget_instructions())
    instructions.append(
        _create_ata_instruction(
            authority,
            authority,
            WSOL_MINT,
            str(TOKEN_PROGRAM_ID),
            idempotent=True,
        )
    )
    instructions.append(transfer(TransferParams(from_pubkey=authority, to_pubkey=ata, lamports=lamports)))
    instructions.append(_sync_native_instruction(ata))
    if not stats_exist:
        instructions.append(_initialize_user_stats_instruction(user_stats, state, authority))
    if not user_exists:
        instructions.append(_initialize_user_instruction(user, user_stats, state, authority))
    instructions.append(
        _deposit_instruction(
            state=state,
            user=user,
            user_stats=user_stats,
            authority=authority,
            vault=vault,
            user_token_account=ata,
            market_index=SOL_SPOT_MARKET_INDEX,
            amount_lamports=lamports,
        )
    )
    return {
        "instructions": instructions,
        "extra_lamports": extra,
        "user_exists": user_exists,
        "spot_market": str(spot_market),
        "user": str(user),
    }
