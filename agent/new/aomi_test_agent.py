"""Test Aomi Agent: Aomi builds a SOL transfer, Circle signs and broadcasts it."""

from __future__ import annotations

import os
import re
import uuid
from typing import Any, Optional

import requests

from circle_dca_wallets import (
    circle_dca_enabled,
    circle_sign_raw_transaction,
    ensure_agent_wallet_for_user,
    get_agent_wallet_address,
)

AOMI_API_URL = os.environ.get("AOMI_API_URL", "https://chat.aomi.dev").rstrip("/")
AOMI_ACCESS_TOKEN = os.environ.get("AOMI_ACCESS_TOKEN", "").strip()
AOMI_APPLICATION_ID = os.environ.get("AOMI_APPLICATION_ID", "").strip()
AOMI_AGENT_TYPE = "aomi_test"
AOMI_MAX_SEND_SOL = float(os.environ.get("AOMI_MAX_SEND_SOL", "0.05") or "0.05")

_SEND = re.compile(
    r"send\s+([\d.]+)\s*sol\s+to\s+([1-9A-HJ-NP-Za-km-z]{32,44})",
    re.I,
)


def aomi_configured() -> bool:
    return bool(AOMI_ACCESS_TOKEN)


def cluster_label() -> str:
    from dca_agent import SOLANA_CLUSTER

    raw = (SOLANA_CLUSTER or "devnet").strip().lower()
    if raw in ("mainnet", "mainnet-beta"):
        return "solana:mainnet"
    if raw == "testnet":
        return "solana:testnet"
    return "solana:devnet"


def wallet_status(user_wallet: str) -> dict[str, Any]:
    address = None
    error = None
    if circle_dca_enabled() and user_wallet:
        try:
            row = ensure_agent_wallet_for_user(user_wallet, AOMI_AGENT_TYPE)
            address = row.get("agent_wallet_address")
        except Exception as exc:
            error = str(exc)
            address = get_agent_wallet_address(user_wallet, AOMI_AGENT_TYPE)
    return {
        "agent_type": AOMI_AGENT_TYPE,
        "circle_configured": circle_dca_enabled(),
        "agent_wallet": address,
        "error": error,
        "cluster": cluster_label(),
        "max_send_sol": AOMI_MAX_SEND_SOL,
    }


