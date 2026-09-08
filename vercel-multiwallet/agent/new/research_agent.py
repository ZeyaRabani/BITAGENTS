import json
import re
import requests
from datetime import datetime, timezone
from typing import Any

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "llama3.1"

COINGECKO_API   = "https://api.coingecko.com/api/v3"
GITHUB_API      = "https://api.github.com"
DEFILLAMA_API   = "https://api.llama.fi"

HEADERS = {"User-Agent": "ResearchAgent/1.0"}

def get_crypto_market_overview(limit: int = 10) -> dict:
    """Get top cryptocurrencies by market cap with price, volume, and change data."""
    try:
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": min(limit, 20),
            "page": 1,
            "sparkline": False,
            "price_change_percentage": "1h,24h,7d"
        }
        resp = requests.get(f"{COINGECKO_API}/coins/markets", params=params, headers=HEADERS, timeout=15)
        data = resp.json()
        coins = []
        for c in data:
            coins.append({
                "rank": c["market_cap_rank"],
                "name": c["name"],
                "symbol": c["symbol"].upper(),
                "price_usd": c["current_price"],
                "market_cap_usd": c["market_cap"],
                "volume_24h_usd": c["total_volume"],
                "change_1h_pct": c.get("price_change_percentage_1h_in_currency"),
                "change_24h_pct": c.get("price_change_percentage_24h"),
                "change_7d_pct": c.get("price_change_percentage_7d_in_currency"),
                "ath_usd": c["ath"],
                "ath_change_pct": c["ath_change_percentage"],
            })
        return {"coins": coins, "fetched_at": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        return {"error": str(e)}


def get_coin_details(coin_id: str) -> dict:
    """Get detailed data for a specific coin: description, links, dev activity, community."""
    try:
        resp = requests.get(
            f"{COINGECKO_API}/coins/{coin_id}",
            params={"localization": False, "tickers": False, "community_data": True, "developer_data": True},
            headers=HEADERS, timeout=15
        )
        d = resp.json()
        if "error" in d:
            return {"error": d["error"]}

        return {
            "name": d["name"],
            "symbol": d["symbol"].upper(),
            "categories": d.get("categories", [])[:5],
            "description": (d.get("description", {}).get("en", "") or "")[:500] + "...",
            "homepage": (d.get("links", {}).get("homepage", [""])[0] or ""),
            "github_repos": d.get("links", {}).get("repos_url", {}).get("github", [])[:2],
            "twitter_followers": d.get("community_data", {}).get("twitter_followers"),
            "reddit_subscribers": d.get("community_data", {}).get("reddit_subscribers"),
            "github_stars": d.get("developer_data", {}).get("stars"),
            "github_forks": d.get("developer_data", {}).get("forks"),
            "commit_activity_4w": d.get("developer_data", {}).get("commit_count_4_weeks"),
            "genesis_date": d.get("genesis_date"),
            "sentiment_up_pct": d.get("sentiment_votes_up_percentage"),
            "market_data": {
                "price_usd": d.get("market_data", {}).get("current_price", {}).get("usd"),
                "market_cap_usd": d.get("market_data", {}).get("market_cap", {}).get("usd"),
                "total_supply": d.get("market_data", {}).get("total_supply"),
                "circulating_supply": d.get("market_data", {}).get("circulating_supply"),
                "all_time_high_usd": d.get("market_data", {}).get("ath", {}).get("usd"),
            }
        }
    except Exception as e:
        return {"error": str(e)}


def get_defi_protocols(limit: int = 10) -> dict:
    """Get top DeFi protocols by TVL (Total Value Locked) from DeFiLlama."""
    try:
        resp = requests.get(f"{DEFILLAMA_API}/protocols", headers=HEADERS, timeout=15)
        protocols = resp.json()
        top = sorted(protocols, key=lambda x: x.get("tvl", 0), reverse=True)[:limit]
        result = []
        for p in top:
            result.append({
                "name": p.get("name"),
                "symbol": p.get("symbol", "").upper(),
                "category": p.get("category"),
                "tvl_usd": p.get("tvl"),
                "chain": p.get("chain"),
                "chains": p.get("chains", [])[:4],
                "change_1d_pct": p.get("change_1d"),
                "change_7d_pct": p.get("change_7d"),
                "mcap_tvl_ratio": round(p["mcap"] / p["tvl"], 3) if p.get("mcap") and p.get("tvl") else None,
            })
        return {"protocols": result, "total_protocols_tracked": len(protocols)}
    except Exception as e:
        return {"error": str(e)}


def get_defi_chain_tvl() -> dict:
    """Get TVL breakdown by blockchain chain from DeFiLlama."""
    try:
        resp = requests.get(f"{DEFILLAMA_API}/v2/chains", headers=HEADERS, timeout=15)
        chains = resp.json()
        top = sorted(chains, key=lambda x: x.get("tvl", 0), reverse=True)[:15]
        total_tvl = sum(c.get("tvl", 0) for c in chains)
        result = []
        for c in top:
            tvl = c.get("tvl", 0)
            result.append({
                "chain": c.get("name"),
                "tvl_usd": tvl,
                "dominance_pct": round(tvl / total_tvl * 100, 2) if total_tvl else 0,
            })
        return {"chains": result, "total_defi_tvl_usd": total_tvl}
    except Exception as e:
        return {"error": str(e)}


def get_github_project(owner: str, repo: str) -> dict:
    """Fetch GitHub project stats: stars, forks, issues, language, recent activity."""
    try:
        resp = requests.get(f"{GITHUB_API}/repos/{owner}/{repo}", headers=HEADERS, timeout=10)
        d = resp.json()
        if "message" in d:
            return {"error": d["message"]}

        # Also get recent commits
        commits_resp = requests.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/commits",
            params={"per_page": 5}, headers=HEADERS, timeout=10
        )
        recent_commits = []
        if commits_resp.status_code == 200:
            for c in commits_resp.json():
                recent_commits.append({
                    "message": c["commit"]["message"].split("\n")[0][:80],
                    "author": c["commit"]["author"]["name"],
                    "date": c["commit"]["author"]["date"][:10]
                })

        return {
            "full_name": d.get("full_name"),
            "description": d.get("description"),
            "language": d.get("language"),
            "stars": d.get("stargazers_count"),
            "forks": d.get("forks_count"),
            "open_issues": d.get("open_issues_count"),
            "watchers": d.get("watchers_count"),
            "created_at": d.get("created_at", "")[:10],
            "last_pushed": d.get("pushed_at", "")[:10],
            "topics": d.get("topics", []),
            "license": d.get("license", {}).get("name") if d.get("license") else None,
            "homepage": d.get("homepage"),
            "recent_commits": recent_commits
        }
    except Exception as e:
        return {"error": str(e)}


