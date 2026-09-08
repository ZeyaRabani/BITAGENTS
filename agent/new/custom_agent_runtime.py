"""
Runtime for launched custom (user-created) agents.

Every hand-coded agent in this repo (dca_agent.py, volume_agent.py, ...) is a
thin wrapper around agent_tool_runner.run_tool_agent() with its own hardcoded
system prompt and tools. A custom agent is the same runtime, just loaded
dynamically from its `custom_agents` DB row instead of hardcoded in a file.

Scope for this first pass: custom agents run on their creator-authored system
prompt only, with no tool access — no trading, no wallet, no fund movement,
regardless of a "trading" tool_scope, until a reviewed, explicitly-whitelisted
tool set is wired in per agent. tool_scope is enforced at the visibility layer
(who can chat with it, see custom_agent_routes below) and at the future point
trading tools are added — not by this file granting anything today.
"""

from __future__ import annotations

from typing import Any, Optional

import db
from agent_tool_runner import run_tool_agent

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

    reply, history, actions = run_tool_agent(
        user_input,
        conversation_history,
        system_prompt=system_prompt,
        tools=[],
        tool_registry={},
        model=model,
        app_suffix=f"custom-{agent['handle'] or agent_id[:8]}",
        session_id=session_id,
    )
    db.record_custom_agent_run(agent_id)
    return reply, history, actions
