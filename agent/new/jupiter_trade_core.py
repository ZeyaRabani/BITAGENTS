"""
Jupiter Trade Agent core.

Flow:
1) propose_strategy → awaiting_confirm (agent restates understanding)
2) confirm_understanding → paper_running (≥24h paper required)
3) paper monitor marks paper_ready after min hours
4) confirm_live → live Jupiter spot buys/sells (not perps)
"""

from __future__ import annotations

import os
import secrets
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

from psycopg2.extras import Json

from db import get_conn, init_db

JT_PAPER_MIN_HOURS = float(os.environ.get("JT_PAPER_MIN_HOURS", "24"))
JT_MONITOR_INTERVAL_SECONDS = int(os.environ.get("JT_MONITOR_INTERVAL_SECONDS", "900"))
JT_MAX_CAPITAL_SOL = float(os.environ.get("JT_MAX_CAPITAL_SOL", "10"))
JT_DEFAULT_TP_PCT = float(os.environ.get("JT_DEFAULT_TP_PCT", "12"))
JT_DEFAULT_SL_PCT = float(os.environ.get("JT_DEFAULT_SL_PCT", "6"))
SOL_MINT = "So11111111111111111111111111111111111111112"

_scheduler_started = False
_scheduler_lock = threading.Lock()


def _new_id(prefix: str = "jt") -> str:
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


def _parse_symbols(symbols: Optional[list[str] | str]) -> list[str]:
    if symbols is None:
        return []
    if isinstance(symbols, str):
        parts = [p.strip().upper() for p in symbols.replace(",", " ").split() if p.strip()]
        return parts[:8]
    out: list[str] = []
    for s in symbols:
        t = str(s or "").strip().upper()
        if t and t not in out:
            out.append(t)
    return out[:8]


def _resolve_mint(symbol: str) -> dict[str, Any]:
    from dca_agent import resolve_token

    try:
        resolved = resolve_token(symbol)
        if isinstance(resolved, dict) and not resolved.get("error"):
            mint = resolved.get("mint") or resolved.get("address")
            if mint:
                return {
                    "symbol": (resolved.get("symbol") or symbol).upper(),
                    "mint": mint,
                    "decimals": int(resolved.get("decimals") or 6),
                }
    except Exception as exc:
        return {"error": f"Could not resolve {symbol}: {exc}"}
    return {"error": f"Unknown token {symbol}. Use a Solana ticker or mint."}


def _price_usd(symbol_or_mint: str) -> Optional[float]:
    try:
        from dca_agent import get_token_price

        p = get_token_price(symbol_or_mint)
        if isinstance(p, dict):
            return float(p.get("price_usd") or p.get("usd_price") or 0) or None
        return float(p) if p else None
    except Exception:
        return None


def _sol_usd() -> float:
    return _price_usd("SOL") or _price_usd(SOL_MINT) or 150.0


def _add_event(strategy_id: str, user_wallet: str, event_type: str, detail: dict[str, Any]) -> None:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO jt_events (id, strategy_id, user_wallet, event_type, detail)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (_new_id("je"), strategy_id, user_wallet, event_type, Json(detail)),
            )


