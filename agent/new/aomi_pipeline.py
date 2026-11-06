"""Aomi Pipeline gate for a Jupiter swap the DCA agent already built.

Stage the unsigned transaction, simulate it on a fork, check it against the
plan, then commit. Circle signs only after that commit.

Aomi accepts the swap only when the fee payer is the Solana wallet on the
session. Each Circle agent wallet signs its own session, so a new user does
not sign in and the shared device-login token is not the fee payer.
"""

from __future__ import annotations

import base64
import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

import requests

AOMI_API_URL = os.environ.get("AOMI_API_URL", "https://chat.aomi.dev").rstrip("/")
AOMI_ACCESS_TOKEN = os.environ.get("AOMI_ACCESS_TOKEN", "").strip()
AOMI_REFRESH_TOKEN = os.environ.get("AOMI_REFRESH_TOKEN", "").strip()
AOMI_CLIENT_ID = os.environ.get("AOMI_OAUTH_CLIENT_ID", "").strip()
AOMI_RESOURCE = os.environ.get("AOMI_RESOURCE", "https://chat.aomi.dev/v1/pipeline").strip()
_ENV_PATH = Path(__file__).resolve().parent / ".env"
_SESSION_PATH = Path(__file__).resolve().parent / ".aomi-wallet-sessions.json"
_token_lock = threading.Lock()
_session_lock = threading.Lock()
_SIWS_CHAIN = "solana:mainnet"


def _token_exp(token: str) -> int:
    try:
        payload = token.split(".")[1]
        padded = payload + "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded))
        return int(data.get("exp") or 0)
    except Exception:
        return 0


_expires_at = _token_exp(AOMI_ACCESS_TOKEN)


def aomi_configured() -> bool:
    return bool(AOMI_ACCESS_TOKEN or (AOMI_REFRESH_TOKEN and AOMI_CLIENT_ID))


def dca_gate_mode() -> str:
    raw = (os.environ.get("AOMI_DCA_MODE") or "gate").strip().lower()
    return raw if raw in ("gate", "log") else "gate"


def _persist_tokens() -> None:
    if not _ENV_PATH.exists():
        return
    updates = {
        "AOMI_ACCESS_TOKEN": AOMI_ACCESS_TOKEN,
        "AOMI_REFRESH_TOKEN": AOMI_REFRESH_TOKEN,
        "AOMI_TOKEN_EXPIRES_AT": str(_expires_at),
    }
    lines = _ENV_PATH.read_text(encoding="utf-8").splitlines()
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0] if "=" in line and not line.lstrip().startswith("#") else ""
        if key in updates:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, value in updates.items():
        if key not in seen:
            out.append(f"{key}={value}")
    _ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")


def _refresh_access_token() -> Optional[str]:
    """Mint a new pipeline access token. Aomi access tokens last about 5 minutes."""
    global AOMI_ACCESS_TOKEN, AOMI_REFRESH_TOKEN, _expires_at
    if not AOMI_REFRESH_TOKEN or not AOMI_CLIENT_ID:
        return AOMI_ACCESS_TOKEN or None
    try:
        response = requests.post(
            f"{AOMI_API_URL}/api/auth/oauth2/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": AOMI_REFRESH_TOKEN,
                "client_id": AOMI_CLIENT_ID,
                "resource": AOMI_RESOURCE,
            },
            headers={"Accept": "application/json"},
            timeout=30,
        )
        data = response.json()
    except Exception:
        return AOMI_ACCESS_TOKEN or None
    if response.status_code >= 400 or not isinstance(data, dict) or not data.get("access_token"):
        return AOMI_ACCESS_TOKEN or None
    AOMI_ACCESS_TOKEN = str(data["access_token"])
    if data.get("refresh_token"):
        AOMI_REFRESH_TOKEN = str(data["refresh_token"])
    if data.get("expires_at"):
        _expires_at = int(data["expires_at"])
    else:
        _expires_at = int(time.time()) + int(data.get("expires_in") or 300)
    try:
        _persist_tokens()
    except Exception:
        pass
    return AOMI_ACCESS_TOKEN


