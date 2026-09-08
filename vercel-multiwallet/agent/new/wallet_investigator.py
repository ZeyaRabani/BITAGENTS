import json
import time
import requests
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from typing import Any

OLLAMA_URL    = "http://localhost:11434/api/chat"
MODEL         = "llama3.1"

ETH_RPC       = "https://eth.llamarpc.com"
ETHERSCAN_API = "https://api.etherscan.io/api"
ETHERSCAN_KEY = "YourApiKeyToken"   # ToDo: free → etherscan.io/apis
COINGECKO_API = "https://api.coingecko.com/api/v3"

HEADERS = {"User-Agent": "WalletInvestigator/1.0"}

KNOWN_CONTRACTS = {
    "0x7a250d5630b4cf539739df2c5dacb4c659f2488d": "Uniswap V2 Router",
    "0xe592427a0aece92de3edee1f18e0157c05861564": "Uniswap V3 Router",
    "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45": "Uniswap Universal Router",
    "0xd9e1ce17f2641f24ae83637ab66a2cca9c378b9f": "SushiSwap Router",
    "0x1111111254fb6c44bac0bed2854e76f90643097d": "1inch V4",
    "0x1111111254eeb25477b68fb85ed929f73a960582": "1inch V5",
    "0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad": "Uniswap Universal Router 2",
    "0x00000000219ab540356cbb839cbe05303d7705fa": "ETH2 Deposit Contract",
    "0xae7ab96520de3a18e5e111b5eaab095312d7fe84": "Lido stETH",
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": "USDC",
    "0xdac17f958d2ee523a2206206994597c13d831ec7": "USDT",
    "0x6b175474e89094c44da98b954eedeac495271d0f": "DAI",
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": "WETH",
    "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": "WBTC",
    "0xba12222222228d8ba445958a75a0704d566bf2c8": "Balancer Vault",
    "0xdef1c0ded9bec7f1a1670819833240f027b25eff": "0x Exchange Proxy",
}

def _etherscan(params: dict) -> dict:
    params.setdefault("apikey", ETHERSCAN_KEY)
    try:
        r = requests.get(ETHERSCAN_API, params=params, headers=HEADERS, timeout=15)
        return r.json()
    except Exception as e:
        return {"status": "0", "message": str(e), "result": []}


def _rpc(method: str, params: list) -> Any:
    try:
        r = requests.post(ETH_RPC,
            json={"jsonrpc": "2.0", "method": method, "params": params, "id": 1},
            timeout=10)
        return r.json().get("result")
    except Exception:
        return None


def _eth_price() -> float:
    try:
        r = requests.get(f"{COINGECKO_API}/simple/price",
            params={"ids": "ethereum", "vs_currencies": "usd"}, timeout=8)
        return r.json().get("ethereum", {}).get("usd", 2000)
    except Exception:
        return 2000


def _label(addr: str) -> str:
    return KNOWN_CONTRACTS.get(addr.lower(), addr[:8] + "..." + addr[-4:])


def _fmt_eth(wei_str: str) -> float:
    try:
        return round(int(wei_str) / 1e18, 6)
    except Exception:
        return 0.0


def _ago(ts: int) -> str:
    delta = datetime.now(timezone.utc) - datetime.fromtimestamp(ts, timezone.utc)
    d = delta.days
    if d == 0:
        h = delta.seconds // 3600
        return f"{h}h ago" if h else f"{delta.seconds//60}m ago"
    if d < 30:  return f"{d}d ago"
    if d < 365: return f"{d//30}mo ago"
    return f"{d//365}y ago"