def get_strategy(strategy_id: str, user_wallet: Optional[str] = None) -> Optional[dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            if user_wallet:
                cur.execute(
                    "SELECT * FROM jt_strategies WHERE id = %s AND user_wallet = %s",
                    (strategy_id, user_wallet),
                )
            else:
                cur.execute("SELECT * FROM jt_strategies WHERE id = %s", (strategy_id,))
            return _row(cur.fetchone())


def list_strategies(user_wallet: str) -> list[dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM jt_strategies
                WHERE user_wallet = %s
                ORDER BY created_at DESC
                LIMIT 50
                """,
                (user_wallet,),
            )
            return [_row(r) for r in cur.fetchall()]


def list_trades(strategy_id: str, limit: int = 100) -> list[dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM jt_paper_trades
                WHERE strategy_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (strategy_id, limit),
            )
            return [_row(r) for r in cur.fetchall()]


def list_positions(strategy_id: str) -> list[dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM jt_paper_positions
                WHERE strategy_id = %s AND units > 0
                ORDER BY symbol
                """,
                (strategy_id,),
            )
            rows = [_row(r) for r in cur.fetchall()]
    for row in rows:
        mark = _price_usd(row.get("mint") or row.get("symbol") or "")
        if mark:
            row["mark_price_usd"] = mark
            units = float(row.get("units") or 0)
            entry = float(row.get("avg_entry_usd") or 0)
            row["market_value_usd"] = units * mark
            row["unrealized_pnl_usd"] = units * (mark - entry)
            row["unrealized_pnl_pct"] = ((mark - entry) / entry * 100.0) if entry else 0.0
    return rows


def _build_understanding(
    *,
    name: str,
    symbols: list[str],
    capital_sol: float,
    take_profit_pct: float,
    stop_loss_pct: float,
    notes: str,
    mint_map: dict[str, str],
    template: Optional[dict[str, Any]] = None,
) -> str:
    from jupiter_trade_templates import format_template_for_understanding

    book = ", ".join(f"{s} ({mint_map.get(s, '?')[:6]}…)" for s in symbols) or "(none)"
    algo_block = format_template_for_understanding(template) if template else "- Algo template: custom / notes only"
    return (
        f"I understand this Jupiter spot strategy as:\n"
        f"- Name: {name}\n"
        f"- Venue: Jupiter spot swaps only (not Jupiter Perps)\n"
        f"- Book: {book}\n"
        f"- Capital: {capital_sol:.4f} SOL (paper first)\n"
        f"- Take profit: {take_profit_pct:.2f}% · Stop loss: {stop_loss_pct:.2f}%\n"
        f"{algo_block}\n"
        f"- Notes: {notes or 'none'}\n"
        f"- Platform fee: 0.1% per live Jupiter spot trade\n\n"
        f"If this matches what you want, confirm understanding for this strategy. "
        f"I will then run paper mode for at least {JT_PAPER_MIN_HOURS:g} hours and record fills "
        f"for you to review before any live Jupiter trades."
    )


def propose_strategy(
    user_wallet: str,
    *,
    name: str = "",
    symbols: Optional[list[str] | str] = None,
    capital_sol: float = 1.0,
    take_profit_pct: Optional[float] = None,
    stop_loss_pct: Optional[float] = None,
    notes: str = "",
    template_id: str = "",
    created_by: str = "user",
) -> dict[str, Any]:
    from jupiter_trade_templates import get_strategy_template, match_strategy_template

    user_wallet = (user_wallet or "").strip()
    if not user_wallet:
        return {"error": "user_wallet required"}

    syms = _parse_symbols(symbols)
    if not syms:
        return {"error": "Provide at least one Solana token symbol (e.g. SOL BONK JUP)."}

    template = None
    template_query = (template_id or "").strip()
    if template_query:
        found = get_strategy_template(template_query)
        if found.get("error"):
            found = match_strategy_template(template_query)
        if found.get("error"):
            return found
        template = found["template"]
    elif notes:
        # Soft-match notes like "use MACD" without forcing a template.
        soft = match_strategy_template(notes)
        if soft.get("template") and soft.get("matched_by") in ("exact_alias", "id"):
            template = soft["template"]

    capital_sol = max(0.01, min(JT_MAX_CAPITAL_SOL, float(capital_sol or 1.0)))
    tp_default = float(template["default_tp_pct"]) if template else JT_DEFAULT_TP_PCT
    sl_default = float(template["default_sl_pct"]) if template else JT_DEFAULT_SL_PCT
    # Templates with 0 defaults (pure trail) fall back to agent defaults.
    if tp_default <= 0:
        tp_default = JT_DEFAULT_TP_PCT
    if sl_default <= 0:
        sl_default = JT_DEFAULT_SL_PCT
    tp = float(take_profit_pct if take_profit_pct is not None else tp_default)
    sl = float(stop_loss_pct if stop_loss_pct is not None else sl_default)
    if tp <= 0 or sl <= 0:
        return {"error": "take_profit_pct and stop_loss_pct must be > 0"}

    mint_map: dict[str, str] = {}
    decimals_map: dict[str, int] = {}
    errors: list[str] = []
    for sym in syms:
        if sym == "SOL":
            mint_map[sym] = SOL_MINT
            decimals_map[sym] = 9
            continue
        resolved = _resolve_mint(sym)
        if resolved.get("error"):
            errors.append(str(resolved["error"]))
            continue
        mint_map[sym] = resolved["mint"]
        decimals_map[sym] = int(resolved.get("decimals") or 6)
    if errors and not mint_map:
        return {"error": "; ".join(errors)}
    valid_syms = [s for s in syms if s in mint_map]
    if not valid_syms:
        return {"error": "No resolvable tokens."}

    if name:
        strategy_name = name.strip()[:80]
    elif template:
        strategy_name = f"{template['name']} · {'/'.join(valid_syms[:3])}"[:80]
    else:
        strategy_name = f"JT {'/'.join(valid_syms[:3])}"[:80]

    understanding = _build_understanding(
        name=strategy_name,
        symbols=valid_syms,
        capital_sol=capital_sol,
        take_profit_pct=tp,
        stop_loss_pct=sl,
        notes=notes,
        mint_map=mint_map,
        template=template,
    )
    rules: dict[str, Any] = {
        "take_profit_pct": tp,
        "stop_loss_pct": sl,
        "notes": notes,
        "mint_map": mint_map,
        "decimals_map": decimals_map,
        "venue": "jupiter_spot",
        "perps": False,
        "paper_min_hours": JT_PAPER_MIN_HOURS,
    }
    if template:
        rules["template_id"] = template["id"]
        rules["template_name"] = template["name"]
        rules["template_family"] = template["family"]
        rules["algo"] = {
            "id": template["id"],
            "name": template["name"],
            "family": template["family"],
            "params": template.get("params") or {},
            "entry": template.get("entry"),
            "exit": template.get("exit"),
            "timeframe": template.get("timeframe") or "1h",
        }
    sid = _new_id("jt")
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO jt_strategies (
                    id, user_wallet, name, status, symbols, rules, understanding,
                    capital_sol, cash_sol, created_by
                ) VALUES (%s,%s,%s,'awaiting_confirm',%s,%s,%s,%s,%s,%s)
                RETURNING *
                """,
                (
                    sid,
                    user_wallet,
                    strategy_name,
                    Json(valid_syms),
                    Json(rules),
                    understanding,
                    capital_sol,
                    capital_sol,
                    created_by,
                ),
            )
            strategy = _row(cur.fetchone())
    _add_event(sid, user_wallet, "proposed", {"understanding": understanding})
    return {
        "status": "awaiting_confirm",
        "strategy": strategy,
        "understanding": understanding,
        "next_step": f"Reply: confirm understanding {sid}",
        "paper_min_hours": JT_PAPER_MIN_HOURS,
        "resolve_warnings": errors,
    }


def confirm_understanding(strategy_id: str, user_wallet: str) -> dict[str, Any]:
    strategy = get_strategy(strategy_id, user_wallet)
    if not strategy:
        return {"error": "Strategy not found"}
    if strategy.get("status") not in ("awaiting_confirm", "paused"):
        return {
            "error": f"Cannot confirm understanding from status={strategy.get('status')}",
            "strategy": strategy,
        }

    # Deploy initial paper allocation across non-SOL symbols (or hold SOL book).
    symbols = strategy.get("symbols") or []
    rules = strategy.get("rules") or {}
    mint_map = rules.get("mint_map") or {}
    capital = float(strategy.get("capital_sol") or 0)
    sol_usd = _sol_usd()
    capital_usd = capital * sol_usd
    tradable = [s for s in symbols if s != "SOL"]
    if not tradable:
        tradable = list(symbols)[:1]

    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE jt_strategies
                SET status = 'paper_running',
                    paper_started_at = NOW(),
                    paper_ready_at = NULL,
                    live_started_at = NULL,
                    cash_sol = %s,
                    updated_at = NOW()
                WHERE id = %s AND user_wallet = %s
                RETURNING *
                """,
                (capital, strategy_id, user_wallet),
            )
            strategy = _row(cur.fetchone())

            per_usd = capital_usd / max(1, len(tradable))
            remaining_sol = capital
            for sym in tradable:
                mint = mint_map.get(sym) or (SOL_MINT if sym == "SOL" else None)
                px = _price_usd(mint or sym) or (_sol_usd() if sym == "SOL" else None)
                if not px or px <= 0:
                    continue
                notional_usd = per_usd
                units = notional_usd / px
                spent_sol = notional_usd / sol_usd
                if spent_sol > remaining_sol:
                    spent_sol = remaining_sol
                    notional_usd = spent_sol * sol_usd
                    units = notional_usd / px
                if units <= 0:
                    continue
                remaining_sol = max(0.0, remaining_sol - spent_sol)
                pid = _new_id("jp")
                cur.execute(
                    """
                    INSERT INTO jt_paper_positions (
                        id, strategy_id, user_wallet, symbol, mint, units, avg_entry_usd, mark_price_usd
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (strategy_id, symbol) DO UPDATE SET
                        units = EXCLUDED.units,
                        avg_entry_usd = EXCLUDED.avg_entry_usd,
                        mark_price_usd = EXCLUDED.mark_price_usd,
                        updated_at = NOW()
                    """,
                    (pid, strategy_id, user_wallet, sym, mint, units, px, px),
                )
                cur.execute(
                    """
                    INSERT INTO jt_paper_trades (
                        id, strategy_id, user_wallet, symbol, mint, side, units,
                        price_usd, notional_usd, reason, mode
                    ) VALUES (%s,%s,%s,%s,%s,'BUY',%s,%s,%s,%s,'paper')
                    """,
                    (
                        _new_id("jt"),
                        strategy_id,
                        user_wallet,
                        sym,
                        mint,
                        units,
                        px,
                        notional_usd,
                        "paper open after understanding confirm",
                    ),
                )
            cur.execute(
                "UPDATE jt_strategies SET cash_sol = %s, updated_at = NOW() WHERE id = %s",
                (remaining_sol, strategy_id),
            )
            cur.execute("SELECT * FROM jt_strategies WHERE id = %s", (strategy_id,))
            strategy = _row(cur.fetchone())

    _add_event(strategy_id, user_wallet, "paper_started", {"paper_min_hours": JT_PAPER_MIN_HOURS})
    return {
        "status": "paper_running",
        "strategy": strategy,
        "message": (
            f"Understanding confirmed. Paper mode running for at least {JT_PAPER_MIN_HOURS:g} hours. "
            "Review recorded trades before enabling live Jupiter spot."
        ),
        "paper_min_hours": JT_PAPER_MIN_HOURS,
        "positions": list_positions(strategy_id),
    }