def _bearer() -> str:
    global AOMI_ACCESS_TOKEN
    with _token_lock:
        if not AOMI_ACCESS_TOKEN or (_expires_at and int(time.time()) >= _expires_at - 30):
            _refresh_access_token()
        return AOMI_ACCESS_TOKEN


def _widget_headers(token: Optional[str] = None) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": AOMI_API_URL,
        "Referer": f"{AOMI_API_URL}/",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _siws_message(challenge: dict[str, Any], address: str) -> str:
    return (
        f"{challenge['domain']} wants you to sign in with your Solana account:\n"
        f"{address}\n\n"
        "Sign in to Aomi.\n\n"
        f"URI: {challenge['uri']}\n"
        "Version: 1\n"
        f"Chain ID: {_SIWS_CHAIN}\n"
        f"Nonce: {challenge['nonce']}\n"
        f"Issued At: {challenge['issued_at']}"
    )


def _read_sessions() -> dict[str, Any]:
    try:
        data = json.loads(_SESSION_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_sessions(sessions: dict[str, Any]) -> None:
    tmp = _SESSION_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(sessions), encoding="utf-8")
    tmp.replace(_SESSION_PATH)


def _mint_wallet_session(address: str, circle_wallet_id: str) -> dict[str, Any]:
    from circle_dca_wallets import circle_sign_message

    challenge = requests.post(
        f"{AOMI_API_URL}/api/auth/widget/siws/nonce",
        json={"wallet_address": address, "chain_id": _SIWS_CHAIN},
        headers=_widget_headers(),
        timeout=30,
    )
    if challenge.status_code != 200:
        raise RuntimeError(f"Aomi sign-in challenge failed ({challenge.status_code}).")
    payload = challenge.json()
    if not isinstance(payload, dict) or not payload.get("nonce") or not payload.get("issued_at"):
        raise RuntimeError("Aomi sign-in challenge was incomplete.")
    message = _siws_message(payload, address)
    raw = circle_sign_message(circle_wallet_id, message)
    hex_body = raw[2:] if raw.startswith("0x") else raw
    try:
        signature = bytes.fromhex(hex_body)
    except ValueError as exc:
        raise RuntimeError("Circle message signature was not hex.") from exc
    if len(signature) != 64:
        raise RuntimeError("Circle message signature was not 64 bytes.")
    verified = requests.post(
        f"{AOMI_API_URL}/api/auth/widget/siws/verify",
        json={
            "message": message,
            "signature": base64.b64encode(signature).decode("ascii"),
            "wallet_address": address,
            "chain_id": _SIWS_CHAIN,
        },
        headers=_widget_headers(),
        timeout=30,
    )
    body = verified.json() if verified.content else {}
    token = body.get("access_token") if isinstance(body, dict) else None
    if verified.status_code != 200 or not isinstance(token, str) or not token:
        code = ""
        if isinstance(body, dict):
            err = body.get("error")
            if isinstance(err, str):
                code = err
            elif isinstance(err, dict):
                code = str(err.get("code") or "")
        suffix = f" ({code})" if code else ""
        raise RuntimeError(f"Aomi rejected the agent wallet sign-in{suffix}.")
    return {"access_token": token, "expires_at": int(body.get("expires_at") or 0)}


def ensure_wallet_session(address: str, circle_wallet_id: str, *, force: bool = False) -> str:
    """Return a pipeline bearer whose Solana wallet is this Circle address."""
    address = address.strip()
    with _session_lock:
        sessions = _read_sessions()
        current = sessions.get(address) if not force else None
        if isinstance(current, dict):
            expires_at = int(current.get("expires_at") or 0)
            token = current.get("access_token")
            if isinstance(token, str) and token and expires_at > int(time.time()) + 60:
                return token
        minted = _mint_wallet_session(address, circle_wallet_id)
        sessions[address] = minted
        try:
            _write_sessions(sessions)
        except Exception:
            pass
        return str(minted["access_token"])


