import json
import time
import requests
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from typing import Any

OLLAMA_URL    = "http://localhost:11434/api/chat"
MODEL         = "llama3.1"

COINGECKO_API = "https://api.coingecko.com/api/v3"
DEFILLAMA_API = "https://api.llama.fi"
GITHUB_API    = "https://api.github.com"

HEADERS = {"User-Agent": "MarketIntelAgent/1.0"}

NARRATIVE_MAP = {
    "layer-1":                       "Layer 1 Blockchains",
    "ethereum-ecosystem":             "Ethereum Ecosystem",
    "solana-ecosystem":               "Solana Ecosystem",
    "avalanche-ecosystem":            "Avalanche Ecosystem",
    "cosmos-ecosystem":               "Cosmos / IBC",
    "near-protocol-ecosystem":        "NEAR Ecosystem",
    "sui-ecosystem":                  "Sui Ecosystem",
    "aptos-ecosystem":                "Aptos Ecosystem",
    "layer-2":                        "Layer 2 Scaling",
    "arbitrum-ecosystem":             "Arbitrum Ecosystem",
    "optimism-ecosystem":             "Optimism Ecosystem",
    "polygon-ecosystem":              "Polygon Ecosystem",
    "zksync-ecosystem":               "zkSync Ecosystem",
    "decentralized-finance-defi":     "DeFi",
    "decentralized-exchange":         "DEXs",
    "lending-borrowing":              "Lending / Borrowing",
    "liquid-staking-tokens":          "Liquid Staking",
    "yield-aggregator":               "Yield Aggregators",
    "real-world-assets-rwa":          "Real World Assets (RWA)",
    "artificial-intelligence":        "AI Tokens",
    "decentralized-ai":               "Decentralized AI",
    "large-language-model":           "LLM / AI Infra",
    "ai-agents":                      "AI Agents",
    "data-availability":              "Data Availability",
    "oracle":                         "Oracles",
    "non-fungible-tokens-nft":        "NFTs",
    "gaming":                         "GameFi",
    "play-to-earn":                   "Play-to-Earn",
    "socialfi":                       "SocialFi",
    "metaverse":                      "Metaverse",
    "meme-token":                     "Meme Coins",
    "dog-themed-coins":               "Dog Memes",
    "cat-themed-coins":               "Cat Memes",
    "privacy-coins":                  "Privacy",
    "cross-chain-communication":      "Cross-Chain / Bridges",
    "storage":                        "Decentralized Storage",
    "infrastructure":                 "Infrastructure",
    "stablecoins":                    "Stablecoins",
    "desci":                          "DeSci",
    "decentralized-physical-infrastructure-networks-depin": "DePIN",
    "restaking":                      "Restaking",
    "modular-blockchain":             "Modular Blockchains",
    "zero-knowledge-zk":              "Zero Knowledge (ZK)",
    "account-abstraction":            "Account Abstraction",
    "bitcoin-ecosystem":              "Bitcoin Ecosystem",
    "wrapped-tokens":                 "Wrapped Tokens",
}

ALL_CATEGORY_IDS = list(NARRATIVE_MAP.keys())

def _get(url: str, params: dict = None) -> Any:
    try:
        r = requests.get(url, params=params or {}, headers=HEADERS, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def _pct(val) -> str:
    if val is None:
        return "N/A"
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.2f}%"


def _fmt_usd(val) -> str:
    if val is None:
        return "N/A"
    if val >= 1_000_000_000:
        return f"${val/1e9:.2f}B"
    if val >= 1_000_000:
        return f"${val/1e6:.2f}M"
    if val >= 1_000:
        return f"${val/1e3:.1f}K"
    return f"${val:.2f}"

