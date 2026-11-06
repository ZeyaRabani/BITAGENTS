"""Hedge Fund paper-trading engine: portfolios, strategies, shared market monitor, 4h scheduler."""

from __future__ import annotations

import os
import secrets
import threading
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from psycopg2.extras import Json

from db import get_conn, init_db
from hedge_fund_core import run_mock_backtest
from yahoo_market_data import (
    fetch_yahoo_daily_prices,
    fetch_yahoo_news,
    resolve_yahoo_asset,
)

HF_MONITOR_INTERVAL_SECONDS = int(os.environ.get("HF_MONITOR_INTERVAL_SECONDS", str(4 * 3600)))
HF_SCHEDULER_POLL_SECONDS = int(os.environ.get("HF_SCHEDULER_POLL_SECONDS", "900"))
# Paper book defaults — strategy sleeves capped at $100 USDC (paper) for now
HF_MAX_STRATEGY_USDC = float(os.environ.get("HF_MAX_STRATEGY_USDC", "100"))
HF_MIN_STRATEGY_USDC = float(os.environ.get("HF_MIN_STRATEGY_USDC", "1"))
# Minimum capital per individual asset in the book (before the 1% start fee
# is deducted) — keeps each leg's swap size meaningful instead of Jupiter
# routing a few cents through a token with thin liquidity.
HF_MIN_PER_ASSET_USDC = float(os.environ.get("HF_MIN_PER_ASSET_USDC", "5"))
DEFAULT_PAPER_CAPITAL = float(os.environ.get("HF_DEFAULT_PAPER_CAPITAL", str(HF_MAX_STRATEGY_USDC)))
# Live sleeves need a few days before the book typically turns a profit.
HF_MIN_HORIZON_DAYS = max(1, int(os.environ.get("HF_MIN_HORIZON_DAYS", "3")))


def clamp_strategy_capital(amount: Optional[float]) -> float:
    """Paper sleeve capital: between min and max (default max $100 USDC)."""
    if amount is None:
        return float(HF_MAX_STRATEGY_USDC)
    try:
        val = float(amount)
    except (TypeError, ValueError):
        return float(HF_MAX_STRATEGY_USDC)
    return max(HF_MIN_STRATEGY_USDC, min(HF_MAX_STRATEGY_USDC, val))


def min_capital_for_book(num_assets: int) -> float:
    return round(HF_MIN_PER_ASSET_USDC * max(1, num_assets), 2)


def clamp_horizon_days(days: Optional[int]) -> Optional[int]:
    """Keep open-ended (None/0); raise any shorter finite horizon to the 3-day minimum."""
    if days is None:
        return None
    try:
        d = int(days)
    except (TypeError, ValueError):
        return None
    if d <= 0:
        return None
    return max(HF_MIN_HORIZON_DAYS, d)


def _horizon_label_for(days: Optional[int]) -> str:
    if not days:
        return "open"
    from covenant_picker import horizon_preset

    return horizon_preset(int(days))["key"]

_scheduler_thread: Optional[threading.Thread] = None
_scheduler_stop = threading.Event()
_last_market_refresh_at: Optional[datetime] = None


def _new_id(prefix: str = "") -> str:
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
        elif isinstance(v, date):
            out[k] = v.isoformat()
    return out


# ─── Market snapshots (shared across users) ───────────────────────────────────

def upsert_market_snapshot(symbol: str, force: bool = False) -> dict[str, Any]:
    """Fetch Yahoo quote into shared cache. Skip if fresh (<4h) unless force."""
    init_db()
    resolved = resolve_yahoo_asset(symbol)
    if resolved.get("error"):
        return resolved
    sym = resolved["symbol"]
    yahoo = resolved["yahoo_symbol"]

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM hf_market_snapshots WHERE symbol = %s", (sym,))
            existing = cur.fetchone()
            if existing and not force:
                fetched = existing["fetched_at"]
                if fetched.tzinfo is None:
                    fetched = fetched.replace(tzinfo=timezone.utc)
                age = (_now() - fetched).total_seconds()
                if age < HF_MONITOR_INTERVAL_SECONDS:
                    return {**_row(existing), "cached": True}

    end = _now().date()
    start = end - timedelta(days=5)
    hist = fetch_yahoo_daily_prices(yahoo, start.isoformat(), end.isoformat())
    if hist.get("error"):
        return {"symbol": sym, "error": hist["error"]}
    prices = hist.get("prices") or []
    if not prices:
        return {"symbol": sym, "error": "No Yahoo prices"}
    last = prices[-1][1]
    prev = prices[-2][1] if len(prices) > 1 else last
    change = ((last - prev) / prev * 100) if prev else 0.0

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO hf_market_snapshots (symbol, yahoo_symbol, asset_class, price_usd, change_24h_pct, raw, fetched_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (symbol) DO UPDATE SET
                    yahoo_symbol = EXCLUDED.yahoo_symbol,
                    asset_class = EXCLUDED.asset_class,
                    price_usd = EXCLUDED.price_usd,
                    change_24h_pct = EXCLUDED.change_24h_pct,
                    raw = EXCLUDED.raw,
                    fetched_at = NOW()
                RETURNING *
                """,
                (
                    sym,
                    yahoo,
                    resolved.get("asset_class") or "equity",
                    float(last),
                    float(change),
                    Json({"bars": len(prices)}),
                ),
            )
            row = cur.fetchone()
    return {**_row(row), "cached": False}


def refresh_symbols(symbols: list[str], force: bool = False) -> dict[str, Any]:
    unique = []
    for s in symbols:
        u = (s or "").strip().upper()
        if u and u not in unique:
            unique.append(u)
    rows = []
    errors = []
    for sym in unique:
        r = upsert_market_snapshot(sym, force=force)
        if r.get("error"):
            errors.append(f"{sym}: {r['error']}")
        else:
            rows.append(r)
    return {"snapshots": rows, "errors": errors, "count": len(rows)}


def get_market_snapshots(symbols: Optional[list[str]] = None) -> list[dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            if symbols:
                cur.execute(
                    "SELECT * FROM hf_market_snapshots WHERE symbol = ANY(%s) ORDER BY symbol",
                    (list(symbols),),
                )
            else:
                cur.execute("SELECT * FROM hf_market_snapshots ORDER BY fetched_at DESC LIMIT 100")
            return [_row(r) for r in cur.fetchall()]


def list_watched_symbols() -> list[str]:
    """Union of symbols across all active strategies (shared monitor set)."""
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT jsonb_array_elements_text(symbols) AS symbol
                FROM hf_strategies
                WHERE status = 'active'
                """
            )
            return [r["symbol"] for r in cur.fetchall() if r.get("symbol")]


# ─── Portfolios ───────────────────────────────────────────────────────────────

