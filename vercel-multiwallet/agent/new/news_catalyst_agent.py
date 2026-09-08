"""
News & Catalyst AI Agent using Ollama + Tool Calling
Monitors: Exchange listings, partnerships, fundraises,
governance proposals, major unlocks.
Produces actionable summaries.
"""

import json
import re
import requests
from datetime import datetime, timezone, timedelta
from typing import Any

# ─── Configuration ────────────────────────────────────────────────────────────
OLLAMA_URL    = "http://localhost:11434/api/chat"
MODEL         = "llama3.1"

# Free public APIs - no keys required unless noted
COINGECKO_API   = "https://api.coingecko.com/api/v3"
CRYPTOPANIC_API = "https://cryptopanic.com/api/v1/posts/"
CRYPTOPANIC_KEY = "free"          # works for public feed; get a real key at cryptopanic.com/developers/api/
LUNARCRUSH_API  = "https://lunarcrush.com/api4/public"
DEFILLAMA_API   = "https://api.llama.fi"

# RSS / Atom feeds (parsed without a key)
NEWS_FEEDS = {
    "cointelegraph": "https://cointelegraph.com/rss",
    "decrypt":       "https://decrypt.co/feed",
    "theblock":      "https://www.theblock.co/rss.xml",
    "coindesk":      "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "blockworks":    "https://blockworks.co/feed",
}

# Catalyst signal keywords used for classification
CATALYST_KEYWORDS = {
    "listing":      ["listed", "listing", "now available", "trading on", "launches on",
                     "added to", "coinbase", "binance", "kraken", "bybit", "okx", "kucoin"],
    "partnership":  ["partner", "partnership", "collaboration", "integrat", "team up",
                     "join forces", "alliance", "agreement", "deal"],
    "fundraise":    ["raise", "raised", "funding", "round", "investment", "seed",
                     "series a", "series b", "venture", "backed by", "valuation", "million"],
    "unlock":       ["unlock", "vesting", "cliff", "release", "token release",
                     "circulating supply", "linear vesting"],
    "governance":   ["governance", "proposal", "vote", "dao", "snapshot", "on-chain vote",
                     "community vote", "gip", "aip", "uip", "cip"],
    "hack_exploit": ["hack", "exploit", "vulnerability", "breach", "drained",
                     "attack", "stolen", "compromised", "reentrancy"],
    "upgrade":      ["upgrade", "v2", "v3", "migration", "mainnet launch", "deploy",
                     "protocol upgrade", "hardfork", "hard fork"],
    "regulatory":   ["sec", "cftc", "regulation", "lawsuit", "legal", "ban", "approve",
                     "etf", "court", "compliance", "congress", "senate"],
}

BULLISH_CATALYSTS  = {"listing", "partnership", "fundraise", "upgrade"}
BEARISH_CATALYSTS  = {"hack_exploit", "regulatory", "unlock"}
NEUTRAL_CATALYSTS  = {"governance"}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def classify_catalyst(text: str) -> list[str]:
    """Return matching catalyst categories for a text snippet."""
    text_lower = text.lower()
    found = []
    for cat, kws in CATALYST_KEYWORDS.items():
        if any(kw in text_lower for kw in kws):
            found.append(cat)
    return found or ["general"]


def sentiment_emoji(cats: list[str]) -> str:
    if any(c in BEARISH_CATALYSTS for c in cats):
        return "🔴"
    if any(c in BULLISH_CATALYSTS for c in cats):
        return "🟢"
    return "🟡"


def days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%dT%H:%M:%SZ")


# ─── Tool Functions ────────────────────────────────────────────────────────────

def get_crypto_news_feed(filter_type: str = "all", limit: int = 20) -> dict:
    """
    Fetch latest crypto news from CryptoPanic's public API.
    Classifies each item by catalyst type and sentiment.

    filter_type options:
      'all'         – everything
      'rising'      – trending / rising stories
      'hot'         – hot stories
      'bullish'     – community-tagged bullish
      'bearish'     – community-tagged bearish
      'important'   – high-importance posts
    """
    try:
        params = {
            "auth_token": CRYPTOPANIC_KEY,
            "public": "true",
            "kind": "news",
            "filter": filter_type if filter_type != "all" else "",
            "limit": min(limit, 50)
        }
        r = requests.get(CRYPTOPANIC_API, params=params, timeout=15)
        if r.status_code != 200:
            return {"error": f"CryptoPanic returned {r.status_code}"}

        data    = r.json()
        results = data.get("results", [])
        items   = []

        for post in results:
            title    = post.get("title", "")
            url      = post.get("url", "")
            pub_at   = post.get("published_at", "")
            source   = post.get("source", {}).get("title", "")
            votes    = post.get("votes", {})
            tokens   = [c.get("code", "") for c in post.get("currencies", [])]
            cats     = classify_catalyst(title)

            items.append({
                "title":        title,
                "source":       source,
                "published":    pub_at[:16].replace("T", " "),
                "catalyst_types": cats,
                "sentiment":    sentiment_emoji(cats),
                "tokens_mentioned": tokens,
                "votes_positive": votes.get("positive", 0),
                "votes_negative": votes.get("negative", 0),
                "url":          url
            })

        return {
            "feed":          items,
            "count":         len(items),
            "filter":        filter_type,
            "fetched_at":    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        }
    except Exception as e:
        return {"error": str(e)}


