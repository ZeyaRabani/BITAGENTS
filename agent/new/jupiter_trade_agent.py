"""Jupiter Trade Agent — strategy confirm → 24h paper → live Jupiter spot."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

from agent_tool_runner import run_tool_agent
from hosted_llm import CAPIX_MODEL, DEFAULT_LLM_MODEL, use_capix
from jupiter_trade_core import (
    JT_PAPER_MIN_HOURS,
    close_strategy,
    confirm_live,
    confirm_understanding,
    dashboard,
    get_strategy,
    list_trades,
    paper_gate,
    propose_strategy,
    update_strategy_rules,
)
from jupiter_trade_ledger import JT_PLATFORM_FEE_RATE
from jupiter_trade_templates import (
    get_strategy_template,
    list_strategy_templates,
    match_strategy_template,
)


def _openrouter_model_id(value: str) -> bool:
    return bool(value) and "/" in value and " " not in value


def resolve_jt_llm() -> tuple[str, Optional[str]]:
    """Return (model, provider override). Defaults to OpenRouter for Jupiter Trade."""
    provider = os.environ.get("JT_LLM_PROVIDER", "openrouter").strip().lower()
    if provider in ("ollama", "hosted"):
        provider = "hosted_ollama"
    if provider not in ("openrouter", "capix", "hosted_ollama"):
        provider = "openrouter"

    if provider == "openrouter":
        candidate = (
            os.environ.get("JUPITER_TRADE_MODEL", "").strip()
            or os.environ.get("JT_MODEL", "").strip()
            or os.environ.get("OPEN_ROUTER_MODEL", "").strip()
        )
        model = (
            candidate
            if _openrouter_model_id(candidate)
            else "meta-llama/llama-3.3-70b-instruct"
        )
        return model, "openrouter"
    if provider == "capix":
        return CAPIX_MODEL, "capix"
    if provider == "hosted_ollama":
        return (
            os.environ.get("JUPITER_TRADE_MODEL", "").strip()
            or os.environ.get("HOSTED_OLLAMA_MODEL", DEFAULT_LLM_MODEL)
        ), "hosted_ollama"
    return (
        os.environ.get(
            "JUPITER_TRADE_MODEL",
            os.environ.get("DCA_MODEL", os.environ.get("OPEN_ROUTER_MODEL", DEFAULT_LLM_MODEL)),
        ),
        provider,
    )


JT_MODEL, JT_LLM_PROVIDER = resolve_jt_llm()

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "propose_trade_strategy",
            "description": "Create a Jupiter spot strategy proposal and show understanding for user confirm. Pass template_id when user picks/names an algo (MACD, RSI, Supertrend, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "symbols": {"type": "string", "description": "Space/comma separated tickers"},
                    "capital_sol": {"type": "number"},
                    "take_profit_pct": {"type": "number"},
                    "stop_loss_pct": {"type": "number"},
                    "notes": {"type": "string"},
                    "template_id": {
                        "type": "string",
                        "description": "Template id or name, e.g. macd_classic, rsi_mean_reversion, supertrend",
                    },
                },
                "required": ["symbols"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_strategy_templates",
            "description": "List popular named trading strategy templates (100+). Optional family or search query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "family": {
                        "type": "string",
                        "description": "trend|macd|mean_reversion|breakout|momentum|risk|...",
                    },
                    "query": {"type": "string", "description": "Search text e.g. MACD, RSI, bollinger"},
                    "limit": {"type": "number"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "match_strategy_template",
            "description": "Map user wording to the best strategy template.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_strategy_template",
            "description": "Get full details for one template id.",
            "parameters": {
                "type": "object",
                "properties": {"template_id": {"type": "string"}},
                "required": ["template_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confirm_strategy_understanding",
            "description": "User confirmed the agent understood the strategy. Starts ≥24h paper mode.",
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
            "name": "confirm_live_trading",
            "description": "After ≥24h paper and user review, enable live Jupiter spot trading.",
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
            "name": "get_trade_dashboard",
            "description": "List strategies, paper gates, positions, and recent trades.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_strategy_status",
            "description": "Status + paper gate for one strategy.",
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
            "name": "list_strategy_trades",
            "description": "Show recorded paper/live trades for verification.",
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
            "name": "update_trade_rules",
            "description": "Change TP/SL/notes. Resets to understanding confirm (restarts paper clock).",
            "parameters": {
                "type": "object",
                "properties": {
                    "strategy_id": {"type": "string"},
                    "take_profit_pct": {"type": "number"},
                    "stop_loss_pct": {"type": "number"},
                    "notes": {"type": "string"},
                },
                "required": ["strategy_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "close_trade_strategy",
            "description": "Close a strategy.",
            "parameters": {
                "type": "object",
                "properties": {"strategy_id": {"type": "string"}},
                "required": ["strategy_id"],
            },
        },
    },
]


def _registry(user_wallet: str) -> dict[str, Any]:
    def propose_trade_strategy(**kwargs):
        return propose_strategy(
            user_wallet,
            name=str(kwargs.get("name") or ""),
            symbols=str(kwargs.get("symbols") or ""),
            capital_sol=float(kwargs.get("capital_sol") or 1),
            take_profit_pct=kwargs.get("take_profit_pct"),
            stop_loss_pct=kwargs.get("stop_loss_pct"),
            notes=str(kwargs.get("notes") or ""),
            template_id=str(kwargs.get("template_id") or ""),
            created_by="agent",
        )

    def list_strategy_templates_tool(family: str = "", query: str = "", limit: float = 40):
        return list_strategy_templates(family=family, query=query, limit=int(limit or 40))

    def match_strategy_template_tool(text: str = ""):
        return match_strategy_template(text)

    def get_strategy_template_tool(template_id: str = ""):
        return get_strategy_template(template_id)

    def confirm_strategy_understanding(strategy_id: str = ""):
        return confirm_understanding(strategy_id, user_wallet)

    def confirm_live_trading(strategy_id: str = ""):
        return confirm_live(strategy_id, user_wallet)

    def get_trade_dashboard():
        return dashboard(user_wallet)

    def get_strategy_status(strategy_id: str = ""):
        strategy = get_strategy(strategy_id, user_wallet)
        if not strategy:
            return {"error": "Strategy not found"}
        return {"strategy": strategy, "gate": paper_gate(strategy), "understanding": strategy.get("understanding")}

    def list_strategy_trades(strategy_id: str = ""):
        return {"strategy_id": strategy_id, "trades": list_trades(strategy_id, limit=40)}

    def update_trade_rules(**kwargs):
        return update_strategy_rules(
            str(kwargs.get("strategy_id") or ""),
            user_wallet,
            take_profit_pct=kwargs.get("take_profit_pct"),
            stop_loss_pct=kwargs.get("stop_loss_pct"),
            notes=kwargs.get("notes"),
            reset_to_confirm=True,
        )

    def close_trade_strategy(strategy_id: str = ""):
        return close_strategy(strategy_id, user_wallet)

    return {
        "propose_trade_strategy": propose_trade_strategy,
        "list_strategy_templates": list_strategy_templates_tool,
        "match_strategy_template": match_strategy_template_tool,
        "get_strategy_template": get_strategy_template_tool,
        "confirm_strategy_understanding": confirm_strategy_understanding,
        "confirm_live_trading": confirm_live_trading,
        "get_trade_dashboard": get_trade_dashboard,
        "get_strategy_status": get_strategy_status,
        "list_strategy_trades": list_strategy_trades,
        "update_trade_rules": update_trade_rules,
        "close_trade_strategy": close_trade_strategy,
    }


SYSTEM_PROMPT = f"""You are **Jupiter Trade Agent** on BIT Agents.