def get_trending_narratives(top_n: int = 10) -> dict:
    """
    Rank crypto narratives/sectors by average 24h price performance.
    Surfaces which themes are gaining momentum today.
    """
    data = _get(f"{COINGECKO_API}/coins/categories")
    if isinstance(data, dict) and "error" in data:
        return data

    results = []
    for cat in data:
        cid = cat.get("id", "")
        label = NARRATIVE_MAP.get(cid, cat.get("name", cid))
        chg = cat.get("market_cap_change_24h")
        vol = cat.get("volume_24h")
        mcap = cat.get("market_cap")
        if chg is None:
            continue
        results.append({
            "narrative": label,
            "category_id": cid,
            "market_cap_change_24h_pct": round(chg, 2),
            "volume_24h_usd": _fmt_usd(vol),
            "market_cap_usd": _fmt_usd(mcap),
            "top_3_coins": cat.get("top_3_coins", [])[:3],
        })

    gainers = sorted(results, key=lambda x: x["market_cap_change_24h_pct"], reverse=True)[:top_n]
    losers  = sorted(results, key=lambda x: x["market_cap_change_24h_pct"])[:5]

    return {
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "top_gaining_narratives": gainers,
        "top_losing_narratives":  losers,
        "total_categories_tracked": len(results),
    }


def get_sector_rotation(days: int = 7) -> dict:
    """
    Compare 24h vs 7d performance per sector to detect rotation:
    sectors accelerating (24h > 7d avg) vs decelerating.
    """
    data = _get(f"{COINGECKO_API}/coins/categories")
    if isinstance(data, dict) and "error" in data:
        return data

    accelerating = []
    decelerating = []

    for cat in data:
        cid   = cat.get("id", "")
        label = NARRATIVE_MAP.get(cid, cat.get("name", cid))
        chg_24h = cat.get("market_cap_change_24h")
        if chg_24h is None:
            continue
        entry = {
            "narrative": label,
            "category_id": cid,
            "change_24h_pct": round(chg_24h, 2),
            "volume_24h_usd": _fmt_usd(cat.get("volume_24h")),
        }
        if chg_24h > 3:
            accelerating.append(entry)
        elif chg_24h < -3:
            decelerating.append(entry)

    accelerating.sort(key=lambda x: x["change_24h_pct"], reverse=True)
    decelerating.sort(key=lambda x: x["change_24h_pct"])

    return {
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "rotating_in":  accelerating[:8],
        "rotating_out": decelerating[:8],
        "signal": "Sectors with >3% 24h gain = capital flowing in. <-3% = capital leaving.",
    }


def get_trending_coins() -> dict:
    """Get the top trending coins on CoinGecko in the last 24h with context."""
    data = _get(f"{COINGECKO_API}/search/trending")
    if isinstance(data, dict) and "error" in data:
        return data

    coins = []
    for item in data.get("coins", []):
        c = item["item"]
        coins.append({
            "name":          c["name"],
            "symbol":        c["symbol"],
            "market_cap_rank": c.get("market_cap_rank", "unranked"),
            "score":         c.get("score", 0),
            "price_btc":     c.get("price_btc"),
            "data": {
                "price_usd":         c.get("data", {}).get("price"),
                "price_change_24h":  c.get("data", {}).get("price_change_percentage_24h", {}).get("usd"),
                "market_cap":        c.get("data", {}).get("market_cap"),
                "total_volume":      c.get("data", {}).get("total_volume"),
                "sparkline":         c.get("data", {}).get("sparkline"),
            }
        })

    nfts = []
    for nft in data.get("nfts", [])[:5]:
        nfts.append({
            "name":          nft.get("name"),
            "symbol":        nft.get("symbol"),
            "floor_price":   nft.get("floor_price_in_native_currency"),
            "change_24h":    nft.get("floor_price_24h_percentage_change"),
        })

    return {
        "trending_coins": coins,
        "trending_nfts":  nfts,
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }


