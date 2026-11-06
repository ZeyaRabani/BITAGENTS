import json
import time
import requests
from datetime import datetime, timezone, timedelta
from typing import Any

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL      = "llama3.1"

ETH_RPC          = "https://eth.llamarpc.com"
ETHERSCAN_API    = "https://api.etherscan.io/api"
ETHERSCAN_KEY    = "YourApiKeyToken"   # ToDo: free key → etherscan.io/apis
COINGECKO_API    = "https://api.coingecko.com/api/v3"
DEFILLAMA_API    = "https://api.llama.fi"

HEADERS = {"User-Agent": "WhaleAgent/1.0"}

WHALE_REGISTRY = {
    "smart_money": {
        "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045": "Vitalik Buterin",
        "0x220866B1A2219f40e72f5c628B65D54268cA3A9D": "Ethereum Foundation",
        "0x4B3b8C49600dB6ee0d8B26E8B46Ee8b25F38E5b3": "Paradigm Fund",
    },
    "vc": {
        "0xBE0eB53F46cd790Cd13851d5EFf43D12404d33E8": "Binance Hot Wallet",
        "0x40B38765696e3d5d8d9d834D8AaD4bB6e418E489": "Robinhood Crypto",
        "0x1cB0906955623920c86A3963593a02a405Bb97fC": "a16z Crypto",
    },
    "fund": {
        "0x8EB8a3b98659Cce290402893d0123abb75E3ab28": "Avalanche Foundation",
        "0x2FAF487A4414Fe77e2327F0bf4AE2a264a776AD2": "FTX Exchange (historic)",
        "0x3f5CE5FBFe3E9af3971dD833D26bA9b5C936f0bE": "Binance Deposit",
    },
    "influencer": {
        "0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B": "Vitalik Alt",
        "0x4976fb03C32e5B8cfe2b6cCB31c09Ba78EBaBa41": "ENS DAO",
        "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe": "Ethereum Dev Fund",
    },
}

ALL_WHALES = {addr: name for cat in WHALE_REGISTRY.values() for addr, name in cat.items()}

def _etherscan(params: dict) -> dict:
    params.setdefault("apikey", ETHERSCAN_KEY)
    try:
        r = requests.get(ETHERSCAN_API, params=params, headers=HEADERS, timeout=15)
        return r.json()
    except Exception as e:
        return {"status": "0", "message": str(e), "result": []}


def _rpc(method: str, params: list) -> Any:
    try:
        r = requests.post(ETH_RPC, json={"jsonrpc": "2.0", "method": method, "params": params, "id": 1}, timeout=10)
        return r.json().get("result")
    except Exception:
        return None


def _days_ago(days: int) -> int:
    return int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())


def _fmt_eth(wei_str: str) -> float:
    try:
        return round(int(wei_str) / 1e18, 4)
    except Exception:
        return 0.0

def _fmt_usd(val: float, decimals: int = 0) -> str:
    if val >= 1_000_000_000:
        return f"${val/1_000_000_000:.2f}B"
    if val >= 1_000_000:
        return f"${val/1_000_000:.2f}M"
    if val >= 1_000:
        return f"${val/1_000:.1f}K"
    return f"${val:.{decimals}f}"

def list_tracked_whales(category: str = "all") -> dict:
    """Return the curated whale registry, optionally filtered by category."""
    if category == "all":
        result = {}
        for cat, wallets in WHALE_REGISTRY.items():
            result[cat] = [{"address": a, "label": l} for a, l in wallets.items()]
        return {"registry": result, "total": len(ALL_WHALES)}
    cat = category.lower()
    if cat in WHALE_REGISTRY:
        wallets = WHALE_REGISTRY[cat]
        return {
            "category": cat,
            "whales": [{"address": a, "label": l} for a, l in wallets.items()],
            "count": len(wallets)
        }
    return {"error": f"Unknown category '{category}'. Choose: smart_money, vc, fund, influencer, all"}


def get_whale_eth_balance(address: str) -> dict:
    """Get ETH balance and basic profile for a known whale address."""
    label = ALL_WHALES.get(address, "Unknown Wallet")
    category = next((c for c, w in WHALE_REGISTRY.items() if address in w), "unknown")
    raw = _rpc("eth_getBalance", [address, "latest"])
    balance_eth = round(int(raw, 16) / 1e18, 4) if raw else 0
    nonce = _rpc("eth_getTransactionCount", [address, "latest"])
    tx_count = int(nonce, 16) if nonce else 0

    try:
        price_r = requests.get(f"{COINGECKO_API}/simple/price", params={"ids": "ethereum", "vs_currencies": "usd"}, timeout=8)
        eth_usd = price_r.json().get("ethereum", {}).get("usd", 0)
    except Exception:
        eth_usd = 0

    return {
        "address": address,
        "label": label,
        "category": category,
        "balance_eth": balance_eth,
        "balance_usd": _fmt_usd(balance_eth * eth_usd),
        "total_transactions": tx_count,
    }


