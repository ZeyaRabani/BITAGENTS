"""
Per-user Circle wallet + deposit ledger for the Bounce Agent (and other
price-signal strategy agents).

Mirrors yield_ledger.py's proven pattern exactly, on its own Circle wallet
type ("bounce") so a user's trading capital and any profit never shares a
wallet with DCA, Yield, or the "launch" creator-payout wallet. See the
AGENT_TYPES comment in circle_dca_wallets.py for why a dedicated wallet is
required here, not optional.

Direction semantics for the underlying user_ledger rows:
  deposit  -- user sends SOL into the Bounce Agent wallet
  spend    -- agent buys (BASE_TOKEN -> token) on a fired signal, or the
              auto-conversion of a fresh SOL deposit into BASE_TOKEN
  acquire  -- agent sells (token -> BASE_TOKEN) closing a position, or the
              USDC side of a deposit auto-conversion, crediting proceeds
  withdraw -- user pulls BASE_TOKEN back out

Resting capital is USDC, not SOL. The user only ever deposits native SOL
(zero extra setup -- same as every other agent), but the instant a deposit
is verified, it's auto-converted to USDC (see verify_and_record_bounce_deposit).
This is also what makes SOL a valid trade target again: capital and the
thing being traded can't be the same asset (see open_position's SOL
self-swap guard in bounce_trading.py), and with USDC as the resting
currency, watching and trading SOL itself -- the original ask -- works.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from db import insert_ledger_entry, load_ledger_for_user
from dca_agent import SOL_ADDRESS_FULL, resolve_token, sol_rpc

ALLOWED_DEPOSIT_TOKENS = {"SOL"}  # what the user sends in, on-chain
# USDC is the normal resting currency; SOL stays withdrawable too so a failed
# or partial auto-conversion (see verify_and_record_bounce_deposit) never
# strands funds with no way to get them back out.
ALLOWED_WITHDRAW_TOKENS = {"USDC", "SOL"}
BASE_TOKEN = "USDC"
AGENT_TYPE = "bounce"


def load_bounce_keypair():
    """Local-signing fallback, used when Circle isn't configured (the normal
    case for local dev -- see BOUNCE_WALLET_PRIVATE_KEY in .env.example).
    Mirrors load_hf_keypair/load_volume_keypair/load_easya_keypair exactly,
    same pattern Harshal already uses for every other agent's local wallet."""
    from dca_agent import HAS_SOLDERS, Keypair

    if not HAS_SOLDERS:
        return None
    raw = os.environ.get("BOUNCE_WALLET_PRIVATE_KEY", "").strip()
    if not raw:
        return None
    try:
        import base58

        if raw.startswith("["):
            return Keypair.from_bytes(bytes(json.loads(raw)))
        return Keypair.from_bytes(base58.b58decode(raw))
    except Exception:
        return None


def get_bounce_wallet_pubkey(user_wallet: Optional[str] = None) -> Optional[str]:
    """The address ledger rows are scoped to for this user. Must stay in sync
    with resolve_agent_signing_context's precedence (local key first for
    bounce, then Circle) -- otherwise balances get tracked against one
    address while swaps actually sign from another."""
    user_wallet = (user_wallet or "").strip()
    if not user_wallet:
        return None
    local = load_bounce_keypair()
    if local:
        return str(local.pubkey())
    try:
        from circle_dca_wallets import get_agent_wallet_address

        return get_agent_wallet_address(user_wallet, AGENT_TYPE)
    except Exception as exc:
        print(f"  warning: Bounce Circle wallet unavailable: {exc}")
        return None


