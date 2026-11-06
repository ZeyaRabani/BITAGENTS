"""Wallet Monitoring Agent - on-chain wallet analysis for any Solana address."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

from agent_tool_runner import run_tool_agent
from hosted_llm import CAPIX_MODEL, DEFAULT_LLM_MODEL, call_llm, use_capix
from kickstart_copilot_agent import get_token_analytics, search_tokens
from solana_wallet_tools import (
    WALLET_SNAPSHOT_CACHE_TTL_SECONDS,
    analyze_wallet_profile,
    extract_wallet_query,
    format_wallet_snapshot_reply,
    get_wallet_analysis_cached,
    get_wallet_cache_stats,
    get_wallet_recent_activity,
    get_wallet_snapshot,
    get_wallet_sol_balance,
    get_wallet_token_balances,
    set_wallet_analysis_cached,
)

WALLET_MONITORING_MODEL = (
    CAPIX_MODEL
    if use_capix()
    else os.environ.get(
        "WALLET_MONITORING_MODEL",
        os.environ.get("DCA_MODEL", os.environ.get("OPEN_ROUTER_MODEL", DEFAULT_LLM_MODEL)),
    )
)

WALLET_INTENT_RE = re.compile(
    r"\b("
    r"wallet|analyze|analysis|monitor|holdings|portfolio|balance|tokens|"
    r"suggest|trades|activity|my wallet|connected wallet"
    r")\b",
    re.I,
)


def _analysis_cache_get(address: str) -> Optional[str]:
    return get_wallet_analysis_cached(address)


def _analysis_cache_set(address: str, text: str) -> None:
    set_wallet_analysis_cached(address, text)


def _resolve_wallet_address(address: Optional[str] = None, user_wallet: Optional[str] = None) -> Optional[str]:
    target = (address or user_wallet or "").strip()
    return target if len(target) >= 32 else None


def analyze_wallet(
    address: Optional[str] = None,
    user_wallet: Optional[str] = None,
) -> dict[str, Any]:
    """Analyze any Solana wallet (explicit address or connected wallet)."""
    target = _resolve_wallet_address(address, user_wallet)
    if not target:
        return {
            "error": "Provide a Solana wallet address or connect your wallet and ask about 'my wallet'.",
            "needs_valid_address": True,
        }
    return get_wallet_snapshot(target)


def analyze_connected_wallet(user_wallet: Optional[str] = None) -> dict[str, Any]:
    return analyze_wallet(user_wallet=user_wallet)


def suggest_wallet_trades(
    address: Optional[str] = None,
    user_wallet: Optional[str] = None,
    risk_profile: str = "balanced",
) -> dict[str, Any]:
    snapshot = analyze_wallet(address=address, user_wallet=user_wallet)
    if snapshot.get("error"):
        return snapshot
    from solana_wallet_tools import _build_trade_suggestions

    suggestions = _build_trade_suggestions(
        {"sol_balance": snapshot.get("sol_balance"), "tokens": snapshot.get("tokens") or []},
        risk_profile=risk_profile,
    )
    return {
        "wallet": snapshot.get("address"),
        "risk_profile": risk_profile,
        "suggestions": suggestions,
        "holdings_with_market": snapshot.get("holdings_with_prices") or [],
        "disclaimer": "Suggestions are informational only — not financial advice.",
    }


def lookup_holding_token(
    token: str,
    address: Optional[str] = None,
    user_wallet: Optional[str] = None,
) -> dict[str, Any]:
    target = _resolve_wallet_address(address, user_wallet)
    if not target:
        return {"error": "Wallet address required."}
    holdings = get_wallet_token_balances(target, limit=50)
    tokens = holdings.get("tokens") or []
    token_q = (token or "").strip().upper()
    match = next((t for t in tokens if str(t.get("symbol", "")).upper() == token_q), None)
    if not match:
        match = next((t for t in tokens if str(t.get("mint", "")) == token.strip()), None)
    analytics = get_token_analytics(token)
    return {
        "wallet": target,
        "holding": match,
        "market": analytics,
        "in_wallet": match is not None,
    }


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "analyze_wallet",
            "description": (
                "PRIMARY tool. Full on-chain snapshot for ANY Solana wallet: SOL, SPL holdings, "
                "activity, Jupiter prices. Pass address for other wallets; omit to use connected wallet."
            ),
            "parameters": {
                "type": "object",
                "properties": {"address": {"type": "string", "description": "Solana wallet address to analyze"}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_wallet_sol_balance",
            "description": "SOL balance via Solana RPC.",
            "parameters": {
                "type": "object",
                "properties": {"address": {"type": "string"}},
                "required": ["address"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_wallet_token_balances",
            "description": "SPL token balances via Solana RPC.",
            "parameters": {
                "type": "object",
                "properties": {"address": {"type": "string"}, "limit": {"type": "integer"}},
                "required": ["address"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_wallet_recent_activity",
            "description": "Recent transaction signatures via Solana RPC.",
            "parameters": {
                "type": "object",
                "properties": {"address": {"type": "string"}, "limit": {"type": "integer"}},
                "required": ["address"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_wallet_trades",
            "description": "Informational trade suggestions from on-chain holdings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {"type": "string"},
                    "risk_profile": {"type": "string"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_holding_token",
            "description": "Check if a token is in a wallet and fetch market data.",
            "parameters": {
                "type": "object",
                "properties": {"token": {"type": "string"}, "address": {"type": "string"}},
                "required": ["token"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_tokens",
            "description": "Search tokens on EASY Screener.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
                "required": ["query"],
            },
        },
    },
]


def _wallet_tool(name: str, user_wallet: Optional[str] = None, **kwargs):
    address = (kwargs.get("address") or user_wallet or "").strip()
    if name == "analyze_wallet":
        return analyze_wallet(address=kwargs.get("address"), user_wallet=user_wallet)
    if name == "analyze_connected_wallet":
        return analyze_wallet(user_wallet=user_wallet)
    if name == "suggest_wallet_trades":
        return suggest_wallet_trades(
            address=kwargs.get("address"),
            user_wallet=user_wallet,
            risk_profile=kwargs.get("risk_profile", "balanced"),
        )
    if name == "lookup_holding_token":
        return lookup_holding_token(
            token=kwargs.get("token", ""),
            address=kwargs.get("address"),
            user_wallet=user_wallet,
        )
    if name == "get_wallet_sol_balance":
        return get_wallet_sol_balance(address) if address else {"error": "address is required"}
    if name == "get_wallet_token_balances":
        return get_wallet_token_balances(address, kwargs.get("limit", 25)) if address else {"error": "address is required"}
    if name == "get_wallet_recent_activity":
        return get_wallet_recent_activity(address, kwargs.get("limit", 12)) if address else {"error": "address is required"}
    raise KeyError(name)


TOOL_REGISTRY = {
    "analyze_wallet": lambda **kw: _wallet_tool("analyze_wallet", **kw),
    "analyze_connected_wallet": lambda **kw: _wallet_tool("analyze_connected_wallet", **kw),
    "get_wallet_sol_balance": lambda **kw: _wallet_tool("get_wallet_sol_balance", **kw),
    "get_wallet_token_balances": lambda **kw: _wallet_tool("get_wallet_token_balances", **kw),
    "get_wallet_recent_activity": lambda **kw: _wallet_tool("get_wallet_recent_activity", **kw),
    "suggest_wallet_trades": lambda **kw: _wallet_tool("suggest_wallet_trades", **kw),
    "lookup_holding_token": lambda **kw: _wallet_tool("lookup_holding_token", **kw),
    "search_tokens": search_tokens,
    "get_token_analytics": get_token_analytics,
}

SYSTEM_PROMPT = f"""You are **Wallet Monitoring Agent** on Solana.

