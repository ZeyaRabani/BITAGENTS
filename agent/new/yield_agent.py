"""Yield Agent: compare Solana venues, deploy idle SOL into LSTs, rebalance on better APY."""

from __future__ import annotations

import os
import threading
import uuid
from typing import Any, Optional

from agent_tool_runner import run_tool_agent
from hosted_llm import CAPIX_MODEL, DEFAULT_LLM_MODEL, use_capix
from yield_ledger import (
    AGENT_TYPE,
    check_yield_can_spend,
    get_yield_agent_wallet_info,
    get_yield_user_balances,
    record_yield_credit,
    record_yield_spend,
)
from yield_protocols import (
    SOL_MINT,
    best_executable_venue,
    compare_for_requirements,
    compare_solana_yields,
    get_executable_venue,
)

YIELD_MODEL = (
    CAPIX_MODEL
    if use_capix()
    else os.environ.get(
        "YIELD_MODEL",
        os.environ.get("DCA_MODEL", os.environ.get("OPEN_ROUTER_MODEL", DEFAULT_LLM_MODEL)),
    )
)

MIN_ALLOCATE_SOL = float(os.environ.get("YIELD_MIN_ALLOCATE_SOL", "0.05") or "0.05")
SOL_FEE_RESERVE = float(os.environ.get("YIELD_SOL_RESERVE", "0.03") or "0.03")
DEFAULT_MIN_APY_GAIN = float(os.environ.get("YIELD_MIN_APY_GAIN", "0.5") or "0.5")
YIELD_SCHEDULER_POLL_SECONDS = int(os.environ.get("YIELD_SCHEDULER_POLL_SECONDS", "900") or "900")
SLIPPAGE_BPS = int(os.environ.get("YIELD_SLIPPAGE_BPS", "50") or "50")

_scheduler_stop = threading.Event()
_scheduler_thread: Optional[threading.Thread] = None

SYSTEM_PROMPT = """You are the BIT Agents Yield Agent for Solana.

You hold the user's assets in their Circle yield wallet and invest them with Jupiter.

When the user gives an asset, capital, and duration:
1. Call invest with those requirements. It compares Solana pools, picks the best protocol, and stakes through Jupiter when that venue is executable.
2. If lending pays clearly more than any Jupiter-executable venue, report the comparison and do not pretend a stake happened.
3. Rebalance when another executable venue is better by the mandate threshold.
4. Unwind back to idle SOL so the user can withdraw.

Rules:
- Use invest for requirement-based deposits (asset, capital, duration). Use allocate only for a plain SOL amount.
- Never invent APYs, signatures, or balances.
- Not financial advice. Keep replies concise.
"""


def _execute_swap(
    *,
    user_wallet: str,
    input_mint: str,
    output_mint: str,
    amount: float,
    input_decimals: int = 9,
) -> dict[str, Any]:
    from dca_agent import _build_and_execute_swap, sol_rpc
    from circle_dca_wallets import resolve_agent_signing_context

    signing = resolve_agent_signing_context(user_wallet, AGENT_TYPE)
    keypair = signing.get("keypair") if signing.get("mode") == "local" else None
    circle_wallet_id = signing.get("wallet_id") if signing.get("mode") == "circle" else None
    pubkey = signing.get("pubkey")
    if not pubkey or (signing.get("mode") == "local" and not keypair):
        return {"error": "Yield wallet is not configured (Circle)."}
    if amount <= 0:
        return {"error": "Swap amount must be greater than zero."}

    try:
        lamports = int((sol_rpc("getBalance", [pubkey]) or {}).get("value", 0))
        sol_balance = lamports / 1e9
        if input_mint == SOL_MINT and sol_balance - amount < SOL_FEE_RESERVE - 1e-12:
            return {
                "error": (
                    f"Swap of {amount:.6f} SOL would leave only "
                    f"{max(0.0, sol_balance - amount):.6f} SOL for fees. "
                    f"Keep at least {SOL_FEE_RESERVE} SOL idle."
                )
            }
    except Exception:
        pass

    raw = int(round(float(amount) * (10 ** int(input_decimals))))
    if raw <= 0:
        return {"error": "Swap amount is too small."}
    return _build_and_execute_swap(
        input_mint,
        output_mint,
        raw,
        pubkey,
        keypair,
        slippage_bps=SLIPPAGE_BPS,
        retries=3,
        circle_wallet_id=circle_wallet_id,
        compute_unit_price_percentile="veryHigh",
    )


