"""Due Diligence Agent — on-chain token risk assessment on Solana."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

from agent_tool_runner import run_tool_agent
from cache_store import get_json, set_json
from hosted_llm import CAPIX_MODEL, DEFAULT_LLM_MODEL, call_llm, use_capix
from kickstart_copilot_agent import search_tokens
from solana_token_diligence import (
    extract_diligence_query,
    format_due_diligence_reply,
    get_mint_authorities,
    run_due_diligence_report,
)
from solana_token_onchain import (
    TOKEN_RESEARCH_CACHE_TTL_SECONDS,
    format_unresolved_token_reply,
    get_onchain_mint_info,
    get_token_research_cache_stats,
    has_min_onchain_data,
)

DUE_DILIGENCE_MODEL = (
    CAPIX_MODEL
    if use_capix()
    else os.environ.get(
        "DUE_DILIGENCE_MODEL",
        os.environ.get("DCA_MODEL", os.environ.get("OPEN_ROUTER_MODEL", DEFAULT_LLM_MODEL)),
    )
)

DILIGENCE_INTENT_RE = re.compile(
    r"\b("
    r"due diligence|diligence|vet|audit|risk score|risk assessment|"
    r"mint authority|freeze authority|safe to buy|is it safe|"
    r"holder concentration|top holders|concentration"
    r")\b",
    re.I,
)

_DILIGENCE_ANALYSIS_PREFIX = "diligence:analysis:"


def _analysis_cache_get(mint: str) -> Optional[str]:
    value = get_json(f"{_DILIGENCE_ANALYSIS_PREFIX}{mint.strip()}")
    return value if isinstance(value, str) else None


def _analysis_cache_set(mint: str, text: str) -> None:
    set_json(
        f"{_DILIGENCE_ANALYSIS_PREFIX}{mint.strip()}",
        text,
        TOKEN_RESEARCH_CACHE_TTL_SECONDS,
    )


def _generate_diligence_analysis(report: dict[str, Any]) -> str:
    mint = str(report.get("mint") or "")
    if not mint:
        return ""

    cached = _analysis_cache_get(mint)
    if cached:
        return cached

    payload = {
        "symbol": report.get("symbol"),
        "mint": mint,
        "due_diligence_score": report.get("due_diligence_score"),
        "grade": report.get("grade"),
        "findings": report.get("findings"),
        "risks": report.get("risks"),
        "authorities": report.get("authorities"),
        "analytics": report.get("analytics"),
        "top3_holder_pct": report.get("top3_holder_pct"),
    }
    try:
        response = call_llm(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a Solana token due diligence analyst. Given JSON from Solana RPC, write a "
                        "**Due Diligence Assessment** with: Summary, Authority risks, Liquidity/holder risks, "
                        "Grade rationale, Conditional recommendation. Use ONLY provided data. Under 250 words. "
                        "Never call a token 'safe'. Not financial advice."
                    ),
                },
                {"role": "user", "content": json.dumps(payload, indent=2, default=str)},
            ],
            model=DUE_DILIGENCE_MODEL,
            temperature=0.35,
            app_suffix="Due Diligence Analysis",
        )
        text = ((response.get("message") or {}).get("content") or "").strip()
    except Exception as exc:
        text = f"_Analysis unavailable ({exc}). Review the on-chain report above._"

    if text:
        _analysis_cache_set(mint, text)
    return text


def build_full_diligence_reply(report: dict[str, Any]) -> str:
    metrics = format_due_diligence_reply(report)
    if report.get("error") or report.get("needs_mint_address"):
        return metrics
    analysis = _generate_diligence_analysis(report)
    return f"{metrics}\n\n---\n\n**Due Diligence Assessment**\n\n{analysis}"


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_due_diligence_report",
            "description": (
                "PRIMARY tool. Full on-chain due diligence: authorities, holders, liquidity, risk score. "
                "Uses shared 15-minute cache per mint (same data as Token Research Agent)."
            ),
            "parameters": {
                "type": "object",
                "properties": {"token": {"type": "string"}, "holder_limit": {"type": "integer"}},
                "required": ["token"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_mint_authorities",
            "description": "Mint and freeze authority from Solana RPC.",
            "parameters": {"type": "object", "properties": {"token": {"type": "string"}}, "required": ["token"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_onchain_mint_info",
            "description": "Mint account details: supply, decimals, authorities.",
            "parameters": {"type": "object", "properties": {"token": {"type": "string"}}, "required": ["token"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_tokens",
            "description": "Search tokens to resolve ambiguous symbols to a mint.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
                "required": ["query"],
            },
        },
    },
]

TOOL_REGISTRY = {
    "run_due_diligence_report": run_due_diligence_report,
    "get_mint_authorities": get_mint_authorities,
    "get_onchain_mint_info": get_onchain_mint_info,
    "search_tokens": search_tokens,
}

SYSTEM_PROMPT = f"""You are **Due Diligence Agent** on Solana.