def get_or_create_portfolio(user_wallet: str, capital_usd: float = DEFAULT_PAPER_CAPITAL) -> dict[str, Any]:
    init_db()
    wallet = user_wallet.strip()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM hf_paper_portfolios
                WHERE user_wallet = %s AND status = 'active'
                ORDER BY created_at ASC LIMIT 1
                """,
                (wallet,),
            )
            row = cur.fetchone()
            if row:
                return _row(row)
            pid = _new_id("hp")
            capital = max(HF_MIN_STRATEGY_USDC, float(capital_usd))
            cur.execute(
                """
                INSERT INTO hf_paper_portfolios (id, user_wallet, name, cash_usd, starting_capital)
                VALUES (%s, %s, %s, %s, %s) RETURNING *
                """,
                (pid, wallet, "Paper Book", capital, capital),
            )
            return _row(cur.fetchone())


def get_portfolio(portfolio_id: str, user_wallet: Optional[str] = None) -> Optional[dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            if user_wallet:
                cur.execute(
                    "SELECT * FROM hf_paper_portfolios WHERE id = %s AND user_wallet = %s",
                    (portfolio_id, user_wallet),
                )
            else:
                cur.execute("SELECT * FROM hf_paper_portfolios WHERE id = %s", (portfolio_id,))
            row = cur.fetchone()
            return _row(row) if row else None


def list_positions(portfolio_id: str) -> list[dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM hf_paper_positions WHERE portfolio_id = %s ORDER BY symbol",
                (portfolio_id,),
            )
            return [_row(r) for r in cur.fetchall()]


def portfolio_summary(user_wallet: str) -> dict[str, Any]:
    portfolio = get_or_create_portfolio(user_wallet)
    positions = list_positions(portfolio["id"])
    # Mark to market
    symbols = [p["symbol"] for p in positions]
    snaps = {s["symbol"]: s for s in get_market_snapshots(symbols)} if symbols else {}
    equity = float(portfolio["cash_usd"])
    marked = []
    for p in positions:
        mark = float((snaps.get(p["symbol"]) or {}).get("price_usd") or p.get("mark_price_usd") or p.get("avg_entry_usd") or 0)
        value = float(p["units"]) * mark
        cost = float(p["units"]) * float(p["avg_entry_usd"] or 0)
        equity += value
        marked.append(
            {
                **p,
                "mark_price_usd": mark,
                "market_value_usd": round(value, 2),
                "unrealized_pnl_usd": round(value - cost, 2),
            }
        )
    starting = float(portfolio["starting_capital"])
    return {
        "portfolio": portfolio,
        "positions": marked,
        "equity_usd": round(equity, 2),
        "cash_usd": round(float(portfolio["cash_usd"]), 2),
        "pnl_usd": round(equity - starting, 2),
        "pnl_pct": round(((equity - starting) / starting) * 100, 2) if starting else 0,
        "mode": "paper",
    }


# ─── Strategies ───────────────────────────────────────────────────────────────

def _default_rules(user_rules: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    rules = {
        "objective": "max_profit",
        "take_profit_pct": 15.0,
        "stop_loss_pct": 8.0,
        "max_position_pct": 25.0,
        "rebalance": "signal",
        "notes": "",
    }
    if user_rules:
        rules.update({k: v for k, v in user_rules.items() if v is not None})
    return rules


def create_strategy(
    user_wallet: str,
    symbols: Optional[list[str]] = None,
    name: str = "",
    mode: str = "agent",
    rules: Optional[dict[str, Any]] = None,
    allocation_pct: Optional[dict[str, float]] = None,
    capital_usd: Optional[float] = None,
    created_by: str = "agent",
    horizon_days: Optional[int] = None,
    horizon_text: str = "",
    require_confirm: bool = True,
    deploy: bool = False,
    trading_mode: str = "live",
    funding_token: str = "SOL",
    mint_overrides: Optional[dict[str, str]] = None,
    max_names: Optional[int] = None,
) -> dict[str, Any]:
    """
    Create strategy (live by default). Pending until confirm_strategy().
    Live: requires SOL deposit, Jupiter swaps, 1% start fee / 10% perf on profit.
    Paper: virtual fills only (trading_mode='paper').
    Capital sleeve capped at HF_MAX_STRATEGY_USDC (default $100 USD notional).
    """
    from hedge_fund_assets import SOL_MINT, resolve_hf_book_mints
    from covenant_picker import (
        filter_real_tickers,
        horizon_days_for_picker,
        horizon_preset,
        parse_asset_class_preference,
        parse_asset_count,
        parse_horizon_days,
        select_assets_for_horizon,
    )

    trading_mode = (trading_mode or "live").strip().lower()
    if trading_mode not in ("live", "paper"):
        trading_mode = "live"
    funding_token = "SOL"

    portfolio = get_or_create_portfolio(user_wallet, capital_usd or DEFAULT_PAPER_CAPITAL)
    sleeve_capital = clamp_strategy_capital(capital_usd)
    # If user specifies capital and book is unused, resize paper cash to match
    if capital_usd is not None:
        try:
            cap = sleeve_capital
            init_db()
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, cash_usd, starting_capital FROM hf_paper_portfolios
                        WHERE id = %s
                        """,
                        (portfolio["id"],),
                    )
                    row = cur.fetchone()
                    cur.execute(
                        "SELECT COUNT(*) AS n FROM hf_paper_positions WHERE portfolio_id = %s AND units > 0",
                        (portfolio["id"],),
                    )
                    n_pos = int((cur.fetchone() or {}).get("n") or 0)
                    if row and n_pos == 0 and abs(float(row["cash_usd"]) - float(row["starting_capital"])) < 0.01:
                        cur.execute(
                            """
                            UPDATE hf_paper_portfolios
                            SET cash_usd = %s, starting_capital = %s, updated_at = NOW()
                            WHERE id = %s
                            RETURNING *
                            """,
                            (cap, cap, portfolio["id"]),
                        )
                        portfolio = _row(cur.fetchone()) or portfolio
        except Exception:
            pass

    days = clamp_horizon_days(parse_horizon_days(horizon_text, horizon_days))
    pick_days = horizon_days_for_picker(days)
    preset = horizon_preset(pick_days)
    horizon_label = "open" if not days else preset["key"]
    pick_meta: dict[str, Any] = {}
    notes_blob = f"{horizon_text or ''} {(rules or {}).get('notes') or ''}".strip()
    asset_pref = parse_asset_class_preference(notes_blob)
    allow_crypto = asset_pref != "stocks"
    crypto_only = asset_pref == "crypto"
    requested_count = max_names if max_names else parse_asset_count(notes_blob)

    # Drop mandate words like STOCKS / CRYPTO so agent can auto-select
    syms = filter_real_tickers(symbols)
    agent_picked = False
    if not syms:
        pick_meta = select_assets_for_horizon(
            horizon_days=pick_days,
            max_names=requested_count,
            allow_crypto=allow_crypto,
            crypto_only=crypto_only,
            fast=True,
        )
        syms = list(pick_meta.get("symbols") or [])
        agent_picked = True
        created_by = created_by or "agent"
        mode = mode if mode in ("agent", "user", "hybrid") else "agent"
        if not name:
            label = "stocks" if asset_pref == "stocks" else ("crypto" if asset_pref == "crypto" else "book")
            name = f"Agent {label} {horizon_label}" + (f" {days}d" if days else " open")

    # Validate symbols via Yahoo (skip heavy probe when agent-ranked already)
    valid = []
    errors = []
    for s in syms[:10]:
        r = resolve_yahoo_asset(s, probe=not agent_picked)
        if r.get("error"):
            errors.append(r["error"])
        else:
            # Honor stocks-only / crypto-only after resolve
            cls = r.get("asset_class")
            if asset_pref == "stocks" and cls == "crypto":
                continue
            if asset_pref == "crypto" and cls != "crypto":
                continue
            valid.append(r["symbol"])

    # If user/LLM gave junk tickers, fall back to agent pick instead of failing
    if not valid:
        pick_meta = select_assets_for_horizon(
            horizon_days=pick_days,
            allow_crypto=allow_crypto,
            crypto_only=crypto_only,
            fast=True,
        )
        syms = list(pick_meta.get("symbols") or [])
        agent_picked = True
        created_by = "agent"
        mode = "agent"
        errors = []
        for s in syms[:10]:
            r = resolve_yahoo_asset(s, probe=False)
            if not r.get("error"):
                valid.append(r["symbol"])
        if not name:
            name = f"Agent {horizon_label}" + (f" {days}d" if days else " open")

    if not valid:
        return {
            "error": "No valid symbols — stocks or crypto are required",
            "errors": errors,
            "hint": "Omit tickers to let the agent pick, or use e.g. AAPL, NVDA, BTC",
            "picker": pick_meta,
        }
    min_required = min_capital_for_book(len(valid))
    if sleeve_capital < min_required:
        return {
            "error": (
                f"Capital too low for {len(valid)} asset(s) — need at least "
                f"${min_required:.2f} (${HF_MIN_PER_ASSET_USDC:.0f}/asset minimum) so each leg's "
                f"swap stays meaningful, got ${sleeve_capital:.2f}."
            ),
            "min_required_usd": min_required,
            "per_asset_min_usd": HF_MIN_PER_ASSET_USDC,
            "symbols": valid,
            "hint": f"Raise capital to ${min_required:.2f}+ or ask for fewer assets.",
        }
    rules_final_pref = dict(rules or {})
    rules_final_pref["asset_class_preference"] = asset_pref
    rules_final_pref["agent_picked"] = agent_picked
    rules = rules_final_pref

    # Jupiter / catalog mint resolution (stocks from hedge-fund-tokens.json)
    mint_info = resolve_hf_book_mints(valid, mint_overrides=mint_overrides)
    if mint_info.get("errors"):
        # Soft-fail: still propose but flag missing mints
        errors.extend([e.get("error") for e in mint_info["errors"] if e.get("error")])

    if not allocation_pct:
        w = round(100.0 / len(valid), 4)
        allocation_pct = {s: w for s in valid}
    rules_final = _default_rules(rules)
    rules_final["horizon_days"] = days
    rules_final["horizon_label"] = horizon_label
    rules_final["open_ended"] = days is None
    rules_final["capital_usd"] = sleeve_capital
    rules_final["max_capital_usd"] = HF_MAX_STRATEGY_USDC
    rules_final["mint_map"] = mint_info.get("mint_map") or {}
    rules_final["solana_assets"] = mint_info.get("assets") or []
    rules_final["liquidation_asset"] = "SOL"
    rules_final["liquidation_mint"] = SOL_MINT
    rules_final["objective"] = rules_final.get("objective") or "max_profit"
    rules_final["trading_mode"] = trading_mode
    rules_final["funding_token"] = funding_token
    rules_final["paper_mode"] = trading_mode == "paper"
    rules_final["deposits_required"] = trading_mode == "live"
    rules_final["mgmt_fee_pct"] = 1.0
    rules_final["perf_fee_pct"] = 10.0

    status = "active" if (deploy and not require_confirm) else "pending"
    sid = _new_id("hs")
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO hf_strategies (
                    id, portfolio_id, user_wallet, name, mode, status, symbols, allocation_pct,
                    rules, created_by, horizon_days, horizon_label, trading_mode
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
                """,
                (
                    sid,
                    portfolio["id"],
                    user_wallet.strip(),
                    name or f"{'Agent' if created_by == 'agent' else 'User'} Strategy {sid}",
                    mode if mode in ("agent", "user", "hybrid") else "agent",
                    status,
                    Json(valid),
                    Json(allocation_pct),
                    Json(rules_final),
                    created_by if created_by in ("agent", "user") else "agent",
                    days,
                    horizon_label,
                    trading_mode,
                ),
            )
            strategy = _row(cur.fetchone())

    deploy_result = None
    if status == "active":
        if trading_mode == "live":
            from hedge_fund_live import deploy_live_allocations

            deploy_result = deploy_live_allocations(
                strategy,
                capital_usd=sleeve_capital,
                funding_token=funding_token,
                mint_overrides=mint_overrides,
            )
        else:
            refresh_symbols(valid, force=False)
            deploy_result = _deploy_initial_allocations(
                portfolio["id"], sid, user_wallet, valid, allocation_pct, capital_usd=sleeve_capital
            )

    horizon_note = (
        f"Open-ended — liquidate anytime with **liquidate {sid}**."
        if not days
        else f"Horizon {days}d — auto-liquidates to SOL when ended (or liquidate early)."
        + (
            f" (raised to the {HF_MIN_HORIZON_DAYS}d minimum)"
            if (
                horizon_days is not None
                and int(horizon_days or 0) > 0
                and int(horizon_days) < HF_MIN_HORIZON_DAYS
            )
            else ""
        )
    )
    mode_note = (
        f"LIVE · deposit SOL first · 1% fee at start · 10% of profit on liquidate · max ${HF_MAX_STRATEGY_USDC:,.0f}"
        if trading_mode == "live"
        else f"PAPER · virtual fills · max ${HF_MAX_STRATEGY_USDC:,.0f}"
    )
    return {
        **strategy,
        "strategy": strategy,
        "deploy": deploy_result,
        "errors": errors,
        "mode": strategy.get("mode") or mode,
        "trading_mode": trading_mode,
        "paper": trading_mode == "paper",
        "deposits_required": trading_mode == "live",
        "picker": pick_meta,
        "horizon_days": days,
        "horizon_label": horizon_label,
        "open_ended": days is None,
        "capital_usd": sleeve_capital,
        "max_capital_usd": HF_MAX_STRATEGY_USDC,
        "funding_token": funding_token,
        "solana_assets": mint_info.get("assets") or [],
        "mint_map": mint_info.get("mint_map") or {},
        "sol_mint": SOL_MINT,
        "status": status,
        "awaiting_confirmation": status == "pending",
        "confirm_hint": (
            f"Review mints below. Reply **confirm {sid}** (optional: `with $50`, mint overrides) to deploy. "
            f"{mode_note}. {horizon_note}"
            if status == "pending"
            else None
        ),
    }


def _strategy_trade_count(strategy_id: str, user_wallet: str) -> int:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS n FROM hf_paper_trades
                WHERE strategy_id = %s AND user_wallet = %s
                """,
                (strategy_id, user_wallet.strip()),
            )
            return int((cur.fetchone() or {}).get("n") or 0)


def _ensure_paper_cash(portfolio_id: str, need_usd: float) -> dict[str, Any]:
    """Paper book: credit cash so a strategy sleeve can deploy (does not steal other sleeves)."""
    need = max(0.0, float(need_usd))
    if need <= 0:
        return {"credited_usd": 0.0}
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT cash_usd, starting_capital FROM hf_paper_portfolios WHERE id = %s FOR UPDATE",
                (portfolio_id,),
            )
            row = cur.fetchone()
            if not row:
                return {"error": "Portfolio not found", "credited_usd": 0.0}
            cash = float(row["cash_usd"] or 0)
            starting = float(row["starting_capital"] or 0)
            if cash + 1e-6 >= need:
                return {"credited_usd": 0.0, "cash_usd": cash}
            credit = need - cash
            cur.execute(
                """
                UPDATE hf_paper_portfolios
                SET cash_usd = %s, starting_capital = %s, updated_at = NOW()
                WHERE id = %s
                RETURNING cash_usd, starting_capital
                """,
                (cash + credit, starting + credit, portfolio_id),
            )
            updated = cur.fetchone()
            return {
                "credited_usd": round(credit, 2),
                "cash_usd": float(updated["cash_usd"]),
                "starting_capital": float(updated["starting_capital"]),
            }


