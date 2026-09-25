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
    return get_launch_cost_sol() <= 0


def get_launch_config() -> dict[str, Any]:
    fee_wallet = get_launch_fee_wallet()
    fee_sol = get_launch_cost_sol()
    mode = get_app_mode()
    free = fee_sol <= 0
    return {
        "mode": mode,
        "fee_sol": fee_sol,
        "fee_wallet": fee_wallet,
        "configured": True if free else bool(fee_wallet),
        "cluster": SOLANA_CLUSTER,
        "allowed_modules": sorted(ALLOWED_LAUNCH_MODULES),
        "payment_required": not free,
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
        return {
            "status": "confirmed",
            "agent": agent,
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

        return {
            "status": "confirmed",
            "agent": agent,
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


def get_marketplace_launched_agent(agent_id: str) -> dict[str, Any]:
    agent = get_launched_agent(agent_id)
    if not agent:
        return {"error": "Agent not found."}
    if agent.get("visibility") != "public" or agent.get("status") != "active":
        return {"error": "Agent is not publicly listed."}
    return {"agent": agent}


def subscribe_to_agent(
    *,
    buyer_wallet: str,
    agent_id: str,
    signature: str,
) -> dict[str, Any]:
    """
    Verify a monthly SOL payment from buyer to the agent creator and record a subscription.
    """
    buyer_wallet = (buyer_wallet or "").strip()
    agent_id = (agent_id or "").strip()
    signature = (signature or "").strip()

    if not buyer_wallet:
        return {"error": "User wallet is required."}
    if not agent_id:
        return {"error": "Agent id is required."}
    if not signature:
        return {"error": "Transaction signature is required."}
    if not _valid_signature(signature):
        return {"error": "Invalid transaction signature format."}

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

        inbound = _parse_verified_user_deposits(tx, buyer_wallet, seller_wallet)
        sol_transfers = [
            t for t in inbound if str(t.get("token", "")).upper() in ("SOL", "WSOL")
        ]
        if not sol_transfers:
            return {
                "error": (
                    f"No verifiable SOL transfer from your wallet to the seller "
                    f"({seller_wallet[:4]}…{seller_wallet[-4:]}) was found."
                ),
            }

        paid = max(float(t.get("amount") or 0) for t in sol_transfers)
        if paid + 1e-9 < price_sol:
            return {
                "error": (
                    f"Monthly price is {price_sol} SOL. This transaction paid {paid} SOL."
                ),
            }

        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=30)
        explorer = _explorer_url(signature)
        sub_id = uuid.uuid4().hex[:16]

        subscription = create_agent_subscription(
            {
                "id": sub_id,
                "agent_id": agent_id,
                "buyer_wallet": buyer_wallet,
                "seller_wallet": seller_wallet,
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
                "agent_wallet": seller_wallet,
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
            "agent": agent,
            "paid_sol": paid,
            "message": f'Subscribed to "{agent.get("name")}" for 30 days.',
        }


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
        bought = list_buyer_subscriptions(wallet, limit=100)
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
    }
