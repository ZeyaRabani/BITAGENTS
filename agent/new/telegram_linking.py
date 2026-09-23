"""
One-click Telegram connect: the user never types a chat ID or a token.

Flow: the builder generates a short code (create_telegram_link_code), hands
the user a t.me deep link containing it. They tap the link, Telegram opens
the bot, they press Start -- Telegram sends the bot a "/start <code>"
message. This module's background poller reads that via getUpdates and
writes the resulting chat_id against the code (claim_telegram_link_code).
The builder then just polls get_telegram_link_code(code) until chat_id
shows up. No webhook/public URL needed for local dev -- long polling works
anywhere the backend can reach api.telegram.org.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Optional

import requests

from db import claim_telegram_link_code

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
POLL_SECONDS = int(os.environ.get("TELEGRAM_LINK_POLL_SECONDS", "2"))

_running = False
_lock = threading.Lock()
_bot_username: Optional[str] = None


def get_bot_username() -> Optional[str]:
    """Cached lookup of the bot's own @username, needed to build t.me links."""
    global _bot_username
    if _bot_username or not TELEGRAM_BOT_TOKEN:
        return _bot_username
    try:
        resp = requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe", timeout=10)
        data = resp.json()
        if data.get("ok"):
            _bot_username = data["result"]["username"]
    except requests.RequestException:
        pass
    return _bot_username


def build_deep_link(code: str) -> Optional[str]:
    username = get_bot_username()
    if not username:
        return None
    return f"https://t.me/{username}?start={code}"


def _poll_loop(poll_seconds: int = POLL_SECONDS) -> None:
    global _running
    offset = 0
    while _running:
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
                params={"offset": offset, "timeout": 10, "allowed_updates": '["message"]'},
                timeout=15,
            )
            data = resp.json()
            if data.get("ok"):
                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    message = update.get("message") or {}
                    text = (message.get("text") or "").strip()
                    chat_id = message.get("chat", {}).get("id")
                    if text.startswith("/start ") and chat_id:
                        code = text.split(" ", 1)[1].strip()
                        if claim_telegram_link_code(code, str(chat_id)):
                            print(f"  ✅ Telegram linked: code {code} -> chat {chat_id}")
        except Exception as exc:
            print(f"  ⚠️  Telegram link poller error: {exc}")
        time.sleep(poll_seconds)


def start_poller() -> bool:
    global _running
    if not TELEGRAM_BOT_TOKEN:
        return False
    with _lock:
        if _running:
            return False
        _running = True
        t = threading.Thread(target=_poll_loop, daemon=True, name="telegram-link-poller")
        t.start()
        return True


def stop_poller() -> None:
    global _running
    _running = False