def _out_amount(swap: dict[str, Any], fallback: float) -> float:
    for key in ("output_amount", "out_amount", "amount_out"):
        val = swap.get(key)
        if val is None:
            continue
        try:
            num = float(val)
        except (TypeError, ValueError):
            continue
        if num > 1000:
            num = num / 1e9
        if num > 0:
            return num
    return fallback


def tool_compare_yields(limit: int = 12, **_ctx) -> dict[str, Any]:
    return compare_solana_yields(limit=int(limit or 12))


def tool_get_portfolio(user_wallet: Optional[str] = None, **_ctx) -> dict[str, Any]:
    from db import get_yield_mandate, list_yield_positions, list_yield_rebalances

    wallet = (user_wallet or "").strip()
    if not wallet:
        return {"error": "Connect a wallet first."}
    return {
        "wallet": get_yield_agent_wallet_info(wallet),
        "balances": get_yield_user_balances(wallet),
        "mandate": get_yield_mandate(wallet),
        "positions": list_yield_positions(wallet, active_only=True),
        "recent_moves": list_yield_rebalances(wallet, limit=8),
    }


def tool_set_mandate(
    auto_rebalance: bool = True,
    min_apy_gain: float = DEFAULT_MIN_APY_GAIN,
    idle_reserve_sol: float = SOL_FEE_RESERVE,
    user_wallet: Optional[str] = None,
    **_ctx,
) -> dict[str, Any]:
    from db import upsert_yield_mandate

    wallet = (user_wallet or "").strip()
    if not wallet:
        return {"error": "Connect a wallet first."}
    gain = max(0.05, float(min_apy_gain or DEFAULT_MIN_APY_GAIN))
    reserve = max(0.01, float(idle_reserve_sol or SOL_FEE_RESERVE))
    row = upsert_yield_mandate(
        wallet,
        {
            "auto_rebalance": bool(auto_rebalance),
            "min_apy_gain": gain,
            "idle_reserve_sol": reserve,
            "status": "active",
        },
    )
    return {"status": "saved", "mandate": row}


def allocate_to_venue(
    user_wallet: str,
    amount_sol: float,
    protocol_id: Optional[str] = None,
) -> dict[str, Any]:
    from db import insert_yield_position, insert_yield_rebalance, upsert_yield_mandate

    wallet = (user_wallet or "").strip()
    amount = round(float(amount_sol), 9)
    if amount < MIN_ALLOCATE_SOL:
        return {"error": f"Minimum allocate is {MIN_ALLOCATE_SOL} SOL."}

    venue = get_executable_venue(protocol_id) if protocol_id else best_executable_venue()
    if not venue:
        venue = best_executable_venue()
    if not venue or not venue.get("mint"):
        return {"error": "No executable yield venue is available right now."}

    spend = check_yield_can_spend(wallet, amount)
    if spend.get("error"):
        return spend

    swap = _execute_swap(
        user_wallet=wallet,
        input_mint=SOL_MINT,
        output_mint=str(venue["mint"]),
        amount=amount,
        input_decimals=9,
    )
    if swap.get("error") or swap.get("status") in ("failed", "error"):
        return {"error": swap.get("error") or "Jupiter swap failed.", "swap": swap}

    out_amt = _out_amount(swap, amount)
    signature = swap.get("signature")
    explorer = swap.get("explorer_url") or (f"https://solscan.io/tx/{signature}" if signature else None)
    pos_id = uuid.uuid4().hex[:16]
    record_yield_spend(
        wallet,
        amount,
        reference_id=pos_id,
        signature=signature,
        explorer_url=explorer,
    )
    position = insert_yield_position(
        {
            "id": pos_id,
            "user_wallet": wallet,
            "protocol_id": venue["protocol_id"],
            "protocol_name": venue.get("protocol_name") or venue["protocol_id"],
            "mint": venue["mint"],
            "symbol": venue.get("symbol") or "LST",
            "amount": out_amt,
            "entry_apy": venue.get("apy"),
            "status": "active",
            "last_signature": signature,
            "explorer_url": explorer,
        }
    )
    insert_yield_rebalance(
        {
            "id": uuid.uuid4().hex[:16],
            "user_wallet": wallet,
            "position_id": pos_id,
            "from_protocol": "idle_sol",
            "to_protocol": venue["protocol_id"],
            "amount": amount,
            "from_apy": 0,
            "to_apy": venue.get("apy"),
            "signature": signature,
            "explorer_url": explorer,
            "status": "confirmed",
        }
    )
    upsert_yield_mandate(wallet, {"auto_rebalance": True, "min_apy_gain": DEFAULT_MIN_APY_GAIN})
    return {
        "status": "allocated",
        "position": position,
        "spent_sol": amount,
        "received": out_amt,
        "venue": venue,
        "signature": signature,
        "explorer_url": explorer,
        "message": (
            f'Allocated {amount} SOL to {venue.get("protocol_name")} '
            f'({venue.get("symbol")}'
            + (f', {venue.get("apy")}% APY' if venue.get("apy") is not None else "")
            + ")."
        ),
    }


