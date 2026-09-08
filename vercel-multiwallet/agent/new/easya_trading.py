"""
EasyA Analysis Agent trading ΓÇö Jupiter market/limit buy orders (one-time, non-recurring).

Users deposit SOL to EASYA_ANALYSIS_AGENT_WALLET_PRIVATE_KEY; orders execute via Jupiter.
Platform fee: 0.1% on successful fills.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from db import claim_due_easya_orders, get_conn, init_db
from dca_agent import (
    HAS_SOLDERS,
    _build_and_execute_swap,
    _is_mainnet,
    _lamports,
    resolve_token,
)
from easya_screener_client import resolve_token as screener_resolve_token
from easya_trading_ledger import (
    check_easya_can_spend_order,
    easya_execution_total_cost,
    easya_platform_fee,
    get_easya_wallet_pubkey,
    load_easya_keypair,
    record_easya_acquire,
    record_easya_platform_fee,
    record_easya_spend,
)

EASYA_ORDER_POLL_SECONDS = int(os.environ.get("EASYA_ORDER_POLL_SECONDS", "30"))
THRESHOLD_CHECK_INTERVAL_SECONDS = int(os.environ.get("EASYA_THRESHOLD_CHECK_SECONDS", "900"))
MIN_CHECK_INTERVAL_SECONDS = int(os.environ.get("EASYA_MIN_CHECK_SECONDS", "60"))
METRICS_CACHE_SECONDS = int(os.environ.get("EASYA_METRICS_CACHE_SECONDS", "900"))
_order_lock = threading.Lock()
_order_scheduler_running = False
_token_metrics_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _token_metrics(token: str) -> dict[str, Optional[float]]:
    screener = screener_resolve_token(token)
    if isinstance(screener, dict) and screener.get("error"):
        return {"price_usd": None, "market_cap_usd": None}
    return {
        "price_usd": _float_or_none(screener.get("price_usd")),
        "market_cap_usd": _float_or_none(screener.get("market_cap_usd")),
    }


def _cached_token_metrics(token: str, *, force_refresh: bool = False) -> dict[str, Any]:
    key = (token or "").strip().upper()
    now = time.time()
    if not force_refresh and key in _token_metrics_cache:
        expires_at, payload = _token_metrics_cache[key]
        if expires_at > now:
            return payload

    raw = _token_metrics(token)
    cached_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "price_usd": raw.get("price_usd"),
        "market_cap_usd": raw.get("market_cap_usd"),
        "cached_at": cached_at,
        "cache_ttl_seconds": METRICS_CACHE_SECONDS,
    }
    _token_metrics_cache[key] = (now + METRICS_CACHE_SECONDS, payload)
    return payload


def _token_price_usd(token: str) -> Optional[float]:
    return _token_metrics(token).get("price_usd")


def _infer_condition_mode(
    *,
    limit_price_usd: Optional[float],
    limit_market_cap_usd: Optional[float],
    condition_mode: Optional[str] = None,
) -> str:
    if condition_mode:
        mode = str(condition_mode).strip().lower()
        if mode in {"price", "market_cap", "both"}:
            return mode
    has_price = limit_price_usd is not None and limit_price_usd > 0
    has_mcap = limit_market_cap_usd is not None and limit_market_cap_usd > 0
    if has_price and has_mcap:
        return "both"
    if has_mcap:
        return "market_cap"
    return "price"


def _validate_buy_triggers(
    *,
    limit_price_usd: Optional[float],
    limit_market_cap_usd: Optional[float],
) -> Optional[str]:
    has_price = limit_price_usd is not None and limit_price_usd > 0
    has_mcap = limit_market_cap_usd is not None and limit_market_cap_usd > 0
    if not has_price and not has_mcap:
        return "Set at least one buy trigger: limit_price_usd and/or limit_market_cap_usd."
    if limit_price_usd is not None and limit_price_usd <= 0:
        return "limit_price_usd must be greater than zero when set."
    if limit_market_cap_usd is not None and limit_market_cap_usd <= 0:
        return "limit_market_cap_usd must be greater than zero when set."
    return None


def _buy_trigger_met(order: dict[str, Any], metrics: dict[str, Optional[float]]) -> bool:
    mode = str(order.get("condition_mode") or "price")
    price = metrics.get("price_usd")
    mcap = metrics.get("market_cap_usd")
    limit_price = order.get("limit_price_usd")
    limit_mcap = order.get("limit_market_cap_usd")

    checks: list[bool] = []
    if mode in {"price", "both"} and limit_price is not None:
        checks.append(price is not None and price <= float(limit_price))
    if mode in {"market_cap", "both"} and limit_mcap is not None:
        checks.append(mcap is not None and mcap <= float(limit_mcap))

    if not checks:
        return False
    return all(checks)


def _stop_trigger_met(order: dict[str, Any], metrics: dict[str, Optional[float]]) -> tuple[bool, Optional[str]]:
    price = metrics.get("price_usd")
    mcap = metrics.get("market_cap_usd")
    stop_price = order.get("stop_price_usd")
    stop_mcap = order.get("stop_market_cap_usd")

    if stop_mcap is not None and mcap is not None and mcap > float(stop_mcap):
        return True, f"Market cap rose above ${stop_mcap:,.0f} (now ${mcap:,.0f})."
    if stop_price is not None and price is not None and price > float(stop_price):
        return True, f"Price rose above ${stop_price} (now ${price})."
    return False, None


def _format_trigger_summary(order: dict[str, Any]) -> str:
    parts: list[str] = []
    token = order.get("output_token") or "token"
    if order.get("limit_price_usd") is not None:
        parts.append(f"price <= ${order['limit_price_usd']}")
    if order.get("limit_market_cap_usd") is not None:
        parts.append(f"market cap <= ${order['limit_market_cap_usd']:,.0f}")
    if not parts:
        return f"No buy trigger configured for {token}"
    mode = order.get("condition_mode") or "price"
    joiner = " AND " if mode == "both" and len(parts) > 1 else " OR " if len(parts) > 1 else ""
    return f"Buy when {token} {joiner.join(parts)}"


def _format_stop_summary(order: dict[str, Any]) -> str:
    parts: list[str] = []
    if order.get("stop_market_cap_usd") is not None:
        parts.append(f"market cap > ${order['stop_market_cap_usd']:,.0f}")
    if order.get("stop_price_usd") is not None:
        parts.append(f"price > ${order['stop_price_usd']}")
    if not parts:
        return "Stops when SOL runs out or max executions reached"
    return "Stop when " + " OR ".join(parts)


def _normalize_check_interval(seconds: Optional[int]) -> int:
    if seconds is None:
        return THRESHOLD_CHECK_INTERVAL_SECONDS
    seconds = int(seconds)
    return max(MIN_CHECK_INTERVAL_SECONDS, seconds)


def _order_row(
    row: dict[str, Any],
    *,
    current_price_usd: Optional[float] = None,
    current_market_cap_usd: Optional[float] = None,
    metrics_cached_at: Optional[str] = None,
) -> dict[str, Any]:
    input_token = row["input_token"]
    output_token = row["output_token"]
    order_type = row["order_type"]
    executions = int(row.get("executions") or 0)
    max_executions = row.get("max_executions")
    recurring = bool(row.get("recurring")) or order_type == "threshold"
    condition_mode = str(row.get("condition_mode") or "price")
    order_dict = {
        "id": row["id"],
        "user_wallet": row["user_wallet"],
        "order_type": order_type,
        "recurring": recurring,
        "condition_mode": condition_mode,
        "input_token": input_token,
        "output_token": output_token,
        "pair": f"{input_token} → {output_token}",
        "input_mint": row["input_mint"],
        "output_mint": row["output_mint"],
        "amount_input": float(row["amount_input"]),
        "limit_price_usd": float(row["limit_price_usd"]) if row.get("limit_price_usd") is not None else None,
        "limit_market_cap_usd": (
            float(row["limit_market_cap_usd"]) if row.get("limit_market_cap_usd") is not None else None
        ),
        "stop_price_usd": float(row["stop_price_usd"]) if row.get("stop_price_usd") is not None else None,
        "stop_market_cap_usd": (
            float(row["stop_market_cap_usd"]) if row.get("stop_market_cap_usd") is not None else None
        ),
        "slippage_bps": int(row.get("slippage_bps") or 100),
        "status": row["status"],
        "executions": executions,
        "max_executions": int(max_executions) if max_executions is not None else None,
        "total_spent": float(row.get("total_spent") or 0),
        "check_interval_seconds": int(row.get("check_interval_seconds") or THRESHOLD_CHECK_INTERVAL_SECONDS),
        "last_checked_at": _iso(row.get("last_checked_at")),
        "last_filled_at": _iso(row.get("last_filled_at")),
        "platform_fee": float(row["platform_fee"]) if row.get("platform_fee") is not None else None,
        "output_amount": float(row["output_amount"]) if row.get("output_amount") is not None else None,
        "signature": row.get("signature"),
        "error_message": row.get("error_message"),
        "created_at": _iso(row.get("created_at")),
        "filled_at": _iso(row.get("filled_at")),
        "cancelled_at": _iso(row.get("cancelled_at")),
        "current_price_usd": current_price_usd,
        "current_market_cap_usd": current_market_cap_usd,
        "metrics_cached_at": metrics_cached_at,
    }
    order_dict["trigger_summary"] = _format_trigger_summary(order_dict)
    order_dict["stop_summary"] = _format_stop_summary(order_dict)
    return order_dict


def resolve_output_token(token: str) -> dict[str, Any]:
    raw = (token or "").strip().lstrip("$")
    if not raw:
        return {"error": "Token symbol or mint is required."}

    resolved = resolve_token(raw)
    if "error" not in resolved:
        return resolved

    screener = screener_resolve_token(raw)
    if isinstance(screener, dict) and screener.get("error"):
        return screener
    if not screener.get("mint"):
        return {"error": f"Could not resolve token '{token}' on Jupiter or EASY Screener."}

    return {
        "symbol": screener.get("symbol") or raw.upper(),
        "mint": screener["mint"],
        "decimals": 6,
        "name": screener.get("name"),
        "source": "easy_screener",
    }


def _insert_order(record: dict[str, Any]) -> dict[str, Any]:
    init_db()
    record.setdefault("recurring", record.get("order_type") == "threshold")
    record.setdefault("executions", 0)
    record.setdefault("total_spent", 0.0)
    record.setdefault("check_interval_seconds", THRESHOLD_CHECK_INTERVAL_SECONDS)
    record.setdefault("condition_mode", _infer_condition_mode(
        limit_price_usd=record.get("limit_price_usd"),
        limit_market_cap_usd=record.get("limit_market_cap_usd"),
        condition_mode=record.get("condition_mode"),
    ))
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO easya_orders (
                    id, user_wallet, order_type, input_token, output_token,
                    input_mint, output_mint, amount_input, limit_price_usd,
                    limit_market_cap_usd, stop_price_usd, stop_market_cap_usd,
                    condition_mode, slippage_bps, status, recurring, max_executions,
                    executions, total_spent, check_interval_seconds, created_at
                ) VALUES (
                    %(id)s, %(user_wallet)s, %(order_type)s, %(input_token)s, %(output_token)s,
                    %(input_mint)s, %(output_mint)s, %(amount_input)s, %(limit_price_usd)s,
                    %(limit_market_cap_usd)s, %(stop_price_usd)s, %(stop_market_cap_usd)s,
                    %(condition_mode)s, %(slippage_bps)s, %(status)s, %(recurring)s, %(max_executions)s,
                    %(executions)s, %(total_spent)s, %(check_interval_seconds)s, NOW()
                )
                RETURNING *
                """,
                record,
            )
            row = cur.fetchone()
    return _order_row(row)