def get_token_news(token_symbol: str, limit: int = 15) -> dict:
    """
    Fetch news specifically about a token from CryptoPanic.
    token_symbol: e.g. 'BTC', 'ETH', 'UNI', 'ARB'
    Returns classified catalyst items for that token.
    """
    try:
        params = {
            "auth_token": CRYPTOPANIC_KEY,
            "public": "true",
            "currencies": token_symbol.upper(),
            "kind": "news",
            "limit": min(limit, 50)
        }
        r = requests.get(CRYPTOPANIC_API, params=params, timeout=15)
        if r.status_code != 200:
            return {"error": f"CryptoPanic returned {r.status_code}"}

        results = r.json().get("results", [])
        items   = []
        catalyst_counts: dict = {}

        for post in results:
            title = post.get("title", "")
            cats  = classify_catalyst(title)
            for c in cats:
                catalyst_counts[c] = catalyst_counts.get(c, 0) + 1

            items.append({
                "title":          title,
                "source":         post.get("source", {}).get("title", ""),
                "published":      post.get("published_at", "")[:16].replace("T", " "),
                "catalyst_types": cats,
                "sentiment":      sentiment_emoji(cats),
                "url":            post.get("url", "")
            })

        dominant = max(catalyst_counts, key=catalyst_counts.get) if catalyst_counts else "general"

        return {
            "token":             token_symbol.upper(),
            "news_items":        items,
            "count":             len(items),
            "catalyst_breakdown": catalyst_counts,
            "dominant_catalyst": dominant,
            "overall_sentiment": sentiment_emoji([dominant])
        }
    except Exception as e:
        return {"error": str(e)}


def get_coingecko_token_events(token_id: str) -> dict:
    """
    Fetch known upcoming events for a token from CoinGecko
    (status updates, partnerships, exchange listings, releases).
    token_id: CoinGecko slug e.g. 'ethereum', 'uniswap', 'chainlink'
    """
    try:
        r = requests.get(
            f"{COINGECKO_API}/coins/{token_id}",
            params={"localization": "false", "tickers": "false",
                    "market_data": "false", "community_data": "false",
                    "developer_data": "false"},
            timeout=15
        )
        if r.status_code != 200:
            return {"error": f"CoinGecko returned {r.status_code} for '{token_id}'"}

        d = r.json()
        status_updates = d.get("status_updates", [])

        events = []
        for u in status_updates[:10]:
            cats = classify_catalyst(u.get("description", "") + " " + u.get("category", ""))
            events.append({
                "date":           u.get("created_at", "")[:10],
                "category":       u.get("category", ""),
                "description":    (u.get("description") or "")[:300],
                "catalyst_types": cats,
                "sentiment":      sentiment_emoji(cats),
                "pin":            u.get("pin", False)
            })

        links = d.get("links", {})
        return {
            "token":          token_id,
            "name":           d.get("name"),
            "symbol":         d.get("symbol", "").upper(),
            "status_updates": events,
            "upcoming_count": len(events),
            "homepage":       (links.get("homepage") or [""])[0],
            "announcement_channels": links.get("announcement_url", []),
            "twitter":        links.get("twitter_screen_name"),
            "blog":           (links.get("subreddit_url") or "")
        }
    except Exception as e:
        return {"error": str(e)}