def get_wallet_identity(address: str) -> dict:
    """
    Build a basic identity profile: ETH balance, age, total tx count,
    first/last activity, ENS name if any.
    """
    eth_price = _eth_price()

    raw = _rpc("eth_getBalance", [address, "latest"])
    balance_eth = round(int(raw, 16) / 1e18, 4) if raw else 0

    nonce_raw = _rpc("eth_getTransactionCount", [address, "latest"])
    tx_count = int(nonce_raw, 16) if nonce_raw else 0

    first_tx_data = _etherscan({
        "module": "account", "action": "txlist",
        "address": address, "startblock": 0, "endblock": 99999999,
        "page": 1, "offset": 1, "sort": "asc"
    })
    first_tx = None
    wallet_age_days = None
    if first_tx_data.get("status") == "1" and first_tx_data.get("result"):
        ts = int(first_tx_data["result"][0]["timeStamp"])
        first_tx = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        wallet_age_days = (datetime.now() - datetime.fromtimestamp(ts)).days

    last_tx_data = _etherscan({
        "module": "account", "action": "txlist",
        "address": address, "page": 1, "offset": 1, "sort": "desc"
    })
    last_active = None
    if last_tx_data.get("status") == "1" and last_tx_data.get("result"):
        ts = int(last_tx_data["result"][0]["timeStamp"])
        last_active = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")

    code = _rpc("eth_getCode", [address, "latest"])
    is_contract = code and code != "0x"

    return {
        "address":        address,
        "balance_eth":    balance_eth,
        "balance_usd":    f"${balance_eth * eth_price:,.0f}",
        "total_tx_sent":  tx_count,
        "first_tx_date":  first_tx,
        "last_active":    last_active,
        "wallet_age_days": wallet_age_days,
        "is_contract":    is_contract,
        "type":           "Smart Contract" if is_contract else "EOA (Externally Owned)",
    }


def analyze_trading_behavior(address: str, limit: int = 100) -> dict:
    """
    Classify the wallet's trading style by analyzing transaction patterns:
    - DEX usage (DeFi trader vs simple transfer wallet)
    - Average trade size
    - Trade frequency
    - Hold duration proxy
    - Gas usage patterns (high gas = aggressive/sniper)
    - Day/night activity distribution
    """
    data = _etherscan({
        "module": "account", "action": "txlist",
        "address": address, "page": 1, "offset": limit, "sort": "desc"
    })

    if data.get("status") != "1" or not data.get("result"):
        return {"error": "No transaction history found"}

    txs = data["result"]
    outgoing = [t for t in txs if t["from"].lower() == address.lower()]

    dex_txs = [t for t in outgoing if t.get("to", "").lower() in KNOWN_CONTRACTS]
    dex_names = [KNOWN_CONTRACTS[t["to"].lower()] for t in dex_txs]
    dex_freq = defaultdict(int)
    for n in dex_names:
        dex_freq[n] += 1

    values_eth = [_fmt_eth(t["value"]) for t in outgoing if int(t["value"]) > 0]
    avg_tx_eth = round(sum(values_eth) / len(values_eth), 4) if values_eth else 0
    max_tx_eth = round(max(values_eth), 4) if values_eth else 0

    gas_prices = [int(t["gasPrice"]) / 1e9 for t in outgoing]
    avg_gas_gwei = round(sum(gas_prices) / len(gas_prices), 1) if gas_prices else 0
    max_gas_gwei = round(max(gas_prices), 1) if gas_prices else 0

    hourly = defaultdict(int)
    for t in outgoing:
        h = datetime.fromtimestamp(int(t["timeStamp"]), timezone.utc).hour
        hourly[h] += 1
    peak_hour = max(hourly, key=hourly.get) if hourly else 0
    peak_label = f"{peak_hour:02d}:00–{(peak_hour+1)%24:02d}:00 UTC"

    if len(txs) >= 2:
        span_days = (int(txs[0]["timeStamp"]) - int(txs[-1]["timeStamp"])) / 86400
        tx_per_day = round(len(outgoing) / max(span_days, 1), 2)
    else:
        tx_per_day = 0

    failed = [t for t in outgoing if t.get("isError") == "1"]
    fail_pct = round(len(failed) / max(len(outgoing), 1) * 100, 1)

    if len(dex_txs) / max(len(outgoing), 1) > 0.6 and avg_gas_gwei > 50:
        style = "🤖 MEV / Sniper Bot"
    elif len(dex_txs) / max(len(outgoing), 1) > 0.5:
        style = "📈 Active DeFi Trader"
    elif tx_per_day > 5:
        style = "⚡ High-Frequency Trader"
    elif avg_tx_eth > 10:
        style = "🐳 Whale / OTC Mover"
    elif tx_per_day < 0.1:
        style = "💎 Long-Term Holder / HODLer"
    else:
        style = "👤 Regular User"

    return {
        "address":           address,
        "txs_analyzed":      len(txs),
        "outgoing_txs":      len(outgoing),
        "trading_style":     style,
        "dex_interactions":  len(dex_txs),
        "dex_breakdown":     dict(dex_freq),
        "avg_tx_size_eth":   avg_tx_eth,
        "max_tx_size_eth":   max_tx_eth,
        "avg_gas_gwei":      avg_gas_gwei,
        "max_gas_gwei":      max_gas_gwei,
        "txs_per_day":       tx_per_day,
        "failed_tx_pct":     fail_pct,
        "peak_activity":     peak_label,
        "notes": {
            "high_fail_rate":  fail_pct > 20,
            "uses_dex":        len(dex_txs) > 0,
            "aggressive_gas":  max_gas_gwei > 200,
        }
    }


