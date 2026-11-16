"""
Platform fee pots, creator-agent payment wallets, and monthly treasury sweeps.

See docs/PAYMENTS.md for the product rules.
"""

from __future__ import annotations

import os
import threading
import uuid
from calendar import monthrange
from datetime import datetime, timezone
from typing import Any, Optional

from db import get_conn, init_db

# Transfer fee paid from platform fee (not charged to the user).
TRANSFER_BUFFER_SOL = float(os.environ.get("PLATFORM_FEE_TRANSFER_BUFFER_SOL", "0.000005") or "0.000005")
# Do not sweep if net after buffer is at or below this (uneconomical).
MIN_SWEEP_NET_SOL = float(os.environ.get("PLATFORM_FEE_MIN_SWEEP_NET_SOL", "0.000002") or "0.000002")
SWEEP_HOUR_GMT = int(os.environ.get("PLATFORM_FEE_SWEEP_HOUR_GMT", "11") or "11")

_scheduler_stop = threading.Event()
_scheduler_thread: Optional[threading.Thread] = None
_last_sweep_ym: Optional[str] = None
_payments_lock = threading.RLock()


def get_company_treasury_wallet() -> Optional[str]:
    for key in ("COMPANY_TREASURY_WALLET", "TREASURY_PUBLIC_KEY"):
        val = (os.getenv(key) or "").strip()
        if val and "REPLACE_WITH" not in val:
            return val
    return None


def get_launch_fee_wallet() -> Optional[str]:
    for key in ("LAUNCH_FEE_WALLET", "TREASURY_PUBLIC_KEY"):
        val = (os.getenv(key) or "").strip()
        if val and "REPLACE_WITH" not in val:
            return val
    return None


