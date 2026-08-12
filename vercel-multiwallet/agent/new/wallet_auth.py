"""
Wallet signature authentication for the DCA API.

Users sign a server-issued challenge with their Solana wallet to obtain a
short-lived session token. Protected routes require Authorization: Bearer <token>.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

try:
    from solders.pubkey import Pubkey
    from solders.signature import Signature

    HAS_SOLDERS = True
except ImportError:
    HAS_SOLDERS = False

from db import get_conn, init_db

PUBLIC_APP_URL = os.environ.get("BITAGENTS_PUBLIC_URL", "https://bitagents.app").rstrip("/")
SESSION_TTL_HOURS = int(os.environ.get("DCA_SESSION_TTL_HOURS", "24"))
CHALLENGE_TTL_MINUTES = int(os.environ.get("DCA_CHALLENGE_TTL_MINUTES", "10"))
INTERNAL_API_KEY = (
    os.environ.get("AGENTS_INTERNAL_API_KEY", "").strip()
    or os.environ.get("DCA_INTERNAL_API_KEY", "").strip()
)

_challenge_lock = threading.Lock()
_recent_challenges: dict[str, list[float]] = {}


def internal_api_configured() -> bool:
    return bool(INTERNAL_API_KEY)


def verify_internal_api_key(provided: Optional[str]) -> bool:
    if not INTERNAL_API_KEY:
        return True
    return bool(provided) and secrets.compare_digest(provided, INTERNAL_API_KEY)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _rate_limit_challenge(key: str, limit: int = 12, window_seconds: int = 60) -> bool:
    now = _utcnow().timestamp()
    with _challenge_lock:
        bucket = _recent_challenges.setdefault(key, [])
        bucket[:] = [t for t in bucket if now - t < window_seconds]
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True


def verify_wallet_signature(user_wallet: str, message: str, signature_b58: str) -> bool:
    if not HAS_SOLDERS:
        return False
    try:
        pubkey = Pubkey.from_string(user_wallet.strip())
        signature = Signature.from_string(signature_b58.strip())
        return signature.verify(pubkey, message.encode("utf-8"))
    except Exception:
        return False


def create_auth_challenge(user_wallet: str) -> dict[str, Any]:
    user_wallet = user_wallet.strip()
    if len(user_wallet) < 32:
        return {"error": "Invalid wallet address."}

    if not _rate_limit_challenge(user_wallet):
        return {"error": "Too many auth attempts. Wait a minute and try again."}

    init_db()
    nonce = secrets.token_urlsafe(16)
    expires = _utcnow() + timedelta(minutes=CHALLENGE_TTL_MINUTES)
    message = (
        "Sign in to BIT Agents\n\n"
        "By signing this message, you agree to the BIT Agents:\n"
        f"- Terms of Service: {PUBLIC_APP_URL}/terms\n"
        f"- Privacy Policy: {PUBLIC_APP_URL}/privacy\n"
        f"- Risk Disclaimer: {PUBLIC_APP_URL}/risk-disclaimer\n\n"
        "This signature does not authorize any transaction or token transfer.\n\n"
        f"Wallet: {user_wallet}\n"
        f"Nonce: {nonce}\n"
        f"Expires: {expires.isoformat()}"
    )

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO wallet_auth_challenges (nonce, user_wallet, message, expires_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (nonce) DO NOTHING
                """,
                (nonce, user_wallet, message, expires),
            )

    return {
        "user_wallet": user_wallet,
        "message": message,
        "nonce": nonce,
        "expires_at": expires.isoformat(),
    }


def verify_auth_challenge(
    user_wallet: str,
    message: str,
    signature: str,
) -> dict[str, Any]:
    user_wallet = user_wallet.strip()
    if not verify_wallet_signature(user_wallet, message, signature):
        return {"error": "Invalid wallet signature."}

    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT nonce, user_wallet, message, expires_at, used
                FROM wallet_auth_challenges
                WHERE user_wallet = %s AND message = %s
                ORDER BY expires_at DESC
                LIMIT 1
                """,
                (user_wallet, message),
            )
            row = cur.fetchone()

            if not row:
                return {"error": "Unknown or expired auth challenge. Request a new one."}
            if row["used"]:
                return {"error": "Challenge already used. Request a new one."}
            expires_at = row["expires_at"]
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < _utcnow():
                return {"error": "Auth challenge expired. Request a new one."}

            token = secrets.token_urlsafe(32)
            token_hash = _hash_token(token)
            session_expires = _utcnow() + timedelta(hours=SESSION_TTL_HOURS)

            cur.execute(
                """
                INSERT INTO wallet_sessions (token_hash, user_wallet, expires_at)
                VALUES (%s, %s, %s)
                """,
                (token_hash, user_wallet, session_expires),
            )
            cur.execute(
                "UPDATE wallet_auth_challenges SET used = TRUE WHERE nonce = %s",
                (row["nonce"],),
            )

    return {
        "status": "authenticated",
        "token": token,
        "user_wallet": user_wallet,
        "expires_at": session_expires.isoformat(),
    }


def resolve_session_token(token: str) -> Optional[str]:
    if not token or not token.strip():
        return None
    init_db()
    token_hash = _hash_token(token.strip())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_wallet, expires_at FROM wallet_sessions
                WHERE token_hash = %s
                LIMIT 1
                """,
                (token_hash,),
            )
            row = cur.fetchone()
            if not row:
                return None
            expires_at = row["expires_at"]
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < _utcnow():
                cur.execute("DELETE FROM wallet_sessions WHERE token_hash = %s", (token_hash,))
                return None
            return row["user_wallet"]


def revoke_session_token(token: str) -> bool:
    if not token:
        return False
    init_db()
    token_hash = _hash_token(token.strip())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM wallet_sessions WHERE token_hash = %s", (token_hash,))
            return cur.rowcount > 0


def get_session_info(token: str) -> Optional[dict[str, Any]]:
    wallet = resolve_session_token(token)
    if not wallet:
        return None
    init_db()
    token_hash = _hash_token(token.strip())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_wallet, expires_at FROM wallet_sessions WHERE token_hash = %s",
                (token_hash,),
            )
            row = cur.fetchone()
    if not row:
        return None
    expires_at = row["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return {
        "user_wallet": row["user_wallet"],
        "expires_at": expires_at.isoformat(),
    }