def _finish_live_deploy(strategy_id: str, rules: dict[str, Any], deploy: dict[str, Any]) -> None:
    """
    Persist the outcome of a (possibly backgrounded) live deploy: mark the
    strategy failed on total failure, or record fills/errors on success.
    Runs after deploy_live_allocations returns — called from a background
    thread so confirm_strategy can respond to the user immediately instead
    of blocking on however long the Jupiter swaps take.
    """
    rules = dict(rules)
    if deploy.get("error") or not deploy.get("ok"):
        rules["last_error"] = str(deploy.get("error") or "Live deploy failed — could not buy tokens/stocks")
        rules["deploy_errors"] = deploy.get("errors") or []
        rules["deploy_failed_at"] = _now().isoformat()
        init_db()
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE hf_strategies
                    SET status = 'failed', rules = %s, updated_at = NOW()
                    WHERE id = %s
                    """,
                    (Json(rules), strategy_id),
                )
        return

    rules["deploy_usd"] = deploy.get("deploy_usd")
    rules["mgmt_fee_usd"] = deploy.get("mgmt_fee_usd")
    rules["mint_map"] = deploy.get("mint_map") or rules.get("mint_map")
    rules["solana_assets"] = deploy.get("solana_assets") or rules.get("solana_assets")
    if deploy.get("errors"):
        rules["deploy_errors"] = deploy.get("errors")
        rules["partial_deploy_refunded"] = bool(deploy.get("refunded_partial"))
        rules["last_error"] = (
            f"{len(deploy['errors'])} buy(s) failed and were skipped"
            + (" — unspent capital refunded." if deploy.get("refunded_partial") else ".")
        )
    else:
        rules["deploy_errors"] = []
        rules["last_error"] = None
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE hf_strategies SET rules = %s, updated_at = NOW() WHERE id = %s",
                (Json(rules), strategy_id),
            )


def confirm_strategy(
    strategy_id: str,
    user_wallet: str,
    capital_usd: Optional[float] = None,
    horizon_days: Optional[int] = None,
    mint_overrides: Optional[dict[str, str]] = None,
    funding_token: Optional[str] = None,
) -> dict[str, Any]:
    """Activate pending strategy and deploy (live Jupiter or paper fills)."""
    strategy = get_strategy(strategy_id, user_wallet)
    if not strategy:
        return {"error": "Strategy not found"}

    status = strategy.get("status")
    rules = dict(strategy.get("rules") or {})
    trading_mode = (strategy.get("trading_mode") or rules.get("trading_mode") or "live").lower()

    if trading_mode == "live":
        from hedge_fund_live import list_live_positions, list_live_trades

        n_live = len(list_live_trades(strategy_id, limit=5))
        open_live = sum(float(p.get("units") or 0) for p in list_live_positions(strategy_id))
        if status == "active" and (open_live > 0 or n_live > 0):
            return {"strategy": strategy, "note": "Already active (live)", "confirmed": True}
    else:
        n_trades = _strategy_trade_count(strategy_id, user_wallet)
        if status == "active":
            positions = list_positions_for_strategy(strategy_id)
            open_units = sum(float(p.get("units") or 0) for p in positions)
            if open_units > 0 or n_trades > 0:
                return {"strategy": strategy, "note": "Already active", "confirmed": True}
        elif status == "closed" and n_trades > 0:
            return {
                "error": "Strategy already closed with trade history. Create a new strategy to redeploy.",
                "strategy_id": strategy_id,
            }

    if status not in ("pending", "paused", "closed", "active"):
        return {"error": f"Cannot confirm strategy in status={status}"}

    symbols = list(strategy.get("symbols") or [])
    if not symbols:
        return {"error": "Strategy has no symbols — stocks/crypto are required before confirm"}
    allocation_pct = dict(strategy.get("allocation_pct") or {})
    if capital_usd is not None:
        sleeve = clamp_strategy_capital(capital_usd)
    else:
        sleeve = clamp_strategy_capital(rules.get("capital_usd"))
    min_required = min_capital_for_book(len(symbols))
    if sleeve < min_required:
        return {
            "error": (
                f"Capital too low for {len(symbols)} asset(s) — need at least "
                f"${min_required:.2f} (${HF_MIN_PER_ASSET_USDC:.0f}/asset minimum), got ${sleeve:.2f}."
            ),
            "min_required_usd": min_required,
            "per_asset_min_usd": HF_MIN_PER_ASSET_USDC,
        }
    rules["capital_usd"] = sleeve
    rules["max_capital_usd"] = HF_MAX_STRATEGY_USDC
    rules["trading_mode"] = trading_mode
    rules["paper_mode"] = trading_mode == "paper"
    rules["deposits_required"] = trading_mode == "live"
    if funding_token:
        rules["funding_token"] = "SOL"
    funding = "SOL"
    rules["funding_token"] = "SOL"

    # Apply mint corrections
    if mint_overrides:
        from hedge_fund_assets import resolve_hf_book_mints

        mint_info = resolve_hf_book_mints(symbols, mint_overrides=mint_overrides)
        rules["mint_map"] = mint_info.get("mint_map") or rules.get("mint_map") or {}
        rules["solana_assets"] = mint_info.get("assets") or rules.get("solana_assets") or []
        if mint_info.get("errors"):
            return {"error": "Mint resolution failed", "details": mint_info["errors"]}

    if horizon_days is not None:
        days = int(horizon_days) if int(horizon_days) > 0 else None
    else:
        days = strategy.get("horizon_days")
        if days is None and rules.get("horizon_days") is not None:
            days = rules.get("horizon_days")
        if days is not None:
            try:
                days = int(days) if int(days) > 0 else None
            except (TypeError, ValueError):
                days = None
    days = clamp_horizon_days(days)
    rules["horizon_days"] = days
    rules["open_ended"] = days is None
    rules["horizon_label"] = _horizon_label_for(days)

    if not allocation_pct and symbols:
        w = round(100.0 / len(symbols), 4)
        allocation_pct = {s: w for s in symbols}

    if trading_mode == "live":
        # Mark deploy as in-progress so a concurrent dashboard refresh (which
        # triggers reconcile_stuck_live_strategies) doesn't mistake an
        # in-flight Jupiter swap for an abandoned deploy and refund/dismiss
        # the strategy out from under this call.
        rules["deploy_started_at"] = _now().isoformat()

    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE hf_strategies
                SET status = 'active', rules = %s, horizon_days = %s, horizon_label = %s,
                    trading_mode = %s, created_at = NOW(), updated_at = NOW()
                WHERE id = %s AND user_wallet = %s RETURNING *
                """,
                (
                    Json(rules),
                    days,
                    rules["horizon_label"],
                    trading_mode,
                    strategy_id,
                    user_wallet.strip(),
                ),
            )
            strategy = _row(cur.fetchone())

    if trading_mode == "live":
        import threading

        def _run_deploy_and_finish() -> None:
            from hedge_fund_live import deploy_live_allocations

            deploy = deploy_live_allocations(
                strategy,
                capital_usd=sleeve,
                funding_token=funding,
                # Re-resolve mints on deploy. Do not lock stale mint_map (e.g. Ondo
                # NVDAon with no Jupiter routes) from the proposal step.
                mint_overrides=mint_overrides,
            )
            _finish_live_deploy(strategy_id, dict(rules), deploy)

        threading.Thread(target=_run_deploy_and_finish, daemon=True).start()

        symbol_list = ", ".join(symbols)
        return {
            "strategy": strategy,
            "confirmed": True,
            "deploying": True,
            "trading_mode": "live",
            "capital_usd": sleeve,
            "horizon_days": days,
            "open_ended": days is None,
            "symbols": symbols,
            "message": (
                f"Confirmed {strategy_id} — buying {len(symbols)} asset(s) via Jupiter now "
                f"({symbol_list}). Each buy can take up to ~2-3 minutes on-chain. Fills (or "
                "errors) land in the Strategies tab as they complete — ask me "
                f"'status {strategy_id}' anytime to check."
            ),
        }

    refresh_symbols(symbols, force=False)
    deploy = _deploy_initial_allocations(
        strategy["portfolio_id"],
        strategy_id,
        user_wallet,
        symbols,
        allocation_pct,
        capital_usd=sleeve,
    )
    return {
        "strategy": strategy,
        "deploy": deploy,
        "confirmed": True,
        "trading_mode": "paper",
        "capital_usd": sleeve,
        "max_capital_usd": HF_MAX_STRATEGY_USDC,
        "horizon_days": days,
        "open_ended": days is None,
        "symbols": symbols,
        "solana_assets": rules.get("solana_assets") or [],
        "mint_map": rules.get("mint_map") or {},
        "paper": True,
        "message": (
            f"Strategy {strategy_id} confirmed — deployed ${sleeve:,.2f} paper sleeve "
            f"(max ${HF_MAX_STRATEGY_USDC:,.0f}) across {', '.join(symbols)}."
        ),
    }