def analyze_profitability(address: str, days: int = 90) -> dict:
    """
    Estimate wallet profitability by analyzing ETH inflows vs outflows,
    token buy/sell patterns, and net position change over time.
    """
    eth_price = _eth_price()
    cutoff = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())

    eth_data = _etherscan({
        "module": "account", "action": "txlist",
        "address": address, "page": 1, "offset": 200, "sort": "desc"
    })

    inflow_eth  = 0.0
    outflow_eth = 0.0
    tx_count    = 0

    if eth_data.get("status") == "1":
        for tx in eth_data["result"]:
            if int(tx["timeStamp"]) < cutoff:
                continue
            val = _fmt_eth(tx["value"])
            gas_cost = int(tx["gasUsed"]) * int(tx["gasPrice"]) / 1e18 if tx.get("gasUsed") else 0
            if tx["to"].lower() == address.lower():
                inflow_eth += val
            else:
                outflow_eth += val + gas_cost
            tx_count += 1

    net_eth = round(inflow_eth - outflow_eth, 4)

    tok_data = _etherscan({
        "module": "account", "action": "tokentx",
        "address": address, "page": 1, "offset": 200, "sort": "desc"
    })

    tokens: dict[str, dict] = {}
    if tok_data.get("status") == "1":
        for tx in tok_data["result"]:
            if int(tx["timeStamp"]) < cutoff:
                continue
            sym = tx["tokenSymbol"] or "???"
            dec = int(tx["tokenDecimal"]) if tx["tokenDecimal"] else 18
            amt = int(tx["value"]) / (10 ** dec)
            direction = "OUT" if tx["from"].lower() == address.lower() else "IN"
            if sym not in tokens:
                tokens[sym] = {"symbol": sym, "in": 0.0, "out": 0.0, "txs": 0}
            tokens[sym]["in" if direction == "IN" else "out"] += amt
            tokens[sym]["txs"] += 1

    net_positions = []
    for sym, t in tokens.items():
        net = t["in"] - t["out"]
        net_positions.append({
            "symbol": sym,
            "received":  round(t["in"],  4),
            "sent":      round(t["out"], 4),
            "net":       round(net,      4),
            "txs":       t["txs"],
            "status":    "Accumulating" if net > 0 else "Distributing" if net < 0 else "Neutral",
        })
    net_positions.sort(key=lambda x: abs(x["net"]), reverse=True)

    return {
        "address":         address,
        "period_days":     days,
        "txs_analyzed":    tx_count,
        "eth_inflow":      round(inflow_eth,  4),
        "eth_outflow":     round(outflow_eth, 4),
        "net_eth_pnl":     net_eth,
        "net_eth_usd":     f"${net_eth * eth_price:,.0f}",
        "eth_roi_pct":     round(net_eth / max(outflow_eth, 0.0001) * 100, 1),
        "unique_tokens":   len(tokens),
        "top_positions":   net_positions[:10],
        "profitable":      net_eth > 0,
        "note": "ROI is ETH net flow based. Token USD P&L requires historical prices not available on free APIs.",
    }


