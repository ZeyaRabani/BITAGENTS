"""
Multi-wallet DCA — real integration, running alongside the existing pooled
flow (per agent/new/docs/per-user-wallets-scoping.md's recommended sequencing:
new path first, old path untouched, no big-bang migration).

Every function here reads/writes a user's OWN derived wallet
(agent_wallets.py) directly on-chain — never the shared pooled agent wallet,
and never trusts an off-chain ledger as the source of truth for "how much
can this user spend." Real on-chain balance is checked immediately before
every mutating action.

Deliberately plain, deterministic functions — no LLM anywhere in this file.
Given the hallucinated-plan bug found in the pooled chat flow, this new
fund-critical path is built to never have that failure mode available to it
in the first place: every function either does the real thing or returns a
real error, there is no free-text step in between where a model could
describe success without having caused it.

Plans created here are tagged wallet_mode='multiwallet' in dca_plans, so the
scheduler (dca_agent._scheduler_loop) knows to sign with this user's derived
keypair instead of the pooled DCA_WALLET_PRIVATE_KEY.

Platform fee: since each user's funds now live in their own separate wallet,
the 0.5% DCA fee can no longer be pure bookkeeping the way it was in the
pooled model (there was never anywhere else for it to "go" -- it just
stayed in the one shared wallet). Here it's a second, real, small transfer
out of the user's wallet to a fee-collector address on every successful buy.
The existing pooled agent wallet is reused as that collector -- under the
new model it stops holding user funds and becomes purely the platform's fee
wallet, which is a clean, deliberate reuse rather than a new piece of
infrastructure to stand up.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import agent_wallets
from dca_agent import (
    SOL_ADDRESS_FULL,
    _build_and_execute_swap,
    _lamports,
    _parse_interval,
    get_wallet_pubkey,
    resolve_token,
    send_tokens_to_user,
    sol_rpc,
)
from db import find_plan, insert_plan, update_plan
from deposit_ledger import DCA_PLATFORM_FEE_RATE, dca_platform_fee, insert_ledger_entry

AGENT = "dca"


def get_deposit_address(user_wallet: str) -> str:
    """This user's dedicated derived deposit address for the DCA agent.
    Different for every user, different from the pooled agent wallet, and
    different from this same user's Volume/EasyA derived addresses."""
    return agent_wallets.get_user_wallet_pubkey(AGENT, user_wallet)


def get_sol_balance_lamports(user_wallet: str) -> int:
    address = get_deposit_address(user_wallet)
    result = sol_rpc("getBalance", [address, {"commitment": "confirmed"}])
    return int((result or {}).get("value") or 0)


def get_token_balance_raw(user_wallet: str, mint: str, decimals: int) -> float:
    """Real on-chain balance of a specific SPL token in this user's derived
    wallet, in human units (not raw base units)."""
    address = get_deposit_address(user_wallet)
    result = sol_rpc("getTokenAccountsByOwner", [address, {"mint": mint}, {"encoding": "jsonParsed"}])
    total_raw = 0
    for entry in (result or {}).get("value") or []:
        try:
            info = entry["account"]["data"]["parsed"]["info"]["tokenAmount"]
            total_raw += int(info["amount"])
        except (KeyError, TypeError, ValueError):
            continue
    return total_raw / (10**decimals) if decimals else float(total_raw)


def get_balances(user_wallet: str, extra_tokens: Optional[list[str]] = None) -> dict[str, Any]:
    """Real on-chain balances for this user's derived DCA wallet: SOL, plus
    any tokens named in extra_tokens (e.g. the output token of an active plan) --
    not a ledger sum, the actual current chain state."""
    address = get_deposit_address(user_wallet)
    sol_lamports = get_sol_balance_lamports(user_wallet)
    balances = [
        {
            "token": "SOL",
            "mint": SOL_ADDRESS_FULL,
            "balance": sol_lamports / 1_000_000_000,
            "is_active": agent_wallets.is_wallet_active(sol_lamports),
        }
    ]
    for token in extra_tokens or []:
        resolved = resolve_token(token)
        if "error" in resolved:
            continue
        bal = get_token_balance_raw(user_wallet, resolved["mint"], resolved["decimals"])
        balances.append({"token": resolved["symbol"], "mint": resolved["mint"], "balance": bal})
    return {
        "user_wallet": user_wallet,
        "deposit_address": address,
        "balances": balances,
        "min_sol_to_activate_lamports": agent_wallets.MIN_SOL_TO_ACTIVATE_LAMPORTS,
    }


