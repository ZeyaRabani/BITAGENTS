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
from yahoo_market_data import DEFAULT_STOCK_CRYPTO_BOOK, KNOWN_STOCK_TICKERS, YAHOO_TICKER_MAP

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
    r"\b(backtest|back\s*test|mock\s*trad|paper\s*trad|simulate|simulation|pnl|p&l|profit\s*and\s*loss|"
    r"historical\s*(?:return|performance)|from\s+\w+\s+20\d{2}|start\s+trading|"
    r"allowed\s+to\s+trade|give\s+(?:the\s+)?pnl|20\d{2}-\d{2}-\d{2})\b",
    re.I,
)

OPEN_MANDATE_RE = re.compile(
    r"\b(whatever|any\s+assets?|stocks?\s+or\s+crypto|crypto\s+or\s+stocks?|"
    r"allowed\s+to\s+trade|trade\s+whatever|pick\s+(?:the\s+)?assets?|"
    r"name\s+of\s+assets|you\s+would\s+trade)\b",
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

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_mock_backtest",
            "description": (
                "PRIMARY for historical/mock trading and PnL. Uses Yahoo Finance daily prices + news. "
                "Supports stocks (AAPL, MSFT, NVDA…) and crypto (BTC, ETH, SOL). "
                "If tokens omitted / open mandate, uses a default diversified stock+crypto book."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tokens": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tickers e.g. AAPL, BTC. Empty = default book.",
                    },
                    "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "capital_usd": {"type": "number"},
                    "include_news": {"type": "boolean"},
                },
                "required": ["start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_portfolio_analysis",
            "description": (
                "Live Covenant-style portfolio analysis on Solana tokens: "
                "quant/value analyst signals, risk limits, suggested allocations."
            ),
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
            "description": "Single-token analyst signals + position limit for a given portfolio size.",
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
            "description": "Calculate 1/10 fees (1% mgmt + 10% performance) for given AUM and profit.",
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
            "description": "Return the hedge fund 1/10 fee model and comparison to 2/20.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

TOOL_REGISTRY = {
    "run_mock_backtest": run_mock_backtest,
    "run_portfolio_analysis": run_portfolio_analysis,
    "analyze_token_for_portfolio": analyze_token_for_portfolio,
    "calculate_fees": calculate_fees,
    "get_fee_structure": get_fee_structure,
}

SYSTEM_PROMPT = f"""You are **Hedge Fund Agent** — Covenant-inspired fund manager with a **1/10** fee model
({MANAGEMENT_FEE_RATE*100:.0f}% annual management + {PERFORMANCE_FEE_RATE*100:.0f}% performance).

Rules:
- For historical / mock trading / PnL / backtests (stocks or crypto, date ranges), call `run_mock_backtest`.
- Prices and news come from **Yahoo Finance**. Crypto tickers: BTC, ETH, SOL. Stocks: AAPL, MSFT, etc.
- If the user gives an open mandate ("whatever", "stocks or crypto") and no tickers, omit `tokens` so the default book is used.
- For live Solana token allocation research, call `run_portfolio_analysis`.
- Never invent prices or PnL — only report tool JSON.
- Dates must be YYYY-MM-DD. Default capital $10,000 if unspecified.
- Not financial advice. Mock trades are simulations.
"""


def _extract_tokens(text: str) -> list[str]:
    """Return explicit Yahoo-eligible tickers only — never English filler words."""
    if OPEN_MANDATE_RE.search(text) and not re.search(
        r"\b(?:BTC|ETH|SOL|AAPL|MSFT|NVDA|AMZN|GOOGL|TSLA|SPY|QQQ)\b", text, re.I
    ):
        return []

    found: list[str] = []
    # $AAPL style
    for m in re.findall(r"\$([A-Za-z]{1,5})\b", text):
        sym = m.upper()
        if sym not in found:
            found.append(sym)

    # Explicit crypto / known stocks only when written as standalone tickers
    candidates = re.findall(r"\b([A-Za-z]{1,5})\b", text.upper())
    allow = set(YAHOO_TICKER_MAP) | set(KNOWN_STOCK_TICKERS) | {"BTC", "ETH", "SOL"}
    for s in candidates:
        if s in allow and s not in found:
            found.append(s)

    # Normalize bitcoin/ethereum words
    if re.search(r"\bbitcoin\b", text, re.I) and "BTC" not in found:
        found.append("BTC")
    if re.search(r"\bethereum\b", text, re.I) and "ETH" not in found:
        found.append("ETH")

    return found[:8]


def _extract_capital(text: str) -> float:
    # Prefer explicit $ amounts or amounts with usd/capital/k markers — avoid years like 2025
    patterns = [
        r"\$\s*([\d,]+(?:\.\d+)?)\s*([kK])?\b",
        r"\b([\d,]+(?:\.\d+)?)\s*([kK])\s*(?:usd|USD)?\b",
        r"\b([\d,]+(?:\.\d+)?)\s*(?:usd|USD)\b",
        r"\b(?:capital|aum|portfolio)\s*(?:of|=|:)?\s*\$?\s*([\d,]+(?:\.\d+)?)\s*([kK])?\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if not m:
            continue
        raw = m.group(1).replace(",", "")
        try:
            val = float(raw)
        except ValueError:
            continue
        # Skip year-like bare numbers without $ or k
        if "$" not in pattern and "k" not in pattern.lower() and "usd" not in pattern.lower():
            if 1900 <= val <= 2100:
                continue
        suffix = m.group(2) if m.lastindex and m.lastindex >= 2 else None
        if suffix and suffix.lower() == "k":
            val *= 1000
        elif re.search(r"\b[\d,]+(?:\.\d+)?\s*[kK]\b", text) and "$" in (m.group(0) or ""):
            pass
        return max(100.0, val)
    return 10_000.0


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
        "**Covenant Hedge Fund — Mock Backtest / PnL Report**",
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
            "**Positions**",
        ]
    )
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
    if not BACKTEST_INTENT_RE.search(user_input) and not OPEN_MANDATE_RE.search(user_input):
        # Still allow pure ISO date-range PnL asks
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
                "tokens": tokens or list(DEFAULT_STOCK_CRYPTO_BOOK),
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


def run_hedge_fund_agent(
    user_input: str,
    conversation_history: list,
    user_wallet: Optional[str] = None,
    session_id: Optional[str] = None,
) -> tuple[str, list, list[dict[str, Any]]]:
    prompt = user_input.strip()

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

    backtest = _try_backtest_shortcut(prompt)
    if backtest:
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
        tool_registry=TOOL_REGISTRY,
        model=HEDGE_FUND_MODEL,
        app_suffix="Hedge Fund",
        user_wallet=user_wallet,
        session_id=session_id,
    )

    # If tools returned a backtest, prefer formatted report over raw LLM prose
    for action in reversed(actions):
        if action.get("tool") != "run_mock_backtest":
            continue
        try:
            data = json.loads(action.get("result") or "{}")
        except json.JSONDecodeError:
            break
        formatted = _format_backtest_reply(data)
        history[-1] = {"role": "assistant", "content": formatted}
        return formatted, history, actions

    return reply, history, actions
