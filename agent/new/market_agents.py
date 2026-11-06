"""Hedge Fund and Sniper agents.

Both trade from their own Circle wallet. Jupiter builds the swap, Aomi
simulates it, and Circle signs only after that commit.
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from typing import Any, Optional

from circle_dca_wallets import resolve_agent_signing_context
from dca_agent import (
    DCA_LLM_PROVIDER,
    MODEL,
    SOLANA_CLUSTER,
    _build_and_execute_swap,
    _is_mainnet,
    SOLANA_RPC,
    _lamports,
    _redact_rpc_url,
    get_jupiter_quote,
    resolve_token,
    sol_rpc,
)
from hosted_llm import call_llm

AGENTS: dict[str, dict[str, str]] = {
    "hedge-fund": {
        "agent_type": "hedge_fund",
        "name": "Hedge Fund Agent",
        "focus": "sized Jupiter buys and sells from this agent's Circle wallet",
    },
    "sniper": {
        "agent_type": "sniper",
        "name": "Sniper Agent",
        "focus": "SOL entries into a token after a renounce check, size cap, and Aomi simulation",
    },
}

_LOCK = threading.Lock()
_pending: dict[str, dict[str, Any]] = {}
_sniper_settings: dict[str, dict[str, Any]] = {}

_BUY = re.compile(
    r"\b(?:buy|snipe|swap)\s+([0-9]*\.?[0-9]+)\s*sol\s+(?:into|of|for|to)\s+([A-Za-z0-9]+)",
    re.I,
)
_SELL = re.compile(
    r"\bsell\s+([0-9]*\.?[0-9]+)\s+([A-Za-z0-9]+)\s+(?:to|for|into)\s+sol\b",
    re.I,
)
_MAX_BUY = re.compile(r"\bmax buy(?:\s+to)?\s+([0-9]*\.?[0-9]+)", re.I)
_SLIP = re.compile(r"\b(?:max )?slip(?:page)?(?:\s+to)?\s+([0-9]+)\s*(?:bps)?", re.I)
_CONFIRM = re.compile(r"\b(yes|confirm|proceed|go ahead|do it)\b", re.I)
_DECLINE = re.compile(r"\b(no|cancel|stop)\b", re.I)


def agent_spec(slug: str) -> Optional[dict[str, str]]:
    return AGENTS.get((slug or "").strip().lower())


def _key(slug: str, session_id: Optional[str], user_wallet: str) -> str:
    return f"{slug}:{(session_id or user_wallet).strip()}"


def _settings(user_wallet: str) -> dict[str, Any]:
    current = _sniper_settings.get(user_wallet)
    if current is None:
        current = {"max_buy_sol": 0.5, "slippage_bps": 300, "require_renounced": True}
        _sniper_settings[user_wallet] = current
    return current


def wallet_status(slug: str, user_wallet: str) -> dict[str, Any]:
    spec = agent_spec(slug)
    if not spec:
        return {"error": "Unknown agent."}
    signing = resolve_agent_signing_context(user_wallet, spec["agent_type"])
    pubkey = signing.get("pubkey")
    sol = None
    if pubkey:
        try:
            sol = int(sol_rpc("getBalance", [pubkey]).get("value") or 0) / 1_000_000_000
        except Exception as exc:
            sol = None
            balance_error = str(exc)
        else:
            balance_error = None
    else:
        balance_error = "Circle wallet is not available for this agent."
    return {
        "agent": spec["name"],
        "agent_type": spec["agent_type"],
        "agent_wallet": pubkey,
        "wallet_provider": signing.get("mode"),
        "sol_balance": sol,
        "balance_error": balance_error,
        "cluster": SOLANA_CLUSTER,
        "execution": "jupiter build, aomi simulate, circle sign",
        "rpc_url": _redact_rpc_url(SOLANA_RPC),
    }


def _mint_authorities(mint: str) -> dict[str, Any]:
    info = sol_rpc("getAccountInfo", [mint, {"encoding": "jsonParsed"}])
    value = (info or {}).get("value") or {}
    parsed = ((value.get("data") or {}).get("parsed") or {}).get("info") or {}
    return {
        "mint_authority": parsed.get("mintAuthority"),
        "freeze_authority": parsed.get("freezeAuthority"),
    }


def _sol_balance(pubkey: str) -> int:
    return int(sol_rpc("getBalance", [pubkey]).get("value") or 0)


def execute_market_swap(
    slug: str,
    user_wallet: str,
    input_token: str,
    output_token: str,
    amount: float,
    slippage_bps: int,
    *,
    require_renounced: bool = False,
) -> dict[str, Any]:
    spec = agent_spec(slug)
    if not spec:
        return {"error": "Unknown agent."}
    if not _is_mainnet():
        return {"error": "These agents swap on mainnet. Set SOLANA_CLUSTER to mainnet."}
    signing = resolve_agent_signing_context(user_wallet, spec["agent_type"])
    pubkey = signing.get("pubkey")
    if not pubkey or signing.get("mode") not in {"circle", "local"}:
        return {"error": "No Circle wallet is available for this agent."}
    circle_wallet_id = signing.get("wallet_id") if signing.get("mode") == "circle" else None
    keypair = signing.get("keypair") if signing.get("mode") == "local" else None

    amount = float(amount)
    if amount <= 0:
        return {"error": "Amount must be greater than zero."}
    slippage_bps = max(1, min(int(slippage_bps), 1500))

    if slug == "sniper":
        settings = _settings(user_wallet)
        if input_token.strip().upper() != "SOL":
            return {"error": "Sniper entries spend SOL only."}
        if amount > float(settings["max_buy_sol"]):
            return {
                "error": f"Amount is above the sniper max buy of {settings['max_buy_sol']} SOL.",
            }
        slippage_bps = min(slippage_bps, int(settings["slippage_bps"]))
        require_renounced = bool(settings["require_renounced"])

    inp = resolve_token(input_token)
    out = resolve_token(output_token)
    if "error" in inp:
        return inp
    if "error" in out:
        return out

    if require_renounced:
        try:
            authorities = _mint_authorities(out["mint"])
        except Exception as exc:
            return {"error": f"Could not read the mint account: {exc}"}
        if authorities.get("mint_authority") or authorities.get("freeze_authority"):
            return {
                "error": "Mint or freeze authority is still set. Sniper will not buy this token.",
                "mint": out["mint"],
                **authorities,
            }

    if inp["symbol"] == "SOL":
        needed = _lamports(amount, 9) + 3_000_000
        try:
            have = _sol_balance(pubkey)
        except Exception as exc:
            return {"error": f"Could not read the agent wallet balance: {exc}"}
        if have < needed:
            return {
                "error": (
                    f"Agent wallet has {have / 1_000_000_000:.6f} SOL. "
                    f"Send at least {needed / 1_000_000_000:.6f} SOL to {pubkey} before this swap."
                ),
                "agent_wallet": pubkey,
            }

    quote = get_jupiter_quote(inp["symbol"], out["symbol"], amount, slippage_bps, taker=pubkey)
    if isinstance(quote, dict) and quote.get("error"):
        return quote
    impact = quote.get("price_impact_pct") if isinstance(quote, dict) else None
    try:
        impact_num = abs(float(impact)) if impact not in (None, "") else 0.0
    except (TypeError, ValueError):
        impact_num = 0.0
    impact_pct = impact_num * 100 if impact_num <= 1 else impact_num
    if slug == "sniper" and impact_pct > slippage_bps / 100:
        return {
            "error": (
                f"Price impact {impact_pct:.2f}% is above the sniper slippage cap "
                f"of {slippage_bps / 100:.2f}%."
            ),
        }

    result = _build_and_execute_swap(
        inp["mint"],
        out["mint"],
        _lamports(amount, inp["decimals"]),
        pubkey,
        keypair,
        slippage_bps,
        circle_wallet_id=circle_wallet_id,
        plan_id=f"{spec['agent_type']}-{uuid.uuid4().hex[:8]}",
        run_index=1,
    )
    if result.get("status") == "success":
        result["input_token"] = inp["symbol"]
        result["output_token"] = out["symbol"]
        result["input_amount"] = amount
        result["agent_wallet"] = pubkey
        result["aomi"] = "committed"
    return result


def _summary(slug: str, args: dict[str, Any]) -> str:
    spec = AGENTS[slug]
    return (
        f"Please confirm before I proceed: {spec['name']} will swap "
        f"{args['amount']} {args['input_token']} -> {args['output_token']} "
        f"from its Circle wallet. Aomi simulates the transaction before Circle signs. "
        f"Reply yes to proceed, or no to cancel."
    )


def _stage(slug: str, session_key: str, args: dict[str, Any]) -> dict[str, Any]:
    message = _summary(slug, args)
    with _LOCK:
        _pending[session_key] = {"tool": "execute_swap", "args": args, "message": message}
    return {
        "status": "confirmation_required",
        "message": message,
        "pending_action": message,
        "confirmation_details": {"action": "execute_swap", **args},
    }


def _apply_settings(user_wallet: str, text: str) -> Optional[str]:
    settings = _settings(user_wallet)
    changed = False
    max_buy = _MAX_BUY.search(text)
    if max_buy:
        settings["max_buy_sol"] = float(max_buy.group(1))
        changed = True
    slip = _SLIP.search(text)
    if slip:
        settings["slippage_bps"] = max(1, min(int(slip.group(1)), 1500))
        changed = True
    if re.search(r"allow mint authority", text, re.I):
        settings["require_renounced"] = False
        changed = True
    elif re.search(r"renounc", text, re.I):
        settings["require_renounced"] = True
        changed = True
    if not changed:
        return None
    return (
        "Sniper settings updated. "
        f"Max buy {settings['max_buy_sol']} SOL, "
        f"slippage {settings['slippage_bps']} bps, "
        f"renounced mint required: {settings['require_renounced']}."
    )


def _parse_trade(slug: str, text: str, user_wallet: str) -> Optional[dict[str, Any]]:
    sell = _SELL.search(text)
    if sell:
        if slug == "sniper":
            return {"error": "Sniper only buys with SOL. Use the Hedge Fund agent to sell."}
        return {
            "input_token": sell.group(2),
            "output_token": "SOL",
            "amount": float(sell.group(1)),
            "slippage_bps": 100,
        }
    buy = _BUY.search(text)
    if not buy:
        return None
    slippage = 300 if slug == "sniper" else 100
    if slug == "sniper":
        slippage = int(_settings(user_wallet)["slippage_bps"])
    return {
        "input_token": "SOL",
        "output_token": buy.group(2),
        "amount": float(buy.group(1)),
        "slippage_bps": slippage,
    }


def _tools(slug: str) -> list[dict[str, Any]]:
    trade = (
        "Buy a token with SOL. Sniper rejects a mint that still has mint or freeze authority, "
        "and rejects a buy above the user's max size."
        if slug == "sniper"
        else "Buy or sell between SOL and another token from the Hedge Fund Circle wallet."
    )
    return [
        {
            "type": "function",
            "function": {
                "name": "get_agent_wallet",
                "description": "Return this agent's Circle wallet address and SOL balance.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "quote_swap",
                "description": "Preview a Jupiter swap. Does not send a transaction.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "input_token": {"type": "string"},
                        "output_token": {"type": "string"},
                        "amount": {"type": "number"},
                        "slippage_bps": {"type": "integer"},
                    },
                    "required": ["input_token", "output_token", "amount"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "execute_swap",
                "description": trade + " Ask the user to confirm before calling this.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "input_token": {"type": "string"},
                        "output_token": {"type": "string"},
                        "amount": {"type": "number"},
                        "slippage_bps": {"type": "integer"},
                    },
                    "required": ["input_token", "output_token", "amount"],
                },
            },
        },
    ]


def _run_tool(slug: str, name: str, args: dict[str, Any], user_wallet: str, session_key: str, confirmed: bool) -> dict[str, Any]:
    if name == "get_agent_wallet":
        return wallet_status(slug, user_wallet)
    if name == "quote_swap":
        signing = resolve_agent_signing_context(user_wallet, AGENTS[slug]["agent_type"])
        if not signing.get("pubkey"):
            return {"error": "No Circle wallet is available for this agent."}
        return get_jupiter_quote(
            str(args.get("input_token") or ""),
            str(args.get("output_token") or ""),
            float(args.get("amount") or 0),
            int(args.get("slippage_bps") or (300 if slug == "sniper" else 100)),
            taker=signing.get("pubkey"),
        )
    if name == "execute_swap":
        trade = {
            "input_token": str(args.get("input_token") or ""),
            "output_token": str(args.get("output_token") or ""),
            "amount": float(args.get("amount") or 0),
            "slippage_bps": int(args.get("slippage_bps") or (300 if slug == "sniper" else 100)),
        }
        if not confirmed:
            return _stage(slug, session_key, trade)
        return execute_market_swap(slug, user_wallet, **trade)
    return {"error": f"Unknown tool {name}"}


def _system(slug: str) -> str:
    spec = AGENTS[slug]
    extra = (
        "Sniper spends SOL only. Refuse a buy when the user is above their max buy. "
        "Tell them a mint with mint or freeze authority will be rejected."
        if slug == "sniper"
        else "You may buy SOL into a token, or sell a token amount back to SOL."
    )
    return (
        f"You are the {spec['name']} on BIT Agents. {spec['focus']}. {extra} "
        "Every live swap is built by Jupiter, simulated on Aomi, then signed by this agent's Circle wallet. "
        "Never claim a swap was sent unless execute_swap returns a signature. "
        "Before execute_swap, tell the user the tokens, amount, and that Aomi will simulate it, then wait for yes. "
        "Read-only tools can run immediately. End with: Not financial advice. DYOR."
    )


def run_market_agent(
    slug: str,
    user_input: str,
    history: list,
    *,
    user_wallet: str,
    session_id: Optional[str] = None,
) -> tuple[str, list, list[dict[str, Any]]]:
    spec = agent_spec(slug)
    if not spec:
        return "Unknown agent.", history, []
    text = user_input.strip()
    session_key = _key(slug, session_id, user_wallet)
    actions: list[dict[str, Any]] = []

    if _DECLINE.search(text) and not _CONFIRM.search(text):
        with _LOCK:
            had = _pending.pop(session_key, None)
        if had:
            reply = "Cancelled. Nothing was sent."
            history = history + [
                {"role": "user", "content": text},
                {"role": "assistant", "content": reply},
            ]
            return reply, history, [{"tool": "execute_swap", "args": had["args"], "result": json.dumps({"status": "cancelled"})}]

    if _CONFIRM.search(text):
        with _LOCK:
            pending = _pending.pop(session_key, None)
        if pending:
            result = execute_market_swap(slug, user_wallet, **pending["args"])
            reply = _format_result(result)
            actions.append({"tool": "execute_swap", "args": pending["args"], "result": json.dumps(result)})
            history = history + [
                {"role": "user", "content": text},
                {"role": "assistant", "content": reply},
            ]
            return reply, history, actions

    settings_reply = _apply_settings(user_wallet, text) if slug == "sniper" else None
    trade = _parse_trade(slug, text, user_wallet)
    if isinstance(trade, dict) and trade.get("error"):
        reply = str(trade["error"])
        history = history + [
            {"role": "user", "content": text},
            {"role": "assistant", "content": reply},
        ]
        return reply, history, [{"tool": "execute_swap", "args": {}, "result": json.dumps(trade)}]
    if trade:
        staged = _stage(slug, session_key, trade)
        prefix = f"{settings_reply}\n\n" if settings_reply else ""
        reply = prefix + staged["message"]
        actions.append({"tool": "execute_swap", "args": trade, "result": json.dumps(staged)})
        history = history + [
            {"role": "user", "content": text},
            {"role": "assistant", "content": reply},
        ]
        return reply, history, actions
    if settings_reply:
        history = history + [
            {"role": "user", "content": text},
            {"role": "assistant", "content": settings_reply},
        ]
        return settings_reply, history, []

    messages = [{"role": "system", "content": _system(slug)}, *history[-12:], {"role": "user", "content": text}]
    for _ in range(4):
        response = call_llm(
            messages,
            model=MODEL,
            tools=_tools(slug),
            temperature=0.2,
            provider=DCA_LLM_PROVIDER,
        )
        message = response.get("message") if isinstance(response.get("message"), dict) else {}
        tool_calls = message.get("tool_calls") or []
        content = str(message.get("content") or "").strip()
        if not tool_calls:
            reply = content or "I could not complete that. Not financial advice. DYOR."
            history = history + [
                {"role": "user", "content": text},
                {"role": "assistant", "content": reply},
            ]
            return reply, history, actions
        messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})
        for call in tool_calls:
            fn = call.get("function") or {}
            name = str(fn.get("name") or "")
            try:
                raw_args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                raw_args = {}
            if not isinstance(raw_args, dict):
                raw_args = {}
            result = _run_tool(slug, name, raw_args, user_wallet, session_key, confirmed=False)
            actions.append({"tool": name, "args": raw_args, "result": json.dumps(result)})
            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id") or name,
                "content": json.dumps(result),
            })
            if result.get("status") == "confirmation_required":
                reply = str(result["message"])
                history = history + [
                    {"role": "user", "content": text},
                    {"role": "assistant", "content": reply},
                ]
                return reply, history, actions
    reply = "I stopped after several tool calls. Ask again with the token and amount. Not financial advice. DYOR."
    history = history + [
        {"role": "user", "content": text},
        {"role": "assistant", "content": reply},
    ]
    return reply, history, actions


def _format_result(result: dict[str, Any]) -> str:
    if result.get("error"):
        return f"{result['error']}\n\nNot financial advice. DYOR."
    signature = result.get("signature")
    if signature:
        return (
            f"Swap sent from the agent wallet. Signature: {signature}. "
            "Aomi simulated it before Circle signed.\n\nNot financial advice. DYOR."
        )
    status = result.get("status") or "finished"
    return f"Swap {status}.\n\nNot financial advice. DYOR."