def strategy_live_pnl(strategy_id: str, user_wallet: str) -> dict[str, Any]:
    """Live mark-to-market PnL for a strategy (live Jupiter book or paper marks)."""
    strategy = get_strategy(strategy_id, user_wallet)
    if not strategy:
        return {"error": "Strategy not found", "strategy_id": strategy_id}

    rules = strategy.get("rules") or {}
    trading_mode = (strategy.get("trading_mode") or rules.get("trading_mode") or "live").lower()
    if trading_mode == "live":
        from hedge_fund_live import live_strategy_mark

        mark = live_strategy_mark(strategy_id, user_wallet)
        created = strategy.get("created_at")
        horizon = int(strategy.get("horizon_days") or rules.get("horizon_days") or 0)
        ends_at = None
        expired = False
        status = strategy.get("status")
        if created and horizon and status == "active":
            try:
                if isinstance(created, str):
                    created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                else:
                    created_dt = created
                if created_dt.tzinfo is None:
                    created_dt = created_dt.replace(tzinfo=timezone.utc)
                ends_at = created_dt + timedelta(days=horizon)
                expired = _now() >= ends_at
            except Exception:
                pass
        return {
            **mark,
            "name": strategy.get("name"),
            "status": status,
            "symbols": list(strategy.get("symbols") or []),
            "mint_map": rules.get("mint_map") or {},
            "solana_assets": rules.get("solana_assets") or [],
            "capital_usd": rules.get("capital_usd"),
            "horizon_days": horizon or None,
            "created_at": created,
            "ends_at": ends_at.isoformat() if ends_at else None,
            "expired": expired,
            "never_deployed": not mark.get("trades"),
            "hint": (
                f"No live fills yet — confirm {strategy_id} after depositing SOL."
                if not mark.get("trades") and status in ("pending", "closed")
                else None
            ),
            "liquidation_asset": "SOL",
            "liquidation_mint": rules.get("liquidation_mint"),
            "trading_mode": "live",
            "note": "LIVE Jupiter marks — real on-chain positions.",
        }

    symbols = list(strategy.get("symbols") or [])
    refresh_symbols(symbols, force=False)
    positions = list_positions_for_strategy(strategy_id)
    snaps = {s["symbol"]: s for s in get_market_snapshots(symbols)} if symbols else {}
    rules = strategy.get("rules") or {}
    mint_map = rules.get("mint_map") or {}
    sleeve_capital = float(rules.get("capital_usd") or 0) or None
    liq_proceeds = rules.get("liquidation_proceeds_usd")

    marked = []
    market_value = 0.0
    cost_basis = 0.0
    for p in positions:
        mark = float(
            (snaps.get(p["symbol"]) or {}).get("price_usd")
            or p.get("mark_price_usd")
            or p.get("avg_entry_usd")
            or 0
        )
        units = float(p.get("units") or 0)
        entry = float(p.get("avg_entry_usd") or 0)
        mv = units * mark
        cost = units * entry
        market_value += mv
        cost_basis += cost
        marked.append(
            {
                **p,
                "mark_price_usd": mark,
                "market_value_usd": round(mv, 2),
                "cost_basis_usd": round(cost, 2),
                "unrealized_pnl_usd": round(mv - cost, 2),
                "unrealized_pnl_pct": round(((mv - cost) / cost) * 100, 2) if cost else 0,
                "mint": mint_map.get(p["symbol"]),
            }
        )

    trades = []
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM hf_paper_trades
                WHERE strategy_id = %s AND user_wallet = %s
                ORDER BY created_at DESC LIMIT 100
                """,
                (strategy_id, user_wallet.strip()),
            )
            trades = [_row(r) for r in cur.fetchall()]

    buy_notional = sum(float(t["notional_usd"]) for t in trades if t.get("side") == "BUY")
    sell_notional = sum(float(t["notional_usd"]) for t in trades if t.get("side") == "SELL")
    unrealized = market_value - cost_basis
    sleeve_equity = market_value
    realized_approx = sell_notional - buy_notional + market_value if trades else 0.0
    if liq_proceeds is not None and buy_notional:
        realized_approx = float(liq_proceeds) - buy_notional

    created = strategy.get("created_at")
    horizon = int(strategy.get("horizon_days") or rules.get("horizon_days") or 0)
    ends_at = None
    expired = False
    status = strategy.get("status")
    if created and horizon and status == "active":
        try:
            if isinstance(created, str):
                created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            else:
                created_dt = created
            if created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=timezone.utc)
            ends_at = created_dt + timedelta(days=horizon)
            expired = _now() >= ends_at
        except Exception:
            pass
    elif created and horizon:
        try:
            if isinstance(created, str):
                created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            else:
                created_dt = created
            if created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=timezone.utc)
            ends_at = created_dt + timedelta(days=horizon)
        except Exception:
            pass

    never_deployed = len(trades) == 0 and market_value <= 0
    hint = None
    if never_deployed and status in ("pending", "closed", "paused"):
        hint = (
            f"No paper fills were placed for this strategy"
            + (f" (intended sleeve ${sleeve_capital:,.2f})" if sleeve_capital else "")
            + f". Reply **confirm {strategy_id}** to deploy now."
        )
    elif never_deployed and status == "active":
        hint = f"Active but empty — reply **confirm {strategy_id}** to force redeploy fills."

    return {
        "mode": "live_paper",
        "strategy_id": strategy_id,
        "name": strategy.get("name"),
        "status": status,
        "symbols": symbols,
        "mint_map": mint_map,
        "solana_assets": rules.get("solana_assets") or [],
        "capital_usd": sleeve_capital,
        "horizon_days": horizon,
        "created_at": created,
        "ends_at": ends_at.isoformat() if ends_at else None,
        "expired": expired,
        "never_deployed": never_deployed,
        "hint": hint,
        "positions": marked,
        "sleeve_market_value_usd": round(sleeve_equity, 2),
        "cost_basis_usd": round(cost_basis, 2),
        "unrealized_pnl_usd": round(unrealized, 2),
        "unrealized_pnl_pct": round((unrealized / cost_basis) * 100, 2) if cost_basis else 0,
        "realized_pnl_usd": round(realized_approx, 2) if trades else 0.0,
        "liquidation_proceeds_usd": liq_proceeds,
        "trade_counts": {
            "buys": sum(1 for t in trades if t.get("side") == "BUY"),
            "sells": sum(1 for t in trades if t.get("side") == "SELL"),
            "buy_notional_usd": round(buy_notional, 2),
            "sell_notional_usd": round(sell_notional, 2),
        },
        "recent_trades": trades[:20],
        "liquidation_asset": rules.get("liquidation_asset") or "SOL",
        "liquidation_mint": rules.get("liquidation_mint"),
        "note": "Live paper mark-to-market — not a mock historical backtest.",
    }


def _merge_liquidation_txs(rules: dict[str, Any], live: dict[str, Any]) -> dict[str, Any]:
    txs = list(rules.get("liquidation_txs") or [])
    seen = {str(t.get("signature")) for t in txs if t.get("signature")}
    incoming = list(live.get("liquidation_txs") or [])
    if not incoming:
        for t in live.get("trades") or []:
            sig = t.get("signature")
            if not sig:
                continue
            incoming.append(
                {
                    "signature": sig,
                    "explorer_url": t.get("explorer_url") or f"https://explorer.solana.com/tx/{sig}",
                    "symbol": t.get("symbol"),
                    "side": t.get("side"),
                }
            )
    for t in incoming:
        sig = t.get("signature")
        if not sig or str(sig) in seen:
            continue
        txs.append(t)
        seen.add(str(sig))
    rules["liquidation_txs"] = txs
    return rules


def _apply_live_usdc_exit(
    strategy: dict[str, Any],
    reason: str,
    *,
    reopen_on_partial: bool,
) -> dict[str, Any]:
    from hedge_fund_assets import SOL_MINT
    from hedge_fund_live import liquidate_live_strategy

    strategy_id = strategy["id"]
    rules0 = dict(strategy.get("rules") or {})
    live = liquidate_live_strategy(strategy, reason=reason)
    rules0 = _merge_liquidation_txs(rules0, live)
    rules0["last_liquidation_attempt_at"] = _now().isoformat()
    rules0["liquidation_errors"] = live.get("errors") or []

    fully = bool(live.get("liquidated"))
    if not fully:
        new_status = "active" if reopen_on_partial else "closed"
        rules0["swapped_to_usdc"] = False
        init_db()
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE hf_strategies
                    SET status = %s, rules = %s, updated_at = NOW()
                    WHERE id = %s RETURNING *
                    """,
                    (new_status, Json(rules0), strategy_id),
                )
                strategy = _row(cur.fetchone())
        return {**live, "strategy": strategy, "trading_mode": "live"}

    rules0["liquidated_at"] = _now().isoformat()
    rules0["liquidation_proceeds_usd"] = live.get("proceeds_usdc")
    rules0["liquidation_total_proceeds_usd"] = live.get("total_proceeds_usdc")
    rules0["liquidation_profit_usd"] = live.get("profit_usd")
    rules0["perf_fee_usd"] = live.get("perf_fee_usd")
    rules0["liquidation_mint"] = SOL_MINT
    rules0["swapped_to_usdc"] = True
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE hf_strategies SET status = 'closed', rules = %s, updated_at = NOW()
                WHERE id = %s RETURNING *
                """,
                (Json(rules0), strategy_id),
            )
            strategy = _row(cur.fetchone())
    return {**live, "strategy": strategy, "trading_mode": "live"}


def _claim_usdc_exit(
    strategy_id: str,
    allowed_statuses: tuple[str, ...],
    user_wallet: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Mark a strategy liquidating so two close/swap runs cannot double-sell."""
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            if user_wallet:
                cur.execute(
                    """
                    UPDATE hf_strategies
                    SET
                        rules = jsonb_set(
                            COALESCE(rules, '{}'::jsonb),
                            '{pre_liquidation_status}',
                            to_jsonb(status)
                        ),
                        status = 'liquidating',
                        updated_at = NOW()
                    WHERE id = %s AND user_wallet = %s AND status = ANY(%s)
                    RETURNING *
                    """,
                    (strategy_id, user_wallet.strip(), list(allowed_statuses)),
                )
            else:
                cur.execute(
                    """
                    UPDATE hf_strategies
                    SET
                        rules = jsonb_set(
                            COALESCE(rules, '{}'::jsonb),
                            '{pre_liquidation_status}',
                            to_jsonb(status)
                        ),
                        status = 'liquidating',
                        updated_at = NOW()
                    WHERE id = %s AND status = ANY(%s)
                    RETURNING *
                    """,
                    (strategy_id, list(allowed_statuses)),
                )
            row = cur.fetchone()
    return _row(row) if row else None


def liquidate_strategy(
    strategy_id: str,
    user_wallet: str,
    reason: str = "Horizon ended — liquidate to SOL",
) -> dict[str, Any]:
    """Sell all strategy positions to SOL (live Jupiter or paper). Marks strategy closed."""
    from hedge_fund_live import open_live_holdings

    strategy = get_strategy(strategy_id, user_wallet)
    if not strategy:
        return {"error": "Strategy not found"}

    rules0 = dict(strategy.get("rules") or {})
    trading_mode = (strategy.get("trading_mode") or rules0.get("trading_mode") or "live").lower()

    if strategy.get("status") == "closed":
        if trading_mode == "live" and open_live_holdings(strategy_id):
            claimed = _claim_usdc_exit(strategy_id, ("closed",), user_wallet)
            if not claimed:
                latest = get_strategy(strategy_id, user_wallet)
                return {
                    "strategy": latest,
                    "note": "SOL exit already in progress",
                    "liquidating": True,
                    "trades": [],
                }
            return _apply_live_usdc_exit(claimed, reason, reopen_on_partial=False)
        return {"strategy": strategy, "note": "Already closed", "trades": []}
    if strategy.get("status") == "liquidating":
        return {
            "strategy": strategy,
            "note": "Liquidation already in progress",
            "liquidating": True,
            "trades": [],
        }
    if strategy.get("status") not in ("active", "paused"):
        return {"error": f"Cannot liquidate strategy in status={strategy.get('status')}"}

    claimed = _claim_usdc_exit(strategy_id, ("active", "paused"), user_wallet)
    if not claimed:
        latest = get_strategy(strategy_id, user_wallet)
        return {
            "strategy": latest,
            "note": "Liquidation already in progress or strategy is no longer active",
            "liquidating": True,
            "trades": [],
        }
    strategy = claimed

    trading_mode = (strategy.get("trading_mode") or (strategy.get("rules") or {}).get("trading_mode") or "live").lower()
    if trading_mode == "live":
        return _apply_live_usdc_exit(strategy, reason, reopen_on_partial=True)

    return _liquidate_paper(strategy_id, user_wallet, reason)


def retry_strategy_deploy(
    strategy_id: str,
    user_wallet: str,
    replace: Optional[dict[str, str]] = None,
    mint_overrides: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """
    Retry the Jupiter buy for any leg of a confirmed live strategy that never
    filled (e.g. "No routes found"). Optionally swap a failed ticker for a
    different one via `replace` (e.g. {"AAPL": "PLTR"}) before retrying.
    """
    strategy = get_strategy(strategy_id, user_wallet)
    if not strategy:
        return {"error": "Strategy not found"}
    trading_mode = (strategy.get("trading_mode") or (strategy.get("rules") or {}).get("trading_mode") or "live").lower()
    if trading_mode != "live":
        return {"error": "Retry only applies to live strategies"}
    if strategy.get("status") not in ("active", "paused"):
        return {"error": f"Cannot retry while status={strategy.get('status')}"}

    import threading

    from hedge_fund_live import retry_live_deploy

    rules = dict(strategy.get("rules") or {})
    rules["deploy_started_at"] = _now().isoformat()
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE hf_strategies SET rules = %s, updated_at = NOW() WHERE id = %s",
                (Json(rules), strategy_id),
            )

    def _run_retry() -> None:
        retry_live_deploy(strategy, replace=replace, mint_overrides=mint_overrides)

    threading.Thread(target=_run_retry, daemon=True).start()

    return {
        "ok": True,
        "retrying": True,
        "strategy": strategy,
        "message": "Retrying the failed leg(s) via Jupiter now — check the Strategies tab or ask 'status' in a moment.",
    }


