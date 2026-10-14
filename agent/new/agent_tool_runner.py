"""Shared tool-calling loop for research-style agents."""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Callable, Optional

from hosted_llm import call_llm

_TEXT_TOOL_PREAMBLE = re.compile(
    r"the function call with its proper arguments that best answers the given prompt is\s*:?",
    re.IGNORECASE,
)

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


def _extract_json_objects(text: str) -> list[dict[str, Any]]:
    decoder = json.JSONDecoder()
    found: list[dict[str, Any]] = []
    idx = 0
    while idx < len(text):
        start = text.find("{", idx)
        if start < 0:
            break
        try:
            obj, end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            idx = start + 1
            continue
        if isinstance(obj, dict):
            found.append(obj)
        idx = start + end
    return found


def _recover_text_tool_calls(content: str, known_names: set[str]) -> list[dict[str, Any]]:
    """Llama on some OpenRouter routes prints a function call instead of using tool_calls."""
    if not content or not known_names:
        return []
    calls: list[dict[str, Any]] = []
    for obj in _extract_json_objects(content):
        name = obj.get("name")
        if not isinstance(name, str):
            fn = obj.get("function")
            if isinstance(fn, dict):
                name = fn.get("name")
        if not isinstance(name, str) or name not in known_names:
            continue
        args = obj.get("parameters", obj.get("arguments"))
        if args is None and isinstance(obj.get("function"), dict):
            args = obj["function"].get("arguments") or obj["function"].get("parameters")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        if not isinstance(args, dict):
            args = {}
        calls.append(
            {
                "id": f"call_text_{len(calls)}",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args, separators=(",", ":"))},
            }
        )
    if not calls:
        return []
    if _TEXT_TOOL_PREAMBLE.search(content):
        return calls
    leftover = content
    for obj in _extract_json_objects(content):
        raw = json.dumps(obj, separators=(",", ":"))
        pretty = json.dumps(obj)
        leftover = leftover.replace(raw, "").replace(pretty, "")
    leftover = re.sub(r"```(?:json)?", "", leftover).strip(" \n`")
    if leftover and len(leftover) > 80:
        return []
    return calls


def _reply_from_tool_result(actions: list[dict[str, Any]]) -> str:
    if not actions:
        return "I could not complete that request."
    raw = actions[-1].get("result") or ""
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return str(raw)[:1500]
    if not isinstance(data, dict):
        return str(raw)[:1500]
    if data.get("error"):
        return str(data["error"])
    if data.get("message"):
        return str(data["message"])
    markets = data.get("markets") or data.get("ranked")
    if isinstance(markets, list) and markets:
        lines = []
        for row in markets[:8]:
            if not isinstance(row, dict):
                continue
            name = row.get("protocol_name") or row.get("project") or "market"
            symbol = row.get("symbol") or ""
            kind = str(row.get("yield_type") or "").replace("_", " ")
            apy = row.get("apy")
            rate = f"{apy}% APY" if apy is not None else "APY unavailable"
            lines.append(f"- {name} {symbol} {kind}: {rate}".replace("  ", " ").strip())
        if lines:
            label = data.get("yield_type") or "yield"
            return f"{label} markets:\n" + "\n".join(lines)
    return json.dumps(data, indent=2, default=str)[:1500]


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
    provider: Optional[str] = None,
) -> tuple[str, list, list[dict[str, Any]]]:
    actions: list[dict[str, Any]] = []
    prompt = user_input.strip()
    if user_wallet:
        prompt = f"[Connected user wallet: {user_wallet}]\n{prompt}"

    conversation_history.append({"role": "user", "content": prompt})
    effective_system_prompt = system_prompt + (BATCH_TOOL_CALLS_INSTRUCTION if tools else "")
    messages = [{"role": "system", "content": effective_system_prompt}] + conversation_history

    run_started = time.time()
    seen_calls: set[str] = set()
    known_names = set(tool_registry)
    for round_num in range(1, max_rounds + 1):
        round_started = time.time()
        response = call_llm(
            messages,
            model=model,
            tools=tools,
            temperature=0.3,
            app_suffix=app_suffix,
            provider=provider,
        )
        message = response.get("message") or {}
        tool_calls = message.get("tool_calls") or []
        content = (message.get("content") or "").strip()
        if not tool_calls:
            tool_calls = _recover_text_tool_calls(content, known_names)
            if tool_calls:
                content = ""
        if TOOL_ROUND_TIMING_LOG:
            round_ms = int((time.time() - round_started) * 1000)
            print(
                f"  ⏱ {app_suffix or 'agent'} round {round_num}/{max_rounds}: "
                f"llm_ms={round_ms}, tool_calls={len(tool_calls)}"
            )
        if not tool_calls:
            reply = content
            if _TEXT_TOOL_PREAMBLE.search(reply) and actions:
                reply = _reply_from_tool_result(actions)
            if not reply and actions:
                reply = _reply_from_tool_result(actions)
            conversation_history.append({"role": "assistant", "content": reply})
            if TOOL_ROUND_TIMING_LOG:
                total_ms = int((time.time() - run_started) * 1000)
                print(f"  ⏱ {app_suffix or 'agent'} done: rounds={round_num}, total_ms={total_ms}")
            return reply, conversation_history, actions

        call_key = json.dumps(
            [
                {
                    "name": (tc.get("function") or {}).get("name"),
                    "arguments": (tc.get("function") or {}).get("arguments"),
                }
                for tc in tool_calls
            ],
            sort_keys=True,
        )
        if call_key in seen_calls and actions:
            reply = _reply_from_tool_result(actions)
            conversation_history.append({"role": "assistant", "content": reply})
            return reply, conversation_history, actions
        seen_calls.add(call_key)

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

        messages.append({"role": "assistant", "content": content, "tool_calls": sanitized})
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