def get_whale_recent_txs(address: str, days: int = 7, limit: int = 20) -> dict:
    """Get recent ETH transactions for a whale wallet, flagging large moves."""
    label = ALL_WHALES.get(address, address[:10] + "...")
    start_block = 0  # Etherscan filters by time via offset; we filter by timestamp below
    cutoff = _days_ago(days)

    data = _etherscan({
        "module": "account", "action": "txlist",
        "address": address, "startblock": 0, "endblock": 99999999,
        "page": 1, "offset": 50, "sort": "desc"
    })

    txs = []
    if data.get("status") == "1":
        for tx in data["result"]:
            if int(tx["timeStamp"]) < cutoff:
                break
            val_eth = _fmt_eth(tx["value"])
            if val_eth < 0.01:
                continue  # skip dust
            direction = "OUT" if tx["from"].lower() == address.lower() else "IN"
            txs.append({
                "hash": tx["hash"][:18] + "...",
                "direction": direction,
                "counterparty": tx["to"] if direction == "OUT" else tx["from"],
                "value_eth": val_eth,
                "timestamp": datetime.fromtimestamp(int(tx["timeStamp"])).strftime("%Y-%m-%d %H:%M"),
                "status": "✅" if tx.get("txreceipt_status") == "1" else "❌",
                "gas_used": tx["gasUsed"],
            })
            if len(txs) >= limit:
                break

    buys  = [t for t in txs if t["direction"] == "IN"]
    sells = [t for t in txs if t["direction"] == "OUT"]

    return {
        "address": address,
        "label": label,
        "period_days": days,
        "total_txs_found": len(txs),
        "inflows": buys,
        "outflows": sells,
        "net_eth_flow": round(sum(t["value_eth"] for t in buys) - sum(t["value_eth"] for t in sells), 4),
    }


def get_whale_token_activity(address: str, days: int = 7) -> dict:
    """Get ERC-20 token transfers for a whale: buys and sells."""
    label = ALL_WHALES.get(address, address[:10] + "...")
    cutoff = _days_ago(days)

    data = _etherscan({
        "module": "account", "action": "tokentx",
        "address": address, "page": 1, "offset": 100, "sort": "desc"
    })

    token_summary: dict[str, dict] = {}

    if data.get("status") == "1":
        for tx in data["result"]:
            if int(tx["timeStamp"]) < cutoff:
                continue
            symbol   = tx["tokenSymbol"] or "???"
            decimals = int(tx["tokenDecimal"]) if tx["tokenDecimal"] else 18
            amount   = int(tx["value"]) / (10 ** decimals)
            direction = "SELL" if tx["from"].lower() == address.lower() else "BUY"
            ts = datetime.fromtimestamp(int(tx["timeStamp"])).strftime("%Y-%m-%d %H:%M")

            if symbol not in token_summary:
                token_summary[symbol] = {
                    "symbol": symbol,
                    "name": tx.get("tokenName", ""),
                    "contract": tx["contractAddress"],
                    "buys": 0, "sells": 0,
                    "total_bought": 0.0, "total_sold": 0.0,
                    "last_tx": ts,
                }
            if direction == "BUY":
                token_summary[symbol]["buys"] += 1
                token_summary[symbol]["total_bought"] += amount
            else:
                token_summary[symbol]["sells"] += 1
                token_summary[symbol]["total_sold"] += amount
            token_summary[symbol]["last_tx"] = ts

    tokens = sorted(token_summary.values(), key=lambda x: x["buys"] + x["sells"], reverse=True)[:20]
    return {
        "address": address,
        "label": label,
        "period_days": days,
        "unique_tokens": len(token_summary),
        "tokens": tokens,
        "top_buys":  [t for t in tokens if t["buys"] > t["sells"]][:5],
        "top_sells": [t for t in tokens if t["sells"] > t["buys"]][:5],
    }


