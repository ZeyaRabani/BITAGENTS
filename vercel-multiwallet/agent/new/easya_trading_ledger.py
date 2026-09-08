"""
Per-user deposit ledger for the EasyA Analysis Agent trading wallet.

Balances are scoped to EASYA_ANALYSIS_AGENT_WALLET_PRIVATE_KEY (separate from DCA).
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from db import deposit_exists, find_deposit_by_signature, get_conn, init_db, insert_ledger_entry, load_ledger_for_user
from deposit_ledger import (
    _ledger_lock,
    _parse_verified_user_deposits,
    _user_in_transaction,
    _valid_signature,
    user_token_withdraw_lock,
)
from dca_agent import SOLANA_CLUSTER, SOLANA_RPC, resolve_token, sol_rpc

EASYA_PLATFORM_FEE_RATE = 0.001  # 0.1%


def load_easya_keypair():
    from dca_agent import HAS_SOLDERS, Keypair

    if not HAS_SOLDERS:
        return None
    raw = (
        os.environ.get("EASYA_ANALYSIS_AGENT_WALLET_PRIVATE_KEY", "").strip()
        or os.environ.get("EASYA_AGENT_WALLET_PRIVATE_KEY", "").strip()
    )
    if not raw:
        return None
    try:
        import base58

        if raw.startswith("["):
            return Keypair.from_bytes(bytes(json.loads(raw)))
        return Keypair.from_bytes(base58.b58decode(raw))
    except Exception:
        return None


def get_easya_wallet_pubkey() -> Optional[str]:
    kp = load_easya_keypair()
    return str(kp.pubkey()) if kp else None


def easya_platform_fee(swap_amount: float) -> float:
    amount = float(swap_amount)
    if amount <= 0:
        return 0.0
    return round(amount * EASYA_PLATFORM_FEE_RATE, 12)


def easya_execution_total_cost(swap_amount: float) -> float:
    amount = float(swap_amount)
    return round(amount + easya_platform_fee(amount), 12)


def _easya_rows(user_wallet: str) -> list[dict[str, Any]]:
    agent_wallet = get_easya_wallet_pubkey()
    if not agent_wallet:
        return []
    rows = load_ledger_for_user(user_wallet.strip())
    return [r for r in rows if r.get("agent_wallet") == agent_wallet]


def _ledger_totals(user_wallet: str, token_symbol: str, rows: list[dict[str, Any]]) -> dict[str, float]:
    token_symbol = token_symbol.strip().upper()
    deposited = spent = acquired = withdrawn = 0.0
    for row in rows:
        if row.get("status") != "confirmed":
            continue
        if str(row.get("token", "")).upper() != token_symbol:
            continue
        amount = float(row.get("amount") or 0)
        direction = row.get("direction", "deposit")
        if direction == "deposit":
            deposited += amount
        elif direction == "spend":
            spent += amount
        elif direction == "acquire":
            acquired += amount
        elif direction == "withdraw":
            withdrawn += amount
    return {
        "deposited": round(deposited, 9),
        "spent_ledger": round(spent, 9),
        "acquired": round(acquired, 9),
        "withdrawn": round(withdrawn, 9),
    }


def _reserved_for_orders(user_wallet: str, token_symbol: str) -> float:
    token_symbol = token_symbol.strip().upper()
    init_db()
    reserved = 0.0
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT amount_input FROM easya_orders
                WHERE user_wallet = %s AND status IN ('pending', 'active')
                  AND UPPER(input_token) = %s
                """,
                (user_wallet.strip(), token_symbol),
            )
            for row in cur.fetchall():
                reserved += easya_execution_total_cost(float(row["amount_input"] or 0))
    return round(reserved, 9)


def get_easya_agent_wallet_info() -> dict[str, Any]:
    from dca_agent import TOKEN_MINTS

    wallet = get_easya_wallet_pubkey()
    return {
        "agent_wallet": wallet,
        "configured": bool(wallet),
        "any_spl_token": True,
        "token_resolution": "symbol_or_mint",
        "common_tokens": sorted(k for k in TOKEN_MINTS if k != "WSOL"),
        "storage": "neon_postgres",
        "cluster": SOLANA_CLUSTER,
        "rpc_url": SOLANA_RPC,
        "platform_fee_rate": EASYA_PLATFORM_FEE_RATE,
        "platform_fee_pct": "0.1%",
    }


