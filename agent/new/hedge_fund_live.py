"""Hedge Fund live trading: Jupiter swaps, fees, live positions/trades (separate from paper)."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any, Optional

from psycopg2.extras import Json

from db import get_conn, init_db
from hedge_fund_assets import SOL_MINT, USDC_MINT, resolve_hf_book_mints, resolve_hf_solana_asset
from hedge_fund_ledger import (
    HF_MAX_STRATEGY_USDC,
    HF_MGMT_FEE_RATE,
    HF_PERF_FEE_RATE,
    check_hf_can_spend,
    get_hf_wallet_pubkey,
    load_hf_keypair,
    record_hf_credit,
    record_hf_spend,
    sol_usd_price,
    usdc_notional_from_funding,
)


def _new_id(prefix: str = "hl") -> str:
    return f"{prefix}{secrets.token_hex(4)}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _row(r: Any) -> dict[str, Any]:
    if not r:
        return {}
    out = dict(r)
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


def list_live_trades(strategy_id: str, limit: int = 100) -> list[dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM hf_live_trades
                WHERE strategy_id = %s
                ORDER BY created_at DESC LIMIT %s
                """,
                (strategy_id, limit),
            )
            return [_row(r) for r in cur.fetchall()]


def list_live_positions(strategy_id: str) -> list[dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM hf_live_positions WHERE strategy_id = %s AND units > 0 ORDER BY symbol",
                (strategy_id,),
            )
            return [_row(r) for r in cur.fetchall()]


def open_live_holdings(strategy_id: str) -> list[dict[str, Any]]:
    """Open units to swap back to USDC — positions first, else unmatched BUY fills."""
    positions = [
        p for p in list_live_positions(strategy_id) if float(p.get("units") or 0) > 0
    ]
    if positions:
        return positions
    bought: dict[str, dict[str, Any]] = {}
    sold: dict[str, float] = {}
    for t in list_live_trades(strategy_id, limit=500):
        mint = str(t.get("mint") or "")
        units = float(t.get("units") or 0)
        side = str(t.get("side") or "").upper()
        if not mint or units <= 0:
            continue
        if side == "BUY":
            prev = bought.get(mint) or {
                "mint": mint,
                "symbol": t.get("symbol") or "?",
                "units": 0.0,
                "user_wallet": t.get("user_wallet"),
            }
            prev["units"] = float(prev["units"]) + units
            bought[mint] = prev
        elif side == "SELL":
            sold[mint] = sold.get(mint, 0.0) + units
    leftover = []
    for mint, row in bought.items():
        remaining = float(row["units"]) - sold.get(mint, 0.0)
        if remaining > 1e-9:
            leftover.append({**row, "units": remaining})
    return leftover


