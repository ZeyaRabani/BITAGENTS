"""Bridge from BITAGENTS to an Aomi backend: agent wallet, chat turns, signing lane.

LOCAL DEVELOPMENT AUTH. This module signs Aomi session bearers itself with the
dev issuer keys that ship in the Aomi repos, and seeds the Aomi user row
directly. That only works against a local Aomi stack. A hosted deployment needs
Aomi to issue BITAGENTS a partner credential that can act for a user; that
credential does not exist yet.
"""

from __future__ import annotations

import base64
import json
import os
import time
import uuid
from typing import Any, Optional

import psycopg2
import requests
from fastapi import HTTPException

API = os.environ.get("AOMI_API_URL", "").rstrip("/")            # public Agent API (api-server)
BACKEND = os.environ.get("AOMI_BACKEND_URL", "").rstrip("/")    # account routes
DEV_DB = os.environ.get("AOMI_DEV_DATABASE_URL", "")
EDGE_KEY_FILE = os.environ.get("AOMI_DEV_EDGE_KEY_FILE", "")
BFF_KEY_FILE = os.environ.get("AOMI_DEV_BFF_KEY_FILE", "")
WALLET_PREFIX = "BITAGENTS "


def configured() -> Optional[str]:
    """None when usable, otherwise the reason it is not."""
    missing = [k for k, v in (("AOMI_API_URL", API), ("AOMI_BACKEND_URL", BACKEND), ("AOMI_DEV_DATABASE_URL", DEV_DB),
                              ("AOMI_DEV_EDGE_KEY_FILE", EDGE_KEY_FILE), ("AOMI_DEV_BFF_KEY_FILE", BFF_KEY_FILE)) if not v]
    return f"This server is not connected to an Aomi backend ({', '.join(missing)} not set)." if missing else None


def _require() -> None:
    reason = configured()
    if reason:
        raise HTTPException(503, reason)


def _pem(path: str) -> bytes:
    text = open(path).read()
    if "EDGE_SERVICE_PRIVATE_KEY" in text:  # a .dev.vars file
        line = next(l for l in text.splitlines() if l.startswith("EDGE_SERVICE_PRIVATE_KEY"))
        text = line.split("=", 1)[1].strip().strip('"').replace("\\n", "\n")
    return text.encode()


def _mint(key_file: str, kid: str, claims: dict[str, Any]) -> str:
    from cryptography.hazmat.primitives import serialization

    def b64(o: dict) -> bytes:
        return base64.urlsafe_b64encode(json.dumps(o, separators=(",", ":")).encode()).rstrip(b"=")

    now = int(time.time())
    signing_input = b64({"alg": "EdDSA", "kid": kid}) + b"." + b64({**claims, "iat": now, "exp": now + 600})
    key = serialization.load_pem_private_key(_pem(key_file), password=None)
    return (signing_input + b"." + base64.urlsafe_b64encode(key.sign(signing_input)).rstrip(b"=")).decode()


def user_id(owner_wallet: str) -> str:
    return f"bit-{owner_wallet}"


def _account(method: str, path: str, uid: str, body: Any = None) -> Any:
    token = _mint(BFF_KEY_FILE, "aomi-bff-dev-1", {"sub": uid, "iss": "aomi-bff", "aud": "aomi-backend", "role": "user",
                                                    "auth_source": "session", "principal_class": "user"})
    r = requests.request(method, BACKEND + path, json=body, timeout=90,
                         headers={"authorization": f"Bearer {token}", "content-type": "application/json"})
    if not r.ok:
        raise HTTPException(502, f"Aomi {method} {path} returned {r.status_code}: {r.text[:300]}")
    return r.json()


def _agent(method: str, path: str, uid: str, body: Any = None, idem: bool = False) -> Any:
    token = _mint(EDGE_KEY_FILE, "aomi-edge-dev-1", {
        "sub": uid, "iss": "aomi-edge", "aud": "aomi-api-server", "role": "user",
        "scope": "agent:read agent:write agent:actions:resolve", "resource": "https://aomi.chat/v1/agent",
        "auth_source": "session", "principal_class": "user"})
    headers = {"authorization": f"Bearer {token}", "content-type": "application/json"}
    if idem:
        headers["idempotency-key"] = uuid.uuid4().hex
    r = requests.request(method, API + path, json=body, timeout=90, headers=headers)
    if not r.ok:
        raise HTTPException(502, f"Aomi {method} {path.split('?')[0]} returned {r.status_code}: {r.text[:300]}")
    return r.json()


def _db(sql: str, args: tuple) -> Optional[tuple]:
    with psycopg2.connect(DEV_DB) as conn, conn.cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchone() if cur.description else None


def application_id(app_name: str) -> Optional[int]:
    row = _db("SELECT id FROM applications WHERE name = %s ORDER BY id DESC LIMIT 1", (app_name,))
    return int(row[0]) if row else None


def _find_wallet(uid: str, app_name: str) -> Optional[dict[str, Any]]:
    for w in _account("GET", "/v1/account/agent-wallets", uid)["wallets"]:
        if w["name"] == WALLET_PREFIX + app_name and not w.get("archived_at"):
            return w
    return None