def ensure_payments_schema() -> None:
    init_db()
    statements = [
        """
        CREATE TABLE IF NOT EXISTS platform_fee_pots (
            pot_key            VARCHAR(128) PRIMARY KEY,
            fee_wallet_address VARCHAR(64) NOT NULL,
            circle_wallet_id   VARCHAR(128),
            owner_user_wallet  VARCHAR(64),
            agent_type         VARCHAR(32),
            agent_id           VARCHAR(32),
            source             VARCHAR(32) NOT NULL DEFAULT 'agent_fee',
            accrued_sol        DOUBLE PRECISION NOT NULL DEFAULT 0,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_swept_at      TIMESTAMPTZ
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_platform_fee_pots_wallet ON platform_fee_pots (fee_wallet_address)",
        "CREATE INDEX IF NOT EXISTS idx_platform_fee_pots_agent ON platform_fee_pots (agent_id)",
        """
        CREATE TABLE IF NOT EXISTS agent_payment_wallets (
            agent_id               VARCHAR(32) PRIMARY KEY,
            creator_user_wallet    VARCHAR(64) NOT NULL,
            payment_wallet_address VARCHAR(64) NOT NULL,
            circle_wallet_id       VARCHAR(128),
            circle_wallet_set_id   VARCHAR(128),
            creator_available_sol  DOUBLE PRECISION NOT NULL DEFAULT 0,
            platform_accrued_sol   DOUBLE PRECISION NOT NULL DEFAULT 0,
            created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_agent_payment_wallets_creator ON agent_payment_wallets (creator_user_wallet)",
        "CREATE INDEX IF NOT EXISTS idx_agent_payment_wallets_addr ON agent_payment_wallets (payment_wallet_address)",
        """
        CREATE TABLE IF NOT EXISTS platform_fee_sweeps (
            id                 VARCHAR(32) PRIMARY KEY,
            pot_key            VARCHAR(128) NOT NULL,
            fee_wallet_address VARCHAR(64) NOT NULL,
            treasury_wallet    VARCHAR(64) NOT NULL,
            accrued_before     DOUBLE PRECISION NOT NULL,
            buffer_sol         DOUBLE PRECISION NOT NULL,
            sent_sol           DOUBLE PRECISION NOT NULL,
            signature          VARCHAR(128),
            explorer_url       TEXT,
            status             VARCHAR(20) NOT NULL,
            error              TEXT,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "ALTER TABLE launched_agents ADD COLUMN IF NOT EXISTS payment_wallet_address VARCHAR(64)",
        "ALTER TABLE launched_agents ADD COLUMN IF NOT EXISTS payment_circle_wallet_id VARCHAR(128)",
    ]
    with get_conn() as conn:
        with conn.cursor() as cur:
            for sql in statements:
                cur.execute(sql)


def _pot_key_for_agent_wallet(agent_type: str, user_wallet: str) -> str:
    return f"agent:{agent_type}:{user_wallet.strip().lower()}"


def _pot_key_for_creator_agent(agent_id: str) -> str:
    return f"creator_agent:{agent_id.strip()}"


def accrue_platform_fee(
    *,
    amount_sol: float,
    fee_wallet_address: str,
    circle_wallet_id: Optional[str] = None,
    owner_user_wallet: Optional[str] = None,
    agent_type: Optional[str] = None,
    agent_id: Optional[str] = None,
    source: str = "agent_fee",
    pot_key: Optional[str] = None,
) -> dict[str, Any]:
    """Add SOL to a platform fee pot that lives in fee_wallet_address until monthly sweep."""
    ensure_payments_schema()
    amount = round(float(amount_sol), 12)
    if amount <= 0:
        return {"status": "skipped", "accrued": 0.0}
    fee_wallet_address = (fee_wallet_address or "").strip()
    if not fee_wallet_address:
        return {"error": "fee_wallet_address is required"}

    if not pot_key:
        if agent_id:
            pot_key = _pot_key_for_creator_agent(agent_id)
        elif agent_type and owner_user_wallet:
            pot_key = _pot_key_for_agent_wallet(agent_type, owner_user_wallet)
        else:
            pot_key = f"wallet:{fee_wallet_address.lower()}"

    with _payments_lock:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO platform_fee_pots (
                        pot_key, fee_wallet_address, circle_wallet_id, owner_user_wallet,
                        agent_type, agent_id, source, accrued_sol, updated_at
                    )
                    VALUES (
                        %(pot_key)s, %(fee_wallet_address)s, %(circle_wallet_id)s, %(owner_user_wallet)s,
                        %(agent_type)s, %(agent_id)s, %(source)s, %(amount)s, NOW()
                    )
                    ON CONFLICT (pot_key) DO UPDATE SET
                        accrued_sol = platform_fee_pots.accrued_sol + EXCLUDED.accrued_sol,
                        fee_wallet_address = EXCLUDED.fee_wallet_address,
                        circle_wallet_id = COALESCE(EXCLUDED.circle_wallet_id, platform_fee_pots.circle_wallet_id),
                        owner_user_wallet = COALESCE(EXCLUDED.owner_user_wallet, platform_fee_pots.owner_user_wallet),
                        agent_type = COALESCE(EXCLUDED.agent_type, platform_fee_pots.agent_type),
                        agent_id = COALESCE(EXCLUDED.agent_id, platform_fee_pots.agent_id),
                        updated_at = NOW()
                    RETURNING *
                    """,
                    {
                        "pot_key": pot_key,
                        "fee_wallet_address": fee_wallet_address,
                        "circle_wallet_id": circle_wallet_id,
                        "owner_user_wallet": owner_user_wallet,
                        "agent_type": agent_type,
                        "agent_id": agent_id,
                        "source": source,
                        "amount": amount,
                    },
                )
                row = cur.fetchone()
    return {
        "status": "accrued",
        "pot_key": pot_key,
        "amount": amount,
        "accrued_sol": float(row["accrued_sol"]) if row else amount,
    }


def accrue_agent_type_platform_fee(
    user_wallet: str,
    agent_type: str,
    amount_sol: float,
) -> dict[str, Any]:
    """Accrue fee held in the user's Circle wallet for a built-in agent."""
    user_wallet = (user_wallet or "").strip()
    agent_type = (agent_type or "").strip().lower()
    if not user_wallet or not agent_type or amount_sol <= 0:
        return {"status": "skipped"}
    try:
        from circle_dca_wallets import ensure_agent_wallet_for_user

        wallet = ensure_agent_wallet_for_user(user_wallet, agent_type)
    except Exception as exc:
        return {"error": f"Could not resolve agent wallet for fee accrual: {exc}"}
    return accrue_platform_fee(
        amount_sol=amount_sol,
        fee_wallet_address=wallet["agent_wallet_address"],
        circle_wallet_id=wallet.get("circle_wallet_id"),
        owner_user_wallet=user_wallet,
        agent_type=agent_type,
        source="agent_fee",
    )


def ensure_creator_agent_payment_wallet(agent_id: str, creator_user_wallet: str) -> dict[str, Any]:
    """
    Provision a unique Circle payment wallet for a public paid creator agent.
    All subscribers of this agent pay to the same address.
    """
    ensure_payments_schema()
    agent_id = (agent_id or "").strip()
    creator_user_wallet = (creator_user_wallet or "").strip()
    if not agent_id or not creator_user_wallet:
        return {"error": "agent_id and creator_user_wallet are required."}

    with _payments_lock:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM agent_payment_wallets WHERE agent_id = %s", (agent_id,))
                existing = cur.fetchone()
        if existing:
            return dict(existing)

        from circle_dca_wallets import (
            CircleDcaWalletError,
            circle_dca_enabled,
            normalize_agent_type,
        )

        # Reuse Circle create path with a synthetic user key so each agent gets its own wallet.
        if not circle_dca_enabled():
            return {
                "error": (
                    "Circle wallets are required for public paid agents. "
                    "Set CIRCLE_API_KEY and CIRCLE_ENTITY_SECRET."
                )
            }

        # Register creator_pay as allowed type for labeling; create via low-level helper.
        try:
            from circle_dca_wallets import _create_circle_wallet_for_user

            # Ensure type is accepted
            try:
                normalize_agent_type("creator_pay")
            except CircleDcaWalletError:
                # Inject into module allow-list for this process if not yet present
                import circle_dca_wallets as cw

                if "creator_pay" not in cw.AGENT_TYPES:
                    cw.AGENT_TYPES = tuple(list(cw.AGENT_TYPES) + ["creator_pay"])
                    cw.AGENT_TYPE_LABELS["creator_pay"] = "CreatorPay"

            created = _create_circle_wallet_for_user(f"pay:{agent_id}", "creator_pay")
        except Exception as exc:
            return {"error": f"Failed to create agent payment wallet: {exc}"}

        record = {
            "agent_id": agent_id,
            "creator_user_wallet": creator_user_wallet,
            "payment_wallet_address": created["agent_wallet_address"],
            "circle_wallet_id": created.get("circle_wallet_id"),
            "circle_wallet_set_id": created.get("circle_wallet_set_id"),
            "creator_available_sol": 0.0,
            "platform_accrued_sol": 0.0,
        }
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agent_payment_wallets (
                        agent_id, creator_user_wallet, payment_wallet_address,
                        circle_wallet_id, circle_wallet_set_id,
                        creator_available_sol, platform_accrued_sol
                    )
                    VALUES (
                        %(agent_id)s, %(creator_user_wallet)s, %(payment_wallet_address)s,
                        %(circle_wallet_id)s, %(circle_wallet_set_id)s,
                        0, 0
                    )
                    ON CONFLICT (agent_id) DO NOTHING
                    RETURNING *
                    """,
                    record,
                )
                row = cur.fetchone()
                if not row:
                    cur.execute("SELECT * FROM agent_payment_wallets WHERE agent_id = %s", (agent_id,))
                    row = cur.fetchone()
                # Mirror address onto launched_agents for easy UI reads
                cur.execute(
                    """
                    UPDATE launched_agents
                    SET payment_wallet_address = %s,
                        payment_circle_wallet_id = %s
                    WHERE id = %s
                    """,
                    (
                        record["payment_wallet_address"],
                        record.get("circle_wallet_id"),
                        agent_id,
                    ),
                )
        return dict(row) if row else record


def get_agent_payment_wallet(agent_id: str) -> Optional[dict[str, Any]]:
    ensure_payments_schema()
    agent_id = (agent_id or "").strip()
    if not agent_id:
        return None
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM agent_payment_wallets WHERE agent_id = %s", (agent_id,))
            row = cur.fetchone()
    return dict(row) if row else None


def record_creator_agent_subscription_split(
    *,
    agent_id: str,
    price_sol: float,
    platform_rate: float,
) -> dict[str, Any]:
    """
    After a buyer pays the full price into the agent payment wallet, split
    90% creator / 10% platform cut in the ledger.
    """
    ensure_payments_schema()
    pay = get_agent_payment_wallet(agent_id)
    if not pay:
        return {"error": "Agent payment wallet not found."}
    price = round(float(price_sol), 9)
    rate = min(max(float(platform_rate), 0.0), 0.5)
    platform_share = round(price * rate, 9)
    creator_share = round(price - platform_share, 9)

    with _payments_lock:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE agent_payment_wallets
                    SET creator_available_sol = creator_available_sol + %(creator)s,
                        platform_accrued_sol = platform_accrued_sol + %(platform)s,
                        updated_at = NOW()
                    WHERE agent_id = %(agent_id)s
                    RETURNING *
                    """,
                    {
                        "agent_id": agent_id,
                        "creator": creator_share,
                        "platform": platform_share,
                    },
                )
                row = cur.fetchone()

    if platform_share > 0 and row:
        accrue_platform_fee(
            amount_sol=platform_share,
            fee_wallet_address=row["payment_wallet_address"],
            circle_wallet_id=row.get("circle_wallet_id"),
            owner_user_wallet=row.get("creator_user_wallet"),
            agent_id=agent_id,
            source="creator_cut",
            pot_key=_pot_key_for_creator_agent(agent_id),
        )

    return {
        "status": "split",
        "price_sol": price,
        "creator_sol": creator_share,
        "platform_sol": platform_share,
        "payment_wallet": dict(row) if row else pay,
    }


