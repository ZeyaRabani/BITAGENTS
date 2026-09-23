"""
Background-execution proof, now wired to real user-facing delivery.

The whole point: this must work with zero browser tab, zero chat session,
zero anything held in memory between calls -- each invocation independently
fetches the real price, compares to the last recorded baseline, and exits.
Same stateless-cron shape as vercel-multiwallet/api/cron/tick.py, just for a
watch-and-alert agent instead of a scheduled trade.

"Moves X% in one hour" is a rolling window, not "since the last check" --
the baseline resets every `window_hours` regardless of whether it fired, so
a check run every few minutes still measures an hourly move, not a
since-the-dawn-of-time one.
"""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

from db import (
    get_btc_price_alert,
    get_custom_agent,
    list_active_btc_price_alerts,
    log_btc_price_alert_fire,
    update_btc_price_alert_check,
)
from notifications import send_notification

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"

# One shared poll serves every user's alert -- this is the cost lever, not
# the notifications themselves (see the setup-cost discussion). A single
# CoinGecko call + DB pass covers however many agents are watching BTC.
SCHEDULER_POLL_SECONDS = int(os.environ.get("BTC_ALERT_SCHEDULER_POLL_SECONDS", "60"))
_scheduler_running = False
_scheduler_lock = threading.Lock()


def fetch_btc_price_usd() -> float:
    resp = requests.get(
        COINGECKO_URL, params={"ids": "bitcoin", "vs_currencies": "usd"}, timeout=10
    )
    resp.raise_for_status()
    return float(resp.json()["bitcoin"]["usd"])


def _window_expired(alert: dict) -> bool:
    started = alert.get("window_started_at")
    if not started:
        return True
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    hours = alert.get("window_hours") or 1.0
    return datetime.now(timezone.utc) - started >= timedelta(hours=hours)


def _notify_agent_creator(alert: dict, price: float, change_pct: float) -> dict:
    agent_id = alert.get("agent_id")
    if not agent_id:
        return {"ok": False, "error": "alert has no linked agent -- nothing to notify"}
    agent = get_custom_agent(agent_id)
    if not agent or not agent.get("notify_channel") or not agent.get("notify_destination"):
        return {"ok": False, "error": "linked agent has no verified notification channel"}
    if not agent.get("notify_verified_at"):
        return {"ok": False, "error": "notification destination was never confirmed by the user"}
    direction = "up" if change_pct > 0 else "down"
    subject = f"{agent.get('name') or 'Your BITAGENTS agent'}: BTC moved {abs(change_pct):.2f}%"
    body = (
        f"BTC is {direction} {abs(change_pct):.2f}% in the last hour, now ${price:,.2f}.\n\n"
        f"-- {agent.get('name') or 'BITAGENTS'}"
    )
    return send_notification(agent["notify_channel"], agent["notify_destination"], subject, body)


def check_btc_price_alert(alert_id: str, price: Optional[float] = None) -> dict:
    """One tick: fetch price, compare to the rolling-window baseline, alert +
    reset the window if the threshold's crossed or the window's expired.
    Call this repeatedly (a cron job, a manual invocation, whatever) -- it
    needs nothing carried over between calls.

    Pass `price` when the caller already fetched it this tick (the
    scheduler checking N alerts) -- otherwise every alert re-fetches
    independently, which is what was actually rate-limiting us against
    CoinGecko's free tier, not real usage volume."""
    alert = get_btc_price_alert(alert_id)
    if not alert:
        return {"error": f"No alert with id {alert_id}"}

    if price is None:
        price = fetch_btc_price_usd()
    baseline = alert.get("baseline_price_usd")

    if baseline is None or _window_expired(alert):
        # First-ever check, or the rolling window rolled over: reset the
        # baseline to now, nothing to compare against yet this window.
        update_btc_price_alert_check(
            alert_id, price_usd=price, baseline_price_usd=price, reset_window=True
        )
        return {"status": "baseline_set", "price_usd": price}

    change_pct = ((price - baseline) / baseline) * 100
    threshold = alert["threshold_pct"]

    if abs(change_pct) >= threshold:
        log_btc_price_alert_fire(alert_id, price, change_pct)
        update_btc_price_alert_check(alert_id, price_usd=price, fired=True)
        notify_result = _notify_agent_creator(alert, price, change_pct)
        return {
            "status": "fired",
            "price_usd": price,
            "baseline_was": baseline,
            "change_pct": round(change_pct, 3),
            "notification": notify_result,
        }

    update_btc_price_alert_check(alert_id, price_usd=price)
    return {
        "status": "no_change",
        "price_usd": price,
        "baseline": baseline,
        "change_pct": round(change_pct, 3),
    }


# ─── Scheduler ────────────────────────────────────────────────────────────────
# Same shape as dca_agent.py's _scheduler_loop: a daemon thread, one shared
# poll per tick covering every active alert, nothing held between ticks.

def _scheduler_loop(poll_seconds: int = SCHEDULER_POLL_SECONDS) -> None:
    global _scheduler_running
    while _scheduler_running:
        try:
            alert_ids = list_active_btc_price_alerts()
            if alert_ids:
                price = None
                try:
                    price = fetch_btc_price_usd()
                except Exception as exc:
                    print(f"  ⚠️  BTC alert scheduler: price fetch failed: {exc}")
                if price is not None:
                    print(f"  🟠 BTC alert tick: ${price:,.2f} · {len(alert_ids)} active watch(es)")
                    for alert_id in alert_ids:
                        try:
                            result = check_btc_price_alert(alert_id, price=price)
                            if result.get("status") == "fired":
                                notif = result.get("notification") or {}
                                mark = "✅" if notif.get("ok") else "⚠️"
                                print(
                                    f"    {mark} {alert_id}: {result['change_pct']:+.2f}% "
                                    f"→ ${result['price_usd']:,.2f} (notify: {notif})"
                                )
                        except Exception as exc:
                            print(f"  ⚠️  BTC alert {alert_id} check failed: {exc}")
        except Exception as exc:
            print(f"  ⚠️  BTC alert scheduler error: {exc}")
        time.sleep(poll_seconds)


def start_scheduler() -> bool:
    global _scheduler_running
    with _scheduler_lock:
        if _scheduler_running:
            return False
        _scheduler_running = True
        t = threading.Thread(target=_scheduler_loop, daemon=True, name="btc-alert-scheduler")
        t.start()
        return True


def stop_scheduler() -> None:
    global _scheduler_running
    _scheduler_running = False