def invest_for_requirements(
    user_wallet: str,
    asset: str,
    capital: float,
    duration_days: int,
) -> dict[str, Any]:
    """Compare venues for the user's asset, capital, and duration, then stake via Jupiter."""
    from db import insert_yield_position, insert_yield_rebalance, upsert_yield_mandate
    from dca_agent import resolve_token

    wallet = (user_wallet or "").strip()
    asset_norm = (asset or "SOL").strip().upper()
    if asset_norm not in ("SOL", "USDC", "USDT"):
        return {"error": "Asset must be SOL, USDC, or USDT."}
    try:
        amount = round(float(capital), 9)
        duration = int(duration_days)
    except (TypeError, ValueError):
        return {"error": "Capital and duration must be numbers."}
    if amount <= 0:
        return {"error": "Capital must be greater than 0."}
    if duration < 1:
        return {"error": "Duration must be at least 1 day."}
    minimum = MIN_ALLOCATE_SOL if asset_norm == "SOL" else 1.0
    if amount < minimum:
        return {"error": f"Minimum invest for {asset_norm} is {minimum}."}

    comparison = compare_for_requirements(
        asset=asset_norm,
        capital=amount,
        duration_days=duration,
    )
    mandate = upsert_yield_mandate(
        wallet,
        {
            "auto_rebalance": True,
            "asset": asset_norm,
            "capital": amount,
            "duration_days": duration,
            "status": "active",
        },
    )
    venue = comparison.get("best_to_execute") or {}
    if not venue.get("mint"):
        best = comparison.get("best_overall") or {}
        name = best.get("protocol_name") or best.get("project") or "no pool"
        apy = best.get("apy")
        return {
            "status": "compared",
            "mandate": mandate,
            "comparison": comparison,
            "message": (
                f"Best match for {amount} {asset_norm} over {duration} days is {name}"
                + (f" at {apy}% APY" if apy is not None else "")
                + ". That venue is not a Jupiter liquid-staking swap, so nothing was staked."
            ),
        }

    spend = check_yield_can_spend(wallet, amount, token=asset_norm)
    if spend.get("error"):
        return {
            "status": "needs_deposit",
            "mandate": mandate,
            "comparison": comparison,
            "error": spend["error"],
            "available": spend.get("available"),
        }

    tok = resolve_token(asset_norm)
    if tok.get("error"):
        return tok
    input_mint = SOL_MINT if asset_norm == "SOL" else str(tok.get("mint") or "")
    decimals = 9 if asset_norm == "SOL" else int(tok.get("decimals") or 6)
    swap = _execute_swap(
        user_wallet=wallet,
        input_mint=input_mint,
        output_mint=str(venue["mint"]),
        amount=amount,
        input_decimals=decimals,
    )
    if swap.get("error") or swap.get("status") in ("failed", "error"):
        return {"error": swap.get("error") or "Jupiter swap failed.", "swap": swap, "comparison": comparison}

    out_amt = _out_amount(swap, amount)
    signature = swap.get("signature")
    explorer = swap.get("explorer_url") or (f"https://solscan.io/tx/{signature}" if signature else None)
    pos_id = uuid.uuid4().hex[:16]
    record_yield_spend(
        wallet,
        amount,
        token=asset_norm,
        reference_id=pos_id,
        signature=signature,
        explorer_url=explorer,
    )
    position = insert_yield_position(
        {
            "id": pos_id,
            "user_wallet": wallet,
            "protocol_id": venue.get("protocol_id") or venue.get("project"),
            "protocol_name": venue.get("protocol_name") or venue.get("project") or "yield",
            "mint": venue["mint"],
            "symbol": venue.get("symbol") or "LST",
            "amount": out_amt,
            "entry_apy": venue.get("apy"),
            "status": "active",
            "last_signature": signature,
            "explorer_url": explorer,
        }
    )
    insert_yield_rebalance(
        {
            "id": uuid.uuid4().hex[:16],
            "user_wallet": wallet,
            "position_id": pos_id,
            "from_protocol": f"idle_{asset_norm.lower()}",
            "to_protocol": venue.get("protocol_id") or venue.get("project"),
            "amount": amount,
            "from_apy": 0,
            "to_apy": venue.get("apy"),
            "signature": signature,
            "explorer_url": explorer,
            "status": "confirmed",
        }
    )
    return {
        "status": "invested",
        "position": position,
        "spent": amount,
        "asset": asset_norm,
        "duration_days": duration,
        "received": out_amt,
        "venue": venue,
        "route": comparison.get("execution_route"),
        "signature": signature,
        "explorer_url": explorer,
        "mandate": mandate,
            "message": (
                f"Invested {amount} {asset_norm} for {duration} days into "
                f'{venue.get("protocol_name") or venue.get("symbol")}'
                + (f' at {venue.get("apy")}% APY' if venue.get("apy") is not None else "")
                + " via Jupiter."
                + _better_non_executable_note(comparison, venue)
            ),
    }