def get_easya_user_balances(user_wallet: str) -> dict[str, Any]:
    user_wallet = user_wallet.strip()
    rows = _easya_rows(user_wallet)
    tokens: set[str] = set()
    for row in rows:
        if row.get("status") == "confirmed":
            tokens.add(str(row.get("token", "SOL")))

    breakdown = []
    for token in sorted(tokens):
        ledger = _ledger_totals(user_wallet, token, rows)
        reserved = _reserved_for_orders(user_wallet, token)
        spent = ledger["spent_ledger"]
        available = round(max(ledger["deposited"] - spent - reserved, 0.0), 9)
        withdrawable = round(
            max(ledger["deposited"] + ledger["acquired"] - ledger["withdrawn"] - reserved, 0.0),
            9,
        )
        token_mint = None
        for row in rows:
            if str(row.get("token", "")).upper() == token.upper() and row.get("mint"):
                token_mint = row["mint"]
                break
        breakdown.append(
            {
                "token": token,
                "mint": token_mint,
                "deposited": ledger["deposited"],
                "acquired_from_swaps": ledger["acquired"],
                "withdrawn": ledger["withdrawn"],
                "reserved_for_orders": reserved,
                "spent": spent,
                "available": available,
                "withdrawable": withdrawable,
            }
        )

    return {
        "user_wallet": user_wallet,
        "balances": breakdown,
        "agent_wallet": get_easya_wallet_pubkey(),
        "platform_fee_rate": EASYA_PLATFORM_FEE_RATE,
    }


def get_easya_token_totals(user_wallet: str, token_symbol: str) -> dict[str, float]:
    rows = _easya_rows(user_wallet.strip())
    ledger = _ledger_totals(user_wallet, token_symbol, rows)
    reserved = _reserved_for_orders(user_wallet, token_symbol)
    deposited = ledger["deposited"]
    spent = ledger["spent_ledger"]
    available = round(max(deposited - spent - reserved, 0.0), 9)
    return {
        "deposited": deposited,
        "spent": spent,
        "reserved_for_orders": reserved,
        "available_to_spend": available,
    }


def check_easya_can_spend_order(user_wallet: str, input_token: str, swap_amount: float) -> dict[str, Any]:
    if not user_wallet or not str(user_wallet).strip():
        return {"error": "user_wallet is required."}

    tok = resolve_token(input_token)
    if "error" in tok:
        return tok

    swap_amount = float(swap_amount)
    if swap_amount <= 0:
        return {"error": "Amount must be greater than zero."}

    total = easya_execution_total_cost(swap_amount)
    totals = get_easya_token_totals(user_wallet.strip(), tok["symbol"])
    available = totals["available_to_spend"]
    if available + 1e-12 < total:
        fee = easya_platform_fee(swap_amount)
        return {
            "error": (
                f"Insufficient {tok['symbol']} in your EasyA trading balance. "
                f"Available: {available}, required: {total} "
                f"(swap {swap_amount} + fee {fee}). "
                f"Deposit SOL to the EasyA Analysis Agent wallet first."
            ),
            "available": available,
            "swap_amount": swap_amount,
            "platform_fee": fee,
            "total_required": total,
            "agent_wallet": get_easya_wallet_pubkey(),
        }

    return {
        "ok": True,
        "token": tok["symbol"],
        "swap_amount": swap_amount,
        "platform_fee": easya_platform_fee(swap_amount),
        "total_required": total,
        "available": available,
        "fee_rate": EASYA_PLATFORM_FEE_RATE,
    }


def verify_and_record_easya_deposit(signature: str, user_wallet: str) -> dict[str, Any]:
    signature = signature.strip()
    user_wallet = user_wallet.strip()
    agent_wallet = get_easya_wallet_pubkey()

    if not agent_wallet:
        return {"error": "EasyA Analysis Agent wallet is not configured on the server."}
    if not signature:
        return {"error": "Transaction signature is required."}
    if not _valid_signature(signature):
        return {"error": "Invalid transaction signature format."}
    if not user_wallet:
        return {"error": "User wallet address is required."}

    with _ledger_lock:
        if deposit_exists(signature):
            existing = find_deposit_by_signature(signature)
            if existing and existing.get("user_wallet") != user_wallet:
                return {
                    "error": "This deposit was already credited to another wallet.",
                    "status": "rejected",
                }
            return {
                "status": "already_recorded",
                "deposit": existing,
                "balances": get_easya_user_balances(user_wallet),
            }

        tx = None
        for attempt in range(10):
            commitment = "finalized" if attempt >= 4 else "confirmed"
            tx = sol_rpc(
                "getTransaction",
                [
                    signature,
                    {
                        "encoding": "jsonParsed",
                        "maxSupportedTransactionVersion": 0,
                        "commitment": commitment,
                    },
                ],
            )
            if tx:
                break
            if attempt < 9:
                import time

                time.sleep(2.0)
        if not tx:
            return {"error": "Transaction not found. Wait for confirmation and try again."}

        if not _user_in_transaction(tx, user_wallet):
            return {"error": "Your connected wallet is not involved in this transaction."}

        inbound = _parse_verified_user_deposits(tx, user_wallet, agent_wallet)
        if not inbound:
            return {
                "error": (
                    "No verifiable deposit from your wallet to the EasyA Analysis Agent wallet was found."
                ),
            }

        now = datetime.now(timezone.utc).isoformat()
        records = []
        for transfer in inbound:
            tok = resolve_token(transfer["mint"])
            if "error" in tok:
                continue
            record = {
                "id": uuid.uuid4().hex[:16],
                "user_wallet": user_wallet,
                "agent_wallet": agent_wallet,
                "signature": signature,
                "token": tok["symbol"],
                "mint": transfer["mint"],
                "amount": float(transfer["amount"]),
                "direction": "deposit",
                "reference_type": "easya_deposit",
                "reference_id": signature[:128],
                "status": "confirmed",
                "verified_at": now,
                "explorer_url": f"https://explorer.solana.com/tx/{signature}",
            }
            insert_ledger_entry(record)
            records.append(record)

        if not records:
            return {"error": "Could not resolve deposited token metadata."}

        return {
            "status": "confirmed",
            "deposits": records,
            "balances": get_easya_user_balances(user_wallet),
        }