def _headers(
    idempotency_key: Optional[str] = None,
    *,
    token: str,
    wallet_session: bool = False,
) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if wallet_session:
        headers["Origin"] = AOMI_API_URL
        headers["Referer"] = f"{AOMI_API_URL}/"
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key[:160]
    return headers


def _post(
    path: str,
    body: dict[str, Any],
    *,
    idempotency_key: Optional[str] = None,
    token: str,
    wallet_session: bool = False,
    refresh: Optional[Callable[[], str]] = None,
) -> dict[str, Any]:
    url = f"{AOMI_API_URL}{path}"

    def send(current: str) -> requests.Response:
        return requests.post(
            url,
            json=body,
            headers=_headers(idempotency_key, token=current, wallet_session=wallet_session),
            timeout=60,
        )

    try:
        response = send(token)
        if response.status_code == 401 and refresh:
            response = send(refresh())
    except requests.RequestException as exc:
        return {"error": f"Aomi request failed: {exc}", "retryable": True}
    try:
        data = response.json()
    except Exception:
        data = {"raw": response.text[:1500]}
    if response.status_code >= 400:
        detail = data if isinstance(data, dict) else {"raw": str(data)[:1500]}
        message = ""
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict):
                message = str(err.get("message") or err.get("code") or "")
            else:
                message = str(err or data.get("message") or data.get("detail") or "")
        return {
            "error": message or f"Aomi {path} HTTP {response.status_code}",
            "status_code": response.status_code,
            "detail": detail,
            "retryable": response.status_code in (408, 409, 425, 429) or response.status_code >= 500,
        }
    return data if isinstance(data, dict) else {"result": data}


def _find_unsigned(node: Any, found: list[str]) -> None:
    if isinstance(node, dict):
        for key in ("unsigned_transaction_base64", "unsignedTransactionBase64", "tx", "transaction"):
            raw = node.get(key)
            if isinstance(raw, str) and len(raw) > 40:
                found.append(raw)
            elif isinstance(raw, dict):
                inner = raw.get("tx") or raw.get("transaction")
                if isinstance(inner, str) and len(inner) > 40:
                    found.append(inner)
        for value in node.values():
            _find_unsigned(value, found)
    elif isinstance(node, list):
        for item in node:
            _find_unsigned(item, found)


def _numbers(node: Any, found: list[tuple[str, int]]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, bool):
                continue
            if isinstance(value, int):
                found.append((str(key).lower(), value))
            elif isinstance(value, str) and value.lstrip("-").isdigit():
                found.append((str(key).lower(), int(value)))
            else:
                _numbers(value, found)
    elif isinstance(node, list):
        for item in node:
            _numbers(item, found)