def _liquidate_paper(strategy_id: str, user_wallet: str, reason: str) -> dict[str, Any]:
    strategy = get_strategy(strategy_id, user_wallet)
    if not strategy:
        return {"error": "Strategy not found"}
    portfolio_id = strategy["portfolio_id"]
    positions = list_positions_for_strategy(strategy_id)
    refresh_symbols([p["symbol"] for p in positions], force=True)
    trades = []
    proceeds = 0.0
    for pos in positions:
        units = float(pos.get("units") or 0)
        if units <= 0:
            continue
        result = execute_paper_trade(
            portfolio_id=portfolio_id,
            strategy_id=strategy_id,
            user_wallet=user_wallet,
            symbol=pos["symbol"],
            side="SELL",
            units=units,
            reason=reason,
            decision="liquidate_usdc",
        )
        trades.append(result)
        if result.get("trade"):
            proceeds += float(result["trade"].get("notional_usd") or 0)
        _record_decision(
            strategy_id,
            portfolio_id,
            user_wallet,
            pos["symbol"],
            "sell",
            reason,
            float((result.get("trade") or {}).get("price_usd") or 0),
            0.95,
            bool(result.get("trade")),
            (result.get("trade") or {}).get("id"),
            [],
            {"liquidation": True, "to": "SOL", "mint": SOL_MINT},
        )

    rules = dict(strategy.get("rules") or {})
    rules["liquidated_at"] = _now().isoformat()
    rules["liquidation_proceeds_usd"] = round(proceeds, 2)
    rules["liquidation_mint"] = SOL_MINT

    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE hf_strategies SET status = 'closed', rules = %s, updated_at = NOW()
                WHERE id = %s RETURNING *
                """,
                (Json(rules), strategy_id),
            )
            strategy = _row(cur.fetchone())

    return {
        "strategy": strategy,
        "liquidated": True,
        "proceeds_usd": round(proceeds, 2),
        "to_asset": "SOL",
        "to_mint": SOL_MINT,
        "trades": trades,
        "message": (
            f"Strategy {strategy_id} liquidated to SOL (paper). "
            f"Proceeds ${proceeds:,.2f} credited as cash."
        ),
    }


def maybe_liquidate_expired(strategy_id: str) -> Optional[dict[str, Any]]:
    strategy = get_strategy(strategy_id)
    if not strategy or strategy.get("status") not in ("active", "paused"):
        return None
    rules = strategy.get("rules") or {}
    horizon = int(strategy.get("horizon_days") or rules.get("horizon_days") or 0)
    created = strategy.get("created_at")
    if not horizon or not created:
        return None
    try:
        created_dt = (
            datetime.fromisoformat(created.replace("Z", "+00:00"))
            if isinstance(created, str)
            else created
        )
        if created_dt.tzinfo is None:
            created_dt = created_dt.replace(tzinfo=timezone.utc)
        expired = _now() >= created_dt + timedelta(days=horizon)
    except Exception:
        expired = False
    if expired:
        return liquidate_strategy(
            strategy_id,
            strategy["user_wallet"],
            reason=f"Horizon {horizon}d ended — auto-liquidate to SOL",
        )
    return None


def complete_unswapped_closed_strategies() -> dict[str, Any]:
    """Swap leftover live holdings on strategies already marked closed."""
    from hedge_fund_live import open_live_holdings

    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM hf_strategies WHERE status = 'closed'")
            rows = [_row(r) for r in cur.fetchall()]
    results = []
    for strategy in rows:
        rules = strategy.get("rules") or {}
        trading_mode = (
            strategy.get("trading_mode") or rules.get("trading_mode") or "live"
        ).lower()
        if trading_mode != "live":
            continue
        if not open_live_holdings(strategy["id"]):
            continue
        claimed = _claim_usdc_exit(strategy["id"], ("closed",))
        if not claimed:
            continue
        result = _apply_live_usdc_exit(
            claimed,
            "Closed strategy still held tokens — swap remaining to SOL",
            reopen_on_partial=False,
        )
        results.append({"strategy_id": strategy["id"], **result})
    return {"checked": len(rows), "swapped": results, "count": len(results)}


def run_horizon_close_cycle() -> dict[str, Any]:
    expired = liquidate_all_expired_strategies()
    leftover = complete_unswapped_closed_strategies()
    return {
        "expired": expired,
        "unswapped": leftover,
        "expired_count": expired.get("count") or 0,
        "unswapped_count": leftover.get("count") or 0,
    }


def update_strategy_rules(
    strategy_id: str,
    user_wallet: str,
    rules: Optional[dict[str, Any]] = None,
    symbols: Optional[list[str]] = None,
    allocation_pct: Optional[dict[str, float]] = None,
    name: Optional[str] = None,
    status: Optional[str] = None,
    horizon_days: Optional[int] = None,
    add_capital_usd: Optional[float] = None,
) -> dict[str, Any]:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM hf_strategies WHERE id = %s AND user_wallet = %s",
                (strategy_id, user_wallet.strip()),
            )
            row = cur.fetchone()
            if not row:
                return {"error": "Strategy not found"}
            if row["status"] == "pending":
                return {
                    "error": (
                        "Strategy is still pending confirmation — mint addresses can be corrected "
                        "via the mint override fields, but other edits unlock only after you confirm "
                        "and assets are bought. Reply confirm/dismiss first."
                    ),
                }
            composition_change = (
                (symbols is not None and list(symbols) != list(row["symbols"] or []))
                or allocation_pct is not None
                or (rules or {}).get("mint_overrides") is not None
            )
            if composition_change and _successful_live_buys(strategy_id):
                return {
                    "error": (
                        "This strategy has already bought assets on-chain — its symbols/allocation "
                        "can no longer be edited. Liquidate it and create a new strategy instead."
                    ),
                }
            merged_rules = dict(row["rules"] or {})
            if rules:
                merged_rules.update(rules)
            new_symbols = symbols if symbols is not None else list(row["symbols"] or [])
            new_alloc = allocation_pct if allocation_pct is not None else dict(row["allocation_pct"] or {})
            new_name = name if name is not None else row["name"]
            new_status = status if status in ("active", "paused", "closed", "pending") else row["status"]
            new_horizon = row.get("horizon_days")
            if horizon_days is not None:
                new_horizon = int(horizon_days) if int(horizon_days) > 0 else None
                new_horizon = clamp_horizon_days(new_horizon)
                merged_rules["horizon_days"] = new_horizon
                merged_rules["open_ended"] = new_horizon is None
                merged_rules["horizon_label"] = _horizon_label_for(new_horizon)
            cur.execute(
                """
                UPDATE hf_strategies SET
                    name = %s, symbols = %s, allocation_pct = %s, rules = %s,
                    status = %s, horizon_days = %s, horizon_label = %s, updated_at = NOW()
                WHERE id = %s RETURNING *
                """,
                (
                    new_name,
                    Json(new_symbols),
                    Json(new_alloc),
                    Json(merged_rules),
                    new_status,
                    new_horizon,
                    merged_rules.get("horizon_label") or row.get("horizon_label"),
                    strategy_id,
                ),
            )
            strategy = _row(cur.fetchone())

    add_result = None
    if add_capital_usd is not None and float(add_capital_usd) > 0:
        add_result = add_capital_to_strategy(strategy_id, user_wallet, float(add_capital_usd))
        if add_result.get("strategy"):
            strategy = add_result["strategy"]
        if add_result.get("error") and not strategy:
            return add_result

    return {"strategy": strategy, "add_capital": add_result}


def add_capital_to_strategy(
    strategy_id: str, user_wallet: str, add_usd: float
) -> dict[str, Any]:
    """Increase paper sleeve capital (capped at HF_MAX_STRATEGY_USDC) and deploy extra fills."""
    strategy = get_strategy(strategy_id, user_wallet)
    if not strategy:
        return {"error": "Strategy not found"}
    if strategy.get("status") not in ("active", "paused"):
        return {"error": f"Cannot add capital while status={strategy.get('status')}"}

    rules = dict(strategy.get("rules") or {})
    current = float(rules.get("capital_usd") or 0)
    room = max(0.0, HF_MAX_STRATEGY_USDC - current)
    add = min(max(HF_MIN_STRATEGY_USDC, float(add_usd)), room) if room > 0 else 0.0
    if add <= 0:
        return {
            "error": f"Sleeve already at max ${HF_MAX_STRATEGY_USDC:,.0f} paper USD",
            "capital_usd": current,
            "max_capital_usd": HF_MAX_STRATEGY_USDC,
        }

    new_total = round(current + add, 2)
    rules["capital_usd"] = new_total
    symbols = list(strategy.get("symbols") or [])
    allocation_pct = dict(strategy.get("allocation_pct") or {})
    if not allocation_pct and symbols:
        w = round(100.0 / len(symbols), 4)
        allocation_pct = {s: w for s in symbols}

    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE hf_strategies SET rules = %s, updated_at = NOW()
                WHERE id = %s RETURNING *
                """,
                (Json(rules), strategy_id),
            )
            strategy = _row(cur.fetchone())

    deploy = None
    if strategy.get("status") == "active" and symbols:
        refresh_symbols(symbols, force=False)
        deploy = _deploy_initial_allocations(
            strategy["portfolio_id"],
            strategy_id,
            user_wallet,
            symbols,
            allocation_pct,
            capital_usd=add,
        )

    return {
        "strategy": strategy,
        "added_usd": add,
        "capital_usd": new_total,
        "max_capital_usd": HF_MAX_STRATEGY_USDC,
        "deploy": deploy,
        "message": f"Added ${add:,.2f} paper capital → sleeve ${new_total:,.2f} (max ${HF_MAX_STRATEGY_USDC:,.0f}).",
    }


def analyze_live_asset(symbol: str, equity_usd: float = HF_MAX_STRATEGY_USDC) -> dict[str, Any]:
    """Realtime Yahoo mark + 18-analyst graph for a stock/crypto ticker."""
    from covenant_pipeline import analyze_yahoo_asset
    from hedge_fund_assets import resolve_hf_solana_asset

    snap = upsert_market_snapshot(symbol, force=True)
    analysis = analyze_yahoo_asset(
        symbol,
        lookback_days=180,
        equity_usd=float(equity_usd) or HF_MAX_STRATEGY_USDC,
        cash_usd=float(equity_usd) or HF_MAX_STRATEGY_USDC,
    )
    mint_info = resolve_hf_solana_asset(analysis.get("symbol") or symbol)
    return {
        "symbol": analysis.get("symbol") or symbol,
        "live_price_usd": snap.get("price_usd") if not snap.get("error") else None,
        "change_24h_pct": snap.get("change_24h_pct"),
        "snapshot": snap if not snap.get("error") else None,
        "analysis": analysis,
        "solana": mint_info if not mint_info.get("error") else None,
        "paper": True,
        "note": "Live Yahoo marks + deterministic analysts — paper mode, not financial advice.",
    }


def list_strategies(
    user_wallet: str,
    *,
    include_failed: bool = True,
    include_closed: bool = True,
) -> list[dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM hf_strategies WHERE user_wallet = %s ORDER BY created_at DESC",
                (user_wallet.strip(),),
            )
            rows = [_row(r) for r in cur.fetchall()]
    if not include_failed:
        rows = [r for r in rows if r.get("status") != "failed"]
    if not include_closed:
        rows = [r for r in rows if r.get("status") != "closed"]
    return rows


def _successful_live_buys(strategy_id: str) -> bool:
    from hedge_fund_live import list_live_positions, list_live_trades

    if sum(float(p.get("units") or 0) for p in list_live_positions(strategy_id)) > 0:
        return True
    for t in list_live_trades(strategy_id, limit=50):
        if str(t.get("side") or "").upper() == "BUY" and float(t.get("units") or 0) > 0:
            if t.get("signature"):
                return True
            # Paper-like fill without signature still counts as a fill
            if float(t.get("notional_usd") or 0) > 0:
                return True
    return False


