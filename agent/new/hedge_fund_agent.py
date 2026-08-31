"""Hedge Fund Agent — Covenant-inspired portfolio agent with 1/10 fees + mock backtests."""

from __future__ import annotations

import json
import os
import re
from calendar import monthrange
from datetime import date, datetime
from typing import Any, Optional

from agent_tool_runner import run_tool_agent
from hosted_llm import CAPIX_MODEL, DEFAULT_LLM_MODEL, call_llm, use_capix
from hedge_fund_core import (
    MANAGEMENT_FEE_RATE,
    PERFORMANCE_FEE_RATE,
    analyze_token_for_portfolio,
    calculate_fees,
    get_fee_structure,
    run_mock_backtest,
    run_portfolio_analysis,
)
from hedge_fund_paper import (
    HF_MAX_STRATEGY_USDC,
    HF_MIN_HORIZON_DAYS,
    HF_MIN_PER_ASSET_USDC,
    HF_MONITOR_INTERVAL_SECONDS,
    add_capital_to_strategy,
    analyze_live_asset,
    confirm_strategy,
    create_strategy,
    liquidate_strategy,
    list_strategies,
    monitor_cycle,
    paper_dashboard,
    run_strategy_backtest,
    strategy_live_pnl,
    update_strategy_rules,
)
from yahoo_market_data import extract_tickers_from_text
from covenant_picker import parse_horizon_days

HEDGE_FUND_MODEL = (
    CAPIX_MODEL
    if use_capix()
    else os.environ.get(
        "HEDGE_FUND_MODEL",
        os.environ.get("DCA_MODEL", os.environ.get("OPEN_ROUTER_MODEL", DEFAULT_LLM_MODEL)),
    )
)

PORTFOLIO_INTENT_RE = re.compile(
    r"\b(portfolio|analyze|analysis|allocate|allocation|hedge|fund|rebalance|positions?)\b",
    re.I,
)

BACKTEST_INTENT_RE = re.compile(
    r"\b(backtest|back\s*test|mock\s*trad|simulate|simulation|"
    r"historical\s*(?:return|performance)|from\s+\w+\s+20\d{2}|start\s+trading|"
    r"allowed\s+to\s+trade|20\d{2}-\d{2}-\d{2})\b",
    re.I,
)

LIVE_PNL_INTENT_RE = re.compile(
    r"\b(pnl|p&l|profit\s*and\s*loss|live\s*pnl|paper\s*pnl|performance|"
    r"how\s+(?:am\s+i|is\s+(?:it|my\s+strategy)\s+)?doing|unrealized)\b",
    re.I,
)

CONFIRM_INTENT_RE = re.compile(
    r"\b(confirm|approve|go\s*ahead|activate|deploy|looks\s*good|proceed|"
    r"yes\s*,?\s*(?:confirm|deploy|activate|go)|confirm\s+hs[a-f0-9]+)\b",
    re.I,
)

STRATEGY_ID_RE = re.compile(r"\b(hs[a-f0-9]{6,12})\b", re.I)

LIQUIDATE_INTENT_RE = re.compile(
    r"\b(liquidate|close\s+strategy|end\s+strategy|sell\s+all|swap\s+to\s+usdc)\b",
    re.I,
)

OPEN_MANDATE_RE = re.compile(
    r"\b(whatever|any\s+assets?|stocks?\s+or\s+crypto|crypto\s+or\s+stocks?|"
    r"only\s+stocks?|stocks?\s+only|only\s+crypto|crypto\s+only|"
    r"allowed\s+to\s+trade|trade\s+whatever|pick\s+(?:the\s+)?(?:best\s+)?(?:assets?|stocks?|crypto)|"
    r"choose\s+(?:the\s+)?(?:assets?|stocks?|crypto)|select\s+(?:your|the)\s+(?:own\s+)?(?:assets?|stocks?)|"
    r"name\s+of\s+assets|you\s+would\s+trade|maximum\s+profits?|max\s+profits?)\b",
    re.I,
)

_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

