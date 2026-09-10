"""
Circle developer-controlled wallets for per-user agent addresses.

Each (user_wallet, agent_type) pair gets a persistent Solana wallet created once
and stored in Postgres. Entity-secret ciphertext uses RSA-OAEP SHA-256.

Agent types: dca | easya | volume | hedge_fund

Docs:
  https://developers.circle.com/wallets/dev-controlled/create-your-first-wallet
  https://developers.circle.com/wallets/dev-controlled/register-entity-secret
  https://developers.circle.com/wallets/sign-transactions
"""

from __future__ import annotations

import base64
import os
import threading
import uuid
from typing import Any, Optional

import requests

from db import get_user_agent_wallet, save_user_agent_wallet

CIRCLE_API_BASE = os.environ.get("CIRCLE_API_BASE", "https://api.circle.com/v1/w3s").rstrip("/")
CIRCLE_API_KEY = os.environ.get("CIRCLE_API_KEY", "").strip()
CIRCLE_ENTITY_SECRET = os.environ.get("CIRCLE_ENTITY_SECRET", "").strip()
CIRCLE_WALLET_SET_ID = os.environ.get("CIRCLE_WALLET_SET_ID", "").strip()

AGENT_TYPES = ("dca", "easya", "volume", "hedge_fund")
AGENT_TYPE_LABELS = {
    "dca": "DCA",
    "easya": "EasyA",
    "volume": "Volume",
    "hedge_fund": "HedgeFund",
}

_wallet_set_lock = threading.Lock()
_cached_wallet_set_id: Optional[str] = None
_sdk_client = None
_sdk_lock = threading.Lock()
_pubkey_lock = threading.Lock()
_cached_entity_public_key: Optional[str] = None


class CircleDcaWalletError(RuntimeError):
    pass


CircleAgentWalletError = CircleDcaWalletError


def circle_dca_enabled() -> bool:
    return bool(CIRCLE_API_KEY and CIRCLE_ENTITY_SECRET)


circle_agent_wallets_enabled = circle_dca_enabled


def normalize_agent_type(agent_type: str) -> str:
    value = (agent_type or "").strip().lower()
    aliases = {
        "kickstart": "easya",
        "easya_analysis": "easya",
        "hf": "hedge_fund",
        "hedgefund": "hedge_fund",
        "volume2": "volume",
        "bitagents_volume": "volume",
    }
    value = aliases.get(value, value)
    if value not in AGENT_TYPES:
        raise CircleDcaWalletError(
            f"Unknown agent_type '{agent_type}'. Expected one of: {', '.join(AGENT_TYPES)}"
        )
    return value


def _validate_entity_secret() -> str:
    secret = CIRCLE_ENTITY_SECRET.strip()
    if not secret:
        raise CircleDcaWalletError("CIRCLE_ENTITY_SECRET is not configured.")
    if len(secret) != 64 or any(c not in "0123456789abcdefABCDEF" for c in secret):
        raise CircleDcaWalletError(
            "CIRCLE_ENTITY_SECRET must be the registered 64-char hex secret from Circle Console "
            "(https://developers.circle.com/wallets/dev-controlled/register-entity-secret). "
            "Do not paste an API key or a pre-encrypted ciphertext."
        )
    return secret


def circle_blockchain_for_cluster() -> str:
    cluster = os.environ.get("SOLANA_CLUSTER", "devnet").strip().lower()
    rpc = os.environ.get("SOLANA_RPC_URL", "").strip().lower()
    if cluster in ("mainnet", "mainnet-beta"):
        return "SOL"
    if "mainnet" in rpc and "devnet" not in rpc:
        return "SOL"
    return "SOL-DEVNET"


def _try_sdk_client():
    """Return official Circle SDK client when the package is installed."""
    global _sdk_client
    if _sdk_client is not None:
        return _sdk_client
    with _sdk_lock:
        if _sdk_client is not None:
            return _sdk_client
        try:
            from circle.web3 import utils
        except ImportError:
            return None
        try:
            _sdk_client = utils.init_developer_controlled_wallets_client(
                api_key=CIRCLE_API_KEY,
                entity_secret=_validate_entity_secret(),
            )
            return _sdk_client
        except Exception as exc:
            print(f"  ⚠️  Circle SDK init failed, using REST client: {exc}")
            return None


def _auth_headers() -> dict[str, str]:
    if not CIRCLE_API_KEY:
        raise CircleDcaWalletError("CIRCLE_API_KEY is not configured.")
    return {
        "Authorization": f"Bearer {CIRCLE_API_KEY}",
        "Content-Type": "application/json",
    }