def get_volume_spikes(min_volume_usd: float = 50_000_000, top_n: int = 20) -> dict:
    """
    Detect coins with unusually high 24h trading volume relative to market cap.
    High vol/mcap ratio = speculative interest spike.
    """
    params = {
        "vs_currency": "usd",
        "order": "volume_desc",
        "per_page": 100,
        "page": 1,
        "sparkline": False,
        "price_change_percentage": "1h,24h,7d",
    }
    data = _get(f"{COINGECKO_API}/coins/markets", params)
    if isinstance(data, dict) and "error" in data:
        return data

    spikes = []
    for c in data:
        vol  = c.get("total_volume") or 0
        mcap = c.get("market_cap") or 1
        if vol < min_volume_usd:
            continue
        ratio = vol / mcap if mcap else 0
        spikes.append({
            "name":          c["name"],
            "symbol":        c["symbol"].upper(),
            "rank":          c.get("market_cap_rank"),
            "price_usd":     c["current_price"],
            "volume_24h":    _fmt_usd(vol),
            "market_cap":    _fmt_usd(mcap),
            "vol_mcap_ratio": round(ratio, 3),
            "change_1h_pct":  c.get("price_change_percentage_1h_in_currency"),
            "change_24h_pct": c.get("price_change_percentage_24h"),
            "change_7d_pct":  c.get("price_change_percentage_7d_in_currency"),
        })

    spikes.sort(key=lambda x: x["vol_mcap_ratio"], reverse=True)

    return {
        "volume_spikes": spikes[:top_n],
        "note": "vol_mcap_ratio > 0.5 means daily volume exceeds 50% of market cap - extreme speculative activity.",
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }


def get_narrative_coins(narrative: str, top_n: int = 15) -> dict:
    """
    Get top coins within a specific narrative/sector with full market data.
    narrative can be a label like 'AI Tokens', 'DePIN', 'Layer 2 Scaling', etc.
    """
    cat_id = None
    narrative_lower = narrative.lower()
    for cid, label in NARRATIVE_MAP.items():
        if narrative_lower in label.lower() or narrative_lower in cid.lower():
            cat_id = cid
            break

    if not cat_id:
        return {"error": f"Narrative '{narrative}' not found. Try: AI Tokens, DePIN, Layer 2 Scaling, RWA, Meme Coins, etc."}

    params = {
        "vs_currency": "usd",
        "category": cat_id,
        "order": "market_cap_desc",
        "per_page": top_n,
        "page": 1,
        "sparkline": False,
        "price_change_percentage": "1h,24h,7d",
    }
    data = _get(f"{COINGECKO_API}/coins/markets", params)
    if isinstance(data, dict) and "error" in data:
        return data

    coins = []
    for c in data:
        coins.append({
            "name":           c["name"],
            "symbol":         c["symbol"].upper(),
            "rank":           c.get("market_cap_rank"),
            "price_usd":      c["current_price"],
            "market_cap":     _fmt_usd(c["market_cap"]),
            "volume_24h":     _fmt_usd(c["total_volume"]),
            "change_1h_pct":  _pct(c.get("price_change_percentage_1h_in_currency")),
            "change_24h_pct": _pct(c.get("price_change_percentage_24h")),
            "change_7d_pct":  _pct(c.get("price_change_percentage_7d_in_currency")),
            "ath_drawdown":   _pct(c.get("ath_change_percentage")),
        })

    total_vol = sum(c.get("total_volume") or 0 for c in data)
    avg_24h   = sum(c.get("price_change_percentage_24h") or 0 for c in data) / max(len(data), 1)

    return {
        "narrative":   NARRATIVE_MAP.get(cat_id, narrative),
        "category_id": cat_id,
        "coins":       coins,
        "summary": {
            "total_coins_shown": len(coins),
            "avg_24h_change_pct": round(avg_24h, 2),
            "total_volume_24h":   _fmt_usd(total_vol),
        },
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }


def get_defi_tvl_momentum() -> dict:
    """
    Track DeFi TVL momentum: which protocols are gaining or losing TVL fastest.
    TVL inflows = users deploying capital = bullish signal for that protocol/chain.
    """
    data = _get(f"{DEFILLAMA_API}/protocols")
    if isinstance(data, dict) and "error" in data:
        return data

    entries = []
    for p in data:
        tvl     = p.get("tvl") or 0
        chg_1d  = p.get("change_1d")
        chg_7d  = p.get("change_7d")
        if tvl < 1_000_000 or chg_1d is None:
            continue
        entries.append({
            "name":       p["name"],
            "category":   p.get("category", ""),
            "chain":      p.get("chain", ""),
            "tvl":        _fmt_usd(tvl),
            "tvl_raw":    tvl,
            "change_1d":  round(chg_1d, 2),
            "change_7d":  round(chg_7d, 2) if chg_7d is not None else None,
        })

    gainers = sorted(entries, key=lambda x: x["change_1d"], reverse=True)[:10]
    losers  = sorted(entries, key=lambda x: x["change_1d"])[:10]
    largest = sorted(entries, key=lambda x: x["tvl_raw"], reverse=True)[:10]

    for e in gainers + losers + largest:
        del e["tvl_raw"]

    return {
        "tvl_gainers_1d":  gainers,
        "tvl_losers_1d":   losers,
        "largest_by_tvl":  largest,
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }


def get_chain_tvl_momentum() -> dict:
    """
    Which blockchain ecosystems are gaining TVL (capital inflow) vs losing it?
    A leading indicator of narrative / ecosystem rotation.
    """
    data = _get(f"{DEFILLAMA_API}/v2/chains")
    if isinstance(data, dict) and "error" in data:
        return data

    total_tvl = sum(c.get("tvl", 0) for c in data)
    entries = []
    for c in data:
        tvl = c.get("tvl", 0)
        if tvl < 500_000:
            continue
        entries.append({
            "chain":      c.get("name"),
            "tvl":        _fmt_usd(tvl),
            "tvl_raw":    tvl,
            "dominance":  f"{round(tvl/total_tvl*100,2)}%",
        })

    entries.sort(key=lambda x: x["tvl_raw"], reverse=True)
    top = entries[:15]
    for e in top:
        del e["tvl_raw"]

    return {
        "chain_tvl_ranking": top,
        "total_defi_tvl":    _fmt_usd(total_tvl),
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }


def get_global_market_pulse() -> dict:
    """
    Snapshot of global crypto market conditions: fear/greed proxy,
    BTC dominance, total market cap, altcoin season signal.
    """
    global_data = _get(f"{COINGECKO_API}/global")
    if isinstance(global_data, dict) and "error" in global_data:
        return global_data

    d = global_data.get("data", {})
    btc_dom = d.get("market_cap_percentage", {}).get("btc", 0)
    eth_dom = d.get("market_cap_percentage", {}).get("eth", 0)
    total   = d.get("total_market_cap", {}).get("usd", 0)
    vol24h  = d.get("total_volume", {}).get("usd", 0)
    chg24h  = d.get("market_cap_change_percentage_24h_usd", 0)

    alt_signal = "🟢 Altcoin Season" if btc_dom < 45 else ("🟡 Transitioning" if btc_dom < 55 else "🔴 BTC Season")
    market_mood = "📈 Risk-On" if chg24h > 1 else ("📉 Risk-Off" if chg24h < -1 else "😐 Neutral")

    params = {"vs_currency": "usd", "order": "market_cap_desc", "per_page": 20, "page": 1,
              "sparkline": False, "price_change_percentage": "24h"}
    top20 = _get(f"{COINGECKO_API}/coins/markets", params)
    top_gainers = sorted(top20, key=lambda x: x.get("price_change_percentage_24h") or 0, reverse=True)[:5]
    top_losers  = sorted(top20, key=lambda x: x.get("price_change_percentage_24h") or 0)[:5]

    return {
        "market_pulse": {
            "total_market_cap":        _fmt_usd(total),
            "total_volume_24h":        _fmt_usd(vol24h),
            "market_cap_change_24h":   _pct(chg24h),
            "btc_dominance":           f"{round(btc_dom,2)}%",
            "eth_dominance":           f"{round(eth_dom,2)}%",
            "altcoin_season_signal":   alt_signal,
            "market_mood":             market_mood,
            "active_cryptocurrencies": d.get("active_cryptocurrencies"),
            "active_markets":          d.get("markets"),
        },
        "top_gainers_24h": [{"name": c["name"], "symbol": c["symbol"].upper(),
                              "change": _pct(c.get("price_change_percentage_24h"))} for c in top_gainers],
        "top_losers_24h":  [{"name": c["name"], "symbol": c["symbol"].upper(),
                              "change": _pct(c.get("price_change_percentage_24h"))} for c in top_losers],
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }


