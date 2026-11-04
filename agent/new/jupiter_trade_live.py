"""Live Jupiter spot execution for Jupiter Trade Agent via Circle wallets only."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Any, Optional

from jupiter_trade_ledger import (
    JT_AGENT_TYPE,
    JT_PLATFORM_FEE_RATE,
    check_jt_can_spend,
    get_jt_wallet_pubkey,
    jt_execution_total_cost,
    jt_platform_fee,
    record_jt_credit,
    record_jt_platform_fee,
    record_jt_spend,
)

SOL_MINT = "So11111111111111111111111111111111111111112"
SWAP_TIMEOUT_S = float(os.environ.get("JT_SWAP_TIMEOUT_S", "90"))
MIN_SOL_FOR_FEES = float(os.environ.get("JT_MIN_SOL_FOR_FEES", "0.02"))


def _raw_amount(amount: float, decimals: int) -> int:
    return max(1, int(round(float(amount) * (10**int(decimals)))))


def execute_jt_jupiter_swap(
    *,
    input_mint: str,
    output_mint: str,
    amount: float,
    input_decimals: int,
    slippage_bps: int = 100,
    user_wallet: Optional[str] = None,
) -> dict[str, Any]:
    from dca_agent import _build_and_execute_swap, sol_rpc
    from circle_dca_wallets import resolve_agent_signing_context

    user_wallet = (user_wallet or "").strip()
    if not user_wallet:
        return {"error": "user_wallet required for Circle-signed Jupiter Trade swaps."}

    signing = resolve_agent_signing_context(user_wallet, JT_AGENT_TYPE)
    if signing.get("mode") != "circle" or not signing.get("wallet_id") or not signing.get("pubkey"):
        return {
            "error": (
                "Jupiter Trade requires a Circle per-user agent wallet. "
                "Configure CIRCLE_API_KEY and CIRCLE_ENTITY_SECRET, then reopen the agent page."
            ),
            "signing_mode": signing.get("mode"),
            "agent_wallet": get_jt_wallet_pubkey(user_wallet),
        }

    circle_wallet_id = signing["wallet_id"]
    pubkey = signing["pubkey"]
    amount = float(amount)

    try:
        lamports = int((sol_rpc("getBalance", [pubkey]) or {}).get("value", 0))
        sol_balance = lamports / 1e9
        if input_mint == SOL_MINT and sol_balance < amount + MIN_SOL_FOR_FEES:
            return {
                "error": (
                    f"Circle wallet has {sol_balance:.6f} SOL; need {amount + MIN_SOL_FOR_FEES:.6f} "
                    f"including fee reserve. Deposit SOL to {pubkey} and verify."
                ),
                "wallet": pubkey,
            }
    except Exception:
        pass

    raw = _raw_amount(amount, input_decimals)
    api_key = os.environ.get("JUPITER_API_KEY_2", "").strip() or None
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(
        _build_and_execute_swap,
        input_mint,
        output_mint,
        raw,
        pubkey,
        None,  # Circle signs; no local keypair
        slippage_bps=slippage_bps,
        retries=3,
        api_key=api_key,
        circle_wallet_id=circle_wallet_id,
        compute_unit_price_percentile="veryHigh",
    )
    try:
        result = future.result(timeout=SWAP_TIMEOUT_S)
        pool.shutdown(wait=False)
        if isinstance(result, dict):
            result["wallet_provider"] = "circle"
            result["agent_wallet"] = pubkey
        return result
    except FutureTimeout:
        pool.shutdown(wait=False)
        return {"error": f"Swap timed out after {SWAP_TIMEOUT_S}s"}


def deploy_live_from_paper(strategy: dict[str, Any]) -> dict[str, Any]:
    """
    Live confirm: spend verified Circle-ledger SOL and execute Jupiter spot buys.
    """
    user_wallet = str(strategy.get("user_wallet") or "").strip()
    if not user_wallet:
        return {"error": "Missing user wallet on strategy."}
    if not get_jt_wallet_pubkey(user_wallet):
        return {
            "error": (
                "Circle Jupiter Trade wallet is not ready. Check CIRCLE_API_KEY / "
                "CIRCLE_ENTITY_SECRET and reload the page."
            )
        }

    rules = strategy.get("rules") or {}
    mint_map = rules.get("mint_map") or {}
    decimals_map = rules.get("decimals_map") or {}
    symbols = [s for s in (strategy.get("symbols") or []) if s != "SOL"]
    capital_sol = float(strategy.get("cash_sol") or strategy.get("capital_sol") or 0)
    if capital_sol <= 0:
        return {"error": "No SOL capital left to deploy live. Deposit more or keep paper."}

    can = check_jt_can_spend(user_wallet, capital_sol, "SOL")
    if can.get("error"):
        return {
            "error": can["error"],
            "available": can.get("available"),
            "hint": "Deposit SOL to the Circle agent wallet and verify before confirming live.",
        }

    if not symbols:
        return {
            "status": "live_armed",
            "note": "No non-SOL legs to buy. Live monitoring armed; Circle wallet ready.",
            "fills": [],
            "wallet_provider": "circle",
        }

    # Reserve 0.1% platform fee on each leg so fees fit inside capital_sol.
    fee_factor = 1.0 + JT_PLATFORM_FEE_RATE
    per = capital_sol / (len(symbols) * fee_factor)
    fills: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    spent_total = 0.0
    fees_total = 0.0

    for sym in symbols:
        mint = mint_map.get(sym)
        if not mint:
            errors.append({"symbol": sym, "error": "missing mint"})
            continue
        leg_fee = jt_platform_fee(per)
        leg_total = jt_execution_total_cost(per)
        can_leg = check_jt_can_spend(user_wallet, per, "SOL", include_platform_fee=True)
        if can_leg.get("error"):
            errors.append({"symbol": sym, "error": can_leg["error"]})
            continue
        result = execute_jt_jupiter_swap(
            input_mint=SOL_MINT,
            output_mint=mint,
            amount=per,
            input_decimals=9,
            user_wallet=user_wallet,
        )
        if result.get("error") or result.get("status") != "success":
            errors.append({"symbol": sym, "error": result.get("error") or "swap failed"})
            continue
        ref = str(result.get("signature") or strategy.get("id") or "jt_live")
        spend = record_jt_spend(
            user_wallet,
            per,
            reference_id=ref,
            signature=result.get("signature"),
            explorer_url=result.get("explorer_url"),
        )
        if spend.get("error"):
            errors.append({"symbol": sym, "error": spend["error"], "swap": result})
            continue
        fee_rec = record_jt_platform_fee(
            user_wallet,
            per,
            reference_id=f"fee:{ref}",
            signature=result.get("signature"),
            explorer_url=result.get("explorer_url"),
        )
        spent_total += per
        fees_total += float(fee_rec.get("fee") or leg_fee)
        fills.append(
            {
                "symbol": sym,
                "mint": mint,
                "amount_sol": per,
                "platform_fee_sol": float(fee_rec.get("fee") or leg_fee),
                "fee_rate": JT_PLATFORM_FEE_RATE,
                "total_debit_sol": leg_total,
                **result,
            }
        )

    if not fills and errors:
        return {
            "error": "Live deploy failed for all legs. Stay in paper or deposit/fix Circle wallet.",
            "errors": errors,
        }
    return {
        "status": "live_deployed" if fills else "live_armed",
        "fills": fills,
        "errors": errors,
        "spent_sol": spent_total,
        "platform_fees_sol": fees_total,
        "fee_rate": JT_PLATFORM_FEE_RATE,
        "venue": "jupiter_spot",
        "wallet_provider": "circle",
        "decimals_map": decimals_map,
    }


def credit_live_sell_proceeds(
    user_wallet: str,
    amount_sol: float,
    *,
    reference_id: str,
    signature: Optional[str] = None,
    explorer_url: Optional[str] = None,
) -> dict[str, Any]:
    return record_jt_credit(
        user_wallet,
        amount_sol,
        reference_id=reference_id,
        signature=signature,
        explorer_url=explorer_url,
    )
