"""Per-user Circle wallet + deposit ledger for the Yield Agent."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from db import insert_ledger_entry, load_ledger_for_user
from dca_agent import SOL_ADDRESS_FULL, resolve_token, sol_rpc

ALLOWED_DEPOSIT_TOKENS = {"SOL"}
ALLOWED_WITHDRAW_TOKENS = {"SOL"}
AGENT_TYPE = "yield"


def get_yield_wallet_pubkey(user_wallet: Optional[str] = None) -> Optional[str]:
    user_wallet = (user_wallet or "").strip()
    if not user_wallet:
        return None
    try:
        from circle_dca_wallets import get_agent_wallet_address

        return get_agent_wallet_address(user_wallet, AGENT_TYPE)
    except Exception as exc:
        print(f"  ⚠️  Yield Circle wallet unavailable: {exc}")
        return None


def get_yield_agent_wallet_info(user_wallet: Optional[str] = None) -> dict[str, Any]:
    from dca_agent import SOLANA_CLUSTER, SOLANA_RPC
    from circle_dca_wallets import circle_dca_enabled

    user_wallet = (user_wallet or "").strip()
    wallet = get_yield_wallet_pubkey(user_wallet) if user_wallet else None
    provider = "circle" if wallet else None
    circle_error = None
    if user_wallet and circle_dca_enabled() and not wallet:
        circle_error = "Circle Yield wallet provisioning failed. Check CIRCLE_API_KEY / CIRCLE_ENTITY_SECRET."
    elif user_wallet and not circle_dca_enabled():
        circle_error = "Circle is not configured, so the Yield Agent cannot hold capital."

    result = {
        "agent_wallet": wallet,
        "configured": bool(wallet),
        "wallet_provider": provider,
        "per_user_wallet": bool(wallet),
        "cluster": SOLANA_CLUSTER,
        "rpc": SOLANA_RPC,
        "allowed_tokens": sorted(ALLOWED_DEPOSIT_TOKENS),
        "allowed_withdraw_tokens": sorted(ALLOWED_WITHDRAW_TOKENS),
        "sol_mint": SOL_ADDRESS_FULL,
        "live_routing": "kamino_save_and_jlp",
    }
    if circle_error:
        result["circle_error"] = circle_error
    return result


def _yield_rows(user_wallet: str) -> list[dict[str, Any]]:
    wallet = get_yield_wallet_pubkey(user_wallet)
    if not wallet:
        return []
    rows = load_ledger_for_user(user_wallet.strip())
    return [r for r in rows if r.get("agent_wallet") == wallet]


def _ledger_totals(user_wallet: str, token_symbol: str) -> dict[str, float]:
    token_symbol = token_symbol.strip().upper()
    deposited = spent = withdrawn = 0.0
    for row in _yield_rows(user_wallet):
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
        elif direction == "withdraw":
            withdrawn += amount
    return {
        "deposited": round(deposited, 9),
        "spent": round(spent, 9),
        "withdrawn": round(withdrawn, 9),
    }


def get_yield_user_balances(user_wallet: str) -> dict[str, Any]:
    rows = _yield_rows(user_wallet)
    tokens = sorted({str(row.get("token") or "").upper() for row in rows if row.get("token")})
    if "SOL" not in tokens:
        tokens = ["SOL", *tokens]
    balances = []
    for token in tokens:
        totals = _ledger_totals(user_wallet, token)
        idle = round(max(0.0, totals["deposited"] - totals["spent"] - totals["withdrawn"]), 9)
        tok = resolve_token(token)
        balances.append(
            {
                "token": token,
                "mint": None if "error" in tok else tok.get("mint"),
                "deposited": totals["deposited"],
                "spent_in_positions": totals["spent"],
                "withdrawn": totals["withdrawn"],
                "available": idle,
                "withdrawable": idle,
            }
        )
    return {
        "user_wallet": user_wallet.strip(),
        "agent_wallet": get_yield_wallet_pubkey(user_wallet),
        "balances": balances,
    }


def check_yield_can_spend(user_wallet: str, amount: float, token: str = "SOL") -> dict[str, Any]:
    amount = float(amount)
    token = (token or "SOL").strip().upper()
    balances = get_yield_user_balances(user_wallet)
    available = 0.0
    for row in balances.get("balances") or []:
        if str(row.get("token", "")).upper() == token:
            available = float(row.get("available") or 0)
            break
    if available + 1e-12 >= amount:
        return {"ok": True, "available": available, "token": token}
    return {
        "error": (
            f"Insufficient idle {token}. Available: {available}, requested: {amount}. "
            f"Deposit {token} to the Yield Agent Circle wallet first."
        ),
        "available": available,
    }


def _insert_yield_ledger(
    user_wallet: str,
    *,
    token: str,
    direction: str,
    amount: float,
    reference_type: str,
    reference_id: str,
    signature: Optional[str] = None,
    explorer_url: Optional[str] = None,
) -> dict[str, Any]:
    agent_wallet = get_yield_wallet_pubkey(user_wallet)
    if not agent_wallet:
        return {"error": "Yield agent wallet is not configured."}
    tok = resolve_token(token)
    if "error" in tok:
        return tok
    record = {
        "id": uuid.uuid4().hex[:16],
        "user_wallet": user_wallet.strip(),
        "agent_wallet": agent_wallet,
        "signature": signature,
        "token": tok["symbol"],
        "mint": tok.get("mint") or SOL_ADDRESS_FULL,
        "amount": float(amount),
        "direction": direction,
        "reference_type": reference_type,
        "reference_id": (reference_id or "")[:128],
        "status": "confirmed",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "explorer_url": explorer_url,
    }
    insert_ledger_entry(record)
    return record


def record_yield_spend(
    user_wallet: str,
    amount: float,
    *,
    reference_id: str,
    token: str = "SOL",
    signature: Optional[str] = None,
    explorer_url: Optional[str] = None,
) -> dict[str, Any]:
    if amount <= 0:
        return {"spent": 0.0}
    rec = _insert_yield_ledger(
        user_wallet,
        token=token,
        direction="spend",
        amount=amount,
        reference_type="yield_allocate",
        reference_id=reference_id,
        signature=signature,
        explorer_url=explorer_url,
    )
    if rec.get("error"):
        return rec
    return {"spent": float(amount), "token": (token or "SOL").strip().upper()}


def record_yield_credit(
    user_wallet: str,
    amount: float,
    *,
    reference_id: str,
    token: str = "SOL",
    signature: Optional[str] = None,
    explorer_url: Optional[str] = None,
) -> dict[str, Any]:
    if amount <= 0:
        return {"credited": 0.0}
    rec = _insert_yield_ledger(
        user_wallet,
        token=token,
        direction="deposit",
        amount=amount,
        reference_type="yield_unwind",
        reference_id=reference_id,
        signature=signature,
        explorer_url=explorer_url,
    )
    if rec.get("error"):
        return rec
    return {"credited": float(amount), "token": (token or "SOL").strip().upper()}


def verify_and_record_yield_deposit(signature: str, user_wallet: str) -> dict[str, Any]:
    from deposit_ledger import (
        _ledger_lock,
        _parse_verified_user_deposits,
        _user_in_transaction,
        _valid_signature,
    )

    signature = signature.strip()
    user_wallet = user_wallet.strip()
    agent_wallet = get_yield_wallet_pubkey(user_wallet)
    if not agent_wallet:
        return {"error": "Yield agent wallet is not configured (Circle)."}
    if not signature or not _valid_signature(signature):
        return {"error": "Valid transaction signature is required."}

    with _ledger_lock:
        from db import deposit_exists, find_deposit_by_signature

        if deposit_exists(signature):
            existing = find_deposit_by_signature(signature)
            if existing and existing.get("user_wallet") != user_wallet:
                return {"error": "This deposit was already credited to another wallet.", "status": "rejected"}
            return {
                "status": "already_recorded",
                "deposit": existing,
                "balances": get_yield_user_balances(user_wallet),
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
                        "commitment": commitment,
                        "maxSupportedTransactionVersion": 0,
                    },
                ],
            )
            if tx:
                break
            import time

            time.sleep(0.6)

        if not tx:
            return {"error": "Transaction not found yet. Wait a few seconds and retry.", "status": "pending"}

        if not _user_in_transaction(tx, user_wallet):
            return {
                "error": "Connected wallet must be a signer of the deposit transaction.",
                "status": "rejected",
            }

        inbound = _parse_verified_user_deposits(tx, user_wallet, agent_wallet)
        if not inbound:
            return {
                "error": "No verifiable SOL deposit from your wallet to the Yield Agent wallet was found.",
                "status": "rejected",
            }

        now = datetime.now(timezone.utc).isoformat()
        records = []
        for transfer in inbound:
            tok = resolve_token(str(transfer.get("mint") or transfer.get("token") or "SOL"))
            if "error" in tok:
                continue
            token = str(tok.get("symbol") or "").upper()
            if token not in ALLOWED_DEPOSIT_TOKENS:
                return {"error": f"Deposits must be SOL (got {token}).", "status": "rejected"}
            record = {
                "id": uuid.uuid4().hex[:16],
                "user_wallet": user_wallet,
                "agent_wallet": agent_wallet,
                "signature": signature,
                "token": token,
                "mint": tok.get("mint"),
                "amount": float(transfer["amount"]),
                "direction": "deposit",
                "reference_type": "yield_deposit",
                "reference_id": signature[:128],
                "status": "confirmed",
                "verified_at": now,
                "explorer_url": f"https://solscan.io/tx/{signature}",
            }
            insert_ledger_entry(record)
            records.append(record)
        if not records:
            return {"error": "No SOL transfer to the Yield Agent wallet found.", "status": "rejected"}
        return {
            "status": "confirmed",
            "deposits": records,
            "balances": get_yield_user_balances(user_wallet),
            "message": "Deposit verified. Ask the agent to compare yields and allocate.",
        }


def withdraw_yield_tokens(user_wallet: str, token: str, amount: float) -> dict[str, Any]:
    from deposit_ledger import _ledger_lock
    from dca_agent import send_tokens_to_user

    user_wallet = user_wallet.strip()
    token = token.strip().upper()
    if token not in ALLOWED_WITHDRAW_TOKENS:
        return {"error": "Only idle SOL can be withdrawn."}
    tok = resolve_token(token)
    if "error" in tok:
        return tok
    amount = round(float(amount), 9)
    if amount <= 0:
        return {"error": "Withdraw amount must be greater than zero."}

    balances = get_yield_user_balances(user_wallet)
    withdrawable = 0.0
    for row in balances.get("balances") or []:
        if str(row.get("token", "")).upper() == token:
            withdrawable = float(row.get("withdrawable") or 0)
            break

    with _ledger_lock:
        if withdrawable + 1e-12 < amount:
            return {
                "error": (
                    f"Insufficient idle {token}. Withdrawable: {withdrawable}, requested: {amount}. "
                    "Unwind yield positions before withdrawing deployed capital."
                ),
                "withdrawable": withdrawable,
            }
        transfer = send_tokens_to_user(
            user_wallet,
            tok["mint"],
            amount,
            tok["decimals"],
            signing_user_wallet=user_wallet,
            agent_type=AGENT_TYPE,
        )
        if transfer.get("error") or transfer.get("status") != "success":
            return transfer
        signature = transfer.get("signature")
        record = _insert_yield_ledger(
            user_wallet,
            token=token,
            direction="withdraw",
            amount=amount,
            reference_type="yield_withdraw",
            reference_id=(signature or "withdraw")[:128],
            signature=signature,
            explorer_url=transfer.get("explorer_url"),
        )
    return {
        "status": "success",
        "withdraw": record,
        "signature": signature,
        "balances": get_yield_user_balances(user_wallet),
    }


def list_yield_user_ledger(user_wallet: str, limit: int = 50) -> list[dict[str, Any]]:
    rows = _yield_rows(user_wallet)
    rows.sort(key=lambda r: r.get("verified_at") or "", reverse=True)
    return rows[: max(1, min(int(limit or 50), 100))]