def compare_narratives(narrative_list: list) -> dict:
    """
    Side-by-side performance comparison of multiple narratives/sectors.
    E.g. compare AI Tokens vs DePIN vs RWA vs Layer 2.
    """
    results = []
    all_cats = _get(f"{COINGECKO_API}/coins/categories")
    if isinstance(all_cats, dict) and "error" in all_cats:
        return all_cats

    cat_lookup = {c["id"]: c for c in all_cats}

    for narr in narrative_list:
        narr_lower = narr.lower()
        cat_id = None
        for cid, label in NARRATIVE_MAP.items():
            if narr_lower in label.lower() or narr_lower in cid.lower():
                cat_id = cid
                break
        if not cat_id:
            results.append({"narrative": narr, "error": "not found"})
            continue
        c = cat_lookup.get(cat_id, {})
        results.append({
            "narrative":        NARRATIVE_MAP.get(cat_id, narr),
            "change_24h_pct":   round(c.get("market_cap_change_24h") or 0, 2),
            "market_cap":       _fmt_usd(c.get("market_cap")),
            "volume_24h":       _fmt_usd(c.get("volume_24h")),
            "top_coins":        c.get("top_3_coins", [])[:3],
        })

    results.sort(key=lambda x: x.get("change_24h_pct", -999), reverse=True)
    return {
        "comparison": results,
        "winner":     results[0]["narrative"] if results else "N/A",
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }


def get_github_ecosystem_activity(ecosystem: str) -> dict:
    """
    Measure developer activity in a crypto ecosystem via GitHub.
    Searches for recently updated repos in that ecosystem.
    """
    queries = {
        "solana":   "solana blockchain topic:solana",
        "ethereum": "ethereum topic:ethereum",
        "ai":       "crypto ai agent blockchain",
        "depin":    "depin decentralized physical infrastructure",
        "zk":       "zero knowledge proof zkp",
        "l2":       "layer2 rollup ethereum scaling",
        "defi":     "defi protocol ethereum solana",
        "nft":      "nft marketplace blockchain",
    }
    q = queries.get(ecosystem.lower(), f"{ecosystem} blockchain")
    try:
        params = {"q": q, "sort": "updated", "order": "desc", "per_page": 5}
        r = requests.get(f"{GITHUB_API}/search/repositories", params=params, headers=HEADERS, timeout=10)
        data = r.json()
        repos = []
        for repo in data.get("items", []):
            repos.append({
                "name":         repo["full_name"],
                "stars":        repo["stargazers_count"],
                "forks":        repo["forks_count"],
                "language":     repo.get("language"),
                "last_updated": repo.get("updated_at", "")[:10],
                "description":  (repo.get("description") or "")[:100],
                "topics":       repo.get("topics", [])[:5],
            })
        return {
            "ecosystem": ecosystem,
            "query": q,
            "active_repos":  repos,
            "total_matching": data.get("total_count", 0),
        }
    except Exception as e:
        return {"error": str(e)}