def get_conviction_trades(address: str, days: int = 30) -> dict:
    """
    Identify conviction trades: tokens the whale has bought multiple times
    without selling - a signal of strong conviction.
    """
    label = ALL_WHALES.get(address, address[:10] + "...")
    cutoff = _days_ago(days)

    data = _etherscan({
        "module": "account", "action": "tokentx",
        "address": address, "page": 1, "offset": 200, "sort": "desc"
    })

    tokens: dict[str, dict] = {}
    if data.get("status") == "1":
        for tx in data["result"]:
            if int(tx["timeStamp"]) < cutoff:
                continue
            sym = tx["tokenSymbol"] or "???"
            decimals = int(tx["tokenDecimal"]) if tx["tokenDecimal"] else 18
            amount = int(tx["value"]) / (10 ** decimals)
            direction = "SELL" if tx["from"].lower() == address.lower() else "BUY"

            if sym not in tokens:
                tokens[sym] = {"symbol": sym, "name": tx.get("tokenName", ""),
                               "buys": 0, "sells": 0, "buy_amount": 0.0, "sell_amount": 0.0,
                               "contract": tx["contractAddress"]}
            tokens[sym]["buys" if direction == "BUY" else "sells"] += 1
            tokens[sym]["buy_amount" if direction == "BUY" else "sell_amount"] += amount

    conviction = [
        t for t in tokens.values()
        if t["buys"] >= 2 and t["sells"] < t["buys"]
    ]
    conviction.sort(key=lambda x: x["buys"], reverse=True)

    return {
        "address": address,
        "label": label,
        "period_days": days,
        "conviction_positions": conviction[:10],
        "total_found": len(conviction),
        "note": "Tokens with 2+ buys and fewer sells than buys - whale is accumulating."
    }


def scan_category_activity(category: str, days: int = 7) -> dict:
    """
    Scan ALL wallets in a category (smart_money / vc / fund / influencer)
    and aggregate their token activity to find consensus buys/sells.
    """
    if category not in WHALE_REGISTRY:
        return {"error": f"Unknown category. Choose: {list(WHALE_REGISTRY.keys())}"}

    wallets = WHALE_REGISTRY[category]
    consensus_tokens: dict[str, dict] = {}
    wallet_results = []

    for addr, label in wallets.items():
        print(f"    ↳ scanning {label}...")
        time.sleep(0.3)
        data = _etherscan({
            "module": "account", "action": "tokentx",
            "address": addr, "page": 1, "offset": 50, "sort": "desc"
        })
        cutoff = _days_ago(days)
        wallet_buys = set()
        wallet_sells = set()

        if data.get("status") == "1":
            for tx in data["result"]:
                if int(tx["timeStamp"]) < cutoff:
                    continue
                sym = tx["tokenSymbol"] or "???"
                direction = "SELL" if tx["from"].lower() == addr.lower() else "BUY"
                if sym not in consensus_tokens:
                    consensus_tokens[sym] = {
                        "symbol": sym, "name": tx.get("tokenName", ""),
                        "contract": tx["contractAddress"],
                        "whales_buying": [], "whales_selling": [], "buy_count": 0, "sell_count": 0
                    }
                if direction == "BUY" and sym not in wallet_buys:
                    consensus_tokens[sym]["whales_buying"].append(label)
                    consensus_tokens[sym]["buy_count"] += 1
                    wallet_buys.add(sym)
                elif direction == "SELL" and sym not in wallet_sells:
                    consensus_tokens[sym]["whales_selling"].append(label)
                    consensus_tokens[sym]["sell_count"] += 1
                    wallet_sells.add(sym)

        wallet_results.append({"label": label, "address": addr, "tokens_bought": len(wallet_buys), "tokens_sold": len(wallet_sells)})

    top_buys  = sorted(consensus_tokens.values(), key=lambda x: x["buy_count"],  reverse=True)[:10]
    top_sells = sorted(consensus_tokens.values(), key=lambda x: x["sell_count"], reverse=True)[:10]

    return {
        "category": category,
        "wallets_scanned": len(wallets),
        "period_days": days,
        "wallet_summary": wallet_results,
        "consensus_buys":  top_buys,
        "consensus_sells": top_sells,
        "total_unique_tokens": len(consensus_tokens),
    }