def _mints(node: Any, found: list[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if str(key).lower() in ("mint", "outputmint", "output_mint", "tokenmint") and isinstance(value, str):
                found.append(value)
            else:
                _mints(value, found)
    elif isinstance(node, list):
        for item in node:
            _mints(item, found)


def _simulation_failed(simulation: Any) -> Optional[str]:
    if not isinstance(simulation, dict):
        return None
    err = simulation.get("error") or simulation.get("err")
    if err:
        return str(err)[:500]
    status = str(simulation.get("status") or simulation.get("result") or "").lower()
    if status in ("failed", "error", "reverted"):
        return status
    return None


def _plan_check(simulation: Any, plan: dict[str, Any]) -> Optional[str]:
    failed = _simulation_failed(simulation)
    if failed:
        return f"Fork run failed: {failed}"
    if not isinstance(simulation, dict):
        return None
    max_input = int(plan.get("max_input_raw") or 0)
    output_mint = str(plan.get("output_mint") or "")
    min_out = int(plan.get("min_out_raw") or 0)
    nums: list[tuple[str, int]] = []
    _numbers(simulation, nums)
    if max_input > 0:
        spent = [
            abs(value)
            for key, value in nums
            if value < 0 and any(token in key for token in ("lamport", "sol", "native", "input"))
        ]
        if spent and max(spent) > int(max_input * 1.02):
            return "Fork spend is above the plan amount per buy."
    mints: list[str] = []
    _mints(simulation, mints)
    if output_mint and mints and output_mint not in mints:
        return "Fork output mint does not match the plan."
    if min_out > 0:
        received = [
            value
            for key, value in nums
            if value > 0 and any(token in key for token in ("out", "output", "received", "destination"))
        ]
        if received and max(received) < min_out:
            return "Fork output is below the plan minimum after slippage."
    return None


def gate_swap(
    unsigned_tx_b64: str,
    plan: Optional[dict[str, Any]] = None,
    *,
    signer_address: Optional[str] = None,
    circle_wallet_id: Optional[str] = None,
) -> dict[str, Any]:
    """Stage, simulate, and commit one unsigned swap. Circle signs after this."""
    plan = plan or {}
    holder: dict[str, str] = {}
    wallet_session = bool(signer_address and circle_wallet_id)
    if wallet_session:
        try:
            holder["token"] = ensure_wallet_session(str(signer_address), str(circle_wallet_id))
        except Exception as exc:
            return {"status": "skipped", "error": str(exc), "aomi_step": "session"}

        def refresh() -> str:
            holder["token"] = ensure_wallet_session(
                str(signer_address),
                str(circle_wallet_id),
                force=True,
            )
            return holder["token"]
    elif not aomi_configured():
        return {"error": "Set AOMI_ACCESS_TOKEN and AOMI_REFRESH_TOKEN in agent/new/.env and restart the agent API."}
    else:
        holder["token"] = _bearer()

        def refresh() -> str:
            with _token_lock:
                _refresh_access_token()
            holder["token"] = AOMI_ACCESS_TOKEN
            return holder["token"]

    def post(path: str, body: dict[str, Any], key: str) -> dict[str, Any]:
        return _post(
            path,
            body,
            idempotency_key=key,
            token=holder["token"],
            wallet_session=wallet_session,
            refresh=refresh,
        )

    idem = str(plan.get("idempotency_key") or uuid.uuid4().hex)
    stage_body = {"kind": "transaction", "transaction": {"tx": unsigned_tx_b64}}
    staged = post("/v1/pipeline/svm/stage", stage_body, f"{idem}:stage")
    if staged.get("error") and staged.get("status_code") == 404:
        staged = post("/v1/pipeline/svm/build", stage_body, f"{idem}:stage")
    if staged.get("error"):
        return {
            "status": "skipped",
            "error": staged["error"],
            "detail": staged.get("detail"),
            "aomi_step": "stage",
        }

    simulated = staged if str(staged.get("status") or "").lower() == "simulated" else post(
        "/v1/pipeline/svm/simulate",
        {"build": staged},
        f"{idem}:simulate",
    )
    if simulated.get("error"):
        return {
            "status": "skipped",
            "error": simulated["error"],
            "detail": simulated.get("detail"),
            "aomi_step": "simulate",
        }

    simulation = simulated.get("simulation") if isinstance(simulated.get("simulation"), dict) else simulated
    summary = simulated.get("summary") or (simulation.get("summary") if isinstance(simulation, dict) else None)
    reason = _plan_check(simulation if isinstance(simulation, dict) else {}, plan)
    mode = dca_gate_mode()
    if reason and mode == "gate":
        return {
            "status": "skipped",
            "error": reason,
            "aomi_summary": summary,
            "aomi_digest": simulated.get("digest"),
            "aomi_step": "plan_check",
        }

    committed = post("/v1/pipeline/svm/commit", {"build": simulated}, idem)
    if committed.get("error"):
        return {
            "status": "skipped",
            "error": committed["error"],
            "detail": committed.get("detail"),
            "aomi_summary": summary,
            "aomi_step": "commit",
            "retryable": committed.get("retryable"),
        }

    unsigned: list[str] = []
    _find_unsigned(committed, unsigned)
    if not unsigned:
        _find_unsigned(simulated, unsigned)
    return {
        "ok": True,
        "unsigned_transaction_base64": unsigned[0] if unsigned else unsigned_tx_b64,
        "aomi_digest": committed.get("digest") or simulated.get("digest"),
        "aomi_summary": summary,
        "aomi_check": reason or "ok",
        "aomi_mode": mode,
    }