Fetch wallet data from **Solana RPC** (never invent balances or holdings).

Rules:
- Use `analyze_wallet` first — pass `address` for ANY wallet the user names, or omit for their connected wallet.
- On-chain snapshots are cached **{WALLET_SNAPSHOT_CACHE_TTL_SECONDS // 60} minutes** per address.
- Never fabricate SOL amounts, token lists, or signatures — only report tool JSON output.
- Trade suggestions are informational only, not financial advice.
"""


def _generate_wallet_analysis(snapshot: dict[str, Any]) -> str:
    address = str(snapshot.get("address") or "")
    cached = _analysis_cache_get(address)
    if cached:
        return cached

    payload = {
        "address": snapshot.get("address"),
        "sol_balance": snapshot.get("sol_balance"),
        "estimated_portfolio_value_usd": snapshot.get("estimated_portfolio_value_usd"),
        "token_count": snapshot.get("token_count"),
        "top_holdings": (snapshot.get("holdings_with_prices") or snapshot.get("tokens") or [])[:8],
        "recent_activity_count": (snapshot.get("recent_activity") or {}).get("count"),
        "trade_suggestions": snapshot.get("trade_suggestions"),
    }
    try:
        response = call_llm(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a Solana wallet analyst. Given JSON from Solana RPC, write a **Wallet Analysis** with: "
                        "Summary, Portfolio composition, Activity notes, Risks, Actionable suggestions. "
                        "Use ONLY provided data. Under 250 words. Not financial advice."
                    ),
                },
                {"role": "user", "content": json.dumps(payload, indent=2, default=str)},
            ],
            model=WALLET_MONITORING_MODEL,
            temperature=0.35,
            app_suffix="Wallet Analysis",
        )
        text = ((response.get("message") or {}).get("content") or "").strip()
    except Exception as exc:
        text = f"_Analysis unavailable ({exc}). Review the on-chain snapshot above._"

    if text and address:
        _analysis_cache_set(address, text)
    return text


def build_full_wallet_reply(snapshot: dict[str, Any]) -> str:
    metrics = format_wallet_snapshot_reply(snapshot)
    if snapshot.get("error"):
        return metrics
    analysis = _generate_wallet_analysis(snapshot)
    return f"{metrics}\n\n---\n\n**Wallet Analysis**\n\n{analysis}"


def _try_wallet_shortcut(
    user_input: str,
    user_wallet: Optional[str] = None,
) -> Optional[tuple[str, list[dict[str, Any]]]]:
    if not WALLET_INTENT_RE.search(user_input):
        return None

    target = extract_wallet_query(user_input, connected_wallet=user_wallet)
    if not target and user_wallet:
        if re.search(r"\b(my|connected|own)\b", user_input, re.I):
            target = user_wallet

    if not target:
        return None

    snapshot = get_wallet_snapshot(target)
    action = {
        "tool": "analyze_wallet",
        "args": {"address": target},
        "result": json.dumps(snapshot, indent=2, default=str),
    }
    if snapshot.get("error"):
        reply = format_wallet_snapshot_reply(snapshot)
    else:
        reply = build_full_wallet_reply(snapshot)
    return reply, [action]


def _reply_from_wallet_actions(actions: list[dict[str, Any]], llm_reply: str) -> str:
    for action in reversed(actions):
        if action.get("tool") not in ("analyze_wallet", "analyze_connected_wallet"):
            continue
        try:
            data = json.loads(action.get("result") or "{}")
        except json.JSONDecodeError:
            continue
        if data.get("error"):
            return format_wallet_snapshot_reply(data)
        return build_full_wallet_reply(data)
    return llm_reply


def run_wallet_monitoring_agent(
    user_input: str,
    conversation_history: list,
    user_wallet: Optional[str] = None,
    session_id: Optional[str] = None,
) -> tuple[str, list, list[dict[str, Any]]]:
    prompt = user_input.strip()

    shortcut = _try_wallet_shortcut(prompt, user_wallet)
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
        model=WALLET_MONITORING_MODEL,
        app_suffix="Wallet Monitoring",
        user_wallet=user_wallet,
        session_id=session_id,
    )

    synthesized = _reply_from_wallet_actions(actions, reply)
    if synthesized != reply:
        history[-1] = {"role": "assistant", "content": synthesized}
        reply = synthesized
    return reply, history, actions


def get_wallet_monitoring_cache_stats() -> dict[str, Any]:
    return get_wallet_cache_stats()