def get_portfolio_snapshot(address: str) -> dict:
    """
    Get a whale's current portfolio: ETH balance + all ERC-20 tokens
    they have received (approximation via token transfer history).
    """
    label = ALL_WHALES.get(address, address[:10] + "...")

    raw = _rpc("eth_getBalance", [address, "latest"])
    eth_bal = round(int(raw, 16) / 1e18, 4) if raw else 0

    data = _etherscan({
        "module": "account", "action": "tokentx",
        "address": address, "page": 1, "offset": 200, "sort": "desc"
    })

    holdings: dict[str, dict] = {}
    if data.get("status") == "1":
        for tx in data["result"]:
            sym = tx["tokenSymbol"] or "???"
            decimals = int(tx["tokenDecimal"]) if tx["tokenDecimal"] else 18
            amount = int(tx["value"]) / (10 ** decimals)
            direction = "OUT" if tx["from"].lower() == address.lower() else "IN"

            if sym not in holdings:
                holdings[sym] = {"symbol": sym, "name": tx.get("tokenName", ""),
                                 "net_amount": 0.0, "contract": tx["contractAddress"]}
            holdings[sym]["net_amount"] += amount if direction == "IN" else -amount

    active = {k: v for k, v in holdings.items() if v["net_amount"] > 0}
    sorted_holdings = sorted(active.values(), key=lambda x: x["net_amount"], reverse=True)[:15]

    return {
        "address": address,
        "label": label,
        "eth_balance": eth_bal,
        "token_positions": sorted_holdings,
        "total_tokens_held": len(active),
        "note": "Net token amounts based on transfer history. Does not reflect current USD values without price data."
    }


def compare_whale_portfolios(addresses: list) -> dict:
    """Compare portfolios of multiple whale addresses to find common holdings."""
    if len(addresses) > 5:
        addresses = addresses[:5]

    all_holdings: dict[str, list] = {}
    profiles = []

    for addr in addresses:
        label = ALL_WHALES.get(addr, addr[:10] + "...")
        snap = get_portfolio_snapshot(addr)
        syms = {t["symbol"] for t in snap.get("token_positions", [])}
        profiles.append({"address": addr, "label": label, "tokens": list(syms)})
        for sym in syms:
            all_holdings.setdefault(sym, []).append(label)

    shared = {k: v for k, v in all_holdings.items() if len(v) > 1}
    shared_sorted = sorted(shared.items(), key=lambda x: len(x[1]), reverse=True)[:10]

    return {
        "wallets_compared": len(addresses),
        "profiles": profiles,
        "shared_holdings": [{"symbol": s, "held_by": h, "whale_count": len(h)} for s, h in shared_sorted],
        "note": "Shared holdings may signal a high-conviction trade among whales."
    }


def add_custom_whale(address: str, label: str, category: str) -> dict:
    """Add a new wallet to the in-session whale registry."""
    if category not in WHALE_REGISTRY:
        return {"error": f"Invalid category. Use: {list(WHALE_REGISTRY.keys())}"}
    WHALE_REGISTRY[category][address] = label
    ALL_WHALES[address] = label
    return {"status": "added", "address": address, "label": label, "category": category}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_tracked_whales",
            "description": "List all tracked whale wallets, optionally filtered by category (smart_money, vc, fund, influencer)",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Category filter: all, smart_money, vc, fund, influencer"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_whale_eth_balance",
            "description": "Get ETH balance and profile for a specific whale address",
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {"type": "string", "description": "Ethereum wallet address"}
                },
                "required": ["address"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_whale_recent_txs",
            "description": "Get recent ETH inflows and outflows for a whale wallet over N days",
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {"type": "string"},
                    "days":    {"type": "integer", "description": "Lookback window in days (default 7)"},
                    "limit":   {"type": "integer", "description": "Max transactions to return (default 20)"}
                },
                "required": ["address"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_whale_token_activity",
            "description": "Get ERC-20 token buys and sells for a whale address over N days",
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {"type": "string"},
                    "days":    {"type": "integer", "description": "Lookback window in days (default 7)"}
                },
                "required": ["address"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_conviction_trades",
            "description": "Find tokens a whale has bought multiple times without selling - signals of high conviction / accumulation",
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {"type": "string"},
                    "days":    {"type": "integer", "description": "Lookback window (default 30 days)"}
                },
                "required": ["address"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scan_category_activity",
            "description": "Scan ALL wallets in a category and find consensus buys/sells - which tokens are smart money collectively buying or selling",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "smart_money | vc | fund | influencer"},
                    "days":     {"type": "integer", "description": "Lookback window in days (default 7)"}
                },
                "required": ["category"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_portfolio_snapshot",
            "description": "Get a whale's current portfolio: ETH balance and estimated token holdings based on transfer history",
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {"type": "string"}
                },
                "required": ["address"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compare_whale_portfolios",
            "description": "Compare portfolios of multiple whale addresses to find shared/common holdings",
            "parameters": {
                "type": "object",
                "properties": {
                    "addresses": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of whale wallet addresses to compare (max 5)"
                    }
                },
                "required": ["addresses"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_custom_whale",
            "description": "Add a new wallet address to the in-session whale registry for tracking",
            "parameters": {
                "type": "object",
                "properties": {
                    "address":  {"type": "string", "description": "Ethereum wallet address"},
                    "label":    {"type": "string", "description": "Human-readable name/label"},
                    "category": {"type": "string", "description": "smart_money | vc | fund | influencer"}
                },
                "required": ["address", "label", "category"]
            }
        }
    }
]