def _better_non_executable_note(comparison: dict[str, Any], venue: dict[str, Any]) -> str:
    best = comparison.get("best_overall") or {}
    try:
        best_apy = float(best.get("apy"))
        used_apy = float(venue.get("apy"))
    except (TypeError, ValueError):
        return ""
    if best.get("executable") or best_apy <= used_apy + 0.5:
        return ""
    name = best.get("protocol_name") or best.get("project") or "Another pool"
    return (
        f" {name} shows {best_apy}% APY, but it is not a Jupiter liquid-staking swap, "
        "so the agent used the best venue it can stake."
    )


def unwind_position(user_wallet: str, position_id: Optional[str] = None) -> dict[str, Any]:
    from db import list_yield_positions, update_yield_position, insert_yield_rebalance

    wallet = (user_wallet or "").strip()
    positions = list_yield_positions(wallet, active_only=True)
    if not positions:
        return {"error": "No active yield positions to unwind."}
    pos = None
    if position_id:
        pos = next((p for p in positions if p.get("id") == position_id), None)
    else:
        pos = positions[0]
    if not pos:
        return {"error": "Position not found."}

    amount = float(pos.get("amount") or 0)
    swap = _execute_swap(
        user_wallet=wallet,
        input_mint=str(pos["mint"]),
        output_mint=SOL_MINT,
        amount=amount,
        input_decimals=9,
    )
    if swap.get("status") != "success" and swap.get("error"):
        return {"error": swap.get("error") or "Unwind swap failed.", "swap": swap}

    sol_out = _out_amount(swap, amount)
    signature = swap.get("signature")
    explorer = swap.get("explorer_url") or (f"https://solscan.io/tx/{signature}" if signature else None)
    record_yield_credit(
        wallet,
        sol_out,
        reference_id=str(pos["id"]),
        signature=signature,
        explorer_url=explorer,
    )
    update_yield_position(
        pos["id"],
        {
            "status": "closed",
            "amount": 0,
            "last_signature": signature,
            "explorer_url": explorer,
        },
    )
    insert_yield_rebalance(
        {
            "id": uuid.uuid4().hex[:16],
            "user_wallet": wallet,
            "position_id": pos["id"],
            "from_protocol": pos.get("protocol_id"),
            "to_protocol": "idle_sol",
            "amount": sol_out,
            "from_apy": pos.get("entry_apy"),
            "to_apy": 0,
            "signature": signature,
            "explorer_url": explorer,
            "status": "confirmed",
        }
    )
    return {
        "status": "unwound",
        "sol_returned": sol_out,
        "signature": signature,
        "explorer_url": explorer,
        "message": f"Unwound {pos.get('symbol')} back to {sol_out} idle SOL.",
    }