def create_plan(
    user_wallet: str,
    output_token: str,
    amount_per_buy: float,
    interval: str,
    max_executions: int,
) -> dict[str, Any]:
    """Create a real multi-wallet DCA plan. Checks the user's OWN derived
    wallet's real on-chain SOL balance -- not a ledger -- before allowing it,
    so a plan can never be created that the wallet can't actually afford."""
    user_wallet = user_wallet.strip()
    if not user_wallet:
        return {"error": "user_wallet is required."}

    amount_per_buy = float(amount_per_buy)
    if amount_per_buy <= 0:
        return {"error": "amount_per_buy must be greater than zero."}
    max_executions = int(max_executions)
    if max_executions <= 0:
        return {"error": "max_executions must be at least 1."}

    try:
        interval_minutes = _parse_interval(interval)
    except ValueError as exc:
        return {"error": str(exc)}

    out = resolve_token(output_token)
    if "error" in out:
        return out
    sol = resolve_token("SOL")

    address = get_deposit_address(user_wallet)
    balance_lamports = get_sol_balance_lamports(user_wallet)
    fee = dca_platform_fee(amount_per_buy)
    required_for_one_buy = _lamports(amount_per_buy + fee, sol["decimals"])
    if balance_lamports < required_for_one_buy + agent_wallets.SOLANA_BASE_FEE_LAMPORTS:
        return {
            "error": (
                f"Insufficient SOL in your deposit address for even one buy. "
                f"Balance: {balance_lamports / 1e9:.6f} SOL, need at least "
                f"{(required_for_one_buy + agent_wallets.SOLANA_BASE_FEE_LAMPORTS) / 1e9:.6f} SOL "
                f"(buy amount + {DCA_PLATFORM_FEE_RATE*100:.1f}% platform fee + network fee)."
            ),
            "deposit_address": address,
            "balance_sol": balance_lamports / 1e9,
        }

    now = datetime.now(timezone.utc)
    plan = {
        "id": uuid.uuid4().hex[:12],
        "user_wallet": user_wallet,
        "name": f"{sol['symbol']} -> {out['symbol']} DCA (multi-wallet)",
        "input_token": sol["symbol"],
        "output_token": out["symbol"],
        "input_mint": sol["mint"],
        "output_mint": out["mint"],
        "amount_per_buy": amount_per_buy,
        "interval": interval,
        "interval_minutes": interval_minutes,
        "total_budget": None,
        "spent_so_far": 0.0,
        "max_executions": max_executions,
        "executions_count": 0,
        "slippage_bps": 100,
        "status": "active",
        "created_at": now.isoformat(),
        "next_execution_at": now.isoformat(),
        "executions": [],
        "wallet_mode": "multiwallet",
    }
    insert_plan(plan)
    return {"status": "created", "plan": plan, "deposit_address": address}


def execute_plan_now(plan_id: str) -> dict[str, Any]:
    """Execute one buy for a multi-wallet plan: swap from the plan owner's
    OWN derived wallet, using their own derived keypair as signer -- never
    the pooled agent wallet. Called by the scheduler for due plans, or
    directly for an immediate/dry test."""
    plan = find_plan(plan_id)
    if not plan:
        return {"error": f"Plan '{plan_id}' not found."}
    if plan.get("wallet_mode") != "multiwallet":
        return {"error": "This is not a multi-wallet plan."}
    if plan.get("status") != "active":
        return {"error": f"Plan is {plan.get('status')}, not active."}

    user_wallet = plan["user_wallet"]
    amount = float(plan["amount_per_buy"])
    fee = dca_platform_fee(amount)

    keypair = agent_wallets.get_user_wallet_keypair(AGENT, user_wallet)
    wallet_pubkey = str(keypair.pubkey())

    sol = resolve_token("SOL")
    balance_lamports = get_sol_balance_lamports(user_wallet)
    required = _lamports(amount + fee, sol["decimals"]) + agent_wallets.SOLANA_BASE_FEE_LAMPORTS * 2
    if balance_lamports < required:
        return {
            "error": (
                f"Insufficient SOL to execute this buy. Balance: {balance_lamports/1e9:.6f} SOL, "
                f"need at least {required/1e9:.6f} SOL."
            ),
            "plan_id": plan_id,
        }

    raw_amount = _lamports(amount, sol["decimals"])
    swap_result = _build_and_execute_swap(
        sol["mint"], plan["output_mint"], raw_amount, wallet_pubkey, keypair, int(plan.get("slippage_bps", 100))
    )

    now = datetime.now(timezone.utc)
    exec_record = {
        "at": now.isoformat(),
        "amount": amount,
        "platform_fee": fee,
        "input_token": plan["input_token"],
        "output_token": plan["output_token"],
        "result": {k: v for k, v in swap_result.items() if k not in ("build_data", "quote")},
        "wallet_mode": "multiwallet",
    }

    if swap_result.get("status") != "success":
        executions = plan.get("executions", []) + [exec_record]
        update_plan(plan_id, {"executions": executions[-50:]})
        return {"plan_id": plan_id, "execution_failed": True, **swap_result}

    # Real fee transfer -- out of the user's own wallet, since it's the only
    # place this money exists under the multi-wallet model. Uses the user's
    # own derived keypair as signer, sending to the pooled wallet address
    # (now acting purely as the platform fee collector, holding no user funds).
    fee_collector = get_wallet_pubkey()
    fee_result = None
    if fee_collector and fee > 0:
        fee_result = send_tokens_to_user(fee_collector, sol["mint"], fee, sol["decimals"], signing_keypair=keypair)
        exec_record["fee_transfer"] = {
            k: v for k, v in (fee_result or {}).items() if k not in ("build_data", "quote")
        }

    interval_minutes = float(plan.get("interval_minutes", 1440))
    next_run = now + timedelta(minutes=interval_minutes)
    executions_count = int(plan.get("executions_count", 0)) + 1
    executions = plan.get("executions", []) + [exec_record]
    new_status = "completed" if executions_count >= int(plan.get("max_executions") or 0) else "active"

    update_plan(plan_id, {
        "executions_count": executions_count,
        "spent_so_far": round(float(plan.get("spent_so_far", 0)) + amount + fee, 9),
        "next_execution_at": next_run.isoformat(),
        "executions": executions[-50:],
        "status": new_status,
    })

    # Ledger entries are history/display only here -- the real balance is
    # always the on-chain wallet, checked fresh above, not this record.
    insert_ledger_entry({
        "user_wallet": user_wallet,
        "agent_wallet": wallet_pubkey,
        "signature": swap_result.get("signature"),
        "token": plan["output_token"],
        "mint": plan["output_mint"],
        "amount": swap_result.get("output_amount") or 0,
        "direction": "acquire",
        "reference_type": "multiwallet_swap",
        "reference_id": (swap_result.get("signature") or plan_id)[:128],
        "status": "confirmed",
        "verified_at": now.isoformat(),
    })

    swap_result["plan_id"] = plan_id
    swap_result["next_execution_at"] = next_run.isoformat()
    swap_result["fee_transfer"] = fee_result
    return swap_result