def find_connected_wallets(address: str, depth: int = 1) -> dict:
    """
    Map connected wallets by finding frequent counterparties in transaction history.
    Depth 1 = direct connections. Flags potential cluster/team wallets.
    """
    data = _etherscan({
        "module": "account", "action": "txlist",
        "address": address, "page": 1, "offset": 200, "sort": "desc"
    })

    if data.get("status") != "1":
        return {"error": "Could not fetch transaction history"}

    counterparty_count: dict[str, int] = defaultdict(int)
    counterparty_volume: dict[str, float] = defaultdict(float)

    for tx in data["result"]:
        val  = _fmt_eth(tx["value"])
        frm  = tx["from"].lower()
        to   = tx.get("to", "").lower()
        peer = to if frm == address.lower() else frm
        if not peer or peer == address.lower():
            continue
        if peer in KNOWN_CONTRACTS:
            continue
        counterparty_count[peer]  += 1
        counterparty_volume[peer] += val

    sorted_peers = sorted(counterparty_count.items(), key=lambda x: x[1], reverse=True)[:15]

    connections = []
    for peer, count in sorted_peers:
        connections.append({
            "address":      peer,
            "label":        KNOWN_CONTRACTS.get(peer, peer[:8] + "..." + peer[-4:]),
            "interactions": count,
            "total_eth":    round(counterparty_volume[peer], 4),
            "type":         "Smart Contract" if peer in KNOWN_CONTRACTS else "Wallet",
        })

    high_freq = [c for c in connections if c["interactions"] >= 5]

    return {
        "address":          address,
        "total_unique_peers": len(counterparty_count),
        "top_connections":  connections,
        "likely_related_wallets": high_freq,
        "note": "Wallets with 5+ interactions may be team wallets, deployers, or related fund addresses.",
    }


