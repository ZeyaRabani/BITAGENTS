"""
User deposit ledger for the AI Agent wallet.

Verifies on-chain transfers into the agent wallet and tracks per-user balances
so DCA plans cannot spend more than each user has deposited.
"""

from __future__ import annotations

import re
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from db import (
    deposit_exists,
    find_deposit_by_signature,
    insert_ledger_entry,
    load_all_ledger_entries,
    load_all_plans,
    load_ledger_for_user,
    load_user_balance_data,
)
from dca_agent import (
    SOL_ADDRESS_FULL,
    SOL_ADDRESS_SHORT,
    TOKEN_MINTS,
    get_wallet_pubkey,
    resolve_token,
    sol_rpc,
)

# DCA / Volume / EasyA accept SOL deposits only. Hedge Fund stays USDC-only in its own ledger.
ALLOWED_AGENT_DEPOSIT_SYMBOLS = {"SOL", "WSOL"}


def is_allowed_sol_deposit(token_symbol: str, mint: Optional[str] = None) -> bool:
    symbol = str(token_symbol or "").strip().upper()
    mint_addr = str(mint or "").strip()
    if symbol in ALLOWED_AGENT_DEPOSIT_SYMBOLS:
        return True
    return mint_addr in (SOL_ADDRESS_FULL, SOL_ADDRESS_SHORT)

_ledger_lock = threading.Lock()

# Platform fee on each successful scheduled DCA execution (input token).
DCA_PLATFORM_FEE_RATE = 0.005  # 0.5%


def dca_platform_fee(swap_amount: float) -> float:
    """Fee charged in the swap input token after a successful DCA buy."""
    amount = float(swap_amount)
    if amount <= 0:
        return 0.0
    return round(amount * DCA_PLATFORM_FEE_RATE, 12)


def dca_execution_total_cost(swap_amount: float) -> float:
    """Swap amount plus platform fee for one DCA execution."""
    amount = float(swap_amount)
    return round(amount + dca_platform_fee(amount), 12)

MINT_TO_SYMBOL = {info["mint"]: sym for sym, info in TOKEN_MINTS.items() if sym != "WSOL"}


def _load_deposits() -> list[dict[str, Any]]:
    return load_all_ledger_entries()


def _load_user_ledger(user_wallet: str) -> list[dict[str, Any]]:
    return load_ledger_for_user(user_wallet.strip())


def _load_plans(user_wallet: Optional[str] = None) -> list[dict[str, Any]]:
    return load_all_plans(user_wallet)


def _mint_to_symbol(mint: str) -> str:
    tok = resolve_token(mint)
    if "error" not in tok:
        return tok["symbol"]
    return mint[:8]


def _account_keys(tx: dict) -> list[str]:
    message = tx.get("transaction", {}).get("message", {})
    keys: list[str] = []
    raw_keys = message.get("accountKeys") or message.get("staticAccountKeys") or []
    for entry in raw_keys:
        if isinstance(entry, dict):
            keys.append(entry.get("pubkey", ""))
        else:
            keys.append(str(entry))
    return [k for k in keys if k]


def _valid_signature(signature: str) -> bool:
    signature = signature.strip()
    if len(signature) < 80 or len(signature) > 128:
        return False
    return bool(re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]+", signature))


def _transaction_signers(tx: dict) -> set[str]:
    signers: set[str] = set()
    message = tx.get("transaction", {}).get("message", {})
    raw_keys = message.get("accountKeys") or message.get("staticAccountKeys") or []
    for entry in raw_keys:
        if isinstance(entry, dict) and entry.get("signer") and entry.get("pubkey"):
            signers.add(str(entry["pubkey"]))
    return signers


def _user_in_transaction(tx: dict, user_wallet: str) -> bool:
    keys = _account_keys(tx)
    if user_wallet in keys:
        return True
    meta = tx.get("meta") or {}
    for bucket in ("preTokenBalances", "postTokenBalances"):
        for bal in meta.get(bucket, []):
            if bal.get("owner") == user_wallet:
                return True
    return False