def reconcile_stuck_live_strategies(user_wallet: str) -> dict[str, Any]:
    """
    Failed Jupiter deploys left strategies on the board and ledger spend
    even though tokens never left the HF wallet. Refund + dismiss those sleeves.
    """
    from hedge_fund_ledger import refund_failed_hf_deploy, _strategy_deploy_spend_outstanding
    from hedge_fund_live import list_live_trades

    # Worst-case deploy time: up to 12 assets * SWAP_TIMEOUT_S(150s) each,
    # sequential, plus overhead. Anything still mid-flight within this window
    # is NOT stuck — leave it alone so we don't race a live deploy call.
    DEPLOY_GRACE_MINUTES = 35

    healed = []
    for s in list_strategies(user_wallet):
        status = s.get("status")
        if status in ("dismissed", "closed"):
            continue
        rules = dict(s.get("rules") or {})
        mode = (s.get("trading_mode") or rules.get("trading_mode") or "live").lower()
        if mode != "live":
            continue
        sid = s["id"]
        if _successful_live_buys(sid):
            continue

        deploy_started_at = rules.get("deploy_started_at")
        if deploy_started_at:
            try:
                started = datetime.fromisoformat(str(deploy_started_at))
                if (_now() - started).total_seconds() < DEPLOY_GRACE_MINUTES * 60:
                    continue
            except (TypeError, ValueError):
                pass

        live_tr = list_live_trades(sid, limit=50)
        outstanding = _strategy_deploy_spend_outstanding(user_wallet, sid)
        attempted = bool(
            live_tr
            or outstanding
            or rules.get("last_error")
            or rules.get("deploy_failed_at")
            or status in ("failed", "active")
        )
        # Clean pending proposal with no deploy attempt — leave for confirm
        if status == "pending" and not attempted:
            continue
        if not attempted:
            continue

        refund = refund_failed_hf_deploy(user_wallet, sid) if outstanding else {"refunded": False, "credits": []}
        err_bits = [
            t.get("reason")
            for t in live_tr
            if str(t.get("side") or "").upper() == "ERROR" and t.get("reason")
        ]
        rules["last_error"] = rules.get("last_error") or (
            err_bits[0] if err_bits else "Could not buy tokens/stocks — capital returned to your balance"
        )
        rules["ledger_refunded"] = bool(refund.get("refunded") or refund.get("credits"))
        rules["refund_credits"] = refund.get("credits") or []
        rules["dismissed"] = True
        rules["dismissed_at"] = _now().isoformat()
        rules["dismiss_reason"] = "auto_reconcile_failed_deploy"
        init_db()
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE hf_strategies
                    SET status = 'dismissed', rules = %s, updated_at = NOW()
                    WHERE id = %s AND user_wallet = %s
                    """,
                    (Json(rules), sid, user_wallet.strip()),
                )
        healed.append(
            {
                "id": sid,
                "refunded": rules["ledger_refunded"],
                "credits": rules["refund_credits"],
                "error": rules["last_error"],
            }
        )
    return {"healed": healed, "count": len(healed)}


def dismiss_strategy(strategy_id: str, user_wallet: str) -> dict[str, Any]:
    """Remove failed/pending-never-deployed strategies from the board and refund unused spend."""
    from hedge_fund_ledger import refund_failed_hf_deploy

    strategy = get_strategy(strategy_id, user_wallet)
    if not strategy:
        return {"error": "Strategy not found"}
    status = strategy.get("status")
    rules = dict(strategy.get("rules") or {})
    if status not in ("failed", "pending", "closed", "active"):
        return {
            "error": "Only failed, pending, closed, or empty active strategies can be dismissed.",
            "status": status,
        }
    if status == "active" and _successful_live_buys(strategy_id):
        return {"error": "Active strategy has live fills — liquidate instead of dismiss."}

    refund = refund_failed_hf_deploy(user_wallet, strategy_id)
    rules["ledger_refunded"] = bool(refund.get("refunded") or refund.get("credits"))
    rules["refund_credits"] = refund.get("credits") or []
    rules["dismissed"] = True
    rules["dismissed_at"] = _now().isoformat()

    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE hf_strategies
                SET status = 'dismissed', rules = %s, updated_at = NOW()
                WHERE id = %s AND user_wallet = %s RETURNING *
                """,
                (Json(rules), strategy_id, user_wallet.strip()),
            )
            row = cur.fetchone()
    return {
        "dismissed": True,
        "strategy_id": strategy_id,
        "strategy": _row(row) if row else None,
        "refund": refund,
        "message": (
            f"Strategy {strategy_id} dismissed."
            + (" Unused deploy capital returned to your balance." if refund.get("credits") else "")
        ),
    }