def _record_order_execution(
    order_id: str,
    user_wallet: str,
    *,
    amount_input: float,
    platform_fee: Optional[float],
    output_amount: Optional[float],
    price_usd: Optional[float],
    signature: Optional[str],
    status: str = "success",
    error_message: Optional[str] = None,
) -> None:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO easya_order_executions (
                    order_id, user_wallet, amount_input, platform_fee, output_amount,
                    price_usd, signature, status, error_message, executed_at
                ) VALUES (
                    %(order_id)s, %(user_wallet)s, %(amount_input)s, %(platform_fee)s,
                    %(output_amount)s, %(price_usd)s, %(signature)s, %(status)s,
                    %(error_message)s, NOW()
                )
                """,
                {
                    "order_id": order_id,
                    "user_wallet": user_wallet.strip(),
                    "amount_input": amount_input,
                    "platform_fee": platform_fee,
                    "output_amount": output_amount,
                    "price_usd": price_usd,
                    "signature": signature,
                    "status": status,
                    "error_message": error_message,
                },
            )


def list_easya_order_executions(
    user_wallet: str,
    order_id: Optional[str] = None,
    limit: int = 50,
) -> dict[str, Any]:
    init_db()
    user_wallet = user_wallet.strip()
    limit = max(1, min(int(limit), 100))
    query = "SELECT * FROM easya_order_executions WHERE user_wallet = %s"
    params: list[Any] = [user_wallet]
    if order_id:
        query += " AND order_id = %s"
        params.append(order_id.strip())
    query += " ORDER BY executed_at DESC LIMIT %s"
    params.append(limit)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
    executions = []
    for row in rows:
        executions.append(
            {
                "id": row["id"],
                "order_id": row["order_id"],
                "amount_input": float(row["amount_input"] or 0),
                "platform_fee": float(row["platform_fee"]) if row.get("platform_fee") is not None else None,
                "output_amount": float(row["output_amount"]) if row.get("output_amount") is not None else None,
                "price_usd": float(row["price_usd"]) if row.get("price_usd") is not None else None,
                "signature": row.get("signature"),
                "status": row.get("status"),
                "error_message": row.get("error_message"),
                "executed_at": _iso(row.get("executed_at")),
            }
        )
    return {"user_wallet": user_wallet, "count": len(executions), "executions": executions}


def get_easya_order_executions(user_wallet: str, order_id: str, *, limit: int = 50) -> dict[str, Any]:
    order = get_easya_order(order_id)
    if not order:
        return {"error": "Order not found."}
    if order["user_wallet"] != user_wallet.strip():
        return {"error": "This order belongs to another wallet."}

    result = list_easya_order_executions(user_wallet, order_id=order_id, limit=limit)
    executions = result.get("executions") or []

    if not executions and order.get("signature"):
        fill_price = None
        if order.get("output_amount") and float(order["output_amount"]) > 0:
            fill_price = round(float(order["amount_input"]) / float(order["output_amount"]), 12)
        executions = [
            {
                "id": None,
                "order_id": order_id,
                "amount_input": float(order.get("amount_input") or 0),
                "platform_fee": float(order["platform_fee"]) if order.get("platform_fee") is not None else None,
                "output_amount": float(order["output_amount"]) if order.get("output_amount") is not None else None,
                "price_usd": fill_price,
                "signature": order.get("signature"),
                "status": "success" if order.get("status") in ("filled", "completed") else order.get("status"),
                "error_message": order.get("error_message"),
                "executed_at": _iso(order.get("filled_at") or order.get("last_filled_at") or order.get("created_at")),
            }
        ]

    return {
        "user_wallet": user_wallet.strip(),
        "order_id": order_id,
        "order_type": order.get("order_type"),
        "output_token": order.get("output_token"),
        "count": len(executions),
        "executions": executions,
    }


def _update_order(order_id: str, **fields: Any) -> Optional[dict[str, Any]]:
    if not fields:
        return get_easya_order(order_id)
    init_db()
    sets = ", ".join(f"{key} = %({key})s" for key in fields)
    fields["id"] = order_id
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE easya_orders SET {sets} WHERE id = %(id)s RETURNING *",
                fields,
            )
            row = cur.fetchone()
    return _order_row(row) if row else None


def get_easya_order(order_id: str) -> Optional[dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM easya_orders WHERE id = %s", (order_id.strip(),))
            row = cur.fetchone()
    return _order_row(row) if row else None


def list_easya_orders(
    user_wallet: str,
    *,
    active_only: bool = False,
    limit: int = 50,
    refresh_metrics: bool = False,
) -> dict[str, Any]:
    init_db()
    user_wallet = user_wallet.strip()
    limit = max(1, min(int(limit), 100))
    query = "SELECT * FROM easya_orders WHERE user_wallet = %s"
    params: list[Any] = [user_wallet]
    if active_only:
        query += " AND status IN ('pending', 'active')"
    query += " ORDER BY created_at DESC LIMIT %s"
    params.append(limit)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
    orders = []
    for row in rows:
        metrics = {"price_usd": None, "market_cap_usd": None}
        metrics_cached_at = None
        order_type = row.get("order_type")
        status = row.get("status")
        if order_type == "market":
            cached = _cached_token_metrics(row["output_token"], force_refresh=refresh_metrics)
            metrics = {
                "price_usd": cached.get("price_usd"),
                "market_cap_usd": cached.get("market_cap_usd"),
            }
            metrics_cached_at = cached.get("cached_at")
        elif order_type in ("limit", "threshold") and status in ("active", "pending"):
            live = _token_metrics(row["output_token"])
            metrics = {
                "price_usd": live.get("price_usd"),
                "market_cap_usd": live.get("market_cap_usd"),
            }
        orders.append(
            _order_row(
                row,
                current_price_usd=metrics.get("price_usd"),
                current_market_cap_usd=metrics.get("market_cap_usd"),
                metrics_cached_at=metrics_cached_at,
            )
        )
    return {
        "user_wallet": user_wallet,
        "count": len(orders),
        "orders": orders,
        "metrics_cache_ttl_seconds": METRICS_CACHE_SECONDS,
    }


def execute_easya_swap_buy(
    user_wallet: str,
    output_token: str,
    amount_sol: float,
    *,
    slippage_bps: int = 100,
    order_id: Optional[str] = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    user_wallet = (user_wallet or "").strip()
    amount_sol = float(amount_sol)
    slippage_bps = int(slippage_bps)

    if not user_wallet:
        return {"error": "user_wallet is required."}
    if amount_sol <= 0:
        return {"error": "SOL amount must be greater than zero."}

    spend_check = check_easya_can_spend_order(user_wallet, "SOL", amount_sol)
    if spend_check.get("error"):
        return spend_check

    if dry_run:
        out = resolve_output_token(output_token)
        if "error" in out:
            return out
        return {
            "status": "dry_run",
            "would_buy": f"{amount_sol} SOL -> {out['symbol']}",
            "platform_fee": easya_platform_fee(amount_sol),
            "total_cost": easya_execution_total_cost(amount_sol),
            "output_token": out,
        }

    if not _is_mainnet():
        return {"error": "Jupiter swaps require mainnet. Set SOLANA_CLUSTER=mainnet."}

    keypair = load_easya_keypair()
    if not keypair or not HAS_SOLDERS:
        return {"error": "EASYA_ANALYSIS_AGENT_WALLET_PRIVATE_KEY is not configured."}

    inp = resolve_token("SOL")
    out = resolve_output_token(output_token)
    if "error" in inp:
        return inp
    if "error" in out:
        return out

    wallet_pubkey = str(keypair.pubkey())
    raw_amount = _lamports(amount_sol, inp["decimals"])
    result = _build_and_execute_swap(
        inp["mint"],
        out["mint"],
        raw_amount,
        wallet_pubkey,
        keypair,
        slippage_bps,
    )

    if result.get("status") != "success":
        return result

    ref_id = (order_id or result.get("signature") or "easya_swap")[:128]
    sig = result.get("signature")
    record_easya_spend(
        user_wallet,
        "SOL",
        amount_sol,
        reference_type="easya_swap",
        reference_id=ref_id,
        signature=sig,
    )
    fee_result = record_easya_platform_fee(
        user_wallet,
        amount_sol,
        reference_id=ref_id,
        signature=sig,
    )

    out_raw = int(result.get("output_amount_raw") or 0)
    output_amount = 0.0
    if out_raw > 0:
        output_amount = round(out_raw / (10 ** out["decimals"]), 9)
        record_easya_acquire(
            user_wallet,
            out["symbol"],
            output_amount,
            reference_type="easya_swap",
            reference_id=ref_id,
            signature=sig,
        )

    return {
        **result,
        "input_token": inp["symbol"],
        "output_token": out["symbol"],
        "input_amount": amount_sol,
        "output_amount": output_amount,
        "platform_fee": fee_result.get("fee", easya_platform_fee(amount_sol)),
        "platform_fee_rate": 0.001,
    }


def place_market_buy_order(
    user_wallet: str,
    output_token: str,
    amount_sol: float,
    slippage_bps: int = 100,
) -> dict[str, Any]:
    user_wallet = user_wallet.strip()
    out = resolve_output_token(output_token)
    if "error" in out:
        return out
    inp = resolve_token("SOL")
    if "error" in inp:
        return inp

    order_id = uuid.uuid4().hex[:12]
    order = _insert_order(
        {
            "id": order_id,
            "user_wallet": user_wallet,
            "order_type": "market",
            "input_token": inp["symbol"],
            "output_token": out["symbol"],
            "input_mint": inp["mint"],
            "output_mint": out["mint"],
            "amount_input": float(amount_sol),
            "limit_price_usd": None,
            "slippage_bps": int(slippage_bps),
            "status": "pending",
        }
    )

    swap = execute_easya_swap_buy(
        user_wallet,
        out["symbol"],
        float(amount_sol),
        slippage_bps=int(slippage_bps),
        order_id=order_id,
    )

    if swap.get("status") == "success":
        fill_metrics = _token_metrics(out["symbol"])
        _record_order_execution(
            order_id,
            user_wallet,
            amount_input=float(amount_sol),
            platform_fee=float(swap.get("platform_fee") or easya_platform_fee(amount_sol)),
            output_amount=float(swap.get("output_amount") or 0) if swap.get("output_amount") is not None else None,
            price_usd=fill_metrics.get("price_usd"),
            signature=swap.get("signature"),
            status="success",
        )
        updated = _update_order(
            order_id,
            status="filled",
            platform_fee=swap.get("platform_fee"),
            output_amount=swap.get("output_amount"),
            signature=swap.get("signature"),
            filled_at=datetime.now(timezone.utc),
            executions=1,
            total_spent=float(amount_sol),
        )
        return updated or {**order, **swap}

    _update_order(
        order_id,
        status="failed",
        error_message=str(swap.get("error") or swap.get("status") or "Swap failed"),
    )
    return {"order": order, **swap}


def place_limit_buy_order(
    user_wallet: str,
    output_token: str,
    amount_sol: float,
    *,
    limit_price_usd: Optional[float] = None,
    limit_market_cap_usd: Optional[float] = None,
    condition_mode: Optional[str] = None,
    slippage_bps: int = 100,
) -> dict[str, Any]:
    user_wallet = user_wallet.strip()
    amount_sol = float(amount_sol)
    if amount_sol <= 0:
        return {"error": "amount_sol must be greater than zero."}

    limit_price_usd = _float_or_none(limit_price_usd)
    limit_market_cap_usd = _float_or_none(limit_market_cap_usd)
    trigger_error = _validate_buy_triggers(
        limit_price_usd=limit_price_usd,
        limit_market_cap_usd=limit_market_cap_usd,
    )
    if trigger_error:
        return {"error": trigger_error}

    mode = _infer_condition_mode(
        limit_price_usd=limit_price_usd,
        limit_market_cap_usd=limit_market_cap_usd,
        condition_mode=condition_mode,
    )

    out = resolve_output_token(output_token)
    if "error" in out:
        return out
    inp = resolve_token("SOL")
    if "error" in inp:
        return inp

    check = check_easya_can_spend_order(user_wallet, "SOL", amount_sol)
    if check.get("error"):
        return check

    order_id = uuid.uuid4().hex[:12]
    order = _insert_order(
        {
            "id": order_id,
            "user_wallet": user_wallet,
            "order_type": "limit",
            "input_token": inp["symbol"],
            "output_token": out["symbol"],
            "input_mint": inp["mint"],
            "output_mint": out["mint"],
            "amount_input": amount_sol,
            "limit_price_usd": limit_price_usd,
            "limit_market_cap_usd": limit_market_cap_usd,
            "stop_price_usd": None,
            "stop_market_cap_usd": None,
            "condition_mode": mode,
            "slippage_bps": int(slippage_bps),
            "status": "active",
            "recurring": False,
            "max_executions": 1,
        }
    )
    metrics = _token_metrics(out["symbol"])
    mcap_str = (
        f"${metrics['market_cap_usd']:,.0f}"
        if metrics.get("market_cap_usd") is not None
        else "n/a"
    )
    return {
        **order,
        "message": (
            f"Limit buy placed: spend {amount_sol} SOL for {out['symbol']} "
            f"when {_format_trigger_summary(order)} (one-time, 1 execution). "
            f"Current price: ${metrics.get('price_usd') if metrics.get('price_usd') is not None else 'n/a'}, "
            f"market cap: {mcap_str}"
        ),
        "current_price_usd": metrics.get("price_usd"),
        "current_market_cap_usd": metrics.get("market_cap_usd"),
        "platform_fee_rate": 0.001,
    }


def place_threshold_buy_order(
    user_wallet: str,
    output_token: str,
    amount_sol: float,
    *,
    limit_price_usd: Optional[float] = None,
    limit_market_cap_usd: Optional[float] = None,
    stop_price_usd: Optional[float] = None,
    stop_market_cap_usd: Optional[float] = None,
    condition_mode: Optional[str] = None,
    slippage_bps: int = 100,
    max_executions: Optional[int] = None,
    check_interval_seconds: Optional[int] = None,
) -> dict[str, Any]:
    """Recurring threshold buy until SOL runs out, max executions, or stop condition."""
    user_wallet = user_wallet.strip()
    amount_sol = float(amount_sol)
    if amount_sol <= 0:
        return {"error": "amount_sol must be greater than zero."}

    limit_price_usd = _float_or_none(limit_price_usd)
    limit_market_cap_usd = _float_or_none(limit_market_cap_usd)
    stop_price_usd = _float_or_none(stop_price_usd)
    stop_market_cap_usd = _float_or_none(stop_market_cap_usd)
    trigger_error = _validate_buy_triggers(
        limit_price_usd=limit_price_usd,
        limit_market_cap_usd=limit_market_cap_usd,
    )
    if trigger_error:
        return {"error": trigger_error}

    if max_executions is not None:
        max_executions = int(max_executions)
        if max_executions < 1:
            return {"error": "max_executions must be at least 1 when set."}

    mode = _infer_condition_mode(
        limit_price_usd=limit_price_usd,
        limit_market_cap_usd=limit_market_cap_usd,
        condition_mode=condition_mode,
    )
    interval = _normalize_check_interval(check_interval_seconds)

    out = resolve_output_token(output_token)
    if "error" in out:
        return out
    inp = resolve_token("SOL")
    if "error" in inp:
        return inp

    check = check_easya_can_spend_order(user_wallet, "SOL", amount_sol)
    if check.get("error"):
        return check

    order_id = uuid.uuid4().hex[:12]
    order = _insert_order(
        {
            "id": order_id,
            "user_wallet": user_wallet,
            "order_type": "threshold",
            "input_token": inp["symbol"],
            "output_token": out["symbol"],
            "input_mint": inp["mint"],
            "output_mint": out["mint"],
            "amount_input": amount_sol,
            "limit_price_usd": limit_price_usd,
            "limit_market_cap_usd": limit_market_cap_usd,
            "stop_price_usd": stop_price_usd,
            "stop_market_cap_usd": stop_market_cap_usd,
            "condition_mode": mode,
            "slippage_bps": int(slippage_bps),
            "status": "active",
            "recurring": True,
            "max_executions": max_executions,
            "check_interval_seconds": interval,
        }
    )
    metrics = _token_metrics(out["symbol"])
    max_label = str(max_executions) if max_executions is not None else "until SOL runs out"
    interval_label = f"{interval // 60} min" if interval % 60 == 0 else f"{interval}s"
    mcap_str = (
        f"${metrics['market_cap_usd']:,.0f}"
        if metrics.get("market_cap_usd") is not None
        else "n/a"
    )
    return {
        **order,
        "message": (
            f"Threshold buy placed: spend {amount_sol} SOL for {out['symbol']} "
            f"each time {_format_trigger_summary(order)}. Checks every {interval_label}. "
            f"Stops: {_format_stop_summary(order)}. Max buys: {max_label}. "
            f"Current price: ${metrics.get('price_usd') if metrics.get('price_usd') is not None else 'n/a'}, "
            f"market cap: {mcap_str}"
        ),
        "current_price_usd": metrics.get("price_usd"),
        "current_market_cap_usd": metrics.get("market_cap_usd"),
        "platform_fee_rate": 0.001,
    }


def update_easya_limit_order(
    user_wallet: str,
    order_id: str,
    *,
    amount_sol: Optional[float] = None,
    limit_price_usd: Optional[float] = None,
    limit_market_cap_usd: Optional[float] = None,
    stop_price_usd: Optional[float] = None,
    stop_market_cap_usd: Optional[float] = None,
    slippage_bps: Optional[int] = None,
) -> dict[str, Any]:
    order = get_easya_order(order_id)
    if not order:
        return {"error": "Order not found."}
    if order["user_wallet"] != user_wallet.strip():
        return {"error": "This order belongs to another wallet."}
    if order["order_type"] not in ("limit", "threshold"):
        return {"error": "Only limit and threshold orders can be edited."}
    if order["status"] != "active":
        return {"error": f"Order is {order['status']} and cannot be edited."}

    updates: dict[str, Any] = {}
    if amount_sol is not None:
        amount_sol = float(amount_sol)
        if amount_sol <= 0:
            return {"error": "amount_sol must be greater than zero."}
        old_cost = easya_execution_total_cost(float(order["amount_input"]))
        new_cost = easya_execution_total_cost(amount_sol)
        delta = round(new_cost - old_cost, 12)
        if delta > 0:
            from easya_trading_ledger import get_easya_token_totals

            totals = get_easya_token_totals(user_wallet.strip(), order["input_token"])
            if totals["available_to_spend"] + 1e-12 < delta:
                return {
                    "error": (
                        f"Insufficient {order['input_token']} to increase order size. "
                        f"Need {delta} more SOL (incl. fee), available: {totals['available_to_spend']}."
                    )
                }
        updates["amount_input"] = amount_sol

    if limit_price_usd is not None:
        limit_price_usd = _float_or_none(limit_price_usd)
        if limit_price_usd is not None and limit_price_usd <= 0:
            return {"error": "limit_price_usd must be greater than zero."}
        updates["limit_price_usd"] = limit_price_usd

    if limit_market_cap_usd is not None:
        limit_market_cap_usd = _float_or_none(limit_market_cap_usd)
        if limit_market_cap_usd is not None and limit_market_cap_usd <= 0:
            return {"error": "limit_market_cap_usd must be greater than zero."}
        updates["limit_market_cap_usd"] = limit_market_cap_usd

    if stop_price_usd is not None:
        stop_price_usd = _float_or_none(stop_price_usd)
        if stop_price_usd is not None and stop_price_usd <= 0:
            return {"error": "stop_price_usd must be greater than zero."}
        updates["stop_price_usd"] = stop_price_usd

    if stop_market_cap_usd is not None:
        stop_market_cap_usd = _float_or_none(stop_market_cap_usd)
        if stop_market_cap_usd is not None and stop_market_cap_usd <= 0:
            return {"error": "stop_market_cap_usd must be greater than zero."}
        updates["stop_market_cap_usd"] = stop_market_cap_usd

    if slippage_bps is not None:
        slippage_bps = int(slippage_bps)
        if slippage_bps < 1 or slippage_bps > 5000:
            return {"error": "slippage_bps must be between 1 and 5000."}
        updates["slippage_bps"] = slippage_bps

    if not updates:
        return {
            "error": (
                "No fields to update. Provide amount_sol, limit_price_usd, limit_market_cap_usd, "
                "stop_price_usd, stop_market_cap_usd, and/or slippage_bps."
            )
        }

    next_price = updates.get("limit_price_usd", order.get("limit_price_usd"))
    next_mcap = updates.get("limit_market_cap_usd", order.get("limit_market_cap_usd"))
    trigger_err = _validate_buy_triggers(
        limit_price_usd=_float_or_none(next_price),
        limit_market_cap_usd=_float_or_none(next_mcap),
    )
    if trigger_err:
        return {"error": trigger_err}

    if "limit_price_usd" in updates or "limit_market_cap_usd" in updates:
        updates["condition_mode"] = _infer_condition_mode(
            limit_price_usd=_float_or_none(next_price),
            limit_market_cap_usd=_float_or_none(next_mcap),
            condition_mode=order.get("condition_mode"),
        )

    updated = _update_order(order_id, **updates)
    if not updated:
        return {"error": "Could not update order."}

    metrics = _token_metrics(updated["output_token"])
    order_view = _order_row(
        updated,
        current_price_usd=metrics.get("price_usd"),
        current_market_cap_usd=metrics.get("market_cap_usd"),
    )
    return {
        "status": "updated",
        "order": order_view,
        "message": (
            f"Order updated: spend {updated['amount_input']} {updated['input_token']} "
            f"for {updated['output_token']} when {order_view['trigger_summary']}."
        ),
    }


def cancel_easya_order(user_wallet: str, order_id: str) -> dict[str, Any]:
    order = get_easya_order(order_id)
    if not order:
        return {"error": "Order not found."}
    if order["user_wallet"] != user_wallet.strip():
        return {"error": "This order belongs to another wallet."}
    if order["status"] not in ("pending", "active"):
        return {"error": f"Order is already {order['status']} and cannot be cancelled."}
    updated = _update_order(
        order_id,
        status="cancelled",
        cancelled_at=datetime.now(timezone.utc),
    )
    return {"status": "cancelled", "order": updated}


def _apply_successful_fill(
    order: dict[str, Any],
    swap: dict[str, Any],
    *,
    price_usd: Optional[float],
    complete_after_fill: bool,
) -> None:
    order_id = order["id"]
    user_wallet = order["user_wallet"]
    amount = float(order["amount_input"])
    fee = float(swap.get("platform_fee") or easya_platform_fee(amount))
    spent = round(float(order.get("total_spent") or 0) + amount, 12)
    executions = int(order.get("executions") or 0) + 1
    now = datetime.now(timezone.utc)

    _record_order_execution(
        order_id,
        user_wallet,
        amount_input=amount,
        platform_fee=fee,
        output_amount=float(swap.get("output_amount") or 0) if swap.get("output_amount") is not None else None,
        price_usd=price_usd,
        signature=swap.get("signature"),
        status="success",
    )

    updates: dict[str, Any] = {
        "executions": executions,
        "total_spent": spent,
        "platform_fee": fee,
        "output_amount": swap.get("output_amount"),
        "signature": swap.get("signature"),
        "last_filled_at": now,
        "error_message": None,
    }

    max_exec = order.get("max_executions")
    if complete_after_fill:
        updates["status"] = "filled"
        updates["filled_at"] = now
    elif max_exec is not None and executions >= int(max_exec):
        updates["status"] = "completed"
        updates["filled_at"] = now
        updates["error_message"] = f"Reached max executions ({max_exec})."
    else:
        check = check_easya_can_spend_order(user_wallet, order["input_token"], amount)
        if check.get("error"):
            updates["status"] = "completed"
            updates["filled_at"] = now
            updates["error_message"] = "Insufficient SOL remaining for another buy."
        else:
            updates["status"] = "active"

    _update_order(order_id, **updates)


def _try_fill_limit_order(order: dict[str, Any]) -> None:
    if order.get("status") != "active" or order.get("order_type") != "limit":
        return

    metrics = _token_metrics(order["output_token"])
    if not _buy_trigger_met(order, metrics):
        return

    user_wallet = order["user_wallet"]
    with _order_lock:
        fresh = get_easya_order(order["id"])
        if not fresh or fresh["status"] != "active":
            return
        _update_order(fresh["id"], status="pending")

    swap = execute_easya_swap_buy(
        user_wallet,
        fresh["output_token"],
        float(fresh["amount_input"]),
        slippage_bps=int(fresh.get("slippage_bps") or 100),
        order_id=fresh["id"],
    )

    if swap.get("status") == "success":
        _apply_successful_fill(fresh, swap, price_usd=metrics.get("price_usd"), complete_after_fill=True)
    else:
        _record_order_execution(
            fresh["id"],
            user_wallet,
            amount_input=float(fresh["amount_input"]),
            platform_fee=None,
            output_amount=None,
            price_usd=metrics.get("price_usd"),
            signature=swap.get("signature"),
            status="failed",
            error_message=str(swap.get("error") or "Fill attempt failed"),
        )
        _update_order(
            fresh["id"],
            status="active",
            error_message=str(swap.get("error") or "Fill attempt failed"),
        )


def _try_fill_threshold_order(order: dict[str, Any]) -> None:
    # Due-check + last_checked_at claim lease now happen in claim_due_easya_orders()
    # (SELECT ... FOR UPDATE SKIP LOCKED) before this is ever called — don't re-check
    # here, since last_checked_at was just bumped to NOW() by the claim itself.
    if order.get("status") != "active" or order.get("order_type") != "threshold":
        return

    metrics = _token_metrics(order["output_token"])
    now = datetime.now(timezone.utc)
    should_stop, stop_reason = _stop_trigger_met(order, metrics)
    if should_stop:
        _update_order(
            order["id"],
            status="completed",
            filled_at=now,
            error_message=stop_reason,
        )
        return

    if not _buy_trigger_met(order, metrics):
        return

    user_wallet = order["user_wallet"]
    amount = float(order["amount_input"])
    can_spend = check_easya_can_spend_order(user_wallet, order["input_token"], amount)
    if can_spend.get("error"):
        _update_order(
            order["id"],
            status="completed",
            filled_at=now,
            error_message=str(can_spend["error"]),
        )
        return

    with _order_lock:
        fresh = get_easya_order(order["id"])
        if not fresh or fresh["status"] != "active":
            return
        _update_order(fresh["id"], status="pending")

    swap = execute_easya_swap_buy(
        user_wallet,
        fresh["output_token"],
        amount,
        slippage_bps=int(fresh.get("slippage_bps") or 100),
        order_id=fresh["id"],
    )

    if swap.get("status") == "success":
        _apply_successful_fill(fresh, swap, price_usd=metrics.get("price_usd"), complete_after_fill=False)
        # Re-check stop condition immediately after a fill (e.g. mcap rose above threshold).
        fresh_after = get_easya_order(fresh["id"])
        if fresh_after and fresh_after.get("status") == "active":
            metrics_after = _token_metrics(fresh_after["output_token"])
            stop_after, stop_reason_after = _stop_trigger_met(fresh_after, metrics_after)
            if stop_after:
                _update_order(
                    fresh_after["id"],
                    status="completed",
                    filled_at=datetime.now(timezone.utc),
                    error_message=stop_reason_after,
                )
    else:
        _record_order_execution(
            fresh["id"],
            user_wallet,
            amount_input=amount,
            platform_fee=None,
            output_amount=None,
            price_usd=metrics.get("price_usd"),
            signature=swap.get("signature"),
            status="failed",
            error_message=str(swap.get("error") or "Fill attempt failed"),
        )
        _update_order(
            fresh["id"],
            status="active",
            error_message=str(swap.get("error") or "Fill attempt failed"),
        )


def _order_scheduler_loop() -> None:
    global _order_scheduler_running
    while _order_scheduler_running:
        try:
            for row in claim_due_easya_orders():
                parsed = _order_row(row)
                if parsed.get("order_type") == "threshold":
                    _try_fill_threshold_order(parsed)
                else:
                    _try_fill_limit_order(parsed)
        except Exception as exc:
            print(f"  ΓÜá∩╕Å  EasyA order scheduler error: {exc}")
        time.sleep(max(5, EASYA_ORDER_POLL_SECONDS))


def start_easya_order_scheduler() -> bool:
    global _order_scheduler_running
    if not get_easya_wallet_pubkey():
        return False
    with _order_lock:
        if _order_scheduler_running:
            return False
        _order_scheduler_running = True
        thread = threading.Thread(
            target=_order_scheduler_loop,
            daemon=True,
            name="easya-order-scheduler",
        )
        thread.start()
    return True


def stop_easya_order_scheduler() -> None:
    global _order_scheduler_running
    _order_scheduler_running = False
