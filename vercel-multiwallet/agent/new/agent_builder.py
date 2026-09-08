"""
Conversational agent-builder — the "meta-agent" behind /launch/create.

Users describe the agent they want in plain English; this agent asks natural
follow-up questions and progressively fills in a draft `custom_agents` row via
tool calls, writing the resulting agent's system prompt itself rather than
asking the user to write one. It proposes the finished draft and only calls
finalize_and_launch() after the user explicitly confirms — same
propose-then-confirm pattern already used by the Hedge Fund agent's strategy
proposals.

No trading/wallet tools live here — this agent only edits its own draft row.
"""

from __future__ import annotations

from typing import Any, Optional

import db
from agent_tool_runner import run_tool_agent
from agent_tool_catalog import catalog_summary_for_builder, valid_tool_names

BUILDER_MODEL = "openai/gpt-4o-mini"

CATEGORIES = ("Trading", "Research", "Monitoring", "Utility")
TOOL_SCOPES = ("read_only", "trading")

def _build_system_prompt() -> str:
    return f"""You are the BITAGENTS agent-builder — you help someone launch a new AI agent \
on the marketplace by having a natural, open-ended conversation. You are not a form; do not \
demand fields in a fixed order. Ask whatever follow-up questions make sense given what they've \
told you so far.

Your job across the conversation:
1. Understand what the agent should actually do — its purpose, what it watches/researches/trades, \
   any limits or rules it should follow.
2. Figure out a short name and a lowercase handle (like a username, no "$" prefix — this is not a \
   token) for it.
3. Pick the best-fitting category: Trading, Research, Monitoring, or Utility.
4. Write a one-sentence public description (shown on its marketplace card).
5. Write the actual system prompt the launched agent will run on — this is the most important part. \
   The user will rarely write a good one themselves; that's your job. Write it in second person \
   ("You are..."), specific about behavior, tone, and any limits, based on what they told you.
6. Determine tool_scope: ask directly whether this agent needs to move user funds or execute trades. \
   If yes, tool_scope is "trading" (explain this requires manual review before it can go live with \
   real funds — this capability isn't wired up yet, so say the agent will launch read-only for now \
   and trading comes later). If it only researches, monitors, or advises, tool_scope is "read_only" \
   (launches automatically after a 24h testing window, no review needed). Default to read_only.
7. Pick which real capabilities the agent needs from this fixed catalog — never invent a tool name \
   that isn't listed here, and never suggest the agent can execute custom code:

{catalog_summary_for_builder()}

   Infer which of these fit from what the user described (e.g. "watches whale wallets" needs \
   analyze_wallet + wallet_recent_activity; "researches a token before I buy" needs lookup_token + \
   research_token). Call select_agent_capabilities with your chosen list, then say in plain language \
   what you gave it and why — never show this as a checklist, just narrate it naturally. If nothing \
   in the catalog fits, that's fine — the agent can still be a pure conversational advisor.

Call set_agent_field / set_agent_personality / set_tool_scope / select_agent_capabilities as you \
learn each piece — don't wait until the end to set everything at once. Use show_draft whenever you \
want to check what's already been captured before asking your next question.

When you believe the draft is complete, call show_draft, present the full configuration clearly to \
the user (name, handle, category, description, the system prompt you wrote, which capabilities it \
has, and whether it's read_only or trading), and explicitly ask them to confirm before launching. \
Only call finalize_and_launch after they clearly confirm (e.g. "yes", "launch it", "confirm") — \
never call it speculatively or before showing the draft."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "set_agent_field",
            "description": "Set a single top-level field on the draft agent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "field": {
                        "type": "string",
                        "enum": ["name", "handle", "category", "description"],
                    },
                    "value": {"type": "string"},
                },
                "required": ["field", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_agent_personality",
            "description": (
                "Write/update the system prompt the launched agent will actually run on. "
                "You write this on the user's behalf based on the conversation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "system_prompt": {"type": "string"},
                },
                "required": ["system_prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_tool_scope",
            "description": (
                "Set whether this agent is read_only (research/monitoring, launches automatically) "
                "or trading (can move user funds, requires manual review before going live)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_scope": {"type": "string", "enum": list(TOOL_SCOPES)},
                },
                "required": ["tool_scope"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "select_agent_capabilities",
            "description": (
                "Set which tools from the fixed catalog this agent can use. Replaces any "
                "previous selection. Pass an empty list for a pure conversational agent."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_names": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["tool_names"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_draft",
            "description": "Return the current state of the draft agent so you can check what's already set.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finalize_and_launch",
            "description": (
                "Finalize the draft and move it into the 24h testing window. Only call this after "
                "showing the user the full draft and receiving explicit confirmation."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def _builder_tools(agent_id: str) -> dict[str, Any]:
    def set_agent_field(**kwargs):
        field = (kwargs.get("field") or "").strip()
        value = (kwargs.get("value") or "").strip()
        if field not in ("name", "handle", "category", "description"):
            return {"error": f"Unknown field: {field}"}
        if field == "category" and value not in CATEGORIES:
            return {"error": f"category must be one of {CATEGORIES}"}
        if field == "handle":
            value = value.lower().lstrip("$").replace(" ", "-")[:40]
        updated = db.update_custom_agent_fields(agent_id, **{field: value})
        return {"ok": True, "draft": updated}

    def set_agent_personality(**kwargs):
        prompt = (kwargs.get("system_prompt") or "").strip()
        if not prompt:
            return {"error": "system_prompt cannot be empty"}
        updated = db.update_custom_agent_fields(agent_id, system_prompt=prompt)
        return {"ok": True, "draft": updated}

    def set_tool_scope(**kwargs):
        scope = (kwargs.get("tool_scope") or "").strip()
        if scope not in TOOL_SCOPES:
            return {"error": f"tool_scope must be one of {TOOL_SCOPES}"}
        updated = db.update_custom_agent_fields(agent_id, tool_scope=scope)
        return {"ok": True, "draft": updated}

    def select_agent_capabilities(**kwargs):
        requested = kwargs.get("tool_names") or []
        valid = valid_tool_names([str(n).strip() for n in requested])
        invalid = [n for n in requested if n not in valid]
        updated = db.update_custom_agent_fields(agent_id, enabled_tools=valid)
        result = {"ok": True, "enabled_tools": valid, "draft": updated}
        if invalid:
            result["ignored_unknown_tools"] = invalid
        return result

    def show_draft(**_kwargs):
        return db.get_custom_agent(agent_id) or {"error": "draft not found"}

    def finalize_and_launch(**_kwargs):
        draft = db.get_custom_agent(agent_id)
        if not draft:
            return {"error": "draft not found"}
        missing = [
            f for f in ("name", "handle", "category", "description", "system_prompt")
            if not (draft.get(f) or "").strip()
        ]
        if missing:
            return {"error": f"Cannot launch yet, missing: {', '.join(missing)}"}
        finalized = db.finalize_custom_agent(agent_id)
        if not finalized:
            return {"error": "Could not finalize — draft may already be launched."}
        return {"ok": True, "agent": finalized, "status": finalized["status"]}

    return {
        "set_agent_field": set_agent_field,
        "set_agent_personality": set_agent_personality,
        "set_tool_scope": set_tool_scope,
        "select_agent_capabilities": select_agent_capabilities,
        "show_draft": show_draft,
        "finalize_and_launch": finalize_and_launch,
    }


def run_builder_agent(
    user_input: str,
    conversation_history: list,
    *,
    agent_id: str,
    session_id: Optional[str] = None,
) -> tuple[str, list, list[dict[str, Any]]]:
    return run_tool_agent(
        user_input,
        conversation_history,
        system_prompt=_build_system_prompt(),
        tools=TOOLS,
        tool_registry=_builder_tools(agent_id),
        model=BUILDER_MODEL,
        app_suffix="agent-builder",
        session_id=session_id,
    )