def _paper_elapsed_hours(strategy: dict[str, Any]) -> float:
    started = strategy.get("paper_started_at")
    if not started:
        return 0.0
    if isinstance(started, str):
        try:
            started_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
        except ValueError:
            return 0.0
    else:
        started_dt = started
    if started_dt.tzinfo is None:
        started_dt = started_dt.replace(tzinfo=timezone.utc)
    return max(0.0, (_now() - started_dt).total_seconds() / 3600.0)


def paper_gate(strategy: dict[str, Any]) -> dict[str, Any]:
    hours = _paper_elapsed_hours(strategy)
    ready = hours >= JT_PAPER_MIN_HOURS and strategy.get("status") in (
        "paper_running",
        "paper_ready",
        "live",
    )
    return {
        "paper_min_hours": JT_PAPER_MIN_HOURS,
        "hours_elapsed": round(hours, 3),
        "hours_remaining": round(max(0.0, JT_PAPER_MIN_HOURS - hours), 3),
        "ready_for_live_confirm": hours >= JT_PAPER_MIN_HOURS and strategy.get("status") in (
            "paper_running",
            "paper_ready",
        ),
        "status": strategy.get("status"),
    }


def evaluate_strategy(strategy_id: str) -> dict[str, Any]:
    strategy = get_strategy(strategy_id)
    if not strategy:
        return {"error": "Strategy not found"}
    status = strategy.get("status")
    if status not in ("paper_running", "paper_ready", "live"):
        return {"strategy_id": strategy_id, "skipped": True, "status": status}

    rules = strategy.get("rules") or {}
    tp = float(rules.get("take_profit_pct") or JT_DEFAULT_TP_PCT)
    sl = float(rules.get("stop_loss_pct") or JT_DEFAULT_SL_PCT)
    user_wallet = strategy["user_wallet"]
    actions: list[dict[str, Any]] = []

    positions = list_positions(strategy_id)
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            for pos in positions:
                entry = float(pos.get("avg_entry_usd") or 0)
                mark = float(pos.get("mark_price_usd") or 0)
                units = float(pos.get("units") or 0)
                if entry <= 0 or mark <= 0 or units <= 0:
                    continue
                pnl_pct = (mark - entry) / entry * 100.0
                hit_tp = pnl_pct >= tp
                hit_sl = pnl_pct <= -sl
                if not (hit_tp or hit_sl):
                    cur.execute(
                        """
                        UPDATE jt_paper_positions
                        SET mark_price_usd = %s, updated_at = NOW()
                        WHERE id = %s
                        """,
                        (mark, pos["id"]),
                    )
                    continue
                reason = f"{'take_profit' if hit_tp else 'stop_loss'} {pnl_pct:.2f}%"
                mode = "live" if status == "live" else "paper"
                if status == "live":
                    live_result = _live_sell_position(strategy, pos)
                    if live_result.get("error"):
                        actions.append({"symbol": pos["symbol"], "error": live_result["error"]})
                        continue
                    actions.append({"symbol": pos["symbol"], "side": "SELL", "live": live_result, "reason": reason})
                else:
                    notional = units * mark
                    cur.execute(
                        """
                        INSERT INTO jt_paper_trades (
                            id, strategy_id, user_wallet, symbol, mint, side, units,
                            price_usd, notional_usd, reason, mode
                        ) VALUES (%s,%s,%s,%s,%s,'SELL',%s,%s,%s,%s,'paper')
                        """,
                        (
                            _new_id("jt"),
                            strategy_id,
                            user_wallet,
                            pos["symbol"],
                            pos.get("mint"),
                            units,
                            mark,
                            notional,
                            reason,
                        ),
                    )
                    cur.execute(
                        "UPDATE jt_paper_positions SET units = 0, mark_price_usd = %s, updated_at = NOW() WHERE id = %s",
                        (mark, pos["id"]),
                    )
                    sol_back = notional / _sol_usd()
                    cur.execute(
                        "UPDATE jt_strategies SET cash_sol = cash_sol + %s, updated_at = NOW() WHERE id = %s",
                        (sol_back, strategy_id),
                    )
                    actions.append({"symbol": pos["symbol"], "side": "SELL", "reason": reason, "mode": mode})

            gate = paper_gate(strategy)
            new_status = status
            if status == "paper_running" and gate["hours_elapsed"] >= JT_PAPER_MIN_HOURS:
                new_status = "paper_ready"
                cur.execute(
                    """
                    UPDATE jt_strategies
                    SET status = 'paper_ready', paper_ready_at = COALESCE(paper_ready_at, NOW()),
                        last_evaluated_at = NOW(), updated_at = NOW()
                    WHERE id = %s
                    """,
                    (strategy_id,),
                )
            else:
                cur.execute(
                    "UPDATE jt_strategies SET last_evaluated_at = NOW(), updated_at = NOW() WHERE id = %s",
                    (strategy_id,),
                )

    refreshed = get_strategy(strategy_id) or strategy
    return {
        "strategy_id": strategy_id,
        "status": refreshed.get("status"),
        "actions": actions,
        "gate": paper_gate(refreshed),
        "positions": list_positions(strategy_id),
    }


