"""
Experiment 2: watch an arbitrary product page for a price drop.

Same stateless-tick shape as btc_price_alert.py -- each check independently
fetches the page, extracts a price, compares to a running baseline, and
exits. No API for "the price of this random URL" exists, so this is a
best-effort HTML scraper, not a keyed integration: it tries the structured-
data sources real e-commerce sites already publish (JSON-LD, Open Graph,
itemprop) before falling back to a regex over visible text. A site with
none of these, or one that blocks scraping outright, will genuinely fail --
that failure is surfaced honestly (last_error), never silently ignored.
"""

from __future__ import annotations

import json
import re
import threading
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

from db import (
    get_product_price_watch,
    get_custom_agent,
    list_active_product_price_watches,
    log_product_price_watch_fire,
    update_product_price_watch_check,
)
from notifications import send_notification

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
SCHEDULER_POLL_SECONDS = 300  # page scraping is heavier than a price API -- 5 min default
_scheduler_running = False
_scheduler_lock = threading.Lock()

PRICE_RE = re.compile(r"[$£€]\s?(\d{1,3}(?:[,.\s]\d{3})*(?:\.\d{2})?)")


def _price_from_jsonld(soup: BeautifulSoup) -> Optional[tuple[float, Optional[str]]]:
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            offers = item.get("offers")
            if isinstance(offers, list):
                offers = offers[0] if offers else None
            if isinstance(offers, dict) and offers.get("price"):
                try:
                    return float(str(offers["price"]).replace(",", "")), offers.get("priceCurrency")
                except ValueError:
                    continue
    return None


def _price_from_meta(soup: BeautifulSoup) -> Optional[tuple[float, Optional[str]]]:
    for prop in ("product:price:amount", "og:price:amount"):
        tag = soup.find("meta", property=prop)
        if tag and tag.get("content"):
            try:
                price = float(str(tag["content"]).replace(",", ""))
                currency_tag = soup.find("meta", property=prop.replace("amount", "currency"))
                return price, (currency_tag["content"] if currency_tag else None)
            except ValueError:
                continue
    return None


def _price_from_itemprop(soup: BeautifulSoup) -> Optional[tuple[float, Optional[str]]]:
    tag = soup.find(attrs={"itemprop": "price"})
    if tag:
        raw = tag.get("content") or tag.get_text()
        match = re.search(r"[\d,.]+", raw or "")
        if match:
            try:
                return float(match.group(0).replace(",", "")), None
            except ValueError:
                pass
    return None


def _price_from_text_regex(soup: BeautifulSoup) -> Optional[tuple[float, Optional[str]]]:
    match = PRICE_RE.search(soup.get_text(" ", strip=True))
    if match:
        try:
            return float(match.group(1).replace(",", "")), None
        except ValueError:
            pass
    return None


def fetch_product_price(url: str) -> tuple[float, Optional[str]]:
    """Returns (price, currency). Raises ValueError with a human-readable
    reason if no price could be found -- callers surface this directly,
    never invent a fallback price."""
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for extractor in (_price_from_jsonld, _price_from_meta, _price_from_itemprop, _price_from_text_regex):
        result = extractor(soup)
        if result:
            return result
    raise ValueError("Could not find a price on this page (no structured data or recognizable price text).")


def _notify_agent_creator(watch: dict, price: float, change_pct: float, currency: Optional[str]) -> dict:
    agent_id = watch.get("agent_id")
    if not agent_id:
        return {"ok": False, "error": "watch has no linked agent -- nothing to notify"}
    agent = get_custom_agent(agent_id)
    if not agent or not agent.get("notify_channel") or not agent.get("notify_destination"):
        return {"ok": False, "error": "linked agent has no verified notification channel"}
    if not agent.get("notify_verified_at"):
        return {"ok": False, "error": "notification destination was never confirmed by the user"}
    label = watch.get("product_label") or "your watched item"
    ccy = currency or "$"
    subject = f"{agent.get('name') or 'Your BITAGENTS agent'}: price drop on {label}"
    body = (
        f"{label} dropped {abs(change_pct):.1f}% -- now {ccy}{price:,.2f}.\n{watch['url']}\n\n"
        f"-- {agent.get('name') or 'BITAGENTS'}"
    )
    return send_notification(agent["notify_channel"], agent["notify_destination"], subject, body)


def check_product_price_watch(watch_id: str) -> dict:
    watch = get_product_price_watch(watch_id)
    if not watch:
        return {"error": f"No watch with id {watch_id}"}

    try:
        price, currency = fetch_product_price(watch["url"])
    except Exception as exc:
        update_product_price_watch_check(watch_id, error=str(exc))
        return {"status": "error", "error": str(exc)}

    baseline = watch.get("baseline_price")
    if baseline is None:
        update_product_price_watch_check(watch_id, price=price, new_baseline=price, error=None)
        return {"status": "baseline_set", "price": price}

    change_pct = ((price - baseline) / baseline) * 100
    threshold = watch["threshold_pct"]

    if change_pct <= -threshold:
        log_product_price_watch_fire(watch_id, price, change_pct)
        update_product_price_watch_check(watch_id, price=price, new_baseline=price, fired=True, error=None)
        notify_result = _notify_agent_creator(watch, price, change_pct, currency)
        return {
            "status": "fired", "price": price, "baseline_was": baseline,
            "change_pct": round(change_pct, 2), "notification": notify_result,
        }

    update_product_price_watch_check(watch_id, price=price, error=None)
    return {"status": "no_change", "price": price, "baseline": baseline, "change_pct": round(change_pct, 2)}


def _scheduler_loop(poll_seconds: int = SCHEDULER_POLL_SECONDS) -> None:
    global _scheduler_running
    while _scheduler_running:
        try:
            watch_ids = list_active_product_price_watches()
            for watch_id in watch_ids:
                try:
                    result = check_product_price_watch(watch_id)
                    if result.get("status") == "fired":
                        print(f"  🟢 Product price drop {watch_id}: {result['change_pct']:+.1f}% -> {result['price']}")
                    elif result.get("status") == "error":
                        print(f"  ⚠️  Product watch {watch_id} error: {result['error']}")
                except Exception as exc:
                    print(f"  ⚠️  Product watch {watch_id} check failed: {exc}")
        except Exception as exc:
            print(f"  ⚠️  Product price scheduler error: {exc}")
        time.sleep(poll_seconds)


def start_scheduler() -> bool:
    global _scheduler_running
    with _scheduler_lock:
        if _scheduler_running:
            return False
        _scheduler_running = True
        t = threading.Thread(target=_scheduler_loop, daemon=True, name="product-price-scheduler")
        t.start()
        return True


def stop_scheduler() -> None:
    global _scheduler_running
    _scheduler_running = False