def analyze_token_timing(address: str) -> dict:
    """
    Analyze how early the wallet enters token positions:
    - Time between token contract deploy and first buy
    - Average entry timing vs broader market
    Surfaces if wallet is an early-stage insider or late retail.
    """
    tok_data = _etherscan({
        "module": "account", "action": "tokentx",
        "address": address, "page": 1, "offset": 200, "sort": "asc"
    })

    if tok_data.get("status") != "1":
        return {"error": "No token history found"}

    first_buys: dict[str, dict] = {}
    for tx in tok_data["result"]:
        if tx["from"].lower() == address.lower():
            continue  # skip sells
        contract = tx["contractAddress"].lower()
        ts       = int(tx["timeStamp"])
        sym      = tx["tokenSymbol"] or "???"
        if contract not in first_buys:
            first_buys[contract] = {
                "symbol":     sym,
                "contract":   contract,
                "first_buy":  datetime.fromtimestamp(ts).strftime("%Y-%m-%d"),
                "ts":         ts,
            }

    timing_analysis = []
    for contract, info in list(first_buys.items())[:20]:
        deploy_data = _etherscan({
            "module": "account", "action": "txlist",
            "address": contract, "page": 1, "offset": 1, "sort": "asc"
        })
        deploy_ts = None
        if deploy_data.get("status") == "1" and deploy_data.get("result"):
            deploy_ts = int(deploy_data["result"][0]["timeStamp"])

        days_after_deploy = None
        if deploy_ts:
            days_after_deploy = max(0, (info["ts"] - deploy_ts) // 86400)

        timing_analysis.append({
            "symbol":             info["symbol"],
            "first_buy_date":     info["first_buy"],
            "days_after_deploy":  days_after_deploy,
            "timing_label": (
                "🎯 Pre-launch / Insider" if days_after_deploy is not None and days_after_deploy < 1 else
                "⚡ Very Early (day 1–7)"  if days_after_deploy is not None and days_after_deploy < 7  else
                "🌱 Early (1–4 weeks)"    if days_after_deploy is not None and days_after_deploy < 30  else
                "📈 Momentum (1–3 months)" if days_after_deploy is not None and days_after_deploy < 90  else
                "🐢 Late / Retail"        if days_after_deploy is not None else "Unknown"
            ),
        })
        time.sleep(0.15)

    early_entries   = [t for t in timing_analysis if t["days_after_deploy"] is not None and t["days_after_deploy"] < 7]
    insider_entries = [t for t in timing_analysis if t["days_after_deploy"] is not None and t["days_after_deploy"] < 1]

    avg_days = None
    valid = [t["days_after_deploy"] for t in timing_analysis if t["days_after_deploy"] is not None]
    if valid:
        avg_days = round(sum(valid) / len(valid), 1)

    return {
        "address":            address,
        "tokens_analyzed":    len(timing_analysis),
        "avg_days_after_deploy": avg_days,
        "early_entries_count": len(early_entries),
        "insider_entries":    insider_entries,
        "timing_breakdown":   timing_analysis[:15],
        "profile":   (
            "🚨 Likely Insider / Dev Wallet" if len(insider_entries) > 2 else
            "🎯 Smart Early Buyer"           if len(early_entries) > 3    else
            "📊 Mixed / Momentum Trader"     if avg_days and avg_days < 60  else
            "🐢 Late Mover / Retail"
        ),
    }


def compute_roi_explanation(address: str, days: int = 90) -> dict:
    """
    Explain the sources of a wallet's ROI:
    - Which tokens drove the most volume
    - ETH accumulation vs distribution
    - Most active protocols
    - Best and worst trades by volume
    Designed to answer "why does this wallet have X% ROI?"
    """
    eth_price = _eth_price()
    cutoff = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())

    tok_data = _etherscan({
        "module": "account", "action": "tokentx",
        "address": address, "page": 1, "offset": 500, "sort": "desc"
    })

    eth_data = _etherscan({
        "module": "account", "action": "txlist",
        "address": address, "page": 1, "offset": 200, "sort": "desc"
    })

    token_volume: dict[str, dict] = {}
    if tok_data.get("status") == "1":
        for tx in tok_data["result"]:
            if int(tx["timeStamp"]) < cutoff:
                continue
            sym = tx["tokenSymbol"] or "???"
            dec = int(tx["tokenDecimal"]) if tx["tokenDecimal"] else 18
            amt = int(tx["value"]) / (10 ** dec)
            direction = "sell" if tx["from"].lower() == address.lower() else "buy"
            if sym not in token_volume:
                token_volume[sym] = {"symbol": sym, "buys": 0, "sells": 0,
                                     "buy_amt": 0.0, "sell_amt": 0.0, "tx_count": 0}
            token_volume[sym][f"{direction}s"] += 1
            token_volume[sym][f"{direction}_amt"] += amt
            token_volume[sym]["tx_count"] += 1

    protocol_freq: dict[str, int] = defaultdict(int)
    eth_in = 0.0
    eth_out = 0.0
    if eth_data.get("status") == "1":
        for tx in eth_data["result"]:
            if int(tx["timeStamp"]) < cutoff:
                continue
            val = _fmt_eth(tx["value"])
            to  = tx.get("to", "").lower()
            if to in KNOWN_CONTRACTS:
                protocol_freq[KNOWN_CONTRACTS[to]] += 1
            if tx["to"].lower() == address.lower():
                eth_in  += val
            else:
                eth_out += val

    net_eth = eth_in - eth_out
    most_traded = sorted(token_volume.values(), key=lambda x: x["tx_count"], reverse=True)[:8]

    conviction = [t for t in token_volume.values() if t["buys"] >= 2 and t["sells"] == 0]

    return {
        "address":         address,
        "period_days":     days,
        "net_eth":         round(net_eth, 4),
        "net_eth_usd":     f"${net_eth * eth_price:,.0f}",
        "eth_inflow":      round(eth_in, 4),
        "eth_outflow":     round(eth_out, 4),
        "most_traded_tokens": most_traded,
        "conviction_holds":   conviction[:5],
        "protocol_usage":  dict(sorted(protocol_freq.items(), key=lambda x: x[1], reverse=True)[:8]),
        "roi_drivers": [
            f"Net ETH gain of {round(net_eth,2)} ETH (≈ ${net_eth*eth_price:,.0f})",
            f"Traded {len(token_volume)} unique tokens over {days} days",
            f"Top protocol: {max(protocol_freq, key=protocol_freq.get, default='N/A')}",
            f"{len(conviction)} conviction holds (bought multiple times, never sold)",
        ]
    }