def _headers(idempotency_key: Optional[str] = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {AOMI_ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key[:160]
    return headers


def _aomi(method: str, path: str, body: Optional[dict] = None, *, idempotency_key: Optional[str] = None) -> dict[str, Any]:
    if not aomi_configured():
        return {"error": "AOMI_ACCESS_TOKEN is not set in agent/new/.env"}
    url = path if path.startswith("http") else f"{AOMI_API_URL}{path if path.startswith('/') else '/' + path}"
    try:
        res = requests.request(
            method,
            url,
            headers=_headers(idempotency_key),
            json=body if method.upper() != "GET" else None,
            timeout=45,
        )
    except requests.RequestException as exc:
        return {"error": f"Aomi request failed: {exc}"}
    try:
        data = res.json()
    except ValueError:
        data = {"raw": (res.text or "")[:800]}
    if res.status_code >= 400:
        detail = data.get("error") if isinstance(data, dict) else data
        return {
            "error": f"Aomi {method} {path} failed ({res.status_code})",
            "detail": detail,
            "status_code": res.status_code,
        }
    return data if isinstance(data, dict) else {"data": data}


def _walk_operations(node: Any, found: list[dict[str, Any]], depth: int = 0) -> None:
    if depth > 5 or not isinstance(node, dict):
        return
    kind = str(node.get("kind") or "")
    name = str(node.get("name") or "")
    href = str(node.get("href") or "")
    if kind == "operation" or "transfer" in name.lower() or "transfer" in href.lower():
        found.append(node)
    for entry in node.get("entries") or []:
        if isinstance(entry, dict):
            _walk_operations(entry, found, depth + 1)
            href_entry = entry.get("href")
            if entry.get("kind") == "directory" and href_entry and depth < 3:
                child = _aomi("GET", str(href_entry))
                if not child.get("error"):
                    _walk_operations(child, found, depth + 1)


def _pick_transfer_operation() -> dict[str, Any]:
    catalog = _aomi("GET", "/v1/pipeline/svm")
    if catalog.get("error"):
        skills = _aomi("GET", "/v1/pipeline/skills")
        if skills.get("error"):
            return catalog
        catalog = skills
    found: list[dict[str, Any]] = []
    _walk_operations(catalog, found)
    ranked = sorted(
        found,
        key=lambda row: (
            0 if "transfer" in str(row.get("name") or row.get("href") or "").lower() else 1,
            str(row.get("name") or ""),
        ),
    )
    if not ranked:
        return {"error": "Aomi catalog has no SVM transfer operation", "catalog_keys": list(catalog)[:12]}
    chosen = ranked[0]
    href = chosen.get("href")
    if href:
        described = _aomi("GET", str(href))
        if not described.get("error"):
            return described
    return chosen


def _arguments_for(schema: dict[str, Any], *, payer: str, destination: str, amount_sol: float) -> dict[str, Any]:
    lamports = str(int(round(amount_sol * 1_000_000_000)))
    props = {}
    if isinstance(schema, dict):
        props = schema.get("properties") or {}
        if not props and isinstance(schema.get("inputSchema"), dict):
            props = schema["inputSchema"].get("properties") or {}
    if not props:
        return {
            "from": payer,
            "to": destination,
            "amount": lamports,
            "cluster": cluster_label(),
            "payer": payer,
        }
    args: dict[str, Any] = {}
    for key in props:
        low = key.lower()
        if low in ("to", "destination", "recipient", "receiver"):
            args[key] = destination
        elif low in ("from", "source", "owner", "sender", "payer", "authority"):
            args[key] = payer
        elif "lamport" in low or low in ("amount", "value", "quantity"):
            args[key] = lamports
        elif "cluster" in low or low == "network":
            args[key] = cluster_label()
        elif "sol" in low and "lamport" not in low:
            args[key] = str(amount_sol)
    return args


def _find_unsigned(node: Any, found: list[str]) -> None:
    if isinstance(node, dict):
        raw = node.get("unsigned_transaction_base64") or node.get("unsignedTransactionBase64")
        if isinstance(raw, str) and raw:
            found.append(raw)
        for value in node.values():
            _find_unsigned(value, found)
    elif isinstance(node, list):
        for item in node:
            _find_unsigned(item, found)


def _broadcast_signed(signed_b64: str) -> dict[str, Any]:
    from dca_agent import _confirm_transaction, _is_mainnet, sol_rpc

    try:
        sig = sol_rpc(
            "sendTransaction",
            [
                signed_b64,
                {
                    "encoding": "base64",
                    "skipPreflight": True,
                    "preflightCommitment": "confirmed",
                    "maxRetries": 3,
                },
            ],
        )
    except Exception as exc:
        return {"error": f"sendTransaction failed: {exc}"}
    confirm = _confirm_transaction(sig, timeout_s=45, encoded_tx=signed_b64)
    if not confirm.get("confirmed"):
        return {"status": "failed", "signature": sig, "error": confirm.get("error") or "not confirmed"}
    cluster = "mainnet" if _is_mainnet() else "devnet"
    return {
        "status": "success",
        "signature": sig,
        "explorer_url": f"https://explorer.solana.com/tx/{sig}?cluster={cluster}",
    }


def send_sol(user_wallet: str, destination: str, amount_sol: float) -> dict[str, Any]:
    user_wallet = (user_wallet or "").strip()
    destination = (destination or "").strip()
    if not user_wallet:
        return {"error": "Connect and sign in with your wallet first."}
    if not circle_dca_enabled():
        return {"error": "Circle is not configured (CIRCLE_API_KEY and CIRCLE_ENTITY_SECRET)."}
    if not aomi_configured():
        return {"error": "Set AOMI_ACCESS_TOKEN in agent/new/.env and restart the agent API."}
    try:
        amount_sol = float(amount_sol)
    except (TypeError, ValueError):
        return {"error": "amount_sol must be a number."}
    if amount_sol <= 0 or amount_sol > AOMI_MAX_SEND_SOL:
        return {"error": f"Amount must be between 0 and {AOMI_MAX_SEND_SOL} SOL."}
    try:
        from solders.pubkey import Pubkey

        Pubkey.from_string(destination)
    except Exception:
        return {"error": "Destination is not a valid Solana address."}

    wallet = ensure_agent_wallet_for_user(user_wallet, AOMI_AGENT_TYPE)
    payer = str(wallet.get("agent_wallet_address") or "")
    circle_id = str(wallet.get("circle_wallet_id") or "")
    if not payer or not circle_id:
        return {"error": "Circle agent wallet is not ready."}
    if payer == destination:
        return {"error": "Destination is the agent wallet itself."}

    operation = _pick_transfer_operation()
    if operation.get("error"):
        return operation
    schema = operation.get("inputSchema") if isinstance(operation.get("inputSchema"), dict) else operation
    arguments = _arguments_for(schema if isinstance(schema, dict) else {}, payer=payer, destination=destination, amount_sol=amount_sol)
    op_name = str(operation.get("name") or "transfer")
    build_body = {
        "operations": [{"name": op_name, "arguments": arguments}],
        "cluster": cluster_label(),
        "payer": payer,
    }
    built = _aomi("POST", "/v1/pipeline/svm/build", build_body, idempotency_key=uuid.uuid4().hex)
    if built.get("error"):
        built = _aomi(
            "POST",
            "/v1/pipeline/svm/build",
            {"operation": op_name, "arguments": arguments, "payer": payer, "cluster": cluster_label()},
            idempotency_key=uuid.uuid4().hex,
        )
    if built.get("error"):
        return {
            "error": built["error"],
            "detail": built.get("detail"),
            "operation": op_name,
            "arguments": arguments,
            "agent_wallet": payer,
        }
    if built.get("status") != "simulated":
        simulated = _aomi("POST", "/v1/pipeline/svm/simulate", built, idempotency_key=uuid.uuid4().hex)
        if not simulated.get("error"):
            built = simulated
    committed = _aomi("POST", "/v1/pipeline/svm/commit", built, idempotency_key=uuid.uuid4().hex)
    if committed.get("error"):
        return {
            "error": committed["error"],
            "detail": committed.get("detail"),
            "simulation": built.get("simulation"),
            "agent_wallet": payer,
        }
    unsigned: list[str] = []
    _find_unsigned(committed, unsigned)
    if not unsigned:
        _find_unsigned(built, unsigned)
    if not unsigned:
        return {
            "error": "Aomi committed the build but returned no unsigned Solana transaction to sign.",
            "digest": committed.get("digest") or built.get("digest"),
            "simulation": (committed.get("simulation") or built.get("simulation")),
            "agent_wallet": payer,
        }
    try:
        signed = circle_sign_raw_transaction(circle_id, unsigned[0])
    except Exception as exc:
        return {"error": f"Circle signing failed: {exc}", "agent_wallet": payer}
    sent = _broadcast_signed(signed)
    sent["agent_wallet"] = payer
    sent["destination"] = destination
    sent["amount_sol"] = amount_sol
    sent["aomi_digest"] = committed.get("digest")
    sent["simulation"] = committed.get("simulation") or built.get("simulation")
    sent["infra"] = "aomi+circle"
    return sent


def _sign_action(session_id: str, action: dict[str, Any], circle_id: str) -> dict[str, Any]:
    request = action.get("request") or {}
    unsigned: list[str] = []
    _find_unsigned(request, unsigned)
    if not unsigned:
        return {"error": "Aomi action has no unsigned transaction."}
    legs = []
    for raw in unsigned:
        signed = circle_sign_raw_transaction(circle_id, raw)
        sent = _broadcast_signed(signed)
        if sent.get("error"):
            return sent
        legs.append(
            {
                "id": action.get("id") or "tx",
                "status": "submitted",
                "transactionId": sent.get("signature"),
                "signedTransactionBase64": signed,
            }
        )
    result = _aomi(
        "POST",
        f"/v1/agent/chat/{session_id}/actions/{action.get('id')}/result",
        {"revision": int(action.get("revision") or 0), "result": {"status": "submitted", "legs": legs}},
        idempotency_key=uuid.uuid4().hex,
    )
    result["signatures"] = [leg["transactionId"] for leg in legs]
    return result


def _chat_turn(message: str, session_id: Optional[str], payer: str, circle_id: str) -> dict[str, Any]:
    body: dict[str, Any] = {
        "message": message,
        "userState": {
            "connection": {
                "is_connected": True,
                "provider": "circle",
                "provider_label": "Circle",
                "auth_method": "server",
            },
            "svm": {
                "address": payer,
                "cluster": cluster_label(),
                "wallet_name": "Test Aomi Circle",
                "transport": "circle",
                "capabilities": ["sign", "send"],
            },
        },
    }
    if session_id:
        body["sessionId"] = session_id
    if AOMI_APPLICATION_ID.isdigit():
        body["applicationId"] = int(AOMI_APPLICATION_ID)
    page = _aomi("POST", "/v1/agent/chat", body, idempotency_key=uuid.uuid4().hex)
    if page.get("error"):
        return page
    texts: list[str] = []
    signatures: list[str] = []
    cursor = page.get("cursor")
    session = page.get("session_id") or session_id
    events = list(page.get("events") or [])
    for _ in range(8):
        pending = False
        for event in events:
            if not isinstance(event, dict):
                continue
            if event.get("type") == "message" and event.get("sender") == "agent" and event.get("content"):
                texts.append(str(event["content"]))
            if event.get("type") == "error" and event.get("message"):
                texts.append(str(event["message"]))
            if event.get("type") == "action" and event.get("state") == "pending":
                pending = True
                signed = _sign_action(str(session), event, circle_id)
                if signed.get("error"):
                    return signed
                signatures.extend(signed.get("signatures") or [])
        if not pending and texts:
            break
        if not session:
            break
        nxt = _aomi("GET", f"/v1/agent/chat/{session}?wait=8000" + (f"&cursor={cursor}" if cursor else ""))
        if nxt.get("error"):
            break
        cursor = nxt.get("cursor") or cursor
        events = list(nxt.get("events") or [])
        if not events and texts:
            break
    reply = "\n".join(dict.fromkeys(texts)) or "Aomi returned no message."
    if signatures:
        reply = f"{reply}\n\nSent: {', '.join(signatures)}"
    return {"reply": reply, "session_id": session, "signatures": signatures}


def run_aomi_test_agent(
    user_input: str,
    conversation_history: list,
    user_wallet: Optional[str] = None,
    session_id: Optional[str] = None,
) -> tuple[str, list, list[dict[str, Any]]]:
    wallet = (user_wallet or "").strip()
    text = (user_input or "").strip()
    if not wallet:
        return "Connect and sign in with your wallet first.", conversation_history, []
    match = _SEND.search(text)
    if match:
        result = send_sol(wallet, match.group(2), float(match.group(1)))
        if result.get("error"):
            reply = str(result["error"])
        else:
            reply = (
                f"Sent {result.get('amount_sol')} SOL from {result.get('agent_wallet')} "
                f"to {result.get('destination')}. Signature: {result.get('signature')}"
            )
        return reply, conversation_history, [{"tool": "aomi_send_sol", "args": {"text": text}, "result": str(result)[:4000]}]

    if not aomi_configured():
        return "Set AOMI_ACCESS_TOKEN to chat with Aomi. You can still use Send SOL once it is set.", conversation_history, []
    status = wallet_status(wallet)
    if status.get("error") and not status.get("agent_wallet"):
        return str(status["error"]), conversation_history, []
    payer = str(status.get("agent_wallet") or "")
    ensured = ensure_agent_wallet_for_user(wallet, AOMI_AGENT_TYPE)
    turned = _chat_turn(text, session_id, payer, str(ensured.get("circle_wallet_id") or ""))
    if turned.get("error"):
        return str(turned["error"]), conversation_history, [{"tool": "aomi_chat", "args": {}, "result": str(turned)[:2000]}]
    return str(turned.get("reply") or ""), conversation_history, [
        {"tool": "aomi_chat", "args": {}, "result": str(turned)[:4000]}
    ]
