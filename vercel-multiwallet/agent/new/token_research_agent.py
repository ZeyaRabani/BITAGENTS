"""Token Research Agent - on-chain Solana token research (RPC + Jupiter + Meteora)."""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from agent_tool_runner import run_tool_agent
from hosted_llm import CAPIX_MODEL, DEFAULT_LLM_MODEL, call_llm, use_capix
from kickstart_copilot_agent import recommend_tools, search_tokens
from solana_token_onchain import (
    COMPARE_INTENT_RE,
    RESEARCH_INTENT_RE,
    TOKEN_RESEARCH_CACHE_TTL_SECONDS,
    cache_get_analysis,
    cache_set_analysis,
    extract_token_query,
    format_onchain_research_reply,
    format_unresolved_token_reply,
    get_onchain_mint_info,
    get_onchain_token_research,
    has_min_onchain_data,
)

TOKEN_RESEARCH_MODEL = (
    CAPIX_MODEL
    if use_capix()
    else os.environ.get(
        "TOKEN_RESEARCH_MODEL",
        os.environ.get("DCA_MODEL", os.environ.get("OPEN_ROUTER_MODEL", DEFAULT_LLM_MODEL)),
    )
)

ANALYSIS_SYSTEM_PROMPT = """You are a Solana token analyst. You receive JSON on-chain metrics already fetched from Solana RPC, Jupiter, and Meteora.

Write a concise **Token Analysis** section with:
1. **Summary** — what this token looks like based on the data (2-3 sentences)
2. **Strengths** — bullet points from verifiable metrics (authorities renounced, liquidity, holder base, etc.)
3. **Weaknesses / risks** — bullet points from the risks array and metrics (concentration, low liquidity, micro-cap, etc.)
4. **Verdict** — neutral, conditional recommendation (not financial advice)

Rules:
- Use ONLY numbers and facts from the provided JSON. Never invent data.
- If a field is null, say it is unavailable — do not guess.
- Keep the full analysis under 250 words.
- End with "Not financial advice. DYOR."
"""


def get_onchain_token_profile(token: str, holder_limit: int = 10) -> dict[str, Any]:
    result = get_onchain_token_research(token, holder_limit=holder_limit)
    if result.get("error"):
        return {
            **result,
            "query": token,
            "needs_mint_address": True,
            "instruction": (
                "Could not resolve this symbol on-chain. Ask the user for the Solana mint address "
                "and do not invent token metrics."
            ),
        }
    if not has_min_onchain_data(result):
        return {
            "error": "On-chain data incomplete for this identifier.",
            "query": token,
            "needs_mint_address": True,
            "instruction": "Ask the user for the exact mint address. Do not guess supply, price, or holders.",
        }
    return result


def _analysis_payload(profile: dict[str, Any]) -> dict[str, Any]:
    pool = profile.get("primary_pool") or {}
    return {
        "symbol": profile.get("symbol"),
        "name": profile.get("name"),
        "mint": profile.get("mint"),
        "price_usd": profile.get("price_usd"),
        "market_cap_usd": profile.get("market_cap_usd"),
        "total_supply": profile.get("total_supply"),
        "holder_count": profile.get("holder_count"),
        "top3_holder_pct": profile.get("top3_holder_pct"),
        "mint_authority_renounced": profile.get("mint_authority_renounced"),
        "freeze_authority_renounced": profile.get("freeze_authority_renounced"),
        "pool_tvl_usd": pool.get("liquidity_usd"),
        "pool_volume_24h_usd": pool.get("volume_24h_usd"),
        "risks": profile.get("risks") or [],
        "cached_metrics": profile.get("cached"),
    }


def generate_token_analysis(profile: dict[str, Any], holder_limit: int = 10) -> str:
    mint = str(profile.get("mint") or "")
    if not mint:
        return ""

    cached = cache_get_analysis(mint, holder_limit)
    if cached:
        return cached

    try:
        response = call_llm(
            [
                {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Analyze this token using only the JSON metrics below:\n\n"
                        + json.dumps(_analysis_payload(profile), indent=2, default=str)
                    ),
                },
            ],
            model=TOKEN_RESEARCH_MODEL,
            temperature=0.35,
            app_suffix="Token Research Analysis",
        )
        analysis = ((response.get("message") or {}).get("content") or "").strip()
    except Exception as exc:
        analysis = f"_Analysis unavailable ({exc}). Review the on-chain metrics above._"

    if analysis:
        cache_set_analysis(mint, holder_limit, analysis)
    return analysis