def get_strategy(strategy_id: str, user_wallet: Optional[str] = None) -> Optional[dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            if user_wallet:
                cur.execute(
                    "SELECT * FROM hf_strategies WHERE id = %s AND user_wallet = %s",
                    (strategy_id, user_wallet.strip()),
                )
            else:
                cur.execute("SELECT * FROM hf_strategies WHERE id = %s", (strategy_id,))
            row = cur.fetchone()
            return _row(row) if row else None


# ─── Paper execution ──────────────────────────────────────────────────────────

def _get_price(symbol: str) -> Optional[float]:
    snap = upsert_market_snapshot(symbol, force=False)
    if snap.get("error"):
        return None
    return float(snap.get("price_usd") or 0) or None


def _deploy_initial_allocations(
    portfolio_id: str,
    strategy_id: str,
    user_wallet: str,
    symbols: list[str],
    allocation_pct: dict[str, float],
    capital_usd: Optional[float] = None,
) -> dict[str, Any]:
    trades = []
    portfolio = get_portfolio(portfolio_id)
    if not portfolio:
        return {"trades": [], "count": 0, "error": "Portfolio not found"}

    # Prefer strategy sleeve capital (e.g. $1000) — not the entire book cash
    sleeve = float(capital_usd) if capital_usd is not None else None
    if sleeve is None:
        st = get_strategy(strategy_id, user_wallet)
        rules = (st or {}).get("rules") or {}
        sleeve = float(rules.get("capital_usd") or 0) or float(portfolio["cash_usd"])
    sleeve = max(HF_MIN_STRATEGY_USDC, float(sleeve))

    funded = _ensure_paper_cash(portfolio_id, sleeve)
    if funded.get("error"):
        return {"trades": [], "count": 0, "error": funded["error"], "capital_usd": sleeve}

    for sym in symbols:
        pct = float(allocation_pct.get(sym) or (100.0 / max(len(symbols), 1)))
        notional = sleeve * (pct / 100.0)
        price = _get_price(sym)
        if not price or notional < 1:
            continue
        portfolio = get_portfolio(portfolio_id)
        cash = float((portfolio or {}).get("cash_usd") or 0)
        spend = min(notional, cash)
        if spend < 1:
            continue
        t = execute_paper_trade(
            portfolio_id=portfolio_id,
            strategy_id=strategy_id,
            user_wallet=user_wallet,
            symbol=sym,
            side="BUY",
            notional_usd=spend,
            reason=f"Initial paper allocation (${sleeve:,.0f} sleeve)",
            decision="buy",
        )
        trades.append(t)
    ok = [t for t in trades if not t.get("error") and t.get("trade")]
    return {
        "trades": trades,
        "count": len(ok),
        "capital_usd": sleeve,
        "cash_credited_usd": funded.get("credited_usd") or 0,
        "error": None if ok else "No fills placed (check prices / cash)",
    }


def execute_paper_trade(
    portfolio_id: str,
    user_wallet: str,
    symbol: str,
    side: str,
    notional_usd: Optional[float] = None,
    units: Optional[float] = None,
    strategy_id: Optional[str] = None,
    reason: str = "",
    decision: str = "",
) -> dict[str, Any]:
    init_db()
    side = side.upper()
    if side not in ("BUY", "SELL"):
        return {"error": "side must be BUY or SELL"}
    price = _get_price(symbol)
    if not price:
        return {"error": f"No price for {symbol}"}

    portfolio = get_portfolio(portfolio_id, user_wallet)
    if not portfolio:
        return {"error": "Portfolio not found"}

    with get_conn() as conn:
        with conn.cursor() as cur:
            if strategy_id:
                cur.execute(
                    """
                    SELECT * FROM hf_paper_positions
                    WHERE portfolio_id = %s AND symbol = %s AND strategy_id = %s FOR UPDATE
                    """,
                    (portfolio_id, symbol.upper(), strategy_id),
                )
            else:
                cur.execute(
                    """
                    SELECT * FROM hf_paper_positions
                    WHERE portfolio_id = %s AND symbol = %s
                    ORDER BY updated_at DESC LIMIT 1 FOR UPDATE
                    """,
                    (portfolio_id, symbol.upper()),
                )
            pos = cur.fetchone()
            cash = float(portfolio["cash_usd"])

            if side == "BUY":
                if units is None:
                    if not notional_usd or notional_usd <= 0:
                        return {"error": "notional_usd or units required"}
                    units = float(notional_usd) / price
                units = float(units)
                cost = units * price
                if cost > cash + 1e-6:
                    return {"error": f"Insufficient paper cash (${cash:.2f}) for ${cost:.2f} buy"}
                new_cash = cash - cost
                if pos:
                    old_u = float(pos["units"])
                    old_avg = float(pos["avg_entry_usd"])
                    new_u = old_u + units
                    new_avg = ((old_u * old_avg) + cost) / new_u if new_u else price
                    cur.execute(
                        """
                        UPDATE hf_paper_positions SET units=%s, avg_entry_usd=%s, mark_price_usd=%s,
                            strategy_id=COALESCE(%s, strategy_id), updated_at=NOW()
                        WHERE id=%s
                        """,
                        (new_u, new_avg, price, strategy_id, pos["id"]),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO hf_paper_positions (id, portfolio_id, strategy_id, symbol, units, avg_entry_usd, mark_price_usd)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (_new_id("hz"), portfolio_id, strategy_id, symbol.upper(), units, price, price),
                    )
            else:
                if not pos or float(pos["units"]) <= 0:
                    return {"error": f"No position in {symbol} to sell"}
                held = float(pos["units"])
                if units is None:
                    if notional_usd and notional_usd > 0:
                        units = min(held, float(notional_usd) / price)
                    else:
                        units = held
                units = min(held, float(units))
                proceeds = units * price
                new_cash = cash + proceeds
                new_u = held - units
                if new_u < 1e-8:
                    cur.execute("DELETE FROM hf_paper_positions WHERE id = %s", (pos["id"],))
                else:
                    cur.execute(
                        """
                        UPDATE hf_paper_positions SET units=%s, mark_price_usd=%s, updated_at=NOW()
                        WHERE id=%s
                        """,
                        (new_u, price, pos["id"]),
                    )
                cost = units  # for notional below
                cost = proceeds

            tid = _new_id("ht")
            notional = units * price
            cur.execute(
                """
                UPDATE hf_paper_portfolios SET cash_usd=%s, updated_at=NOW() WHERE id=%s
                """,
                (new_cash, portfolio_id),
            )
            cur.execute(
                """
                INSERT INTO hf_paper_trades (
                    id, portfolio_id, strategy_id, user_wallet, symbol, side, units, price_usd, notional_usd, reason, decision
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
                """,
                (
                    tid,
                    portfolio_id,
                    strategy_id,
                    user_wallet.strip(),
                    symbol.upper(),
                    side,
                    units,
                    price,
                    notional,
                    reason,
                    decision or side.lower(),
                ),
            )
            trade = _row(cur.fetchone())
    return {"trade": trade, "cash_usd": round(new_cash, 2)}


def list_trades(user_wallet: str, limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM hf_paper_trades WHERE user_wallet = %s
                ORDER BY created_at DESC LIMIT %s
                """,
                (user_wallet.strip(), max(1, min(limit, 200))),
            )
            return [_row(r) for r in cur.fetchall()]


def list_decisions(user_wallet: str, limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM hf_decisions WHERE user_wallet = %s
                ORDER BY created_at DESC LIMIT %s
                """,
                (user_wallet.strip(), max(1, min(limit, 200))),
            )
            return [_row(r) for r in cur.fetchall()]


# ─── Decision engine ──────────────────────────────────────────────────────────

def _record_decision(
    strategy_id: str,
    portfolio_id: str,
    user_wallet: str,
    symbol: str,
    action: str,
    rationale: str,
    price_usd: float,
    confidence: float = 0.5,
    executed: bool = False,
    trade_id: Optional[str] = None,
    signals: Optional[list] = None,
    decision_graph: Optional[dict] = None,
) -> dict[str, Any]:
    init_db()
    did = _new_id("hd")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO hf_decisions (
                    id, strategy_id, portfolio_id, user_wallet, symbol, action,
                    confidence, rationale, price_usd, executed, trade_id, signals, decision_graph
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
                """,
                (
                    did,
                    strategy_id,
                    portfolio_id,
                    user_wallet,
                    symbol.upper(),
                    action,
                    confidence,
                    rationale,
                    price_usd,
                    executed,
                    trade_id,
                    Json(signals or []),
                    Json(decision_graph or {}),
                ),
            )
            return _row(cur.fetchone())


def list_positions_for_strategy(strategy_id: str) -> list[dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM hf_paper_positions WHERE strategy_id = %s AND units > 0 ORDER BY symbol",
                (strategy_id,),
            )
            return [_row(r) for r in cur.fetchall()]


def evaluate_strategy(strategy_id: str, execute: bool = True) -> dict[str, Any]:
    """Covenant 18-analyst decisions + user TP/SL overrides. Auditable signal graph."""
    from covenant_pipeline import analyze_yahoo_asset

    # Auto-liquidate when horizon ends
    liq = maybe_liquidate_expired(strategy_id)
    if liq and liq.get("liquidated"):
        return {
            "strategy_id": strategy_id,
            "liquidated": True,
            "liquidation": liq,
            "decisions": [],
            "count": 0,
            "evaluated_at": _now().isoformat(),
        }

    strategy = get_strategy(strategy_id)
    if not strategy or strategy.get("status") != "active":
        return {"error": "Strategy not active", "strategy_id": strategy_id}

    rules0 = strategy.get("rules") or {}
    trading_mode = (strategy.get("trading_mode") or rules0.get("trading_mode") or "live").lower()
    if trading_mode == "live":
        # Live sleeves: only horizon auto-liquidate runs above; no paper fills.
        return {
            "strategy_id": strategy_id,
            "trading_mode": "live",
            "skipped_paper_eval": True,
            "decisions": [],
            "count": 0,
            "evaluated_at": _now().isoformat(),
            "note": "Live strategy — marks/trades on-chain; paper covenant loop skipped.",
        }

    symbols = list(strategy.get("symbols") or [])
    rules = strategy.get("rules") or {}
    tp = float(rules.get("take_profit_pct") or 0)
    sl = float(rules.get("stop_loss_pct") or 0)
    horizon = int(strategy.get("horizon_days") or rules.get("horizon_days") or 90)
    lookback = max(90, min(500, horizon * 2))
    portfolio_id = strategy["portfolio_id"]
    user_wallet = strategy["user_wallet"]

    refresh_symbols(symbols, force=False)
    positions = {p["symbol"]: p for p in list_positions_for_strategy(strategy_id)}
    portfolio = get_portfolio(portfolio_id)
    cash = float((portfolio or {}).get("cash_usd") or 0)
    # Mark equity for this strategy sleeve + shared cash
    snaps = {s["symbol"]: s for s in get_market_snapshots(symbols)}
    sleeve_value = 0.0
    marked_positions = []
    for sym, pos in positions.items():
        mark = float((snaps.get(sym) or {}).get("price_usd") or pos.get("mark_price_usd") or pos.get("avg_entry_usd") or 0)
        mv = float(pos["units"]) * mark
        sleeve_value += mv
        marked_positions.append({**pos, "market_value_usd": mv, "mark_price_usd": mark})
    equity = cash + sleeve_value

    decisions = []
    for sym in symbols:
        pos = positions.get(sym)
        price = float((snaps.get(sym) or {}).get("price_usd") or 0)
        analysis = analyze_yahoo_asset(
            sym,
            lookback_days=lookback,
            equity_usd=equity,
            cash_usd=cash,
            existing_positions=marked_positions,
        )
        if analysis.get("error"):
            dec = _record_decision(
                strategy_id, portfolio_id, user_wallet, sym, "hold",
                f"Analysis error: {analysis['error']}", price or 0, 10, False, None, [], {"error": analysis["error"]},
            )
            decisions.append(dec)
            continue

        action = analysis.get("action") or "hold"
        synthesis = analysis.get("synthesis") or {}
        rationale = (
            f"Covenant 18-analyst composite {synthesis.get('composite_score')} → {action} "
            f"(domains {synthesis.get('domain_scores')})"
        )
        confidence = float(synthesis.get("confidence") or 50)
        signals = analysis.get("analyst_signals") or []
        graph = analysis.get("decision_graph") or {}

        # User TP/SL overrides (compliance R15)
        if pos and float(pos.get("units") or 0) > 0 and price:
            entry = float(pos.get("avg_entry_usd") or price)
            pnl_pct = ((price - entry) / entry) * 100 if entry else 0
            if tp and pnl_pct >= tp:
                action = "sell"
                rationale = f"Take-profit hit: +{pnl_pct:.2f}% >= TP {tp}% (overrides signals)"
                confidence = max(confidence, 85)
                graph["override"] = "take_profit"
            elif sl and pnl_pct <= -abs(sl):
                action = "sell"
                rationale = f"Stop-loss hit: {pnl_pct:.2f}% <= -SL {abs(sl)}% (overrides signals)"
                confidence = max(confidence, 90)
                graph["override"] = "stop_loss"

        trade_id = None
        executed = False
        if execute and action in ("buy", "sell"):
            if action == "buy":
                notional = float(analysis.get("suggested_notional_usd") or 0)
                if notional >= 25 and cash >= 25:
                    result = execute_paper_trade(
                        portfolio_id=portfolio_id,
                        strategy_id=strategy_id,
                        user_wallet=user_wallet,
                        symbol=sym,
                        side="BUY",
                        notional_usd=notional,
                        reason=rationale[:240],
                        decision="buy",
                    )
                    if result.get("trade"):
                        executed = True
                        trade_id = result["trade"]["id"]
                        cash = float(result.get("cash_usd") or cash)
            elif action == "sell" and pos:
                result = execute_paper_trade(
                    portfolio_id=portfolio_id,
                    strategy_id=strategy_id,
                    user_wallet=user_wallet,
                    symbol=sym,
                    side="SELL",
                    units=float(pos["units"]),
                    reason=rationale[:240],
                    decision="sell",
                )
                if result.get("trade"):
                    executed = True
                    trade_id = result["trade"]["id"]
                    cash = float(result.get("cash_usd") or cash)

        price = price or float((analysis.get("features") or {}).get("price") or 0)
        dec = _record_decision(
            strategy_id,
            portfolio_id,
            user_wallet,
            sym,
            action,
            rationale[:500],
            price,
            confidence / 100.0 if confidence > 1 else confidence,
            executed,
            trade_id,
            signals,
            graph,
        )
        decisions.append(dec)

    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE hf_strategies SET last_evaluated_at = NOW(), updated_at = NOW() WHERE id = %s",
                (strategy_id,),
            )

    return {
        "strategy_id": strategy_id,
        "horizon_days": horizon,
        "decisions": decisions,
        "count": len(decisions),
        "analysts": 18,
        "llm_required": False,
        "evaluated_at": _now().isoformat(),
    }


def evaluate_all_active_strategies() -> dict[str, Any]:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM hf_strategies WHERE status = 'active'")
            ids = [r["id"] for r in cur.fetchall()]
    results = []
    for sid in ids:
        results.append(evaluate_strategy(sid, execute=True))
    return {"strategies_evaluated": len(ids), "results": results}


def liquidate_all_expired_strategies() -> dict[str, Any]:
    """Cheap scheduler pass: check every active horizon without market-data calls."""
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Recover a claim if the API process died during an on-chain call.
            cur.execute(
                """
                UPDATE hf_strategies
                SET status = CASE
                    WHEN rules->>'pre_liquidation_status' IN ('closed', 'paused', 'active')
                        THEN rules->>'pre_liquidation_status'
                    ELSE 'active'
                END,
                    updated_at = NOW()
                WHERE status = 'liquidating'
                  AND updated_at < NOW() - INTERVAL '10 minutes'
                """
            )
            cur.execute(
                """
                SELECT id FROM hf_strategies
                WHERE status IN ('active', 'paused')
                  AND horizon_days IS NOT NULL AND horizon_days > 0
                """
            )
            ids = [r["id"] for r in cur.fetchall()]
    results = []
    for sid in ids:
        result = maybe_liquidate_expired(sid)
        if result:
            results.append({"strategy_id": sid, **result})
    return {"checked": len(ids), "liquidations": results, "count": len(results)}


def monitor_cycle(force_prices: bool = False) -> dict[str, Any]:
    """Refresh shared market data for watched symbols, then evaluate strategies."""
    global _last_market_refresh_at
    symbols = list_watched_symbols()
    market = refresh_symbols(symbols, force=force_prices) if symbols else {"snapshots": [], "count": 0}
    evals = evaluate_all_active_strategies()
    _last_market_refresh_at = _now()
    return {
        "market": market,
        "evaluations": evals,
        "monitored_symbols": symbols,
        "at": _last_market_refresh_at.isoformat(),
        "interval_seconds": HF_MONITOR_INTERVAL_SECONDS,
    }


# ─── Backtests for strategies ─────────────────────────────────────────────────

PERIOD_DAYS = {
    "1w": 7,
    "1week": 7,
    "1m": 30,
    "1month": 30,
    "3m": 90,
    "6m": 182,
    "6months": 182,
    "1y": 365,
    "1year": 365,
}


def run_strategy_backtest(
    user_wallet: str,
    period: str = "6m",
    strategy_id: Optional[str] = None,
    symbols: Optional[list[str]] = None,
    capital_usd: float = DEFAULT_PAPER_CAPITAL,
) -> dict[str, Any]:
    from covenant_picker import select_assets_for_horizon

    label = (period or "6m").lower().strip()
    days = PERIOD_DAYS.get(label)
    if not days:
        return {"error": f"Unknown period '{period}'. Use 1w, 1m, 3m, 6m, 1y."}

    rules = {}
    horizon_days = days
    if strategy_id:
        strategy = get_strategy(strategy_id, user_wallet)
        if not strategy:
            return {"error": "Strategy not found"}
        symbols = list(strategy.get("symbols") or [])
        rules = strategy.get("rules") or {}
        horizon_days = int(strategy.get("horizon_days") or rules.get("horizon_days") or days)
    elif not symbols:
        pick = select_assets_for_horizon(horizon_days=days)
        symbols = list(pick.get("symbols") or [])
        rules = {"picker": pick.get("note"), "horizon_days": days}

    syms = [s.strip().upper() for s in (symbols or [])]
    if not syms:
        return {"error": "No symbols to backtest"}
    end = _now().date()
    start = end - timedelta(days=days)
    result = run_mock_backtest(
        tokens=syms,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        capital_usd=capital_usd,
        include_news=True,
    )
    if result.get("error"):
        return result

    bid = _new_id("hb")
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO hf_backtest_runs (
                    id, strategy_id, user_wallet, period_label, start_date, end_date, symbols, rules, result
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id, created_at
                """,
                (
                    bid,
                    strategy_id,
                    user_wallet.strip(),
                    label,
                    start,
                    end,
                    Json(syms),
                    Json(rules),
                    Json(result),
                ),
            )
            row = cur.fetchone()
    return {
        "backtest_id": bid,
        "period": label,
        "horizon_days": horizon_days,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "symbols": syms,
        "rules": rules,
        "result": result,
        "metrics": result.get("metrics"),
        "created_at": row["created_at"].isoformat() if row else None,
    }


def list_backtests(user_wallet: str, limit: int = 20) -> list[dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, strategy_id, period_label, start_date, end_date, symbols, created_at,
                       result->'gross_pnl_pct' AS gross_pnl_pct,
                       result->'net_pnl_pct' AS net_pnl_pct,
                       result->'end_value_usd' AS end_value_usd
                FROM hf_backtest_runs
                WHERE user_wallet = %s
                ORDER BY created_at DESC LIMIT %s
                """,
                (user_wallet.strip(), max(1, min(limit, 50))),
            )
            return [_row(r) for r in cur.fetchall()]


def paper_dashboard(user_wallet: str) -> dict[str, Any]:
    from hedge_fund_live import list_live_positions, list_live_trades

    reconcile_stuck_live_strategies(user_wallet)
    summary = portfolio_summary(user_wallet)
    all_strategies = list_strategies(user_wallet)

    # Hide dismissed + failed from the main board
    strategies = [s for s in all_strategies if s.get("status") not in ("dismissed", "failed")]
    failed_strategies = [
        {
            **s,
            "last_error": (s.get("rules") or {}).get("last_error"),
            "deploy_errors": (s.get("rules") or {}).get("deploy_errors") or [],
        }
        for s in all_strategies
        if s.get("status") == "failed"
    ]
    decisions = list_decisions(user_wallet, limit=30)
    trades = list_trades(user_wallet, limit=30)
    backtests = list_backtests(user_wallet, limit=5)
    has_paper = any(
        (s.get("trading_mode") or (s.get("rules") or {}).get("trading_mode") or "live") == "paper"
        for s in strategies
    )
    # Avoid Yahoo market refresh on live-only dashboards (was making loads ~20s+)
    market = get_market_snapshots(list_watched_symbols()[:12]) if has_paper else []

    def _closed_pnl_fields(
        strategy: dict[str, Any],
        trade_rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Realized PnL snapshot for closed / liquidated strategies."""
        if strategy.get("status") != "closed":
            return {}
        rules_local = strategy.get("rules") or {}
        capital = float(rules_local.get("capital_usd") or 0)
        proceeds = rules_local.get("liquidation_proceeds_usd")
        buy_notional = sum(
            float(t.get("notional_usd") or 0)
            for t in trade_rows
            if str(t.get("side") or "").upper() == "BUY"
        )
        sell_notional = sum(
            float(t.get("notional_usd") or 0)
            for t in trade_rows
            if str(t.get("side") or "").upper() == "SELL"
        )
        fee_notional = sum(
            float(t.get("notional_usd") or t.get("fee_usd") or 0)
            for t in trade_rows
            if str(t.get("side") or "").upper() == "FEE"
        )
        if proceeds is not None:
            basis = buy_notional or capital
            realized = float(proceeds) - basis
        else:
            realized = sell_notional - buy_notional
        basis_pct = buy_notional or capital
        return {
            "closed": True,
            "realized_pnl_usd": round(realized, 2),
            "realized_pnl_pct": round((realized / basis_pct) * 100, 2) if basis_pct else 0.0,
            "liquidation_proceeds_usd": float(proceeds) if proceeds is not None else None,
            "capital_usd": capital or None,
            "perf_fee_usd": round(fee_notional, 2) if fee_notional else rules_local.get("perf_fee_usd"),
        }

    all_live_trades: list[dict[str, Any]] = []
    # Per-strategy breakdown (same asset can appear under multiple strategies)
    by_strategy: list[dict[str, Any]] = []
    for s in strategies:
        sid = s["id"]
        rules = s.get("rules") or {}
        trading_mode = (s.get("trading_mode") or rules.get("trading_mode") or "live").lower()
        # Pending proposals belong on the strategy list, not the live-sleeve board
        if s.get("status") == "pending":
            continue
        if trading_mode == "live":
            live_pos = list_live_positions(sid)
            live_tr = list_live_trades(sid, limit=30)
            all_live_trades.extend(live_tr)
            sleeve = sum(float(p.get("cost_basis_usd") or 0) for p in live_pos)
            marked = [
                {
                    **p,
                    "strategy_id": sid,
                    "strategy_name": s.get("name"),
                    "market_value_usd": p.get("cost_basis_usd"),
                    "unrealized_pnl_usd": None,
                }
                for p in live_pos
                if float(p.get("units") or 0) > 0
            ]
            by_strategy.append(
                {
                    "strategy": s,
                    "trading_mode": "live",
                    "positions": marked,
                    "sleeve_value_usd": round(sleeve, 2),
                    "trades": [],
                    "live_trades": live_tr[:15],
                    "decisions": [d for d in decisions if d.get("strategy_id") == sid][:10],
                    "symbols": s.get("symbols") or [],
                    "horizon_days": s.get("horizon_days"),
                    "horizon_label": s.get("horizon_label"),
                    "liquidation_txs": (rules.get("liquidation_txs") or []),
                    **_closed_pnl_fields(s, live_tr),
                }
            )
            continue

        spos = list_positions_for_strategy(sid)
        marked = []
        sleeve = 0.0
        for p in spos:
            mark = float(p.get("mark_price_usd") or p.get("avg_entry_usd") or 0)
            mv = float(p["units"]) * mark
            cost = float(p["units"]) * float(p["avg_entry_usd"] or 0)
            sleeve += mv
            marked.append(
                {
                    **p,
                    "strategy_id": sid,
                    "strategy_name": s.get("name"),
                    "mark_price_usd": mark,
                    "market_value_usd": round(mv, 2),
                    "unrealized_pnl_usd": round(mv - cost, 2),
                }
            )
        s_trades_all = [t for t in trades if t.get("strategy_id") == sid]
        s_trades = s_trades_all[:15]
        s_decisions = [d for d in decisions if d.get("strategy_id") == sid][:10]
        by_strategy.append(
            {
                "strategy": s,
                "trading_mode": "paper",
                "positions": marked,
                "sleeve_value_usd": round(sleeve, 2),
                "trades": s_trades,
                "live_trades": [],
                "decisions": s_decisions,
                "symbols": s.get("symbols") or [],
                "horizon_days": s.get("horizon_days"),
                "horizon_label": s.get("horizon_label"),
                **_closed_pnl_fields(s, s_trades_all),
            }
        )

    # Shared assets across strategies
    symbol_to_strategies: dict[str, list[str]] = {}
    for block in by_strategy:
        for sym in block["symbols"]:
            symbol_to_strategies.setdefault(sym, []).append(block["strategy"]["id"])
    overlapping = {k: v for k, v in symbol_to_strategies.items() if len(v) > 1}

    live_count = sum(1 for s in strategies if (s.get("trading_mode") or (s.get("rules") or {}).get("trading_mode") or "live") == "live")
    return {
        "mode": "live" if live_count else "paper",
        "live_trading": True,
        "paper_trading": True,
        "governance": "Covenant 18-analyst deterministic",
        "llm_required": False,
        "monitor_interval_seconds": HF_MONITOR_INTERVAL_SECONDS,
        "last_market_refresh_at": _last_market_refresh_at.isoformat() if _last_market_refresh_at else None,
        "portfolio": summary,
        "strategies": strategies,
        "failed_strategies": failed_strategies,
        "by_strategy": by_strategy,
        "overlapping_assets": overlapping,
        "decisions": decisions,
        "trades": trades,
        "live_trades": all_live_trades[:50],
        "backtests": backtests,
        "market": market,
        # Skip Yahoo news on every dashboard poll — was making the page feel stuck
        "news": [],
    }


# ─── Scheduler ────────────────────────────────────────────────────────────────

def _scheduler_loop() -> None:
    global _last_market_refresh_at
    try:
        print("  HF close cycle on startup (expired + unswapped closed → SOL)")
        startup = run_horizon_close_cycle()
        if startup["expired_count"] or startup["unswapped_count"]:
            print(
                f"  HF startup close: {startup['expired_count']} expired, "
                f"{startup['unswapped_count']} previously-closed still holding tokens"
            )
        else:
            print("  HF startup close: no strategies needed swapping")
    except Exception as exc:
        print(f"  ⚠️  HF startup close cycle error: {exc}")

    while not _scheduler_stop.is_set():
        if _scheduler_stop.wait(HF_SCHEDULER_POLL_SECONDS):
            break
        try:
            cycle = run_horizon_close_cycle()
            if cycle["expired_count"] or cycle["unswapped_count"]:
                print(
                    f"  HF auto-close: {cycle['expired_count']} expired, "
                    f"{cycle['unswapped_count']} unswapped closed"
                )

            due = True
            if _last_market_refresh_at is not None:
                age = (_now() - _last_market_refresh_at).total_seconds()
                due = age >= HF_MONITOR_INTERVAL_SECONDS
            if due:
                print(f"\n  📈 Hedge Fund paper monitor cycle ({HF_MONITOR_INTERVAL_SECONDS // 3600}h)")
                result = monitor_cycle(force_prices=True)
                print(
                    f"  HF monitor: {result.get('market', {}).get('count', 0)} symbols · "
                    f"{result.get('evaluations', {}).get('strategies_evaluated', 0)} strategies"
                )
        except Exception as exc:
            print(f"  ⚠️  HF paper scheduler error: {exc}")


def start_hedge_fund_scheduler() -> bool:
    global _scheduler_thread
    if _scheduler_thread and _scheduler_thread.is_alive():
        return True
    _scheduler_stop.clear()
    _scheduler_thread = threading.Thread(
        target=_scheduler_loop, name="hf-paper-scheduler", daemon=True
    )
    _scheduler_thread.start()
    return True


def stop_hedge_fund_scheduler() -> None:
    _scheduler_stop.set()


def scheduler_status() -> dict[str, Any]:
    return {
        "running": bool(_scheduler_thread and _scheduler_thread.is_alive()),
        "interval_seconds": HF_MONITOR_INTERVAL_SECONDS,
        "poll_seconds": HF_SCHEDULER_POLL_SECONDS,
        "close_poll_seconds": HF_SCHEDULER_POLL_SECONDS,
        "last_market_refresh_at": _last_market_refresh_at.isoformat() if _last_market_refresh_at else None,
        "watched_symbols": list_watched_symbols(),
    }
