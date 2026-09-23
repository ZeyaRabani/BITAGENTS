"""
Experiment 3: a true recurring digest, independent of any trigger condition.

This is the genuinely new piece -- experiments 1 and 2 both reuse the
"check on a tick, compare to a baseline, maybe fire" shape. A daily digest
has no baseline to compare against; it just needs to fire once, at roughly
the right hour, every day, whether or not anything "changed". Content
source is Google News' public RSS search (no key, no cost) -- headlines
only for this MVP, not an LLM-summarized digest, to keep this cheap to run
at any frequency/scale.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from xml.etree import ElementTree

import requests

from db import (
    get_custom_agent,
    get_digest_watch,
    list_active_digest_watches,
    update_digest_watch_sent,
)
from notifications import send_notification

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
SCHEDULER_POLL_SECONDS = 900  # 15 min -- fine-grained enough to hit an hourly slot without hammering the feed
MAX_HEADLINES = 6


def fetch_topic_headlines(topic: str, limit: int = MAX_HEADLINES) -> list[str]:
    resp = requests.get(
        GOOGLE_NEWS_RSS,
        params={"q": topic, "hl": "en-US", "gl": "US", "ceid": "US:en"},
        timeout=15,
    )
    resp.raise_for_status()
    root = ElementTree.fromstring(resp.text)
    titles = [item.findtext("title") for item in root.findall(".//item")]
    return [t for t in titles if t][:limit]


def _already_sent_today(watch: dict) -> bool:
    last = watch.get("last_sent_at")
    if not last:
        return False
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return last.date() == now.date()


def _is_due(watch: dict) -> bool:
    if _already_sent_today(watch):
        return False
    return datetime.now(timezone.utc).hour >= (watch.get("schedule_hour") or 8)


def _notify_agent_creator(watch: dict, headlines: list[str]) -> dict:
    agent_id = watch.get("agent_id")
    if not agent_id:
        return {"ok": False, "error": "watch has no linked agent"}
    agent = get_custom_agent(agent_id)
    if not agent or not agent.get("notify_channel") or not agent.get("notify_destination"):
        return {"ok": False, "error": "linked agent has no verified notification channel"}
    if not agent.get("notify_verified_at"):
        return {"ok": False, "error": "notification destination was never confirmed by the user"}
    topic = watch.get("topic", "your topic")
    subject = f"{agent.get('name') or 'Your BITAGENTS agent'}: daily digest on {topic}"
    if headlines:
        body = f"Today's headlines on \"{topic}\":\n\n" + "\n".join(f"- {h}" for h in headlines)
    else:
        body = f"No new headlines found for \"{topic}\" today."
    body += f"\n\n-- {agent.get('name') or 'BITAGENTS'}"
    return send_notification(agent["notify_channel"], agent["notify_destination"], subject, body)


def check_digest_watch(watch_id: str, *, force: bool = False) -> dict:
    """One tick: if it's this watch's hour and it hasn't sent today (or
    `force`, for manual testing), fetch real headlines and send. Stateless
    like the other two checkers -- nothing carried over between calls."""
    watch = get_digest_watch(watch_id)
    if not watch:
        return {"error": f"No digest watch with id {watch_id}"}

    if not force and not _is_due(watch):
        return {"status": "not_due"}

    try:
        headlines = fetch_topic_headlines(watch["topic"])
    except Exception as exc:
        update_digest_watch_sent(watch_id, error=str(exc))
        return {"status": "error", "error": str(exc)}

    notify_result = _notify_agent_creator(watch, headlines)
    update_digest_watch_sent(watch_id, sent=True, error=None if notify_result.get("ok") else str(notify_result.get("error")))
    return {"status": "sent", "headlines": headlines, "notification": notify_result}


_scheduler_running = False
_scheduler_lock = threading.Lock()


def _scheduler_loop(poll_seconds: int = SCHEDULER_POLL_SECONDS) -> None:
    global _scheduler_running
    while _scheduler_running:
        try:
            for watch_id in list_active_digest_watches():
                try:
                    result = check_digest_watch(watch_id)
                    if result.get("status") == "sent":
                        print(f"  📰 Digest sent {watch_id}: {len(result.get('headlines', []))} headlines")
                    elif result.get("status") == "error":
                        print(f"  ⚠️  Digest {watch_id} error: {result['error']}")
                except Exception as exc:
                    print(f"  ⚠️  Digest {watch_id} check failed: {exc}")
        except Exception as exc:
            print(f"  ⚠️  Digest scheduler error: {exc}")
        time.sleep(poll_seconds)


def start_scheduler() -> bool:
    global _scheduler_running
    with _scheduler_lock:
        if _scheduler_running:
            return False
        _scheduler_running = True
        t = threading.Thread(target=_scheduler_loop, daemon=True, name="digest-scheduler")
        t.start()
        return True


def stop_scheduler() -> None:
    global _scheduler_running
    _scheduler_running = False