def _parse_verified_user_deposits(
    tx: dict,
    user_wallet: str,
    agent_wallet: str,
) -> list[dict[str, Any]]:
    """
    Deposits to the agent wallet that were sent by user_wallet in this transaction.
    Requires the user to be a signer and show an outbound balance decrease matching
    the agent inbound increase (prevents claiming someone else's transfer).
    """
    meta = tx.get("meta") or {}
    if meta.get("err"):
        return []

    if user_wallet not in _transaction_signers(tx):
        return []

    keys = _account_keys(tx)
    found: list[dict[str, Any]] = []

    if user_wallet in keys and agent_wallet in keys:
        user_idx = keys.index(user_wallet)
        agent_idx = keys.index(agent_wallet)
        pre_balances = meta.get("preBalances") or []
        post_balances = meta.get("postBalances") or []
        if (
            user_idx < len(pre_balances)
            and user_idx < len(post_balances)
            and agent_idx < len(pre_balances)
            and agent_idx < len(post_balances)
        ):
            user_delta = post_balances[user_idx] - pre_balances[user_idx]
            agent_delta = post_balances[agent_idx] - pre_balances[agent_idx]
            if user_delta < 0 and agent_delta > 0:
                found.append(
                    {
                        "token": "SOL",
                        "mint": SOL_ADDRESS_FULL,
                        "amount": round(agent_delta / 1e9, 9),
                    }
                )

    user_pre: dict[str, float] = {}
    user_post: dict[str, float] = {}
    agent_pre: dict[str, float] = {}
    agent_post: dict[str, float] = {}

    for bal in meta.get("preTokenBalances") or []:
        owner = bal.get("owner")
        mint = bal.get("mint")
        if not owner or not mint:
            continue
        amt = float((bal.get("uiTokenAmount") or {}).get("uiAmount") or 0)
        if owner == user_wallet:
            user_pre[mint] = amt
        elif owner == agent_wallet:
            agent_pre[mint] = amt

    for bal in meta.get("postTokenBalances") or []:
        owner = bal.get("owner")
        mint = bal.get("mint")
        if not owner or not mint:
            continue
        amt = float((bal.get("uiTokenAmount") or {}).get("uiAmount") or 0)
        if owner == user_wallet:
            user_post[mint] = amt
        elif owner == agent_wallet:
            agent_post[mint] = amt

    for mint in set(agent_pre) | set(agent_post) | set(user_pre) | set(user_post):
        agent_delta = agent_post.get(mint, 0.0) - agent_pre.get(mint, 0.0)
        user_delta = user_post.get(mint, 0.0) - user_pre.get(mint, 0.0)
        if agent_delta > 0 and user_delta < 0:
            found.append(
                {
                    "token": _mint_to_symbol(mint),
                    "mint": mint,
                    "amount": round(min(agent_delta, -user_delta), 9),
                }
            )

    return found


def _parse_inbound_transfers(tx: dict, agent_wallet: str) -> list[dict[str, Any]]:
    meta = tx.get("meta") or {}
    if meta.get("err"):
        return []

    found: list[dict[str, Any]] = []
    keys = _account_keys(tx)

    if agent_wallet in keys:
        idx = keys.index(agent_wallet)
        pre_balances = meta.get("preBalances") or []
        post_balances = meta.get("postBalances") or []
        if idx < len(pre_balances) and idx < len(post_balances):
            delta = post_balances[idx] - pre_balances[idx]
            if delta > 0:
                found.append({"token": "SOL", "mint": SOL_ADDRESS_FULL, "amount": delta / 1e9})

    pre_tokens: dict[tuple[str, str], float] = {}
    for bal in meta.get("preTokenBalances") or []:
        owner = bal.get("owner")
        mint = bal.get("mint")
        if not owner or not mint:
            continue
        ui = bal.get("uiTokenAmount") or {}
        pre_tokens[(owner, mint)] = float(ui.get("uiAmount") or 0)

    for bal in meta.get("postTokenBalances") or []:
        if bal.get("owner") != agent_wallet:
            continue
        mint = bal.get("mint")
        if not mint:
            continue
        ui = bal.get("uiTokenAmount") or {}
        post_amt = float(ui.get("uiAmount") or 0)
        pre_amt = pre_tokens.get((agent_wallet, mint), 0.0)
        delta = post_amt - pre_amt
        if delta > 0:
            found.append(
                {
                    "token": _mint_to_symbol(mint),
                    "mint": mint,
                    "amount": round(delta, 9),
                }
            )

    return found