def _live_sell_position(strategy: dict[str, Any], pos: dict[str, Any]) -> dict[str, Any]:
    from jupiter_trade_ledger import JT_PLATFORM_FEE_RATE, jt_platform_fee, record_jt_platform_fee
    from jupiter_trade_live import credit_live_sell_proceeds, execute_jt_jupiter_swap

    mint = pos.get("mint")
    units = float(pos.get("units") or 0)
    if not mint or units <= 0:
        return {"error": "Nothing to sell"}
    decimals = int((strategy.get("rules") or {}).get("decimals_map", {}).get(pos["symbol"]) or 6)
    result = execute_jt_jupiter_swap(
        input_mint=mint,
        output_mint=SOL_MINT,
        amount=units,
        input_decimals=decimals,
        user_wallet=strategy["user_wallet"],
    )
    if result.get("error") or result.get("status") != "success":
        return {"error": result.get("error") or "Sell failed", "raw": result}

    notional_usd = float(pos.get("units") or 0) * float(pos.get("mark_price_usd") or 0)
    sol_back = notional_usd / _sol_usd() if notional_usd > 0 else 0.0
    fee_sol = jt_platform_fee(sol_back) if sol_back > 0 else 0.0
    net_sol = max(0.0, sol_back - fee_sol)
    ref = str(result.get("signature") or strategy["id"])
    if fee_sol > 0:
        record_jt_platform_fee(
            strategy["user_wallet"],
            sol_back,
            reference_id=f"fee:{ref}",
            signature=result.get("signature"),
            explorer_url=result.get("explorer_url"),
        )
        result["platform_fee_sol"] = fee_sol
        result["fee_rate"] = JT_PLATFORM_FEE_RATE
    if net_sol > 0:
        credit_live_sell_proceeds(
            strategy["user_wallet"],
            net_sol,
            reference_id=ref,
            signature=result.get("signature"),
            explorer_url=result.get("explorer_url"),
        )

    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO jt_paper_trades (
                    id, strategy_id, user_wallet, symbol, mint, side, units,
                    price_usd, notional_usd, reason, mode, signature, explorer_url
                ) VALUES (%s,%s,%s,%s,%s,'SELL',%s,%s,%s,%s,'live',%s,%s)
                """,
                (
                    _new_id("jt"),
                    strategy["id"],
                    strategy["user_wallet"],
                    pos["symbol"],
                    mint,
                    units,
                    float(pos.get("mark_price_usd") or 0),
                    notional_usd,
                    "live stop/tp · circle",
                    result.get("signature"),
                    result.get("explorer_url"),
                ),
            )
            cur.execute(
                "UPDATE jt_paper_positions SET units = 0, updated_at = NOW() WHERE id = %s",
                (pos["id"],),
            )
            if net_sol > 0:
                cur.execute(
                    "UPDATE jt_strategies SET cash_sol = cash_sol + %s, updated_at = NOW() WHERE id = %s",
                    (net_sol, strategy["id"]),
                )
    return result


def confirm_live(strategy_id: str, user_wallet: str) -> dict[str, Any]:
    strategy = get_strategy(strategy_id, user_wallet)
    if not strategy:
        return {"error": "Strategy not found"}
    gate = paper_gate(strategy)
    if strategy.get("status") not in ("paper_ready", "paper_running"):
        return {"error": f"Live confirm not allowed from status={strategy.get('status')}", "gate": gate}
    if gate["hours_elapsed"] < JT_PAPER_MIN_HOURS:
        return {
            "error": (
                f"Paper mode must run at least {JT_PAPER_MIN_HOURS:g}h before live. "
                f"{gate['hours_remaining']}h remaining."
            ),
            "gate": gate,
            "strategy": strategy,
        }
    if strategy.get("status") == "paper_running":
        # Promote to paper_ready if hours satisfied but monitor hasn't flipped yet.
        init_db()
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE jt_strategies
                    SET status = 'paper_ready', paper_ready_at = COALESCE(paper_ready_at, NOW()), updated_at = NOW()
                    WHERE id = %s
                    """,
                    (strategy_id,),
                )
        strategy = get_strategy(strategy_id, user_wallet) or strategy

    from jupiter_trade_live import deploy_live_from_paper

    deploy = deploy_live_from_paper(strategy)
    if deploy.get("error"):
        return {"error": deploy["error"], "gate": gate, "deploy": deploy}

    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE jt_strategies
                SET status = 'live', live_started_at = NOW(), updated_at = NOW()
                WHERE id = %s AND user_wallet = %s
                RETURNING *
                """,
                (strategy_id, user_wallet),
            )
            strategy = _row(cur.fetchone())
    _add_event(strategy_id, user_wallet, "live_started", {"deploy": deploy})
    return {
        "status": "live",
        "strategy": strategy,
        "deploy": deploy,
        "message": "Live mode enabled. Buys/sells execute on Jupiter spot (not perps).",
        "trades": list_trades(strategy_id, limit=20),
    }


def update_strategy_rules(
    strategy_id: str,
    user_wallet: str,
    *,
    take_profit_pct: Optional[float] = None,
    stop_loss_pct: Optional[float] = None,
    notes: Optional[str] = None,
    reset_to_confirm: bool = True,
) -> dict[str, Any]:
    strategy = get_strategy(strategy_id, user_wallet)
    if not strategy:
        return {"error": "Strategy not found"}
    if strategy.get("status") == "live":
        return {"error": "Pause/close live strategy before changing rules."}

    rules = dict(strategy.get("rules") or {})
    if take_profit_pct is not None:
        rules["take_profit_pct"] = float(take_profit_pct)
    if stop_loss_pct is not None:
        rules["stop_loss_pct"] = float(stop_loss_pct)
    if notes is not None:
        rules["notes"] = notes
    understanding = _build_understanding(
        name=strategy["name"],
        symbols=list(strategy.get("symbols") or []),
        capital_sol=float(strategy.get("capital_sol") or 0),
        take_profit_pct=float(rules.get("take_profit_pct") or JT_DEFAULT_TP_PCT),
        stop_loss_pct=float(rules.get("stop_loss_pct") or JT_DEFAULT_SL_PCT),
        notes=str(rules.get("notes") or ""),
        mint_map=dict(rules.get("mint_map") or {}),
    )
    new_status = "awaiting_confirm" if reset_to_confirm else strategy.get("status")
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE jt_strategies
                SET rules = %s,
                    understanding = %s,
                    status = %s,
                    paper_started_at = CASE WHEN %s THEN NULL ELSE paper_started_at END,
                    paper_ready_at = CASE WHEN %s THEN NULL ELSE paper_ready_at END,
                    updated_at = NOW()
                WHERE id = %s AND user_wallet = %s
                RETURNING *
                """,
                (
                    Json(rules),
                    understanding,
                    new_status,
                    reset_to_confirm,
                    reset_to_confirm,
                    strategy_id,
                    user_wallet,
                ),
            )
            strategy = _row(cur.fetchone())
    _add_event(strategy_id, user_wallet, "rules_updated", {"reset": reset_to_confirm})
    return {
        "strategy": strategy,
        "understanding": understanding,
        "next_step": f"Confirm understanding {strategy_id}" if reset_to_confirm else None,
    }


