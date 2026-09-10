"""
Per-user deposit ledger for the Hedge Fund agent wallet (live trading).
Users may deposit SOL only. Strategies fund from SOL and liquidate back to SOL.
Leftover USDC (from older strategies) can still be withdrawn.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from db import insert_ledger_entry, load_ledger_for_user
from dca_agent import resolve_token, sol_rpc
from hedge_fund_assets import SOL_MINT, USDC_MINT

HF_MGMT_FEE_RATE = float(os.environ.get("HF_MGMT_FEE_RATE", "0.01"))  # 1% at start
HF_PERF_FEE_RATE = float(os.environ.get("HF_PERF_FEE_RATE", "0.10"))  # 10% of profit on liquidate
HF_MAX_STRATEGY_USDC = float(os.environ.get("HF_MAX_STRATEGY_USDC", "100"))
HF_MIN_PER_ASSET_USDC = float(os.environ.get("HF_MIN_PER_ASSET_USDC", "5"))
ALLOWED_DEPOSIT_TOKENS = {"SOL"}
ALLOWED_FUNDING_TOKENS = {"SOL"}
ALLOWED_WITHDRAW_TOKENS = {"SOL", "USDC"}  # USDC kept for leftover balances from older strategies
DEFAULT_FUNDING_TOKEN = "SOL"
DEFAULT_LIQUIDATION_ASSET = "SOL"


def load_hf_keypair():
    from dca_agent import HAS_SOLDERS, Keypair

    if not HAS_SOLDERS:
        return None
    raw = (
        os.environ.get("HEDGE_FUND_WALLET_PRIVATE_KEY", "").strip()
        or os.environ.get("HF_WALLET_PRIVATE_KEY", "").strip()
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


def _shared_hf_pubkey() -> Optional[str]:
    kp = load_hf_keypair()
    return str(kp.pubkey()) if kp else None


def get_hf_wallet_pubkey(user_wallet: Optional[str] = None) -> Optional[str]:
    user_wallet = (user_wallet or "").strip()
    if user_wallet:
        from circle_dca_wallets import get_agent_wallet_address

        address = get_agent_wallet_address(user_wallet, "hedge_fund")
        if address:
            return address
    return _shared_hf_pubkey()


def _hf_agent_addresses(user_wallet: str) -> set[str]:
    addresses: set[str] = set()
    primary = get_hf_wallet_pubkey(user_wallet)
    if primary:
        addresses.add(primary)
    shared = _shared_hf_pubkey()
    if shared:
        addresses.add(shared)
    return addresses


def get_hf_agent_wallet_info(user_wallet: Optional[str] = None) -> dict[str, Any]:
    from dca_agent import SOLANA_CLUSTER, SOLANA_RPC
    from circle_dca_wallets import circle_dca_enabled, get_agent_wallet_address

    user_wallet = (user_wallet or "").strip()
    wallet = get_hf_wallet_pubkey(user_wallet) if user_wallet else _shared_hf_pubkey()
    provider = "local"
    circle_error = None
    per_user = False
    if user_wallet and circle_dca_enabled():
        circle_addr = get_agent_wallet_address(user_wallet, "hedge_fund")
        if circle_addr:
            wallet = circle_addr
            provider = "circle"
            per_user = True
        else:
            circle_error = (
                "Circle Hedge Fund wallet provisioning failed. Check CIRCLE_ENTITY_SECRET. "
                "Falling back to shared HEDGE_FUND_WALLET_PRIVATE_KEY if configured."
            )

    result = {
        "agent_wallet": wallet,
        "configured": bool(wallet),
        "wallet_provider": provider,
        "per_user_wallet": per_user,
        "cluster": SOLANA_CLUSTER,
        "rpc": SOLANA_RPC,
        "allowed_tokens": sorted(ALLOWED_DEPOSIT_TOKENS),
        "allowed_withdraw_tokens": sorted(ALLOWED_WITHDRAW_TOKENS),
        "max_strategy_usdc": HF_MAX_STRATEGY_USDC,
        "min_per_asset_usdc": HF_MIN_PER_ASSET_USDC,
        "management_fee_pct": HF_MGMT_FEE_RATE * 100,
        "performance_fee_pct": HF_PERF_FEE_RATE * 100,
        "usdc_mint": USDC_MINT,
        "sol_mint": SOL_MINT,
        "live_trading": True,
        "paper_trading": True,
    }
    if circle_error and not per_user:
        result["circle_error"] = circle_error
    return result


def _hf_rows(user_wallet: str) -> list[dict[str, Any]]:
    addresses = _hf_agent_addresses(user_wallet)
    if not addresses:
        return []
    rows = load_ledger_for_user(user_wallet.strip())
    return [r for r in rows if r.get("agent_wallet") in addresses]


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


def _reserved_for_live_strategies(
    user_wallet: str,
    token_symbol: str,
    exclude_strategy_id: Optional[str] = None,
    strategies: Optional[list[dict[str, Any]]] = None,
) -> float:
    """
    Reserve capital for pending live strategies (not yet spent on-chain).
    Active strategies already debit the ledger via spend — do not double-count.
    """
    from hedge_fund_paper import list_strategies

    token_symbol = token_symbol.strip().upper()
    rows = strategies if strategies is not None else list_strategies(user_wallet)
    reserved = 0.0
    for s in rows:
        if s.get("id") == exclude_strategy_id:
            continue
        rules = s.get("rules") or {}
        if (rules.get("trading_mode") or s.get("trading_mode") or "paper") != "live":
            continue
        # Pending proposals do not lock funds — spend happens only on confirm.
        # Failed/dismissed/closed never reserve.
        if s.get("status") not in ("paused",):
            continue
        funding = str(rules.get("funding_token") or DEFAULT_FUNDING_TOKEN).upper()
        if funding != token_symbol:
            continue
        # Skip if already deployed (has live spend reference)
        if float(rules.get("deploy_usd") or 0) > 0 or float(rules.get("mgmt_fee_usd") or 0) > 0:
            continue
        cap = float(rules.get("capital_usd") or 0)
        if funding == "USDC":
            reserved += max(0.0, cap)
        else:
            px = sol_usd_price() or 0.0
            if px > 0:
                reserved += max(0.0, round(cap / px, 9))
    return round(reserved, 9)


def get_hf_user_balances(
    user_wallet: str, exclude_strategy_id: Optional[str] = None
) -> dict[str, Any]:
    from hedge_fund_paper import list_strategies, reconcile_stuck_live_strategies

    # Return unused spend from failed deploys before computing available
    try:
        reconcile_stuck_live_strategies(user_wallet)
    except Exception:
        pass

    rows = _hf_rows(user_wallet)
    strategies = list_strategies(user_wallet)
    tokens = ["SOL"]
    usdc_totals = _ledger_totals(user_wallet, "USDC", rows)
    if (
        usdc_totals["deposited"] > 0
        or usdc_totals["spent_ledger"] > 0
        or usdc_totals["withdrawn"] > 0
    ):
        tokens.append("USDC")
    balances = []
    for token in tokens:
        totals = _ledger_totals(user_wallet, token, rows)
        reserved = _reserved_for_live_strategies(
            user_wallet, token, exclude_strategy_id, strategies=strategies
        )
        deposited = totals["deposited"]
        spent = totals["spent_ledger"]
        withdrawn = totals["withdrawn"]
        available = round(max(0.0, deposited - spent - withdrawn - reserved), 9)
        balances.append(
            {
                "token": token,
                "mint": USDC_MINT if token == "USDC" else SOL_MINT,
                "deposited": deposited,
                "spent_in_strategies": spent,
                "reserved_for_strategies": reserved,
                "reserved_for_plans": reserved,  # DCA-shaped field for shared UI patterns
                "withdrawn": withdrawn,
                "available": available,
                "withdrawable": available,
            }
        )
    return {
        "user_wallet": user_wallet.strip(),
        "agent_wallet": get_hf_wallet_pubkey(user_wallet),
        "balances": balances,
        "max_strategy_usdc": HF_MAX_STRATEGY_USDC,
        "funding_token": DEFAULT_FUNDING_TOKEN,
        "liquidation_asset": DEFAULT_LIQUIDATION_ASSET,
    }


def check_hf_can_spend(
    user_wallet: str,
    token: str,
    amount: float,
    exclude_strategy_id: Optional[str] = None,
) -> dict[str, Any]:
    token = token.strip().upper()
    if token not in ALLOWED_FUNDING_TOKENS:
        return {"error": f"Only SOL can fund strategies (got {token})."}
    balances = get_hf_user_balances(user_wallet, exclude_strategy_id=exclude_strategy_id)
    amount = float(amount)
    for row in balances.get("balances") or []:
        if str(row.get("token", "")).upper() == token:
            available = float(row.get("available") or 0)
            if available + 1e-12 >= amount:
                return {"ok": True, "available": available, "token": token}
            return {
                "error": (
                    f"Insufficient {token}. Available: {available}, requested: {amount}. "
                    f"Deposit more {token} to the Hedge Fund wallet."
                ),
                "available": available,
            }
    return {"error": f"No deposited {token}.", "available": 0.0}


def record_hf_spend(
    user_wallet: str,
    token: str,
    amount: float,
    *,
    reference_id: str,
    reference_type: str = "hf_strategy",
    signature: Optional[str] = None,
) -> dict[str, Any]:
    if amount <= 0:
        return {"spent": 0.0}
    tok = resolve_token(token)
    if "error" in tok:
        return tok
    agent_wallet = get_hf_wallet_pubkey(user_wallet)
    if not agent_wallet:
        return {"error": "Hedge Fund wallet not configured."}
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
            "reference_type": reference_type,
            "reference_id": reference_id[:128],
            "status": "confirmed",
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return {"spent": float(amount), "token": tok["symbol"]}


def record_hf_credit(
    user_wallet: str,
    token: str,
    amount: float,
    *,
    reference_id: str,
    reference_type: str = "hf_liquidate_return",
    signature: Optional[str] = None,
) -> dict[str, Any]:
    if amount <= 0:
        return {"credited": 0.0}
    tok = resolve_token(token)
    if "error" in tok:
        return tok
    agent_wallet = get_hf_wallet_pubkey(user_wallet)
    if not agent_wallet:
        return {"error": "Hedge Fund wallet not configured."}
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
            "reference_type": reference_type,
            "reference_id": reference_id[:128],
            "status": "confirmed",
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return {"credited": float(amount), "token": tok["symbol"]}


def _strategy_deploy_spend_outstanding(
    user_wallet: str, strategy_id: str
) -> list[dict[str, Any]]:
    """Return unrefunded deploy spends for a strategy (token, amount)."""
    rows = _hf_rows(user_wallet)
    spent_by_token: dict[str, float] = {}
    refunded_by_token: dict[str, float] = {}
    spend_types = {"hf_strategy_deploy", "hf_mgmt_fee", "hf_strategy"}
    for row in rows:
        if row.get("status") != "confirmed":
            continue
        ref = str(row.get("reference_id") or "")
        rtype = str(row.get("reference_type") or "")
        token = str(row.get("token") or "").upper()
        amount = float(row.get("amount") or 0)
        if not token or amount <= 0:
            continue
        belongs = strategy_id in ref
        if row.get("direction") == "spend" and belongs and rtype in spend_types:
            spent_by_token[token] = spent_by_token.get(token, 0) + amount
        if row.get("direction") == "deposit" and belongs and "refund" in rtype:
            refunded_by_token[token] = refunded_by_token.get(token, 0) + amount
    out = []
    for token, spent in spent_by_token.items():
        due = round(max(0.0, spent - refunded_by_token.get(token, 0.0)), 9)
        if due > 1e-12:
            out.append({"token": token, "amount": due})
    return out


def refund_failed_hf_deploy(user_wallet: str, strategy_id: str) -> dict[str, Any]:
    """Credit back ledger spend when Jupiter never filled the sleeve (tokens still in HF wallet)."""
    outstanding = _strategy_deploy_spend_outstanding(user_wallet, strategy_id)
    credited = []
    for item in outstanding:
        rec = record_hf_credit(
            user_wallet,
            item["token"],
            item["amount"],
            reference_id=f"{strategy_id}-deploy-refund",
            reference_type="hf_strategy_deploy_refund",
        )
        credited.append({**item, **rec})
    return {"refunded": bool(credited), "credits": credited}


def verify_and_record_hf_deposit(signature: str, user_wallet: str) -> dict[str, Any]:
    from deposit_ledger import _ledger_lock, _parse_verified_user_deposits, _user_in_transaction, _valid_signature

    signature = signature.strip()
    user_wallet = user_wallet.strip()
    agent_wallet = get_hf_wallet_pubkey(user_wallet)
    if not agent_wallet:
        return {"error": "Hedge Fund wallet is not configured (HEDGE_FUND_WALLET_PRIVATE_KEY)."}
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
                "balances": get_hf_user_balances(user_wallet),
            }

        tx = None
        for attempt in range(10):
            commitment = "finalized" if attempt >= 4 else "confirmed"
            tx = sol_rpc(
                "getTransaction",
                [signature, {"encoding": "jsonParsed", "commitment": commitment, "maxSupportedTransactionVersion": 0}],
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

        # Returns a list of transfers (same helper as DCA / Volume) — not a dict
        inbound = _parse_verified_user_deposits(tx, user_wallet, agent_wallet)
        if not inbound:
            return {
                "error": (
                    "No verifiable SOL deposit from your wallet to the Hedge Fund wallet "
                    "was found in this transaction."
                ),
                "status": "rejected",
            }

        now = datetime.now(timezone.utc).isoformat()
        records = []
        for transfer in inbound:
            mint = str(transfer.get("mint") or "")
            tok = resolve_token(mint if mint else str(transfer.get("token") or ""))
            if "error" in tok:
                continue
            token = str(tok.get("symbol") or "").upper()
            if token not in ALLOWED_DEPOSIT_TOKENS:
                return {
                    "error": f"Only SOL deposits are accepted (got {token}).",
                    "status": "rejected",
                }
            record = {
                "id": str(uuid.uuid4())[:8],
                "user_wallet": user_wallet,
                "agent_wallet": agent_wallet,
                "signature": signature,
                "token": token,
                "mint": tok.get("mint") or mint,
                "amount": float(transfer["amount"]),
                "direction": "deposit",
                "reference_type": "hf_deposit",
                "reference_id": signature[:128],
                "status": "confirmed",
                "verified_at": now,
                "explorer_url": f"https://explorer.solana.com/tx/{signature}",
            }
            insert_ledger_entry(record)
            records.append(record)
        if not records:
            return {
                "error": "No SOL transfer to the Hedge Fund wallet found in this transaction.",
                "status": "rejected",
            }
        return {
            "status": "confirmed",
            "deposits": records,
            "balances": get_hf_user_balances(user_wallet),
            "message": "Deposit verified and credited to your balance.",
        }


def withdraw_hf_tokens(user_wallet: str, token: str, amount: float) -> dict[str, Any]:
    from deposit_ledger import _ledger_lock
    from dca_agent import send_tokens_to_user

    user_wallet = user_wallet.strip()
    token = token.strip().upper()
    if token not in ALLOWED_WITHDRAW_TOKENS:
        return {"error": "Only SOL (or leftover USDC) can be withdrawn."}
    tok = resolve_token(token)
    if "error" in tok:
        return tok
    amount = round(float(amount), 9)
    if amount <= 0:
        return {"error": "Withdraw amount must be greater than zero."}

    balances = get_hf_user_balances(user_wallet)
    withdrawable = 0.0
    for row in balances.get("balances") or []:
        if str(row.get("token", "")).upper() == token:
            withdrawable = float(row.get("withdrawable") or 0)
            break

    with _ledger_lock:
        if withdrawable + 1e-12 < amount:
            return {
                "error": (
                    f"Insufficient withdrawable {token}. Withdrawable: {withdrawable}, requested: {amount}. "
                    "Funds reserved by active strategies cannot be withdrawn until liquidated/completed."
                ),
                "withdrawable": withdrawable,
            }
        transfer = send_tokens_to_user(
            user_wallet,
            tok["mint"],
            amount,
            tok["decimals"],
            signing_user_wallet=user_wallet,
            agent_type="hedge_fund",
        )
        if transfer.get("error") or transfer.get("status") != "success":
            return transfer
        signature = transfer.get("signature")
        record = {
            "id": str(uuid.uuid4())[:8],
            "user_wallet": user_wallet,
            "agent_wallet": get_hf_wallet_pubkey(user_wallet),
            "signature": signature,
            "token": tok["symbol"],
            "mint": tok["mint"],
            "amount": amount,
            "direction": "withdraw",
            "reference_type": "hf_withdraw",
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
        "balances": get_hf_user_balances(user_wallet),
    }


def list_hf_user_ledger(user_wallet: str, limit: int = 50) -> list[dict[str, Any]]:
    rows = _hf_rows(user_wallet)
    rows.sort(key=lambda r: r.get("verified_at") or "", reverse=True)
    return rows[:limit]


def sol_usd_price() -> Optional[float]:
    try:
        from dca_agent import get_token_price

        p = get_token_price("SOL")
        if isinstance(p, dict):
            return float(p.get("price_usd") or p.get("usd_price") or 0) or None
        return float(p) if p else None
    except Exception:
        return None


def usdc_notional_from_funding(token: str, amount: float) -> dict[str, Any]:
    """Convert funding amount to USDC notional for the $100 cap check."""
    token = token.strip().upper()
    amount = float(amount)
    if token == "USDC":
        return {"usdc_notional": amount, "funding_token": "USDC", "funding_amount": amount}
    if token == "SOL":
        px = sol_usd_price()
        if not px:
            return {"error": "Could not price SOL in USD"}
        return {
            "usdc_notional": round(amount * px, 6),
            "funding_token": "SOL",
            "funding_amount": amount,
            "sol_usd": px,
        }
    return {"error": f"Unsupported funding token {token}"}
