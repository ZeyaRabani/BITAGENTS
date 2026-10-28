"""
Launch Agents: compose a custom agent and pay a fixed SOL launch fee.

User sends LAUNCH_COST_SOL to LAUNCH_FEE_WALLET (or TREASURY_PUBLIC_KEY),
then POSTs the form + tx signature. Backend verifies the transfer and
persists the agent definition.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from db import (
    count_agent_subscribers,
    create_agent_subscription,
    create_launched_agent,
    get_active_subscription,
    get_launched_agent,
    get_launched_agent_by_signature,
    get_subscription_by_signature,
    insert_ledger_entry,
    list_buyer_subscriptions,
    list_launched_agents,
    list_public_launched_agents,
    list_seller_subscriptions,
    update_launched_agent,
)
from dca_agent import SOL_ADDRESS_FULL, SOLANA_CLUSTER, sol_rpc
from deposit_ledger import (
    _explorer_url,
    _parse_verified_user_deposits,
    _user_in_transaction,
    _valid_signature,
)

def get_app_mode() -> str:
    """Runtime mode: development | testing | production (default)."""
    raw = (os.getenv("MODE") or os.getenv("APP_MODE") or "production").strip().lower()
    if raw in ("dev", "development"):
        return "development"
    if raw in ("test", "testing"):
        return "testing"
    return "production"


def get_launch_cost_sol() -> float:
    """Launch fee is 0 SOL in development; 1 SOL in testing/production."""
    if get_app_mode() == "development":
        return 0.0
    try:
        return float(os.getenv("LAUNCH_COST_SOL", "1") or "1")
    except (TypeError, ValueError):
        return 1.0


LAUNCH_COST_SOL = get_launch_cost_sol()

ALLOWED_LAUNCH_MODULES = {
    "web_search",
    "yahoo_news",
    "yahoo_market",
    "token_research",
    "whale_tracking",
    "user_wallet",
    "agent_wallet",
    "jupiter_swaps",
    "dca_scheduler",
    "limit_orders",
    "volume_campaigns",
    "solana_rpc",
    "easya_screener",
    # Watches a token for a price pattern (e.g. "drop X%, then bounce Y%")
    # and reports when it fires. Signal-only -- does not execute trades.
    # See signal_watcher.py. Execution wiring is a deliberate separate step.
    "price_signal_watch",
}

_launch_lock = threading.RLock()


def get_launch_fee_wallet() -> Optional[str]:
    """Public key that receives the 1 SOL launch fee."""
    for key in ("LAUNCH_FEE_WALLET", "TREASURY_PUBLIC_KEY"):
        val = (os.getenv(key) or "").strip()
        if val and "REPLACE_WITH" not in val:
            return val
    return None


def is_free_launch() -> bool:
    return get_app_mode() == "development" or get_launch_cost_sol() <= 0


def get_platform_fee_rate() -> float:
    try:
        rate = float(os.getenv("LAUNCH_PLATFORM_FEE_RATE", "0.10") or "0.10")
    except (TypeError, ValueError):
        rate = 0.10
    return min(max(rate, 0.0), 0.5)


def get_creator_payout_wallet(user_wallet: str) -> Optional[str]:
    """Circle launch wallet for the creator, or None if Circle is unavailable."""
    user_wallet = (user_wallet or "").strip()
    if not user_wallet:
        return None
    try:
        from circle_dca_wallets import get_agent_wallet_address

        return get_agent_wallet_address(user_wallet, "launch")
    except Exception as exc:
        print(f"  ⚠️  Creator Circle wallet unavailable: {exc}")
        return None


def get_launch_config() -> dict[str, Any]:
    fee_wallet = get_launch_fee_wallet()
    fee_sol = get_launch_cost_sol()
    mode = get_app_mode()
    free = is_free_launch()
    return {
        "mode": mode,
        "fee_sol": 0.0 if free else fee_sol,
        "fee_wallet": fee_wallet,
        "configured": True if free else bool(fee_wallet),
        "cluster": SOLANA_CLUSTER,
        "allowed_modules": sorted(ALLOWED_LAUNCH_MODULES),
        "payment_required": not free,
        "platform_fee_rate": get_platform_fee_rate(),
    }


def _normalize_modules(modules: Any) -> list[str]:
    if not modules:
        return []
    if not isinstance(modules, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in modules:
        mid = str(item or "").strip().lower()
        if not mid or mid in seen:
            continue
        if mid not in ALLOWED_LAUNCH_MODULES:
            continue
        seen.add(mid)
        out.append(mid)
    return out


def launch_agent(
    *,
    user_wallet: str,
    name: str,
    description: str,
    task: str,
    modules: list[str],
    signature: str,
    visibility: str = "private",
    price_per_month_sol: Optional[float] = None,
) -> dict[str, Any]:
    """
    Verify a 1 SOL fee transfer to the launch fee wallet and create the agent.
    """
    user_wallet = (user_wallet or "").strip()
    name = (name or "").strip()
    description = (description or "").strip()
    task = (task or "").strip()
    signature = (signature or "").strip()
    modules_norm = _normalize_modules(modules)
    fee_sol = get_launch_cost_sol()
    fee_wallet = get_launch_fee_wallet()
    visibility_norm = (visibility or "private").strip().lower()
    if visibility_norm not in ("public", "private"):
        return {"error": "Visibility must be public or private."}

    price: Optional[float] = None
    if visibility_norm == "public":
        try:
            price = float(price_per_month_sol) if price_per_month_sol is not None else None
        except (TypeError, ValueError):
            return {"error": "Price per month must be a number."}
        if price is None or not (price > 0):
            return {"error": "Public agents require a price per month greater than 0 SOL."}
        if price > 1000:
            return {"error": "Price per month must be 1000 SOL or less."}
    else:
        price = None

    if fee_sol > 0 and not fee_wallet:
        return {
            "error": (
                "Launch fee wallet is not configured. "
                "Set LAUNCH_FEE_WALLET (or TREASURY_PUBLIC_KEY) on the agents API."
            ),
        }
    if not user_wallet:
        return {"error": "User wallet is required."}
    if not name:
        return {"error": "Agent name is required."}
    if len(name) > 120:
        return {"error": "Agent name must be 120 characters or fewer."}
    if not task:
        return {"error": "Agent task is required."}
    if len(task) > 20000:
        return {"error": "Agent task is too long."}
    if len(description) > 2000:
        return {"error": "Agent description is too long."}
    if not modules_norm:
        return {"error": "Select at least one valid module."}

    now = datetime.now(timezone.utc).isoformat()
    agent_id = uuid.uuid4().hex[:16]
    dest_wallet = fee_wallet or user_wallet

    if fee_sol <= 0:
        signature = f"development-{uuid.uuid4().hex[:16]}"
        try:
            agent = create_launched_agent(
                {
                    "id": agent_id,
                    "user_wallet": user_wallet,
                    "name": name,
                    "description": description,
                    "task": task,
                    "modules": modules_norm,
                    "visibility": visibility_norm,
                    "price_per_month_sol": price,
                    "fee_sol": 0,
                    "fee_signature": signature,
                    "fee_wallet": dest_wallet,
                    "status": "active",
                    "explorer_url": None,
                }
            )
        except Exception as exc:
            return {"error": f"Failed to save launched agent: {exc}"}
        get_creator_payout_wallet(user_wallet)
        agent = _ensure_public_payment_wallet(agent)
        return {
            "status": "confirmed",
            "agent": _decorate_agent(agent),
            "fee_sol": 0,
            "paid_sol": 0,
            "message": f'Agent "{name}" launched successfully ({get_app_mode()}: no launch fee).',
        }

    if not signature:
        return {"error": "Transaction signature is required."}
    if not _valid_signature(signature):
        return {"error": "Invalid transaction signature format."}

    with _launch_lock:
        existing = get_launched_agent_by_signature(signature)
        if existing:
            if existing.get("user_wallet") != user_wallet:
                return {
                    "error": "This fee transaction was already used by another wallet.",
                    "status": "rejected",
                }
            return {
                "status": "already_recorded",
                "agent": existing,
                "message": "This launch fee was already recorded for your agent.",
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
                    "You can only launch with a fee you signed and sent."
                ),
            }

        inbound = _parse_verified_user_deposits(tx, user_wallet, dest_wallet)
        sol_transfers = [
            t for t in inbound if str(t.get("token", "")).upper() in ("SOL", "WSOL")
        ]
        if not sol_transfers:
            return {
                "error": (
                    f"No verifiable SOL transfer from your wallet to the launch fee wallet "
                    f"({dest_wallet[:4]}…{dest_wallet[-4:]}) was found."
                ),
            }

        paid = max(float(t.get("amount") or 0) for t in sol_transfers)
        if paid + 1e-9 < fee_sol:
            return {
                "error": (
                    f"Launch fee is {fee_sol} SOL. This transaction paid {paid} SOL."
                ),
            }

        explorer = _explorer_url(signature)

        agent = create_launched_agent(
            {
                "id": agent_id,
                "user_wallet": user_wallet,
                "name": name,
                "description": description,
                "task": task,
                "modules": modules_norm,
                "visibility": visibility_norm,
                "price_per_month_sol": price,
                "fee_sol": fee_sol,
                "fee_signature": signature,
                "fee_wallet": dest_wallet,
                "status": "active",
                "explorer_url": explorer,
            }
        )

        # Record fee in shared ledger (does not credit DCA spendable balance
        # when filtered by DCA/Circle agent wallets).
        insert_ledger_entry(
            {
                "id": uuid.uuid4().hex[:16],
                "user_wallet": user_wallet,
                "agent_wallet": dest_wallet,
                "signature": signature,
                "token": "SOL",
                "mint": SOL_ADDRESS_FULL,
                "amount": float(paid),
                "direction": "deposit",
                "reference_type": "launch_fee",
                "reference_id": agent_id,
                "status": "confirmed",
                "verified_at": now,
                "explorer_url": explorer,
            }
        )

        get_creator_payout_wallet(user_wallet)
        agent = _ensure_public_payment_wallet(agent)
        return {
            "status": "confirmed",
            "agent": _decorate_agent(agent),
            "fee_sol": fee_sol,
            "paid_sol": paid,
            "message": f'Agent "{name}" launched successfully.',
        }


def list_user_launched_agents(user_wallet: str, limit: int = 50) -> dict[str, Any]:
    agents = list_launched_agents(user_wallet, limit=limit)
    return {"agents": agents, "count": len(agents)}


def list_marketplace_launched_agents(limit: int = 100) -> dict[str, Any]:
    agents = list_public_launched_agents(limit=limit)
    return {"agents": agents, "count": len(agents)}


def _ensure_public_payment_wallet(agent: dict[str, Any]) -> dict[str, Any]:
    """Create the unique Circle payment wallet when an agent is public + priced."""
    if str(agent.get("visibility") or "") != "public":
        return agent
    try:
        price = float(agent.get("price_per_month_sol") or 0)
    except (TypeError, ValueError):
        price = 0.0
    if price <= 0:
        return agent
    from platform_payments import ensure_creator_agent_payment_wallet, get_agent_payment_wallet

    existing = get_agent_payment_wallet(str(agent["id"]))
    if existing:
        agent = {
            **agent,
            "payment_wallet_address": existing.get("payment_wallet_address"),
            "payment_circle_wallet_id": existing.get("circle_wallet_id"),
        }
        return agent
    created = ensure_creator_agent_payment_wallet(
        str(agent["id"]),
        str(agent.get("user_wallet") or ""),
    )
    if created.get("error"):
        print(f"  ⚠️  Agent payment wallet: {created['error']}")
        return {**agent, "payment_wallet_error": created["error"]}
    return {
        **agent,
        "payment_wallet_address": created.get("payment_wallet_address"),
        "payment_circle_wallet_id": created.get("circle_wallet_id"),
    }


def _decorate_agent(agent: dict[str, Any]) -> dict[str, Any]:
    from platform_payments import get_agent_payment_wallet, get_company_treasury_wallet

    seller = str(agent.get("user_wallet") or "").strip()
    payout = get_creator_payout_wallet(seller) or seller
    pay = get_agent_payment_wallet(str(agent.get("id") or ""))
    payment_addr = (
        (pay or {}).get("payment_wallet_address")
        or agent.get("payment_wallet_address")
    )
    return {
        **agent,
        "creator_payout_wallet": payout,
        "payment_wallet_address": payment_addr,
        "creator_available_sol": float((pay or {}).get("creator_available_sol") or 0),
        "platform_accrued_sol": float((pay or {}).get("platform_accrued_sol") or 0),
        "platform_fee_wallet": get_launch_fee_wallet(),
        "company_treasury_wallet": get_company_treasury_wallet(),
        "platform_fee_rate": get_platform_fee_rate(),
        "payment_required": not is_free_launch(),
        "mode": get_app_mode(),
    }


def get_marketplace_launched_agent(agent_id: str) -> dict[str, Any]:
    agent = get_launched_agent(agent_id)
    if not agent:
        return {"error": "Agent not found."}
    if agent.get("visibility") != "public" or agent.get("status") != "active":
        return {"error": "Agent is not publicly listed."}
    return {"agent": _decorate_agent(agent)}


def get_owned_or_accessible_agent(agent_id: str, user_wallet: str) -> dict[str, Any]:
    agent = get_launched_agent(agent_id)
    if not agent:
        return {"error": "Agent not found."}
    access = check_agent_access(agent_id, user_wallet)
    if agent.get("user_wallet") != user_wallet and agent.get("visibility") != "public":
        if not access.get("allowed"):
            return {"error": "Agent not found."}
    return {"agent": _decorate_agent(agent), "access": access}


def check_agent_access(agent_id: str, user_wallet: str) -> dict[str, Any]:
    """
    Visibility works like GitHub:
    public listings are discoverable; switching to private hides the agent from
    new users. Anyone with an active paid subscription keeps access until it expires.
    """
    agent = get_launched_agent(agent_id)
    if not agent:
        return {"allowed": False, "reason": "not_found"}
    user_wallet = (user_wallet or "").strip()
    if agent.get("user_wallet") == user_wallet:
        return {"allowed": True, "reason": "owner", "payment_required": False}
    if agent.get("status") != "active":
        return {"allowed": False, "reason": "inactive", "payment_required": False}
    sub = get_active_subscription(agent_id, user_wallet)
    if sub:
        return {
            "allowed": True,
            "reason": "subscribed",
            "payment_required": False,
            "subscription": sub,
            "visibility": agent.get("visibility"),
        }
    if agent.get("visibility") != "public":
        return {"allowed": False, "reason": "private", "payment_required": False}
    if is_free_launch():
        return {"allowed": True, "reason": "development", "payment_required": False}
    return {
        "allowed": False,
        "reason": "payment_required",
        "payment_required": True,
        "price_per_month_sol": agent.get("price_per_month_sol"),
    }


def update_user_launched_agent(
    *,
    user_wallet: str,
    agent_id: str,
    name: str,
    description: str,
    task: str,
    modules: list[str],
    visibility: str = "private",
    price_per_month_sol: Optional[float] = None,
) -> dict[str, Any]:
    user_wallet = (user_wallet or "").strip()
    existing = get_launched_agent(agent_id)
    if not existing:
        return {"error": "Agent not found."}
    if existing.get("user_wallet") != user_wallet:
        return {"error": "You can only edit your own agents."}

    name = (name or "").strip()
    description = (description or "").strip()
    task = (task or "").strip()
    modules_norm = _normalize_modules(modules)
    visibility_norm = (visibility or "private").strip().lower()
    if visibility_norm not in ("public", "private"):
        return {"error": "Visibility must be public or private."}
    if not name:
        return {"error": "Agent name is required."}
    if not task:
        return {"error": "Agent task is required."}
    if not modules_norm:
        return {"error": "Select at least one valid module."}

    price: Optional[float] = None
    if visibility_norm == "public":
        try:
            price = float(price_per_month_sol) if price_per_month_sol is not None else None
        except (TypeError, ValueError):
            return {"error": "Price per month must be a number."}
        if price is None or not (price > 0):
            return {"error": "Public agents require a price per month greater than 0 SOL."}
    else:
        price = None

    updated = update_launched_agent(
        agent_id,
        user_wallet,
        {
            "name": name,
            "description": description,
            "task": task,
            "modules": modules_norm,
            "visibility": visibility_norm,
            "price_per_month_sol": price,
            "status": "active",
        },
    )
    if not updated:
        return {"error": "Failed to update agent."}
    updated = _ensure_public_payment_wallet(updated)
    message = f'Agent "{name}" relaunched.'
    if visibility_norm == "private" and existing.get("visibility") == "public":
        message = (
            f'Agent "{name}" is now private. People who already subscribed keep access '
            "until that subscription ends. After it ends, the agent is hidden from them "
            "and from the marketplace."
        )
    elif visibility_norm == "public" and existing.get("visibility") != "public":
        message = f'Agent "{name}" is public on the marketplace again.'
    return {
        "status": "updated",
        "agent": _decorate_agent(updated),
        "message": message,
    }


# Tools that spend real capital. Never executed on the tool call that
# proposes them -- only when the user's very next message confirms (see
# BOUNCE_CONFIRM_PHRASES / _user_confirmed below). This mirrors DCA's
# proven CONFIRMATION_REQUIRED_TOOLS pattern, not a new invention.
BOUNCE_CONFIRMATION_REQUIRED_TOOLS = frozenset(
    {"open_bounce_position", "close_bounce_position", "withdraw_bounce_balance", "convert_bounce_sol_to_usdc"}
)

# Deterministic pending-action store, mirroring dca_agent.py's proven
# _pending_confirmations pattern. Found necessary by actually testing this
# live: a small/free model does not reliably restate the exact proposed
# numbers on its own when the user says "yes" -- it can re-decide what to do
# from scratch, which for a fund-moving tool is a real safety gap, not just
# a UX one. "Yes" now executes the EXACT last-proposed action with its EXACT
# stored arguments, never whatever the model chooses to call that turn.
_BOUNCE_CONFIRMATION_LOCK = threading.Lock()
_bounce_pending: dict[str, dict[str, Any]] = {}


def _bounce_confirmation_key(user_wallet: str, agent_id: str) -> str:
    return f"{(user_wallet or '').strip()}:{(agent_id or '').strip()}"


def _stage_bounce_confirmation(user_wallet: str, agent_id: str, tool_name: str, args: dict[str, Any]) -> None:
    key = _bounce_confirmation_key(user_wallet, agent_id)
    with _BOUNCE_CONFIRMATION_LOCK:
        _bounce_pending[key] = {"tool": tool_name, "args": args}


def _pop_bounce_pending(user_wallet: str, agent_id: str) -> Optional[dict[str, Any]]:
    key = _bounce_confirmation_key(user_wallet, agent_id)
    with _BOUNCE_CONFIRMATION_LOCK:
        return _bounce_pending.pop(key, None)


def _describe_bounce_proposal(result: dict[str, Any]) -> str:
    """Human-readable confirmation prompt for a staged fund-moving action,
    built deterministically from the tool result rather than the LLM, so the
    user always sees the exact numbers that will execute if they confirm."""
    action = result.get("proposed_action")
    if action == "open_bounce_position":
        return (
            f"Proposed: buy {result.get('symbol')} with {result.get('amount_usdc')} USDC, "
            f"stop-loss {result.get('stop_loss_pct')}% / take-profit {result.get('take_profit_pct')}%. "
            "Confirm to execute, or tell me to cancel."
        )
    if action == "close_bounce_position":
        return (
            f"Proposed: close position {result.get('position_id')} at the current market price. "
            "Confirm to execute, or tell me to cancel."
        )
    if action == "withdraw_bounce_balance":
        return (
            f"Proposed: withdraw {result.get('amount_usdc')} USDC. "
            "Confirm to execute, or tell me to cancel."
        )
    if action == "convert_bounce_sol_to_usdc":
        return "Proposed: convert idle SOL in this wallet to USDC. Confirm to execute, or tell me to cancel."
    return f"Proposed action: {action}. Confirm to execute, or tell me to cancel."


def peek_bounce_pending(user_wallet: str, agent_id: str) -> Optional[dict[str, Any]]:
    """Read the pending action without consuming it -- for a frontend to poll
    and render an Approve/Reject card, same underlying store the chat path
    uses, so a button click and a typed 'yes' are equally deterministic."""
    key = _bounce_confirmation_key(user_wallet, agent_id)
    with _BOUNCE_CONFIRMATION_LOCK:
        return _bounce_pending.get(key)


# Separate store for the fast_test diagnostic profile, which skips the
# approval gate above entirely (see _maybe_auto_stage_trade in
# signal_watcher.py) -- there's nothing to approve, but the frontend still
# needs to know a trade just happened on its own, so it can show the result
# instead of implying something is awaiting a click.
_BOUNCE_AUTO_TRADE_LOCK = threading.Lock()
_bounce_last_auto_trade: dict[str, dict[str, Any]] = {}


def _record_bounce_auto_trade(user_wallet: str, agent_id: str, *, args: dict[str, Any], result: dict[str, Any]) -> None:
    key = _bounce_confirmation_key(user_wallet, agent_id)
    with _BOUNCE_AUTO_TRADE_LOCK:
        _bounce_last_auto_trade[key] = {
            "tool": "open_bounce_position",
            "args": args,
            "result": result,
            "at": datetime.now(timezone.utc).isoformat(),
        }


def peek_bounce_last_auto_trade(user_wallet: str, agent_id: str) -> Optional[dict[str, Any]]:
    """Read (without consuming) the most recent fast_test auto-trade, for the
    frontend to poll. Unlike pending confirmations this isn't awaiting a
    decision, so nothing pops it -- it just gets overwritten by the next one."""
    key = _bounce_confirmation_key(user_wallet, agent_id)
    with _BOUNCE_AUTO_TRADE_LOCK:
        return _bounce_last_auto_trade.get(key)


def respond_to_bounce_pending(user_wallet: str, agent_id: str, *, approve: bool) -> dict[str, Any]:
    """Approve or reject the pending action directly -- bypasses chat and the
    LLM entirely, same deterministic execution the chat 'yes' path uses."""
    if not approve:
        cancelled = _pop_bounce_pending(user_wallet, agent_id)
        if not cancelled:
            return {"error": "No pending action to reject."}
        return {"status": "cancelled", "tool": cancelled["tool"], "args": cancelled["args"]}

    pending = _pop_bounce_pending(user_wallet, agent_id)
    if not pending:
        return {"error": "No pending action to approve."}
    tool_name, result = _execute_pending_bounce_action(pending, agent_id=agent_id, user_wallet=user_wallet)
    return {"tool": tool_name, "args": pending["args"], "result": result}


def _signal_tools_for_agent(agent: dict[str, Any]) -> list[dict[str, Any]]:
    """Tool definitions for price-pattern signal watches and (once a watch
    fires) trading on them. Only offered when the agent has the
    price_signal_watch module enabled.

    Opening or manually closing a position always requires the user's next
    message to explicitly confirm -- see BOUNCE_CONFIRMATION_REQUIRED_TOOLS.
    A stop-loss/take-profit on an already-open position fires on its own
    without a fresh confirmation each time, because the user already
    authorized exactly that exit condition when they confirmed the entry."""
    if "price_signal_watch" not in (agent.get("modules") or []):
        return []
    return [
        {
            "type": "function",
            "function": {
                "name": "create_price_signal_watch",
                "description": (
                    "Start watching a token for a drop-then-bounce price pattern "
                    "(e.g. 'drops 10%, then bounces 5% off the low'). Does not "
                    "execute any trade, it only watches and reports."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string", "description": "Token symbol, e.g. SOL"},
                        "profile": {
                            "type": "string",
                            "enum": ["real", "test", "fast_test"],
                            "description": (
                                "'real' uses the agent's actual configured thresholds. "
                                "'test' and 'fast_test' use much smaller thresholds purely "
                                "to prove the watch fires correctly - only use these when "
                                "the user explicitly asks to test the pipeline, never for "
                                "a real strategy."
                            ),
                        },
                    },
                    "required": ["symbol"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "check_price_signal",
                "description": "Check the current state of a price signal watch (neutral/armed/fired/cooldown) and the live price.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "watch_id": {"type": "string"},
                    },
                    "required": ["watch_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_price_signal_watches",
                "description": "List all price signal watches this agent currently has running.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_bounce_balance",
                "description": "Show the user's deposited, spent, credited, and withdrawable SOL balance in the Bounce Agent wallet, and the wallet's deposit address.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "verify_bounce_deposit",
                "description": (
                    "Verify an on-chain SOL transfer the user already sent to the Bounce Agent "
                    "wallet and credit it to their balance. Call get_bounce_balance first if the "
                    "user doesn't have the deposit address yet. This only records money that has "
                    "already moved on-chain -- it does not move anything itself."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "signature": {"type": "string", "description": "The deposit transaction signature"},
                    },
                    "required": ["signature"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "convert_bounce_sol_to_usdc",
                "description": (
                    "Convert any idle SOL currently sitting in the Bounce Agent wallet into USDC "
                    "(e.g. a deposit made before auto-conversion existed). A real on-chain swap -- "
                    "money stays in the user's own custodial wallet throughout, it just changes from "
                    "SOL to USDC. Only executed once the user explicitly confirms in their next message."
                ),
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "withdraw_bounce_balance",
                "description": (
                    "Send withdrawable USDC from the Bounce Agent wallet back to the user's own "
                    "wallet. Spends nothing of the user's capital gain beyond what's withdrawable "
                    "(open positions can't be withdrawn until closed), but it is a real transfer "
                    "and is only executed once the user explicitly confirms in their next message."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "amount_usdc": {"type": "number"},
                    },
                    "required": ["amount_usdc"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "open_bounce_position",
                "description": (
                    "Buy `symbol` with `amount_usdc` USDC from the user's deposited Bounce Agent "
                    "balance, setting a stop-loss and take-profit. This spends real capital and "
                    "is only executed once the user explicitly confirms in their next message -- "
                    "the first call always just proposes the trade."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": (
                                "The token to swap the USDC capital into -- SOL is the normal, "
                                "expected choice, since that's what this agent watches. Must NOT be "
                                "USDC itself, that would be a self-swap, not a trade."
                            ),
                        },
                        "amount_usdc": {"type": "number", "description": "USDC to spend opening the position"},
                        "stop_loss_pct": {"type": "number", "description": "Percent below entry price to exit at a loss"},
                        "take_profit_pct": {"type": "number", "description": "Percent above entry price to exit at a profit"},
                        "watch_id": {"type": "string", "description": "The signal watch that fired, if any"},
                    },
                    "required": ["symbol", "amount_usdc", "stop_loss_pct", "take_profit_pct"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "close_bounce_position",
                "description": (
                    "Manually sell an open position back to SOL before its stop or target is hit. "
                    "Spends real capital (a real swap) and is only executed once the user explicitly "
                    "confirms in their next message."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"position_id": {"type": "string"}},
                    "required": ["position_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_bounce_positions",
                "description": "List this agent's open and closed positions for the user.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]


def _execute_signal_tool(
    name: str, args: dict[str, Any], *, agent_id: str, user_wallet: str, user_confirmed: bool
) -> dict[str, Any]:
    import signal_watcher as sw
    import bounce_trading as bt
    import bounce_ledger as bl

    if name == "create_price_signal_watch":
        symbol = str(args.get("symbol") or "SOL").strip().upper()
        profile = str(args.get("profile") or "real").strip().lower()
        if profile not in sw.SIGNAL_PROFILES:
            return {"error": f"Unknown profile '{profile}'. Use real, test, or fast_test."}
        return sw.create_watch(agent_id=agent_id, symbol=symbol, profile=profile)
    if name == "check_price_signal":
        watch_id = str(args.get("watch_id") or "").strip()
        if not watch_id:
            return {"error": "watch_id is required"}
        return sw.evaluate_watch(watch_id)
    if name == "list_price_signal_watches":
        return {"watches": sw.list_watches_for_agent(agent_id)}
    if name == "get_bounce_balance":
        return bl.get_bounce_user_balances(user_wallet)
    if name == "list_bounce_positions":
        return {"positions": bt.list_positions_for_user(user_wallet)}
    if name == "verify_bounce_deposit":
        signature = str(args.get("signature") or "").strip()
        if not signature:
            return {"error": "signature is required"}
        return bl.verify_and_record_bounce_deposit(signature, user_wallet)

    if name == "convert_bounce_sol_to_usdc":
        if not user_confirmed:
            _stage_bounce_confirmation(user_wallet, agent_id, name, {})
            return {"status": "confirmation_required", "proposed_action": "convert_bounce_sol_to_usdc"}
        return bl.convert_idle_sol_to_usdc(user_wallet)

    if name == "withdraw_bounce_balance":
        amount_usdc = float(args.get("amount_usdc") or 0)
        if not user_confirmed:
            _stage_bounce_confirmation(user_wallet, agent_id, name, {"amount_usdc": amount_usdc})
            return {"status": "confirmation_required", "proposed_action": "withdraw_bounce_balance", "amount_usdc": amount_usdc}
        return bl.withdraw_bounce_tokens(user_wallet, "USDC", amount_usdc)

    if name == "open_bounce_position":
        proposed = {
            "symbol": str(args.get("symbol") or "SOL").strip().upper(),
            "amount_usdc": float(args.get("amount_usdc") or 0),
            "stop_loss_pct": float(args.get("stop_loss_pct") or 0),
            "take_profit_pct": float(args.get("take_profit_pct") or 0),
            "watch_id": str(args.get("watch_id") or "").strip() or None,
        }
        if not user_confirmed:
            _stage_bounce_confirmation(user_wallet, agent_id, name, proposed)
            return {"status": "confirmation_required", "proposed_action": "open_bounce_position", **proposed}
        bt.start_position_monitor()
        return bt.open_position(
            user_wallet=user_wallet,
            agent_id=agent_id,
            watch_id=proposed["watch_id"],
            symbol=proposed["symbol"],
            amount_usdc=proposed["amount_usdc"],
            stop_loss_pct=proposed["stop_loss_pct"],
            take_profit_pct=proposed["take_profit_pct"],
        )

    if name == "close_bounce_position":
        # Never trust the LLM's position_id string at face value -- it has no
        # real way to know the exact id and, observed in practice, sometimes
        # fabricates one (e.g. a placeholder-looking "position_id_from_..."
        # instead of the real value) even when told to copy it from
        # list_bounce_positions. Resolve the real open position deterministically
        # instead: if the given id is genuinely one of the user's open
        # positions use it, otherwise fall back to the only open position (or
        # the only one matching a symbol hint) so a valid id is never required
        # from the model for the single-position case, which is the common one.
        requested_id = str(args.get("position_id") or "").strip()
        symbol_hint = str(args.get("symbol") or "").strip().upper() or None
        open_positions = bt.list_positions_for_user(user_wallet, status="open")
        position_id = requested_id if any(p["position_id"] == requested_id for p in open_positions) else None
        if not position_id:
            candidates = (
                [p for p in open_positions if str(p.get("symbol") or "").upper() == symbol_hint]
                if symbol_hint else open_positions
            )
            if len(candidates) == 1:
                position_id = candidates[0]["position_id"]
            elif not candidates:
                return {"error": "No open position found to close."}
            else:
                return {
                    "error": "Multiple open positions match - say which symbol, or ask me to list them.",
                    "open_positions": [{"position_id": p["position_id"], "symbol": p.get("symbol")} for p in candidates],
                }
        if not user_confirmed:
            _stage_bounce_confirmation(user_wallet, agent_id, name, {"position_id": position_id})
            return {"status": "confirmation_required", "proposed_action": "close_bounce_position", "position_id": position_id}
        return bt.close_position(position_id, reason="manual")

    return {"error": f"Unknown tool: {name}"}


def _execute_pending_bounce_action(pending: dict[str, Any], *, agent_id: str, user_wallet: str) -> tuple[str, dict[str, Any]]:
    """Deterministically run a staged action with its exact stored args.
    Bypasses the LLM entirely for this step -- see module note above."""
    import bounce_trading as bt
    import bounce_ledger as bl

    tool_name = pending["tool"]
    args = pending.get("args") or {}

    if tool_name == "withdraw_bounce_balance":
        return tool_name, bl.withdraw_bounce_tokens(user_wallet, "USDC", float(args.get("amount_usdc") or 0))
    if tool_name == "convert_bounce_sol_to_usdc":
        return tool_name, bl.convert_idle_sol_to_usdc(user_wallet)
    if tool_name == "open_bounce_position":
        bt.start_position_monitor()
        return tool_name, bt.open_position(
            user_wallet=user_wallet,
            agent_id=agent_id,
            watch_id=args.get("watch_id"),
            symbol=args["symbol"],
            amount_usdc=args["amount_usdc"],
            stop_loss_pct=args["stop_loss_pct"],
            take_profit_pct=args["take_profit_pct"],
        )
    if tool_name == "close_bounce_position":
        return tool_name, bt.close_position(args["position_id"], reason="manual")
    return tool_name, {"error": f"Unknown pending tool: {tool_name}"}


def chat_with_launched_agent(
    *,
    user_wallet: str,
    agent_id: str,
    message: str,
    history: Optional[list[dict[str, str]]] = None,
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    access = check_agent_access(agent_id, user_wallet)
    if not access.get("allowed"):
        if access.get("reason") == "private":
            return {
                "error": (
                    "This agent is private. Existing subscriptions keep access until they "
                    "expire, and it is hidden after that."
                ),
                "status": "private",
            }
        return {
            "error": "Subscribe to this agent to chat with it.",
            "status": "payment_required",
        }
    agent = get_launched_agent(agent_id)
    if not agent:
        return {"error": "Agent not found."}

    from hosted_llm import DEFAULT_LLM_MODEL, call_llm

    modules = ", ".join(agent.get("modules") or []) or "none"
    tools = _signal_tools_for_agent(agent)
    system = (
        f"You are {agent.get('name')}, a BIT Agents marketplace agent.\n"
        f"Description: {agent.get('description') or 'n/a'}\n"
        f"Your task and capabilities:\n{agent.get('task')}\n\n"
        f"Available modules: {modules}\n"
        "Stay on task. Be concise and useful. Do not invent transaction signatures."
    )
    if tools:
        system += (
            "\n\nIf the user wants to deposit, call get_bounce_balance to give them the wallet "
            "address, then once they say they've sent SOL, call verify_bounce_deposit with the "
            "transaction signature they give you. The deposit is automatically converted to USDC "
            "the moment it's verified - that's the agent's resting capital, not SOL.\n"
            "You can watch a token's price for the drop-then-bounce pattern using "
            "create_price_signal_watch, then check it with check_price_signal. "
            "If a watch fires, tell the user and ask whether they want to open a position. "
            "The symbol being bought must be a different token than USDC - USDC is the capital, "
            "not a valid trade target. SOL is the normal, expected target (it's what this agent "
            "watches).\n"
            "open_bounce_position, close_bounce_position, and withdraw_bounce_balance all spend "
            "or move real money. If the user asks to open or close a position or withdraw WITHOUT "
            "giving you the specific numbers it needs (amount_usdc, and for opening also "
            "stop_loss_pct and take_profit_pct), do NOT call the tool and do NOT guess - just ask "
            "them for the missing numbers in plain text. Only call the tool once you actually have "
            "them. Calling any of these tools only PROPOSES the action - it comes back as "
            "confirmation_required and nothing executes yet. Clearly state the exact numbers "
            "(symbol/amount_usdc/stop_loss_pct/take_profit_pct for a trade, or amount_usdc for a "
            "withdrawal) and ask the user to confirm. Do NOT call the tool again yourself after "
            "they say yes - the system executes the exact proposed action automatically the moment "
            "they confirm, before you are even called again. If the user instead wants to change "
            "a number, propose a fresh action with the new number; do not try to confirm the old one.\n"
            "close_bounce_position needs the position's exact position_id, which you do not know "
            "and must never guess or invent - always call list_bounce_positions first to find the "
            "real id of the open position the user means (match it by symbol if they named one), "
            "and use that id. If the user wants to close more than one open position, propose and "
            "confirm them one at a time rather than trying to close several in a single call.\n"
            "If create_price_signal_watch is called again for the same symbol while a watch is "
            "already running, it returns the existing watch instead of creating a new one - so "
            "always check_price_signal or list_price_signal_watches first rather than creating "
            "several watches for the same thing.\n"
            "Once a position is open its stop-loss and take-profit are monitored and executed "
            "automatically without asking again, because the user already authorized that exit "
            "when they confirmed the entry. Never invent a transaction signature or balance - "
            "always get it from a tool result."
        )
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    for item in history or []:
        role = str((item or {}).get("role") or "")
        content = str((item or {}).get("content") or "").strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": (message or "").strip()})

    from dca_agent import _user_confirmed, _user_declined

    user_declined = _user_declined(message)
    user_confirmed = _user_confirmed(message) and not user_declined

    actions: list[dict[str, Any]] = []

    # Deterministic confirm/decline of a previously staged action, bypassing
    # the LLM entirely -- see _bounce_pending's module note for why this is
    # necessary, not optional, for a fund-moving tool.
    if tools and user_declined:
        cancelled = _pop_bounce_pending(user_wallet, agent_id)
        if cancelled:
            reply = f"Cancelled. {cancelled['tool']} was not executed."
            return {
                "reply": reply,
                "session_id": session_id or uuid.uuid4().hex,
                "actions": [{"tool": cancelled["tool"], "args": cancelled["args"], "result": {"status": "cancelled"}}],
                "agent": _decorate_agent(agent),
            }
    if tools and user_confirmed:
        pending = _pop_bounce_pending(user_wallet, agent_id)
        if pending:
            tool_name, result = _execute_pending_bounce_action(pending, agent_id=agent_id, user_wallet=user_wallet)
            if result.get("error"):
                reply = f"Could not complete {tool_name}: {result['error']}"
            else:
                reply = f"Confirmed and executed {tool_name}. {result}"
            return {
                "reply": reply,
                "session_id": session_id or uuid.uuid4().hex,
                "actions": [{"tool": tool_name, "args": pending["args"], "result": result}],
                "agent": _decorate_agent(agent),
            }

    for _ in range(4):
        try:
            # CapIX is currently returning 401 for every request (confirmed dead,
            # not a transient issue) and call_llm's default routing always tries
            # CapIX first whenever it's "configured", even though it can't
            # actually serve requests -- it never reaches the OpenRouter fallback.
            # Forcing openrouter here, scoped to just this launched-agent chat
            # path, not any other agent's LLM routing.
            raw = call_llm(
                messages, model=DEFAULT_LLM_MODEL, tools=tools or None, temperature=0.3, provider="openrouter"
            )
        except Exception as exc:
            return {"error": f"Agent chat failed: {exc}"}

        if not isinstance(raw, dict) or raw.get("error"):
            return {"error": str((raw or {}).get("error") or "Agent chat failed.")}

        choices = raw.get("choices") or []
        msg = (choices[0].get("message") if choices else raw.get("message")) or {}
        tool_calls = msg.get("tool_calls") or []

        if not tool_calls:
            reply = str(msg.get("content") or raw.get("reply") or raw.get("content") or "").strip()
            if not reply:
                reply = "The agent did not return a reply. Try again."
            return {
                "reply": reply,
                "session_id": session_id or uuid.uuid4().hex,
                "actions": actions,
                "agent": _decorate_agent(agent),
            }

        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": tool_calls})
        for tc in tool_calls:
            name = tc["function"]["name"]
            raw_args = tc["function"].get("arguments", {})
            if isinstance(raw_args, str):
                try:
                    import json
                    raw_args = json.loads(raw_args)
                except Exception:
                    raw_args = {}
            if not isinstance(raw_args, dict):
                raw_args = {}
            result = _execute_signal_tool(
                name, raw_args, agent_id=agent_id, user_wallet=user_wallet, user_confirmed=user_confirmed
            )
            actions.append({"tool": name, "args": raw_args, "result": result})
            import json as _json
            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id") or name,
                "content": _json.dumps(result, default=str),
            })

            # A fund-moving tool proposing an action is a terminal state for this
            # turn -- return it directly instead of looping back to the LLM,
            # which (observed in practice) sometimes re-calls the same tool
            # instead of stopping to ask for confirmation, burning the step
            # budget without ever replying to the user.
            if isinstance(result, dict) and result.get("status") == "confirmation_required":
                return {
                    "reply": _describe_bounce_proposal(result),
                    "session_id": session_id or uuid.uuid4().hex,
                    "actions": actions,
                    "agent": _decorate_agent(agent),
                }

    return {
        "reply": "Reached the step limit for this turn - try asking again.",
        "session_id": session_id or uuid.uuid4().hex,
        "actions": actions,
        "agent": _decorate_agent(agent),
    }


def subscribe_to_agent(
    *,
    buyer_wallet: str,
    agent_id: str,
    signature: str,
) -> dict[str, Any]:
    """
    Verify a monthly SOL payment and record a subscription.

    Buyer pays the full listed price to the agent's unique payment wallet.
    Inside that wallet we split 90% creator / 10% platform cut. The platform
    cut stays until the monthly treasury sweep. Development mode is free.
    """
    from platform_payments import (
        ensure_creator_agent_payment_wallet,
        get_agent_payment_wallet,
        record_creator_agent_subscription_split,
    )

    buyer_wallet = (buyer_wallet or "").strip()
    agent_id = (agent_id or "").strip()
    signature = (signature or "").strip()

    if not buyer_wallet:
        return {"error": "User wallet is required."}
    if not agent_id:
        return {"error": "Agent id is required."}

    agent = get_launched_agent(agent_id)
    if not agent:
        return {"error": "Agent not found."}
    if agent.get("visibility") != "public" or agent.get("status") != "active":
        return {"error": "Only public active agents can be purchased."}

    seller_wallet = str(agent.get("user_wallet") or "").strip()
    if not seller_wallet:
        return {"error": "Agent seller wallet is missing."}
    if seller_wallet == buyer_wallet:
        return {"error": "You cannot subscribe to your own agent."}

    price = agent.get("price_per_month_sol")
    try:
        price_sol = float(price) if price is not None else 0.0
    except (TypeError, ValueError):
        price_sol = 0.0
    if price_sol <= 0:
        return {"error": "This agent does not have a valid monthly price."}

    platform_rate = get_platform_fee_rate()
    creator_share = round(price_sol * (1.0 - platform_rate), 9)
    platform_share = round(price_sol * platform_rate, 9)

    pay = get_agent_payment_wallet(agent_id)
    if not pay:
        created = ensure_creator_agent_payment_wallet(agent_id, seller_wallet)
        if created.get("error"):
            return created
        pay = created
    payment_dest = str(pay.get("payment_wallet_address") or "").strip()
    if not payment_dest:
        return {"error": "Agent payment wallet is not configured."}

    if is_free_launch():
        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=30)
        sub_id = uuid.uuid4().hex[:16]
        signature = f"development-{uuid.uuid4().hex[:16]}"
        subscription = create_agent_subscription(
            {
                "id": sub_id,
                "agent_id": agent_id,
                "buyer_wallet": buyer_wallet,
                "seller_wallet": payment_dest,
                "price_sol": 0,
                "payment_signature": signature,
                "status": "active",
                "starts_at": now.isoformat(),
                "expires_at": expires.isoformat(),
                "explorer_url": None,
            }
        )
        return {
            "status": "confirmed",
            "subscription": subscription,
            "agent": _decorate_agent(agent),
            "paid_sol": 0,
            "creator_sol": 0,
            "platform_sol": 0,
            "payment_wallet_address": payment_dest,
            "message": f'Subscribed to "{agent.get("name")}" for 30 days (development: no fee).',
        }

    if not signature:
        return {"error": "Transaction signature is required."}
    if not _valid_signature(signature):
        return {"error": "Invalid transaction signature format."}

    with _launch_lock:
        existing_sig = get_subscription_by_signature(signature)
        if existing_sig:
            if existing_sig.get("buyer_wallet") != buyer_wallet:
                return {
                    "error": "This payment was already used by another wallet.",
                    "status": "rejected",
                }
            return {
                "status": "already_recorded",
                "subscription": existing_sig,
                "agent": agent,
                "message": "This subscription payment was already recorded.",
            }

        active = get_active_subscription(agent_id, buyer_wallet)
        if active:
            return {
                "error": (
                    "You already have an active subscription for this agent "
                    f"until {active.get('expires_at')}."
                ),
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

        if not _user_in_transaction(tx, buyer_wallet):
            return {
                "error": (
                    "Your connected wallet is not involved in this transaction. "
                    "You can only subscribe with a payment you signed and sent."
                ),
            }

        inbound = _parse_verified_user_deposits(tx, buyer_wallet, payment_dest)
        sol_transfers = [
            t for t in inbound if str(t.get("token", "")).upper() in ("SOL", "WSOL")
        ]
        paid = max((float(t.get("amount") or 0) for t in sol_transfers), default=0.0)
        if paid + 1e-9 < price_sol:
            return {
                "error": (
                    f"Subscription is {price_sol} SOL to the agent payment wallet "
                    f"{payment_dest[:4]}…{payment_dest[-4:]}. This transaction paid {paid} SOL."
                ),
            }

        split = record_creator_agent_subscription_split(
            agent_id=agent_id,
            price_sol=price_sol,
            platform_rate=platform_rate,
        )
        if split.get("error"):
            return split

        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=30)
        explorer = _explorer_url(signature)
        sub_id = uuid.uuid4().hex[:16]

        subscription = create_agent_subscription(
            {
                "id": sub_id,
                "agent_id": agent_id,
                "buyer_wallet": buyer_wallet,
                "seller_wallet": payment_dest,
                "price_sol": price_sol,
                "payment_signature": signature,
                "status": "active",
                "starts_at": now.isoformat(),
                "expires_at": expires.isoformat(),
                "explorer_url": explorer,
            }
        )

        insert_ledger_entry(
            {
                "id": uuid.uuid4().hex[:16],
                "user_wallet": buyer_wallet,
                "agent_wallet": payment_dest,
                "signature": signature,
                "token": "SOL",
                "mint": SOL_ADDRESS_FULL,
                "amount": float(paid),
                "direction": "deposit",
                "reference_type": "agent_subscription",
                "reference_id": sub_id,
                "status": "confirmed",
                "verified_at": now.isoformat(),
                "explorer_url": explorer,
            }
        )

        return {
            "status": "confirmed",
            "subscription": subscription,
            "agent": _decorate_agent(get_launched_agent(agent_id) or agent),
            "paid_sol": paid,
            "creator_sol": creator_share,
            "platform_sol": platform_share,
            "payment_wallet_address": payment_dest,
            "message": (
                f'Subscribed to "{agent.get("name")}" for 30 days. '
                f"{creator_share} SOL is available for the creator to withdraw; "
                f"{platform_share} SOL platform cut stays until the monthly treasury sweep."
            ),
        }


def withdraw_creator_agent_earnings(
    *,
    user_wallet: str,
    agent_id: str,
    amount_sol: Optional[float] = None,
    destination_wallet: Optional[str] = None,
) -> dict[str, Any]:
    from platform_payments import withdraw_creator_earnings

    return withdraw_creator_earnings(
        agent_id=agent_id,
        creator_user_wallet=user_wallet,
        destination_wallet=destination_wallet,
        amount_sol=amount_sol,
    )


def _subscription_is_active(sub: dict[str, Any]) -> bool:
    if str(sub.get("status") or "") != "active":
        return False
    raw = sub.get("expires_at")
    if not raw:
        return False
    try:
        exp = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return False
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return exp > datetime.now(timezone.utc)


def _buyer_subscription_visible(sub: dict[str, Any]) -> bool:
    """Keep a private agent visible only while the buyer's subscription is still active."""
    if _subscription_is_active(sub):
        return True
    visibility = str(sub.get("agent_visibility") or "").lower()
    status = str(sub.get("agent_status") or "").lower()
    return visibility == "public" and status == "active"


