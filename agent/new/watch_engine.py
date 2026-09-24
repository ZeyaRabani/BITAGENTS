"""
Generic watch engine -- the shared infrastructure behind all three
experiments (BTC alerts, product price drops, news digests).

Each experiment used to be a fully separate stack: own table, own
scheduler thread, own check function. That made every NEW trigger type a
full day-sized build. This collapses them into one shared shape:

    source  -> fetches a value/content for a watch
    condition -> decides, from that value + the watch's stored state,
                 whether to fire, and how to update the baseline
    (notification is already generic -- see notifications.py, unchanged)

Adding a new capability is "write one source function + maybe one
condition function", not a new table/scheduler/tool. See btc_price_alert.py
and product_price_watch.py for the underlying fetchers this reuses --
they're kept as the actual fetch implementations; this file only adds the
generic registry + scheduling layer on top.

Builder-facing tools (create_price_watch etc. in agent_builder.py) stay
concrete and specific -- see the top of that file for why: a fully
generic "create_watch(source_type, condition_type, config_json)" tool
would ask the model to compose structured config correctly every time,
which is a worse failure surface than a few specific, well-typed tools
calling into this same shared engine underneath.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from btc_price_alert import fetch_btc_price_usd
from product_price_watch import fetch_product_price
from digest_watch import fetch_topic_headlines
from db import (
    get_custom_agent,
    get_watch,
    list_due_watches,
    log_watch_fire,
    update_watch_check,
)
from notifications import send_notification

# ─── Source registry: source_type -> fetch(config) -> (value, content) ────
# `value` is a comparable number (price); `content` is a list of strings
# for content-type sources (news). Exactly one of the two is meaningful
# per source type -- the condition function knows which it needs.

SourceFn = Callable[[dict[str, Any]], tuple[Optional[float], Optional[list[str]], Optional[str]]]


def _source_btc_price(_config: dict[str, Any]) -> tuple[Optional[float], Optional[list[str]], Optional[str]]:
    return fetch_btc_price_usd(), None, None


def _source_product_price(config: dict[str, Any]) -> tuple[Optional[float], Optional[list[str]], Optional[str]]:
    price, currency = fetch_product_price(config["url"])
    return price, None, currency


def _source_news(config: dict[str, Any]) -> tuple[Optional[float], Optional[list[str]], Optional[str]]:
    return None, fetch_topic_headlines(config["topic"]), None


SOURCES: dict[str, SourceFn] = {
    "btc_price": _source_btc_price,
    "product_price": _source_product_price,
    "news": _source_news,
}


# ─── Condition registry: decides fire/no-fire + how to update state ───────
# Each returns a dict describing what happened; the engine applies it.

def _condition_percent_move(watch: dict, value: float, config: dict) -> dict:
    """Rolling window (BTC-style): fires on X% move either direction within
    window_hours, baseline resets every window regardless of firing."""
    threshold = config.get("threshold_pct", 1.0)
    window_hours = config.get("window_hours", 1.0)
    baseline = watch.get("baseline_value")
    started = watch.get("window_started_at")
    expired = True
    if started:
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        expired = datetime.now(timezone.utc) - started >= timedelta(hours=window_hours)

    if baseline is None or expired:
        return {"fired": False, "reset_window": True, "new_baseline": value, "change_pct": 0.0}

    change_pct = ((value - baseline) / baseline) * 100
    if abs(change_pct) >= threshold:
        return {"fired": True, "reset_window": True, "new_baseline": value, "change_pct": change_pct}
    return {"fired": False, "reset_window": False, "new_baseline": None, "change_pct": change_pct}


def _condition_percent_drop(watch: dict, value: float, config: dict) -> dict:
    """Drop-only (product-watch style): baseline is the last-seen price,
    resets down each time it fires so further drops keep being caught."""
    threshold = config.get("threshold_pct", 5.0)
    baseline = watch.get("baseline_value")
    if baseline is None:
        return {"fired": False, "reset_window": False, "new_baseline": value, "change_pct": 0.0}
    change_pct = ((value - baseline) / baseline) * 100
    if change_pct <= -threshold:
        return {"fired": True, "reset_window": False, "new_baseline": value, "change_pct": change_pct}
    return {"fired": False, "reset_window": False, "new_baseline": None, "change_pct": change_pct}


def _condition_daily_fire(watch: dict, _value: Any, config: dict) -> dict:
    """Digest-style: no comparison, just "is it this hour and not sent
    today". `_force` (set by check_watch when called with force=True, e.g.
    manual testing) bypasses the hour/already-sent-today check entirely."""
    if config.get("_force"):
        return {"fired": True, "reset_window": False, "new_baseline": None, "change_pct": None}
    hour = config.get("schedule_hour", 8)
    last_alert = watch.get("last_alert_at")
    if last_alert:
        if last_alert.tzinfo is None:
            last_alert = last_alert.replace(tzinfo=timezone.utc)
        if last_alert.date() == datetime.now(timezone.utc).date():
            return {"fired": False, "reset_window": False, "new_baseline": None, "change_pct": None}
    due = datetime.now(timezone.utc).hour >= hour
    return {"fired": due, "reset_window": False, "new_baseline": None, "change_pct": None}


CONDITIONS: dict[str, Callable[[dict, Any, dict], dict]] = {
    "percent_move": _condition_percent_move,
    "percent_drop": _condition_percent_drop,
    "daily_fire": _condition_daily_fire,
}


def _notify_agent_creator(watch: dict, value: Optional[float], content: Optional[list[str]], change_pct: Optional[float], currency: Optional[str]) -> dict:
    agent_id = watch.get("agent_id")
    if not agent_id:
        return {"ok": False, "error": "watch has no linked agent"}
    agent = get_custom_agent(agent_id)
    if not agent or not agent.get("notify_channel") or not agent.get("notify_destination"):
        return {"ok": False, "error": "linked agent has no verified notification channel"}
    if not agent.get("notify_verified_at"):
        return {"ok": False, "error": "notification destination was never confirmed by the user"}

    name = agent.get("name") or "Your BITAGENTS agent"
    if content is not None:
        subject = f"{name}: daily digest"
        body = "\n".join(f"- {h}" for h in content) if content else "No new items found today."
    else:
        ccy = currency or "$"
        direction = "up" if (change_pct or 0) > 0 else "down"
        subject = f"{name}: moved {abs(change_pct or 0):.2f}%"
        body = f"Now {direction} {abs(change_pct or 0):.2f}% -- {ccy}{value:,.2f}" if value is not None else subject
    body += f"\n\n-- {name}"
    return send_notification(agent["notify_channel"], agent["notify_destination"], subject, body)


def check_watch(watch_id: str, *, force: bool = False) -> dict:
    """One tick for any watch, regardless of type -- fetches via the
    registered source, evaluates via the registered condition, notifies if
    fired. Stateless like all three original checkers: nothing carried
    between calls, everything read fresh from the DB row."""
    watch = get_watch(watch_id)
    if not watch:
        return {"error": f"No watch with id {watch_id}"}

    source_fn = SOURCES.get(watch["source_type"])
    condition_fn = CONDITIONS.get(watch["condition_type"])
    if not source_fn or not condition_fn:
        return {"error": f"Unknown source_type/condition_type: {watch['source_type']}/{watch['condition_type']}"}

    try:
        value, content, currency = source_fn(watch.get("source_config") or {})
    except Exception as exc:
        update_watch_check(watch_id, error=str(exc))
        return {"status": "error", "error": str(exc)}

    if not force and watch["condition_type"] != "daily_fire" and value is None and content is None:
        update_watch_check(watch_id, error="source returned nothing")
        return {"status": "error", "error": "source returned nothing"}

    condition_config = dict(watch.get("condition_config") or {})
    if force:
        condition_config["_force"] = True
    outcome = condition_fn(watch, value, condition_config)

    if not outcome["fired"]:
        update_watch_check(
            watch_id, value=value, baseline_value=outcome.get("new_baseline"),
            reset_window=outcome.get("reset_window", False), error=None,
        )
        return {"status": "no_change", "value": value, "change_pct": outcome.get("change_pct")}

    log_watch_fire(watch_id, value, outcome.get("change_pct"))
    update_watch_check(
        watch_id, value=value, baseline_value=outcome.get("new_baseline"),
        reset_window=outcome.get("reset_window", False), fired=True, error=None,
    )
    notify_result = _notify_agent_creator(watch, value, content, outcome.get("change_pct"), currency)
    return {
        "status": "fired", "value": value, "content": content,
        "change_pct": outcome.get("change_pct"), "notification": notify_result,
    }


# ─── Scheduler: one loop, respects each watch's own poll_interval_seconds ──

_scheduler_running = False
_scheduler_lock = threading.Lock()
SCHEDULER_TICK_SECONDS = 30  # granularity of the shared loop, not any watch's own cadence


def _scheduler_loop(tick_seconds: int = SCHEDULER_TICK_SECONDS) -> None:
    global _scheduler_running
    while _scheduler_running:
        try:
            for watch in list_due_watches():
                try:
                    result = check_watch(watch["id"])
                    if result.get("status") == "fired":
                        print(f"  ⚡ Watch fired {watch['id']} ({watch['source_type']}): {result.get('change_pct')}")
                    elif result.get("status") == "error":
                        print(f"  ⚠️  Watch {watch['id']} error: {result['error']}")
                except Exception as exc:
                    print(f"  ⚠️  Watch {watch['id']} check failed: {exc}")
        except Exception as exc:
            print(f"  ⚠️  Watch engine scheduler error: {exc}")
        time.sleep(tick_seconds)


def start_scheduler() -> bool:
    global _scheduler_running
    with _scheduler_lock:
        if _scheduler_running:
            return False
        _scheduler_running = True
        t = threading.Thread(target=_scheduler_loop, daemon=True, name="watch-engine-scheduler")
        t.start()
        return True


def stop_scheduler() -> None:
    global _scheduler_running
    _scheduler_running = False
