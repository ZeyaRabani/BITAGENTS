"""
Shared tool catalog for launched custom agents.

Custom agents never get generated code. They get a fixed, pre-built,
already-tested set of Python functions -- the exact same ones the
hand-coded agents (Token Research, Whale Tracking, DCA) already use in
production. An agent only ever chooses *which* of these to call and
*with what arguments*; it can never write or execute new code.

The agent-builder picks a subset of this catalog during the launch
conversation based on what the user describes needing, and stores the
selection as `custom_agents.enabled_tools`. custom_agent_runtime.py then
loads exactly that subset -- nothing more -- for the launched agent to use.

risk_tier:
  "read_only" -- no fund movement, safe to grant automatically, available
                 to every read_only-scope agent today.
  "trading"   -- moves user funds. Not wired into any runtime yet; listed
                 here as the target shape for when per-agent wallet
                 provisioning (Circle) lands. Never returned by
                 get_tool_registry() for a read_only-scope agent.
"""

from __future__ import annotations

from typing import Any, Callable

from dca_agent import resolve_token
from token_research_agent import compare_onchain_tokens, get_onchain_token_profile
from solana_wallet_tools import analyze_wallet_profile, get_wallet_recent_activity


def _lookup_token(**kwargs) -> dict[str, Any]:
    return resolve_token((kwargs.get("symbol_or_mint") or "").strip())


def _research_token(**kwargs) -> dict[str, Any]:
    return get_onchain_token_profile((kwargs.get("token") or "").strip())


def _compare_tokens(**kwargs) -> dict[str, Any]:
    tokens = kwargs.get("tokens") or []
    return compare_onchain_tokens([str(t).strip() for t in tokens if str(t).strip()])


def _analyze_wallet(**kwargs) -> dict[str, Any]:
    return analyze_wallet_profile((kwargs.get("address") or "").strip())


def _wallet_recent_activity(**kwargs) -> dict[str, Any]:
    address = (kwargs.get("address") or "").strip()
    limit = int(kwargs.get("limit") or 12)
    return get_wallet_recent_activity(address, limit)


class CatalogTool:
    def __init__(self, name: str, description: str, risk_tier: str, parameters: dict[str, Any], fn: Callable):
        self.name = name
        self.description = description
        self.risk_tier = risk_tier
        self.parameters = parameters
        self.fn = fn

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


CATALOG: dict[str, CatalogTool] = {
    tool.name: tool
    for tool in [
        CatalogTool(
            "lookup_token",
            "Resolve a token symbol or mint address to canonical info (mint, decimals, verified name).",
            "read_only",
            {
                "type": "object",
                "properties": {"symbol_or_mint": {"type": "string"}},
                "required": ["symbol_or_mint"],
            },
            _lookup_token,
        ),
        CatalogTool(
            "research_token",
            "Full on-chain research on a token: price, supply, holder distribution, liquidity, risk flags.",
            "read_only",
            {
                "type": "object",
                "properties": {"token": {"type": "string", "description": "Symbol or mint address"}},
                "required": ["token"],
            },
            _research_token,
        ),
        CatalogTool(
            "compare_tokens",
            "Compare on-chain fundamentals across 2-5 tokens side by side.",
            "read_only",
            {
                "type": "object",
                "properties": {"tokens": {"type": "array", "items": {"type": "string"}}},
                "required": ["tokens"],
            },
            _compare_tokens,
        ),
        CatalogTool(
            "analyze_wallet",
            "Profile a Solana wallet: holdings, activity level, notable patterns. Read-only, any wallet.",
            "read_only",
            {
                "type": "object",
                "properties": {"address": {"type": "string"}},
                "required": ["address"],
            },
            _analyze_wallet,
        ),
        CatalogTool(
            "wallet_recent_activity",
            "Recent transactions for a Solana wallet -- useful for watching/alerting on wallet movement.",
            "read_only",
            {
                "type": "object",
                "properties": {
                    "address": {"type": "string"},
                    "limit": {"type": "integer", "description": "Max transactions to return, default 12"},
                },
                "required": ["address"],
            },
            _wallet_recent_activity,
        ),
    ]
}


def catalog_summary_for_builder() -> str:
    """Human-readable catalog listing, injected into the builder agent's system prompt."""
    lines = []
    for tool in CATALOG.values():
        lines.append(f"- {tool.name} ({tool.risk_tier}): {tool.description}")
    return "\n".join(lines)


def valid_tool_names(names: list[str]) -> list[str]:
    return [n for n in names if n in CATALOG]


def get_tool_schemas(names: list[str], *, max_risk_tier: str = "read_only") -> list[dict[str, Any]]:
    allowed_tiers = {"read_only"} if max_risk_tier == "read_only" else {"read_only", "trading"}
    return [CATALOG[n].schema for n in names if n in CATALOG and CATALOG[n].risk_tier in allowed_tiers]


def get_tool_registry(names: list[str], *, max_risk_tier: str = "read_only") -> dict[str, Callable]:
    allowed_tiers = {"read_only"} if max_risk_tier == "read_only" else {"read_only", "trading"}
    return {n: CATALOG[n].fn for n in names if n in CATALOG and CATALOG[n].risk_tier in allowed_tiers}