def get_exchange_listings(limit: int = 20) -> dict:
    """
    Detect recent exchange listing news by scanning CryptoPanic
    for listing-related stories in the last 48 hours.
    """
    try:
        params = {
            "auth_token": CRYPTOPANIC_KEY,
            "public": "true",
            "kind": "news",
            "limit": 50
        }
        r = requests.get(CRYPTOPANIC_API, params=params, timeout=15)
        if r.status_code != 200:
            return {"error": f"CryptoPanic returned {r.status_code}"}

        results  = r.json().get("results", [])
        listings = []
        cutoff   = datetime.now(timezone.utc) - timedelta(hours=48)

        for post in results:
            title = post.get("title", "")
            pub   = post.get("published_at", "")

            # Parse timestamp
            try:
                pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            except Exception:
                continue

            if pub_dt < cutoff:
                continue

            cats = classify_catalyst(title)
            if "listing" not in cats:
                continue

            tokens = [c.get("code", "") for c in post.get("currencies", [])]
            listings.append({
                "title":    title,
                "tokens":   tokens,
                "source":   post.get("source", {}).get("title", ""),
                "published": pub[:16].replace("T", " "),
                "url":      post.get("url", ""),
                "sentiment": "🟢"
            })

        return {
            "exchange_listings": listings[:limit],
            "count":             len(listings),
            "window":            "last 48 hours",
            "fetched_at":        datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        }
    except Exception as e:
        return {"error": str(e)}


def get_fundraise_news(limit: int = 20) -> dict:
    """
    Surface recent fundraising / VC investment announcements
    from the last 7 days. Returns project name, amount (if parseable),
    and investors mentioned.
    """
    try:
        params = {
            "auth_token": CRYPTOPANIC_KEY,
            "public": "true",
            "kind": "news",
            "limit": 50
        }
        r = requests.get(CRYPTOPANIC_API, params=params, timeout=15)
        if r.status_code != 200:
            return {"error": f"CryptoPanic returned {r.status_code}"}

        results   = r.json().get("results", [])
        raises    = []
        cutoff    = datetime.now(timezone.utc) - timedelta(days=7)
        amt_re    = re.compile(r'\$[\d,.]+\s*(?:million|billion|M|B)\b', re.IGNORECASE)

        for post in results:
            title = post.get("title", "")
            pub   = post.get("published_at", "")
            try:
                pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            except Exception:
                continue
            if pub_dt < cutoff:
                continue

            cats = classify_catalyst(title)
            if "fundraise" not in cats:
                continue

            amounts  = amt_re.findall(title)
            tokens   = [c.get("code", "") for c in post.get("currencies", [])]
            raises.append({
                "title":           title,
                "tokens_involved": tokens,
                "amounts_found":   amounts,
                "source":          post.get("source", {}).get("title", ""),
                "published":       pub[:16].replace("T", " "),
                "url":             post.get("url", ""),
                "sentiment":       "🟢"
            })

        return {
            "fundraise_news": raises[:limit],
            "count":          len(raises),
            "window":         "last 7 days",
            "fetched_at":     datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        }
    except Exception as e:
        return {"error": str(e)}


def get_major_token_unlocks() -> dict:
    """
    Fetch upcoming major token unlocks from DeFiLlama's unlock tracker.
    Returns projects with large unlock events in the next 30 days.
    These are bearish catalysts - large supply releases create sell pressure.
    """
    try:
        r = requests.get(f"{DEFILLAMA_API}/unlocks", timeout=15)
        if r.status_code != 200:
            return {"error": f"DeFiLlama returned {r.status_code}"}

        data     = r.json()
        projects = data.get("protocols", []) or []
        now_ts   = datetime.now(timezone.utc).timestamp()
        window   = 30 * 86400  # 30 days in seconds
        upcoming = []

        for proj in projects:
            events = proj.get("events", []) or []
            for ev in events:
                ts = ev.get("timestamp", 0)
                if not (now_ts <= ts <= now_ts + window):
                    continue

                usd_val = ev.get("noOfTokens", 0) * (proj.get("price") or 0)
                upcoming.append({
                    "project":         proj.get("name", "Unknown"),
                    "token":           proj.get("symbol", ""),
                    "unlock_date":     datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d"),
                    "days_until":      int((ts - now_ts) / 86400),
                    "tokens_unlocked": round(ev.get("noOfTokens", 0), 2),
                    "usd_value_est":   round(usd_val, 0),
                    "unlock_type":     ev.get("type", "unknown"),
                    "sentiment":       "🔴",
                    "note":            "Large unlock = potential sell pressure"
                })

        upcoming.sort(key=lambda x: x["days_until"])

        return {
            "upcoming_unlocks":    upcoming[:25],
            "count":               len(upcoming),
            "window":              "next 30 days",
            "source":              "DeFiLlama",
            "fetched_at":          datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        }
    except Exception as e:
        return {"error": str(e)}