def close_strategy(strategy_id: str, user_wallet: str) -> dict[str, Any]:
    strategy = get_strategy(strategy_id, user_wallet)
    if not strategy:
        return {"error": "Strategy not found"}
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE jt_strategies SET status = 'closed', updated_at = NOW()
                WHERE id = %s AND user_wallet = %s
                RETURNING *
                """,
                (strategy_id, user_wallet),
            )
            strategy = _row(cur.fetchone())
    _add_event(strategy_id, user_wallet, "closed", {})
    return {"status": "closed", "strategy": strategy}


def dashboard(user_wallet: str) -> dict[str, Any]:
    strategies = list_strategies(user_wallet)
    enriched = []
    for s in strategies:
        item = dict(s)
        item["gate"] = paper_gate(s)
        item["positions"] = list_positions(s["id"]) if s.get("status") != "closed" else []
        item["recent_trades"] = list_trades(s["id"], limit=8)
        enriched.append(item)
    from jupiter_trade_ledger import JT_PLATFORM_FEE_RATE

    return {
        "strategies": enriched,
        "paper_min_hours": JT_PAPER_MIN_HOURS,
        "venue": "jupiter_spot",
        "perps_enabled": False,
        "platform_fee_rate": JT_PLATFORM_FEE_RATE,
        "platform_fee_pct": JT_PLATFORM_FEE_RATE * 100,
    }


def monitor_cycle(force: bool = False) -> dict[str, Any]:
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id FROM jt_strategies
                WHERE status IN ('paper_running', 'paper_ready', 'live')
                ORDER BY updated_at ASC
                LIMIT 50
                """
            )
            ids = [r["id"] for r in cur.fetchall()]
    results = [evaluate_strategy(sid) for sid in ids]
    return {"checked": len(ids), "results": results, "forced": force}


def start_jupiter_trade_scheduler() -> bool:
    global _scheduler_started
    with _scheduler_lock:
        if _scheduler_started:
            return False

        def _loop() -> None:
            while True:
                try:
                    monitor_cycle()
                except Exception as exc:
                    print(f"  ⚠️  Jupiter Trade monitor error: {exc}")
                time.sleep(max(60, JT_MONITOR_INTERVAL_SECONDS))

        threading.Thread(target=_loop, name="jt-monitor", daemon=True).start()
        _scheduler_started = True
        return True


def scheduler_status() -> dict[str, Any]:
    return {
        "started": _scheduler_started,
        "interval_seconds": JT_MONITOR_INTERVAL_SECONDS,
        "paper_min_hours": JT_PAPER_MIN_HOURS,
    }
