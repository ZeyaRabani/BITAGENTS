"""
Multi-turn tool-call smoke test for hosted Ollama.

Usage:
  cd agent/new
  python test_hosted_llm_tools.py
"""

from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

from hosted_llm import HOSTED_OLLAMA_MODEL, call_hosted_ollama, use_hosted_ollama

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "echo_plan",
            "description": "Echo a DCA plan summary back to the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "input_token": {"type": "string"},
                    "output_token": {"type": "string"},
                    "amount_per_buy": {"type": "number"},
                    "interval": {"type": "string"},
                    "max_executions": {"type": "integer"},
                },
                "required": ["input_token", "output_token", "amount_per_buy", "interval"],
            },
        },
    }
]


def main() -> None:
    if not use_hosted_ollama():
        raise SystemExit("HOSTED_MODEL_API_KEY is not set")

    messages = [
        {
            "role": "user",
            "content": (
                "Swap 0.00001 SOL to token iu3A7azWTm3zQSk81SUC1JctB4zPYnxLmcmqq71EASY "
                "every 10 sec for 1 trx. Call echo_plan with those values."
            ),
        }
    ]

    print("Round 1 …")
    first = call_hosted_ollama(messages, model=HOSTED_OLLAMA_MODEL, tools=TOOLS)
    message = first["message"]
    tool_calls = message.get("tool_calls") or []
    print("tool_calls:", json.dumps(tool_calls, indent=2))
    if not tool_calls:
        print("No tool calls returned:", message.get("content"))
        raise SystemExit(1)

    tc = tool_calls[0]
    fn = tc.get("function") or {}
    args = fn.get("arguments") or "{}"
    if isinstance(args, str):
        args = json.loads(args)

    messages.append({
        "role": "assistant",
        "content": message.get("content") or "",
        "tool_calls": tool_calls,
    })
    messages.append({
        "role": "tool",
        "tool_name": fn.get("name"),
        "tool_call_id": tc.get("id"),
        "content": json.dumps({"status": "ok", "args": args}, separators=(",", ":")),
    })

    print("Round 2 …")
    second = call_hosted_ollama(messages, model=HOSTED_OLLAMA_MODEL, tools=TOOLS)
    print(json.dumps(second, indent=2)[:1200])


if __name__ == "__main__":
    main()