def get_bounce_agent_wallet_info(user_wallet: Optional[str] = None) -> dict[str, Any]:
    from dca_agent import SOLANA_CLUSTER, SOLANA_RPC
    from circle_dca_wallets import circle_dca_enabled

    user_wallet = (user_wallet or "").strip()
    wallet = get_bounce_wallet_pubkey(user_wallet) if user_wallet else None
    provider = "circle" if wallet else None
    circle_error = None
    if user_wallet and circle_dca_enabled() and not wallet:
        circle_error = "Circle Bounce wallet provisioning failed. Check CIRCLE_API_KEY / CIRCLE_ENTITY_SECRET."
    elif user_wallet and not circle_dca_enabled():
        circle_error = "Circle is not configured, so the Bounce Agent cannot hold capital."

    result = {
        "agent_wallet": wallet,
        "configured": bool(wallet),
        "wallet_provider": provider,
        "per_user_wallet": bool(wallet),
        "cluster": SOLANA_CLUSTER,
        "rpc": SOLANA_RPC,
        "allowed_tokens": sorted(ALLOWED_DEPOSIT_TOKENS),
        "allowed_withdraw_tokens": sorted(ALLOWED_WITHDRAW_TOKENS),
        "sol_mint": SOL_ADDRESS_FULL,
    }
    if circle_error:
        result["circle_error"] = circle_error
    return result


def _bounce_rows(user_wallet: str) -> list[dict[str, Any]]:
    wallet = get_bounce_wallet_pubkey(user_wallet)
    if not wallet:
        return []
    rows = load_ledger_for_user(user_wallet.strip())
    return [r for r in rows if r.get("agent_wallet") == wallet]


def _ledger_totals(user_wallet: str, token_symbol: str) -> dict[str, float]:
    token_symbol = token_symbol.strip().upper()
    deposited = spent = acquired = withdrawn = 0.0
    for row in _bounce_rows(user_wallet):
        if row.get("status") != "confirmed":
            continue
        if str(row.get("token", "")).upper() != token_symbol:
            continue
        amount = float(row.get("amount") or 0)
        direction = row.get("direction", "deposit")
        if direction == "deposit":
            deposited += amount
        elif direction == "spend":
            spent += amount
        elif direction == "acquire":
            acquired += amount
        elif direction == "withdraw":
            withdrawn += amount
    return {
        "deposited": round(deposited, 9),
        "spent": round(spent, 9),
        "acquired": round(acquired, 9),
        "withdrawn": round(withdrawn, 9),
    }


def get_bounce_user_balances(user_wallet: str) -> dict[str, Any]:
    rows = _bounce_rows(user_wallet)
    tokens = sorted({str(row.get("token") or "").upper() for row in rows if row.get("token")})
    if "SOL" not in tokens:
        tokens = ["SOL", *tokens]
    balances = []
    for token in tokens:
        totals = _ledger_totals(user_wallet, token)
        # "Idle" SOL (deposited, not currently in an open position) plus any
        # sale proceeds already credited back is what's actually withdrawable.
        idle = round(max(0.0, totals["deposited"] + totals["acquired"] - totals["spent"] - totals["withdrawn"]), 9)
        tok = resolve_token(token)
        balances.append(
            {
                "token": token,
                "mint": None if "error" in tok else tok.get("mint"),
                "deposited": totals["deposited"],
                "spent_on_buys": totals["spent"],
                "credited_from_sells": totals["acquired"],
                "withdrawn": totals["withdrawn"],
                "available": idle,
                "withdrawable": idle,
            }
        )
    return {
        "user_wallet": user_wallet.strip(),
        "agent_wallet": get_bounce_wallet_pubkey(user_wallet),
        "balances": balances,
    }


def check_bounce_can_spend(user_wallet: str, amount: float, token: str = "SOL") -> dict[str, Any]:
    amount = float(amount)
    token = (token or "SOL").strip().upper()
    balances = get_bounce_user_balances(user_wallet)
    available = 0.0
    for row in balances.get("balances") or []:
        if str(row.get("token", "")).upper() == token:
            available = float(row.get("available") or 0)
            break
    if available + 1e-12 >= amount:
        return {"ok": True, "available": available, "token": token}
    return {
        "error": (
            f"Insufficient idle {token}. Available: {available}, requested: {amount}. "
            f"Deposit {token} to the Bounce Agent wallet first."
        ),
        "available": available,
    }