def get_agent_wallet_info(user_wallet: Optional[str] = None) -> dict[str, Any]:
    from dca_agent import SOLANA_CLUSTER, SOLANA_RPC, load_keypair
    from circle_dca_wallets import circle_dca_enabled, get_dca_agent_wallet_address

    user_wallet = (user_wallet or "").strip()
    wallet = None
    provider = "local"
    circle_error = None
    per_user = False

    if user_wallet and circle_dca_enabled():
        try:
            wallet = get_dca_agent_wallet_address(user_wallet)
            if wallet:
                provider = "circle"
                per_user = True
            else:
                circle_error = (
                    "Circle wallet provisioning failed. Check CIRCLE_ENTITY_SECRET is the "
                    "registered 64-char hex secret (register at Circle Console). "
                    "Falling back to shared DCA_WALLET_PRIVATE_KEY if configured."
                )
        except Exception as exc:
            circle_error = str(exc)

    if not wallet:
        wallet = get_wallet_pubkey()
        if wallet:
            provider = "local"

    if not wallet and load_keypair() is None and circle_dca_enabled() and not circle_error:
        circle_error = "No agent wallet available (Circle failed and no DCA_WALLET_PRIVATE_KEY)."

    result = {
        "agent_wallet": wallet,
        "configured": bool(wallet),
        "wallet_provider": provider,
        "per_user_wallet": per_user,
        "any_spl_token": False,
        "token_resolution": "symbol_or_mint",
        "common_tokens": ["SOL"],
        "allowed_deposit_tokens": ["SOL"],
        "storage": "neon_postgres",
        "cluster": SOLANA_CLUSTER,
        "rpc_url": SOLANA_RPC,
    }
    if circle_error and not per_user:
        result["circle_error"] = circle_error
    return result


