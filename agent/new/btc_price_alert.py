"""
MVP proof for the marketplace background-execution experiment.

The whole point: this must work with zero browser tab, zero chat session,
zero anything held in memory between calls -- each invocation independently
fetches the real price, compares to the last recorded baseline, and exits.
Same stateless-cron shape as vercel-multiwallet/api/cron/tick.py, just for a
watch-and-alert agent instead of a scheduled trade.
"""

from __future__ import annotations

import requests

from db import (
    get_btc_price_alert,
    log_btc_price_alert_fire,
    update_btc_price_alert_check,
)

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"


def fetch_btc_price_usd() -> float:
    resp = requests.get(
        COINGECKO_URL, params={"ids": "bitcoin", "vs_currencies": "usd"}, timeout=10
    )
    resp.raise_for_status()
    return float(resp.json()["bitcoin"]["usd"])


def check_btc_price_alert(alert_id: str) -> dict:
    """One tick: fetch price, compare to baseline, alert + reset baseline if
    the threshold's crossed. Call this repeatedly (a cron job, a manual
    invocation, whatever) -- it needs nothing carried over between calls."""
    alert = get_btc_price_alert(alert_id)
    if not alert:
        return {"error": f"No alert with id {alert_id}"}

    price = fetch_btc_price_usd()
    baseline = alert.get("baseline_price_usd")

    if baseline is None:
        # First-ever check: just establish the baseline, nothing to compare yet.
        update_btc_price_alert_check(alert_id, price_usd=price, baseline_price_usd=price)
        return {"status": "baseline_set", "price_usd": price}

    change_pct = ((price - baseline) / baseline) * 100
    threshold = alert["threshold_pct"]

    if abs(change_pct) >= threshold:
        log_btc_price_alert_fire(alert_id, price, change_pct)
        update_btc_price_alert_check(alert_id, price_usd=price, fired=True)
        return {
            "status": "fired",
            "price_usd": price,
            "baseline_was": baseline,
            "change_pct": round(change_pct, 3),
        }

    update_btc_price_alert_check(alert_id, price_usd=price)
    return {
        "status": "no_change",
        "price_usd": price,
        "baseline": baseline,
        "change_pct": round(change_pct, 3),
    }
