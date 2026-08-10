"""Shared tool-calling loop for research-style agents."""

from __future__ import annotations

import json
import os
import time
from typing import Any, Callable, Optional

from hosted_llm import call_llm

ToolFn = Callable[..., Any]

TOOL_ROUND_TIMING_LOG = os.environ.get("TOOL_ROUND_TIMING_LOG", "1").strip().lower() not in (
    "0",
    "false",
    "",
)

BATCH_TOOL_CALLS_INSTRUCTION = (
    "\n\nTool-use efficiency: each round trip to you is slow, so when you already know you need "
    "multiple independent pieces of data, request ALL of those tool calls together in a single "
    "response instead of one at a time across multiple turns. Only make a tool call alone if it "
    "depends on the result of a previous call."
)


def execute_tool(name: str, args: dict[str, Any], registry: dict[str, ToolFn], **ctx) -> str:
    fn = registry.get(name)
    if not fn:
        return json.dumps({"error": f"Unknown tool '{name}'."})
    try:
        result = fn(**args, **{k: v for k, v in ctx.items() if k in ("user_wallet", "session_id")})
        if isinstance(result, str):
            return result
        return json.dumps(result, indent=2, default=str)
    except TypeError as exc:
        return json.dumps({"error": str(exc), "received_args": args})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def run_tool_agent(
    user_input: str,
    conversation_history: list,
    *,
    system_prompt: str,
    tools: list,
    tool_registry: dict[str, ToolFn],
    model: str,
    app_suffix: str,
    user_wallet: Optional[str] = None,
    session_id: Optional[str] = None,
    max_rounds: int = 10,
) -> tuple[str, list, list[dict[str, Any]]]:
    actions: list[dict[str, Any]] = []
    prompt = user_input.strip()
    if user_wallet:
        prompt = f"[Connected user wallet: {user_wallet}]\n{prompt}"

    conversation_history.append({"role": "user", "content": prompt})
    effective_system_prompt = system_prompt + (BATCH_TOOL_CALLS_INSTRUCTION if tools else "")
    messages = [{"role": "system", "content": effective_system_prompt}] + conversation_history

    run_started = time.time()
    for round_num in range(1, max_rounds + 1):
        round_started = time.time()
        response = call_llm(
            messages,
            model=model,
            tools=tools,
            temperature=0.3,
            app_suffix=app_suffix,
        )
        message = response.get("message") or {}
        tool_calls = message.get("tool_calls") or []
        if TOOL_ROUND_TIMING_LOG:
            round_ms = int((time.time() - round_started) * 1000)
            print(
                f"  ⏱ {app_suffix or 'agent'} round {round_num}/{max_rounds}: "
                f"llm_ms={round_ms}, tool_calls={len(tool_calls)}"
            )
        if not tool_calls:
            reply = (message.get("content") or "").strip()
            if not reply and actions:
                reply = "I completed the requested checks. See tool results above."
            conversation_history.append({"role": "assistant", "content": reply})
            if TOOL_ROUND_TIMING_LOG:
                total_ms = int((time.time() - run_started) * 1000)
                print(f"  ⏱ {app_suffix or 'agent'} done: rounds={round_num}, total_ms={total_ms}")
            return reply, conversation_history, actions

        sanitized: list[dict[str, Any]] = []
        parsed: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        for idx, tc in enumerate(tool_calls):
            fn = tc.get("function") or {}
            name = fn.get("name", "")
            raw_args = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except json.JSONDecodeError:
                args = {}
            if not isinstance(args, dict):
                args = {}
            call_id = tc.get("id") or f"call_{idx}"
            sanitized.append(
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args, separators=(",", ":"))},
                }
            )
            parsed.append((name, args, tc))

        messages.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": sanitized})
        for name, args, tc in parsed:
            result = execute_tool(name, args, tool_registry, user_wallet=user_wallet, session_id=session_id)
            actions.append({"tool": name, "args": args, "result": result})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.get("id", "call"),
                    "tool_name": name,
                    "content": result,
                }
            )

    reply = "I hit the tool limit. Please ask a narrower question."
    conversation_history.append({"role": "assistant", "content": reply})
    if TOOL_ROUND_TIMING_LOG:
        total_ms = int((time.time() - run_started) * 1000)
        print(f"  ⏱ {app_suffix or 'agent'} hit max_rounds={max_rounds}, total_ms={total_ms}")
    return reply, conversation_history, actions