def _insert_bounce_ledger(
    user_wallet: str,
    *,
    token: str,
    direction: str,
    amount: float,
    reference_type: str,
    reference_id: str,
    signature: Optional[str] = None,
    explorer_url: Optional[str] = None,
) -> dict[str, Any]:
    agent_wallet = get_bounce_wallet_pubkey(user_wallet)
    if not agent_wallet:
        return {"error": "Bounce agent wallet is not configured."}
    tok = resolve_token(token)
    if "error" in tok:
        return tok
    record = {
        "id": uuid.uuid4().hex[:16],
        "user_wallet": user_wallet.strip(),
        "agent_wallet": agent_wallet,
        "signature": signature,
        "token": tok["symbol"],
        "mint": tok.get("mint") or SOL_ADDRESS_FULL,
        "amount": float(amount),
        "direction": direction,
        "reference_type": reference_type,
        "reference_id": (reference_id or "")[:128],
        "status": "confirmed",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "explorer_url": explorer_url,
    }
    insert_ledger_entry(record)
    return record


def record_bounce_spend(
    user_wallet: str,
    amount: float,
    *,
    reference_id: str,
    token: str = "SOL",
    signature: Optional[str] = None,
    explorer_url: Optional[str] = None,
) -> dict[str, Any]:
    """Record a buy (opening a position). amount is the SOL spent."""
    if amount <= 0:
        return {"spent": 0.0}
    rec = _insert_bounce_ledger(
        user_wallet,
        token=token,
        direction="spend",
        amount=amount,
        reference_type="bounce_buy",
        reference_id=reference_id,
        signature=signature,
        explorer_url=explorer_url,
    )
    if rec.get("error"):
        return rec
    return {"spent": float(amount), "token": (token or "SOL").strip().upper()}


def record_bounce_credit(
    user_wallet: str,
    amount: float,
    *,
    reference_id: str,
    token: str = "SOL",
    signature: Optional[str] = None,
    explorer_url: Optional[str] = None,
) -> dict[str, Any]:
    """Record a sell (closing a position). amount is the SOL proceeds, profit or loss included."""
    if amount <= 0:
        return {"credited": 0.0}
    rec = _insert_bounce_ledger(
        user_wallet,
        token=token,
        direction="acquire",
        amount=amount,
        reference_type="bounce_sell",
        reference_id=reference_id,
        signature=signature,
        explorer_url=explorer_url,
    )
    if rec.get("error"):
        return rec
    return {"credited": float(amount), "token": (token or "SOL").strip().upper()}