def build_full_research_reply(profile: dict[str, Any], holder_limit: int = 10) -> str:
    metrics = format_onchain_research_reply(profile)
    if profile.get("error") or not has_min_onchain_data(profile):
        return metrics

    analysis = generate_token_analysis(profile, holder_limit=holder_limit)
    if not analysis:
        return metrics

    return f"{metrics}\n\n---\n\n**Token Analysis**\n\n{analysis}"


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_onchain_token_profile",
            "description": (
                "PRIMARY tool. Full on-chain research brief: mint/supply, Jupiter price, "
                "Meteora pool liquidity, top holders via Solana RPC. Cached 15 minutes per mint."
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
            "name": "get_onchain_mint_info",
            "description": "Mint account details from Solana RPC: supply, decimals, mint/freeze authority.",
            "parameters": {"type": "object", "properties": {"token": {"type": "string"}}, "required": ["token"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_tokens",
            "description": "Search Jupiter/EASY Screener to resolve ambiguous token names to a mint.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                    "verified_only": {"type": "boolean"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_onchain_tokens",
            "description": "Compare 2-5 tokens using on-chain profiles.",
            "parameters": {
                "type": "object",
                "properties": {"tokens": {"type": "array", "items": {"type": "string"}}},
                "required": ["tokens"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recommend_tools",
            "description": "Recommend Solana tools for a research task.",
            "parameters": {"type": "object", "properties": {"task": {"type": "string"}}, "required": ["task"]},
        },
    },
]


def compare_onchain_tokens(tokens: list[str]) -> dict[str, Any]:
    if not tokens or len(tokens) < 2:
        return {"error": "Provide at least two tokens (symbol or mint) to compare."}
    rows = []
    for token in tokens[:5]:
        profile = get_onchain_token_profile(token)
        if profile.get("error"):
            return profile
        rows.append(profile)
    return {"count": len(rows), "comparison": rows, "source": "solana_rpc + jupiter + meteora"}


TOOL_REGISTRY = {
    "get_onchain_token_profile": get_onchain_token_profile,
    "get_onchain_mint_info": get_onchain_mint_info,
    "search_tokens": search_tokens,
    "compare_onchain_tokens": compare_onchain_tokens,
    "recommend_tools": recommend_tools,
}

SYSTEM_PROMPT = f"""You are **Token Research Agent** on Solana.

On-chain metrics are cached **{TOKEN_RESEARCH_CACHE_TTL_SECONDS // 60} minutes** per mint (shared across users).

Rules:
- Always call `get_onchain_token_profile` first when the user asks about a specific token.
- If the tool returns `needs_mint_address: true` or an error, ask the user for the **Solana mint address** and stop.
- Never fabricate metrics. Only report fields present in tool JSON output.
"""


def _research_action(token: str, profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "tool": "get_onchain_token_profile",
        "args": {"token": token},
        "result": json.dumps(profile, indent=2, default=str),
    }


def _direct_onchain_research(user_input: str) -> Optional[tuple[str, list[dict[str, Any]]]]:
    if COMPARE_INTENT_RE.search(user_input):
        return None
    token = extract_token_query(user_input)
    if not token:
        return None
    if not RESEARCH_INTENT_RE.search(user_input) and not _looks_like_mint(token):
        return None

    result = get_onchain_token_research(token)
    action = _research_action(token, result)
    if result.get("error") or not has_min_onchain_data(result):
        reply = format_unresolved_token_reply(token, result if isinstance(result, dict) else None)
    else:
        reply = build_full_research_reply(result)
    return reply, [action]


def _looks_like_mint(value: str) -> bool:
    value = (value or "").strip()
    return 32 <= len(value) <= 44


def _reply_from_profile_actions(actions: list[dict[str, Any]], llm_reply: str) -> str:
    for action in reversed(actions):
        if action.get("tool") != "get_onchain_token_profile":
            continue
        try:
            data = json.loads(action.get("result") or "{}")
        except json.JSONDecodeError:
            continue
        if data.get("error") or data.get("needs_mint_address"):
            query = str(data.get("query") or (action.get("args") or {}).get("token") or "this token")
            return format_unresolved_token_reply(query, data)
        if has_min_onchain_data(data):
            holder_limit = int((action.get("args") or {}).get("holder_limit") or 10)
            return build_full_research_reply(data, holder_limit=holder_limit)
    return llm_reply


def run_token_research_agent(
    user_input: str,
    conversation_history: list,
    user_wallet: Optional[str] = None,
    session_id: Optional[str] = None,
) -> tuple[str, list, list[dict[str, Any]]]:
    prompt = user_input.strip()

    direct = _direct_onchain_research(prompt)
    if direct:
        reply, actions = direct
        conversation_history.append({"role": "user", "content": prompt})
        conversation_history.append({"role": "assistant", "content": reply})
        return reply, conversation_history, actions

    reply, history, actions = run_tool_agent(
        prompt,
        conversation_history,
        system_prompt=SYSTEM_PROMPT,
        tools=TOOLS,
        tool_registry=TOOL_REGISTRY,
        model=TOKEN_RESEARCH_MODEL,
        app_suffix="Token Research",
        user_wallet=user_wallet,
        session_id=session_id,
    )

    synthesized = _reply_from_profile_actions(actions, reply)
    if synthesized != reply:
        history[-1] = {"role": "assistant", "content": synthesized}
        reply = synthesized
    return reply, history, actions