def get_portfolio_catalyst_scan(token_symbols: list) -> dict:
    """
    Scan for all catalysts (news, unlocks, listings) across a list
    of portfolio tokens and produce a prioritised action list.
    token_symbols: e.g. ['BTC', 'ETH', 'UNI', 'ARB', 'LINK']
    """
    summary: dict = {}
    all_catalysts = []

    for sym in token_symbols:
        sym = sym.upper().strip()
        result = get_token_news(sym, limit=10)
        if "error" in result:
            summary[sym] = {"error": result["error"]}
            continue

        items = result.get("news_items", [])
        high_priority = [i for i in items
                         if any(c in BULLISH_CATALYSTS | BEARISH_CATALYSTS
                                for c in i.get("catalyst_types", []))]

        summary[sym] = {
            "total_news":        len(items),
            "high_priority":     len(high_priority),
            "dominant_catalyst": result.get("dominant_catalyst", "general"),
            "overall_sentiment": result.get("overall_sentiment", "🟡"),
            "top_headlines":     [i["title"] for i in high_priority[:3]]
        }

        for item in high_priority[:2]:
            all_catalysts.append({
                "token":          sym,
                "title":          item["title"],
                "catalyst_types": item["catalyst_types"],
                "sentiment":      item["sentiment"],
                "published":      item["published"],
                "url":            item["url"]
            })

    # Sort: bearish first (most urgent), then bullish
    def priority(item):
        cats = item.get("catalyst_types", [])
        if any(c in BEARISH_CATALYSTS for c in cats):
            return 0
        if any(c in BULLISH_CATALYSTS for c in cats):
            return 1
        return 2

    all_catalysts.sort(key=priority)

    bearish_tokens = [s for s, v in summary.items()
                      if v.get("overall_sentiment") == "🔴"]
    bullish_tokens = [s for s, v in summary.items()
                      if v.get("overall_sentiment") == "🟢"]

    return {
        "tokens_scanned":     list(summary.keys()),
        "per_token_summary":  summary,
        "priority_catalysts": all_catalysts[:20],
        "bearish_alert":      bearish_tokens,
        "bullish_alert":      bullish_tokens,
        "action_summary": (
            f"⚠️ Bearish catalysts detected for: {', '.join(bearish_tokens)}. "
            if bearish_tokens else ""
        ) + (
            f"🚀 Bullish catalysts for: {', '.join(bullish_tokens)}."
            if bullish_tokens else ""
        ) or "No high-priority catalysts detected right now.",
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    }