def verify_and_record_bounce_deposit(signature: str, user_wallet: str) -> dict[str, Any]:
    from deposit_ledger import (
        _ledger_lock,
        _parse_verified_user_deposits,
        _user_in_transaction,
        _valid_signature,
    )

    signature = signature.strip()
    user_wallet = user_wallet.strip()
    agent_wallet = get_bounce_wallet_pubkey(user_wallet)
    if not agent_wallet:
        return {"error": "Bounce agent wallet is not configured (Circle)."}
    if not signature or not _valid_signature(signature):
        return {"error": "Valid transaction signature is required."}

    with _ledger_lock:
        from db import deposit_exists, find_deposit_by_signature

        if deposit_exists(signature):
            existing = find_deposit_by_signature(signature)
            if existing and existing.get("user_wallet") != user_wallet:
                return {"error": "This deposit was already credited to another wallet.", "status": "rejected"}
            return {
                "status": "already_recorded",
                "deposit": existing,
                "balances": get_bounce_user_balances(user_wallet),
            }

        tx = None
        for attempt in range(10):
            commitment = "finalized" if attempt >= 4 else "confirmed"
            tx = sol_rpc(
                "getTransaction",
                [
                    signature,
                    {
                        "encoding": "jsonParsed",
                        "commitment": commitment,
                        "maxSupportedTransactionVersion": 0,
                    },
                ],
            )
            if tx:
                break
            import time

            time.sleep(0.6)

        if not tx:
            return {"error": "Transaction not found yet. Wait a few seconds and retry.", "status": "pending"}

        if not _user_in_transaction(tx, user_wallet):
            return {
                "error": "Connected wallet must be a signer of the deposit transaction.",
                "status": "rejected",
            }

        inbound = _parse_verified_user_deposits(tx, user_wallet, agent_wallet)
        if not inbound:
            return {
                "error": "No verifiable SOL deposit from your wallet to the Bounce Agent wallet was found.",
                "status": "rejected",
            }

        now = datetime.now(timezone.utc).isoformat()
        records = []
        for transfer in inbound:
            tok = resolve_token(str(transfer.get("mint") or transfer.get("token") or "SOL"))
            if "error" in tok:
                continue
            token = str(tok.get("symbol") or "").upper()
            if token not in ALLOWED_DEPOSIT_TOKENS:
                return {"error": f"Deposits must be SOL (got {token}).", "status": "rejected"}
            record = {
                "id": uuid.uuid4().hex[:16],
                "user_wallet": user_wallet,
                "agent_wallet": agent_wallet,
                "signature": signature,
                "token": token,
                "mint": tok.get("mint"),
                "amount": float(transfer["amount"]),
                "direction": "deposit",
                "reference_type": "bounce_deposit",
                "reference_id": signature[:128],
                "status": "confirmed",
                "verified_at": now,
                "explorer_url": f"https://solscan.io/tx/{signature}",
            }
            insert_ledger_entry(record)
            records.append(record)
        if not records:
            return {"error": "No SOL transfer to the Bounce Agent wallet found.", "status": "rejected"}

        conversion = _auto_convert_deposit_to_usdc(
            user_wallet, sum(float(r["amount"]) for r in records)
        )

        return {
            "status": "confirmed",
            "deposits": records,
            "conversion": conversion,
            "balances": get_bounce_user_balances(user_wallet),
            "message": (
                "Deposit verified and converted to USDC. The agent can now trade with this "
                "capital once you confirm a signal."
                if conversion.get("status") == "success"
                else "Deposit verified, but auto-conversion to USDC failed -- your SOL is safe "
                "and withdrawable as SOL. "
                + str(conversion.get("error") or "")
            ),
        }


def _auto_convert_deposit_to_usdc(user_wallet: str, sol_amount: float) -> dict[str, Any]:
    """Immediately swap a fresh SOL deposit into USDC, the resting currency.
    Never raises -- a failed conversion just leaves the SOL as SOL, still
    fully withdrawable (see ALLOWED_WITHDRAW_TOKENS), not stranded."""
    from hedge_fund_live import execute_agent_jupiter_swap, _sol_operating_reserve, MIN_SOL_FOR_FEES
    from dca_agent import TOKEN_MINTS

    # execute_agent_jupiter_swap separately enforces MIN_SOL_FOR_FEES against
    # the wallet's total balance (every swap needs SOL for gas, regardless of
    # what's being swapped) -- make sure what we leave behind clears both
    # that absolute floor and the ATA-rent/fee headroom, with a little margin.
    reserve = max(_sol_operating_reserve(1), MIN_SOL_FOR_FEES) + 0.002
    convert_amount = round(sol_amount - reserve, 9)
    if convert_amount <= 0:
        return {"status": "skipped", "reason": "Deposit too small to leave fee/rent headroom after converting."}

    usdc = TOKEN_MINTS["USDC"]
    try:
        swap = execute_agent_jupiter_swap(
            agent_type=AGENT_TYPE,
            input_mint=SOL_ADDRESS_FULL,
            output_mint=usdc["mint"],
            amount=convert_amount,
            input_decimals=9,
            user_wallet=user_wallet,
        )
    except Exception as exc:
        return {"status": "error", "error": str(exc)}

    if swap.get("error") or swap.get("status") != "success":
        return {"status": "error", "error": swap.get("error") or "Conversion swap failed."}

    out_raw = int(swap.get("output_amount_raw") or 0)
    usdc_amount = out_raw / (10 ** usdc["decimals"]) if out_raw > 0 else 0.0
    if usdc_amount <= 0:
        return {"status": "error", "error": "Conversion swap reported success but returned no USDC amount."}

    record_bounce_spend(
        user_wallet, convert_amount,
        reference_id=swap.get("signature") or uuid.uuid4().hex,
        token="SOL", signature=swap.get("signature"), explorer_url=swap.get("explorer_url"),
    )
    record_bounce_credit(
        user_wallet, usdc_amount,
        reference_id=swap.get("signature") or uuid.uuid4().hex,
        token="USDC", signature=swap.get("signature"), explorer_url=swap.get("explorer_url"),
    )
    return {"status": "success", "sol_converted": convert_amount, "usdc_received": usdc_amount, "signature": swap.get("signature")}


