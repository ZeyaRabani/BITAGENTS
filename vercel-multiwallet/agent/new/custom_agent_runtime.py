"""
Runtime for launched custom (user-created) agents.

Every hand-coded agent in this repo (dca_agent.py, volume_agent.py, ...) is a
thin wrapper around agent_tool_runner.run_tool_agent() with its own hardcoded
system prompt and tools. A custom agent is the same runtime, just loaded
dynamically from its `custom_agents` DB row instead of hardcoded in a file.

Tool access comes from agent_tool_catalog.py, filtered to the agent's own
`enabled_tools` selection (chosen by the builder conversation) AND capped by
`tool_scope`. A "trading" tool_scope does NOT currently grant any trading
tools -- the catalog has none registered above "read_only" yet, so this is
enforced defense-in-depth even once trading tools exist: get_tool_registry()
still won't return them for a scope this file doesn't explicitly widen.
"""

from __future__ import annotations

from typing import Any, Optional

import db
from agent_tool_runner import run_tool_agent
from agent_tool_catalog import get_tool_registry, get_tool_schemas

CUSTOM_AGENT_MODEL_BY_TIER = {
    "fast": "openai/gpt-4o-mini",
    "balanced": "openai/gpt-4o-mini",
    "reasoning": "openai/gpt-4o",
}


def run_custom_agent(
    agent_id: str,
    user_input: str,
    conversation_history: list,
    *,
    session_id: Optional[str] = None,
) -> tuple[str, list, list[dict[str, Any]]]:
    agent = db.get_custom_agent(agent_id)
    if not agent:
        return "This agent no longer exists.", conversation_history, []
    if agent["status"] not in ("testing", "live"):
        return "This agent hasn't launched yet.", conversation_history, []

    model = CUSTOM_AGENT_MODEL_BY_TIER.get(agent.get("model_tier") or "balanced", CUSTOM_AGENT_MODEL_BY_TIER["balanced"])
    system_prompt = agent.get("system_prompt") or "You are a helpful assistant."
    enabled_tools = agent.get("enabled_tools") or []
    tool_scope = agent.get("tool_scope") or "read_only"

    reply, history, actions = run_tool_agent(
        user_input,
        conversation_history,
        system_prompt=system_prompt,
        tools=get_tool_schemas(enabled_tools, max_risk_tier=tool_scope),
        tool_registry=get_tool_registry(enabled_tools, max_risk_tier=tool_scope),
        model=model,
        app_suffix=f"custom-{agent['handle'] or agent_id[:8]}",
        session_id=session_id,
    )
    db.record_custom_agent_run(agent_id)
    return reply, history, actions