def detect_wallet_archetype(address: str) -> dict:
    """
    Synthesize all signals into a final wallet archetype classification.
    Combines: trade frequency, gas behavior, DEX usage, token timing, ETH balance.
    """
    eth_price = _eth_price()

    raw = _rpc("eth_getBalance", [address, "latest"])
    balance_eth = round(int(raw, 16) / 1e18, 4) if raw else 0

    data = _etherscan({
        "module": "account", "action": "txlist",
        "address": address, "page": 1, "offset": 50, "sort": "desc"
    })

    dex_count     = 0
    high_gas_count = 0
    fail_count    = 0
    tx_total      = 0
    eth_moved     = 0.0

    if data.get("status") == "1":
        for tx in data["result"]:
            if tx["from"].lower() != address.lower():
                continue
            tx_total += 1
            val = _fmt_eth(tx["value"])
            eth_moved += val
            gas_gwei = int(tx["gasPrice"]) / 1e9
            if tx.get("to", "").lower() in KNOWN_CONTRACTS:
                dex_count += 1
            if gas_gwei > 100:
                high_gas_count += 1
            if tx.get("isError") == "1":
                fail_count += 1

    dex_ratio  = dex_count / max(tx_total, 1)
    gas_ratio  = high_gas_count / max(tx_total, 1)
    fail_ratio = fail_count / max(tx_total, 1)

    if fail_ratio > 0.3 and gas_ratio > 0.5:
        archetype = "🤖 MEV / Sandwich Bot"
        confidence = "High"
        signals = ["High failure rate", "Extreme gas usage", "Likely automated"]
    elif dex_ratio > 0.7 and tx_total > 20:
        archetype = "📊 DeFi Power User"
        confidence = "High"
        signals = ["Majority of txs are DEX interactions", "Active on-chain"]
    elif balance_eth > 100 and tx_total < 10:
        archetype = "🏦 Cold Storage Whale"
        confidence = "Medium"
        signals = ["High ETH balance", "Very low activity", "Long-term holder"]
    elif balance_eth > 10 and eth_moved > 50:
        archetype = "🐳 Active Whale"
        confidence = "Medium"
        signals = ["Large ETH balance", "Significant ETH movement"]
    elif dex_ratio > 0.3 and tx_total > 5:
        archetype = "🌊 Retail DeFi User"
        confidence = "Medium"
        signals = ["Regular DEX usage", "Normal gas patterns"]
    elif tx_total < 5:
        archetype = "😴 Dormant / New Wallet"
        confidence = "Low"
        signals = ["Very few transactions", "May be new or inactive"]
    else:
        archetype = "👤 General User"
        confidence = "Low"
        signals = ["Mixed transaction patterns"]

    return {
        "address":          address,
        "eth_balance":      balance_eth,
        "eth_balance_usd":  f"${balance_eth * eth_price:,.0f}",
        "archetype":        archetype,
        "confidence":       confidence,
        "supporting_signals": signals,
        "dex_interaction_ratio": round(dex_ratio, 2),
        "high_gas_ratio":   round(gas_ratio, 2),
        "fail_tx_ratio":    round(fail_ratio, 2),
        "txs_analyzed":     tx_total,
    }

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_wallet_identity",
            "description": "Build identity profile: ETH balance, wallet age, total tx count, first/last activity, EOA vs contract",
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
            "name": "analyze_trading_behavior",
            "description": "Classify trading style: DEX usage patterns, average trade size, gas aggressiveness, peak activity hours, failed tx ratio (bot detection)",
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {"type": "string"},
                    "limit":   {"type": "integer", "description": "Number of transactions to analyze (default 100)"}
                },
                "required": ["address"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_profitability",
            "description": "Estimate wallet profitability over N days: ETH net flow (inflow - outflow), token accumulation vs distribution, ROI estimate",
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {"type": "string"},
                    "days":    {"type": "integer", "description": "Lookback period in days (default 90)"}
                },
                "required": ["address"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_connected_wallets",
            "description": "Map connected/related wallets by finding frequent counterparties. Flags potential team wallets, deployers, or fund clusters.",
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {"type": "string"},
                    "depth":   {"type": "integer", "description": "Graph depth (default 1, max 2)"}
                },
                "required": ["address"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_token_timing",
            "description": "Analyze how early wallet enters tokens vs deploy date. Detects insider wallets, early snipers, or retail late-movers.",
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
            "name": "compute_roi_explanation",
            "description": "Explain the sources of a wallet's ROI: which tokens drove volume, ETH P&L, protocol usage, conviction holds",
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {"type": "string"},
                    "days":    {"type": "integer", "description": "Analysis window in days (default 90)"}
                },
                "required": ["address"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "detect_wallet_archetype",
            "description": "Final synthesis: classify wallet as MEV Bot, DeFi Power User, Whale, HODLer, Retail, etc. with confidence and signals",
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {"type": "string"}
                },
                "required": ["address"]
            }
        }
    },
]

