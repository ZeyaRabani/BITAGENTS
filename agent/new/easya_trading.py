"""
EasyA Analysis Agent trading — Jupiter market/limit buy orders (one-time, non-recurring).

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

from db import get_conn, init_db
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
_order_lock = threading.Lock()
_order_scheduler_running = False


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _order_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "user_wallet": row["user_wallet"],
        "order_type": row["order_type"],
        "input_token": row["input_token"],
        "output_token": row["output_token"],
        "input_mint": row["input_mint"],
        "output_mint": row["output_mint"],
        "amount_input": float(row["amount_input"]),
        "limit_price_usd": float(row["limit_price_usd"]) if row.get("limit_price_usd") is not None else None,
        "slippage_bps": int(row.get("slippage_bps") or 100),
        "status": row["status"],
        "platform_fee": float(row["platform_fee"]) if row.get("platform_fee") is not None else None,
        "output_amount": float(row["output_amount"]) if row.get("output_amount") is not None else None,
        "signature": row.get("signature"),
        "error_message": row.get("error_message"),
        "created_at": _iso(row.get("created_at")),
        "filled_at": _iso(row.get("filled_at")),
        "cancelled_at": _iso(row.get("cancelled_at")),
    }


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
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO easya_orders (
                    id, user_wallet, order_type, input_token, output_token,
                    input_mint, output_mint, amount_input, limit_price_usd,
                    slippage_bps, status, created_at
                ) VALUES (
                    %(id)s, %(user_wallet)s, %(order_type)s, %(input_token)s, %(output_token)s,
                    %(input_mint)s, %(output_mint)s, %(amount_input)s, %(limit_price_usd)s,
                    %(slippage_bps)s, %(status)s, NOW()
                )
                RETURNING *
                """,
                record,
            )
            row = cur.fetchone()
    return _order_row(row)


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
    return {
        "user_wallet": user_wallet,
        "count": len(rows),
        "orders": [_order_row(r) for r in rows],
    }


def _token_price_usd(token: str) -> Optional[float]:
    screener = screener_resolve_token(token)
    if isinstance(screener, dict) and screener.get("error"):
        return None
    price = screener.get("price_usd")
    if price is None:
        return None
    try:
        return float(price)
    except (TypeError, ValueError):
        return None


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
        return _update_order(
            order_id,
            status="filled",
            platform_fee=swap.get("platform_fee"),
            output_amount=swap.get("output_amount"),
            signature=swap.get("signature"),
            filled_at=datetime.now(timezone.utc),
        ) or {**order, **swap}

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
    limit_price_usd: float,
    slippage_bps: int = 100,
) -> dict[str, Any]:
    user_wallet = user_wallet.strip()
    limit_price_usd = float(limit_price_usd)
    if limit_price_usd <= 0:
        return {"error": "limit_price_usd must be greater than zero."}

    out = resolve_output_token(output_token)
    if "error" in out:
        return out
    inp = resolve_token("SOL")
    if "error" in inp:
        return inp

    check = check_easya_can_spend_order(user_wallet, "SOL", float(amount_sol))
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
            "amount_input": float(amount_sol),
            "limit_price_usd": limit_price_usd,
            "slippage_bps": int(slippage_bps),
            "status": "active",
        }
    )
    current = _token_price_usd(out["symbol"])
    return {
        **order,
        "message": (
            f"Limit buy placed: spend {amount_sol} SOL for {out['symbol']} "
            f"when price <= ${limit_price_usd}. Current price: "
            f"${current if current is not None else 'n/a'}."
        ),
        "current_price_usd": current,
        "platform_fee_rate": 0.001,
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


def _try_fill_limit_order(order: dict[str, Any]) -> None:
    if order.get("status") != "active" or order.get("order_type") != "limit":
        return
    limit_price = order.get("limit_price_usd")
    if limit_price is None:
        return

    current = _token_price_usd(order["output_token"])
    if current is None or current > float(limit_price):
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
        _update_order(
            fresh["id"],
            status="filled",
            platform_fee=swap.get("platform_fee"),
            output_amount=swap.get("output_amount"),
            signature=swap.get("signature"),
            filled_at=datetime.now(timezone.utc),
        )
    else:
        _update_order(
            fresh["id"],
            status="active",
            error_message=str(swap.get("error") or "Fill attempt failed"),
        )


def _order_scheduler_loop() -> None:
    global _order_scheduler_running
    while _order_scheduler_running:
        try:
            init_db()
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT * FROM easya_orders
                        WHERE status = 'active' AND order_type = 'limit'
                        ORDER BY created_at ASC
                        LIMIT 25
                        """
                    )
                    rows = cur.fetchall()
            for row in rows:
                _try_fill_limit_order(_order_row(row))
        except Exception as exc:
            print(f"  ⚠️  EasyA order scheduler error: {exc}")
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