def get_new_listings_momentum() -> dict:
    """
    Find recently listed coins with high momentum - new narratives emerging.
    Coins less than 30 days old with significant volume = new narrative signal.
    """
    params = {
        "vs_currency": "usd",
        "order": "gecko_desc",
        "per_page": 50,
        "page": 1,
        "sparkline": False,
        "price_change_percentage": "24h,7d",
    }
    data = _get(f"{COINGECKO_API}/coins/markets", params)
    if isinstance(data, dict) and "error" in data:
        return data

    new_momentum = []
    for c in data:
        vol  = c.get("total_volume") or 0
        mcap = c.get("market_cap") or 1
        chg  = c.get("price_change_percentage_24h") or 0
        if vol < 1_000_000:
            continue
        if mcap == 0:
            continue
        ratio = vol / mcap
        if ratio > 0.3 or abs(chg) > 10:
            new_momentum.append({
                "name":           c["name"],
                "symbol":         c["symbol"].upper(),
                "rank":           c.get("market_cap_rank", "N/A"),
                "price":          c["current_price"],
                "change_24h":     _pct(chg),
                "change_7d":      _pct(c.get("price_change_percentage_7d_in_currency")),
                "volume_24h":     _fmt_usd(vol),
                "vol_mcap_ratio": round(ratio, 2),
            })

    new_momentum.sort(key=lambda x: x["vol_mcap_ratio"], reverse=True)
    return {
        "high_momentum_coins": new_momentum[:15],
        "note": "High vol/mcap ratio or >10% move = potential new narrative signal",
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_global_market_pulse",
            "description": "Get global crypto market snapshot: total market cap, BTC/ETH dominance, altcoin season signal, market mood, top gainers/losers",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_trending_narratives",
            "description": "Rank all crypto narratives/sectors by 24h market cap change. Shows which themes are gaining momentum right now.",
            "parameters": {
                "type": "object",
                "properties": {
                    "top_n": {"type": "integer", "description": "How many top narratives to return (default 10)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_sector_rotation",
            "description": "Detect sector rotation: which narratives are accelerating (capital flowing IN) vs decelerating (capital flowing OUT)",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Lookback window in days (default 7)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_trending_coins",
            "description": "Get the hottest trending coins and NFTs on CoinGecko in the last 24 hours",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_volume_spikes",
            "description": "Detect coins with unusual volume spikes relative to their market cap - signals speculative interest or narrative activation",
            "parameters": {
                "type": "object",
                "properties": {
                    "min_volume_usd": {"type": "number", "description": "Minimum 24h volume in USD (default 50000000)"},
                    "top_n": {"type": "integer", "description": "Number of results (default 20)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_narrative_coins",
            "description": "Get top coins in a specific narrative: 'AI Tokens', 'DePIN', 'Layer 2 Scaling', 'RWA', 'Meme Coins', 'ZK', 'Liquid Staking', 'GameFi', etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "narrative": {"type": "string", "description": "Narrative/sector name (e.g. 'AI Tokens', 'DePIN', 'Layer 2')"},
                    "top_n": {"type": "integer", "description": "Number of coins to return (default 15)"}
                },
                "required": ["narrative"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compare_narratives",
            "description": "Side-by-side 24h performance comparison of multiple narratives. E.g. compare AI Tokens, DePIN, RWA, Layer 2 all at once.",
            "parameters": {
                "type": "object",
                "properties": {
                    "narrative_list": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of narrative names to compare (e.g. ['AI Tokens', 'DePIN', 'RWA', 'Layer 2 Scaling'])"
                    }
                },
                "required": ["narrative_list"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_defi_tvl_momentum",
            "description": "Track DeFi protocol TVL changes: which protocols are gaining or losing total value locked - capital flow signal",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_chain_tvl_momentum",
            "description": "Which blockchain ecosystems are gaining TVL vs losing it? Leading indicator of ecosystem rotation.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_github_ecosystem_activity",
            "description": "Measure developer activity in a crypto ecosystem via GitHub. Ecosystems: solana, ethereum, ai, depin, zk, l2, defi, nft",
            "parameters": {
                "type": "object",
                "properties": {
                    "ecosystem": {"type": "string", "description": "Ecosystem to analyze: solana, ethereum, ai, depin, zk, l2, defi, nft"}
                },
                "required": ["ecosystem"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_new_listings_momentum",
            "description": "Find coins with high momentum signals: unusual volume spikes or large price moves that may indicate new emerging narratives",
            "parameters": {"type": "object", "properties": {}}
        }
    },
]

TOOL_MAP = {
    "get_global_market_pulse":     get_global_market_pulse,
    "get_trending_narratives":     get_trending_narratives,
    "get_sector_rotation":         get_sector_rotation,
    "get_trending_coins":          get_trending_coins,
    "get_volume_spikes":           get_volume_spikes,
    "get_narrative_coins":         get_narrative_coins,
    "compare_narratives":          compare_narratives,
    "get_defi_tvl_momentum":       get_defi_tvl_momentum,
    "get_chain_tvl_momentum":      get_chain_tvl_momentum,
    "get_github_ecosystem_activity": get_github_ecosystem_activity,
    "get_new_listings_momentum":   get_new_listings_momentum,
}

SYSTEM_PROMPT = """You are a crypto market intelligence analyst. Your job is to track narratives, sector rotation, trending ecosystems, and volume anomalies - and surface actionable signals.

When asked about market intelligence:
1. Call MULTIPLE tools to get a comprehensive picture
2. Cross-reference signals: e.g. a narrative trending + volume spike + TVL inflow = high-conviction signal
3. Identify the STORY behind the data - what narrative is the market pricing in?

Output format:
- Lead with the strongest signal
- Use clear sections: 🔥 Trending Narratives | 🔄 Sector Rotation | ⚡ Volume Spikes | 📊 Market Pulse | 🏗️ Ecosystem Activity
- Use emoji signals: 🟢 bullish, 🔴 bearish, 🟡 neutral, ⚡ high conviction
- Highlight cross-signal confluences (multiple indicators pointing same direction)
- Always mention which narratives are losing momentum too

Be analytical, concise, and forward-looking. Think like a macro analyst, not a price predictor."""

def call_ollama(messages: list) -> Any:
    payload = {
        "model": MODEL,
        "messages": messages,
        "tools": TOOLS,
        "stream": False,
        "options": {"temperature": 0.15}
    }
    resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()


def execute_tool(name: str, args: dict) -> str:
    fn = TOOL_MAP.get(name)
    if not fn:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        return json.dumps(fn(**args), indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


def run_agent(user_input: str, history: list) -> tuple[str, list]:
    history.append({"role": "user", "content": user_input})
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history

    for i in range(10):
        resp  = call_ollama(messages)
        msg   = resp["message"]
        calls = msg.get("tool_calls", [])

        if not calls:
            reply = msg.get("content", "")
            history.append({"role": "assistant", "content": reply})
            return reply, history

        print(f"\n  🔧 [{i+1}] {[c['function']['name'] for c in calls]}")
        messages.append({"role": "assistant", "content": msg.get("content", ""), "tool_calls": calls})

        for c in calls:
            name = c["function"]["name"]
            args = c["function"].get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            print(f"  📡 {name}({args})")
            result = execute_tool(name, args)
            print(f"  ✅ done")
            messages.append({"role": "tool", "content": result})

    return "Agent reached max iterations.", history

BANNER = r"""
╔══════════════════════════════════════════════════════════════════╗
║   📡  Market Intelligence AI Agent                              ║
║   Narratives · Rotation · Sentiment · Volume · Ecosystems       ║
╚══════════════════════════════════════════════════════════════════╝
"""

EXAMPLES = """
Example prompts:
  • What narratives are gaining momentum today?
  • Show me sector rotation - what's capital flowing into vs out of?
  • Where are the volume spikes right now?
  • Compare AI Tokens vs DePIN vs RWA vs Layer 2
  • Give me a full market intelligence briefing
  • What's happening in the Solana ecosystem?
  • Which DeFi protocols are gaining TVL the fastest?
  • Are we in altcoin season or BTC season?
  • What are the highest-conviction cross-signal narratives?
  • Show me coins with unusual volume spikes

Commands: save · clear · quit
"""


def main():
    print(BANNER)
    print(f"  Model     : {MODEL}")
    print(f"  Narratives: {len(NARRATIVE_MAP)} tracked sectors")
    print(f"  Sources   : CoinGecko · DeFiLlama · GitHub")
    print(EXAMPLES)
    print("─" * 66)

    history    = []
    last_reply = ""

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n👋 Goodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() == "quit":
            print("👋 Goodbye!")
            break
        if user_input.lower() == "clear":
            history = []
            last_reply = ""
            print("🔄 Conversation cleared.")
            continue
        if user_input.lower() == "save":
            if last_reply:
                ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
                name = f"market_intel_{ts}.md"
                with open(name, "w") as f:
                    f.write(f"# Market Intelligence Report\n*{datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n")
                    f.write(last_reply)
                print(f"  💾 Saved → {name}")
            else:
                print("  ⚠️  Nothing to save yet.")
            continue

        print("\n  📡 Scanning market signals...\n")
        try:
            reply, history = run_agent(user_input, history)
            last_reply = reply
            print(f"\n{'─'*66}")
            print(reply)
            print(f"{'─'*66}")
            print("  💡 Type 'save' to export as .md")
        except requests.exceptions.ConnectionError:
            print("  ❌ Ollama not running → ollama serve")
        except Exception as e:
            print(f"  ❌ Error: {e}")


if __name__ == "__main__":
    main()