"""Shared DeFi strategy agents (LP, copy-trade, grid, guard, perps, arb, treasury, rebalance, sniper, options)."""

from __future__ import annotations

import os
import time
import uuid
from typing import Any, Optional

from agent_tool_runner import run_tool_agent
from hosted_llm import CAPIX_MODEL, DEFAULT_LLM_MODEL, use_capix

DEFI_MODEL = (
    CAPIX_MODEL
    if use_capix()
    else os.environ.get(
        "DEFI_AGENT_MODEL",
        os.environ.get("DCA_MODEL", os.environ.get("OPEN_ROUTER_MODEL", DEFAULT_LLM_MODEL)),
    )
)

DEFI_AGENT_META: dict[str, dict[str, str]] = {
    "liquidity": {
        "name": "Liquidity / LP Agent",
        "focus": "concentrated liquidity on Meteora, Orca, and Raydium",
        "pricing": "0.35% / action",
    },
    "copy-trade": {
        "name": "Copy-Trade Agent",
        "focus": "mirroring whale wallets with size caps and delay",
        "pricing": "0.5% / copy",
    },
    "grid": {
        "name": "Grid / Range Agent",
        "focus": "buy-low / sell-high grids inside a price band",
        "pricing": "0.4% / fill",
    },
    "liquidation-guard": {
        "name": "Liquidation Guard Agent",
        "focus": "perp and lending health monitoring with auto-hedge rules",
        "pricing": "0.25% / hedge",
    },
    "funding-perps": {
        "name": "Funding / Perps Agent",
        "focus": "funding-aware perpetual exposure with leverage caps",
        "pricing": "0.35% / trade",
    },
    "arbitrage": {
        "name": "Arbitrage / Basis Agent",
        "focus": "spot/perp basis and pool mispricing scans",
        "pricing": "0.2% / arb",
    },
    "treasury": {
        "name": "Treasury / Idle Cash Agent",
        "focus": "idle cash sweeps with operating buffers",
        "pricing": "0.15% / sweep",
    },
    "rebalance": {
        "name": "Rebalance Agent",
        "focus": "target portfolio weights and drift bands",
        "pricing": "0.3% / rebalance",
    },
    "sniper": {
        "name": "Sniper / Launch Guard Agent",
        "focus": "new pool entries with liquidity and authority gates",
        "pricing": "0.6% / entry",
    },
    "options": {
        "name": "Options / Structured Agent",
        "focus": "simple structured payoffs (collar, covered call style)",
        "pricing": "0.45% / structure",
    },
}

# user_wallet -> agent_slug -> strategies
_strategies: dict[str, dict[str, list[dict[str, Any]]]] = {}


def _key(user_wallet: Optional[str]) -> str:
    return (user_wallet or "anonymous").strip()


def upsert_strategy(
    agent_slug: str,
    params_json: str = "{}",
    note: str = "",
    user_wallet: Optional[str] = None,
) -> dict[str, Any]:
    import json

    slug = (agent_slug or "").strip()
    if slug not in DEFI_AGENT_META:
        return {"error": f"Unknown agent_slug: {agent_slug}"}
    try:
        params = json.loads(params_json) if params_json else {}
    except json.JSONDecodeError:
        params = {"raw": params_json}
    if not isinstance(params, dict):
        params = {"value": params}

    wallet = _key(user_wallet)
    bucket = _strategies.setdefault(wallet, {}).setdefault(slug, [])
    record = {
        "id": f"str_{uuid.uuid4().hex[:10]}",
        "agent_slug": slug,
        "status": "active",
        "created_at": int(time.time()),
        "params": params,
        "note": note or None,
        "mode": "paper_preview",
    }
    bucket.insert(0, record)
    return {
        "status": "created",
        "strategy": record,
        "count": len(bucket),
        "note": "Strategy stored in paper/preview mode. Live custody wallets can be wired next.",
    }


def list_strategies(agent_slug: str = "", user_wallet: Optional[str] = None) -> dict[str, Any]:
    wallet = _key(user_wallet)
    by_agent = _strategies.get(wallet, {})
    slug = (agent_slug or "").strip()
    if slug:
        items = by_agent.get(slug, [])
        return {"agent_slug": slug, "strategies": items, "count": len(items)}
    flat: list[dict[str, Any]] = []
    for items in by_agent.values():
        flat.extend(items)
    return {"strategies": flat, "count": len(flat)}


def set_strategy_status(
    strategy_id: str,
    status: str = "paused",
    user_wallet: Optional[str] = None,
) -> dict[str, Any]:
    status = (status or "").strip().lower()
    if status not in {"active", "paused", "closed"}:
        return {"error": "status must be active, paused, or closed"}
    wallet = _key(user_wallet)
    for items in _strategies.get(wallet, {}).values():
        for item in items:
            if item.get("id") == strategy_id:
                item["status"] = status
                return {"status": "updated", "strategy": item}
    return {"error": f"Strategy not found: {strategy_id}"}


