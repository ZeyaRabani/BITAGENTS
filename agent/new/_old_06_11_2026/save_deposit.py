"""Build a Save SOL lending deposit for the Circle yield wallet.

Save has no hosted deposit-transaction API. This module builds the same
Solend instructions the live main pool uses, and the caller signs them with Circle.
"""

from __future__ import annotations

import struct
from typing import Any

from solders.instruction import AccountMeta, Instruction
from solders.pubkey import Pubkey
from solders.system_program import TransferParams, transfer

SAVE_PROGRAM_ID = Pubkey.from_string("So1endDq2YkqhipRh3WViPa8hdiSpxWy6z3Z6tMCpAo")
WSOL_MINT = Pubkey.from_string("So11111111111111111111111111111111111111112")
TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
COMPUTE_BUDGET_PROGRAM_ID = Pubkey.from_string("ComputeBudget111111111111111111111111111111")

# Save main pool SOL reserve. Addresses come from https://api.save.finance.
LENDING_MARKET = Pubkey.from_string("4UpD2fh7xH3VP9QQaXtsS1YY3bxzWhtfpks7FatyKvdY")
SOL_RESERVE = Pubkey.from_string("8PbodeaosQP19SjYFx855UMqWxH2HynZLdBXmsrbac36")
RESERVE_LIQUIDITY_SUPPLY = Pubkey.from_string("8UviNr47S8eL6J3WfDxMRa3hvLta1VDJwNWqsDgtN3Cv")
COLLATERAL_MINT = Pubkey.from_string("5h6ssFpeDeRbzsEHDbTQNH7nVGgsKrZydxdSTnLm6QdV")
PYTH_ORACLE = Pubkey.from_string("7UVimffxr9ow1uXYxsr4LHAcV58mLzhmwaeKvJ1pjLiE")
SWITCHBOARD_ORACLE = Pubkey.from_string("GvDMxPzN1sCj7L26YDK2HnMRXEQmQ2aemov8YBtPS7vR")

TOKEN_ACCOUNT_SIZE = 165
COMPUTE_UNIT_LIMIT = 400_000
COMPUTE_UNIT_PRICE = 10_000


def _market_authority() -> Pubkey:
    address, _bump = Pubkey.find_program_address([bytes(LENDING_MARKET)], SAVE_PROGRAM_ID)
    return address


def _account_exists(address: str) -> bool:
    from dca_agent import sol_rpc

    info = sol_rpc("getAccountInfo", [address, {"encoding": "base64"}])
    return bool((info or {}).get("value"))


def _rent_lamports(size: int) -> int:
    from dca_agent import _rpc_u64, sol_rpc

    return _rpc_u64(sol_rpc("getMinimumBalanceForRentExemption", [int(size)]))


def _compute_budget_instructions() -> list[Instruction]:
    return [
        Instruction(
            COMPUTE_BUDGET_PROGRAM_ID,
            bytes([2]) + struct.pack("<I", COMPUTE_UNIT_LIMIT),
            [],
        ),
        Instruction(
            COMPUTE_BUDGET_PROGRAM_ID,
            bytes([3]) + struct.pack("<Q", COMPUTE_UNIT_PRICE),
            [],
        ),
    ]


def _sync_native_instruction(token_account: Pubkey) -> Instruction:
    return Instruction(
        TOKEN_PROGRAM_ID,
        bytes([17]),
        [AccountMeta(token_account, False, True)],
    )


def _refresh_reserve_instruction() -> Instruction:
    # Live main-pool refreshes pass the reserve and its two oracles. Clock is not included.
    return Instruction(
        SAVE_PROGRAM_ID,
        bytes([3]),
        [
            AccountMeta(SOL_RESERVE, False, True),
            AccountMeta(PYTH_ORACLE, False, False),
            AccountMeta(SWITCHBOARD_ORACLE, False, False),
        ],
    )


def _deposit_instruction(
    source_liquidity: Pubkey,
    destination_collateral: Pubkey,
    authority: Pubkey,
    amount_lamports: int,
) -> Instruction:
    return Instruction(
        SAVE_PROGRAM_ID,
        bytes([4]) + struct.pack("<Q", int(amount_lamports)),
        [
            AccountMeta(source_liquidity, False, True),
            AccountMeta(destination_collateral, False, True),
            AccountMeta(SOL_RESERVE, False, True),
            AccountMeta(RESERVE_LIQUIDITY_SUPPLY, False, True),
            AccountMeta(COLLATERAL_MINT, False, True),
            AccountMeta(LENDING_MARKET, False, False),
            AccountMeta(_market_authority(), False, False),
            AccountMeta(authority, True, False),
            AccountMeta(TOKEN_PROGRAM_ID, False, False),
        ],
    )


def prepare_save_sol_deposit(authority_address: str, amount_sol: float) -> dict[str, Any]:
    """Return unsigned instructions that wrap SOL and deposit it into Save's main SOL reserve."""
    from dca_agent import _associated_token_address, _create_ata_instruction

    try:
        authority = Pubkey.from_string(authority_address)
    except Exception:
        return {"error": "Yield wallet address is not a valid Solana public key."}
    lamports = int(round(float(amount_sol) * 1_000_000_000))
    if lamports <= 0:
        return {"error": "Save deposit amount is too small."}

    wsol_ata = _associated_token_address(authority, WSOL_MINT, str(TOKEN_PROGRAM_ID))
    collateral_ata = _associated_token_address(authority, COLLATERAL_MINT, str(TOKEN_PROGRAM_ID))
    extra = 0
    if not _account_exists(str(wsol_ata)):
        extra += _rent_lamports(TOKEN_ACCOUNT_SIZE)
    if not _account_exists(str(collateral_ata)):
        extra += _rent_lamports(TOKEN_ACCOUNT_SIZE)

    instructions: list[Instruction] = list(_compute_budget_instructions())
    instructions.append(
        _create_ata_instruction(authority, authority, WSOL_MINT, str(TOKEN_PROGRAM_ID), idempotent=True)
    )
    instructions.append(transfer(TransferParams(from_pubkey=authority, to_pubkey=wsol_ata, lamports=lamports)))
    instructions.append(_sync_native_instruction(wsol_ata))
    instructions.append(
        _create_ata_instruction(
            authority,
            authority,
            COLLATERAL_MINT,
            str(TOKEN_PROGRAM_ID),
            idempotent=True,
        )
    )
    instructions.append(_refresh_reserve_instruction())
    instructions.append(
        _deposit_instruction(wsol_ata, collateral_ata, authority, lamports)
    )
    return {
        "instructions": instructions,
        "extra_lamports": extra,
        "collateral_mint": str(COLLATERAL_MINT),
        "reserve": str(SOL_RESERVE),
    }