def rebalance_positions(user_wallet: str, force: bool = False) -> dict[str, Any]:
    from db import (
        get_yield_mandate,
        insert_yield_rebalance,
        list_yield_positions,
        update_yield_position,
    )

    wallet = (user_wallet or "").strip()
    mandate = get_yield_mandate(wallet) or {}
    min_gain = float(mandate.get("min_apy_gain") or DEFAULT_MIN_APY_GAIN)
    best = best_executable_venue()
    if not best or best.get("apy") is None:
        return {"status": "skipped", "reason": "No live executable APY to compare."}

    positions = list_yield_positions(wallet, active_only=True)
    if not positions:
        return {"status": "skipped", "reason": "No active positions."}

    moved = []
    skipped = []
    for pos in positions:
        current_id = str(pos.get("protocol_id") or "")
        current_apy = float(pos.get("entry_apy") or 0)
        target_apy = float(best.get("apy") or 0)
        if current_id == best.get("protocol_id"):
            skipped.append({"position_id": pos["id"], "reason": "already in best venue"})
            continue
        if not force and target_apy - current_apy < min_gain:
            skipped.append(
                {
                    "position_id": pos["id"],
                    "reason": f"gain {round(target_apy - current_apy, 3)}% below threshold {min_gain}%",
                }
            )
            continue

        amount = float(pos.get("amount") or 0)
        swap = _execute_swap(
            user_wallet=wallet,
            input_mint=str(pos["mint"]),
            output_mint=str(best["mint"]),
            amount=amount,
            input_decimals=9,
        )
        if swap.get("status") != "success" and swap.get("error"):
            insert_yield_rebalance(
                {
                    "id": uuid.uuid4().hex[:16],
                    "user_wallet": wallet,
                    "position_id": pos["id"],
                    "from_protocol": current_id,
                    "to_protocol": best.get("protocol_id"),
                    "amount": amount,
                    "from_apy": current_apy,
                    "to_apy": target_apy,
                    "status": "failed",
                    "error": swap.get("error"),
                }
            )
            skipped.append({"position_id": pos["id"], "error": swap.get("error")})
            continue

        out_amt = _out_amount(swap, amount)
        signature = swap.get("signature")
        explorer = swap.get("explorer_url") or (f"https://solscan.io/tx/{signature}" if signature else None)
        updated = update_yield_position(
            pos["id"],
            {
                "protocol_id": best["protocol_id"],
                "protocol_name": best.get("protocol_name") or best["protocol_id"],
                "mint": best["mint"],
                "symbol": best.get("symbol"),
                "amount": out_amt,
                "entry_apy": target_apy,
                "last_signature": signature,
                "explorer_url": explorer,
                "status": "active",
            },
        )
        insert_yield_rebalance(
            {
                "id": uuid.uuid4().hex[:16],
                "user_wallet": wallet,
                "position_id": pos["id"],
                "from_protocol": current_id,
                "to_protocol": best.get("protocol_id"),
                "amount": out_amt,
                "from_apy": current_apy,
                "to_apy": target_apy,
                "signature": signature,
                "explorer_url": explorer,
                "status": "confirmed",
            }
        )
        moved.append(updated)

    return {
        "status": "rebalanced" if moved else "held",
        "best_venue": best,
        "moved": moved,
        "skipped": skipped,
        "min_apy_gain": min_gain,
    }


def tool_invest(
    asset: str = "SOL",
    capital: float = 0,
    duration_days: int = 30,
    user_wallet: Optional[str] = None,
    **_ctx,
) -> dict[str, Any]:
    wallet = (user_wallet or "").strip()
    if not wallet:
        return {"error": "Connect a wallet first."}
    return invest_for_requirements(wallet, asset, capital, duration_days)


def tool_allocate(
    amount_sol: float,
    protocol_id: Optional[str] = None,
    user_wallet: Optional[str] = None,
    **_ctx,
) -> dict[str, Any]:
    wallet = (user_wallet or "").strip()
    if not wallet:
        return {"error": "Connect a wallet first."}
    return allocate_to_venue(wallet, amount_sol, protocol_id)


def tool_rebalance(force: bool = False, user_wallet: Optional[str] = None, **_ctx) -> dict[str, Any]:
    wallet = (user_wallet or "").strip()
    if not wallet:
        return {"error": "Connect a wallet first."}
    return rebalance_positions(wallet, force=bool(force))