def state(owner_wallet: str, app_name: str) -> dict[str, Any]:
    """The owner's Aomi agent wallet for this agent, if any, and whether the app is loaded."""
    reason = configured()
    if reason:
        return {"connected": False, "reason": reason}
    app_id = application_id(app_name)
    if app_id is None:
        return {"connected": False, "app": app_name,
                "reason": f"The Aomi backend has not loaded {app_name}. Compile the agent first."}
    uid = user_id(owner_wallet)
    if not _db("SELECT 1 FROM users WHERE id = %s", (uid,)):
        return {"connected": True, "app": app_name, "application_id": app_id, "wallet": None, "lane": None}
    w = _find_wallet(uid, app_name)
    if not w:
        return {"connected": True, "app": app_name, "application_id": app_id, "wallet": None, "lane": None}
    svm = next(a for a in w["addresses"] if a["family"] == "svm")
    lane = next((c["lane"] for c in w["connections"] if c["key"] == "portal"), None)
    return {"connected": True, "app": app_name, "application_id": app_id, "lane": lane, "paused": w["paused"],
            "wallet": {"address": svm["address"], "wallet_ref": svm["wallet_id"], "id": w["id"], "custody": "Para (Aomi agent wallet)"}}


def create_wallet(owner_wallet: str, app_name: str) -> dict[str, Any]:
    """Create the owner's agent wallet for this agent and let it sign without a click."""
    _require()
    uid = user_id(owner_wallet)
    _db("INSERT INTO users (id, username) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING", (uid, uid))
    if not _find_wallet(uid, app_name):
        _account("POST", "/v1/account/agent-wallets", uid, {"name": WALLET_PREFIX + app_name, "families": ["svm"]})
    mine = [w for w in _account("GET", "/v1/account/agent-wallets", uid)["wallets"]
            if w["name"].startswith(WALLET_PREFIX) and not w.get("archived_at")]
    _account("PUT", "/v1/account/connections/portal/wallets", uid,
             {"wallets": [{"id": w["id"], "lane": "instant"} for w in mine]})
    return state(owner_wallet, app_name)


def _compact(text: str) -> str:
    """A tool result for the console. Per-analyst detail is dropped so orders are never cut off."""
    try:
        data = json.loads(text)
    except ValueError:
        return text[:6000]
    if isinstance(data, dict) and isinstance(data.get("signals"), list):
        data["signals"] = [{k: v for k, v in s.items() if k not in ("analysts", "headlines")} if isinstance(s, dict) else s
                           for s in data["signals"]]
        for o in data.get("orders") or []:
            if isinstance(o, dict) and "stage" in o:
                o["stage"] = {"instructions": len(o["stage"].get("instructions") or []), "description": o["stage"].get("description")}
    return json.dumps(data)[:60000]


def _event(e: dict[str, Any]) -> Optional[dict[str, Any]]:
    if e.get("type") != "message" or e.get("sender") != "agent":
        return None
    if e.get("tool_name"):
        result = e.get("tool_result") or ["", ""]
        return {"type": "tool", "tool": e["tool_name"], "summary": result[0],
                "result": _compact(result[1]) if len(result) > 1 and isinstance(result[1], str) else None}
    return None


def chat(owner_wallet: str, app_name: str, message: str, session_id: Optional[str]) -> dict[str, Any]:
    """One turn with the agent's Aomi app, acting as the owner with their agent wallet active."""
    _require()
    st = state(owner_wallet, app_name)
    if not st.get("connected"):
        raise HTTPException(503, st["reason"])
    if not st.get("wallet"):
        raise HTTPException(409, "Create your agent wallet first.")
    uid = user_id(owner_wallet)
    body: dict[str, Any] = {"message": message, "app": app_name, "applicationId": st["application_id"],
                            "wallet": st["wallet"]["wallet_ref"]}
    if session_id:
        body["sessionId"] = session_id
    page = _agent("POST", "/v1/agent/chat", uid, body, idem=True)
    sid, turn = page["session_id"], page["started_turn_id"]
    events: list[dict[str, Any]] = []
    reply, final, commits = "", None, list(page.get("commits") or [])
    cursor, deadline = page.get("cursor"), time.time() + 240
    pending = list(page.get("events") or [])
    while final is None:
        for e in pending:
            if e.get("turn_id") != turn:
                continue
            ev = _event(e)
            if ev:
                events.append(ev)
            elif e.get("type") == "message" and e.get("sender") == "agent" and (e.get("content") or "").strip():
                reply = e["content"]
            elif e.get("type") == "turn_state_changed" and e.get("state") in ("complete", "failed", "interrupted"):
                final = e["state"]
        if final is not None:
            break
        if time.time() > deadline:
            raise HTTPException(504, "The agent did not finish within four minutes.")
        time.sleep(1.5)
        page = _agent("GET", f"/v1/agent/chat/{sid}?cursor={cursor}", uid)
        cursor, pending = page.get("cursor", cursor), list(page.get("events") or [])
        commits += list(page.get("commits") or [])
    return {"session_id": sid, "turn_id": turn, "state": final, "reply": reply, "events": events, "commits": commits}