def explain_agent(agent_slug: str) -> dict[str, Any]:
    meta = DEFI_AGENT_META.get((agent_slug or "").strip())
    if not meta:
        return {"error": f"Unknown agent_slug: {agent_slug}", "known": list(DEFI_AGENT_META)}
    return {
        "agent_slug": agent_slug,
        **meta,
        "execution_mode": "paper_preview",
        "guidance": [
            "Collect clear numeric risk limits before suggesting live size.",
            "Never invent fills, funding rates, or pool TVL - mark unknowns explicitly.",
            "Prefer creating or updating a strategy record over claiming an on-chain fill.",
        ],
    }


def simulate_risk_check(
    agent_slug: str,
    params_json: str = "{}",
    user_wallet: Optional[str] = None,
) -> dict[str, Any]:
    import json

    try:
        params = json.loads(params_json) if params_json else {}
    except json.JSONDecodeError:
        params = {"raw": params_json}
    meta = DEFI_AGENT_META.get((agent_slug or "").strip(), {})
    warnings: list[str] = []
    if isinstance(params, dict):
        for key in ("max_leverage", "max_slip_bps", "size_pct", "capital", "max_buy"):
            if key in params:
                try:
                    value = float(params[key])
                except (TypeError, ValueError):
                    continue
                if key == "max_leverage" and value > 5:
                    warnings.append("Leverage above 5x is high for an automated agent.")
                if key == "max_slip_bps" and value > 200:
                    warnings.append("Slippage above 200 bps can fill poorly on thin pools.")
                if key == "size_pct" and value > 25:
                    warnings.append("Copy size above 25% of whale notional is aggressive.")
    return {
        "agent": meta.get("name", agent_slug),
        "params": params,
        "warnings": warnings,
        "ok": len(warnings) == 0,
        "user_wallet": user_wallet,
        "mode": "paper_preview",
    }


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "explain_agent",
            "description": "Explain this DeFi agent's role, pricing, and operating rules.",
            "parameters": {
                "type": "object",
                "properties": {"agent_slug": {"type": "string"}},
                "required": ["agent_slug"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "upsert_strategy",
            "description": "Create a paper/preview strategy with JSON params for this agent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_slug": {"type": "string"},
                    "params_json": {"type": "string", "description": "JSON object of strategy fields"},
                    "note": {"type": "string"},
                },
                "required": ["agent_slug"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_strategies",
            "description": "List saved strategies for the user, optionally filtered by agent_slug.",
            "parameters": {
                "type": "object",
                "properties": {"agent_slug": {"type": "string"}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_strategy_status",
            "description": "Pause, resume, or close a strategy by id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "strategy_id": {"type": "string"},
                    "status": {"type": "string", "description": "active | paused | closed"},
                },
                "required": ["strategy_id", "status"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "simulate_risk_check",
            "description": "Run a lightweight risk sanity check on proposed strategy params.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_slug": {"type": "string"},
                    "params_json": {"type": "string"},
                },
                "required": ["agent_slug"],
            },
        },
    },
]

TOOL_REGISTRY = {
    "explain_agent": explain_agent,
    "upsert_strategy": upsert_strategy,
    "list_strategies": list_strategies,
    "set_strategy_status": set_strategy_status,
    "simulate_risk_check": simulate_risk_check,
}


def _system_prompt(slug: str) -> str:
    meta = DEFI_AGENT_META[slug]
    return f"""You are **{meta['name']}** on Solana BIT Agents.

Focus: {meta['focus']}.
Fee guidance: {meta['pricing']}.

Rules:
- Help users design, review, pause, and update strategies in natural language.
- Use tools for strategy state. Do not invent fills, wallets, or on-chain balances.
- Execution is paper/preview unless a tool result says otherwise. Be explicit about that.
- Emphasize risk limits (size, slippage, health, leverage) before encouraging capital deployment.
- When the user pastes strategy params JSON, call upsert_strategy and simulate_risk_check.
- Keep replies concise and actionable.
"""


def run_defi_strategy_agent(
    agent_slug: str,
    user_input: str,
    conversation_history: list,
    user_wallet: Optional[str] = None,
    session_id: Optional[str] = None,
) -> tuple[str, list, list[dict[str, Any]]]:
    slug = (agent_slug or "").strip()
    if slug not in DEFI_AGENT_META:
        raise ValueError(f"Unknown DeFi agent slug: {agent_slug}")
    return run_tool_agent(
        user_input,
        conversation_history,
        system_prompt=_system_prompt(slug),
        tools=TOOLS,
        tool_registry=TOOL_REGISTRY,
        model=DEFI_MODEL,
        app_suffix=DEFI_AGENT_META[slug]["name"],
        user_wallet=user_wallet,
        session_id=session_id,
    )


def make_runner(agent_slug: str):
    def _runner(
        user_input: str,
        conversation_history: list,
        user_wallet: Optional[str] = None,
        session_id: Optional[str] = None,
    ):
        return run_defi_strategy_agent(
            agent_slug,
            user_input,
            conversation_history,
            user_wallet=user_wallet,
            session_id=session_id,
        )

    return _runner
