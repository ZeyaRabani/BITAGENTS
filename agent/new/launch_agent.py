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


def _decorate_agent(agent: dict[str, Any]) -> dict[str, Any]:
    seller = str(agent.get("user_wallet") or "").strip()
    payout = get_creator_payout_wallet(seller) or seller
    return {
        **agent,
        "creator_payout_wallet": payout,
        "platform_fee_wallet": get_launch_fee_wallet(),
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
    agent = get_launched_agent(agent_id)
    if not agent:
        return {"allowed": False, "reason": "not_found"}
    user_wallet = (user_wallet or "").strip()
    if agent.get("user_wallet") == user_wallet:
        return {"allowed": True, "reason": "owner", "payment_required": False}
    if agent.get("visibility") != "public" or agent.get("status") != "active":
        return {"allowed": False, "reason": "private", "payment_required": True}
    if is_free_launch():
        return {"allowed": True, "reason": "development", "payment_required": False}
    sub = get_active_subscription(agent_id, user_wallet)
    if sub:
        return {
            "allowed": True,
            "reason": "subscribed",
            "payment_required": False,
            "subscription": sub,
        }
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
    return {
        "status": "updated",
        "agent": _decorate_agent(updated),
        "message": f'Agent "{name}" relaunched.',
    }


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
        return {
            "error": "Subscribe to this agent to chat with it.",
            "status": "payment_required",
        }
    agent = get_launched_agent(agent_id)
    if not agent:
        return {"error": "Agent not found."}

    from hosted_llm import DEFAULT_LLM_MODEL, call_llm

    modules = ", ".join(agent.get("modules") or []) or "none"
    system = (
        f"You are {agent.get('name')}, a BIT Agents marketplace agent.\n"
        f"Description: {agent.get('description') or 'n/a'}\n"
        f"Your task and capabilities:\n{agent.get('task')}\n\n"
        f"Available modules: {modules}\n"
        "Stay on task. Be concise and useful. Do not invent transaction signatures."
    )
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    for item in history or []:
        role = str((item or {}).get("role") or "")
        content = str((item or {}).get("content") or "").strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": (message or "").strip()})

    try:
        raw = call_llm(messages, model=DEFAULT_LLM_MODEL, temperature=0.3)
    except Exception as exc:
        return {"error": f"Agent chat failed: {exc}"}

    reply = ""
    if isinstance(raw, dict):
        if raw.get("error"):
            return {"error": str(raw["error"])}
        choices = raw.get("choices") or []
        if choices:
            reply = str((choices[0].get("message") or {}).get("content") or "").strip()
        if not reply:
            reply = str(raw.get("reply") or raw.get("content") or "").strip()
    if not reply:
        reply = "The agent did not return a reply. Try again."

    return {
        "reply": reply,
        "session_id": session_id or uuid.uuid4().hex,
        "actions": [],
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

    Buyer pays the listed price. 10% goes to the platform fee wallet and
    90% goes to the creator Circle wallet. Development mode is free.
    """
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
    creator_dest = get_creator_payout_wallet(seller_wallet) or seller_wallet
    platform_dest = get_launch_fee_wallet()

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
                "seller_wallet": creator_dest,
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

        inbound_creator = _parse_verified_user_deposits(tx, buyer_wallet, creator_dest)
        creator_transfers = [
            t for t in inbound_creator if str(t.get("token", "")).upper() in ("SOL", "WSOL")
        ]
        paid_creator = max((float(t.get("amount") or 0) for t in creator_transfers), default=0.0)

        paid_platform = 0.0
        if platform_dest and platform_share > 0:
            inbound_platform = _parse_verified_user_deposits(tx, buyer_wallet, platform_dest)
            platform_transfers = [
                t for t in inbound_platform if str(t.get("token", "")).upper() in ("SOL", "WSOL")
            ]
            paid_platform = max((float(t.get("amount") or 0) for t in platform_transfers), default=0.0)

        if paid_creator + 1e-9 < creator_share:
            return {
                "error": (
                    f"Creator share is {creator_share} SOL to "
                    f"{creator_dest[:4]}…{creator_dest[-4:]}. This transaction paid {paid_creator} SOL."
                ),
            }
        if platform_dest and platform_share > 0 and paid_platform + 1e-9 < platform_share:
            return {
                "error": (
                    f"Platform fee is {platform_share} SOL. This transaction paid {paid_platform} SOL."
                ),
            }

        paid = paid_creator + paid_platform

        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=30)
        explorer = _explorer_url(signature)
        sub_id = uuid.uuid4().hex[:16]

        subscription = create_agent_subscription(
            {
                "id": sub_id,
                "agent_id": agent_id,
                "buyer_wallet": buyer_wallet,
                "seller_wallet": creator_dest,
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
            "agent": _decorate_agent(agent),
            "paid_sol": paid,
            "creator_sol": paid_creator,
            "platform_sol": paid_platform,
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
        "creator_payout_wallet": get_creator_payout_wallet(wallet),
        "platform_fee_rate": get_platform_fee_rate(),
        "mode": get_app_mode(),
        "payment_required": not is_free_launch(),
    }