def _liquidation_txs(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    txs = []
    seen: set[str] = set()
    for t in trades:
        side = str(t.get("side") or "").upper()
        if side and side not in ("SELL", "FEE"):
            continue
        sig = str(t.get("signature") or "")
        if not sig or sig in seen:
            continue
        seen.add(sig)
        txs.append(
            {
                "signature": sig,
                "explorer_url": t.get("explorer_url")
                or f"https://explorer.solana.com/tx/{sig}",
                "symbol": t.get("symbol"),
                "side": t.get("side"),
            }
        )
    return txs


def _insert_live_trade(
    *,
    strategy_id: str,
    user_wallet: str,
    symbol: str,
    mint: Optional[str],
    side: str,
    units: float,
    price_usd: Optional[float],
    notional_usd: float,
    fee_usd: float = 0.0,
    input_mint: Optional[str] = None,
    output_mint: Optional[str] = None,
    signature: Optional[str] = None,
    explorer_url: Optional[str] = None,
    reason: str = "",
) -> dict[str, Any]:
    init_db()
    tid = _new_id("ht")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO hf_live_trades (
                    id, strategy_id, user_wallet, symbol, mint, side, units, price_usd,
                    notional_usd, fee_usd, input_mint, output_mint, signature, explorer_url, reason
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
                """,
                (
                    tid,
                    strategy_id,
                    user_wallet,
                    symbol,
                    mint,
                    side.upper(),
                    units,
                    price_usd,
                    notional_usd,
                    fee_usd,
                    input_mint,
                    output_mint,
                    signature,
                    explorer_url,
                    reason,
                ),
            )
            return _row(cur.fetchone())


def _upsert_live_position(
    *,
    strategy_id: str,
    user_wallet: str,
    symbol: str,
    mint: str,
    units_delta: float,
    cost_delta_usd: float,
) -> dict[str, Any]:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM hf_live_positions
                WHERE strategy_id = %s AND mint = %s FOR UPDATE
                """,
                (strategy_id, mint),
            )
            row = cur.fetchone()
            if row:
                old_u = float(row["units"] or 0)
                old_cost = float(row["cost_basis_usd"] or 0)
                new_u = old_u + units_delta
                if new_u <= 1e-12:
                    cur.execute("DELETE FROM hf_live_positions WHERE id = %s RETURNING *", (row["id"],))
                    return _row(cur.fetchone()) or {"units": 0}
                if units_delta > 0:
                    new_cost = old_cost + cost_delta_usd
                    avg = new_cost / new_u if new_u else 0
                else:
                    # sell: reduce cost pro-rata
                    frac = min(1.0, abs(units_delta) / old_u) if old_u else 1.0
                    new_cost = max(0.0, old_cost * (1.0 - frac))
                    avg = new_cost / new_u if new_u else 0
                cur.execute(
                    """
                    UPDATE hf_live_positions
                    SET units=%s, avg_entry_usd=%s, cost_basis_usd=%s, updated_at=NOW()
                    WHERE id=%s RETURNING *
                    """,
                    (new_u, avg, new_cost, row["id"]),
                )
                return _row(cur.fetchone())
            if units_delta <= 0:
                return {"error": "No position to sell"}
            pid = _new_id("hz")
            avg = cost_delta_usd / units_delta if units_delta else 0
            cur.execute(
                """
                INSERT INTO hf_live_positions (
                    id, strategy_id, user_wallet, symbol, mint, units, avg_entry_usd, cost_basis_usd
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
                """,
                (pid, strategy_id, user_wallet, symbol, mint, units_delta, avg, cost_delta_usd),
            )
            return _row(cur.fetchone())


def _raw_amount(amount: float, decimals: int) -> int:
    return max(1, int(round(float(amount) * (10 ** int(decimals)))))


SWAP_TIMEOUT_S = 220
# Minimum SOL the HF wallet must hold to reliably pay tx fees + Jupiter's
# priority fee (computeUnitPricePercentile=high) + possible new-ATA rent.
# Below this, transactions get signed and submitted but never land — they
# just silently fail to confirm (skipPreflight bypasses the fee-payer check
# client-side), burning the full 60s confirmation wait for nothing.
MIN_SOL_FOR_FEES = 0.01
# Creating a new SPL token account costs ~0.00203928 SOL rent. After switching
# HF funding to SOL, swaps that spend nearly the whole wallet balance fail with
# InstructionError Custom:1 because nothing is left for the destination ATA.
ATA_RENT_SOL = 0.00204
HF_SOL_FEE_HEADROOM = 0.006  # base fee + Jupiter priority fee cushion


def _sol_operating_reserve(n_assets: int = 1) -> float:
    """SOL that must remain in the HF wallet after funding swaps (ATA rent + fees)."""
    legs = max(1, int(n_assets or 1))
    return round(ATA_RENT_SOL * legs + HF_SOL_FEE_HEADROOM, 9)


def _on_chain_sol_balance(user_wallet: Optional[str] = None) -> Optional[float]:
    from dca_agent import sol_rpc

    pubkey = get_hf_wallet_pubkey(user_wallet)
    if not pubkey:
        return None
    try:
        lamports = int((sol_rpc("getBalance", [pubkey]) or {}).get("value", 0))
        return lamports / 1e9
    except Exception:
        return None


def _humanize_hf_swap_error(err: Any) -> str:
    raw = str(err)
    compact = raw.replace(" ", "")
    lower = raw.lower()
    if "'Custom':1" in compact or '"Custom":1' in compact:
        return (
            "Insufficient SOL left for token-account rent/fees (Custom:1). "
            f"Keep at least ~{_sol_operating_reserve(1):.4f} SOL in the Hedge Fund wallet "
            "beyond the strategy size, then retry."
        )
    if "no routes found" in lower:
        return (
            "Jupiter has no swap route for this mint (often an illiquid Ondo *on token). "
            "Retry the strategy — we now prefer Backed xStocks (e.g. NVDAx) when available."
        )
    if "confirmation timed out" in lower or ("timed out" in lower and "swap" not in lower):
        return (
            "Solana did not confirm the buy in time (tx likely dropped by the RPC). "
            "Your capital was refunded if no fill landed — dismiss, wait a few seconds, "
            "and try again. A private SOLANA_RPC_URL improves landing rates."
        )
    return raw


def execute_hf_jupiter_swap(
    *,
    input_mint: str,
    output_mint: str,
    amount: float,
    input_decimals: int,
    slippage_bps: int = 100,
    user_wallet: Optional[str] = None,
    sol_reserve: Optional[float] = None,
) -> dict[str, Any]:
    import os
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FutureTimeout

    from dca_agent import _build_and_execute_swap, sol_rpc
    from circle_dca_wallets import resolve_agent_signing_context

    signing = resolve_agent_signing_context(user_wallet, "hedge_fund")
    keypair = signing.get("keypair") if signing.get("mode") == "local" else None
    circle_wallet_id = signing.get("wallet_id") if signing.get("mode") == "circle" else None
    pubkey = signing.get("pubkey")
    if not pubkey or (signing.get("mode") == "local" and not keypair):
        return {"error": "Hedge Fund wallet not configured (Circle or HEDGE_FUND_WALLET_PRIVATE_KEY)"}
    amount = float(amount)
    reserve = float(sol_reserve) if sol_reserve is not None else _sol_operating_reserve(1)
    try:
        lamports = int((sol_rpc("getBalance", [pubkey]) or {}).get("value", 0))
        sol_balance = lamports / 1e9
        if sol_balance < MIN_SOL_FOR_FEES:
            return {
                "error": (
                    f"HF wallet has only {sol_balance:.6f} SOL — need at least "
                    f"{MIN_SOL_FOR_FEES} SOL to reliably pay tx fees. Deposit more "
                    f"SOL to {pubkey} before swapping (a low-SOL swap gets signed "
                    "and sent but silently never confirms)."
                ),
                "sol_balance": sol_balance,
            }
        # SOL→token buys must leave rent/fee headroom or Jupiter creates the ATA and fails Custom:1.
        if input_mint == SOL_MINT and sol_balance - amount < reserve - 1e-12:
            return {
                "error": (
                    f"Swap of {amount:.6f} SOL would leave only "
                    f"{max(0.0, sol_balance - amount):.6f} SOL in the HF wallet; "
                    f"need ≥{reserve:.4f} SOL for token-account rent and fees. "
                    f"Deposit more SOL (wallet has {sol_balance:.6f}) or use a smaller size."
                ),
                "sol_balance": sol_balance,
                "sol_reserve": reserve,
            }
    except Exception:
        pass  # Balance check is advisory — don't block the swap on an RPC hiccup here.
    raw = _raw_amount(amount, input_decimals)
    # Use a separate Jupiter API key when configured so Hedge Fund swap
    # traffic doesn't queue behind DCA/volume-agent calls on the shared key's
    # rate-limit budget (falls back to the default JUPITER_API_KEY if unset).
    hf_jupiter_api_key = os.environ.get("JUPITER_API_KEY_2", "").strip() or None
    # Bound each swap so one stuck RPC/Jupiter call cannot hang the whole
    # deploy request forever — a timed-out swap is treated as a failed leg
    # (its unspent capital gets refunded by the partial-failure path). Python
    # threads can't be killed, so on timeout we detach the pool (wait=False)
    # rather than blocking our return on the still-running thread.
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(
        _build_and_execute_swap,
        input_mint,
        output_mint,
        raw,
        pubkey,
        keypair,
        slippage_bps=slippage_bps,
        retries=3,
        api_key=hf_jupiter_api_key,
        circle_wallet_id=circle_wallet_id,
        compute_unit_price_percentile="veryHigh",
    )
    try:
        result = future.result(timeout=SWAP_TIMEOUT_S)
        pool.shutdown(wait=False)
        if result.get("status") != "success" and result.get("error") is not None:
            result = {**result, "error": _humanize_hf_swap_error(result.get("error"))}
        return result
    except _FutureTimeout:
        pool.shutdown(wait=False)
        return {"error": f"Swap timed out after {SWAP_TIMEOUT_S}s (RPC/Jupiter unresponsive)"}


def _token_price_usd(mint_or_symbol: str) -> Optional[float]:
    try:
        from dca_agent import get_token_price

        p = get_token_price(mint_or_symbol)
        if isinstance(p, dict):
            return float(p.get("price_usd") or p.get("usd_price") or 0) or None
        return float(p) if p else None
    except Exception:
        return None


def deploy_live_allocations(
    strategy: dict[str, Any],
    *,
    capital_usd: float,
    funding_token: str = "SOL",
    mint_overrides: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """
    Debit user ledger, charge 1% mgmt fee, Jupiter-swap remaining into equal-weight book.
    """
    strategy_id = strategy["id"]
    user_wallet = strategy["user_wallet"]
    symbols = list(strategy.get("symbols") or [])
    if not symbols:
        return {"error": "No symbols to deploy"}

    capital = min(HF_MAX_STRATEGY_USDC, max(1.0, float(capital_usd)))
    funding_token = (funding_token or "SOL").upper()
    if funding_token != "SOL":
        return {"error": "Funding token must be SOL"}

    # How much funding token to spend for this USDC notional
    if funding_token == "USDC":
        funding_amount = capital
    else:
        px = sol_usd_price()
        if not px:
            return {"error": "Could not price SOL for funding"}
        funding_amount = round(capital / px, 9)

    check = check_hf_can_spend(user_wallet, funding_token, funding_amount, exclude_strategy_id=strategy_id)
    if check.get("error"):
        return check

    mint_info = resolve_hf_book_mints(symbols, mint_overrides=mint_overrides)
    assets = mint_info.get("assets") or []
    if not assets:
        return {"error": "Could not resolve mints", "details": mint_info.get("errors")}

    # SOL funding spends the same asset used for ATA rent / priority fees. Require
    # spare SOL beyond the strategy size so Jupiter can create destination ATAs.
    sol_reserve = _sol_operating_reserve(len(assets))
    if funding_token == "SOL":
        available = float(check.get("available") or 0)
        leftover = available - funding_amount
        if leftover + 1e-12 < sol_reserve:
            need = round(funding_amount + sol_reserve, 9)
            return {
                "error": (
                    f"Need ~{sol_reserve:.4f} SOL left after funding for token-account rent and fees. "
                    f"Available {available:.6f} SOL; strategy needs {funding_amount:.6f} SOL. "
                    f"Deposit at least {need:.6f} SOL total, then retry."
                ),
                "available": available,
                "funding_amount": funding_amount,
                "sol_reserve": sol_reserve,
            }
        on_chain = _on_chain_sol_balance(user_wallet)
        if on_chain is not None and on_chain + 1e-12 < funding_amount + sol_reserve:
            return {
                "error": (
                    f"HF wallet on-chain SOL is {on_chain:.6f}; need ≥"
                    f"{funding_amount + sol_reserve:.6f} (strategy + rent/fee reserve). "
                    "Deposit more SOL to the agent wallet."
                ),
                "sol_balance": on_chain,
                "sol_reserve": sol_reserve,
            }

    mgmt_fee_usd = round(capital * HF_MGMT_FEE_RATE, 6)
    deploy_usd = round(capital - mgmt_fee_usd, 6)
    # Allow small sleeves (e.g. $1) — only reject empty/negative deployable capital
    if deploy_usd <= 0:
        return {"error": "Capital too small after 1% fee"}

    # Ledger: spend full capital from user; record mgmt fee as platform spend portion
    spend = record_hf_spend(
        user_wallet,
        funding_token,
        funding_amount,
        reference_id=f"{strategy_id}-deploy",
        reference_type="hf_strategy_deploy",
    )
    if spend.get("error"):
        return spend
    if funding_token == "USDC":
        fee_token_amt = mgmt_fee_usd
    else:
        fee_token_amt = round(mgmt_fee_usd / (sol_usd_price() or 1), 9)

    input_mint = USDC_MINT if funding_token == "USDC" else SOL_MINT
    input_decimals = 6 if funding_token == "USDC" else 9
    # Amount of funding token available to deploy after fee
    if funding_token == "USDC":
        deploy_funding = deploy_usd
    else:
        deploy_funding = round(funding_amount - fee_token_amt, 9)
        on_chain = _on_chain_sol_balance(user_wallet)
        if on_chain is not None:
            max_spend = max(0.0, round(on_chain - sol_reserve, 9))
            if deploy_funding > max_spend:
                deploy_funding = max_spend
        if deploy_funding <= 0:
            refund = record_hf_credit(
                user_wallet,
                funding_token,
                funding_amount,
                reference_id=f"{strategy_id}-deploy-refund",
                reference_type="hf_strategy_deploy_refund",
            )
            return {
                "ok": False,
                "error": (
                    f"Not enough SOL left after reserving {sol_reserve:.4f} SOL for rent/fees. "
                    "Deposit more SOL and retry."
                ),
                "refunded": True,
                "refund": refund,
                "sol_reserve": sol_reserve,
            }

    per = deploy_funding / len(assets)
    trades = []
    errors = []
    for asset in assets:
        out_mint = asset["mint"]
        sym = asset.get("display_symbol") or asset.get("symbol")
        out_decimals = int(asset.get("decimals") or 6)
        swap = execute_hf_jupiter_swap(
            input_mint=input_mint,
            output_mint=out_mint,
            amount=per,
            input_decimals=input_decimals,
            slippage_bps=150,
            user_wallet=user_wallet,
            sol_reserve=_sol_operating_reserve(1),
        )
        # Illiquid catalog mints (often Ondo *on) → fall back to Jupiter xStock.
        if (
            swap.get("status") != "success"
            and "no routes found" in str(swap.get("error") or "").lower()
        ):
            from hedge_fund_assets import _equity_xstock_from_jupiter

            alt = _equity_xstock_from_jupiter(str(sym))
            alt_mint = (alt or {}).get("mint")
            if alt_mint and alt_mint != out_mint:
                print(f"    ↳ No routes for {sym} ({out_mint[:8]}…); trying {alt.get('symbol')}…")
                out_mint = alt_mint
                out_decimals = int(alt.get("decimals") or out_decimals)
                asset = {**asset, **alt, "mint": out_mint, "decimals": out_decimals}
                swap = execute_hf_jupiter_swap(
                    input_mint=input_mint,
                    output_mint=out_mint,
                    amount=per,
                    input_decimals=input_decimals,
                    slippage_bps=150,
                    user_wallet=user_wallet,
                    sol_reserve=_sol_operating_reserve(1),
                )
        out_raw = int(swap.get("output_amount_raw") or 0)
        # A signature does NOT mean the swap succeeded — the tx may have been
        # submitted but never confirmed (expired blockhash) before our 60s
        # poll gave up, in which case it never landed on-chain. Only a
        # status=="success" result with real output units counts as a fill.
        if swap.get("status") != "success" or out_raw <= 0:
            err_msg = swap.get("error") or str(swap)
            errors.append({"symbol": sym, "error": err_msg, "mint": out_mint})
            _insert_live_trade(
                strategy_id=strategy_id,
                user_wallet=user_wallet,
                symbol=sym,
                mint=out_mint,
                side="ERROR",
                units=0,
                price_usd=None,
                notional_usd=0,
                fee_usd=0,
                input_mint=input_mint,
                output_mint=out_mint,
                signature=swap.get("signature"),
                explorer_url=swap.get("explorer_url"),
                reason=f"Buy failed: {err_msg}"[:500],
            )
            continue
        units = out_raw / (10 ** out_decimals)
        notional = per if funding_token == "USDC" else per * (sol_usd_price() or 0)
        price = (notional / units) if units else None
        explorer = swap.get("explorer_url")
        sig = swap.get("signature")
        if sig and not explorer:
            explorer = f"https://explorer.solana.com/tx/{sig}"
        trade = _insert_live_trade(
            strategy_id=strategy_id,
            user_wallet=user_wallet,
            symbol=sym,
            mint=out_mint,
            side="BUY",
            units=units,
            price_usd=price,
            notional_usd=round(notional, 6),
            fee_usd=round(mgmt_fee_usd / len(assets), 6),
            input_mint=input_mint,
            output_mint=out_mint,
            signature=sig,
            explorer_url=explorer,
            reason="Live strategy entry (Jupiter)",
        )
        trades.append(trade)
        if units > 0:
            _upsert_live_position(
                strategy_id=strategy_id,
                user_wallet=user_wallet,
                symbol=sym,
                mint=out_mint,
                units_delta=units,
                cost_delta_usd=round(notional, 6),
            )

    # Total failure: refund ledger spend so user can retry / withdraw
    if not trades:
        refund = record_hf_credit(
            user_wallet,
            funding_token,
            funding_amount,
            reference_id=f"{strategy_id}-deploy-refund",
            reference_type="hf_strategy_deploy_refund",
        )
        err_summary = "; ".join(
            f"{e.get('symbol')}: {e.get('error')}" for e in errors[:4]
        ) or "All Jupiter buys failed"
        return {
            "ok": False,
            "error": f"Could not buy tokens/stocks — {err_summary}",
            "errors": errors,
            "refunded": True,
            "refund": refund,
            "funding_token": funding_token,
            "funding_amount": funding_amount,
            "trades": [],
            "mint_map": mint_info.get("mint_map"),
            "solana_assets": assets,
        }

    # Partial failure: refund the untouched slice (deploy + fee share) for each
    # failed leg — it was debited from the ledger up front but never spent on-chain.
    refund = None
    charged_fee_usd = mgmt_fee_usd
    if errors:
        num_total = len(assets)
        num_failed = len(errors)
        per_asset_funding = funding_amount / num_total
        refund_amount = round(per_asset_funding * num_failed, 9)
        if refund_amount > 0:
            refund = record_hf_credit(
                user_wallet,
                funding_token,
                refund_amount,
                reference_id=f"{strategy_id}-deploy-partial-refund",
                reference_type="hf_deploy_partial_refund",
            )
        charged_fee_usd = round(mgmt_fee_usd * len(trades) / num_total, 6)

    # Fee trade row (accounting) — only for the capital actually deployed
    if charged_fee_usd > 0:
        _insert_live_trade(
            strategy_id=strategy_id,
            user_wallet=user_wallet,
            symbol="FEE",
            mint=USDC_MINT,
            side="FEE",
            units=0,
            price_usd=1.0,
            notional_usd=charged_fee_usd,
            fee_usd=charged_fee_usd,
            reason=f"1% management fee on ${capital}",
        )

    return {
        "ok": True,
        "capital_usd": capital,
        "mgmt_fee_usd": charged_fee_usd,
        "deploy_usd": deploy_usd,
        "funding_token": funding_token,
        "funding_amount": funding_amount,
        "trades": trades,
        "positions": list_live_positions(strategy_id),
        "mint_map": mint_info.get("mint_map"),
        "solana_assets": assets,
        "errors": errors,
        "refunded_partial": bool(refund and not refund.get("error")),
        "refund": refund,
        "message": (
            f"Live deployed ${deploy_usd:,.2f} after 1% fee (${charged_fee_usd:,.2f}) "
            f"across {len(trades)} fills"
            + (f" · {len(errors)} buy errors (unspent capital refunded)" if errors else "")
            + "."
        ),
    }


def retry_live_deploy(
    strategy: dict[str, Any],
    *,
    replace: Optional[dict[str, str]] = None,
    mint_overrides: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """
    Re-attempt Jupiter buys for legs of an already-confirmed live strategy that
    never filled (e.g. "No routes found", RPC timeout). Only touches legs with
    no successful buy yet — filled legs are left untouched. `replace` swaps a
    failed ticker for a different one (e.g. {"AAPL": "PLTR"}) before retrying.
    """
    strategy_id = strategy["id"]
    user_wallet = strategy["user_wallet"]
    rules = dict(strategy.get("rules") or {})
    symbols = list(strategy.get("symbols") or [])
    if not symbols:
        return {"error": "No symbols on this strategy"}

    replace = {str(k).strip().upper(): str(v).strip().upper() for k, v in (replace or {}).items() if v}

    bought: set[str] = set()
    for t in list_live_trades(strategy_id, limit=200):
        if str(t.get("side") or "").upper() == "BUY" and float(t.get("units") or 0) > 0:
            bought.add(str(t.get("symbol") or "").upper())

    new_symbols = []
    for s in symbols:
        su = s.upper()
        new_symbols.append(replace.get(su, s) if su not in bought else s)
    missing = [s for s in new_symbols if s.upper() not in bought]

    if not missing:
        return {"ok": True, "message": "Nothing to retry — every leg already filled.", "trades": []}

    capital = float(rules.get("capital_usd") or 0)
    funding_token = (rules.get("funding_token") or "SOL").upper()
    if funding_token != "SOL":
        funding_token = "SOL"
    total_legs = max(1, len(symbols))
    per_leg_capital_usd = round((capital * (1.0 - HF_MGMT_FEE_RATE)) / total_legs, 6)
    per_leg_fee_usd = round((capital * HF_MGMT_FEE_RATE) / total_legs, 6)
    per_leg_capital_and_fee_usd = per_leg_capital_usd + per_leg_fee_usd

    if funding_token == "USDC":
        per_leg_funding = per_leg_capital_and_fee_usd
        per_leg_deploy_funding = per_leg_capital_usd
    else:
        px = sol_usd_price()
        if not px:
            return {"error": "Could not price SOL for funding"}
        per_leg_funding = round(per_leg_capital_and_fee_usd / px, 9)
        per_leg_deploy_funding = round(per_leg_capital_usd / px, 9)

    funding_needed = round(per_leg_funding * len(missing), 9)
    check = check_hf_can_spend(user_wallet, funding_token, funding_needed, exclude_strategy_id=strategy_id)
    if check.get("error"):
        return check

    mint_info = resolve_hf_book_mints(missing, mint_overrides=mint_overrides)
    assets = mint_info.get("assets") or []
    if not assets:
        return {"error": "Could not resolve mints for retry", "details": mint_info.get("errors")}

    sol_reserve = _sol_operating_reserve(len(assets))
    if funding_token == "SOL":
        available = float(check.get("available") or 0)
        leftover = available - funding_needed
        if leftover + 1e-12 < sol_reserve:
            need = round(funding_needed + sol_reserve, 9)
            return {
                "error": (
                    f"Need ~{sol_reserve:.4f} SOL left after funding for token-account rent and fees. "
                    f"Available {available:.6f} SOL; retry needs {funding_needed:.6f} SOL. "
                    f"Deposit at least {need:.6f} SOL total, then retry."
                ),
                "available": available,
                "funding_amount": funding_needed,
                "sol_reserve": sol_reserve,
            }

    spend = record_hf_spend(
        user_wallet,
        funding_token,
        funding_needed,
        reference_id=f"{strategy_id}-retry",
        reference_type="hf_strategy_deploy",
    )
    if spend.get("error"):
        return spend

    input_mint = USDC_MINT if funding_token == "USDC" else SOL_MINT
    input_decimals = 6 if funding_token == "USDC" else 9
    per_leg_swap = per_leg_deploy_funding
    if funding_token == "SOL":
        on_chain = _on_chain_sol_balance(user_wallet)
        if on_chain is not None:
            max_total = max(0.0, round(on_chain - sol_reserve, 9))
            max_per = max_total / max(1, len(assets))
            if per_leg_swap > max_per:
                per_leg_swap = max_per
        if per_leg_swap <= 0:
            refund = record_hf_credit(
                user_wallet,
                funding_token,
                funding_needed,
                reference_id=f"{strategy_id}-retry-refund",
                reference_type="hf_deploy_partial_refund",
            )
            return {
                "ok": False,
                "error": (
                    f"Not enough SOL left after reserving {sol_reserve:.4f} SOL for rent/fees. "
                    "Deposit more SOL and retry."
                ),
                "refunded": True,
                "refund": refund,
                "sol_reserve": sol_reserve,
            }

    trades = []
    errors = []
    for asset in assets:
        out_mint = asset["mint"]
        sym = asset.get("display_symbol") or asset.get("symbol")
        swap = execute_hf_jupiter_swap(
            input_mint=input_mint,
            output_mint=out_mint,
            amount=per_leg_swap,
            input_decimals=input_decimals,
            slippage_bps=150,
            user_wallet=user_wallet,
            sol_reserve=_sol_operating_reserve(1),
        )
        out_raw = int(swap.get("output_amount_raw") or 0)
        if swap.get("status") != "success" or out_raw <= 0:
            err_msg = swap.get("error") or str(swap)
            errors.append({"symbol": sym, "error": err_msg, "mint": out_mint})
            _insert_live_trade(
                strategy_id=strategy_id,
                user_wallet=user_wallet,
                symbol=sym,
                mint=out_mint,
                side="ERROR",
                units=0,
                price_usd=None,
                notional_usd=0,
                fee_usd=0,
                input_mint=input_mint,
                output_mint=out_mint,
                signature=swap.get("signature"),
                explorer_url=swap.get("explorer_url"),
                reason=f"Retry buy failed: {err_msg}"[:500],
            )
            continue
        out_decimals = int(asset.get("decimals") or 6)
        units = out_raw / (10 ** out_decimals)
        notional = per_leg_swap if funding_token == "USDC" else per_leg_swap * (sol_usd_price() or 0)
        price = (notional / units) if units else None
        explorer = swap.get("explorer_url")
        sig = swap.get("signature")
        if sig and not explorer:
            explorer = f"https://explorer.solana.com/tx/{sig}"
        trade = _insert_live_trade(
            strategy_id=strategy_id,
            user_wallet=user_wallet,
            symbol=sym,
            mint=out_mint,
            side="BUY",
            units=units,
            price_usd=price,
            notional_usd=round(notional, 6),
            fee_usd=per_leg_fee_usd,
            input_mint=input_mint,
            output_mint=out_mint,
            signature=sig,
            explorer_url=explorer,
            reason="Live strategy retry entry (Jupiter)",
        )
        trades.append(trade)
        if units > 0:
            _upsert_live_position(
                strategy_id=strategy_id,
                user_wallet=user_wallet,
                symbol=sym,
                mint=out_mint,
                units_delta=units,
                cost_delta_usd=round(notional, 6),
            )
            _insert_live_trade(
                strategy_id=strategy_id,
                user_wallet=user_wallet,
                symbol="FEE",
                mint=USDC_MINT,
                side="FEE",
                units=0,
                price_usd=1.0,
                notional_usd=per_leg_fee_usd,
                fee_usd=per_leg_fee_usd,
                reason=f"1% management fee on retried leg {sym}",
            )

    refund = None
    if errors:
        refund_amount = round(per_leg_funding * len(errors), 9)
        if refund_amount > 0:
            refund = record_hf_credit(
                user_wallet,
                funding_token,
                refund_amount,
                reference_id=f"{strategy_id}-retry-refund",
                reference_type="hf_deploy_partial_refund",
            )

    # Refresh deploy_errors: drop entries for legs that just filled, replace
    # remaining/new failures with this retry's errors, refresh mint map/symbols.
    filled_now = {t["symbol"].upper() for t in trades if t.get("symbol")}
    prior_errors = [
        e for e in (rules.get("deploy_errors") or [])
        if str(e.get("symbol") or "").upper() not in filled_now
        and str(e.get("symbol") or "").upper() not in {m.upper() for m in missing}
    ]
    rules["deploy_errors"] = prior_errors + errors
    rules["last_error"] = (
        f"{len(rules['deploy_errors'])} buy(s) failed and were skipped."
        if rules["deploy_errors"]
        else None
    )
    rules["mint_map"] = {**(rules.get("mint_map") or {}), **(mint_info.get("mint_map") or {})}
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE hf_strategies SET symbols = %s, rules = %s, updated_at = NOW() WHERE id = %s",
                (Json(new_symbols), Json(rules), strategy_id),
            )

    return {
        "ok": True,
        "trades": trades,
        "positions": list_live_positions(strategy_id),
        "errors": errors,
        "refunded_partial": bool(refund and not refund.get("error")),
        "refund": refund,
        "symbols": new_symbols,
        "message": (
            f"Retried {len(missing)} leg(s): {len(trades)} filled"
            + (f", {len(errors)} still failed (unspent capital refunded)" if errors else "")
            + "."
        ),
    }


def liquidate_live_strategy(
    strategy: dict[str, Any],
    reason: str = "Liquidate to SOL",
) -> dict[str, Any]:
    """Swap positions to SOL; charge performance fee only after every leg exits."""
    strategy_id = strategy["id"]
    user_wallet = strategy["user_wallet"]
    rules = dict(strategy.get("rules") or {})
    capital = float(rules.get("capital_usd") or 0)
    deploy_usd = float(rules.get("deploy_usd") or (capital * (1.0 - HF_MGMT_FEE_RATE)))

    positions = open_live_holdings(strategy_id)
    trades = []
    proceeds_sol = 0.0
    proceeds_usd = 0.0
    errors = []
    sol_px = sol_usd_price() or 0.0
    if not positions:
        existing = _liquidation_txs(list_live_trades(strategy_id, limit=200))
        return {
            "ok": True,
            "liquidated": True,
            "already_flat": True,
            "proceeds_sol": 0.0,
            "proceeds_usdc": 0.0,
            "perf_fee_usd": 0.0,
            "net_credited_sol": 0.0,
            "net_credited_usdc": 0.0,
            "trades": [],
            "errors": [],
            "liquidation_txs": existing,
            "to_asset": "SOL",
            "to_mint": SOL_MINT,
            "message": "No remaining live positions to swap to SOL.",
        }

    for pos in positions:
        units = float(pos.get("units") or 0)
        mint = pos.get("mint")
        if units <= 0 or not mint:
            continue
        # Already SOL holdings: credit without a swap.
        if mint in (SOL_MINT, "So11111111111111111111111111111111111111112"):
            sol_out = units
            proceeds_sol += sol_out
            usd_out = sol_out * sol_px if sol_px else 0.0
            proceeds_usd += usd_out
            trade = _insert_live_trade(
                strategy_id=strategy_id,
                user_wallet=user_wallet,
                symbol=pos.get("symbol") or "SOL",
                mint=mint,
                side="SELL",
                units=units,
                price_usd=sol_px or None,
                notional_usd=round(usd_out, 6),
                input_mint=mint,
                output_mint=SOL_MINT,
                signature=None,
                explorer_url=None,
                reason=reason,
            )
            trades.append(trade)
            _upsert_live_position(
                strategy_id=strategy_id,
                user_wallet=user_wallet,
                symbol=pos.get("symbol") or "SOL",
                mint=mint,
                units_delta=-units,
                cost_delta_usd=0,
            )
            continue

        # Resolve decimals via Jupiter/catalog
        asset = resolve_hf_solana_asset(pos.get("symbol") or mint, mint_override=mint)
        decimals = int(asset.get("decimals") or 6)
        swap = execute_hf_jupiter_swap(
            input_mint=mint,
            output_mint=SOL_MINT,
            amount=units,
            input_decimals=decimals,
            slippage_bps=150,
            user_wallet=user_wallet,
        )
        out_raw = int(swap.get("output_amount_raw") or 0)
        if swap.get("status") != "success" or out_raw <= 0:
            errors.append({
                "symbol": pos.get("symbol"),
                "error": swap.get("error") or swap,
                "signature": swap.get("signature"),
            })
            continue
        sol_out = out_raw / 1e9
        proceeds_sol += sol_out
        usd_out = sol_out * sol_px if sol_px else 0.0
        proceeds_usd += usd_out
        trade = _insert_live_trade(
            strategy_id=strategy_id,
            user_wallet=user_wallet,
            symbol=pos.get("symbol") or "?",
            mint=mint,
            side="SELL",
            units=units,
            price_usd=(usd_out / units) if units else None,
            notional_usd=round(usd_out, 6),
            input_mint=mint,
            output_mint=SOL_MINT,
            signature=swap.get("signature"),
            explorer_url=swap.get("explorer_url"),
            reason=reason,
        )
        trades.append(trade)
        _upsert_live_position(
            strategy_id=strategy_id,
            user_wallet=user_wallet,
            symbol=pos.get("symbol") or "?",
            mint=mint,
            units_delta=-units,
            cost_delta_usd=0,
        )

    # Credit successful proceeds immediately. Failed legs remain open and are
    # retried by the expiry scheduler (or the user).
    first_signature = trades[0].get("signature") if trades else None
    credit_reference = (
        f"{strategy_id}-liquidate-{str(first_signature)[:20]}"
        if first_signature
        else f"{strategy_id}-liquidate"
    )
    credit = record_hf_credit(
        user_wallet,
        "SOL",
        proceeds_sol,
        reference_id=credit_reference,
        reference_type="hf_liquidate_return",
        signature=first_signature,
    )

    remaining = open_live_holdings(strategy_id)
    fully_liquidated = not remaining and not errors
    liquidation_txs = _liquidation_txs(trades)
    if not fully_liquidated:
        return {
            "ok": False,
            "liquidated": False,
            "partial": bool(trades),
            "proceeds_sol": round(proceeds_sol, 9),
            "proceeds_usdc": round(proceeds_usd, 8),
            "perf_fee_usd": 0.0,
            "net_credited_sol": round(proceeds_sol, 9),
            "net_credited_usdc": round(proceeds_usd, 8),
            "trades": trades,
            "errors": errors,
            "remaining_positions": remaining,
            "liquidation_txs": liquidation_txs,
            "credit": credit,
            "to_asset": "SOL",
            "to_mint": SOL_MINT,
            "message": (
                f"Partial liquidation: {proceeds_sol:,.6f} SOL credited; "
                f"{len(remaining)} position(s) remain. No performance fee charged yet."
            ),
        }

    # Final exit: calculate profit across every SELL, including earlier partial
    # attempts, then charge only the remaining performance fee.
    all_trades = list_live_trades(strategy_id, limit=500)
    total_proceeds = sum(
        float(t.get("notional_usd") or 0)
        for t in all_trades
        if str(t.get("side") or "").upper() == "SELL"
    )
    prior_perf_fees = sum(
        float(t.get("fee_usd") or 0)
        for t in all_trades
        if str(t.get("side") or "").upper() == "FEE"
        and "performance fee" in str(t.get("reason") or "").lower()
    )
    profit = round(total_proceeds - deploy_usd, 8)
    target_perf_fee = round(max(0.0, profit) * HF_PERF_FEE_RATE, 8)
    perf_fee = round(max(0.0, target_perf_fee - prior_perf_fees), 8)
    perf_fee_sol = 0.0
    if perf_fee > 0:
        if not sol_px:
            return {
                "ok": False,
                "liquidated": False,
                "partial": True,
                "proceeds_sol": round(proceeds_sol, 9),
                "proceeds_usdc": round(proceeds_usd, 8),
                "error": "Could not price SOL to charge the performance fee.",
                "trades": trades,
                "credit": credit,
                "to_asset": "SOL",
                "to_mint": SOL_MINT,
            }
        perf_fee_sol = round(perf_fee / sol_px, 9)
        # Cap fee to available proceeds from this liquidation wave.
        perf_fee_sol = min(perf_fee_sol, proceeds_sol)
        if perf_fee_sol > 0:
            record_hf_spend(
                user_wallet,
                "SOL",
                perf_fee_sol,
                reference_id=f"{strategy_id}-perf-fee",
                reference_type="hf_perf_fee",
            )
            _insert_live_trade(
                strategy_id=strategy_id,
                user_wallet=user_wallet,
                symbol="FEE",
                mint=SOL_MINT,
                side="FEE",
                units=0,
                price_usd=sol_px,
                notional_usd=perf_fee,
                fee_usd=perf_fee,
                reason=f"10% performance fee on profit ${profit}",
            )

    net_to_user = round(proceeds_sol - perf_fee_sol, 9)
    return {
        "ok": True,
        "liquidated": True,
        "proceeds_sol": round(proceeds_sol, 9),
        "proceeds_usdc": round(proceeds_usd, 8),
        "total_proceeds_usdc": round(total_proceeds, 8),
        "deploy_usd": deploy_usd,
        "profit_usd": profit,
        "perf_fee_usd": perf_fee,
        "perf_fee_sol": perf_fee_sol,
        "net_credited_sol": net_to_user,
        "net_credited_usdc": round(net_to_user * sol_px, 8) if sol_px else None,
        "trades": trades,
        "errors": errors,
        "credit": credit,
        "liquidation_txs": _liquidation_txs(
            [t for t in list_live_trades(strategy_id, limit=200) if str(t.get("side") or "").upper() in ("SELL", "FEE")]
        ),
        "to_asset": "SOL",
        "to_mint": SOL_MINT,
        "message": (
            f"Liquidated to SOL: total proceeds ${total_proceeds:,.6f}, "
            f"profit ${profit:,.6f}, perf fee ${perf_fee:,.6f} ({perf_fee_sol:.6f} SOL), "
            f"this credit {net_to_user:.6f} SOL."
        ),
    }


def live_strategy_mark(strategy_id: str, user_wallet: str) -> dict[str, Any]:
    positions = list_live_positions(strategy_id)
    marked = []
    mv = 0.0
    cost = 0.0
    for p in positions:
        px = _token_price_usd(p.get("mint") or p.get("symbol") or "") or float(p.get("avg_entry_usd") or 0)
        units = float(p.get("units") or 0)
        c = float(p.get("cost_basis_usd") or 0)
        value = units * px
        mv += value
        cost += c
        marked.append(
            {
                **p,
                "mark_price_usd": px,
                "market_value_usd": round(value, 4),
                "unrealized_pnl_usd": round(value - c, 4),
            }
        )
    trades = list_live_trades(strategy_id, limit=50)
    return {
        "mode": "live",
        "strategy_id": strategy_id,
        "positions": marked,
        "sleeve_market_value_usd": round(mv, 8),
        "cost_basis_usd": round(cost, 8),
        "unrealized_pnl_usd": round(mv - cost, 8),
        "unrealized_pnl_pct": round(((mv - cost) / cost) * 100, 8) if cost else 0.0,
        "trades": trades,
        "trade_counts": {
            "buys": sum(1 for t in trades if t.get("side") == "BUY"),
            "sells": sum(1 for t in trades if t.get("side") == "SELL"),
            "fees": sum(1 for t in trades if t.get("side") == "FEE"),
        },
    }