def withdraw_creator_earnings(
    *,
    agent_id: str,
    creator_user_wallet: str,
    destination_wallet: Optional[str] = None,
    amount_sol: Optional[float] = None,
) -> dict[str, Any]:
    """Creator withdraws available 90% earnings from the agent payment wallet anytime."""
    ensure_payments_schema()
    agent_id = (agent_id or "").strip()
    creator_user_wallet = (creator_user_wallet or "").strip()
    pay = get_agent_payment_wallet(agent_id)
    if not pay:
        return {"error": "Agent payment wallet not found."}
    if pay.get("creator_user_wallet") != creator_user_wallet:
        return {"error": "Only the agent creator can withdraw earnings."}

    available = float(pay.get("creator_available_sol") or 0)
    if available <= 0:
        return {"error": "No creator earnings available to withdraw."}

    dest = (destination_wallet or creator_user_wallet).strip()
    # Leave transfer buffer in the payment wallet so the creator does not pay network fee from nowhere.
    max_send = round(max(0.0, available - TRANSFER_BUFFER_SOL), 9)
    if max_send <= 0:
        return {
            "error": (
                f"Available earnings ({available} SOL) are too small to withdraw after "
                f"the {TRANSFER_BUFFER_SOL} SOL transfer buffer."
            )
        }
    send_amount = max_send if amount_sol is None else round(min(float(amount_sol), max_send), 9)
    if send_amount <= 0:
        return {"error": "Withdraw amount must be greater than zero."}

    sent = _transfer_sol_from_circle_wallet(
        circle_wallet_id=str(pay.get("circle_wallet_id") or ""),
        from_pubkey=str(pay["payment_wallet_address"]),
        to_pubkey=dest,
        amount_sol=send_amount,
    )
    if sent.get("error"):
        return sent

    with _payments_lock:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE agent_payment_wallets
                    SET creator_available_sol = GREATEST(0, creator_available_sol - %(amt)s),
                        updated_at = NOW()
                    WHERE agent_id = %(agent_id)s
                    RETURNING *
                    """,
                    {"agent_id": agent_id, "amt": send_amount},
                )
                row = cur.fetchone()

    return {
        "status": "withdrawn",
        "amount_sol": send_amount,
        "destination": dest,
        "signature": sent.get("signature"),
        "explorer_url": sent.get("explorer_url"),
        "payment_wallet": dict(row) if row else pay,
        "message": f"Withdrew {send_amount} SOL to {dest[:4]}…{dest[-4:]}.",
    }


def _transfer_sol_from_circle_wallet(
    *,
    circle_wallet_id: str,
    from_pubkey: str,
    to_pubkey: str,
    amount_sol: float,
) -> dict[str, Any]:
    if not circle_wallet_id:
        return {"error": "Circle wallet id is missing for this fee pot."}
    try:
        from solders.pubkey import Pubkey
        from solders.system_program import TransferParams, transfer
        from dca_agent import _lamports, _send_signed_transaction
    except Exception as exc:
        return {"error": f"Solana transfer deps unavailable: {exc}"}

    try:
        ix = transfer(
            TransferParams(
                from_pubkey=Pubkey.from_string(from_pubkey),
                to_pubkey=Pubkey.from_string(to_pubkey),
                lamports=_lamports(amount_sol, 9),
            )
        )
    except Exception as exc:
        return {"error": f"Invalid transfer addresses: {exc}"}

    return _send_signed_transaction(None, [ix], circle_wallet_id=circle_wallet_id)


def list_fee_pots(min_accrued: float = 0.0) -> list[dict[str, Any]]:
    ensure_payments_schema()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM platform_fee_pots
                WHERE accrued_sol >= %s
                ORDER BY accrued_sol DESC
                """,
                (float(min_accrued),),
            )
            rows = cur.fetchall()
    return [dict(r) for r in rows]