def withdraw(user_wallet: str, token: str, amount: float) -> dict[str, Any]:
    """Send from this user's OWN derived wallet back to their real wallet,
    signed with their own derived keypair. Checks real on-chain balance,
    always reserving one fee's worth so the wallet never tries to send more
    than it can afford to also pay for sending."""
    user_wallet = user_wallet.strip()
    tok = resolve_token(token)
    if "error" in tok:
        return tok
    amount = round(float(amount), 9)
    if amount <= 0:
        return {"error": "Withdraw amount must be greater than zero."}

    keypair = agent_wallets.get_user_wallet_keypair(AGENT, user_wallet)
    address = str(keypair.pubkey())

    is_sol = tok["mint"] == SOL_ADDRESS_FULL
    if is_sol:
        balance_lamports = get_sol_balance_lamports(user_wallet)
        max_spendable = agent_wallets.max_spendable_lamports(balance_lamports) / 1e9
        if amount > max_spendable + 1e-12:
            return {
                "error": (
                    f"Insufficient withdrawable SOL. Balance: {balance_lamports/1e9:.9f}, "
                    f"max withdrawable (reserving this transaction's own fee): {max_spendable:.9f}, "
                    f"requested: {amount}."
                ),
                "withdrawable": max_spendable,
            }
    else:
        available = get_token_balance_raw(user_wallet, tok["mint"], tok["decimals"])
        if amount > available + 1e-12:
            return {
                "error": f"Insufficient {tok['symbol']}. Balance: {available}, requested: {amount}.",
                "withdrawable": available,
            }
        sol_balance = get_sol_balance_lamports(user_wallet)
        if sol_balance < agent_wallets.SOLANA_BASE_FEE_LAMPORTS:
            return {
                "error": (
                    f"This wallet has no SOL left to pay the network fee for this withdrawal. "
                    f"Deposit at least {agent_wallets.SOLANA_BASE_FEE_LAMPORTS/1e9:.6f} SOL to "
                    f"{address} first."
                ),
            }

    transfer = send_tokens_to_user(user_wallet, tok["mint"], amount, tok["decimals"], signing_keypair=keypair)
    if transfer.get("error") or transfer.get("status") != "success":
        return transfer

    insert_ledger_entry({
        "user_wallet": user_wallet,
        "agent_wallet": address,
        "signature": transfer.get("signature"),
        "token": tok["symbol"],
        "mint": tok["mint"],
        "amount": amount,
        "direction": "withdraw",
        "reference_type": "multiwallet_withdraw",
        "reference_id": (transfer.get("signature") or "withdraw")[:128],
        "status": "confirmed",
        "verified_at": datetime.now(timezone.utc).isoformat(),
    })

    return {
        "status": "success",
        "signature": transfer.get("signature"),
        "explorer_url": transfer.get("explorer_url"),
        "token": tok["symbol"],
        "amount": amount,
    }