def _entity_public_key() -> str:
    global _cached_entity_public_key
    if _cached_entity_public_key:
        return _cached_entity_public_key
    with _pubkey_lock:
        if _cached_entity_public_key:
            return _cached_entity_public_key
        resp = requests.get(
            f"{CIRCLE_API_BASE}/config/entity/publicKey",
            headers=_auth_headers(),
            timeout=30,
        )
        if not resp.ok:
            raise CircleDcaWalletError(
                f"Circle public key fetch failed: {resp.status_code} {resp.text[:300]}"
            )
        public_key = (resp.json().get("data") or {}).get("publicKey")
        if not public_key:
            raise CircleDcaWalletError("Circle public key response missing publicKey.")
        _cached_entity_public_key = str(public_key)
        return _cached_entity_public_key


def _entity_secret_ciphertext() -> str:
    """
    Fresh ciphertext per request (Circle replay protection).
    Must use RSA-OAEP with SHA-256 — default SHA-1 produces 'entity secret is invalid'.
    """
    try:
        from Crypto.Cipher import PKCS1_OAEP
        from Crypto.Hash import SHA256
        from Crypto.PublicKey import RSA
    except ImportError as exc:
        raise CircleDcaWalletError(
            "pycryptodome is required for Circle wallets: pip install pycryptodome"
        ) from exc

    secret_hex = _validate_entity_secret()
    rsa_key = RSA.import_key(_entity_public_key())
    cipher = PKCS1_OAEP.new(rsa_key, hashAlgo=SHA256)
    encrypted = cipher.encrypt(bytes.fromhex(secret_hex))
    return base64.b64encode(encrypted).decode("ascii")


def _circle_post(path: str, payload: dict[str, Any], *, with_entity_secret: bool = True) -> dict[str, Any]:
    body: dict[str, Any] = {
        "idempotencyKey": str(uuid.uuid4()),
        **payload,
    }
    if with_entity_secret:
        body["entitySecretCiphertext"] = _entity_secret_ciphertext()
    resp = requests.post(
        f"{CIRCLE_API_BASE}{path}",
        headers=_auth_headers(),
        json=body,
        timeout=60,
    )
    data = resp.json() if resp.content else {}
    if not resp.ok:
        message = data.get("message") or data.get("code") or resp.text[:500]
        hint = ""
        if "entity secret" in str(message).lower():
            hint = (
                " Register/re-register the entity secret for this API key: "
                "https://developers.circle.com/wallets/dev-controlled/register-entity-secret"
            )
        raise CircleDcaWalletError(f"Circle API {path} failed ({resp.status_code}): {message}.{hint}")
    return data.get("data") or data


def _ensure_wallet_set_id() -> str:
    global _cached_wallet_set_id
    if CIRCLE_WALLET_SET_ID:
        return CIRCLE_WALLET_SET_ID
    if _cached_wallet_set_id:
        return _cached_wallet_set_id

    with _wallet_set_lock:
        if _cached_wallet_set_id:
            return _cached_wallet_set_id

        # Prefer REST — Circle Python SDK often hits circular-import issues for CreateWalletRequest.
        created = _circle_post("/developer/walletSets", {"name": "BITAGENTS Per-User Agent Wallets"})
        wallet_set = created.get("walletSet") or created.get("wallet_set") or created
        wallet_set_id = wallet_set.get("id") if isinstance(wallet_set, dict) else None
        if not wallet_set_id:
            raise CircleDcaWalletError("Circle wallet set creation returned no id.")
        _cached_wallet_set_id = str(wallet_set_id)
        print(
            f"  ℹ️  Created Circle wallet set {_cached_wallet_set_id}. "
            "Set CIRCLE_WALLET_SET_ID in .env to reuse it across restarts."
        )
        return _cached_wallet_set_id


def _ref_id(agent_type: str, user_wallet: str) -> str:
    # Circle refId max length is generous; keep stable and unique per agent.
    return f"{agent_type}:{user_wallet.strip()}"[:128]


def _create_circle_wallet_for_user(user_wallet: str, agent_type: str) -> dict[str, Any]:
    agent_type = normalize_agent_type(agent_type)
    wallet_set_id = _ensure_wallet_set_id()
    blockchain = circle_blockchain_for_cluster()
    label = AGENT_TYPE_LABELS.get(agent_type, agent_type.upper())
    payload = {
        "walletSetId": wallet_set_id,
        "blockchains": [blockchain],
        "count": 1,
        "accountType": "EOA",
        "metadata": [
            {
                "name": f"{label} Agent {user_wallet[:8]}",
                "refId": _ref_id(agent_type, user_wallet),
            }
        ],
    }

    data = _circle_post("/developer/wallets", payload)
    wallets = data.get("wallets") or []
    if not wallets:
        raise CircleDcaWalletError("Circle wallet creation returned no wallets.")
    wallet = wallets[0]
    address = wallet.get("address")
    wallet_id = wallet.get("id")
    if not address or not wallet_id:
        raise CircleDcaWalletError("Circle wallet response missing address or id.")
    return {
        "user_wallet": user_wallet.strip(),
        "agent_type": agent_type,
        "agent_wallet_address": str(address),
        "circle_wallet_id": str(wallet_id),
        "circle_wallet_set_id": wallet_set_id,
        "blockchain": blockchain,
    }