Venue: **Jupiter spot swaps only**. Do NOT use or promise Jupiter Perps (API not ready).
Platform fee: **{JT_PLATFORM_FEE_RATE * 100:g}% per live trade** (not charged in paper).

Efficiency (critical):
- For any "trade / buy / enter / invest with X SOL" request, call **propose_trade_strategy once** and stop.
- Do NOT call list_strategy_templates / match_strategy_template / get_strategy_template unless the user
  explicitly asks to browse or name an algo.
- Defaults when the user is vague: template_id=`macd_classic`, symbols=`BONK`, TP 12, SL 6.
- Never loop tools. After propose, paste the understanding and ask them to confirm.

When the user names an algo (MACD, RSI, Supertrend, …): pass that as template_id on propose
(match only if needed, then propose in the same turn if you can).

Mandatory lifecycle:
1. Call `propose_trade_strategy` and restate understanding.
2. User confirms understanding before anything runs.
3. Paper ≥ {JT_PAPER_MIN_HOURS:g}h, then user confirms live for real Jupiter spot fills.
4. Rule/template changes reset confirm + paper clock.

Rules:
- Never claim a live fill unless a tool result includes a signature.
- Be explicit about paper vs live. Keep answers short.
"""


_CONFIRM_UNDERSTANDING = re.compile(
    r"confirm\s+(?:understanding|strategy)?\s*(jt[a-f0-9]+)",
    re.I,
)
_CONFIRM_LIVE = re.compile(r"confirm\s+live\s*(jt[a-f0-9]+)", re.I)
_STATUS = re.compile(r"(?:status|gate|paper)\s+(jt[a-f0-9]+)", re.I)
_QUICK_TRADE = re.compile(
    r"(?:enter|open|start|make|create|do)?\s*(?:a\s+)?(?:trade|buy|invest|swap|position)"
    r".*?(?:with|for|using)?\s*([\d.]+)\s*sol\b",
    re.I,
)
_QUICK_TRADE_LOOSE = re.compile(
    r"(?:trade|buy|invest|swap).*?([\d.]+)\s*sol\b|\b([\d.]+)\s*sol\b.*?(?:trade|buy|invest)",
    re.I,
)


def _shortcut(
    user_input: str,
    user_wallet: str,
) -> Optional[tuple[str, list, list[dict[str, Any]]]]:
    text = (user_input or "").strip()
    # Vague "enter a trade with 0.01 SOL" → propose once (no LLM tool loop).
    if not re.search(r"\b(jt[a-f0-9]+|confirm|status|template|list|macd|rsi|supertrend)\b", text, re.I):
        qm = _QUICK_TRADE.search(text) or _QUICK_TRADE_LOOSE.search(text)
        if qm:
            amount_raw = next((g for g in qm.groups() if g), "0.01")
            try:
                capital = float(amount_raw)
            except ValueError:
                capital = 0.01
            capital = max(0.01, min(10.0, capital))
            result = propose_strategy(
                user_wallet,
                symbols="BONK",
                capital_sol=capital,
                take_profit_pct=12,
                stop_loss_pct=6,
                notes=text,
                template_id="macd_classic",
                created_by="agent",
            )
            reply = (
                result.get("understanding")
                or result.get("message")
                or result.get("error")
                or json.dumps(result, default=str)
            )
            if result.get("strategy") and not result.get("error"):
                sid = (result.get("strategy") or {}).get("id") or ""
                reply = (
                    f"{reply}\n\nReply `confirm understanding {sid}` to start ≥{JT_PAPER_MIN_HOURS:g}h paper. "
                    "No live Jupiter fills until paper is done and you confirm live."
                )
            return reply, [], [
                {
                    "tool": "propose_trade_strategy",
                    "args": {
                        "symbols": "BONK",
                        "capital_sol": capital,
                        "template_id": "macd_classic",
                    },
                    "result": json.dumps(result, default=str),
                }
            ]
    m = _CONFIRM_LIVE.search(text)
    if m:
        result = confirm_live(m.group(1), user_wallet)
        reply = (
            result.get("message")
            or result.get("error")
            or json.dumps(result, default=str)
        )
        return reply, [], [{"tool": "confirm_live_trading", "args": {"strategy_id": m.group(1)}, "result": json.dumps(result, default=str)}]
    m = _CONFIRM_UNDERSTANDING.search(text)
    if m:
        result = confirm_understanding(m.group(1), user_wallet)
        reply = (
            result.get("message")
            or result.get("error")
            or json.dumps(result, default=str)
        )
        return reply, [], [{"tool": "confirm_strategy_understanding", "args": {"strategy_id": m.group(1)}, "result": json.dumps(result, default=str)}]
    m = _STATUS.search(text)
    if m:
        strategy = get_strategy(m.group(1), user_wallet)
        if not strategy:
            return "Strategy not found.", [], []
        gate = paper_gate(strategy)
        reply = (
            f"{strategy['id']} · {strategy['status']} · "
            f"paper {gate['hours_elapsed']}h / {gate['paper_min_hours']}h · "
            f"remaining {gate['hours_remaining']}h"
        )
        return reply, [], [{"tool": "get_strategy_status", "args": {"strategy_id": m.group(1)}, "result": json.dumps({"strategy": strategy, "gate": gate}, default=str)}]
    return None


def run_jupiter_trade_agent(
    user_input: str,
    conversation_history: list,
    user_wallet: Optional[str] = None,
    session_id: Optional[str] = None,
) -> tuple[str, list, list[dict[str, Any]]]:
    wallet = (user_wallet or "").strip()
    if not wallet:
        return "Connect and sign in with your wallet first.", conversation_history, []

    hit = _shortcut(user_input, wallet)
    if hit:
        return hit

    return run_tool_agent(
        user_input,
        conversation_history,
        system_prompt=SYSTEM_PROMPT,
        tools=TOOLS,
        tool_registry=_registry(wallet),
        model=JT_MODEL,
        app_suffix="Jupiter Trade",
        provider=JT_LLM_PROVIDER,
        user_wallet=wallet,
        session_id=session_id,
        max_rounds=6,
    )