def sweep_fee_pot(pot: dict[str, Any], *, force: bool = False) -> dict[str, Any]:
    """Sweep one pot to company treasury using the buffer / min-net rules."""
    ensure_payments_schema()
    treasury = get_company_treasury_wallet()
    if not treasury:
        return {"error": "COMPANY_TREASURY_WALLET (or TREASURY_PUBLIC_KEY) is not configured."}

    accrued = float(pot.get("accrued_sol") or 0)
    net = round(accrued - TRANSFER_BUFFER_SOL, 12)
    if not force and net <= MIN_SWEEP_NET_SOL:
        return {
            "status": "skipped",
            "reason": "below_min_net",
            "accrued_sol": accrued,
            "net_sol": net,
            "min_net_sol": MIN_SWEEP_NET_SOL,
            "buffer_sol": TRANSFER_BUFFER_SOL,
            "message": (
                f"Accrued {accrued} SOL; after {TRANSFER_BUFFER_SOL} buffer, net {net} SOL "
                f"is not above {MIN_SWEEP_NET_SOL}. Holding until next month."
            ),
        }
    if net <= 0:
        return {"status": "skipped", "reason": "non_positive_net", "accrued_sol": accrued}

    circle_wallet_id = pot.get("circle_wallet_id")
    from_pubkey = pot.get("fee_wallet_address")
    if not from_pubkey:
        return {"error": "Fee pot has no wallet address."}

    # Prefer stored circle id; else resolve from owner/agent_type.
    if not circle_wallet_id and pot.get("owner_user_wallet") and pot.get("agent_type"):
        try:
            from circle_dca_wallets import ensure_agent_wallet_for_user

            w = ensure_agent_wallet_for_user(pot["owner_user_wallet"], pot["agent_type"])
            circle_wallet_id = w.get("circle_wallet_id")
            from_pubkey = w.get("agent_wallet_address") or from_pubkey
        except Exception as exc:
            return {"error": f"Could not resolve Circle wallet for sweep: {exc}"}

    sent = _transfer_sol_from_circle_wallet(
        circle_wallet_id=str(circle_wallet_id or ""),
        from_pubkey=str(from_pubkey),
        to_pubkey=treasury,
        amount_sol=net,
    )
    sweep_id = uuid.uuid4().hex[:16]
    status = "confirmed" if not sent.get("error") else "failed"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO platform_fee_sweeps (
                    id, pot_key, fee_wallet_address, treasury_wallet,
                    accrued_before, buffer_sol, sent_sol, signature, explorer_url,
                    status, error
                )
                VALUES (
                    %(id)s, %(pot_key)s, %(fee_wallet_address)s, %(treasury_wallet)s,
                    %(accrued_before)s, %(buffer_sol)s, %(sent_sol)s, %(signature)s, %(explorer_url)s,
                    %(status)s, %(error)s
                )
                """,
                {
                    "id": sweep_id,
                    "pot_key": pot["pot_key"],
                    "fee_wallet_address": from_pubkey,
                    "treasury_wallet": treasury,
                    "accrued_before": accrued,
                    "buffer_sol": TRANSFER_BUFFER_SOL,
                    "sent_sol": net if status == "confirmed" else 0,
                    "signature": sent.get("signature"),
                    "explorer_url": sent.get("explorer_url"),
                    "status": status,
                    "error": sent.get("error"),
                },
            )
            if status == "confirmed":
                cur.execute(
                    """
                    UPDATE platform_fee_pots
                    SET accrued_sol = GREATEST(0, accrued_sol - %(net)s),
                        last_swept_at = NOW(),
                        updated_at = NOW()
                    WHERE pot_key = %(pot_key)s
                    """,
                    {"net": net, "pot_key": pot["pot_key"]},
                )
                # Keep creator agent mirror in sync
                if pot.get("agent_id") and str(pot.get("source") or "") == "creator_cut":
                    cur.execute(
                        """
                        UPDATE agent_payment_wallets
                        SET platform_accrued_sol = GREATEST(0, platform_accrued_sol - %(net)s),
                            updated_at = NOW()
                        WHERE agent_id = %(agent_id)s
                        """,
                        {"net": net, "agent_id": pot["agent_id"]},
                    )

    if status != "confirmed":
        return {"status": "failed", "error": sent.get("error"), "sweep_id": sweep_id}
    return {
        "status": "swept",
        "sweep_id": sweep_id,
        "sent_sol": net,
        "buffer_sol": TRANSFER_BUFFER_SOL,
        "treasury_wallet": treasury,
        "signature": sent.get("signature"),
        "explorer_url": sent.get("explorer_url"),
    }


def run_monthly_fee_sweep(*, force: bool = False) -> dict[str, Any]:
    """Sweep all eligible fee pots to the company treasury."""
    ensure_payments_schema()
    pots = list_fee_pots(min_accrued=0)
    results = []
    swept = skipped = failed = 0
    for pot in pots:
        result = sweep_fee_pot(pot, force=force)
        results.append({"pot_key": pot.get("pot_key"), **result})
        st = result.get("status")
        if st == "swept":
            swept += 1
        elif st == "skipped":
            skipped += 1
        else:
            failed += 1
    return {
        "status": "ok",
        "swept": swept,
        "skipped": skipped,
        "failed": failed,
        "results": results,
        "treasury_wallet": get_company_treasury_wallet(),
        "buffer_sol": TRANSFER_BUFFER_SOL,
        "min_net_sol": MIN_SWEEP_NET_SOL,
    }


def _is_last_day_of_month(now: datetime) -> bool:
    last = monthrange(now.year, now.month)[1]
    return now.day == last


def _maybe_run_scheduled_sweep() -> None:
    global _last_sweep_ym
    now = datetime.now(timezone.utc)
    if not _is_last_day_of_month(now):
        return
    if now.hour != SWEEP_HOUR_GMT:
        return
    ym = f"{now.year:04d}-{now.month:02d}"
    if _last_sweep_ym == ym:
        return
    print(f"  💸 Monthly platform fee sweep starting ({ym} {SWEEP_HOUR_GMT}:00 GMT)…")
    result = run_monthly_fee_sweep(force=False)
    _last_sweep_ym = ym
    print(
        f"  💸 Sweep done: swept={result.get('swept')} skipped={result.get('skipped')} "
        f"failed={result.get('failed')}"
    )


def platform_payments_scheduler_status() -> dict[str, Any]:
    return {
        "running": bool(_scheduler_thread and _scheduler_thread.is_alive()),
        "sweep_hour_gmt": SWEEP_HOUR_GMT,
        "transfer_buffer_sol": TRANSFER_BUFFER_SOL,
        "min_sweep_net_sol": MIN_SWEEP_NET_SOL,
        "treasury_wallet": get_company_treasury_wallet(),
        "last_sweep_ym": _last_sweep_ym,
    }


def start_platform_payments_scheduler(poll_seconds: int = 60) -> bool:
    global _scheduler_thread
    if _scheduler_thread and _scheduler_thread.is_alive():
        return False

    def _loop() -> None:
        while not _scheduler_stop.wait(poll_seconds):
            try:
                _maybe_run_scheduled_sweep()
            except Exception as exc:
                print(f"  ⚠️  Platform fee sweep scheduler error: {exc}")

    _scheduler_stop.clear()
    _scheduler_thread = threading.Thread(target=_loop, name="platform-fee-sweep", daemon=True)
    _scheduler_thread.start()
    return True


def stop_platform_payments_scheduler() -> None:
    _scheduler_stop.set()