def ensure_agent_wallet_for_user(user_wallet: str, agent_type: str) -> dict[str, Any]:
    """Return the persistent agent wallet for (user, agent_type); create via Circle if needed."""
    from db import init_db

    init_db()
    user_wallet = (user_wallet or "").strip()
    agent_type = normalize_agent_type(agent_type)
    if not user_wallet:
        raise CircleDcaWalletError("User wallet address is required.")
    if not circle_dca_enabled():
        raise CircleDcaWalletError(
            "Circle agent wallets are not configured. Set CIRCLE_API_KEY and CIRCLE_ENTITY_SECRET."
        )

    existing = get_user_agent_wallet(user_wallet, agent_type)
    if existing:
        return existing

    created = _create_circle_wallet_for_user(user_wallet, agent_type)
    save_user_agent_wallet(created)
    return get_user_agent_wallet(user_wallet, agent_type) or created


def ensure_dca_agent_wallet_for_user(user_wallet: str) -> dict[str, Any]:
    return ensure_agent_wallet_for_user(user_wallet, "dca")


def get_agent_wallet_address(user_wallet: str, agent_type: str) -> Optional[str]:
    if not user_wallet:
        return None
    if not circle_dca_enabled():
        return None
    try:
        return ensure_agent_wallet_for_user(user_wallet, agent_type)["agent_wallet_address"]
    except CircleDcaWalletError as exc:
        print(f"  ⚠️  Circle {agent_type} wallet unavailable: {exc}")
        return None
    except Exception as exc:
        print(f"  ⚠️  Circle {agent_type} wallet unexpected error: {exc}")
        return None


def get_dca_agent_wallet_address(user_wallet: str) -> Optional[str]:
    return get_agent_wallet_address(user_wallet, "dca")


def circle_sign_raw_transaction(wallet_id: str, raw_transaction_b64: str) -> str:
    """Sign a base64 Solana transaction via Circle Signing API."""
    data = _circle_post(
        "/developer/sign/transaction",
        {
            "walletId": wallet_id,
            "rawTransaction": raw_transaction_b64,
        },
    )
    signed = data.get("signedTransaction") or data.get("signed_transaction")
    if not signed:
        raise CircleDcaWalletError("Circle signTransaction returned no signedTransaction.")
    return str(signed)


def circle_sign_versioned_message(wallet_id: str, msg: Any) -> str:
    """Sign a solders MessageV0 and return base64-encoded signed transaction bytes."""
    try:
        from solders.signature import Signature
        from solders.transaction import VersionedTransaction
    except ImportError as exc:
        raise CircleDcaWalletError("solders is required for Circle signing.") from exc

    num_sigs = int(msg.header.num_required_signatures)
    placeholders = [Signature(bytes(64)) for _ in range(max(num_sigs, 1))]
    unsigned = VersionedTransaction.populate(msg, placeholders)
    raw_b64 = base64.b64encode(bytes(unsigned)).decode("ascii")
    return circle_sign_raw_transaction(wallet_id, raw_b64)


def _load_fallback_keypair(agent_type: str):
    agent_type = normalize_agent_type(agent_type)
    if agent_type == "dca":
        from dca_agent import load_keypair

        return load_keypair()
    if agent_type == "easya":
        from easya_trading_ledger import load_easya_keypair

        return load_easya_keypair()
    if agent_type == "volume":
        from volume_ledger import load_volume_keypair

        return load_volume_keypair()
    if agent_type == "hedge_fund":
        from hedge_fund_ledger import load_hf_keypair

        return load_hf_keypair()
    return None


def resolve_agent_signing_context(
    user_wallet: Optional[str],
    agent_type: str = "dca",
) -> dict[str, Any]:
    """
    Resolve how to sign agent transactions for a user.
    Prefers Circle per-user wallet; falls back to shared local keypair for that agent.
    """
    agent_type = normalize_agent_type(agent_type)
    user_wallet = (user_wallet or "").strip()
    if user_wallet and circle_dca_enabled():
        try:
            wallet = ensure_agent_wallet_for_user(user_wallet, agent_type)
            return {
                "mode": "circle",
                "agent_type": agent_type,
                "user_wallet": user_wallet,
                "wallet_id": wallet["circle_wallet_id"],
                "pubkey": wallet["agent_wallet_address"],
            }
        except Exception as exc:
            print(f"  ⚠️  Circle {agent_type} signing unavailable, falling back to local key: {exc}")

    keypair = _load_fallback_keypair(agent_type)
    if keypair:
        return {
            "mode": "local",
            "agent_type": agent_type,
            "user_wallet": user_wallet or None,
            "keypair": keypair,
            "pubkey": str(keypair.pubkey()),
        }

    return {"mode": "none", "agent_type": agent_type, "pubkey": None}


def resolve_dca_signing_context(user_wallet: Optional[str]) -> dict[str, Any]:
    return resolve_agent_signing_context(user_wallet, "dca")