TOOL_MAP = {
    "list_tracked_whales":       list_tracked_whales,
    "get_whale_eth_balance":     get_whale_eth_balance,
    "get_whale_recent_txs":      get_whale_recent_txs,
    "get_whale_token_activity":  get_whale_token_activity,
    "get_conviction_trades":     get_conviction_trades,
    "scan_category_activity":    scan_category_activity,
    "get_portfolio_snapshot":    get_portfolio_snapshot,
    "compare_whale_portfolios":  compare_whale_portfolios,
    "add_custom_whale":          add_custom_whale,
}

SYSTEM_PROMPT = """You are a professional on-chain whale tracking analyst. You monitor smart money, VC, fund, and influencer wallets to surface actionable trading signals.

Your job:
- Track wallet activity: ETH flows, token buys/sells, portfolio changes
- Identify conviction trades: repeated buys with no sells = accumulation signal
- Surface consensus trades: when multiple whales buy the same token = strong signal
- Detect distribution: when whales start selling previously held tokens

When a user asks about whale activity:
1. Use the appropriate tools to gather real on-chain data
2. Call multiple tools when needed (e.g., scan category + get conviction trades)
3. Present findings clearly: label wallets, show direction (BUY/SELL), flag patterns

Format your output with clear sections, emoji signals (🐳 whale, 🟢 buy, 🔴 sell, ⚡ conviction, 📊 portfolio), and concise bullet points. Always note the time window and flag any unusual activity."""

def call_ollama(messages: list) -> Any:
    payload = {
        "model": MODEL,
        "messages": messages,
        "tools": TOOLS,
        "stream": False,
        "options": {"temperature": 0.1}
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
        resp = call_ollama(messages)
        msg  = resp["message"]
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
╔═══════════════════════════════════════════════════════════════╗
║   🐳  Whale Tracking AI Agent                                ║
║   Smart Money · VC · Funds · Influencers                     ║
╚═══════════════════════════════════════════════════════════════╝
"""

EXAMPLES = """
Example prompts:
  • Show all tracked whales
  • What has Vitalik bought this week?
  • Scan all VC wallets for consensus buys in the last 7 days
  • What are the conviction trades for 0xd8dA6BF...?
  • Get portfolio snapshot for all smart_money wallets
  • Compare portfolios of these 3 addresses: 0x... 0x... 0x...
  • What tokens are fund wallets selling right now?
  • Add wallet 0x1234... as "Jump Crypto" in the vc category

Commands: save · clear · quit
"""

def main():
    print(BANNER)
    print(f"  Model  : {MODEL}")
    print(f"  Whales : {len(ALL_WHALES)} tracked across 4 categories")
    print(f"  Chain  : Ethereum Mainnet")
    print(EXAMPLES)
    print("─" * 65)

    history   = []
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
                from datetime import datetime
                import re
                ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
                name = f"whale_report_{ts}.md"
                with open(name, "w") as f:
                    f.write(f"# Whale Tracking Report\n*{datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n")
                    f.write(last_reply)
                print(f"  💾 Saved to: {name}")
            else:
                print("  ⚠️  Nothing to save yet.")
            continue

        print("\n  🔍 Scanning on-chain activity...\n")
        try:
            reply, history = run_agent(user_input, history)
            last_reply = reply
            print(f"\n{'─'*65}")
            print(reply)
            print(f"{'─'*65}")
            print("  💡 Type 'save' to export this as a .md report")
        except requests.exceptions.ConnectionError:
            print("  ❌ Ollama not running. Start with: ollama serve")
        except Exception as e:
            print(f"  ❌ Error: {e}")


if __name__ == "__main__":
    main()