def record_easya_spend(
    user_wallet: str,
    input_token: str,
    amount: float,
    *,
    reference_type: str,
    reference_id: str,
    signature: Optional[str] = None,
) -> dict[str, Any]:
    tok = resolve_token(input_token)
    if "error" in tok:
        return tok
    amount = round(float(amount), 9)
    if amount <= 0:
        return {"error": "Spend amount must be greater than zero."}

    record = {
        "id": str(uuid.uuid4())[:8],
        "user_wallet": user_wallet.strip(),
        "agent_wallet": get_easya_wallet_pubkey(),
        "signature": signature,
        "token": tok["symbol"],
        "mint": tok["mint"],
        "amount": amount,
        "direction": "spend",
        "reference_type": reference_type,
        "reference_id": reference_id[:128],
        "status": "confirmed",
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }
    with _ledger_lock:
        insert_ledger_entry(record)
    return {"status": "recorded", "spend": record}


def record_easya_acquire(
    user_wallet: str,
    output_token: str,
    amount: float,
    *,
    reference_type: str,
    reference_id: str,
    signature: Optional[str] = None,
) -> dict[str, Any]:
    tok = resolve_token(output_token)
    if "error" in tok:
        return tok
    amount = round(float(amount), 9)
    if amount <= 0:
        return {"error": "Acquire amount must be greater than zero."}

    record = {
        "id": str(uuid.uuid4())[:8],
        "user_wallet": user_wallet.strip(),
        "agent_wallet": get_easya_wallet_pubkey(),
        "signature": signature,
        "token": tok["symbol"],
        "mint": tok["mint"],
        "amount": amount,
        "direction": "acquire",
        "reference_type": reference_type,
        "reference_id": reference_id[:128],
        "status": "confirmed",
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }
    with _ledger_lock:
        insert_ledger_entry(record)
    return {"status": "recorded", "acquire": record}


def record_easya_platform_fee(
    user_wallet: str,
    swap_amount: float,
    *,
    reference_id: str,
    signature: Optional[str] = None,
) -> dict[str, Any]:
    fee = easya_platform_fee(swap_amount)
    if fee <= 0:
        return {"status": "skipped", "fee": 0.0}
    result = record_easya_spend(
        user_wallet,
        "SOL",
        fee,
        reference_type="easya_fee",
        reference_id=reference_id,
        signature=signature,
    )
    if "error" in result:
        return result
    result["fee"] = fee
    result["fee_rate"] = EASYA_PLATFORM_FEE_RATE
    return result


def withdraw_easya_tokens(user_wallet: str, token: str, amount: float) -> dict[str, Any]:
    from dca_agent import send_tokens_to_user

    user_wallet = user_wallet.strip()
    tok = resolve_token(token)
    if "error" in tok:
        return tok
    amount = round(float(amount), 9)
    if amount <= 0:
        return {"error": "Withdraw amount must be greater than zero."}

    with user_token_withdraw_lock(user_wallet, tok["symbol"]):
        rows = _easya_rows(user_wallet)
        ledger = _ledger_totals(user_wallet, tok["symbol"], rows)
        reserved = _reserved_for_orders(user_wallet, tok["symbol"])
        withdrawable = round(
            max(ledger["deposited"] + ledger["acquired"] - ledger["withdrawn"] - reserved, 0.0),
            9,
        )
        if withdrawable + 1e-12 < amount:
            return {
                "error": (
                    f"Insufficient withdrawable {tok['symbol']}. "
                    f"Withdrawable: {withdrawable}, requested: {amount}."
                ),
                "withdrawable": withdrawable,
            }

        transfer = send_tokens_to_user(
            user_wallet,
            tok["mint"],
            amount,
            tok["decimals"],
            signing_keypair=load_easya_keypair(),
        )
        if transfer.get("error") or transfer.get("status") != "success":
            return transfer

        signature = transfer.get("signature")
        record = {
            "id": str(uuid.uuid4())[:8],
            "user_wallet": user_wallet,
            "agent_wallet": get_easya_wallet_pubkey(),
            "signature": signature,
            "token": tok["symbol"],
            "mint": tok["mint"],
            "amount": amount,
            "direction": "withdraw",
            "reference_type": "easya_withdraw",
            "reference_id": (signature or "withdraw")[:128],
            "status": "confirmed",
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "explorer_url": transfer.get("explorer_url"),
        }
        insert_ledger_entry(record)

    return {
        "status": "success",
        "withdraw": record,
        "signature": signature,
        "explorer_url": transfer.get("explorer_url"),
        "balances": get_easya_user_balances(user_wallet),
    }
