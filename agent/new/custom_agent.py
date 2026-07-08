"""
Custom prompt agents (Phase 1: MVP) - user-authored system prompt, plain chat.

No tool-calling / function execution yet - the agent can only converse using
whatever the user's system prompt instructs. Transactional/tool-using
capabilities are a later phase.
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional

import requests

from dca_agent import (
    OPEN_ROUTER_API,
    OPEN_ROUTER_API_URL,
    OPEN_ROUTER_APP_NAME,
    OPEN_ROUTER_SITE_URL,
)

CUSTOM_AGENT_DEFAULT_MODEL = os.environ.get(
    "CUSTOM_AGENT_MODEL",
    os.environ.get("OPEN_ROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct"),
)

MAX_HISTORY_MESSAGES = 20


def _openrouter_headers() -> dict[str, str]:
    if not OPEN_ROUTER_API:
        raise RuntimeError("OPEN_ROUTER_API is not set in agent/new/.env")
    return {
        "Authorization": f"Bearer {OPEN_ROUTER_API}",
        "Content-Type": "application/json",
        "HTTP-Referer": OPEN_ROUTER_SITE_URL,
        "X-Title": f"{OPEN_ROUTER_APP_NAME} Custom Agent",
    }


def call_openrouter(messages: list, model: str) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.4,
    }
    last_error = "Unknown OpenRouter error"
    for attempt in range(1, 4):
        try:
            resp = requests.post(
                OPEN_ROUTER_API_URL,
                json=payload,
                headers=_openrouter_headers(),
                timeout=180,
            )
        except requests.exceptions.RequestException as exc:
            last_error = str(exc)
            if attempt < 3:
                time.sleep(1.5 * attempt)
                continue
            raise RuntimeError(f"Cannot reach OpenRouter API: {last_error}") from exc
        if resp.status_code >= 400:
            last_error = resp.text or resp.reason
            if resp.status_code in (408, 429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(1.5 * attempt)
                continue
            raise RuntimeError(f"OpenRouter API error ({resp.status_code}): {last_error}")
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("OpenRouter returned no choices.")
        return choices[0]
    raise RuntimeError(last_error)


def run_custom_agent(
    system_prompt: str,
    user_message: str,
    history: Optional[list[dict[str, str]]] = None,
    model: Optional[str] = None,
) -> str:
    normalized_history: list[dict[str, str]] = []
    for msg in (history or [])[-MAX_HISTORY_MESSAGES:]:
        role = (msg.get("role") or "").strip()
        content = (msg.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            normalized_history.append({"role": role, "content": content})

    messages = (
        [{"role": "system", "content": system_prompt}]
        + normalized_history
        + [{"role": "user", "content": user_message.strip()}]
    )

    choice = call_openrouter(messages, model or CUSTOM_AGENT_DEFAULT_MODEL)
    message = choice.get("message") or {}
    return message.get("content") or ""
