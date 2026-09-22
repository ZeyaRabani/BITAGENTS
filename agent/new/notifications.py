"""
Zero-setup notification channels: email and Telegram.

The user never enters a credential -- they only confirm ownership of a
destination (an email address, a Telegram chat) during the launch
conversation, via a real test-send. The one real secret per channel
(RESEND_API_KEY, TELEGRAM_BOT_TOKEN) lives only here, read from the backend's
own .env, and never reaches agent code, the database, or the frontend.

An agent can only ever send to the destination its own creator verified --
enforced by callers always passing the agent's stored notify_destination,
never a value the agent composes itself.
"""

from __future__ import annotations

import os
from typing import Any

import requests

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
RESEND_FROM = os.environ.get("RESEND_FROM", "BITAGENTS <alerts@bitagents.app>").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()

VALID_CHANNELS = ("email", "telegram")


def send_email(to: str, subject: str, body: str) -> dict[str, Any]:
    if not RESEND_API_KEY:
        return {
            "ok": False,
            "error": "RESEND_API_KEY is not configured on the backend. "
                     "Get a free key at resend.com and set it in agent/new/.env.",
        }
    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            json={"from": RESEND_FROM, "to": [to], "subject": subject, "text": body},
            timeout=10,
        )
        if resp.status_code >= 300:
            return {"ok": False, "error": f"Resend API error {resp.status_code}: {resp.text[:300]}"}
        return {"ok": True, "id": resp.json().get("id")}
    except requests.RequestException as exc:
        return {"ok": False, "error": str(exc)}


def send_telegram(chat_id: str, text: str) -> dict[str, Any]:
    if not TELEGRAM_BOT_TOKEN:
        return {
            "ok": False,
            "error": "TELEGRAM_BOT_TOKEN is not configured on the backend. "
                     "Create a free bot via @BotFather and set it in agent/new/.env.",
        }
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
        data = resp.json()
        if not data.get("ok"):
            return {"ok": False, "error": data.get("description", "Telegram API error")}
        return {"ok": True, "id": data.get("result", {}).get("message_id")}
    except requests.RequestException as exc:
        return {"ok": False, "error": str(exc)}


def send_notification(channel: str, destination: str, subject: str, body: str) -> dict[str, Any]:
    """Dispatch to the right channel. `destination` must always come from the
    agent's own stored notify_destination -- never a value composed live by
    the agent -- this is the destination-pinning control from the setup plan."""
    if channel == "email":
        return send_email(destination, subject, body)
    if channel == "telegram":
        return send_telegram(destination, body)
    return {"ok": False, "error": f"Unknown notification channel: {channel}"}