def get_trending_news(limit: int = 15) -> dict:
    """
    Fetch what's trending / most discussed in crypto right now.
    Combines CryptoPanic hot feed with CoinGecko trending tokens.
    """
    results: dict = {"trending_news": [], "trending_tokens": [], "fetched_at": ""}

    # CryptoPanic hot feed
    try:
        params = {
            "auth_token": CRYPTOPANIC_KEY,
            "public": "true",
            "kind": "news",
            "filter": "hot",
            "limit": limit
        }
        r = requests.get(CRYPTOPANIC_API, params=params, timeout=12)
        if r.status_code == 200:
            for post in r.json().get("results", []):
                title = post.get("title", "")
                cats  = classify_catalyst(title)
                results["trending_news"].append({
                    "title":          title,
                    "source":         post.get("source", {}).get("title", ""),
                    "published":      post.get("published_at", "")[:16].replace("T", " "),
                    "catalyst_types": cats,
                    "sentiment":      sentiment_emoji(cats),
                    "tokens":         [c.get("code", "") for c in post.get("currencies", [])],
                    "url":            post.get("url", "")
                })
    except Exception as e:
        results["trending_news_error"] = str(e)

    # CoinGecko trending tokens
    try:
        r2 = requests.get(f"{COINGECKO_API}/search/trending", timeout=12)
        if r2.status_code == 200:
            for item in r2.json().get("coins", [])[:10]:
                coin = item.get("item", {})
                results["trending_tokens"].append({
                    "rank":     coin.get("score", 0) + 1,
                    "name":     coin.get("name"),
                    "symbol":   coin.get("symbol", "").upper(),
                    "market_cap_rank": coin.get("market_cap_rank"),
                    "price_btc": coin.get("price_btc")
                })
    except Exception as e:
        results["trending_tokens_error"] = str(e)

    results["fetched_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return results


def get_partnership_news(limit: int = 20) -> dict:
    """
    Surface recent partnership and collaboration announcements
    from the past 7 days. These are typically bullish catalysts.
    """
    try:
        params = {
            "auth_token": CRYPTOPANIC_KEY,
            "public": "true",
            "kind": "news",
            "limit": 50
        }
        r = requests.get(CRYPTOPANIC_API, params=params, timeout=15)
        if r.status_code != 200:
            return {"error": f"CryptoPanic returned {r.status_code}"}

        results    = r.json().get("results", [])
        partners   = []
        cutoff     = datetime.now(timezone.utc) - timedelta(days=7)

        for post in results:
            title = post.get("title", "")
            pub   = post.get("published_at", "")
            try:
                pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            except Exception:
                continue
            if pub_dt < cutoff:
                continue

            cats = classify_catalyst(title)
            if "partnership" not in cats:
                continue

            tokens = [c.get("code", "") for c in post.get("currencies", [])]
            partners.append({
                "title":           title,
                "tokens_involved": tokens,
                "source":          post.get("source", {}).get("title", ""),
                "published":       pub[:16].replace("T", " "),
                "url":             post.get("url", ""),
                "sentiment":       "🟢"
            })

        return {
            "partnership_news": partners[:limit],
            "count":            len(partners),
            "window":           "last 7 days",
            "fetched_at":       datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        }
    except Exception as e:
        return {"error": str(e)}


def get_hack_and_exploit_alerts() -> dict:
    """
    Detect recent hack, exploit, and security breach news.
    These are high-urgency bearish catalysts.
    Returns last 48 hours of security incidents.
    """
    try:
        params = {
            "auth_token": CRYPTOPANIC_KEY,
            "public": "true",
            "kind": "news",
            "limit": 50
        }
        r = requests.get(CRYPTOPANIC_API, params=params, timeout=15)
        if r.status_code != 200:
            return {"error": f"CryptoPanic returned {r.status_code}"}

        results  = r.json().get("results", [])
        alerts   = []
        cutoff   = datetime.now(timezone.utc) - timedelta(hours=48)
        amt_re   = re.compile(r'\$[\d,.]+\s*(?:million|billion|M|B|k)\b', re.IGNORECASE)

        for post in results:
            title = post.get("title", "")
            pub   = post.get("published_at", "")
            try:
                pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            except Exception:
                continue
            if pub_dt < cutoff:
                continue

            cats = classify_catalyst(title)
            if "hack_exploit" not in cats:
                continue

            amounts = amt_re.findall(title)
            tokens  = [c.get("code", "") for c in post.get("currencies", [])]
            alerts.append({
                "title":           title,
                "tokens_affected": tokens,
                "amounts_lost":    amounts,
                "source":          post.get("source", {}).get("title", ""),
                "published":       pub[:16].replace("T", " "),
                "url":             post.get("url", ""),
                "urgency":         "🔴 HIGH PRIORITY"
            })

        return {
            "hack_exploit_alerts": alerts,
            "count":               len(alerts),
            "window":              "last 48 hours",
            "message": (
                f"🚨 {len(alerts)} security incident(s) detected in last 48h!"
                if alerts else
                "✅ No major hacks or exploits detected in the last 48 hours."
            ),
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        }
    except Exception as e:
        return {"error": str(e)}


def get_regulatory_news(limit: int = 15) -> dict:
    """
    Surface recent regulatory news: SEC actions, ETF decisions,
    government bans or approvals, legal proceedings.
    """
    try:
        params = {
            "auth_token": CRYPTOPANIC_KEY,
            "public": "true",
            "kind": "news",
            "limit": 50
        }
        r = requests.get(CRYPTOPANIC_API, params=params, timeout=15)
        if r.status_code != 200:
            return {"error": f"CryptoPanic returned {r.status_code}"}

        results    = r.json().get("results", [])
        regulatory = []
        cutoff     = datetime.now(timezone.utc) - timedelta(days=7)

        for post in results:
            title = post.get("title", "")
            pub   = post.get("published_at", "")
            try:
                pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            except Exception:
                continue
            if pub_dt < cutoff:
                continue

            cats = classify_catalyst(title)
            if "regulatory" not in cats:
                continue

            tokens = [c.get("code", "") for c in post.get("currencies", [])]
            # Try to determine if this is positive or negative regulatory news
            positive_words = ["approve", "approved", "etf", "legal tender", "allows", "green light"]
            negative_words = ["ban", "banned", "lawsuit", "sued", "charges", "illegal", "restrict"]
            title_lower    = title.lower()
            reg_sentiment  = (
                "🟢" if any(w in title_lower for w in positive_words) else
                "🔴" if any(w in title_lower for w in negative_words) else
                "🟡"
            )

            regulatory.append({
                "title":           title,
                "tokens_affected": tokens,
                "source":          post.get("source", {}).get("title", ""),
                "published":       pub[:16].replace("T", " "),
                "sentiment":       reg_sentiment,
                "url":             post.get("url", "")
            })

        return {
            "regulatory_news": regulatory[:limit],
            "count":           len(regulatory),
            "window":          "last 7 days",
            "fetched_at":      datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        }
    except Exception as e:
        return {"error": str(e)}


def generate_actionable_brief(scan_results: dict) -> dict:
    """
    Synthesise raw scan data into a concise actionable brief.
    Pass the output from get_portfolio_catalyst_scan or any combination
    of catalyst results. Returns a structured briefing with:
    - URGENT items (act now)
    - WATCH items (monitor closely)
    - OPPORTUNITY items (potential upside catalysts)

    scan_results keys (all optional):
      bearish_alert: list of token symbols with bearish news
      bullish_alert: list of token symbols with bullish news
      priority_catalysts: list of catalyst dicts
      hack_alerts: list of hack/exploit items
      unlocks: list of unlock items
      listings: list of listing items
      fundraises: list of fundraise items
    """
    urgent    = []
    watch     = []
    opportun  = []

    # Hacks → always urgent
    for item in scan_results.get("hack_alerts", []):
        urgent.append({
            "action":  "⚠️ SECURITY ALERT",
            "detail":  item.get("title", ""),
            "tokens":  item.get("tokens_affected", []),
            "url":     item.get("url", "")
        })

    # Unlocks within 7 days → urgent/watch
    for item in scan_results.get("unlocks", []):
        days = item.get("days_until", 99)
        entry = {
            "action": "📉 TOKEN UNLOCK",
            "detail": f"{item.get('project')} - {item.get('tokens_unlocked')} {item.get('token')} unlocking (~${item.get('usd_value_est', 0):,.0f})",
            "tokens": [item.get("token", "")],
            "date":   item.get("unlock_date", "")
        }
        if days <= 7:
            urgent.append(entry)
        else:
            watch.append(entry)

    # Bearish catalyst news → watch
    for sym in scan_results.get("bearish_alert", []):
        watch.append({
            "action": f"🔴 BEARISH NEWS - {sym}",
            "detail": f"Negative catalyst detected for {sym}. Review latest news.",
            "tokens": [sym]
        })

    # Listings → opportunity
    for item in scan_results.get("listings", []):
        opportun.append({
            "action":  "🟢 EXCHANGE LISTING",
            "detail":  item.get("title", ""),
            "tokens":  item.get("tokens", []),
            "url":     item.get("url", "")
        })

    # Fundraises → opportunity
    for item in scan_results.get("fundraises", []):
        opportun.append({
            "action":  "🟢 FUNDRAISE",
            "detail":  item.get("title", ""),
            "tokens":  item.get("tokens_involved", []),
            "amounts": item.get("amounts_found", []),
            "url":     item.get("url", "")
        })

    # Bullish catalyst news → opportunity
    for sym in scan_results.get("bullish_alert", []):
        opportun.append({
            "action": f"📈 BULLISH CATALYST - {sym}",
            "detail": f"Positive catalyst detected for {sym}. Review for entry/add opportunity.",
            "tokens": [sym]
        })

    return {
        "actionable_brief": {
            "URGENT":      urgent,
            "WATCH":       watch,
            "OPPORTUNITY": opportun
        },
        "counts": {
            "urgent":      len(urgent),
            "watch":       len(watch),
            "opportunity": len(opportun)
        },
        "headline": (
            f"🚨 {len(urgent)} URGENT items need immediate attention!"
            if urgent else
            f"👀 {len(watch)} items to watch, {len(opportun)} potential opportunities."
            if watch or opportun else
            "✅ Market is quiet. No urgent catalysts right now."
        ),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    }


# ─── Tool Registry ─────────────────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_crypto_news_feed",
            "description": "Fetch latest classified crypto news from CryptoPanic. Each item is tagged with catalyst type (listing, partnership, fundraise, hack, governance, etc.) and sentiment. Use filter_type='hot' for trending, 'bullish'/'bearish' for community-tagged sentiment.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filter_type": {"type": "string", "description": "'all', 'hot', 'rising', 'bullish', 'bearish', 'important' (default 'all')"},
                    "limit":       {"type": "integer", "description": "Number of items (default 20, max 50)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_token_news",
            "description": "Fetch and classify recent news specifically about one token. Returns catalyst breakdown and dominant catalyst type. Use for single-token deep dives.",
            "parameters": {
                "type": "object",
                "properties": {
                    "token_symbol": {"type": "string", "description": "Token ticker e.g. 'BTC', 'ETH', 'UNI', 'ARB'"},
                    "limit":        {"type": "integer", "description": "Number of items (default 15)"}
                },
                "required": ["token_symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_coingecko_token_events",
            "description": "Fetch known status updates and events for a token from CoinGecko (partnerships, releases, announcements). token_id is the CoinGecko slug e.g. 'uniswap', 'chainlink'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "token_id": {"type": "string", "description": "CoinGecko token slug"}
                },
                "required": ["token_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_exchange_listings",
            "description": "Surface recent exchange listing announcements from the last 48 hours. Listings are bullish catalysts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max results (default 20)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_fundraise_news",
            "description": "Surface recent fundraising and VC investment announcements from the last 7 days. Returns project, amounts raised, and investors.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max results (default 20)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_major_token_unlocks",
            "description": "Fetch upcoming major token unlock events from DeFiLlama for the next 30 days. Large unlocks = potential sell pressure = bearish catalyst. ALWAYS include this in portfolio briefings.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_portfolio_catalyst_scan",
            "description": "Scan all catalysts for a list of portfolio tokens at once. Returns per-token news summary, dominant catalysts, and a prioritised action list. Use for 'what's happening with my portfolio?' type queries.",
            "parameters": {
                "type": "object",
                "properties": {
                    "token_symbols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of token symbols e.g. ['BTC', 'ETH', 'UNI', 'ARB', 'LINK']"
                    }
                },
                "required": ["token_symbols"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_trending_news",
            "description": "Fetch what's trending / most discussed in crypto right now. Combines CryptoPanic hot feed with CoinGecko trending tokens.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Number of news items (default 15)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_partnership_news",
            "description": "Surface recent partnership and collaboration announcements from the last 7 days.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max results (default 20)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_hack_and_exploit_alerts",
            "description": "Detect recent hack, exploit, and security breach news from the last 48 hours. ALWAYS call this for portfolio briefings - critical for risk management.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_regulatory_news",
            "description": "Surface recent regulatory news: SEC actions, ETF decisions, government bans or approvals, legal proceedings affecting crypto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max results (default 15)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_actionable_brief",
            "description": "Synthesise raw catalyst scan data into a structured URGENT / WATCH / OPPORTUNITY briefing. Call this LAST after collecting catalyst data to produce the final actionable summary.",
            "parameters": {
                "type": "object",
                "properties": {
                    "scan_results": {
                        "type": "object",
                        "description": "Dict with optional keys: bearish_alert (list), bullish_alert (list), priority_catalysts (list), hack_alerts (list), unlocks (list), listings (list), fundraises (list)."
                    }
                },
                "required": ["scan_results"]
            }
        }
    }
]

TOOL_MAP = {
    "get_crypto_news_feed":         get_crypto_news_feed,
    "get_token_news":               get_token_news,
    "get_coingecko_token_events":   get_coingecko_token_events,
    "get_exchange_listings":        get_exchange_listings,
    "get_fundraise_news":           get_fundraise_news,
    "get_major_token_unlocks":      get_major_token_unlocks,
    "get_portfolio_catalyst_scan":  get_portfolio_catalyst_scan,
    "get_trending_news":            get_trending_news,
    "get_partnership_news":         get_partnership_news,
    "get_hack_and_exploit_alerts":  get_hack_and_exploit_alerts,
    "get_regulatory_news":          get_regulatory_news,
    "generate_actionable_brief":    generate_actionable_brief,
}

SYSTEM_PROMPT = """You are a crypto news and catalyst intelligence agent. You monitor exchange listings, partnerships, fundraises, token unlocks, governance events, hacks, and regulatory news - and turn them into concise, actionable briefings.

## Query flows:

### Full portfolio briefing
"What's happening with my portfolio?" / "Give me a morning briefing for [tokens]"
1. get_portfolio_catalyst_scan(token_symbols=[...])
2. get_hack_and_exploit_alerts()
3. get_major_token_unlocks()
4. get_exchange_listings()
5. generate_actionable_brief(scan_results={...merged data...})

### Single token deep dive
"What's the latest on ARB?" / "Any catalysts for LINK?"
1. get_token_news(token_symbol)
2. get_coingecko_token_events(token_id)  ← use CoinGecko slug

### Category-specific queries
- "Any new exchange listings?"        → get_exchange_listings()
- "Recent fundraises?"                → get_fundraise_news()
- "Any hacks today?"                  → get_hack_and_exploit_alerts()
- "What's trending?"                  → get_trending_news()
- "Recent partnerships?"              → get_partnership_news()
- "Upcoming token unlocks?"           → get_major_token_unlocks()
- "Regulatory news?"                  → get_regulatory_news()
- "What's hot in crypto right now?"   → get_crypto_news_feed(filter_type='hot')

## Output style:
Structure output in three sections:
🚨 URGENT   - hacks, immediate threats, closing unlocks
👀 WATCH    - bearish signals, upcoming unlocks, negative regulatory
🚀 OPPORTUNITY - new listings, fundraises, partnerships, bullish catalysts

Lead every briefing with a one-line market pulse.
Keep headlines tight - one sentence per item plus the URL.
Always include: what it means, which token is affected, and what to do.
Never give financial advice; frame as "signals to monitor".
"""


# ─── Agent Loop ────────────────────────────────────────────────────────────────

def call_ollama(messages: list) -> Any:
    payload = {
        "model": MODEL,
        "messages": messages,
        "tools": TOOLS,
        "stream": False
    }
    resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()


def execute_tool(tool_name: str, tool_args: dict) -> str:
    func = TOOL_MAP.get(tool_name)
    if not func:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    try:
        result = func(**tool_args)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


def run_agent(user_input: str, conversation_history: list) -> tuple[str, list]:
    conversation_history.append({"role": "user", "content": user_input})
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + conversation_history

    max_iterations = 12
    for _ in range(max_iterations):
        response = call_ollama(messages)
        message  = response["message"]
        tool_calls = message.get("tool_calls", [])

        if not tool_calls:
            assistant_reply = message.get("content", "")
            conversation_history.append({"role": "assistant", "content": assistant_reply})
            return assistant_reply, conversation_history

        print(f"  🔧 Tools: {[tc['function']['name'] for tc in tool_calls]}")
        messages.append({
            "role": "assistant",
            "content": message.get("content", ""),
            "tool_calls": tool_calls
        })

        for tc in tool_calls:
            tool_name = tc["function"]["name"]
            tool_args = tc["function"].get("arguments", {})
            if isinstance(tool_args, str):
                tool_args = json.loads(tool_args)

            print(f"  📡 {tool_name}({list(tool_args.values())[:2]})...")
            result = execute_tool(tool_name, tool_args)
            print("  ✅ Done")
            messages.append({"role": "tool", "content": result})

    return "Agent reached maximum iterations.", conversation_history


# ─── CLI ───────────────────────────────────────────────────────────────────────

def main():
    print("=" * 65)
    print("  📡 News & Catalyst AI Agent")
    print("  Monitors: Listings · Partnerships · Fundraises · Unlocks · Hacks")
    print("  Powered by Ollama + CryptoPanic + CoinGecko + DeFiLlama")
    print("=" * 65)
    print(f"  Model: {MODEL}")
    print()
    print("  Example queries:")
    print("  • Morning briefing for my portfolio: ETH, UNI, ARB, LINK, ENS")
    print("  • Any catalysts for ARB today?")
    print("  • What new exchange listings happened in the last 48h?")
    print("  • Any hacks or exploits today?")
    print("  • Recent fundraises in crypto?")
    print("  • Upcoming token unlocks I should know about?")
    print("  • What's trending in crypto right now?")
    print("  • Recent partnership announcements?")
    print("  • Any regulatory news this week?")
    print("  • What's the latest on Chainlink?")
    print()
    print("  Type 'quit' to exit, 'clear' to reset")
    print("=" * 65)
    print()

    conversation_history = []

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Goodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() == "quit":
            print("👋 Goodbye!")
            break
        if user_input.lower() == "clear":
            conversation_history = []
            print("🔄 Conversation cleared.\n")
            continue

        print()
        try:
            reply, conversation_history = run_agent(user_input, conversation_history)
            print(f"Agent:\n{reply}")
        except requests.exceptions.ConnectionError:
            print("❌ Cannot connect to Ollama. Make sure it's running: `ollama serve`")
        except Exception as e:
            print(f"❌ Error: {e}")
        print()


if __name__ == "__main__":
    main()