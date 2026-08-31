"""
Volume Agent — Meteora DLMM pool infrastructure + scheduled buy/sell volume campaigns.

Flow:
1. User signs in (shared wallet auth)
2. User deposits SOL (and token if needed)
3. User creates campaign with pair, frequency, max executions
4. Agent reuses existing Meteora/Jupiter liquidity (same path as BITAGENTS Volume)
5. Scheduler runs round-trip swaps (SOL→token, token→SOL) at 0.25% platform fee per leg
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from db import (
    claim_due_volume_campaigns,
    claim_provisioning_volume_campaigns,
    find_volume_campaign,
    insert_volume_campaign,
    load_all_volume_campaigns,
    update_volume_campaign,
)
from dca_agent import (
    HAS_SOLDERS,
    JUPITER_BUILD_API,
    MODEL,
    SOLANA_CLUSTER,
    SOLANA_RPC,
    _coerce_bool,
    _coerce_nullable_float,
    _coerce_nullable_int,
    _confirm_transaction,
    _execute_jupiter_swap_v2,
    _is_mainnet,
    _jupiter_get,
    _parse_interval,
    _to_instruction,
    resolve_token,
    sol_rpc,
)
from hosted_llm import call_llm, llm_provider, use_hosted_ollama
from meteora_dlmm import (
    NO_ROUTE_MESSAGE,
    check_pool_infrastructure,
    ensure_meteora_dlmm_pool,
    meteora_pool_app_url,
)
from volume_ledger import (
    MAX_CONSECUTIVE_FAILURES,
    VOLUME_PLATFORM_FEE_RATE,
    check_user_can_spend_volume,
    get_volume_agent_wallet_info,
    get_volume_wallet_pubkey,
    load_volume_keypair,
    reclaim_token_account_rent,
    record_user_credit_volume,
    record_user_acquire_volume,
    record_user_spend_volume,
    record_volume_platform_fee,
    validate_volume_trade_amount,
    volume_execution_total_cost,
    volume_platform_fee,
)

VOLUME_MODEL = os.environ.get("VOLUME_MODEL", os.environ.get("DCA_MODEL", MODEL))
VOLUME_SCHEDULER_POLL_SECONDS = int(os.environ.get("VOLUME_SCHEDULER_POLL_SECONDS", "30"))

_scheduler_thread: Optional[threading.Thread] = None
_scheduler_stop = threading.Event()


def get_volume_history(campaign_id: str, user_wallet: Optional[str] = None) -> dict[str, Any]:
    if user_wallet:
        campaign = find_volume_campaign(campaign_id)
        if not campaign:
            return {"error": f"Campaign '{campaign_id}' not found."}
        if (campaign.get("user_wallet") or "").strip() != user_wallet.strip():
            return {"error": "Forbidden: campaign belongs to another wallet."}
    else:
        campaign = find_volume_campaign(campaign_id)
        if not campaign:
            return {"error": f"Campaign '{campaign_id}' not found."}
    return {
        "campaign_id": campaign_id,
        "name": campaign["name"],
        "executions_count": campaign.get("executions_count", 0),
        "spent_so_far": campaign.get("spent_so_far", 0),
        "executions": campaign.get("executions", []),
        "pool_address": campaign.get("pool_address"),
    }


def list_volume_campaigns(
    user_wallet: Optional[str] = None,
    *,
    active_only: bool = False,
    status: Optional[str] = None,
) -> dict[str, Any]:
    campaigns = load_all_volume_campaigns(user_wallet)
    if status:
        campaigns = [c for c in campaigns if c.get("status") == status]
    elif active_only:
        campaigns = [c for c in campaigns if c.get("status") == "active"]
    return {"count": len(campaigns), "campaigns": campaigns}


def _assert_campaign_owner(campaign_id: str, user_wallet: str) -> dict[str, Any]:
    campaign = find_volume_campaign(campaign_id)
    if not campaign:
        return {"error": f"Campaign '{campaign_id}' not found."}
    if (campaign.get("user_wallet") or "").strip() != user_wallet.strip():
        return {"error": "Forbidden: campaign belongs to another wallet."}
    return campaign


def _estimate_campaign_budget(
    trade_amount: float,
    max_executions: int,
    pool_creation_cost_sol: float,
    pool_exists: bool,
) -> float:
    per_cycle = volume_execution_total_cost(trade_amount) * 2
    total = per_cycle * max_executions
    if not pool_exists:
        total += pool_creation_cost_sol
    return round(total, 9)


def _dlmm_pool_ready(infra: dict[str, Any]) -> bool:
    """True when the campaign can swap: a Meteora pool or any Jupiter route."""
    return bool(infra.get("pool_exists"))


def ensure_volume_meteora_pool(
    *,
    base_token: str,
    quote_token: str = "SOL",
    user_wallet: Optional[str] = None,
    create_if_missing: bool = False,
) -> dict[str, Any]:
    """Resolve tokens and reuse existing Meteora/Jupiter liquidity. Never creates a pool."""
    del user_wallet, create_if_missing
    base = resolve_token(base_token)
    quote = resolve_token(quote_token)
    if "error" in base:
        return base
    if "error" in quote:
        return quote

    result = ensure_meteora_dlmm_pool(base["mint"], quote["mint"])
    if result.get("error") and not result.get("pool_exists"):
        return result

    result.update(
        {
            "base_token": base["symbol"],
            "quote_token": quote["symbol"],
            "base_mint": base["mint"],
            "quote_mint": quote["mint"],
            "pair": f"{base['symbol']}/{quote['symbol']}",
        }
    )
    return result


def provision_campaign_infrastructure(campaign_id: str) -> dict[str, Any]:
    campaign = find_volume_campaign(campaign_id)
    if not campaign:
        return {"error": f"Campaign '{campaign_id}' not found."}

    infra = check_pool_infrastructure(campaign["base_mint"], campaign["quote_mint"])
    updates: dict[str, Any] = {
        "infrastructure": {**campaign.get("infrastructure", {}), "last_check": infra},
    }

    if _dlmm_pool_ready(infra):
        pool_address = infra.get("pool_address")
        infra_merged = {**campaign.get("infrastructure", {}), "last_check": infra}
        infra_merged.pop("pool_creation_error", None)
        infra_merged.pop("spend_check_error", None)
        updates["infrastructure"] = infra_merged
        updates["pool_exists"] = True
        updates["pool_address"] = pool_address
        updates["pool_creation_cost_sol"] = 0.0
        prev = campaign.get("status")
        if prev in ("provisioning", "failed"):
            updates["status"] = "active"
            if not campaign.get("next_execution_at"):
                updates["next_execution_at"] = datetime.now(timezone.utc).isoformat()
        update_volume_campaign(campaign_id, updates)
        return {
            "status": "reuse_pool",
            "campaign_id": campaign_id,
            "pool_address": pool_address,
            "source": infra.get("source", "meteora"),
            "jupiter_route": bool(infra.get("jupiter_route")),
            "meteora_url": meteora_pool_app_url(pool_address, infra.get("pool_type") or "dlmm") if pool_address else None,
            "message": infra.get("message"),
            "platform_fee_rate": VOLUME_PLATFORM_FEE_RATE,
        }

    err = infra.get("error") or infra.get("message") or NO_ROUTE_MESSAGE
    updates["status"] = "failed"
    updates["infrastructure"] = {
        **updates.get("infrastructure", {}),
        "pool_creation_error": {"error": err},
        "last_provision_error_at": datetime.now(timezone.utc).isoformat(),
    }
    update_volume_campaign(campaign_id, updates)
    return {"error": err}


def create_volume_campaign(
    *,
    base_token: str,
    quote_token: str = "SOL",
    trade_amount: float,
    interval: str,
    max_executions: int,
    user_wallet: str,
    name: Optional[str] = None,
    total_budget: Optional[float] = None,
    slippage_bps: int = 100,
    seed_token_amount: float = 0.0,
) -> dict[str, Any]:
    trade_amount = float(trade_amount)
    max_executions = int(max_executions)
    slippage_bps = int(slippage_bps)
    total_budget = _coerce_nullable_float(total_budget)

    base = resolve_token(base_token)
    quote = resolve_token(quote_token)
    if "error" in base:
        return base
    if "error" in quote:
        return quote
    if trade_amount <= 0:
        return {"error": "trade_amount must be greater than zero."}
    if max_executions <= 0:
        return {"error": "max_executions must be at least 1."}

    size_check = validate_volume_trade_amount(trade_amount, quote["symbol"])
    if "error" in size_check:
        return size_check

    try:
        interval_minutes = _parse_interval(interval)
    except ValueError as exc:
        return {"error": str(exc)}

    if not user_wallet or not str(user_wallet).strip():
        return {"error": "user_wallet is required. Connect wallet and sign in first."}

    infra = check_pool_infrastructure(base["mint"], quote["mint"])
    dlmm_ready = _dlmm_pool_ready(infra)
    if not dlmm_ready:
        err = infra.get("error") or infra.get("message") or NO_ROUTE_MESSAGE
        return {"error": err, "infrastructure": infra}

    pool_cost = 0.0
    estimated_budget = _estimate_campaign_budget(trade_amount, max_executions, pool_cost, True)

    if total_budget is None:
        total_budget = estimated_budget
    elif total_budget + 1e-12 < estimated_budget:
        return {
            "error": (
                f"total_budget too low. Need at least {estimated_budget} {quote['symbol']} "
                f"({max_executions} round-trips)."
            ),
            "estimated_budget": estimated_budget,
        }

    balance_check = check_user_can_spend_volume(user_wallet.strip(), quote["symbol"], total_budget)
    if "error" in balance_check:
        return balance_check

    if not name or not str(name).strip():
        tail = base["mint"][-4:]
        name = f"{base['symbol']}/{quote['symbol']} Volume ({tail})"

    now = datetime.now(timezone.utc)
    campaign = {
        "id": str(uuid.uuid4())[:8],
        "user_wallet": user_wallet.strip(),
        "name": name,
        "base_token": base["symbol"],
        "quote_token": quote["symbol"],
        "base_mint": base["mint"],
        "quote_mint": quote["mint"],
        "pool_address": infra.get("pool_address"),
        "pool_exists": dlmm_ready,
        "pool_creation_cost_sol": pool_cost,
        "trade_amount": trade_amount,
        "interval": interval,
        "interval_minutes": interval_minutes,
        "total_budget": total_budget,
        "spent_so_far": 0.0,
        "max_executions": max_executions,
        "executions_count": 0,
        "slippage_bps": slippage_bps,
        "platform_fee_rate": VOLUME_PLATFORM_FEE_RATE,
        "status": "active",
        "created_at": now.isoformat(),
        "next_execution_at": now.isoformat(),
        "executions": [],
        "infrastructure": {
            "initial_check": infra,
            "seed_token_amount": seed_token_amount,
        },
    }
    insert_volume_campaign(campaign)

    source = str(infra.get("source") or "")
    if infra.get("pool_address"):
        venue = "existing Meteora pool"
    elif "meteora" in source.lower():
        venue = "existing Meteora liquidity (via Jupiter)"
    else:
        venue = "existing Jupiter route"
    return {
        "status": "created",
        "campaign": campaign,
        "infrastructure": infra,
        "platform_fee_rate": VOLUME_PLATFORM_FEE_RATE,
        "message": f"Volume campaign **{name}** is active on {venue}.",
    }


def update_volume_campaign_status(campaign_id: str, action: str, user_wallet: Optional[str] = None) -> dict[str, Any]:
    if user_wallet:
        owned = _assert_campaign_owner(campaign_id, user_wallet)
        if "error" in owned:
            return owned
        campaign = owned
    else:
        campaign = find_volume_campaign(campaign_id)
        if not campaign:
            return {"error": f"Campaign '{campaign_id}' not found."}

    action = (action or "").strip().lower()
    mapping = {
        "pause": "paused",
        "resume": "active",
        "cancel": "cancelled",
        "stop": "cancelled",
    }
    if action not in mapping:
        return {"error": f"Unknown action '{action}'. Use pause, resume, or cancel."}
    new_status = mapping[action]
    updated = update_volume_campaign(campaign_id, {"status": new_status})
    if new_status == "cancelled":
        _maybe_reclaim_after_campaign_end(campaign)
    return {"status": new_status, "campaign": updated}


def _execute_meteora_swap(
    input_mint: str,
    output_mint: str,
    amount: float,
    input_decimals: int,
    slippage_bps: int,
    pool_address: Optional[str] = None,
) -> dict[str, Any]:
    keypair = load_volume_keypair()
    if not keypair:
        return {"error": "Volume agent wallet not configured (VOLUME_AGENT_WALLET_PRIVATE_KEY)."}
    if not _is_mainnet():
        return {"error": "Volume Agent swaps require mainnet."}

    wallet_pubkey = str(keypair.pubkey())
    raw_amount = int(round(float(amount) * (10 ** int(input_decimals))))
    if raw_amount <= 0:
        return {"error": "Swap amount too small."}

    params: dict[str, Any] = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(raw_amount),
        "taker": wallet_pubkey,
        "payer": wallet_pubkey,
        "slippageBps": str(slippage_bps),
        "wrapAndUnwrapSol": "true",
        "computeUnitPricePercentile": "high",
        "maxAccounts": "54",
        "skipUserAccountsRpcCalls": "true",
    }

    try:
        resp = _jupiter_get(JUPITER_BUILD_API, params)
        if not resp.ok:
            return {"error": f"Jupiter build failed: {resp.status_code} {resp.text[:300]}"}
        build_data = resp.json()
        if build_data.get("error"):
            return {"error": str(build_data["error"])}
        result = _execute_jupiter_swap_v2(build_data, wallet_pubkey, keypair)
        if result.get("status") == "success":
            out_raw = int(build_data.get("outAmount") or 0)
            if out_raw > 0:
                result["output_amount_raw"] = out_raw
        return result
    except Exception as exc:
        return {"error": str(exc)}


def _record_execution_failure(
    campaign_id: str, campaign: dict[str, Any], leg: str, leg_result: dict[str, Any]
) -> dict[str, Any]:
    """
    Track consecutive failures and auto-pause a campaign rather than letting the
    scheduler retry forever — an unattended retry loop silently drains the wallet
    on Solana network fees even when every attempt fails.
    """
    failures = int(campaign.get("consecutive_failures") or 0) + 1
    updates: dict[str, Any] = {"consecutive_failures": failures, "last_error": {"leg": leg, **leg_result}}
    auto_paused = failures >= MAX_CONSECUTIVE_FAILURES
    if auto_paused:
        updates["status"] = "failed"
    update_volume_campaign(campaign_id, updates)

    result = {"campaign_id": campaign_id, "leg": leg, "consecutive_failures": failures, **leg_result}
    if auto_paused:
        result["auto_paused"] = True
        result["message"] = (
            f"Campaign auto-paused after {failures} consecutive failed attempts "
            f"(last error: {leg_result.get('error', 'unknown')}). No further retries "
            f"will run until you review and resume it."
        )
        _maybe_reclaim_after_campaign_end(campaign)
    return result


def _maybe_reclaim_after_campaign_end(campaign: dict[str, Any]) -> None:
    """
    Best-effort: when a campaign reaches a terminal state, close its base-token
    account and reclaim the ~0.002 SOL rent — but only if no other active/paused
    campaign for the same user still trades that same token.
    """
    try:
        user_wallet = (campaign.get("user_wallet") or "").strip()
        base_mint = campaign.get("base_mint")
        campaign_id = campaign.get("id")
        if not user_wallet or not base_mint:
            return
        others_still_using_token = any(
            c.get("id") != campaign_id
            and c.get("base_mint") == base_mint
            and c.get("status") in {"active", "paused", "provisioning"}
            for c in load_all_volume_campaigns(user_wallet)
        )
        if others_still_using_token:
            return
        result = reclaim_token_account_rent(base_mint)
        if result.get("status") == "closed":
            print(f"  💰 Reclaimed {result['reclaimed_sol']} SOL rent for {campaign.get('base_token')} account ({result.get('signature')})")
        elif result.get("error"):
            print(f"  ⚠️  Rent reclaim skipped for {campaign.get('base_token')}: {result['error']}")
    except Exception as exc:
        print(f"  ⚠️  Rent reclaim check failed: {exc}")


def _run_volume_execution(campaign_id: str, *, dry_run: bool = False, force: bool = False) -> dict[str, Any]:
    campaign = find_volume_campaign(campaign_id)
    if not campaign:
        return {"error": f"Campaign '{campaign_id}' not found."}
    if campaign.get("status") != "active" and not force:
        return {"error": f"Campaign is {campaign.get('status')}, not active."}
    if not campaign.get("pool_address") and campaign.get("status") == "provisioning":
        provisioned = provision_campaign_infrastructure(campaign_id)
        if provisioned.get("error"):
            return provisioned
        campaign = find_volume_campaign(campaign_id) or campaign

    trade_amount = float(campaign.get("trade_amount") or 0)
    quote_token = campaign.get("quote_token", "SOL")
    base_token = campaign.get("base_token")
    user_wallet = (campaign.get("user_wallet") or "").strip()
    max_exec = int(campaign.get("max_executions") or 0)
    executions_count = int(campaign.get("executions_count") or 0)
    interval_minutes = float(campaign.get("interval_minutes") or 1)
    slippage_bps = int(campaign.get("slippage_bps") or 100)
    spent = float(campaign.get("spent_so_far") or 0)
    budget = _coerce_nullable_float(campaign.get("total_budget"))
    pool_address = campaign.get("pool_address")

    per_leg_cost = volume_execution_total_cost(trade_amount)
    cycle_cost = per_leg_cost * 2
    if budget is not None and spent + cycle_cost > budget + 1e-12:
        update_volume_campaign(campaign_id, {"status": "completed"})
        _maybe_reclaim_after_campaign_end(campaign)
        return {"error": "Budget exhausted. Campaign marked completed.", "campaign_id": campaign_id}
    if max_exec and executions_count >= max_exec:
        update_volume_campaign(campaign_id, {"status": "completed"})
        _maybe_reclaim_after_campaign_end(campaign)
        return {"error": "Max executions reached. Campaign marked completed.", "campaign_id": campaign_id}

    if not dry_run and user_wallet:
        check = check_user_can_spend_volume(
            user_wallet, quote_token, cycle_cost, exclude_campaign_id=campaign_id
        )
        if "error" in check:
            # Route through the same failure/auto-pause tracking as buy/sell-leg
            # failures — otherwise an underfunded campaign retries forever every
            # poll with no auto-pause and no clear signal to the user.
            return _record_execution_failure(campaign_id, campaign, "balance_check", check)

    base = resolve_token(base_token)
    quote = resolve_token(quote_token)
    if "error" in base or "error" in quote:
        return base if "error" in base else quote

    if dry_run:
        return {
            "campaign_id": campaign_id,
            "dry_run": True,
            "preview": {
                "buy": f"{trade_amount} {quote_token} → {base_token}",
                "sell": f"~{trade_amount} {base_token} → {quote_token}",
                "platform_fee_per_leg": volume_platform_fee(trade_amount),
                "platform_fee_rate": VOLUME_PLATFORM_FEE_RATE,
                "pool_address": pool_address,
            },
        }

    buy = _execute_meteora_swap(
        quote["mint"], base["mint"], trade_amount, quote["decimals"], slippage_bps, pool_address
    )
    if buy.get("status") != "success":
        return _record_execution_failure(campaign_id, campaign, "buy", buy)

    if user_wallet:
        record_user_spend_volume(user_wallet, quote_token, trade_amount, reference_id=f"{campaign_id}-buy", signature=buy.get("signature"))
        record_volume_platform_fee(user_wallet, quote_token, trade_amount, reference_id=f"{campaign_id}-buy-fee", signature=buy.get("signature"))

    out_raw = int(buy.get("output_amount_raw") or 0)
    buy_amount_base = out_raw / (10 ** base["decimals"]) if out_raw > 0 else trade_amount * 0.98
    sell_amount = buy_amount_base

    if user_wallet:
        record_user_acquire_volume(
            user_wallet,
            base_token,
            buy_amount_base,
            reference_id=f"{campaign_id}-buy-base",
            signature=buy.get("signature"),
        )

    sell = _execute_meteora_swap(
        base["mint"], quote["mint"], sell_amount, base["decimals"], slippage_bps, pool_address
    )
    if sell.get("status") != "success":
        result = _record_execution_failure(campaign_id, campaign, "sell", sell)
        result["buy"] = buy
        return result

    if user_wallet:
        record_user_spend_volume(
            user_wallet,
            base_token,
            sell_amount,
            reference_id=f"{campaign_id}-sell-base",
            signature=sell.get("signature"),
        )
        # Fee must be recorded in quote-currency (SOL) terms — sell_amount above is
        # the base-token quantity sold, not SOL, and was wrongly passed here before
        # (produced fee "spends" thousands of times too large, corrupting the ledger).
        # Use the actual SOL proceeds from the sell leg, falling back to trade_amount.
        sell_out_raw = int(sell.get("output_amount_raw") or 0)
        sell_proceeds_sol = (
            sell_out_raw / (10 ** quote["decimals"]) if sell_out_raw > 0 else trade_amount
        )
        record_volume_platform_fee(user_wallet, quote_token, sell_proceeds_sol, reference_id=f"{campaign_id}-sell-fee", signature=sell.get("signature"))
        # The sell leg returns SOL to this same agent wallet — without crediting it
        # back, the ledger only ever debited the buy leg and never reflected the
        # round-trip proceeds, overstating each cycle's real cost by ~20x.
        record_user_credit_volume(user_wallet, quote_token, sell_proceeds_sol, reference_id=f"{campaign_id}-sell-return", signature=sell.get("signature"))

    now = datetime.now(timezone.utc)
    exec_record = {
        "at": now.isoformat(),
        "cycle": executions_count + 1,
        "trade_amount": trade_amount,
        "platform_fee_rate": VOLUME_PLATFORM_FEE_RATE,
        "buy": {k: v for k, v in buy.items() if k != "build_data"},
        "sell": {k: v for k, v in sell.items() if k != "build_data"},
        "pool_address": pool_address,
    }
    next_run = now + timedelta(minutes=interval_minutes)
    executions = (campaign.get("executions") or []) + [exec_record]
    update_volume_campaign(
        campaign_id,
        {
            "executions_count": executions_count + 1,
            "spent_so_far": round(spent + cycle_cost, 9),
            "next_execution_at": next_run.isoformat(),
            "executions": executions[-50:],
            "consecutive_failures": 0,
        },
    )
    return {
        "status": "success",
        "campaign_id": campaign_id,
        "cycle": executions_count + 1,
        "buy_signature": buy.get("signature"),
        "sell_signature": sell.get("signature"),
        "platform_fee_rate": VOLUME_PLATFORM_FEE_RATE,
        "next_execution_at": next_run.isoformat(),
        "message": f"Volume cycle {executions_count + 1} completed on pool {pool_address}.",
    }


def _scheduler_loop() -> None:
    while not _scheduler_stop.is_set():
        try:
            for campaign in claim_provisioning_volume_campaigns():
                print(f"\n  Pool provision retry: {campaign.get('name')} ({campaign.get('id')})")
                result = provision_campaign_infrastructure(campaign["id"])
                if result.get("error"):
                    print(f"  Provision failed: {result.get('error')}")

            for campaign in claim_due_volume_campaigns():
                print(f"\n  ⏰ Volume due: {campaign.get('name')} ({campaign.get('id')}) · user {str(campaign.get('user_wallet',''))[:8]}…")
                result = _run_volume_execution(campaign["id"])
                if result.get("error"):
                    print(f"  ⚠️  {result.get('error')}")
        except Exception as exc:
            print(f"  ⚠️  Volume scheduler error: {exc}")
        _scheduler_stop.wait(VOLUME_SCHEDULER_POLL_SECONDS)


def start_volume_scheduler() -> bool:
    global _scheduler_thread
    if _scheduler_thread and _scheduler_thread.is_alive():
        return True
    if not get_volume_wallet_pubkey():
        print("  ⚠️  Volume scheduler skipped (VOLUME_AGENT_WALLET_PRIVATE_KEY not set)")
        return False
    _scheduler_stop.clear()
    _scheduler_thread = threading.Thread(target=_scheduler_loop, name="volume-scheduler", daemon=True)
    _scheduler_thread.start()
    return True


def stop_volume_scheduler() -> None:
    _scheduler_stop.set()


def _format_create_campaign_reply(result: dict[str, Any]) -> str:
    if result.get("error"):
        return f"Could not create campaign: {result['error']}"
    campaign = result.get("campaign") or {}
    lines = [
        result.get("message") or "Volume campaign created.",
        "",
        f"- ID: `{campaign.get('id', '—')}`",
        f"- Pair: **{campaign.get('base_token')} / {campaign.get('quote_token')}**",
        f"- Trade size: **{campaign.get('trade_amount')} {campaign.get('quote_token')}** per leg",
        f"- Interval: **{campaign.get('interval')}**",
        f"- Cycles: **{campaign.get('max_executions')}**",
        f"- Status: **{campaign.get('status')}**",
        f"- Pool (Meteora): `{campaign.get('pool_address') or 'not set yet'}`",
        "",
        "Not financial advice. DYOR.",
    ]
    infra = result.get("infrastructure") or {}
    if infra.get("error"):
        lines.insert(1, f"\nInfrastructure: {infra['error']}")
    if campaign.get("status") == "failed":
        err = (campaign.get("infrastructure") or {}).get("pool_creation_error") or {}
        if isinstance(err, dict) and err.get("error"):
            lines.insert(1, f"\nPool setup failed: {err['error']}")
    return "\n".join(lines)


def _parse_create_volume_campaign_request(user_input: str) -> Optional[dict[str, Any]]:
    """Parse natural-language volume campaign requests without LLM tool calls."""
    text = (user_input or "").strip()
    lower = text.lower()
    if not text:
        return None
    if not re.search(r"\b(create|start|launch|run|swap|campaign|campagin|volume)\b", lower):
        return None

    base_token: Optional[str] = None
    quote_token: Optional[str] = None
    trade_amount: Optional[float] = None

    arrow_match = re.search(
        r"(\d+(?:\.\d+)?)\s*(sol|usdc|usdt)\s*(?:->|→|to|into)\s*(sol|usdc|usdt|[1-9A-HJ-NP-Za-km-z]{32,44})",
        lower,
    )
    if arrow_match:
        trade_amount = float(arrow_match.group(1))
        quote_token = arrow_match.group(2).upper()
        dest = arrow_match.group(3)
        base_token = dest if _looks_like_mint(dest) else dest.upper()
    else:
        amount_match = re.search(r"\b(\d+(?:\.\d+)?)\s*(sol|usdc|usdt)\b", lower)
        if amount_match:
            trade_amount = float(amount_match.group(1))
            quote_token = amount_match.group(2).upper()
        mint_match = re.search(r"[1-9A-HJ-NP-Za-km-z]{32,44}", text)
        if mint_match:
            base_token = mint_match.group(0)
        for sym in ("USDC", "USDT", "SOL", "JUP", "BONK"):
            if quote_token and sym == quote_token:
                continue
            if re.search(rf"\b{sym.lower()}\b", lower):
                base_token = base_token or sym
                break

    if trade_amount is None or not base_token:
        return None
    if not quote_token:
        quote_token = "SOL"

    max_match = re.search(
        r"(?:for\s+)?(\d+)\s*(?:times?|trx|transactions?|cycles?|executions?|swaps?)\b",
        lower,
    )
    if not max_match:
        return None
    max_executions = int(max_match.group(1))

    interval_match = re.search(
        r"every\s+(\d+)\s*(second|seconds|sec|secs|s|minute|minutes|min|mins|m)\b",
        lower,
    )
    if interval_match:
        count, unit = interval_match.groups()
        unit = unit.rstrip(".")
        unit_aliases = {
            "sec": "seconds",
            "secs": "seconds",
            "s": "seconds",
            "min": "minutes",
            "mins": "minutes",
            "m": "minutes",
        }
        interval = f"{count} {unit_aliases.get(unit, unit)}"
    else:
        interval = os.environ.get("VOLUME_DEFAULT_INTERVAL", "30 seconds")

    return {
        "base_token": base_token,
        "quote_token": quote_token,
        "trade_amount": trade_amount,
        "interval": interval,
        "max_executions": max_executions,
    }


def _looks_like_mint(value: str) -> bool:
    value = (value or "").strip()
    return len(value) >= 32 and bool(re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]+", value))


def run_volume_agent_with_actions(
    user_input: str,
    conversation_history: list,
    *,
    user_wallet: Optional[str] = None,
    session_id: Optional[str] = None,
) -> tuple[str, list, list[dict[str, Any]]]:
    """Lightweight command router for Volume Agent chat (no multi-turn Ollama tools)."""
    del session_id
    text = user_input.strip()
    lower = text.lower()
    actions: list[dict[str, Any]] = []

    if re.search(r"\b(list|show|view)\b", lower) and "campaign" in lower:
        result = list_volume_campaigns(user_wallet)
        reply = f"You have **{result['count']}** volume campaign(s)."
        for c in result.get("campaigns") or []:
            reply += (
                f"\n- `{c.get('id')}` **{c.get('name')}** · {c.get('status')} · "
                f"{c.get('executions_count', 0)}/{c.get('max_executions')} cycles · pool {c.get('pool_address') or 'pending'}"
            )
        reply += "\n\nNot financial advice. DYOR."
        actions.append({"tool": "list_volume_campaigns", "args": {}, "result": json.dumps(result)})
        conversation_history.append({"role": "user", "content": text})
        conversation_history.append({"role": "assistant", "content": reply})
        return reply, conversation_history, actions

    parsed = _parse_create_volume_campaign_request(text)
    if parsed:
        if not user_wallet:
            reply = "Connect your wallet and sign in before creating a volume campaign."
        else:
            args = {**parsed, "user_wallet": user_wallet.strip()}
            result = create_volume_campaign(**args)
            reply = _format_create_campaign_reply(result)
            actions.append({
                "tool": "create_volume_campaign",
                "args": {k: v for k, v in args.items() if k != "user_wallet"},
                "result": json.dumps(result, default=str),
            })
        conversation_history.append({"role": "user", "content": text})
        conversation_history.append({"role": "assistant", "content": reply})
        return reply, conversation_history, actions

    if "pool" in lower and re.search(r"\b(check|status|infra|setup|create)\b", lower):
        pair_match = re.search(
            r"(\w+|sol|usdc|usdt|[1-9A-HJ-NP-Za-km-z]{32,44})\s*(?:/|->|→|and|&)\s*(\w+|sol|usdc|usdt|[1-9A-HJ-NP-Za-km-z]{32,44})",
            lower,
        )
        create_pool = bool(re.search(r"\b(create|setup|provision)\b", lower))
        if pair_match:
            base_t = pair_match.group(1).upper() if len(pair_match.group(1)) <= 8 else pair_match.group(1)
            quote_t = pair_match.group(2).upper() if len(pair_match.group(2)) <= 8 else pair_match.group(2)
            result = ensure_volume_meteora_pool(
                base_token=base_t,
                quote_token=quote_t,
                user_wallet=user_wallet.strip() if user_wallet else None,
                create_if_missing=create_pool and bool(user_wallet),
            )
            args = {"base_token": base_t, "quote_token": quote_t, "create_if_missing": create_pool}
        else:
            mint_match = re.search(r"[1-9A-HJ-NP-Za-km-z]{32,44}", text)
            if mint_match:
                args = {"token_mint": mint_match.group(0)}
                result = check_pool_infrastructure(args["token_mint"])
            else:
                result = {"error": "Provide two tokens (e.g. USDC/SOL) to check Meteora DLMM pool."}
                args = {}
        if result.get("pool_address"):
            reply = (
                f"**Meteora DLMM pool:** `{result['pool_address']}`\n"
                f"Pair: **{result.get('pair') or result.get('base_token', '—')}/{result.get('quote_token', 'SOL')}**\n"
                f"View: {result.get('meteora_url') or meteora_pool_app_url(result['pool_address'])}"
            )
        else:
            reply = result.get("message") or result.get("error") or json.dumps(result)
        actions.append({"tool": "ensure_meteora_dlmm_pool" if pair_match else "check_pool_infrastructure", "args": args, "result": json.dumps(result, default=str)})
        conversation_history.append({"role": "user", "content": text})
        conversation_history.append({"role": "assistant", "content": reply})
        return reply, conversation_history, actions

    reply = (
        "Volume Agent helps you run Meteora DLMM volume campaigns.\n\n"
        "**Create a campaign** using the form above, or say:\n"
        "`Create campaign: swap 0.0001 SOL -> USDC for 3 times every 30 seconds`\n\n"
        "Requirements:\n"
        f"- Deposit **SOL** (and your base token if needed) to the Volume Agent wallet\n"
        f"- The pair must already trade on Jupiter (same as BITAGENTS Volume — no new pool is created)\n"
        f"- Platform fee: **0.25% per swap leg** (buy and sell)\n\n"
        "Not financial advice. DYOR."
    )
    conversation_history.append({"role": "user", "content": text})
    conversation_history.append({"role": "assistant", "content": reply})
    return reply, conversation_history, actions
