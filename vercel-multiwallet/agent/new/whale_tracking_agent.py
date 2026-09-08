"""Whale Tracking Agent - track Solana wallets and research copy-trade opportunities."""

from __future__ import annotations

import os
from typing import Any, Optional

from agent_tool_runner import run_tool_agent
from hosted_llm import CAPIX_MODEL, DEFAULT_LLM_MODEL, use_capix
from solana_wallet_tools import (
    analyze_wallet_profile,
    get_wallet_recent_activity,
    get_wallet_sol_balance,
    get_wallet_token_balances,
    list_tracked_wallets,
)

WHALE_MODEL = (
    CAPIX_MODEL
    if use_capix()
    else os.environ.get(
        "WHALE_TRACKING_MODEL",
        os.environ.get("DCA_MODEL", os.environ.get("OPEN_ROUTER_MODEL", DEFAULT_LLM_MODEL)),
    )
)

_whale_watchlists: dict[str, list[str]] = {}


def add_whale_to_watchlist(address: str, label: str = "", user_wallet: Optional[str] = None) -> dict[str, Any]:
    address = (address or "").strip()
    if len(address) < 32:
        return {"error": "Provide a valid Solana wallet address."}
    key = (user_wallet or "anonymous").strip()
    entries = _whale_watchlists.setdefault(key, [])
    if address not in entries:
        entries.append(address)
    return {
        "status": "added",
        "address": address,
        "label": label or None,
        "watchlist_count": len(entries),
    }


def remove_whale_from_watchlist(address: str, user_wallet: Optional[str] = None) -> dict[str, Any]:
    key = (user_wallet or "anonymous").strip()
    entries = _whale_watchlists.get(key, [])
    if address in entries:
        entries.remove(address)
    return {"status": "removed", "address": address, "watchlist_count": len(entries)}


def get_whale_watchlist(user_wallet: Optional[str] = None) -> dict[str, Any]:
    key = (user_wallet or "anonymous").strip()
    addresses = _whale_watchlists.get(key, [])
    profiles = [analyze_wallet_profile(a) for a in addresses[:20]]
    return {"watchlist": profiles, "count": len(addresses)}


def preview_copy_trade(
    whale_address: str,
    token: str = "",
    recent_limit: int = 8,
    user_wallet: Optional[str] = None,
) -> dict[str, Any]:
    profile = analyze_wallet_profile(whale_address)
    if profile.get("error"):
        return profile
    activity = get_wallet_recent_activity(whale_address, recent_limit)
    token_context = None
    if token.strip():
        from kickstart_copilot_agent import get_token_analytics

        token_context = get_token_analytics(token)
    return {
        "whale_profile": profile,
        "recent_activity": activity,
        "token_context": token_context,
        "copy_trade_mode": "preview_only",
        "note": (
            "This agent does not execute swaps automatically. Review whale activity on Solscan, "
            "then replicate manually via Jupiter or the DCA Agent."
        ),
        "suggested_next_steps": [
            "Inspect recent signatures for swap programs (Jupiter, Raydium, Meteora).",
            "Compare token holdings before/after notable transactions.",
            "Size copy trades smaller than the whale and use limits/slippage controls.",
        ],
        "user_wallet": user_wallet,
    }


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_tracked_wallets",
            "description": "List curated whale / smart-money wallet registry categories.",
            "parameters": {
                "type": "object",
                "properties": {"category": {"type": "string", "description": "all, smart_money, exchange, defi"}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_wallet_profile",
            "description": "SOL balance, top tokens, and recent activity for a wallet.",
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
            "name": "get_wallet_recent_activity",
            "description": "Recent transaction signatures for a wallet.",
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
            "name": "get_wallet_token_balances",
            "description": "SPL token balances held by a wallet.",
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
            "name": "add_whale_to_watchlist",
            "description": "Track a wallet address for ongoing monitoring.",
            "parameters": {
                "type": "object",
                "properties": {"address": {"type": "string"}, "label": {"type": "string"}},
                "required": ["address"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_whale_from_watchlist",
            "description": "Stop tracking a wallet address.",
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
            "name": "get_whale_watchlist",
            "description": "List wallets the user is tracking.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "preview_copy_trade",
            "description": "Research a whale's recent activity and outline a copy-trade plan (no auto execution).",
            "parameters": {
                "type": "object",
                "properties": {
                    "whale_address": {"type": "string"},
                    "token": {"type": "string"},
                    "recent_limit": {"type": "integer"},
                },
                "required": ["whale_address"],
            },
        },
    },
]

TOOL_REGISTRY = {
    "list_tracked_wallets": list_tracked_wallets,
    "analyze_wallet_profile": analyze_wallet_profile,
    "get_wallet_recent_activity": get_wallet_recent_activity,
    "get_wallet_token_balances": get_wallet_token_balances,
    "get_wallet_sol_balance": get_wallet_sol_balance,
    "add_whale_to_watchlist": add_whale_to_watchlist,
    "remove_whale_from_watchlist": remove_whale_from_watchlist,
    "get_whale_watchlist": get_whale_watchlist,
    "preview_copy_trade": preview_copy_trade,
}

SYSTEM_PROMPT = """You are **Whale Tracking Agent** on Solana.

Track wallet addresses, analyze holdings and recent activity, maintain user watchlists, and help users research copy-trading opportunities.

Rules:
- Never invent wallet addresses or transaction details — use tools for all on-chain data.
- Copy trading is **preview/research only** in this agent. Do not claim swaps were executed.
- When suggesting copy trades, emphasize risk management, slippage, and independent verification on Solscan.
- Attribute market data to EASY Screener when used via token tools.
"""


def run_whale_tracking_agent(
    user_input: str,
    conversation_history: list,
    user_wallet: Optional[str] = None,
    session_id: Optional[str] = None,
) -> tuple[str, list, list[dict[str, Any]]]:
    return run_tool_agent(
        user_input,
        conversation_history,
        system_prompt=SYSTEM_PROMPT,
        tools=TOOLS,
        tool_registry=TOOL_REGISTRY,
        model=WHALE_MODEL,
        app_suffix="Whale Tracking",
        user_wallet=user_wallet,
        session_id=session_id,
    )