On-chain token data is cached **{TOKEN_RESEARCH_CACHE_TTL_SECONDS // 60} minutes** per mint (shared with Token Research Agent).

Rules:
- Always call `run_due_diligence_report` first when vetting a specific token.
- If the tool returns `needs_mint_address: true`, ask for the **Solana mint address** and stop.
- Never fabricate mint addresses, authorities, liquidity, or holder percentages.
- Use graded assessments (A-D) — never approve a token as "safe".
- This is not a formal audit.
"""


def _diligence_action(token: str, report: dict[str, Any]) -> dict[str, Any]:
    return {
        "tool": "run_due_diligence_report",
        "args": {"token": token},
        "result": json.dumps(report, indent=2, default=str),
    }


def _try_diligence_shortcut(user_input: str) -> Optional[tuple[str, list[dict[str, Any]]]]:
    if not DILIGENCE_INTENT_RE.search(user_input):
        return None

    token = extract_diligence_query(user_input)
    if not token:
        return None

    report = run_due_diligence_report(token)
    action = _diligence_action(token, report)
    if report.get("error") or report.get("needs_mint_address"):
        reply = format_unresolved_token_reply(token, report)
    else:
        reply = build_full_diligence_reply(report)
    return reply, [action]


def _reply_from_diligence_actions(actions: list[dict[str, Any]], llm_reply: str) -> str:
    for action in reversed(actions):
        if action.get("tool") != "run_due_diligence_report":
            continue
        try:
            data = json.loads(action.get("result") or "{}")
        except json.JSONDecodeError:
            continue
        if data.get("error") or data.get("needs_mint_address"):
            query = str(data.get("query") or (action.get("args") or {}).get("token") or "this token")
            return format_unresolved_token_reply(query, data)
        return build_full_diligence_reply(data)
    return llm_reply


def run_due_diligence_agent(
    user_input: str,
    conversation_history: list,
    user_wallet: Optional[str] = None,
    session_id: Optional[str] = None,
) -> tuple[str, list, list[dict[str, Any]]]:
    prompt = user_input.strip()

    shortcut = _try_diligence_shortcut(prompt)
    if shortcut:
        reply, actions = shortcut
        conversation_history.append({"role": "user", "content": prompt})
        conversation_history.append({"role": "assistant", "content": reply})
        return reply, conversation_history, actions

    reply, history, actions = run_tool_agent(
        prompt,
        conversation_history,
        system_prompt=SYSTEM_PROMPT,
        tools=TOOLS,
        tool_registry=TOOL_REGISTRY,
        model=DUE_DILIGENCE_MODEL,
        app_suffix="Due Diligence",
        user_wallet=user_wallet,
        session_id=session_id,
    )

    synthesized = _reply_from_diligence_actions(actions, reply)
    if synthesized != reply:
        history[-1] = {"role": "assistant", "content": synthesized}
        reply = synthesized
    return reply, history, actions


def get_due_diligence_cache_stats() -> dict[str, Any]:
    return get_token_research_cache_stats()