TOOL_MAP = {
    "get_wallet_identity":      get_wallet_identity,
    "analyze_trading_behavior": analyze_trading_behavior,
    "analyze_profitability":    analyze_profitability,
    "find_connected_wallets":   find_connected_wallets,
    "analyze_token_timing":     analyze_token_timing,
    "compute_roi_explanation":  compute_roi_explanation,
    "detect_wallet_archetype":  detect_wallet_archetype,
}

SYSTEM_PROMPT = """You are an on-chain forensics analyst specializing in deep wallet investigation. You answer questions like "who is this wallet?", "why does it have 400% ROI?", "is it a bot?", "what's its trading strategy?".

INVESTIGATION PROCESS:
1. Start with get_wallet_identity for basic profile
2. Run analyze_trading_behavior to classify style
3. Run analyze_profitability for P&L picture
4. Run detect_wallet_archetype to synthesize
5. Use specialized tools (token timing, connected wallets, ROI explanation) based on the question

REPORT FORMAT - always structure like this:
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔍 WALLET INVESTIGATION: [address short]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🪪 IDENTITY          [age, balance, type]
🎯 ARCHETYPE         [classification + confidence]
📊 TRADING STYLE     [behavior analysis]
💰 PROFITABILITY     [P&L, ROI drivers]
🕸️  CONNECTIONS       [related wallets]
⏱️  TIMING PROFILE    [early/late buyer?]
⚠️  RED FLAGS         [anomalies]
━━━━━━━━━━━━━━━━━━━━━━━━━━━
🧠 SUMMARY & VERDICT
━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Be specific and data-driven. When explaining ROI, name the actual tokens and protocols. When flagging bots, cite the exact signals (fail rate, gas, timing). Think like a blockchain forensics investigator."""

def call_ollama(messages: list) -> Any:
    payload = {
        "model": MODEL, "messages": messages,
        "tools": TOOLS, "stream": False,
        "options": {"temperature": 0.1}
    }
    r = requests.post(OLLAMA_URL, json=payload, timeout=120)
    r.raise_for_status()
    return r.json()


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

    for i in range(12):
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
╔═══════════════════════════════════════════════════════════════════╗
║   🕵️   Wallet Investigator AI Agent                              ║
║   Behavior · Connections · Profitability · Trading Style         ║
╚═══════════════════════════════════════════════════════════════════╝
"""

EXAMPLES = """
Example prompts:
  • Investigate 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045
  • Explain why this wallet has 400% ROI: 0x...
  • Is 0x... a bot or human trader?
  • What's the trading strategy of 0x...?
  • Who are the connected wallets of 0x...?
  • Was 0x... buying tokens early before pumps?
  • Give me a full forensic report on 0x...
  • What protocols does 0x... use the most?

Commands: save · clear · quit
"""


def main():
    print(BANNER)
    print(f"  Model   : {MODEL}")
    print(f"  Chain   : Ethereum Mainnet")
    print(f"  Signals : Identity · Style · P&L · Connections · Timing · Archetype")
    print(EXAMPLES)
    print("─" * 67)

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
            print("🔄 Cleared.")
            continue
        if user_input.lower() == "save":
            if last_reply:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                fn = f"wallet_investigation_{ts}.md"
                with open(fn, "w") as f:
                    f.write(f"# Wallet Investigation Report\n*{datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n")
                    f.write(last_reply)
                print(f"  💾 Saved → {fn}")
            else:
                print("  ⚠️  Nothing to save yet.")
            continue

        print("\n  🕵️  Investigating on-chain data...\n")
        try:
            reply, history = run_agent(user_input, history)
            last_reply = reply
            print(f"\n{'━'*67}")
            print(reply)
            print(f"{'━'*67}")
            print("  💡 Type 'save' to export this report as .md")
        except requests.exceptions.ConnectionError:
            print("  ❌ Ollama not running → ollama serve")
        except Exception as e:
            print(f"  ❌ Error: {e}")


if __name__ == "__main__":
    main()