def search_github_projects(query: str, limit: int = 5) -> dict:
    """Search GitHub for blockchain/crypto projects matching a query."""
    try:
        params = {"q": query, "sort": "stars", "order": "desc", "per_page": limit}
        resp = requests.get(f"{GITHUB_API}/search/repositories", params=params, headers=HEADERS, timeout=10)
        data = resp.json()
        results = []
        for r in data.get("items", []):
            results.append({
                "full_name": r["full_name"],
                "description": r.get("description", "")[:100],
                "stars": r["stargazers_count"],
                "forks": r["forks_count"],
                "language": r.get("language"),
                "last_updated": r.get("updated_at", "")[:10],
                "topics": r.get("topics", [])[:5],
            })
        return {"query": query, "results": results, "total_count": data.get("total_count")}
    except Exception as e:
        return {"error": str(e)}


def get_global_market_stats() -> dict:
    """Get global crypto market statistics: total market cap, BTC dominance, volume."""
    try:
        resp = requests.get(f"{COINGECKO_API}/global", headers=HEADERS, timeout=10)
        d = resp.json().get("data", {})
        return {
            "total_market_cap_usd": d.get("total_market_cap", {}).get("usd"),
            "total_volume_24h_usd": d.get("total_volume", {}).get("usd"),
            "btc_dominance_pct": round(d.get("market_cap_percentage", {}).get("btc", 0), 2),
            "eth_dominance_pct": round(d.get("market_cap_percentage", {}).get("eth", 0), 2),
            "active_cryptocurrencies": d.get("active_cryptocurrencies"),
            "markets": d.get("markets"),
            "market_cap_change_24h_pct": d.get("market_cap_change_percentage_24h_usd"),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        return {"error": str(e)}


def get_trending_coins() -> dict:
    """Get currently trending coins on CoinGecko in the last 24 hours."""
    try:
        resp = requests.get(f"{COINGECKO_API}/search/trending", headers=HEADERS, timeout=10)
        data = resp.json()
        coins = []
        for item in data.get("coins", []):
            c = item["item"]
            coins.append({
                "rank": c.get("market_cap_rank"),
                "name": c["name"],
                "symbol": c["symbol"],
                "score": c.get("score"),
                "price_btc": c.get("price_btc"),
            })
        return {"trending_coins": coins, "as_of": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        return {"error": str(e)}


def generate_research_report(topic: str, data_summary: str) -> dict:
    """
    Signal to the agent to compile all gathered data into a structured research report.
    The agent itself produces the final markdown report.
    """
    return {
        "instruction": "compile_report",
        "topic": topic,
        "data_summary": data_summary,
        "report_sections": [
            "Executive Summary",
            "Market Overview",
            "Project Analysis",
            "On-Chain / DeFi Data",
            "Developer Activity",
            "Community & Sentiment",
            "Key Risks",
            "Conclusion"
        ]
    }

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_global_market_stats",
            "description": "Get global crypto market statistics: total market cap, BTC dominance, 24h volume, number of active coins",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_crypto_market_overview",
            "description": "Get top cryptocurrencies by market cap with price, volume, and % change data",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Number of top coins to fetch (default 10, max 20)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_coin_details",
            "description": "Get deep details for a specific coin: description, links, GitHub activity, community stats, supply data. Use CoinGecko coin IDs like 'bitcoin', 'ethereum', 'solana', 'uniswap'",
            "parameters": {
                "type": "object",
                "properties": {
                    "coin_id": {"type": "string", "description": "CoinGecko coin ID (e.g. 'bitcoin', 'ethereum', 'chainlink', 'uniswap')"}
                },
                "required": ["coin_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_trending_coins",
            "description": "Get currently trending cryptocurrencies in the last 24 hours",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_defi_protocols",
            "description": "Get top DeFi protocols ranked by Total Value Locked (TVL)",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Number of top protocols (default 10)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_defi_chain_tvl",
            "description": "Get TVL breakdown by blockchain: which chains hold the most DeFi value",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_github_project",
            "description": "Fetch detailed GitHub repository stats: stars, forks, language, recent commits, open issues",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string", "description": "GitHub repository owner/org (e.g. 'ethereum', 'solana-labs')"},
                    "repo": {"type": "string", "description": "Repository name (e.g. 'go-ethereum', 'solana')"}
                },
                "required": ["owner", "repo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_github_projects",
            "description": "Search GitHub for blockchain/crypto open-source projects",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (e.g. 'ethereum defi protocol', 'solana nft marketplace')"},
                    "limit": {"type": "integer", "description": "Number of results (default 5)"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_research_report",
            "description": "Call this after gathering all data to trigger compilation of a final structured research report",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "The research topic or project name"},
                    "data_summary": {"type": "string", "description": "Brief summary of all data gathered so far"}
                },
                "required": ["topic", "data_summary"]
            }
        }
    }
]

