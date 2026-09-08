"""
Per-user deposit ledger for the Volume Agent wallet (Meteora DLMM volume campaigns).
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from db import insert_ledger_entry, load_ledger_for_user
from dca_agent import resolve_token, sol_rpc, ASSOCIATED_TOKEN_PROGRAM_ID, TOKEN_PROGRAM_ID

VOLUME_PLATFORM_FEE_RATE = float(os.environ.get("VOLUME_PLATFORM_FEE_RATE", "0.0025"))

# A new SPL token account costs ~0.00204 SOL in rent (refunded only if closed).
# The first execution for a given base token may need to create one, so require
# the per-leg trade size to comfortably clear that cost plus tx fee headroom —
# otherwise the swap fails on-chain with "insufficient SOL for ATA rent" and the
# wallet still pays network fees on every failed attempt.
ATA_RENT_SOL = 0.00204
MIN_VOLUME_TRADE_SOL = float(os.environ.get("MIN_VOLUME_TRADE_SOL", "0.005"))
MAX_CONSECUTIVE_FAILURES = int(os.environ.get("VOLUME_MAX_CONSECUTIVE_FAILURES", "3"))


def validate_volume_trade_amount(trade_amount: float, quote_token: str) -> dict[str, Any]:
    """Reject trade sizes too small to survive ATA-rent overhead, before a campaign is ever created."""
    if (quote_token or "SOL").strip().upper() != "SOL":
        return {}
    amount = float(trade_amount or 0)
    if amount < MIN_VOLUME_TRADE_SOL:
        return {
            "error": (
                f"Trade size {amount} SOL is too small. A new token account costs "
                f"~{ATA_RENT_SOL} SOL in one-time rent, so trade size per leg must be "
                f"at least {MIN_VOLUME_TRADE_SOL} SOL to avoid failed swaps."
            )
        }
    return {}


def reclaim_token_account_rent(mint: str) -> dict[str, Any]:
    """
    Close the Volume Agent wallet's token account for `mint` and reclaim its
    ~0.00204 SOL rent, once a campaign trading that token has ended and no other
    active/paused campaign for the same user still needs the account open.

    Only closes accounts with a zero token balance — if dust remains, this is a
    no-op rather than risking an unintended forced sale to zero it out.
    """
    from dca_agent import HAS_SOLDERS, SOLANA_RPC

    if not HAS_SOLDERS:
        return {"error": "solders not installed."}

    keypair = load_volume_keypair()
    if not keypair:
        return {"error": "Volume agent wallet not configured (VOLUME_AGENT_WALLET_PRIVATE_KEY)."}

    try:
        from solders.pubkey import Pubkey
        from solders.instruction import AccountMeta, Instruction
        from solders.message import MessageV0
        from solders.hash import Hash
        from solders.transaction import VersionedTransaction
        import base64
    except ImportError as exc:
        return {"error": f"solders import failed: {exc}"}

    owner = keypair.pubkey()
    mint_pk = Pubkey.from_string(mint.strip())
    token_program = Pubkey.from_string(TOKEN_PROGRAM_ID)
    ata_program = Pubkey.from_string(ASSOCIATED_TOKEN_PROGRAM_ID)
    ata, _ = Pubkey.find_program_address(
        [bytes(owner), bytes(token_program), bytes(mint_pk)], ata_program
    )

    # Check the account actually exists and is empty before attempting to close it.
    try:
        balance_resp = sol_rpc("getTokenAccountBalance", [str(ata)])
    except Exception as exc:
        # Most common cause: the account was never created (nothing to reclaim).
        return {"status": "skipped", "reason": f"No token account to close: {exc}"}

    raw_balance = int((balance_resp or {}).get("value", {}).get("amount") or 0)
    if raw_balance > 0:
        return {
            "status": "skipped",
            "reason": f"Token account still holds a balance ({raw_balance} raw units) — not closing to avoid an unintended forced sale.",
        }

    # SPL Token "CloseAccount" instruction: opcode 9, no additional data.
    # Accounts: [account to close (writable), destination for reclaimed lamports (writable), owner (signer)]
    close_ix = Instruction(
        token_program,
        bytes([9]),
        [
            AccountMeta(ata, False, True),
            AccountMeta(owner, False, True),
            AccountMeta(owner, True, False),
        ],
    )

    try:
        bh_result = sol_rpc("getLatestBlockhash", [{"commitment": "finalized"}])
        blockhash = Hash.from_string(bh_result["value"]["blockhash"])
        msg = MessageV0.try_compile(owner, [close_ix], [], blockhash)
        tx = VersionedTransaction(msg, [keypair])
        encoded = base64.b64encode(bytes(tx)).decode("utf-8")
        sig = sol_rpc(
            "sendTransaction",
            [encoded, {"encoding": "base64", "skipPreflight": True, "preflightCommitment": "confirmed", "maxRetries": 3}],
        )
    except Exception as exc:
        return {"error": f"Close-account transaction failed: {exc}"}

    from dca_agent import _confirm_transaction, _is_mainnet

    confirm = _confirm_transaction(sig)
    if not confirm.get("confirmed"):
        return {"error": f"Close-account transaction did not confirm: {confirm.get('error', 'unknown')}", "signature": sig}

    cluster = "mainnet" if _is_mainnet() else "devnet"
    return {
        "status": "closed",
        "signature": sig,
        "mint": mint,
        "reclaimed_sol": ATA_RENT_SOL,
        "explorer_url": f"https://explorer.solana.com/tx/{sig}?cluster={cluster}",
    }


def load_volume_keypair():
    from dca_agent import HAS_SOLDERS, Keypair

    if not HAS_SOLDERS:
        return None
    raw = (
        os.environ.get("VOLUME_AGENT_WALLET_PRIVATE_KEY", "").strip()
        or os.environ.get("VOLUME_WALLET_PRIVATE_KEY", "").strip()
    )
    if not raw:
        return None
    try:
        import base58

        if raw.startswith("ll_"):
            raw = raw[3:]
        if raw.startswith("["):
            return Keypair.from_bytes(bytes(json.loads(raw)))
        return Keypair.from_bytes(base58.b58decode(raw))
    except Exception:
        return None


def get_volume_wallet_pubkey() -> Optional[str]:
    kp = load_volume_keypair()
    return str(kp.pubkey()) if kp else None


def volume_platform_fee(trade_amount: float) -> float:
    amount = float(trade_amount)
    if amount <= 0:
        return 0.0
    return round(amount * VOLUME_PLATFORM_FEE_RATE, 12)


def volume_execution_total_cost(trade_amount: float) -> float:
    amount = float(trade_amount)
    return round(amount + volume_platform_fee(amount), 12)


def _volume_rows(user_wallet: str) -> list[dict[str, Any]]:
    agent_wallet = get_volume_wallet_pubkey()
    if not agent_wallet:
        return []
    rows = load_ledger_for_user(user_wallet.strip())
    return [r for r in rows if r.get("agent_wallet") == agent_wallet]


def _ledger_totals(user_wallet: str, token_symbol: str, rows: list[dict[str, Any]]) -> dict[str, float]:
    token_symbol = token_symbol.strip().upper()
    deposited = spent = withdrawn = 0.0
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
        elif direction == "withdraw":
            withdrawn += amount
    return {
        "deposited": round(deposited, 9),
        "spent_ledger": round(spent, 9),
        "withdrawn": round(withdrawn, 9),
    }


def _reserved_for_campaigns(
    user_wallet: str, token_symbol: str, exclude_campaign_id: Optional[str] = None
) -> float:
    from db import load_all_volume_campaigns

    token_symbol = token_symbol.strip().upper()
    reserved = 0.0
    for campaign in load_all_volume_campaigns(user_wallet):
        if campaign.get("status") not in {"active", "provisioning", "paused"}:
            continue
        if exclude_campaign_id and campaign.get("id") == exclude_campaign_id:
            continue
        if str(campaign.get("quote_token", "SOL")).upper() != token_symbol:
            continue
        budget = campaign.get("total_budget")
        spent = float(campaign.get("spent_so_far") or 0)
        if budget is not None:
            reserved += max(0.0, float(budget) - spent)
        else:
            per_trade = float(campaign.get("trade_amount") or 0)
            remaining = max(
                0,
                int(campaign.get("max_executions") or 0) - int(campaign.get("executions_count") or 0),
            )
            reserved += per_trade * 2 * remaining
    return round(reserved, 9)


def get_volume_agent_wallet_info() -> dict[str, Any]:
    from dca_agent import SOLANA_CLUSTER, SOLANA_RPC

    return {
        "agent_wallet": get_volume_wallet_pubkey(),
        "cluster": SOLANA_CLUSTER,
        "rpc": SOLANA_RPC,
        "platform_fee_rate": VOLUME_PLATFORM_FEE_RATE,
        "pool_creation_cost_sol": float(os.environ.get("METEORA_POOL_CREATION_SOL", "0.02669")),
        "any_spl_token": True,
        "common_tokens": ["SOL", "USDC", "USDT"],
    }


def get_volume_user_balances(
    user_wallet: str, exclude_campaign_id: Optional[str] = None
) -> dict[str, Any]:
    from db import load_all_volume_campaigns

    rows = _volume_rows(user_wallet)
    plans = load_all_volume_campaigns(user_wallet)
    by_token: dict[str, dict[str, Any]] = {}
    for row in rows:
        token = str(row.get("token") or "").upper()
        if token:
            by_token[token] = {"token": token, "mint": row.get("mint")}
    for campaign in plans:
        for sym, mint_key in (
            (str(campaign.get("base_token") or "").upper(), "base_mint"),
            (str(campaign.get("quote_token") or "SOL").upper(), "quote_mint"),
        ):
            if sym and sym not in by_token:
                by_token[sym] = {"token": sym, "mint": campaign.get(mint_key)}

    balances = []
    for token, meta in sorted(by_token.items()):
        totals = _ledger_totals(user_wallet, token, rows)
        reserved = _reserved_for_campaigns(user_wallet, token, exclude_campaign_id=exclude_campaign_id)
        deposited = totals["deposited"]
        spent = totals["spent_ledger"]
        withdrawn = totals["withdrawn"]
        available = round(max(0.0, deposited - spent - withdrawn - reserved), 9)
        balances.append(
            {
                "token": token,
                "mint": meta.get("mint"),
                "deposited": deposited,
                "spent_in_campaigns": spent,
                "reserved_for_campaigns": reserved,
                "withdrawn": withdrawn,
                "available": available,
                "withdrawable": available,
            }
        )

    return {
        "user_wallet": user_wallet.strip(),
        "agent_wallet": get_volume_wallet_pubkey(),
        "balances": balances,
    }


def check_user_can_spend_volume(
    user_wallet: str, token: str, amount: float, exclude_campaign_id: Optional[str] = None
) -> dict[str, Any]:
    balances = get_volume_user_balances(user_wallet, exclude_campaign_id=exclude_campaign_id)
    token = token.strip().upper()
    amount = float(amount)
    for row in balances.get("balances") or []:
        if str(row.get("token", "")).upper() == token:
            available = float(row.get("available") or 0)
            if available + 1e-12 >= amount:
                return {"ok": True, "available": available}
            return {
                "error": (
                    f"Insufficient {token} balance. Available: {available}, requested: {amount}. "
                    f"Deposit more {token} to the Volume Agent wallet."
                ),
                "available": available,
            }
    return {
        "error": f"No deposited {token} balance. Deposit to the Volume Agent wallet first.",
        "available": 0.0,
    }


def record_volume_platform_fee(
    user_wallet: str,
    token: str,
    trade_amount: float,
    *,
    reference_id: str,
    signature: Optional[str] = None,
) -> dict[str, Any]:
    fee = volume_platform_fee(trade_amount)
    if fee <= 0:
        return {"fee": 0.0}
    tok = resolve_token(token)
    if "error" in tok:
        return tok
    agent_wallet = get_volume_wallet_pubkey()
    if not agent_wallet:
        return {"error": "Volume agent wallet not configured."}
    insert_ledger_entry(
        {
            "id": str(uuid.uuid4())[:8],
            "user_wallet": user_wallet.strip(),
            "agent_wallet": agent_wallet,
            "signature": signature,
            "token": tok["symbol"],
            "mint": tok["mint"],
            "amount": fee,
            "direction": "spend",
            "reference_type": "volume_fee",
            "reference_id": reference_id[:128],
            "status": "confirmed",
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return {"fee": fee, "token": tok["symbol"]}


def record_user_spend_volume(
    user_wallet: str,
    token: str,
    amount: float,
    *,
    reference_id: str,
    signature: Optional[str] = None,
) -> dict[str, Any]:
    tok = resolve_token(token)
    if "error" in tok:
        return tok
    agent_wallet = get_volume_wallet_pubkey()
    if not agent_wallet:
        return {"error": "Volume agent wallet not configured."}
    insert_ledger_entry(
        {
            "id": str(uuid.uuid4())[:8],
            "user_wallet": user_wallet.strip(),
            "agent_wallet": agent_wallet,
            "signature": signature,
            "token": tok["symbol"],
            "mint": tok["mint"],
            "amount": float(amount),
            "direction": "spend",
            "reference_type": "volume_swap",
            "reference_id": reference_id[:128],
            "status": "confirmed",
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return {"ok": True}


def record_user_credit_volume(
    user_wallet: str,
    token: str,
    amount: float,
    *,
    reference_id: str,
    signature: Optional[str] = None,
) -> dict[str, Any]:
    """Credit SOL/token back to a user's ledger balance without re-verifying an
    on-chain transfer — used when a swap the agent already executed (e.g. the
    sell leg of a volume cycle) returns funds to the same agent wallet. Without
    this, sell proceeds landed back in the wallet but were never reflected in
    the user's available balance, making every cycle look ~20x more expensive
    than its real net cost."""
    if amount <= 0:
        return {"credited": 0.0}
    tok = resolve_token(token)
    if "error" in tok:
        return tok
    agent_wallet = get_volume_wallet_pubkey()
    if not agent_wallet:
        return {"error": "Volume agent wallet not configured."}
    insert_ledger_entry(
        {
            "id": str(uuid.uuid4())[:8],
            "user_wallet": user_wallet.strip(),
            "agent_wallet": agent_wallet,
            "signature": signature,
            "token": tok["symbol"],
            "mint": tok["mint"],
            "amount": float(amount),
            "direction": "deposit",
            "reference_type": "volume_sell_return",
            "reference_id": reference_id[:128],
            "status": "confirmed",
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return {"credited": float(amount), "token": tok["symbol"]}


def verify_and_record_volume_deposit(signature: str, user_wallet: str) -> dict[str, Any]:
    from deposit_ledger import _ledger_lock, _parse_verified_user_deposits, _user_in_transaction, _valid_signature

    signature = signature.strip()
    user_wallet = user_wallet.strip()
    agent_wallet = get_volume_wallet_pubkey()
    if not agent_wallet:
        return {"error": "Volume Agent wallet is not configured on the server."}
    if not signature or not _valid_signature(signature):
        return {"error": "Valid transaction signature is required."}
    if not user_wallet:
        return {"error": "User wallet address is required."}

    with _ledger_lock:
        from db import deposit_exists, find_deposit_by_signature

        if deposit_exists(signature):
            existing = find_deposit_by_signature(signature)
            if existing and existing.get("user_wallet") != user_wallet:
                return {"error": "This deposit was already credited to another wallet.", "status": "rejected"}
            return {
                "status": "already_recorded",
                "deposit": existing,
                "balances": get_volume_user_balances(user_wallet),
            }

        tx = None
        for attempt in range(10):
            commitment = "finalized" if attempt >= 4 else "confirmed"
            tx = sol_rpc(
                "getTransaction",
                [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0, "commitment": commitment}],
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
            return {"error": "No verifiable deposit to the Volume Agent wallet was found."}

        now = datetime.now(timezone.utc).isoformat()
        records = []
        for transfer in inbound:
            tok = resolve_token(transfer["mint"])
            if "error" in tok:
                continue
            record = {
                "id": str(uuid.uuid4())[:8],
                "user_wallet": user_wallet,
                "agent_wallet": agent_wallet,
                "signature": signature,
                "token": tok["symbol"],
                "mint": transfer["mint"],
                "amount": float(transfer["amount"]),
                "direction": "deposit",
                "reference_type": "volume_deposit",
                "reference_id": signature[:128],
                "status": "confirmed",
                "verified_at": now,
                "explorer_url": f"https://explorer.solana.com/tx/{signature}",
            }
            insert_ledger_entry(record)
            records.append(record)
        if not records:
            return {"error": "Could not resolve deposited token metadata."}
        return {"status": "confirmed", "deposits": records, "balances": get_volume_user_balances(user_wallet)}


def withdraw_volume_tokens(user_wallet: str, token: str, amount: float) -> dict[str, Any]:
    from deposit_ledger import user_token_withdraw_lock
    from dca_agent import send_tokens_to_user

    user_wallet = user_wallet.strip()
    tok = resolve_token(token)
    if "error" in tok:
        return tok
    amount = round(float(amount), 9)
    if amount <= 0:
        return {"error": "Withdraw amount must be greater than zero."}

    with user_token_withdraw_lock(user_wallet, tok["symbol"]):
        rows = _volume_rows(user_wallet)
        ledger = _ledger_totals(user_wallet, tok["symbol"], rows)
        reserved = _reserved_for_campaigns(user_wallet, tok["symbol"])
        withdrawable = round(
            max(ledger["deposited"] - ledger["spent_ledger"] - ledger["withdrawn"] - reserved, 0.0), 9
        )
        if withdrawable + 1e-12 < amount:
            return {
                "error": f"Insufficient withdrawable {tok['symbol']}. Withdrawable: {withdrawable}, requested: {amount}.",
                "withdrawable": withdrawable,
            }
        transfer = send_tokens_to_user(
            user_wallet,
            tok["mint"],
            amount,
            tok["decimals"],
            signing_keypair=load_volume_keypair(),
        )
        if transfer.get("error") or transfer.get("status") != "success":
            return transfer
        signature = transfer.get("signature")
        record = {
            "id": str(uuid.uuid4())[:8],
            "user_wallet": user_wallet,
            "agent_wallet": get_volume_wallet_pubkey(),
            "signature": signature,
            "token": tok["symbol"],
            "mint": tok["mint"],
            "amount": amount,
            "direction": "withdraw",
            "reference_type": "volume_withdraw",
            "reference_id": (signature or "withdraw")[:128],
            "status": "confirmed",
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "explorer_url": transfer.get("explorer_url"),
        }
        insert_ledger_entry(record)
    return {"status": "success", "withdraw": record, "signature": signature, "balances": get_volume_user_balances(user_wallet)}


def list_volume_user_ledger(user_wallet: str, limit: int = 50) -> list[dict[str, Any]]:
    rows = _volume_rows(user_wallet)
    rows.sort(key=lambda r: r.get("verified_at") or "", reverse=True)
    return rows[:limit]