def convert_idle_sol_to_usdc(user_wallet: str) -> dict[str, Any]:
    """Convert whatever SOL is currently sitting withdrawable in this wallet
    into USDC -- for deposits made before auto-convert-on-deposit existed,
    or any other SOL that ended up idle here. Reuses the exact same
    conversion path as a fresh deposit; this is a real on-chain swap, not a
    simulation, so the caller (chat confirmation / API route) is responsible
    for getting explicit confirmation before calling this."""
    balances = get_bounce_user_balances(user_wallet)
    sol_balance = next((b["withdrawable"] for b in balances.get("balances") or [] if b["token"] == "SOL"), 0.0)
    if sol_balance <= 0:
        return {"status": "skipped", "reason": "No idle SOL to convert."}
    return _auto_convert_deposit_to_usdc(user_wallet, sol_balance)


def withdraw_bounce_tokens(user_wallet: str, token: str, amount: float) -> dict[str, Any]:
    from deposit_ledger import _ledger_lock
    from dca_agent import send_tokens_to_user

    user_wallet = user_wallet.strip()
    token = token.strip().upper()
    if token not in ALLOWED_WITHDRAW_TOKENS:
        return {"error": "Only idle SOL can be withdrawn."}
    tok = resolve_token(token)
    if "error" in tok:
        return tok
    amount = round(float(amount), 9)
    if amount <= 0:
        return {"error": "Withdraw amount must be greater than zero."}

    balances = get_bounce_user_balances(user_wallet)
    withdrawable = 0.0
    for row in balances.get("balances") or []:
        if str(row.get("token", "")).upper() == token:
            withdrawable = float(row.get("withdrawable") or 0)
            break

    with _ledger_lock:
        if withdrawable + 1e-12 < amount:
            return {
                "error": (
                    f"Insufficient idle {token}. Withdrawable: {withdrawable}, requested: {amount}. "
                    "Close any open position before withdrawing deployed capital."
                ),
                "withdrawable": withdrawable,
            }
        transfer = send_tokens_to_user(
            user_wallet,
            tok["mint"],
            amount,
            tok["decimals"],
            signing_user_wallet=user_wallet,
            agent_type=AGENT_TYPE,
        )
        if transfer.get("error") or transfer.get("status") != "success":
            return transfer
        signature = transfer.get("signature")
        record = _insert_bounce_ledger(
            user_wallet,
            token=token,
            direction="withdraw",
            amount=amount,
            reference_type="bounce_withdraw",
            reference_id=(signature or "withdraw")[:128],
            signature=signature,
            explorer_url=transfer.get("explorer_url"),
        )
    return {
        "status": "success",
        "withdraw": record,
        "signature": signature,
        "balances": get_bounce_user_balances(user_wallet),
    }


def list_bounce_user_ledger(user_wallet: str, limit: int = 50) -> list[dict[str, Any]]:
    rows = _bounce_rows(user_wallet)
    rows.sort(key=lambda r: r.get("verified_at") or "", reverse=True)
    return rows[: max(1, min(int(limit or 50), 100))]