TOOL_MAP = {
    "get_global_market_stats": get_global_market_stats,
    "get_crypto_market_overview": get_crypto_market_overview,
    "get_coin_details": get_coin_details,
    "get_trending_coins": get_trending_coins,
    "get_defi_protocols": get_defi_protocols,
    "get_defi_chain_tvl": get_defi_chain_tvl,
    "get_github_project": get_github_project,
    "search_github_projects": search_github_projects,
    "generate_research_report": generate_research_report,
}

SYSTEM_PROMPT = """You are a professional crypto and blockchain research analyst AI. Your job is to generate thorough, structured research summaries about cryptocurrency projects, DeFi protocols, and market trends.

When asked to research a topic:
1. Call MULTIPLE tools to gather comprehensive data (market data, project details, DeFi stats, GitHub activity)
2. After gathering data, call generate_research_report to signal report compilation
3. Write a clean, structured Markdown report with sections: Executive Summary, Market Overview, Project Analysis, On-Chain/DeFi Data, Developer Activity, Community & Sentiment, Key Risks, Conclusion

Always use real data from tools. Be analytical, not promotional. Highlight both strengths and risks. Format numbers clearly (e.g. $1.2B, 34.5%). Use Markdown headers and bullet points in your final report."""

def call_ollama(messages: list) -> Any:
    payload = {
        "model": MODEL,
        "messages": messages,
        "tools": TOOLS,
        "stream": False,
        "options": {"temperature": 0.2}
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


def save_report(content: str, topic: str):
    """Save a generated report to a markdown file."""
    safe = re.sub(r"[^a-z0-9_]", "_", topic.lower())[:40]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"report_{safe}_{ts}.md"
    with open(filename, "w") as f:
        f.write(f"# Research Report: {topic}\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        f.write(content)
    return filename


def run_agent(user_input: str, conversation_history: list) -> tuple[str, list]:
    conversation_history.append({"role": "user", "content": user_input})
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + conversation_history

    max_iterations = 10
    for i in range(max_iterations):
        response = call_ollama(messages)
        message = response["message"]
        tool_calls = message.get("tool_calls", [])

        if not tool_calls:
            reply = message.get("content", "")
            conversation_history.append({"role": "assistant", "content": reply})
            return reply, conversation_history

        print(f"\n  🔧 [{i+1}] Tools: {[tc['function']['name'] for tc in tool_calls]}")
        messages.append({
            "role": "assistant",
            "content": message.get("content", ""),
            "tool_calls": tool_calls
        })

        for tc in tool_calls:
            name = tc["function"]["name"]
            args = tc["function"].get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            print(f"  📡 {name}({args})")
            result = execute_tool(name, args)
            print(f"  ✅ Done")
            messages.append({"role": "tool", "content": result})

    return "Agent reached max iterations.", conversation_history

BANNER = """
╔══════════════════════════════════════════════════════════════╗
║        📊  Crypto Research AI Agent                         ║
║        Powered by Ollama + CoinGecko + DeFiLlama + GitHub  ║
╚══════════════════════════════════════════════════════════════╝
"""

EXAMPLES = """
Example prompts:
  • Research Ethereum - give me a full report
  • Compare Solana and Avalanche
  • What are the top DeFi protocols by TVL?
  • Research Uniswap as a DeFi project
  • Give me a market overview for today
  • What's trending in crypto right now?
  • Analyze the GitHub activity of the Solana project
  • Generate a report on layer-2 scaling solutions

Commands:
  save     - Save the last report to a .md file
  clear    - Reset conversation
  quit     - Exit
"""

def main():
    print(BANNER)
    print(f"  Model : {MODEL}")
    print(f"  APIs  : CoinGecko (free), DeFiLlama (free), GitHub (free)")
    print(EXAMPLES)
    print("─" * 64)

    conversation_history = []
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
            conversation_history = []
            last_reply = ""
            print("🔄 Conversation cleared.")
            continue

        if user_input.lower() == "save":
            if last_reply:
                topic = input("  Report topic name: ").strip() or "research"
                fname = save_report(last_reply, topic)
                print(f"  💾 Saved to: {fname}")
            else:
                print("  ⚠️  No report to save yet.")
            continue

        print("\n  🤔 Researching...\n")
        try:
            reply, conversation_history = run_agent(user_input, conversation_history)
            last_reply = reply
            print(f"\n{'─'*64}")
            print(reply)
            print(f"{'─'*64}")
            print("\n  💡 Tip: type 'save' to export this report as a .md file")
        except requests.exceptions.ConnectionError:
            print("  ❌ Cannot connect to Ollama. Run: ollama serve")
        except Exception as e:
            print(f"  ❌ Error: {e}")


if __name__ == "__main__":
    main()