PAPER_INTENT_RE = re.compile(
    r"\b(paper\s*trad|start\s+(?:a\s+)?(?:paper\s+)?(?:fund|strategy|portfolio)|"
    r"create\s+strategy|monitor|dashboard|tp\b|sl\b|take[\s-]?profit|stop[\s-]?loss|"
    r"my\s+(?:positions|strategy|strategies|trades|decisions))\b",
    re.I,
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_paper_strategy",
            "description": (
                "Propose a LIVE strategy (pending). "
                "If the user does not name tickers (e.g. 'only stocks', 'pick assets', 'max profit'), "
                "OMIT tokens and set mode='agent' so the agent selects the book. "
                "Do NOT pass tokens like STOCKS/CRYPTO — those are not tickers. "
                f"Capital max ${HF_MAX_STRATEGY_USDC:.0f} USDC from deposited USDC. "
                f"Each asset needs at least ${HF_MIN_PER_ASSET_USDC:.0f} capital — e.g. 2 assets need "
                f"${HF_MIN_PER_ASSET_USDC * 2:.0f}+ total, so pick a book size the stated capital "
                "actually supports (fewer assets if capital is small). "
                "If the user states how many assets to pick (e.g. 'only 2 stocks', 'pick 3 tokens'), "
                "set max_names to that exact number. "
                "Put user wording in notes (including 'only stocks'). Confirm before deploy."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tokens": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Real tickers only (AAPL, NVDA…). Omit for agent pick.",
                    },
                    "name": {"type": "string"},
                    "mode": {"type": "string", "description": "agent | user | hybrid"},
                    "max_names": {
                        "type": "number",
                        "description": "Exact number of assets to pick when agent selects (e.g. user said 'only 2 stocks').",
                    },
                    "take_profit_pct": {"type": "number"},
                    "stop_loss_pct": {"type": "number"},
                    "capital_usd": {
                        "type": "number",
                        "description": (
                            f"USDC sleeve, max {HF_MAX_STRATEGY_USDC}. "
                            "Always copy the user's stated amount into notes too; omit here if unsure."
                        ),
                    },
                    "horizon_days": {
                        "type": "number",
                        "description": f"Trading days (min {HF_MIN_HORIZON_DAYS}; omit/0 = open-ended)",
                    },
                    "notes": {"type": "string", "description": "Include 'only stocks' / 'only crypto' when said"},
                    "trading_mode": {"type": "string", "description": "live (default) | paper"},
                    "funding_token": {"type": "string", "description": "USDC only"},
                    "mint_overrides": {
                        "type": "object",
                        "description": "Optional symbol→mint corrections",
                        "additionalProperties": {"type": "string"},
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confirm_paper_strategy",
            "description": (
                "Confirm pending strategy (hs…). Uses the capital sleeve already set when the "
                "strategy was proposed — DO NOT pass capital_usd unless the user explicitly asks "
                "to change the funding amount right now (e.g. 'confirm with $50'). Passing a "
                "capital_usd here OVERRIDES and replaces the strategy's original amount. "
                "Debits deposit ledger, charges 1% start fee, Jupiter-swaps into book "
                f"(max ${HF_MAX_STRATEGY_USDC:.0f}). Optional horizon_days, funding_token, mint_overrides."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "strategy_id": {"type": "string"},
                    "capital_usd": {
                        "type": "number",
                        "description": "ONLY set if the user explicitly wants to change the funding amount now. Omit to keep the strategy's original capital.",
                    },
                    "horizon_days": {
                        "type": "number",
                        "description": f"Optional; min {HF_MIN_HORIZON_DAYS} days if set",
                    },
                    "funding_token": {"type": "string"},
                    "mint_overrides": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                    },
                },
                "required": ["strategy_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_strategy_live_pnl",
            "description": (
                "LIVE mark-to-market PnL for a strategy id (hs…). "
                "Do NOT use mock backtest for this."
            ),
            "parameters": {
                "type": "object",
                "properties": {"strategy_id": {"type": "string"}},
                "required": ["strategy_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "liquidate_paper_strategy",
            "description": (
                "Liquidate strategy: Jupiter swap holdings to USDC, charge 10% of profit only, "
                "credit ledger so user can withdraw."
            ),
            "parameters": {
                "type": "object",
                "properties": {"strategy_id": {"type": "string"}, "reason": {"type": "string"}},
                "required": ["strategy_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "retry_paper_strategy",
            "description": (
                "Retry the on-chain Jupiter buy for legs of a LIVE strategy that never filled "
                "(e.g. an ERROR trade like 'No routes found', RPC timeout). Only touches legs "
                "with no successful buy yet — already-filled legs are untouched, no double charge. "
                "Use `replace` to swap a failed ticker for a different one first, e.g. the user "
                "says 'use PLTR instead of AAPL' -> replace={'AAPL':'PLTR'}. Ask the user before "
                "picking a replacement ticker on their behalf if they only said 'pick something else'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "strategy_id": {"type": "string"},
                    "replace": {
                        "type": "object",
                        "description": "old_ticker -> new_ticker, only for legs that failed",
                        "additionalProperties": {"type": "string"},
                    },
                    "mint_overrides": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                    },
                },
                "required": ["strategy_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_paper_strategy",
            "description": (
                "Edit strategy: TP/SL, symbols, horizon_days "
                f"(min {HF_MIN_HORIZON_DAYS}; 0=open), add_capital_usd "
                f"(extra capital up to ${HF_MAX_STRATEGY_USDC:.0f}), name, status."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "strategy_id": {"type": "string"},
                    "take_profit_pct": {"type": "number"},
                    "stop_loss_pct": {"type": "number"},
                    "tokens": {"type": "array", "items": {"type": "string"}},
                    "name": {"type": "string"},
                    "status": {"type": "string"},
                    "notes": {"type": "string"},
                    "horizon_days": {
                        "type": "number",
                        "description": f"Min {HF_MIN_HORIZON_DAYS} days if set; 0 = open-ended",
                    },
                    "add_capital_usd": {"type": "number"},
                },
                "required": ["strategy_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_live_asset",
            "description": "Realtime Yahoo price + 18-analyst analysis for a stock/crypto ticker.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "equity_usd": {"type": "number"},
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_paper_dashboard",
            "description": (
                "Portfolio dashboard with per-strategy positions; paper trades and live trades "
                "are separate tables (same asset can appear under multiple strategies)."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_strategy_backtest",
            "description": (
                "HISTORICAL mock backtest only (Yahoo). Not for live PnL of an existing strategy — "
                "use get_strategy_live_pnl for that."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {"type": "string"},
                    "strategy_id": {"type": "string"},
                    "tokens": {"type": "array", "items": {"type": "string"}},
                    "capital_usd": {"type": "number"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_mock_backtest",
            "description": (
                "Ad-hoc HISTORICAL simulation only. For live strategy PnL use get_strategy_live_pnl."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tokens": {"type": "array", "items": {"type": "string"}},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "capital_usd": {"type": "number"},
                    "include_news": {"type": "boolean"},
                    "horizon_days": {"type": "number"},
                },
                "required": ["start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_portfolio_analysis",
            "description": "Live Solana on-chain portfolio analysis (legacy path).",
            "parameters": {
                "type": "object",
                "properties": {
                    "tokens": {"type": "array", "items": {"type": "string"}},
                    "capital_usd": {"type": "number"},
                },
                "required": ["tokens"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_token_for_portfolio",
            "description": "Single Solana token analyst signals.",
            "parameters": {
                "type": "object",
                "properties": {"token": {"type": "string"}, "portfolio_value_usd": {"type": "number"}},
                "required": ["token"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_fees",
            "description": "Calculate 1/10 fees.",
            "parameters": {
                "type": "object",
                "properties": {
                    "aum_usd": {"type": "number"},
                    "profit_usd": {"type": "number"},
                    "months": {"type": "number"},
                    "high_water_mark": {"type": "number"},
                },
                "required": ["aum_usd"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_fee_structure",
            "description": "Return the hedge fund 1/10 fee model.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_learning_snapshot",
            "description": (
                "Reinforcement-learning feedback: per-symbol reward learned from realized "
                "round-trip PnL on past paper + live trades. Shows which tickers the agent "
                "has learned to favor/avoid in future asset selection, and why."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def _paper_tools(user_wallet: Optional[str] = None, last_user_input: Optional[str] = None):
    wallet = (user_wallet or "").strip()
    prompt_context = (last_user_input or "").strip()

    def _capital_source_text(notes: str) -> str:
        parts = [p for p in (notes.strip(), prompt_context) if p]
        return "\n".join(parts)

    def create_paper_strategy(**kwargs):
        if not wallet:
            return {"error": "Wallet sign-in required for paper trading"}
        from covenant_picker import filter_real_tickers

        notes = (kwargs.get("notes") or "").strip()
        source_text = _capital_source_text(notes)
        rules = {
            "take_profit_pct": kwargs.get("take_profit_pct", 15),
            "stop_loss_pct": kwargs.get("stop_loss_pct", 8),
            "notes": notes or source_text[:500],
            "objective": "max_profit",
        }
        tokens = filter_real_tickers(kwargs.get("tokens"))
        # mode=agent or empty tokens → agent selects stocks/crypto
        mode = kwargs.get("mode") or ("user" if tokens else "agent")
        if mode == "agent":
            tokens = []
        created_by = "user" if tokens else "agent"
        horizon_days = kwargs.get("horizon_days")
        if horizon_days is None:
            horizon_days = parse_horizon_days(notes or prompt_context)
        capital = kwargs.get("capital_usd")
        if source_text and _capital_explicit_in_text(source_text):
            capital = _extract_capital(source_text)
        elif capital is None and source_text:
            capital = _extract_capital(source_text)
        max_names = kwargs.get("max_names")
        return create_strategy(
            user_wallet=wallet,
            symbols=tokens or None,
            name=kwargs.get("name") or "",
            mode=mode,
            rules=rules,
            capital_usd=capital,
            created_by=created_by,
            horizon_days=int(horizon_days) if horizon_days else None,
            horizon_text=notes,
            require_confirm=True,
            deploy=False,
            trading_mode=(kwargs.get("trading_mode") or "live"),
            funding_token=(kwargs.get("funding_token") or "USDC"),
            mint_overrides=kwargs.get("mint_overrides"),
            max_names=int(max_names) if max_names else None,
        )

    def confirm_paper_strategy(**kwargs):
        if not wallet:
            return {"error": "Wallet sign-in required"}
        cap = kwargs.get("capital_usd")
        hz = kwargs.get("horizon_days")
        return confirm_strategy(
            kwargs.get("strategy_id", ""),
            wallet,
            capital_usd=float(cap) if cap is not None else None,
            horizon_days=int(hz) if hz is not None else None,
            mint_overrides=kwargs.get("mint_overrides"),
            funding_token=kwargs.get("funding_token"),
        )

    def get_strategy_live_pnl(**kwargs):
        if not wallet:
            return {"error": "Wallet sign-in required"}
        return strategy_live_pnl(kwargs.get("strategy_id", ""), wallet)

    def liquidate_paper_strategy(**kwargs):
        if not wallet:
            return {"error": "Wallet sign-in required"}
        return liquidate_strategy(
            kwargs.get("strategy_id", ""),
            wallet,
            reason=kwargs.get("reason") or "User requested liquidation to USDC",
        )

    def retry_paper_strategy(**kwargs):
        if not wallet:
            return {"error": "Wallet sign-in required"}
        from hedge_fund_paper import retry_strategy_deploy

        return retry_strategy_deploy(
            kwargs.get("strategy_id", ""),
            wallet,
            replace=kwargs.get("replace"),
            mint_overrides=kwargs.get("mint_overrides"),
        )

    def update_paper_strategy(**kwargs):
        if not wallet:
            return {"error": "Wallet sign-in required"}
        rules = {}
        if kwargs.get("take_profit_pct") is not None:
            rules["take_profit_pct"] = kwargs["take_profit_pct"]
        if kwargs.get("stop_loss_pct") is not None:
            rules["stop_loss_pct"] = kwargs["stop_loss_pct"]
        if kwargs.get("notes") is not None:
            rules["notes"] = kwargs["notes"]
        return update_strategy_rules(
            strategy_id=kwargs.get("strategy_id", ""),
            user_wallet=wallet,
            rules=rules or None,
            symbols=kwargs.get("tokens"),
            name=kwargs.get("name"),
            status=kwargs.get("status"),
            horizon_days=kwargs.get("horizon_days"),
            add_capital_usd=kwargs.get("add_capital_usd"),
        )

    def analyze_live_asset_tool(**kwargs):
        return analyze_live_asset(
            kwargs.get("symbol") or "",
            equity_usd=float(kwargs.get("equity_usd") or HF_MAX_STRATEGY_USDC),
        )

    def get_paper_dashboard(**_kwargs):
        if not wallet:
            return {"error": "Wallet sign-in required"}
        return paper_dashboard(wallet)

    def run_strategy_backtest_tool(**kwargs):
        if not wallet:
            return {"error": "Wallet sign-in required"}
        cap = float(kwargs.get("capital_usd") or HF_MAX_STRATEGY_USDC)
        return run_strategy_backtest(
            user_wallet=wallet,
            period=kwargs.get("period") or "6m",
            strategy_id=kwargs.get("strategy_id"),
            symbols=kwargs.get("tokens"),
            capital_usd=min(cap, HF_MAX_STRATEGY_USDC),
        )

    def get_learning_snapshot(**_kwargs):
        from hedge_fund_learning import learning_snapshot

        return learning_snapshot()

    return {
        "create_paper_strategy": create_paper_strategy,
        "confirm_paper_strategy": confirm_paper_strategy,
        "get_strategy_live_pnl": get_strategy_live_pnl,
        "liquidate_paper_strategy": liquidate_paper_strategy,
        "retry_paper_strategy": retry_paper_strategy,
        "update_paper_strategy": update_paper_strategy,
        "analyze_live_asset": analyze_live_asset_tool,
        "get_paper_dashboard": get_paper_dashboard,
        "run_strategy_backtest": run_strategy_backtest_tool,
        "run_mock_backtest": run_mock_backtest,
        "run_portfolio_analysis": run_portfolio_analysis,
        "analyze_token_for_portfolio": analyze_token_for_portfolio,
        "calculate_fees": calculate_fees,
        "get_fee_structure": get_fee_structure,
        "get_learning_snapshot": get_learning_snapshot,
    }


TOOL_REGISTRY = _paper_tools()  # default without wallet; run_* rebuilds per request

SYSTEM_PROMPT = f"""You are **Hedge Fund Agent** — LIVE trading by default (real deposits + Jupiter swaps).
Fees: **1% at strategy start** + **10% of profit only on liquidate** (1/10).

Flow:
1. User must deposit **USDC** (not SOL) to the Hedge Fund wallet first.
2. Create strategy in **chat** → `create_paper_strategy` (pending, trading_mode=live).
   - If user says "only stocks" / "pick assets" / "max profit" without tickers:
     omit `tokens`, set mode=agent, put wording in `notes` — agent selects the book.
   - Never pass STOCKS/CRYPTO as tokens.
   - Stocks resolve from hedge-fund-tokens.json; crypto via Jupiter.
   - Show mint addresses; user may correct via mint_overrides.
   - Capital sleeve max **${HF_MAX_STRATEGY_USDC:.0f} USDC**, min **${HF_MIN_PER_ASSET_USDC:.0f}/asset**
     (2 assets needs ${HF_MIN_PER_ASSET_USDC * 2:.0f}+, 3 needs ${HF_MIN_PER_ASSET_USDC * 3:.0f}+, etc.).
   - Trading horizon minimum **{HF_MIN_HORIZON_DAYS} days** (1–2 day requests are raised to {HF_MIN_HORIZON_DAYS}d; omit/0 stays open-ended).
3. Confirm → `confirm_paper_strategy` spends deposit, takes 1% fee, then buys the book
   IN THE BACKGROUND — the tool call returns immediately (does not wait for the Jupiter
   swaps to finish), so relay its `message` as-is; do not imply the buys are already done.
   Each swap can take up to ~2-3 minutes, so tell the user fills land in the Strategies
   tab or via a status check, not instantly.
3.5. When the user asks for status ("status <id>", "did it work", "any fills yet") on a
   live strategy, call `get_strategy_live_pnl` — it reports fills, still-buying legs, and
   any buy errors with the reason. If it shows a buy error (e.g. "No routes found" —
   Jupiter has no liquidity route for that token right now, not a bug), state plainly
   which ticker failed and why, then ask if they want to (a) retry the same ticker,
   (b) swap it for a different one, or (c) leave it unfilled. On their reply, call
   `retry_paper_strategy` directly — do NOT ask them to type "confirm <id>" again or go
   to the Strategies tab, confirm already ran. Pass replace=(old ticker -> new ticker)
   only when they named a replacement ticker. `retry_paper_strategy` also runs in the
   background — its response confirms the retry started, not that it finished.
4. While active, funds are reserved — withdraw only after liquidate/complete.
5. Live PnL → `get_strategy_live_pnl` (never mock backtest for that).
6. Liquidate → swap to USDC, 10% of profit fee, unlock withdraw.
7. Horizon end auto-liquidates to USDC.
8. Paper mode only if user explicitly asks (`trading_mode=paper`).

Monitor every {HF_MONITOR_INTERVAL_SECONDS // 3600}h. Not financial advice.
"""


def _format_live_pnl(pnl: dict[str, Any]) -> str:
    if pnl.get("error"):
        return f"**Live PnL error:** {pnl['error']}"
    capital = pnl.get("capital_usd")
    lines = [
        f"**Live PnL — `{pnl.get('strategy_id')}`** ({pnl.get('trading_mode') or 'live'})",
        f"Status: {pnl.get('status')} · Horizon: "
        + ("open-ended" if not pnl.get("horizon_days") else f"{pnl.get('horizon_days')}d")
        + (f" · ends {str(pnl.get('ends_at') or '')[:10]}" if pnl.get("ends_at") else "")
        + (f" · Sleeve capital: ${_fmt(capital)}" if capital else "")
        + f" · max ${HF_MAX_STRATEGY_USDC:.0f}",
        f"Symbols: {', '.join(pnl.get('symbols') or [])}",
        f"Sleeve value: ${_fmt(pnl.get('sleeve_market_value_usd'))} · "
        f"Cost: ${_fmt(pnl.get('cost_basis_usd'))} · "
        f"**Unrealized PnL: ${_fmt(pnl.get('unrealized_pnl_usd'))} ({pnl.get('unrealized_pnl_pct')}%)**",
    ]
    if pnl.get("trade_counts", {}).get("buys") or pnl.get("trade_counts", {}).get("sells"):
        lines.append(
            f"Realized (approx): ${_fmt(pnl.get('realized_pnl_usd'))}"
            + (
                f" · Liquidation proceeds: ${_fmt(pnl.get('liquidation_proceeds_usd'))}"
                if pnl.get("liquidation_proceeds_usd") is not None
                else ""
            )
        )
    error_trades = [t for t in (pnl.get("trades") or []) if str(t.get("side") or "").upper() == "ERROR"]
    filled_symbols = {t.get("symbol") for t in (pnl.get("trades") or []) if str(t.get("side") or "").upper() == "BUY"}
    still_missing = [s for s in (pnl.get("symbols") or []) if s not in filled_symbols]
    if pnl.get("status") == "active" and not error_trades and still_missing and not pnl.get("positions"):
        lines.append(f"\n⏳ Still buying {', '.join(still_missing)} via Jupiter — no fills yet, check back shortly.")
    if error_trades:
        lines.append("\n⚠️ **Buy errors:**")
        for t in error_trades[:6]:
            lines.append(f"- {t.get('symbol')}: {t.get('reason') or 'buy failed'}")
        lines.append(
            "Reply with a replacement ticker (e.g. \"use PLTR instead of AAPL\") or \"retry "
            f"{pnl.get('strategy_id')}\" to try again."
        )
    lines.extend(["", "**Positions (mark-to-market)**"])
    for p in pnl.get("positions") or []:
        mint = p.get("mint") or "—"
        lines.append(
            f"- **{p.get('symbol')}**: {p.get('units')} @ ${_fmt(p.get('avg_entry_usd'))} → "
            f"${_fmt(p.get('mark_price_usd'))} · PnL ${_fmt(p.get('unrealized_pnl_usd'))} "
            f"({p.get('unrealized_pnl_pct')}%) · mint `{mint}`"
        )
    if not pnl.get("positions"):
        if pnl.get("never_deployed"):
            lines.append("- no open positions — **never deployed** (no buys yet)")
        else:
            lines.append("- no open positions (already liquidated)")
    counts = pnl.get("trade_counts") or {}
    lines.extend(
        [
            "",
            f"Trades: {counts.get('buys', 0)} buys / {counts.get('sells', 0)} sells",
            f"Liquidation target: {pnl.get('liquidation_asset')} (`{pnl.get('liquidation_mint')}`)",
            "",
            "_Live marks — not a mock historical backtest._",
        ]
    )
    if pnl.get("trading_mode") == "live" or pnl.get("note"):
        note = pnl.get("note") or "LIVE Jupiter positions."
        lines[-1] = f"_{note}_"
    if pnl.get("hint"):
        lines.append(f"\n⚠️ {pnl['hint']}")
    elif pnl.get("expired") and pnl.get("status") == "active":
        lines.append("\n⚠️ Horizon expired — say **liquidate " + str(pnl.get("strategy_id")) + "** to close to USDC.")
    return "\n".join(lines)


def _format_strategy_proposal(result: dict[str, Any]) -> str:
    if result.get("error"):
        return f"**Could not propose strategy:** {result['error']}"
    sid = result.get("id") or (result.get("strategy") or {}).get("id")
    trading_mode = (result.get("trading_mode") or "live").strip().lower()
    is_paper = trading_mode == "paper" or bool(result.get("paper"))

    if is_paper:
        banner = (
            "**PAPER strategy** (simulated fills — no real USDC is spent)\n\n"
            "This proposal runs in paper mode only. To trade with **real deposited USDC**, "
            "say **create a live strategy** with the same assets — do not say “propose” or "
            "“confirm” on this paper sleeve.\n"
        )
        confirm_line = f"**Reply `confirm {sid}` to activate this paper strategy** (virtual fills)."
    else:
        banner = (
            "**LIVE strategy** (real USDC — deposit to the Hedge Fund wallet before confirm)\n\n"
            "After you confirm, the agent debits your USDC deposit and executes Jupiter swaps.\n"
        )
        confirm_line = f"**Reply `confirm {sid}` to deploy live Jupiter buys** (after depositing USDC)."

    lines = [
        banner,
        f"**Strategy proposed — awaiting confirmation** `{sid}`",
        f"- Status: `{result.get('status')}` (no fills yet)",
        f"- Mode: {result.get('mode')} · Horizon: "
        + (
            "open-ended (close anytime)"
            if result.get("open_ended") or not result.get("horizon_days")
            else f"{result.get('horizon_days')}d ({result.get('horizon_label')})"
        ),
        f"- Capital sleeve: ${_fmt(result.get('capital_usd'))} USDC "
        f"(max ${_fmt(result.get('max_capital_usd') or HF_MAX_STRATEGY_USDC)})",
        f"- Symbols: {', '.join(result.get('symbols') or [])}",
        f"- Trading: **{trading_mode or 'live'}** · funding: {result.get('funding_token') or 'USDC'}",
    ]
    if is_paper:
        lines.append("- Paper mode: virtual portfolio only (not on-chain)")
    else:
        lines.append("- Deposit USDC to the Hedge Fund wallet before confirm (1% fee on start)")
    lines.extend(
        [
            "",
            "**Solana mints (catalog / Jupiter) — correct before confirm if needed**",
        ]
    )
    for a in result.get("solana_assets") or []:
        lines.append(
            f"- **{a.get('display_symbol') or a.get('symbol')}** → `{a.get('symbol')}` "
            f"mint `{a.get('mint')}`"
            + (" (xStock)" if a.get("is_xstock") else "")
        )
    if not result.get("solana_assets"):
        mint_map = result.get("mint_map") or {}
        if mint_map:
            for sym, mint in mint_map.items():
                lines.append(f"- **{sym}** mint `{mint}`")
        else:
            lines.append("- (mint lookup pending — confirm still allowed; mints resolve on deploy)")
    lines.extend(
        [
            f"- Liquidation: USDC `{result.get('usdc_mint')}` when horizon ends or you close (10% of profit)",
            "",
            confirm_line,
            "Or edit TP/SL / symbols / mint_overrides before confirming.",
        ]
    )
    if result.get("errors"):
        lines.extend(["", "**Warnings**", *[f"- {e}" for e in result["errors"]]])
    return "\n".join(lines)


def _extract_tokens(text: str) -> list[str]:
    """Return Yahoo-eligible tickers / aliases from free text (XRP, S&P500, AAPL, …)."""
    found = extract_tickers_from_text(text)
    # Open mandate with no explicit assets → empty so picker runs
    if not found and OPEN_MANDATE_RE.search(text):
        return []
    return found[:12]


def _capital_explicit_in_text(text: str) -> bool:
    """True when the user named a dollar amount (not just a default sleeve cap)."""
    if not (text or "").strip():
        return False
    markers = (
        r"\$\s*\d",
        r"\b\d+(?:\.\d+)?\s*(?:k|K)?\s*(?:usd|USDC|usdc|dollars?)\b",
        r"\b\d+(?:\.\d+)?(?:usd|USDC|usdc)\b",
        r"\b(?:capital|amount|budget|invest(?:ment)?|allocate|allocat(?:e|ing)|using|with|for)\b.{0,32}\d",
        r"\d.{0,20}\b(?:capital|amount|budget|usd|USDC|usdc|dollars?)\b",
    )
    return any(re.search(p, text, re.I) for p in markers)


def _parse_capital_match(m: re.Match[str], pattern: str) -> Optional[float]:
    raw = m.group(1).replace(",", "")
    try:
        val = float(raw)
    except ValueError:
        return None
    if (
        "$" not in pattern
        and "k" not in pattern.lower()
        and not re.search(r"(?:usd|USDC|usdc|dollar|amount|budget|invest)", pattern, re.I)
    ):
        if 1900 <= val <= 2100:
            return None
    suffix = m.group(2) if m.lastindex and m.lastindex >= 2 and m.group(2) else None
    if suffix and str(suffix).lower() == "k":
        val *= 1000
    return max(1.0, min(HF_MAX_STRATEGY_USDC, val))


def _extract_capital(text: str) -> float:
    """Parse USDC sleeve size from user text; defaults to max when no amount is stated."""
    if not (text or "").strip():
        return float(HF_MAX_STRATEGY_USDC)

    patterns: list[tuple[str, int]] = [
        (r"\b(?:amount|budget|invest(?:ment)?|allocate|allocat(?:e|ing)|using|with|for)\s*(?:to\s+be\s+)?(?:of|=|:)?\s*\$?\s*([\d,]+(?:\.\d+)?)\s*([kK])?\b", 5),
        (r"\$\s*([\d,]+(?:\.\d+)?)\s*([kK])?\b", 4),
        (r"\b([\d,]+(?:\.\d+)?)\s*([kK])\s*(?:usd|USDC|usdc|dollars?)?\b", 4),
        (r"\b([\d,]+(?:\.\d+)?)\s*(?:usd|USDC|usdc|dollars?)\b", 4),
        (r"\b([\d,]+(?:\.\d+)?)(?:usd|USDC|usdc)\b", 4),
        (r"\b(?:capital|aum|portfolio)\s*(?:of|=|:)?\s*\$?\s*([\d,]+(?:\.\d+)?)\s*([kK])?\b", 3),
    ]

    best_val: Optional[float] = None
    best_score = -1
    for pattern, priority in patterns:
        for m in re.finditer(pattern, text, re.I):
            val = _parse_capital_match(m, pattern)
            if val is None:
                continue
            score = priority * 10_000 - m.start()
            if score > best_score:
                best_score = score
                best_val = val

    if best_val is not None:
        return best_val
    return float(HF_MAX_STRATEGY_USDC)


def _parse_month_year(text: str) -> Optional[date]:
    m = re.search(
        r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
        r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
        r"\s+(\d{4})\b",
        text,
        re.I,
    )
    if not m:
        return None
    month = _MONTHS[m.group(1).lower()]
    year = int(m.group(2))
    return date(year, month, 1)


def _extract_date_range(text: str) -> tuple[str, str]:
    """Return (start_yyyy_mm_dd, end_yyyy_mm_dd)."""
    iso = re.findall(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
    if len(iso) >= 2:
        return iso[0], iso[1]

    # "from Dec 2025" / "today is Apr 2026"
    start = None
    end = None
    from_m = re.search(
        r"\b(?:from|starting|start(?:ing)?\s+(?:trading\s+)?(?:on|in)?|since)\s+"
        r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
        r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
        r"\s+(\d{4})\b",
        text,
        re.I,
    )
    if from_m:
        month = _MONTHS[from_m.group(1).lower()]
        year = int(from_m.group(2))
        start = date(year, month, 1)

    today_m = re.search(
        r"\b(?:today\s+is|until|through|to|ending|end(?:ing)?\s+(?:on|in)?)\s+"
        r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
        r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
        r"\s+(\d{4})\b",
        text,
        re.I,
    )
    if today_m:
        month = _MONTHS[today_m.group(1).lower()]
        year = int(today_m.group(2))
        last = monthrange(year, month)[1]
        end = date(year, month, last)

    months_found = re.findall(
        r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
        r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
        r"\s+(\d{4})\b",
        text,
        re.I,
    )
    if not start and months_found:
        month = _MONTHS[months_found[0][0].lower()]
        year = int(months_found[0][1])
        start = date(year, month, 1)
    if not end and len(months_found) >= 2:
        month = _MONTHS[months_found[-1][0].lower()]
        year = int(months_found[-1][1])
        last = monthrange(year, month)[1]
        end = date(year, month, last)

    if not start:
        start = date(2025, 12, 1)
    if not end:
        # Prefer "today" if provided in prompt context; else use calendar today
        end = date.today()
        if end <= start:
            end = date(start.year, start.month, monthrange(start.year, start.month)[1])

    if end <= start:
        last = monthrange(end.year, end.month)[1]
        end = date(end.year, end.month, last)
        if end <= start:
            end = date(start.year + 1, start.month, min(start.day, monthrange(start.year + 1, start.month)[1]))

    return start.isoformat(), end.isoformat()


def _generate_macro_analysis(analysis: dict[str, Any]) -> str:
    try:
        response = call_llm(
            [
                {
                    "role": "system",
                    "content": (
                        "You are the macro/portfolio manager layer of a Covenant-governed hedge fund. "
                        "Given JSON portfolio analysis (deterministic analyst signals already computed), "
                        "write a concise **Portfolio Analysis** with: Thesis, Overweights, Risks, Fee impact (1/10 model), Verdict. "
                        "Use ONLY data from the JSON. Under 300 words. Not financial advice."
                    ),
                },
                {"role": "user", "content": json.dumps(analysis, indent=2, default=str)[:12000]},
            ],
            model=HEDGE_FUND_MODEL,
            temperature=0.35,
            app_suffix="Hedge Fund Analysis",
        )
        return ((response.get("message") or {}).get("content") or "").strip()
    except Exception as exc:
        return f"_Macro analysis unavailable ({exc}). Review deterministic signals above._"


def _format_portfolio_reply(analysis: dict[str, Any], macro: str = "") -> str:
    lines = [
        "**Covenant Hedge Fund — Portfolio Report**",
        f"Capital: ${_fmt(analysis.get('capital_usd', 0))} · Tokens analyzed: {analysis.get('tokens_analyzed', 0)}",
        "",
    ]
    summary = analysis.get("portfolio_summary") or {}
    lines.extend(
        [
            "**Portfolio summary**",
            f"- Suggested deployment: ${_fmt(summary.get('total_suggested_allocation_usd', 0))} ({summary.get('deployment_pct', 0)}%)",
            f"- Cash reserve: ${_fmt(summary.get('cash_remaining_usd', 0))}",
            f"- Overweight candidates: {', '.join(summary.get('overweight_candidates') or []) or 'none'}",
            f"- Underweight / avoid: {', '.join(summary.get('underweight_avoid') or []) or 'none'}",
            "",
        ]
    )

    for pos in analysis.get("positions") or []:
        syn = pos.get("synthesis") or {}
        lines.append(
            f"**{pos.get('token')}** → {syn.get('action', 'hold').upper()} "
            f"(score {syn.get('composite_score', 0)}, conf {syn.get('confidence', 0)}%) "
            f"· suggest ${_fmt(pos.get('suggested_allocation_usd', 0))}"
        )
        for sig in pos.get("analyst_signals") or []:
            lines.append(f"  - {sig.get('analyst')}: {sig.get('signal')} — {sig.get('reasoning')}")
        lines.append("")

    fees = analysis.get("fee_structure") or {}
    lines.extend(
        [
            "**Fee model (1/10)**",
            f"- {fees.get('management_fee_annual_pct', 1)}% annual management · "
            f"{fees.get('performance_fee_pct', 10)}% performance above high-water mark",
            f"- Traditional 2/20: {fees.get('traditional_2_20', {})}",
            "",
        ]
    )

    if analysis.get("errors"):
        lines.extend(["**Warnings**", *[f"- {e}" for e in analysis["errors"]], ""])

    if macro:
        lines.extend(["---", "", "**Portfolio Analysis**", "", macro, "", "Not financial advice. DYOR."])
    else:
        lines.append("Not financial advice. DYOR.")

    return "\n".join(lines)


def _format_backtest_reply(result: dict[str, Any]) -> str:
    if result.get("error"):
        lines = [f"**Backtest failed:** {result.get('error')}"]
        for e in result.get("errors") or []:
            lines.append(f"- {e}")
        if result.get("hint"):
            lines.append(f"\n_{result['hint']}_")
        return "\n".join(lines)

    fees = result.get("fees") or {}
    counts = result.get("trade_counts") or {}
    lines = [
        "**Hedge Fund — Mock Backtest / PnL Report**",
        f"Window: `{result.get('start_date')}` → `{result.get('end_date')}`",
        f"Strategy: equal-weight + quarterly rebalance · Capital: ${_fmt(result.get('capital_usd', 0))}",
        f"Book: {', '.join(result.get('selected_assets') or [])}",
        f"Note: {result.get('strategy_note') or 'Yahoo Finance simulation'}",
        f"Data: {result.get('data_source')}",
        "",
        "**Allocations (initial)**",
    ]
    for row in result.get("allocations") or []:
        lines.append(
            f"- **{row.get('symbol')}**: {row.get('allocation_pct')}% · ${_fmt(row.get('allocation_usd'))}"
        )

    lines.extend(
        [
            "",
            "**Trade activity**",
            f"- Buys: {counts.get('buys', 0)}",
            f"- Sells: {counts.get('sells', 0)}",
            f"- Total fills: {counts.get('total', 0)}",
            "",
            "**Portfolio PnL**",
            f"- End value: ${_fmt(result.get('end_value_usd', 0))}",
            f"- Gross PnL: ${_fmt(result.get('gross_pnl_usd', 0))} ({result.get('gross_pnl_pct', 0)}%)",
            f"- Fees (1/10): mgmt ${_fmt(fees.get('management_fee_usd', 0))} · "
            f"perf ${_fmt(fees.get('performance_fee_usd', 0))} · "
            f"total ${_fmt(fees.get('total_fees_usd', 0))}",
            f"- Net PnL after fees: ${_fmt(result.get('net_pnl_usd', 0))} ({result.get('net_pnl_pct', 0)}%)",
            "",
            "**Risk / benchmark (SPY)**",
        ]
    )
    metrics = result.get("metrics") or {}
    if metrics and not metrics.get("error"):
        lines.extend(
            [
                f"- Sharpe: {metrics.get('sharpe')} · Sortino: {metrics.get('sortino')}",
                f"- Max drawdown: {metrics.get('max_drawdown_pct')}%",
                f"- SPY return: {metrics.get('spy_return_pct')}% · Alpha vs SPY: {metrics.get('alpha_vs_spy_pct')}%",
                f"- Beta vs SPY: {metrics.get('beta_vs_spy')}",
                "",
                "**Positions**",
            ]
        )
    else:
        lines.append("**Positions**")
    for pos in result.get("positions") or []:
        lines.append(
            f"- **{pos.get('symbol')}** ({pos.get('asset_class') or 'asset'}): "
            f"${_fmt(pos.get('allocation_usd'))} @ ${_fmt(pos.get('entry_price_usd'))} "
            f"→ ${_fmt(pos.get('exit_price_usd'))} · end ${_fmt(pos.get('end_value_usd'))} · "
            f"PnL ${_fmt(pos.get('pnl_usd'))} ({pos.get('pnl_pct')}%)"
        )

    marks = result.get("monthly_marks") or []
    if marks:
        lines.extend(["", "**Monthly marks**"])
        for m in marks[-8:]:
            lines.append(
                f"- {m.get('date')}: value ${_fmt(m.get('portfolio_value_usd'))} · PnL ${_fmt(m.get('pnl_usd'))}"
            )

    trades = [t for t in (result.get("mock_trades") or []) if t.get("side") in ("BUY", "SELL")]
    if trades:
        lines.extend(["", "**Mock trades (sample)**"])
        for t in trades[:20]:
            lines.append(
                f"- {t.get('date')} {t.get('side')} {t.get('symbol')} · "
                f"${_fmt(t.get('notional_usd'))}"
                + (f" @ ${_fmt(t.get('price_usd'))}" if t.get("price_usd") is not None else "")
                + (f" — {t.get('note')}" if t.get("note") else "")
            )
        if len(trades) > 20:
            lines.append(f"- …and {len(trades) - 20} more fills")

    news = result.get("news") or []
    if news:
        lines.extend(["", "**Yahoo Finance news (recent)**"])
        for n in news[:10]:
            lines.append(f"- [{n.get('symbol')}] {n.get('title')} _{n.get('publisher')}_")

    if result.get("errors"):
        lines.extend(["", "**Warnings**", *[f"- {e}" for e in result["errors"]]])

    lines.extend(["", result.get("disclaimer") or "Mock simulation only. Not financial advice. DYOR."])
    return "\n".join(lines)


def _fmt(value: Any) -> str:
    try:
        if value is None or value == "":
            return "0.00"
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(v) >= 1_000_000:
        return f"{v:,.0f}"
    if abs(v) >= 1000:
        return f"{v:,.2f}"
    if abs(v) >= 1:
        return f"{v:.2f}"
    return f"{v:.6g}"


def _try_backtest_shortcut(user_input: str) -> Optional[tuple[str, list[dict[str, Any]]]]:
    # Mock historical only — never for live strategy-id PnL, and not for open-mandate picks
    if STRATEGY_ID_RE.search(user_input) and LIVE_PNL_INTENT_RE.search(user_input):
        return None
    if not BACKTEST_INTENT_RE.search(user_input):
        # Still allow pure ISO date-range historical asks
        if not re.search(r"20\d{2}-\d{2}-\d{2}.*20\d{2}-\d{2}-\d{2}", user_input):
            return None
    tokens = _extract_tokens(user_input)
    # Empty tokens => default diversified Yahoo book inside run_mock_backtest
    capital = _extract_capital(user_input)
    start_date, end_date = _extract_date_range(user_input)
    result = run_mock_backtest(
        tokens or None,
        start_date=start_date,
        end_date=end_date,
        capital_usd=capital,
        include_news=True,
    )
    reply = _format_backtest_reply(result)
    actions = [
        {
            "tool": "run_mock_backtest",
            "args": {
                "tokens": tokens or result.get("selected_assets") or [],
                "start_date": start_date,
                "end_date": end_date,
                "capital_usd": capital,
            },
            "result": json.dumps(result, indent=2, default=str),
        }
    ]
    return reply, actions


def _try_portfolio_shortcut(user_input: str) -> Optional[tuple[str, list[dict[str, Any]]]]:
    tokens = _extract_tokens(user_input)
    if not tokens:
        return None
    if not PORTFOLIO_INTENT_RE.search(user_input) and len(tokens) < 2:
        return None

    capital = _extract_capital(user_input)
    analysis = run_portfolio_analysis(tokens, capital_usd=capital)
    macro = _generate_macro_analysis(analysis)
    reply = _format_portfolio_reply(analysis, macro)
    actions = [
        {
            "tool": "run_portfolio_analysis",
            "args": {"tokens": tokens, "capital_usd": capital},
            "result": json.dumps(analysis, indent=2, default=str),
        }
    ]
    return reply, actions


def _extract_tp_sl(text: str) -> tuple[Optional[float], Optional[float]]:
    tp = None
    sl = None
    m_tp = re.search(r"\b(?:tp|take[\s-]?profit)\s*[:=]?\s*(-?\d+(?:\.\d+)?)\s*%?", text, re.I)
    m_sl = re.search(r"\b(?:sl|stop[\s-]?loss)\s*[:=]?\s*(-?\d+(?:\.\d+)?)\s*%?", text, re.I)
    if m_tp:
        try:
            tp = abs(float(m_tp.group(1)))
        except ValueError:
            pass
    if m_sl:
        try:
            sl = abs(float(m_sl.group(1)))
        except ValueError:
            pass
    return tp, sl


def _format_paper_dashboard(dash: dict[str, Any]) -> str:
    if dash.get("error"):
        return f"**Paper dashboard error:** {dash['error']}"
    port = dash.get("portfolio") or {}
    lines = [
        "**Paper Trading Dashboard**",
        f"Mode: paper · Covenant 18-analyst · Monitor every {HF_MONITOR_INTERVAL_SECONDS // 3600}h",
        f"Cash: ${_fmt(port.get('cash_usd'))} · Equity: ${_fmt(port.get('equity_usd'))} · "
        f"PnL: ${_fmt(port.get('pnl_usd') or port.get('unrealized_pnl_usd'))} "
        f"({port.get('pnl_pct', 0)}%)",
        "",
        "**Strategies**",
    ]
    for s in dash.get("strategies") or []:
        rules = s.get("rules") or {}
        lines.append(
            f"- `{s.get('id')}` **{s.get('name')}** [{s.get('mode')}/{s.get('status')}] "
            f"· horizon {s.get('horizon_days') or rules.get('horizon_days') or '?'}d "
            f"· {', '.join(s.get('symbols') or [])} "
            f"· TP {rules.get('take_profit_pct')}% / SL {rules.get('stop_loss_pct')}%"
        )
    overlap = dash.get("overlapping_assets") or {}
    if overlap:
        lines.append("")
        lines.append("**Overlapping assets (multi-strategy)**")
        for sym, sids in overlap.items():
            lines.append(f"- **{sym}** in strategies: {', '.join(sids)}")

    lines.append("")
    lines.append("**Positions by strategy**")
    by_strategy = dash.get("by_strategy") or []
    if by_strategy:
        for block in by_strategy:
            st = block.get("strategy") or {}
            lines.append(
                f"### `{st.get('id')}` {st.get('name')} · sleeve ${_fmt(block.get('sleeve_value_usd'))}"
            )
            positions = block.get("positions") or []
            if not positions:
                lines.append("- no open positions")
            for p in positions:
                lines.append(
                    f"- **{p.get('symbol')}**: {p.get('units')} @ ${_fmt(p.get('avg_entry_usd'))} "
                    f"· mkt ${_fmt(p.get('mark_price_usd'))} · PnL ${_fmt(p.get('unrealized_pnl_usd'))}"
                )
            for d in (block.get("decisions") or [])[:4]:
                lines.append(
                    f"  · decision `{d.get('action')}` {d.get('symbol')} — {(d.get('rationale') or '')[:100]}"
                )
    else:
        lines.append("")
        lines.append("**Positions**")
        positions = port.get("positions") or dash.get("positions") or []
        if not positions:
            lines.append("- none yet (monitor will allocate on next cycle)")
        for p in positions:
            lines.append(
                f"- **{p.get('symbol')}** {p.get('side') or 'long'}: "
                f"{p.get('units') or p.get('qty')} @ ${_fmt(p.get('avg_entry_usd') or p.get('avg_price_usd'))} "
                f"· mkt ${_fmt(p.get('mark_price_usd') or p.get('mark_usd'))} · "
                f"PnL ${_fmt(p.get('unrealized_pnl_usd'))}"
            )
    lines.extend(["", "**Recent decisions**"])
    for d in (dash.get("decisions") or [])[:8]:
        lines.append(
            f"- {str(d.get('created_at', ''))[:16]} `{d.get('action')}` "
            f"{d.get('symbol') or ''} [{d.get('strategy_id')}] — {d.get('rationale') or ''}"
        )
    lines.append("\nAsk me to create/update strategies, run a backtest (1w/6m/1y), or edit TP/SL.")
    return "\n".join(lines)


def _try_paper_shortcut(
    user_input: str, user_wallet: Optional[str]
) -> Optional[tuple[str, list[dict[str, Any]]]]:
    sid_m = STRATEGY_ID_RE.search(user_input)
    strategy_id = sid_m.group(1).lower() if sid_m else None

    # Live PnL for strategy id — highest priority (never mock backtest)
    if strategy_id and LIVE_PNL_INTENT_RE.search(user_input) and not re.search(r"\bbacktest\b", user_input, re.I):
        if not user_wallet:
            return ("Sign in with your wallet to view live strategy PnL.", [])
        pnl = strategy_live_pnl(strategy_id, user_wallet)
        return _format_live_pnl(pnl), [
            {"tool": "get_strategy_live_pnl", "args": {"strategy_id": strategy_id}, "result": json.dumps(pnl, default=str)}
        ]

    # Confirm pending strategy
    if CONFIRM_INTENT_RE.search(user_input):
        if not user_wallet:
            return ("Sign in to confirm a strategy.", [])
        sid = strategy_id
        if not sid:
            pending = [s for s in list_strategies(user_wallet) if s.get("status") == "pending"]
            sid = pending[0]["id"] if pending else None
        if not sid:
            return ("No pending strategy to confirm. Create one first.", [])
        capital_kw = re.search(r"\$|\busd\b|\bcapital\b|\baum\b", user_input, re.I)
        hz = parse_horizon_days(user_input, None)
        # Only override horizon if user mentioned a duration / open-ended phrase
        hz_kw = re.search(
            r"\b(\d+\s*(?:day|days|week|weeks|month|months|year|years)|open[- ]?ended|no\s+horizon|indefinite)\b",
            user_input,
            re.I,
        )
        result = confirm_strategy(
            sid,
            user_wallet,
            capital_usd=_extract_capital(user_input) if capital_kw else None,
            horizon_days=hz if hz_kw else None,
        )
        if result.get("error"):
            return f"**Confirm failed:** {result['error']}", [
                {"tool": "confirm_paper_strategy", "args": {"strategy_id": sid}, "result": json.dumps(result, default=str)}
            ]
        try:
            monitor_cycle(force_prices=False)
        except Exception:
            pass
        hz_note = (
            "Open-ended — liquidate anytime"
            if result.get("open_ended") or not result.get("horizon_days")
            else f"Horizon {result.get('horizon_days')}d — auto-liquidate at end or liquidate early"
        )
        reply = (
            f"**Confirmed & deployed** `{sid}`\n"
            f"- Paper sleeve ${_fmt(result.get('capital_usd'))} (max ${HF_MAX_STRATEGY_USDC:.0f})\n"
            f"- Assets: {', '.join(result.get('symbols') or [])}\n"
            f"- {hz_note}\n\n"
            + _format_live_pnl(strategy_live_pnl(sid, user_wallet))
        )
        return reply, [
            {"tool": "confirm_paper_strategy", "args": {"strategy_id": sid}, "result": json.dumps(result, default=str)}
        ]

    # Liquidate
    if LIQUIDATE_INTENT_RE.search(user_input):
        if not user_wallet:
            return ("Sign in to liquidate.", [])
        sid = strategy_id
        if not sid:
            active = [s for s in list_strategies(user_wallet) if s.get("status") == "active"]
            sid = active[0]["id"] if active else None
        if not sid:
            return ("No active strategy to liquidate.", [])
        result = liquidate_strategy(sid, user_wallet)
        return (
            result.get("message") or json.dumps(result, default=str),
            [{"tool": "liquidate_paper_strategy", "args": {"strategy_id": sid}, "result": json.dumps(result, default=str)}],
        )

    # Strategy id alone / "status of hs…" → live pnl
    if strategy_id and re.search(r"\b(status|show|for|of)\b", user_input, re.I):
        if not user_wallet:
            return ("Sign in with your wallet.", [])
        pnl = strategy_live_pnl(strategy_id, user_wallet)
        return _format_live_pnl(pnl), [
            {"tool": "get_strategy_live_pnl", "args": {"strategy_id": strategy_id}, "result": json.dumps(pnl, default=str)}
        ]

    if (
        not PAPER_INTENT_RE.search(user_input)
        and not re.search(r"\b(create|start).{0,20}(paper|strategy|fund)\b", user_input, re.I)
        and not OPEN_MANDATE_RE.search(user_input)
        and not CONFIRM_INTENT_RE.search(user_input)
        and not LIQUIDATE_INTENT_RE.search(user_input)
        and not (strategy_id and LIVE_PNL_INTENT_RE.search(user_input))
    ):
        return None
    if not user_wallet:
        return (
            "Sign in with your wallet to use paper trading (strategies are saved per wallet).",
            [],
        )

    # Dashboard
    if re.search(r"\b(dashboard|positions|decisions|my\s+strateg|monitor\s+status)\b", user_input, re.I):
        dash = paper_dashboard(user_wallet)
        return _format_paper_dashboard(dash), [
            {"tool": "get_paper_dashboard", "args": {}, "result": json.dumps(dash, default=str)}
        ]

    # Explicit historical backtest only
    period_m = re.search(r"\b(1w|1m|3m|6m|1y|1\s*week|1\s*month|6\s*months?|1\s*year)\b", user_input, re.I)
    if period_m and re.search(r"\bbacktest\b", user_input, re.I):
        raw = period_m.group(1).lower().replace(" ", "")
        period_map = {
            "1week": "1w",
            "1month": "1m",
            "6month": "6m",
            "6months": "6m",
            "1year": "1y",
        }
        period = period_map.get(raw, raw if raw in ("1w", "1m", "3m", "6m", "1y") else "6m")
        tokens = _extract_tokens(user_input)
        result = run_strategy_backtest(
            user_wallet=user_wallet,
            period=period,
            strategy_id=strategy_id,
            symbols=tokens or None,
            capital_usd=_extract_capital(user_input),
        )
        bt = result.get("result") or result
        reply = _format_backtest_reply(bt if isinstance(bt, dict) else result)
        return reply, [
            {
                "tool": "run_strategy_backtest",
                "args": {"period": period, "tokens": tokens, "strategy_id": strategy_id},
                "result": json.dumps(result, default=str),
            }
        ]

    # Propose strategy (pending confirm)
    if re.search(r"\b(create|start|new|set\s*up|propose)\b", user_input, re.I) or OPEN_MANDATE_RE.search(
        user_input
    ):
        from covenant_picker import filter_real_tickers

        tokens = filter_real_tickers(_extract_tokens(user_input))
        # "only stocks" / open mandate → force agent pick even if junk tickers leaked
        if OPEN_MANDATE_RE.search(user_input) and (
            not tokens
            or re.search(r"\b(only\s+stocks?|stocks?\s+only|pick|choose|select)\b", user_input, re.I)
        ):
            tokens = []
        tp, sl = _extract_tp_sl(user_input)
        rules = {
            "take_profit_pct": tp if tp is not None else 15,
            "stop_loss_pct": sl if sl is not None else 8,
            "objective": "max_profit",
            "notes": user_input[:500],
        }
        created_by = "user" if tokens else "agent"
        mode = "user" if tokens else "agent"
        result = create_strategy(
            user_wallet=user_wallet,
            symbols=tokens or None,
            name="",
            mode=mode,
            rules=rules,
            capital_usd=_extract_capital(user_input),
            created_by=created_by,
            horizon_days=parse_horizon_days(user_input),
            horizon_text=user_input,
            require_confirm=True,
            deploy=False,
            trading_mode="live",
            funding_token="USDC",
        )
        if result.get("error"):
            return f"**Could not propose strategy:** {result['error']}", [
                {"tool": "create_paper_strategy", "args": {}, "result": json.dumps(result, default=str)}
            ]
        reply = _format_strategy_proposal(result)
        if rules:
            reply += f"\n- TP {rules['take_profit_pct']}% / SL {rules['stop_loss_pct']}%"
        return reply, [
            {
                "tool": "create_paper_strategy",
                "args": {"tokens": tokens, "mode": mode},
                "result": json.dumps(result, default=str),
            }
        ]

    # Update TP/SL / horizon / add capital
    if re.search(
        r"\b(update|edit|change|set|add)\b.*\b(tp|sl|take|stop|strategy|horizon|duration|capital)\b",
        user_input,
        re.I,
    ) or re.search(r"\badd\s+(?:more\s+)?(?:capital|\$|\d)", user_input, re.I):
        strategies = list_strategies(user_wallet)
        if not strategies:
            return "No strategies yet — say e.g. `create paper strategy with BTC ETH TP 20 SL 10`.", []
        sid = strategy_id or strategies[0].get("id")
        tp, sl = _extract_tp_sl(user_input)
        rules = {}
        if tp is not None:
            rules["take_profit_pct"] = tp
        if sl is not None:
            rules["stop_loss_pct"] = sl
        hz_kw = re.search(
            r"\b(\d+\s*(?:day|days|week|weeks|month|months|year|years)|open[- ]?ended|no\s+horizon)\b",
            user_input,
            re.I,
        )
        horizon_days = parse_horizon_days(user_input, None) if hz_kw else None
        if hz_kw and re.search(r"open[- ]?ended|no\s+horizon", user_input, re.I):
            horizon_days = 0
        add_cap = None
        if re.search(r"\badd\b.*\b(capital|usd|\$)|more\s+capital", user_input, re.I) or (
            re.search(r"\$|\busd\b", user_input, re.I) and re.search(r"\badd\b", user_input, re.I)
        ):
            add_cap = _extract_capital(user_input)
        if not rules and horizon_days is None and add_cap is None:
            return "Specify TP/SL, horizon (e.g. `set horizon 30 days`), or `add capital $25`.", []
        result = update_strategy_rules(
            strategy_id=sid,
            user_wallet=user_wallet,
            rules=rules or None,
            horizon_days=horizon_days,
            add_capital_usd=add_cap,
        )
        msg = f"**Updated** `{sid}`"
        if rules:
            msg += f" · rules {rules}"
        if horizon_days is not None:
            msg += f" · horizon {'open' if horizon_days == 0 else str(horizon_days) + 'd'}"
        if result.get("add_capital"):
            msg += f" · {result['add_capital'].get('message') or result['add_capital']}"
        return (
            msg + "\n\n" + _format_paper_dashboard(paper_dashboard(user_wallet)),
            [{"tool": "update_paper_strategy", "args": {"strategy_id": sid}, "result": json.dumps(result, default=str)}],
        )

    if PAPER_INTENT_RE.search(user_input):
        dash = paper_dashboard(user_wallet)
        return _format_paper_dashboard(dash), [
            {"tool": "get_paper_dashboard", "args": {}, "result": json.dumps(dash, default=str)}
        ]
    return None


def _format_live_analysis(data: dict[str, Any]) -> str:
    if data.get("error"):
        return f"**Analysis error:** {data['error']}"
    a = data.get("analysis") or {}
    if a.get("error"):
        return f"**Analysis error:** {a['error']}"
    synth = a.get("synthesis") or {}
    lines = [
        f"**Live analysis — {data.get('symbol') or a.get('symbol')}**",
        f"Price: ${_fmt(data.get('live_price_usd') or (a.get('features') or {}).get('last'))}"
        + (f" · 24h {data.get('change_24h_pct')}%" if data.get("change_24h_pct") is not None else ""),
        f"Action: **{synth.get('action', 'n/a')}** · confidence {synth.get('confidence', '—')}",
        f"Asset class: {a.get('asset_class') or '—'}",
    ]
    sol = data.get("solana") or {}
    if sol.get("mint"):
        lines.append(
            f"Solana mint: `{sol.get('mint')}`"
            + (" (xStock)" if sol.get("is_xstock") else "")
        )
    feats = a.get("features") or {}
    if feats:
        lines.append(
            f"Features: ret_5d {feats.get('ret_5d')} · ret_21d {feats.get('ret_21d')} · "
            f"vol {feats.get('vol_21d')}"
        )
    lines.append("\n_Paper mode · live Yahoo marks · not financial advice._")
    return "\n".join(lines)


def run_hedge_fund_agent(
    user_input: str,
    conversation_history: list,
    user_wallet: Optional[str] = None,
    session_id: Optional[str] = None,
) -> tuple[str, list, list[dict[str, Any]]]:
    prompt = user_input.strip()
    tools = _paper_tools(user_wallet, last_user_input=prompt)

    if re.search(r"\b(fee|fees|pricing|1/10|2/20|management fee|performance fee)\b", prompt, re.I):
        if not BACKTEST_INTENT_RE.search(prompt) and not re.search(r"\b(BTC|ETH|SOL|backtest|mock)\b", prompt, re.I):
            fees = get_fee_structure()
            reply = (
                "**Hedge Fund Fee Structure (1/10 model)**\n\n"
                f"- **Management:** {fees['management_fee_annual_pct']}% per year on AUM\n"
                f"- **Performance:** {fees['performance_fee_pct']}% of net profits above high-water mark\n"
                f"- **vs 2/20:** traditional funds charge 2% + 20%\n\n"
                f"Example on $100k with $15k profit (12 mo): "
                f"mgmt ${fees['example_100k_12mo']['management_fee_usd']:,.2f}, "
                f"perf ${fees['example_100k_12mo']['performance_fee_usd']:,.2f}, "
                f"total ${fees['example_100k_12mo']['total_fees_usd']:,.2f}\n\n"
                "See `/agents/hedge-fund/pricing` for full details."
            )
            conversation_history.append({"role": "user", "content": prompt})
            conversation_history.append({"role": "assistant", "content": reply})
            return reply, conversation_history, [{"tool": "get_fee_structure", "args": {}, "result": json.dumps(fees)}]

    # Live PnL / confirm / liquidate / propose — before any mock backtest
    paper = _try_paper_shortcut(prompt, user_wallet)
    if paper:
        reply, actions = paper
        conversation_history.append({"role": "user", "content": prompt})
        conversation_history.append({"role": "assistant", "content": reply})
        return reply, conversation_history, actions

    # Analyze ticker with live marks (before portfolio / backtest)
    if re.search(r"\b(analy[sz]e|analysis|research|what\s+about)\b", prompt, re.I) and not STRATEGY_ID_RE.search(prompt):
        tokens = _extract_tokens(prompt)
        if tokens:
            data = analyze_live_asset(tokens[0], equity_usd=HF_MAX_STRATEGY_USDC)
            reply = _format_live_analysis(data)
            if len(tokens) > 1:
                for t in tokens[1:4]:
                    reply += "\n\n" + _format_live_analysis(analyze_live_asset(t, equity_usd=HF_MAX_STRATEGY_USDC))
            conversation_history.append({"role": "user", "content": prompt})
            conversation_history.append({"role": "assistant", "content": reply})
            return reply, conversation_history, [
                {"tool": "analyze_live_asset", "args": {"symbol": tokens[0]}, "result": json.dumps(data, default=str)}
            ]

    # Strategy-id + pnl without PAPER_INTENT still caught above via LIVE_PNL; if only "pnl hs…"
    sid_m = STRATEGY_ID_RE.search(prompt)
    if sid_m and LIVE_PNL_INTENT_RE.search(prompt) and user_wallet:
        pnl = strategy_live_pnl(sid_m.group(1).lower(), user_wallet)
        reply = _format_live_pnl(pnl)
        conversation_history.append({"role": "user", "content": prompt})
        conversation_history.append({"role": "assistant", "content": reply})
        return reply, conversation_history, [
            {"tool": "get_strategy_live_pnl", "args": {"strategy_id": sid_m.group(1).lower()}, "result": json.dumps(pnl, default=str)}
        ]

    # Historical mock only — never when asking live PnL for hs…
    if sid_m and LIVE_PNL_INTENT_RE.search(prompt):
        pass  # already handled
    else:
        backtest = _try_backtest_shortcut(prompt)
        if backtest and not PAPER_INTENT_RE.search(prompt) and not LIVE_PNL_INTENT_RE.search(prompt):
            reply, actions = backtest
            conversation_history.append({"role": "user", "content": prompt})
            conversation_history.append({"role": "assistant", "content": reply})
            return reply, conversation_history, actions

    shortcut = _try_portfolio_shortcut(prompt)
    if shortcut:
        reply, actions = shortcut
        conversation_history.append({"role": "user", "content": prompt})
        conversation_history.append({"role": "assistant", "content": reply})
        return reply, conversation_history, actions

    reply, history, actions = run_tool_agent(
        prompt,
        conversation_history,
        system_prompt=SYSTEM_PROMPT,
        tools=TOOLS,
        tool_registry=tools,
        model=HEDGE_FUND_MODEL,
        app_suffix="Hedge Fund",
        user_wallet=user_wallet,
        session_id=session_id,
    )

    for action in reversed(actions):
        tool = action.get("tool")
        if tool not in (
            "run_mock_backtest",
            "run_strategy_backtest",
            "get_paper_dashboard",
            "create_paper_strategy",
            "get_strategy_live_pnl",
            "confirm_paper_strategy",
        ):
            continue
        try:
            data = json.loads(action.get("result") or "{}")
        except json.JSONDecodeError:
            break
        if tool == "get_strategy_live_pnl":
            formatted = _format_live_pnl(data)
            history[-1] = {"role": "assistant", "content": formatted}
            return formatted, history, actions
        if tool == "create_paper_strategy":
            formatted = _format_strategy_proposal(data)
            history[-1] = {"role": "assistant", "content": formatted}
            return formatted, history, actions
        if tool == "confirm_paper_strategy" and not data.get("error"):
            sid = (data.get("strategy") or {}).get("id") or ""
            formatted = f"**Confirmed** `{sid}`\n\n" + (
                _format_live_pnl(strategy_live_pnl(sid, user_wallet or "")) if sid and user_wallet else ""
            )
            history[-1] = {"role": "assistant", "content": formatted}
            return formatted, history, actions
        if tool == "get_paper_dashboard":
            formatted = _format_paper_dashboard(data)
            history[-1] = {"role": "assistant", "content": formatted}
            return formatted, history, actions
        bt = data.get("result") if tool == "run_strategy_backtest" else data
        if isinstance(bt, dict) and tool in ("run_mock_backtest", "run_strategy_backtest"):
            formatted = _format_backtest_reply(bt)
            history[-1] = {"role": "assistant", "content": formatted}
            return formatted, history, actions

    return reply, history, actions