def verify_and_record_deposit(signature: str, user_wallet: str) -> dict[str, Any]:
    signature = signature.strip()
    user_wallet = user_wallet.strip()
    agent_wallet = get_wallet_pubkey(user_wallet)

    if not agent_wallet:
        return {"error": "AI Agent wallet is not configured on the server."}
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
                    "error": (
                        "This deposit transaction was already credited to another wallet. "
                        "You cannot claim someone else's deposit."
                    ),
                    "status": "rejected",
                }
            return {
                "status": "already_recorded",
                "deposit": existing,
                "balances": get_user_balances(user_wallet),
                "message": "This deposit was already verified for your wallet.",
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
                time.sleep(2.0)
        if not tx:
            return {"error": "Transaction not found. Wait for confirmation and try again."}

        if not _user_in_transaction(tx, user_wallet):
            return {
                "error": (
                    "Your connected wallet is not involved in this transaction. "
                    "You can only verify deposits you signed and sent."
                ),
            }

        inbound = _parse_verified_user_deposits(tx, user_wallet, agent_wallet)
        if not inbound:
            return {
                "error": (
                    "No verifiable deposit from your wallet to the AI Agent wallet was found. "
                    "Ensure you signed the transfer and it sent tokens to the agent wallet."
                ),
            }

        now = datetime.now(timezone.utc).isoformat()
        records = []
        skipped: list[str] = []
        rejected_non_sol: list[str] = []
        for transfer in inbound:
            tok = resolve_token(transfer["mint"])
            if "error" in tok:
                skipped.append(transfer.get("token") or transfer.get("mint", "unknown"))
                continue
            if not is_allowed_sol_deposit(tok.get("symbol", ""), transfer.get("mint")):
                rejected_non_sol.append(str(tok.get("symbol") or transfer.get("mint")))
                continue
            record = {
                "id": uuid.uuid4().hex[:16],
                "user_wallet": user_wallet,
                "agent_wallet": agent_wallet,
                "signature": signature,
                "token": "SOL",
                "mint": transfer["mint"] if transfer.get("mint") else SOL_ADDRESS_FULL,
                "amount": float(transfer["amount"]),
                "direction": "deposit",
                "status": "confirmed",
                "verified_at": now,
                "explorer_url": _explorer_url(signature),
            }
            if insert_ledger_entry(record):
                records.append(record)

        if not records:
            if rejected_non_sol and not skipped:
                return {
                    "error": (
                        "Only SOL deposits are accepted for the DCA agent. "
                        f"Rejected: {', '.join(rejected_non_sol)}."
                    ),
                }
            if skipped:
                return {
                    "error": (
                        "Deposit found on-chain but token metadata could not be resolved: "
                        + ", ".join(skipped)
                    ),
                }
            return {"error": "Could not save deposit to database. Please retry verification."}
            return {"error": "Could not save deposit to database. Please retry verification."}

        return {
            "status": "confirmed",
            "deposits": records,
            "balances": get_user_balances(user_wallet),
            "message": "Deposit verified and credited to your balance.",
        }


def list_user_deposits(user_wallet: str, limit: int = 20) -> dict[str, Any]:
    user_wallet = user_wallet.strip()
    rows = load_ledger_for_user(user_wallet, limit=limit)
    deposits = [r for r in rows if r.get("direction", "deposit") == "deposit"]
    return {
        "user_wallet": user_wallet,
        "deposits": deposits,
        "balances": get_user_balances(user_wallet),
    }


def list_user_ledger_history(user_wallet: str, limit: int = 50) -> dict[str, Any]:
    """All ledger movements: deposits, DCA spends, acquires, withdrawals."""
    user_wallet = user_wallet.strip()
    rows = load_ledger_for_user(user_wallet, limit=limit)
    return {
        "user_wallet": user_wallet,
        "entries": rows,
        "count": len(rows),
    }


def get_user_dca_executions(user_wallet: str, limit: int = 100) -> dict[str, Any]:
    """Flatten DCA swap executions across all plans for one user."""
    user_wallet = user_wallet.strip()
    plans = _load_plans(user_wallet)
    executions: list[dict[str, Any]] = []
    for plan in plans:
        for entry in plan.get("executions") or []:
            result = entry.get("result") or {}
            executions.append({
                "plan_id": plan["id"],
                "plan_name": plan["name"],
                "pair": f"{plan['input_token']} → {plan['output_token']}",
                "input_mint": plan.get("input_mint"),
                "output_mint": plan.get("output_mint"),
                "at": entry.get("at"),
                "amount": entry.get("amount"),
                "platform_fee": entry.get("platform_fee"),
                "total_cost": entry.get("total_cost"),
                "input_token": entry.get("input_token"),
                "output_token": entry.get("output_token"),
                "dry_run": entry.get("dry_run", False),
                "status": result.get("status"),
                "signature": result.get("signature"),
                "explorer_url": result.get("explorer_url"),
                "output_amount": result.get("output_amount"),
                "error": result.get("error"),
            })
    executions.sort(key=lambda row: row.get("at") or "", reverse=True)
    if limit:
        executions = executions[:limit]
    return {
        "user_wallet": user_wallet,
        "executions": executions,
        "count": len(executions),
    }


def _user_plan_usage(user_wallet: str) -> dict[str, dict[str, float]]:
    return _user_plan_usage_from_plans(user_wallet, _load_plans(user_wallet))


def _user_plan_usage_from_plans(
    user_wallet: str,
    plans: list[dict[str, Any]],
) -> dict[str, dict[str, float]]:
    usage: dict[str, dict[str, float]] = {}
    for plan in plans:
        if plan.get("status") in ("cancelled",):
            continue
        token = plan.get("input_token", "SOL")
        bucket = usage.setdefault(token, {"reserved": 0.0, "spent": 0.0})
        spent = float(plan.get("spent_so_far") or 0)
        bucket["spent"] += spent
        budget = plan.get("total_budget")
        if budget not in (None, "null", ""):
            try:
                budget_f = float(budget)
                bucket["reserved"] += max(budget_f, spent)
            except (TypeError, ValueError):
                bucket["reserved"] += spent
        else:
            max_exec = plan.get("max_executions")
            per_buy = float(plan.get("amount_per_buy") or 0)
            per_execution = dca_execution_total_cost(per_buy)
            if max_exec not in (None, "null", ""):
                try:
                    bucket["reserved"] += per_execution * int(max_exec)
                except (TypeError, ValueError):
                    bucket["reserved"] += spent
            else:
                bucket["reserved"] += max(spent, per_execution)

    return usage


def _ledger_totals_for_user_token(
    user_wallet: str,
    token_symbol: str,
    rows: Optional[list[dict[str, Any]]] = None,
) -> dict[str, float]:
    """Sum ledger directions for one user and token symbol."""
    user_wallet = user_wallet.strip()
    token_symbol = token_symbol.strip().upper()
    deposited = 0.0
    spent_ledger = 0.0
    acquired = 0.0
    withdrawn = 0.0
    source = rows if rows is not None else _load_user_ledger(user_wallet)
    for row in source:
        if row.get("user_wallet") != user_wallet or row.get("status") != "confirmed":
            continue
        if str(row.get("token", "")).upper() != token_symbol:
            continue
        amount = float(row.get("amount") or 0)
        direction = row.get("direction", "deposit")
        if direction == "deposit":
            deposited += amount
        elif direction == "spend":
            spent_ledger += amount
        elif direction == "acquire":
            acquired += amount
        elif direction == "withdraw":
            withdrawn += amount

    return {
        "deposited": round(deposited, 9),
        "spent_ledger": round(spent_ledger, 9),
        "acquired": round(acquired, 9),
        "withdrawn": round(withdrawn, 9),
    }


def get_user_token_withdrawable(user_wallet: str, token_symbol: str) -> float:
    """Unused deposits plus DCA-acquired tokens, minus prior withdrawals and active plan reserves."""
    totals = _ledger_totals_for_user_token(user_wallet, token_symbol)
    usage = _user_plan_usage(user_wallet.strip())
    reserved = float(usage.get(token_symbol, {}).get("reserved", 0.0))
    return round(
        max(
            totals["deposited"] + totals["acquired"] - totals["withdrawn"] - reserved,
            0.0,
        ),
        9,
    )


def get_user_balances(user_wallet: str) -> dict[str, Any]:
    user_wallet = user_wallet.strip()
    user_rows, user_plans = load_user_balance_data(user_wallet)
    ledger_tokens: set[str] = set()
    for row in user_rows:
        if row.get("status") != "confirmed":
            continue
        ledger_tokens.add(str(row.get("token", "SOL")))

    usage = _user_plan_usage_from_plans(user_wallet, user_plans)
    tokens = sorted(ledger_tokens | set(usage))
    breakdown = []
    for token in tokens:
        ledger = _ledger_totals_for_user_token(user_wallet, token, rows=user_rows)
        reserved = usage.get(token, {}).get("reserved", 0.0)
        spent_plans = usage.get(token, {}).get("spent", 0.0)
        spent = round(max(ledger["spent_ledger"], spent_plans), 9)
        available = round(max(ledger["deposited"] - spent, 0.0), 9)
        withdrawable = round(
            max(ledger["deposited"] + ledger["acquired"] - ledger["withdrawn"] - reserved, 0.0),
            9,
        )
        token_mint = None
        for row in user_rows:
            if str(row.get("token", "")).upper() == token.upper() and row.get("mint"):
                token_mint = row["mint"]
                break
        breakdown.append(
            {
                "token": token,
                "mint": token_mint,
                "deposited": ledger["deposited"],
                "acquired_from_dca": ledger["acquired"],
                "withdrawn": ledger["withdrawn"],
                "reserved_for_plans": round(reserved, 9),
                "spent_in_plans": spent,
                "available": available,
                "withdrawable": withdrawable,
            }
        )

    return {
        "user_wallet": user_wallet,
        "balances": breakdown,
        "agent_wallet": get_wallet_pubkey(user_wallet),
    }


def get_user_token_spend_totals(user_wallet: str, token_symbol: str) -> dict[str, float]:
    """Deposited and spent amounts for one user + token."""
    user_wallet = user_wallet.strip()
    token_symbol = token_symbol.strip().upper()
    user_rows = _load_user_ledger(user_wallet)
    ledger = _ledger_totals_for_user_token(user_wallet, token_symbol, rows=user_rows)
    deposited = ledger["deposited"]
    spent_ledger = ledger["spent_ledger"]

    spent_plans = 0.0
    for plan in _load_plans(user_wallet):
        if plan.get("status") == "cancelled":
            continue
        if str(plan.get("input_token", "")).upper() != token_symbol:
            continue
        spent_plans += float(plan.get("spent_so_far") or 0)

    deposited = round(deposited, 9)
    spent = round(max(spent_ledger, spent_plans), 9)
    return {
        "deposited": deposited,
        "spent": spent,
        "available_to_spend": round(max(deposited - spent, 0.0), 9),
    }


def record_user_spend(
    user_wallet: str,
    input_token: str,
    amount: float,
    *,
    reference_type: str,
    reference_id: str,
    signature: Optional[str] = None,
) -> dict[str, Any]:
    """Record an on-chain spend against a user's deposit balance."""
    user_wallet = user_wallet.strip()
    tok = resolve_token(input_token)
    if "error" in tok:
        return tok

    amount = round(float(amount), 9)
    if amount <= 0:
        return {"error": "Spend amount must be greater than zero."}

    now = datetime.now(timezone.utc).isoformat()
    record = {
        "id": str(uuid.uuid4())[:8],
        "user_wallet": user_wallet,
        "agent_wallet": get_wallet_pubkey(user_wallet),
        "signature": signature,
        "token": tok["symbol"],
        "mint": tok["mint"],
        "amount": amount,
        "direction": "spend",
        "reference_type": reference_type,
        "reference_id": reference_id,
        "status": "confirmed",
        "verified_at": now,
    }

    with _ledger_lock:
        insert_ledger_entry(record)

    totals = get_user_token_spend_totals(user_wallet, tok["symbol"])
    return {"status": "recorded", "spend": record, "balances": totals}


def record_user_acquire(
    user_wallet: str,
    output_token: str,
    amount: float,
    *,
    reference_type: str,
    reference_id: str,
    signature: Optional[str] = None,
) -> dict[str, Any]:
    """Credit DCA output tokens to a user's withdrawable balance."""
    user_wallet = user_wallet.strip()
    tok = resolve_token(output_token)
    if "error" in tok:
        return tok

    amount = round(float(amount), 9)
    if amount <= 0:
        return {"error": "Acquire amount must be greater than zero."}

    now = datetime.now(timezone.utc).isoformat()
    record = {
        "id": str(uuid.uuid4())[:8],
        "user_wallet": user_wallet,
        "agent_wallet": get_wallet_pubkey(user_wallet),
        "signature": signature,
        "token": tok["symbol"],
        "mint": tok["mint"],
        "amount": amount,
        "direction": "acquire",
        "reference_type": reference_type,
        "reference_id": reference_id,
        "status": "confirmed",
        "verified_at": now,
    }

    with _ledger_lock:
        insert_ledger_entry(record)

    return {
        "status": "recorded",
        "acquire": record,
        "withdrawable": get_user_token_withdrawable(user_wallet, tok["symbol"]),
    }


def record_dca_platform_fee(
    user_wallet: str,
    input_token: str,
    swap_amount: float,
    *,
    reference_id: str,
    signature: Optional[str] = None,
    plan_id: Optional[str] = None,
) -> dict[str, Any]:
    """Record the 0.5% platform fee for a successful DCA execution (input token)."""
    fee = dca_platform_fee(swap_amount)
    if fee <= 0:
        return {"status": "skipped", "fee": 0.0, "token": input_token}

    ref_id = reference_id[:128]
    if plan_id:
        ref_id = f"{plan_id}:{ref_id}"[:128]

    result = record_user_spend(
        user_wallet,
        input_token,
        fee,
        reference_type="dca_fee",
        reference_id=ref_id,
        signature=signature,
    )
    if "error" in result:
        return result
    result["fee"] = fee
    result["fee_rate"] = DCA_PLATFORM_FEE_RATE
    result["fee_token"] = result.get("spend", {}).get("token") or input_token
    return result


def check_user_can_spend_dca(
    user_wallet: str,
    input_token: str,
    swap_amount: float,
) -> dict[str, Any]:
    """Ensure the user can cover swap amount plus the DCA platform fee."""
    total = dca_execution_total_cost(swap_amount)
    check = check_user_can_spend(user_wallet, input_token, total)
    if "error" in check:
        fee = dca_platform_fee(swap_amount)
        check["swap_amount"] = float(swap_amount)
        check["platform_fee"] = fee
        check["total_required"] = total
        check["fee_rate"] = DCA_PLATFORM_FEE_RATE
    else:
        check["swap_amount"] = float(swap_amount)
        check["platform_fee"] = dca_platform_fee(swap_amount)
        check["total_required"] = total
        check["fee_rate"] = DCA_PLATFORM_FEE_RATE
    return check


def withdraw_user_tokens(user_wallet: str, token: str, amount: float) -> dict[str, Any]:
    """Send tokens from the agent wallet back to the user and record the withdrawal."""
    from dca_agent import send_tokens_to_user

    user_wallet = user_wallet.strip()
    tok = resolve_token(token)
    if "error" in tok:
        return tok

    amount = round(float(amount), 9)
    if amount <= 0:
        return {"error": "Withdraw amount must be greater than zero."}

    with _ledger_lock:
        withdrawable = get_user_token_withdrawable(user_wallet, tok["symbol"])
        if withdrawable + 1e-12 < amount:
            return {
                "error": (
                    f"Insufficient withdrawable {tok['symbol']}. "
                    f"Withdrawable: {withdrawable}, requested: {amount}. "
                    f"Only unused deposits and DCA-acquired tokens can be withdrawn."
                ),
                "withdrawable": withdrawable,
                "requested": amount,
                "token": tok["symbol"],
            }

        transfer = send_tokens_to_user(
            user_wallet,
            tok["mint"],
            amount,
            tok["decimals"],
            signing_user_wallet=user_wallet,
        )
        if transfer.get("error"):
            return transfer
        if transfer.get("status") != "success":
            return transfer

        now = datetime.now(timezone.utc).isoformat()
        signature = transfer.get("signature")
        record = {
            "id": str(uuid.uuid4())[:8],
            "user_wallet": user_wallet,
            "agent_wallet": get_wallet_pubkey(user_wallet),
            "signature": signature,
            "token": tok["symbol"],
            "mint": tok["mint"],
            "amount": amount,
            "direction": "withdraw",
            "reference_type": "withdraw",
            "reference_id": (signature or "withdraw")[:128],
            "status": "confirmed",
            "verified_at": now,
            "explorer_url": transfer.get("explorer_url"),
        }
        insert_ledger_entry(record)

    return {
        "status": "success",
        "withdraw": record,
        "signature": signature,
        "explorer_url": transfer.get("explorer_url"),
        "balances": get_user_balances(user_wallet),
    }


def check_user_can_spend(user_wallet: str, input_token: str, amount: float) -> dict[str, Any]:
    """Ensure a user cannot spend more than they have deposited (minus prior plan spends)."""
    if not user_wallet or not str(user_wallet).strip():
        return {
            "error": (
                "user_wallet is required. Each user may only spend their own verified deposits."
            ),
        }

    tok = resolve_token(input_token)
    if "error" in tok:
        return tok

    amount = float(amount)
    if amount <= 0:
        return {"error": "Amount must be greater than zero."}

    totals = get_user_token_spend_totals(user_wallet.strip(), tok["symbol"])
    available = totals["available_to_spend"]
    if available + 1e-12 < amount:
        return {
            "error": (
                f"Insufficient {tok['symbol']} balance for this user. "
                f"Deposited: {totals['deposited']}, already spent: {totals['spent']}, "
                f"available: {available}, requested: {amount}. "
                f"Deposit more {tok['symbol']} to the AI Agent wallet first."
            ),
            "deposited": totals["deposited"],
            "spent": totals["spent"],
            "available": available,
            "requested": amount,
            "user_wallet": user_wallet.strip(),
            "token": tok["symbol"],
        }

    return {
        "ok": True,
        "deposited": totals["deposited"],
        "spent": totals["spent"],
        "available": available,
        "requested": amount,
        "token": tok["symbol"],
        "user_wallet": user_wallet.strip(),
    }


def check_plan_budget(
    user_wallet: str,
    input_token: str,
    total_budget: Optional[float],
    amount_per_buy: float,
    max_executions: Optional[int],
) -> dict[str, Any]:
    if not user_wallet or not str(user_wallet).strip():
        return {
            "error": "user_wallet is required. User must connect wallet and deposit to the AI Agent wallet first.",
        }

    user_wallet = user_wallet.strip()
    tok = resolve_token(input_token)
    if "error" in tok:
        return tok

    balances = get_user_balances(user_wallet)
    available = 0.0
    deposited = 0.0
    spent = 0.0
    for row in balances.get("balances", []):
        if row["token"] == tok["symbol"]:
            available = float(row["available"])
            deposited = float(row["deposited"])
            spent = float(row["spent_in_plans"])
            break

    if total_budget is None and max_executions is not None:
        required = dca_execution_total_cost(float(amount_per_buy)) * int(max_executions)
    elif total_budget is not None:
        required = float(total_budget)
    else:
        required = dca_execution_total_cost(float(amount_per_buy))

    spendable = round(max(deposited - spent, 0.0), 9)
    if spendable + 1e-12 < required:
        return {
            "error": (
                f"Insufficient {tok['symbol']} balance. "
                f"Deposited: {deposited}, already spent: {spent}, "
                f"available for new plans: {spendable}, required: {required}. "
                f"Deposit {tok['symbol']} to the AI Agent wallet first."
            ),
            "deposited": deposited,
            "spent": spent,
            "available": spendable,
            "required": required,
            "user_wallet": user_wallet,
        }

    if available + 1e-12 < required:
        return {
            "error": (
                f"Insufficient {tok['symbol']} balance. "
                f"Available: {available}, required: {required}. "
                f"Deposit {tok['symbol']} to the AI Agent wallet first."
            ),
            "available": available,
            "required": required,
            "user_wallet": user_wallet,
        }

    return {
        "ok": True,
        "available": available,
        "required": required,
        "token": tok["symbol"],
    }


def _explorer_url(signature: str) -> str:
    from dca_agent import SOLANA_CLUSTER

    cluster = SOLANA_CLUSTER.lower()
    base = f"https://explorer.solana.com/tx/{signature}"
    if cluster in ("mainnet", "mainnet-beta"):
        return base
    if cluster == "devnet":
        return f"{base}?cluster=devnet"
    return f"{base}?cluster={cluster}"
