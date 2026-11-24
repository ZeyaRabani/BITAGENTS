"""Live mainnet execution for built strategies.

Flow: evaluate signals → Jupiter build → Aomi stage/simulate/commit → Circle sign → broadcast.
Paper mode never enters this module.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from . import market, store


def execute_live(agent: dict[str, Any], user_wallet: str) -> dict[str, Any]:
    """Run one live evaluation and send each order on Solana mainnet via the Aomi gate."""
    from circle_dca_wallets import circle_dca_enabled, resolve_agent_signing_context
    from dca_agent import _build_and_execute_swap, _is_mainnet, _lamports

    from .api import evaluate

    if not _is_mainnet():
        raise HTTPException(400, "Live trades require SOLANA_CLUSTER=mainnet (and a mainnet RPC).")
    if agent.get("mode") != "live":
        raise HTTPException(409, "Switch this strategy to live before executing on-chain.")
    if agent.get("build_status") != "ready":
        raise HTTPException(409, "Deploy the strategy first.")
    if not circle_dca_enabled():
        raise HTTPException(503, "Circle wallets are required for live builder trades.")

    signing = resolve_agent_signing_context(user_wallet, "builder")
    if signing.get("mode") != "circle" or not signing.get("pubkey") or not signing.get("wallet_id"):
        raise HTTPException(
            503,
            "Could not provision a Circle builder wallet for this user. Check CIRCLE_API_KEY and CIRCLE_ENTITY_SECRET.",
        )

    payer = str(signing["pubkey"])
    circle_wallet_id = str(signing["wallet_id"])
    decision = evaluate(agent, payer, build=False, caller="execute")
    orders = decision.get("orders") or []
    if not orders:
        return {
            "status": "no_orders",
            "mode": "live",
            "cluster": "mainnet",
            "agent_wallet": payer,
            "decision": decision,
            "fills": [],
            "message": "Strategy evaluated; no orders to send.",
        }

    usdc = market.USDC
    slippage_bps = int((decision.get("limits") or {}).get("slippage_bps") or agent["spec"]["limits"]["slippage_bps"])
    fills: list[dict[str, Any]] = []
    held = {h["mint"]: h for h in (decision.get("wallet") or {}).get("holdings") or []}

    for index, order in enumerate(orders):
        side = str(order.get("side") or "")
        mint = str(order.get("mint") or "")
        usd = float(order.get("usd") or 0)
        try:
            if side == "buy":
                if usd <= 0:
                    fills.append({"index": index, "status": "skipped", "error": "Buy size is zero."})
                    continue
                raw_in = _lamports(usd, usdc["decimals"])
                result = _build_and_execute_swap(
                    usdc["mint"],
                    mint,
                    raw_in,
                    payer,
                    None,
                    slippage_bps,
                    circle_wallet_id=circle_wallet_id,
                    plan_id=f"builder-{agent['id'][:8]}",
                    run_index=index + 1,
                )
            elif side == "sell":
                pos = held.get(mint)
                if not pos or float(pos.get("amount") or 0) <= 0:
                    fills.append({"index": index, "status": "skipped", "error": "No on-chain position to sell."})
                    continue
                decimals = int(pos.get("decimals") or 0)
                raw_in = int(round(float(pos["amount"]) * (10 ** decimals)))
                if raw_in <= 0:
                    fills.append({"index": index, "status": "skipped", "error": "Sell size is zero."})
                    continue
                result = _build_and_execute_swap(
                    mint,
                    usdc["mint"],
                    raw_in,
                    payer,
                    None,
                    slippage_bps,
                    circle_wallet_id=circle_wallet_id,
                    plan_id=f"builder-{agent['id'][:8]}",
                    run_index=index + 1,
                )
            else:
                fills.append({"index": index, "status": "skipped", "error": f"Unknown side {side}."})
                continue
        except Exception as exc:
            fills.append({
                "index": index,
                "side": side,
                "symbol": order.get("symbol"),
                "status": "failed",
                "error": str(exc),
            })
            continue

        fills.append({
            "index": index,
            "side": side,
            "symbol": order.get("symbol"),
            "token_symbol": order.get("token_symbol"),
            "usd": usd,
            "status": result.get("status") or ("success" if result.get("signature") else "failed"),
            "signature": result.get("signature"),
            "explorer_url": result.get("explorer_url"),
            "error": result.get("error"),
            "aomi_digest": result.get("aomi_digest"),
            "aomi_step": result.get("aomi_step"),
            "aomi_summary": result.get("aomi_summary"),
            "agent_wallet": payer,
        })

    ok = sum(1 for f in fills if f.get("status") == "success")
    failed = sum(1 for f in fills if f.get("status") not in {"success", "skipped"})
    status = "success" if ok and not failed else ("partial" if ok else ("skipped" if fills and all(f.get("status") == "skipped" for f in fills) else "failed"))

    store.add_run(
        agent["id"],
        payer,
        "execute",
        True,
        {
            "mode": "live",
            "signals": decision.get("signals"),
            "notes": decision.get("notes"),
            "wallet": decision.get("wallet"),
            "execution": "aomi_gate_circle",
            "status": status,
        },
        fills,
        None if status == "success" else status,
    )

    return {
        "status": status,
        "mode": "live",
        "cluster": "mainnet",
        "execution": "jupiter → aomi stage/simulate/commit → circle sign → broadcast",
        "agent_wallet": payer,
        "decision": {
            "signals": decision.get("signals"),
            "notes": decision.get("notes"),
            "orders": orders,
            "wallet": decision.get("wallet"),
            "limits": decision.get("limits"),
        },
        "fills": fills,
        "message": (
            f"Sent {ok} of {len(fills)} order(s) on mainnet after Aomi commit."
            if ok
            else "No order was broadcast. Check Aomi gate errors and Circle wallet balances (USDC + SOL)."
        ),
    }