def get_user_launch_dashboard(user_wallet: str) -> dict[str, Any]:
    from db import ensure_launch_schema

    ensure_launch_schema()
    wallet = (user_wallet or "").strip()
    owned = list_launched_agents(wallet, limit=100)
    listed = []
    private = []
    for agent in owned:
        try:
            sub_count = count_agent_subscribers(agent["id"])
        except Exception:
            sub_count = 0
        row = {**agent, "active_subscribers": sub_count}
        if agent.get("visibility") == "public":
            listed.append(row)
        else:
            private.append(row)

    try:
        bought = [
            sub
            for sub in list_buyer_subscriptions(wallet, limit=100)
            if _buyer_subscription_visible(sub)
        ]
    except Exception:
        bought = []
    try:
        sales = list_seller_subscriptions(wallet, limit=100)
    except Exception:
        sales = []

    return {
        "listed_for_sale": listed,
        "private_agents": private,
        "bought": bought,
        "sales": sales,
        "counts": {
            "listed_for_sale": len(listed),
            "private_agents": len(private),
            "bought": len(bought),
            "sales": len(sales),
        },
        "creator_payout_wallet": get_creator_payout_wallet(wallet),
        "platform_fee_rate": get_platform_fee_rate(),
        "mode": get_app_mode(),
        "payment_required": not is_free_launch(),
    }