def tool_unwind(
    position_id: Optional[str] = None,
    user_wallet: Optional[str] = None,
    **_ctx,
) -> dict[str, Any]:
    wallet = (user_wallet or "").strip()
    if not wallet:
        return {"error": "Connect a wallet first."}
    return unwind_position(wallet, position_id)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "compare_yields",
            "description": "Compare live Solana yield venues (LSTs executable, lending for comparison).",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max lending rows to include (default 12)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_portfolio",
            "description": "Show idle SOL, deployed LST positions, mandate, and recent rebalances.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_mandate",
            "description": "Set auto-rebalance and the minimum APY gain required to move funds.",
            "parameters": {
                "type": "object",
                "properties": {
                    "auto_rebalance": {"type": "boolean"},
                    "min_apy_gain": {
                        "type": "number",
                        "description": "Move only if the better venue is at least this many APY points higher (default 0.5)",
                    },
                    "idle_reserve_sol": {"type": "number"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "invest",
            "description": (
                "Compare yields for the user's asset, capital, and duration, then stake the "
                "best Jupiter-executable protocol from their Circle yield wallet."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "asset": {"type": "string", "description": "SOL, USDC, or USDT"},
                    "capital": {"type": "number", "description": "Amount already deposited in the Circle wallet"},
                    "duration_days": {"type": "integer", "description": "How long the user wants the position"},
                },
                "required": ["asset", "capital", "duration_days"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "allocate",
            "description": "Deploy idle SOL into a yield venue via Jupiter (best executable LST if protocol_id omitted).",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount_sol": {"type": "number"},
                    "protocol_id": {
                        "type": "string",
                        "description": "jito | marinade | sanctum | blaze | jupsol. Omit to pick the best APY.",
                    },
                },
                "required": ["amount_sol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rebalance",
            "description": "Move existing LST positions to a better executable venue if APY gain clears the mandate.",
            "parameters": {
                "type": "object",
                "properties": {
                    "force": {"type": "boolean", "description": "Ignore the APY gain threshold"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "unwind",
            "description": "Swap a yield position back to idle SOL so it can be withdrawn.",
            "parameters": {
                "type": "object",
                "properties": {
                    "position_id": {"type": "string"},
                },
            },
        },
    },
]

TOOL_REGISTRY = {
    "compare_yields": tool_compare_yields,
    "get_portfolio": tool_get_portfolio,
    "set_mandate": tool_set_mandate,
    "invest": tool_invest,
    "allocate": tool_allocate,
    "rebalance": tool_rebalance,
    "unwind": tool_unwind,
}


def run_yield_agent(
    user_input: str,
    conversation_history: list,
    user_wallet: Optional[str] = None,
    session_id: Optional[str] = None,
) -> tuple[str, list, list[dict[str, Any]]]:
    return run_tool_agent(
        user_input,
        conversation_history,
        system_prompt=SYSTEM_PROMPT,
        tools=TOOLS,
        tool_registry=TOOL_REGISTRY,
        model=YIELD_MODEL,
        app_suffix="yield",
        user_wallet=user_wallet,
        session_id=session_id,
        max_rounds=8,
    )


def get_yield_dashboard(user_wallet: str) -> dict[str, Any]:
    comparison = compare_solana_yields()
    portfolio = tool_get_portfolio(user_wallet=user_wallet)
    return {**portfolio, "yields": comparison}


def _scheduler_loop() -> None:
    from db import list_active_yield_mandates

    while not _scheduler_stop.is_set():
        try:
            for mandate in list_active_yield_mandates():
                wallet = str(mandate.get("user_wallet") or "")
                if not wallet:
                    continue
                result = rebalance_positions(wallet, force=False)
                if result.get("moved"):
                    print(f"  📈 Yield rebalance for {wallet[:8]}…: {result.get('status')}")
        except Exception as exc:
            print(f"  ⚠️  Yield scheduler error: {exc}")
        _scheduler_stop.wait(YIELD_SCHEDULER_POLL_SECONDS)


def start_yield_scheduler() -> bool:
    global _scheduler_thread
    if _scheduler_thread and _scheduler_thread.is_alive():
        return True
    _scheduler_stop.clear()
    _scheduler_thread = threading.Thread(target=_scheduler_loop, name="yield-scheduler", daemon=True)
    _scheduler_thread.start()
    return True


def yield_scheduler_status() -> dict[str, Any]:
    alive = bool(_scheduler_thread and _scheduler_thread.is_alive())
    return {
        "running": alive,
        "poll_seconds": YIELD_SCHEDULER_POLL_SECONDS,
        "min_allocate_sol": MIN_ALLOCATE_SOL,
        "min_apy_gain": DEFAULT_MIN_APY_GAIN,
    }
