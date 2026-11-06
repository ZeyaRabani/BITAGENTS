import json
import requests
from datetime import datetime, timedelta
from typing import Any

OLLAMA_URL    = "http://localhost:11434/api/chat"
MODEL         = "llama3.1"

ETHERSCAN_API = "https://api.etherscan.io/api"
ETHERSCAN_KEY = "YourApiKeyToken"   # ToDo: free key → https://etherscan.io/apis
COINGECKO_API = "https://api.coingecko.com/api/v3"
ETH_RPC       = "https://eth.llamarpc.com"

TOKEN_SECTORS = {
    "fetch-ai": "AI", "singularitynet": "AI", "ocean-protocol": "AI",
    "render-token": "AI", "akash-network": "AI", "bittensor": "AI",
    "numeraire": "AI", "cortex": "AI", "matrix-ai-network": "AI",
    "uniswap": "DeFi", "aave": "DeFi", "compound-governance-token": "DeFi",
    "curve-dao-token": "DeFi", "maker": "DeFi", "synthetix-network-token": "DeFi",
    "1inch": "DeFi", "balancer": "DeFi", "yearn-finance": "DeFi",
    "ethereum": "L1", "solana": "L1", "avalanche-2": "L1", "near": "L1",
    "cosmos": "L1", "polkadot": "L1", "cardano": "L1", "algorand": "L1",
    "matic-network": "L2", "arbitrum": "L2", "optimism": "L2",
    "immutable-x": "L2", "loopring": "L2", "metis-token": "L2",
    "axie-infinity": "Gaming/NFT", "the-sandbox": "Gaming/NFT",
    "decentraland": "Gaming/NFT", "illuvium": "Gaming/NFT",
    "gala": "Gaming/NFT", "gods-unchained": "Gaming/NFT",
    "tether": "Stablecoin", "usd-coin": "Stablecoin", "dai": "Stablecoin",
    "frax": "Stablecoin", "true-usd": "Stablecoin", "paxos-standard": "Stablecoin",
    "bitcoin": "BTC", "wrapped-bitcoin": "BTC", "ren": "BTC",
    "chainlink": "Oracle", "band-protocol": "Oracle", "tellor": "Oracle",
    "the-graph": "Infrastructure", "filecoin": "Infrastructure",
    "arweave": "Infrastructure", "helium": "Infrastructure",
}

def get_wallet_token_balances(wallet_address: str) -> dict:
    """
    Fetch all ERC-20 token balances for a wallet using Etherscan.
    Returns token symbols, contract addresses, and raw quantities.
    """
    try:
        payload = {
            "jsonrpc": "2.0", "method": "eth_getBalance",
            "params": [wallet_address, "latest"], "id": 1
        }
        r = requests.post(ETH_RPC, json=payload, timeout=10)
        eth_wei = int(r.json().get("result", "0x0"), 16)
        eth_balance = eth_wei / 1e18

        params = {
            "module": "account", "action": "tokentx",
            "address": wallet_address,
            "page": 1, "offset": 100, "sort": "desc",
            "apikey": ETHERSCAN_KEY
        }
        r2 = requests.get(ETHERSCAN_API, params=params, timeout=10)
        data = r2.json()

        tokens = {}
        if data.get("status") == "1":
            for tx in data["result"]:
                addr = tx["contractAddress"]
                symbol = tx["tokenSymbol"]
                name = tx["tokenName"]
                decimals = int(tx["tokenDecimal"]) if tx["tokenDecimal"] else 18

                if addr not in tokens:
                    tokens[addr] = {
                        "symbol": symbol,
                        "name": name,
                        "contract": addr,
                        "decimals": decimals,
                        "recent_tx_count": 0
                    }
                tokens[addr]["recent_tx_count"] += 1

        return {
            "wallet": wallet_address,
            "eth_balance": round(eth_balance, 6),
            "erc20_tokens": list(tokens.values())[:20],
            "unique_tokens_found": len(tokens),
            "note": "Token quantities from Etherscan tx history. For exact balances per token, use get_token_balance_for_contract."
        }
    except Exception as e:
        return {"error": str(e)}


def get_token_balance_for_contract(wallet_address: str, contract_address: str, decimals: int = 18) -> dict:
    """
    Get exact ERC-20 token balance for a specific contract using eth_call (balanceOf).
    """
    try:
        padded = wallet_address[2:].zfill(64).lower()
        data = "0x70a08231" + padded
        payload = {
            "jsonrpc": "2.0", "method": "eth_call",
            "params": [{"to": contract_address, "data": data}, "latest"],
            "id": 1
        }
        r = requests.post(ETH_RPC, json=payload, timeout=10)
        result = r.json()
        if "result" in result and result["result"] != "0x":
            raw = int(result["result"], 16)
            balance = raw / (10 ** decimals)
            return {
                "wallet": wallet_address,
                "contract": contract_address,
                "balance": round(balance, 6),
                "raw_balance": raw
            }
        return {"wallet": wallet_address, "contract": contract_address, "balance": 0}
    except Exception as e:
        return {"error": str(e)}


def get_prices_and_market_data(token_ids: list) -> dict:
    """
    Fetch current prices, 24h change, 7d change, 30d change, and market caps
    for a list of CoinGecko token IDs. Used to value portfolio positions.
    token_ids: list of CoinGecko slugs e.g. ['ethereum', 'uniswap', 'chainlink']
    """
    try:
        ids_str = ",".join(token_ids[:25])  # CoinGecko free tier limit
        params = {
            "ids": ids_str,
            "vs_currencies": "usd",
            "include_market_cap": "true",
            "include_24hr_change": "true",
            "include_7d_change": "true",
            "price_change_percentage": "1h,24h,7d,30d"
        }
        r = requests.get(f"{COINGECKO_API}/simple/price", params=params, timeout=15)
        if r.status_code != 200:
            return {"error": f"CoinGecko returned {r.status_code}"}

        data = r.json()
        result = {}
        for tid, v in data.items():
            result[tid] = {
                "price_usd": v.get("usd"),
                "market_cap_usd": v.get("usd_market_cap"),
                "change_24h_pct": v.get("usd_24h_change"),
            }
        return {"prices": result, "fetched_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}
    except Exception as e:
        return {"error": str(e)}

def calculate_portfolio_pnl(positions: list) -> dict:
    """
    Calculate PnL for a portfolio of positions.

    positions: list of dicts, each with:
      - token_id: CoinGecko slug (e.g. 'ethereum')
      - symbol: ticker (e.g. 'ETH')
      - quantity: number of tokens held
      - avg_buy_price_usd: average cost basis per token (0 if unknown)
      - current_price_usd: current market price per token

    Returns per-position PnL and portfolio totals.
    """
    try:
        total_value     = 0.0
        total_cost      = 0.0
        position_detail = []
        unknown_cost    = []

        for p in positions:
            qty      = float(p.get("quantity", 0))
            buy_px   = float(p.get("avg_buy_price_usd", 0))
            curr_px  = float(p.get("current_price_usd", 0))
            symbol   = p.get("symbol", "?")
            tid      = p.get("token_id", symbol)

            curr_val = qty * curr_px
            cost_val = qty * buy_px
            pnl_usd  = curr_val - cost_val
            pnl_pct  = ((curr_px / buy_px) - 1) * 100 if buy_px > 0 else None

            total_value += curr_val
            total_cost  += cost_val

            pos = {
                "token": symbol,
                "token_id": tid,
                "quantity": qty,
                "current_price_usd": curr_px,
                "current_value_usd": round(curr_val, 2),
                "avg_buy_price_usd": buy_px if buy_px > 0 else "unknown",
                "pnl_usd": round(pnl_usd, 2) if buy_px > 0 else "unknown",
                "pnl_pct": round(pnl_pct, 2) if pnl_pct is not None else "unknown",
                "pnl_emoji": ("📈" if pnl_usd >= 0 else "📉") if buy_px > 0 else "❓"
            }
            position_detail.append(pos)
            if buy_px == 0:
                unknown_cost.append(symbol)

        position_detail.sort(key=lambda x: x["current_value_usd"], reverse=True)

        total_pnl     = total_value - total_cost
        total_pnl_pct = ((total_value / total_cost) - 1) * 100 if total_cost > 0 else None

        return {
            "positions": position_detail,
            "portfolio_summary": {
                "total_value_usd": round(total_value, 2),
                "total_cost_usd": round(total_cost, 2),
                "total_pnl_usd": round(total_pnl, 2) if total_cost > 0 else "unknown",
                "total_pnl_pct": round(total_pnl_pct, 2) if total_pnl_pct is not None else "unknown",
                "overall_emoji": ("📈" if total_pnl >= 0 else "📉") if total_cost > 0 else "❓"
            },
            "tokens_with_unknown_cost_basis": unknown_cost
        }
    except Exception as e:
        return {"error": str(e)}


def analyze_allocation(positions: list) -> dict:
    """
    Calculate portfolio allocation percentages by token.
    positions: list of {"symbol": str, "token_id": str, "value_usd": float}
    Returns allocation % per token, sorted largest first.
    """
    try:
        total = sum(float(p.get("value_usd", 0)) for p in positions)
        if total == 0:
            return {"error": "Total portfolio value is zero"}

        allocations = []
        for p in positions:
            val = float(p.get("value_usd", 0))
            pct = (val / total) * 100
            allocations.append({
                "token": p.get("symbol", "?"),
                "token_id": p.get("token_id", ""),
                "value_usd": round(val, 2),
                "allocation_pct": round(pct, 2)
            })

        allocations.sort(key=lambda x: x["allocation_pct"], reverse=True)

        risk_flags = []
        top = allocations[0] if allocations else {}
        if top.get("allocation_pct", 0) > 50:
            risk_flags.append(f"🔴 {top['token']} is {top['allocation_pct']}% of portfolio - extreme concentration")
        elif top.get("allocation_pct", 0) > 30:
            risk_flags.append(f"🟡 {top['token']} is {top['allocation_pct']}% of portfolio - high concentration")

        top3_pct = sum(a["allocation_pct"] for a in allocations[:3])
        if top3_pct > 80:
            risk_flags.append(f"🟡 Top 3 tokens = {round(top3_pct, 1)}% of portfolio - low diversification")

        return {
            "total_portfolio_value_usd": round(total, 2),
            "allocations": allocations,
            "risk_flags": risk_flags
        }
    except Exception as e:
        return {"error": str(e)}


def analyze_sector_exposure(positions: list) -> dict:
    """
    Group portfolio positions by sector/narrative (AI, DeFi, L1, L2, etc.)
    and calculate exposure per sector.
    positions: list of {"symbol": str, "token_id": str, "value_usd": float}

    Returns sector breakdown and flags if overexposed to any single narrative.
    """
    try:
        total = sum(float(p.get("value_usd", 0)) for p in positions)
        if total == 0:
            return {"error": "Total portfolio value is zero"}

        sectors: dict = {}
        untagged = []

        for p in positions:
            tid = p.get("token_id", "").lower()
            val = float(p.get("value_usd", 0))
            sym = p.get("symbol", "?")
            sector = TOKEN_SECTORS.get(tid, "Other")
            if sector == "Other":
                untagged.append(sym)
            if sector not in sectors:
                sectors[sector] = {"sector": sector, "value_usd": 0.0, "tokens": []}
            sectors[sector]["value_usd"] += val
            sectors[sector]["tokens"].append(sym)

        sector_list = []
        for s, v in sectors.items():
            pct = (v["value_usd"] / total) * 100
            sector_list.append({
                "sector": s,
                "value_usd": round(v["value_usd"], 2),
                "exposure_pct": round(pct, 2),
                "tokens": v["tokens"]
            })
        sector_list.sort(key=lambda x: x["exposure_pct"], reverse=True)

        risk_flags = []
        for s in sector_list:
            if s["sector"] == "Stablecoin":
                continue
            if s["exposure_pct"] > 50:
                risk_flags.append(f"🔴 {s['sector']} exposure = {s['exposure_pct']}% - very concentrated in one narrative")
            elif s["exposure_pct"] > 30:
                risk_flags.append(f"🟡 {s['sector']} exposure = {s['exposure_pct']}% - high single-narrative concentration")

        return {
            "total_portfolio_value_usd": round(total, 2),
            "sector_breakdown": sector_list,
            "untagged_tokens": untagged,
            "risk_flags": risk_flags,
            "tip": "Add more token_id → sector mappings in TOKEN_SECTORS dict for better coverage."
        }
    except Exception as e:
        return {"error": str(e)}


def calculate_portfolio_risk_metrics(positions: list) -> dict:
    """
    Calculate risk metrics:
    - Volatility proxy using 30d price changes
    - Beta proxy (correlation to ETH)
    - Stablecoin buffer %
    - Drawdown risk flags

    positions: list of {"symbol": str, "token_id": str, "value_usd": float,
                        "change_30d_pct": float (optional)}
    """
    try:
        total = sum(float(p.get("value_usd", 0)) for p in positions)
        if total == 0:
            return {"error": "Total portfolio value is zero"}

        stablecoin_ids = {"tether", "usd-coin", "dai", "frax", "true-usd", "paxos-standard", "usdd"}
        stablecoin_val = 0.0
        weighted_volatility = 0.0
        high_vol_tokens = []
        low_vol_tokens  = []

        for p in positions:
            tid  = p.get("token_id", "").lower()
            val  = float(p.get("value_usd", 0))
            sym  = p.get("symbol", "?")
            chg  = p.get("change_30d_pct")
            w    = val / total  # weight

            if tid in stablecoin_ids:
                stablecoin_val += val
                continue

            if chg is not None:
                abs_chg = abs(float(chg))
                weighted_volatility += w * abs_chg
                if abs_chg > 50:
                    high_vol_tokens.append({"token": sym, "change_30d_pct": round(float(chg), 1)})
                elif abs_chg < 10:
                    low_vol_tokens.append({"token": sym, "change_30d_pct": round(float(chg), 1)})

        stablecoin_pct = (stablecoin_val / total) * 100

        risk_flags = []
        if stablecoin_pct < 5:
            risk_flags.append("🟡 Less than 5% in stablecoins - no cash buffer for dips")
        elif stablecoin_pct > 50:
            risk_flags.append("🟡 Over 50% in stablecoins - significant idle capital")

        if weighted_volatility > 40:
            risk_flags.append(f"🔴 Portfolio weighted 30d volatility is high (~{round(weighted_volatility, 1)}%)")
        elif weighted_volatility > 20:
            risk_flags.append(f"🟡 Portfolio weighted 30d volatility is moderate (~{round(weighted_volatility, 1)}%)")

        if high_vol_tokens:
            names = ", ".join(t["token"] for t in high_vol_tokens)
            risk_flags.append(f"🟡 High-volatility positions (>50% 30d move): {names}")

        return {
            "total_portfolio_value_usd": round(total, 2),
            "stablecoin_value_usd": round(stablecoin_val, 2),
            "stablecoin_buffer_pct": round(stablecoin_pct, 2),
            "weighted_30d_volatility_proxy": round(weighted_volatility, 2),
            "high_volatility_tokens": high_vol_tokens,
            "low_volatility_tokens": low_vol_tokens,
            "risk_flags": risk_flags
        }
    except Exception as e:
        return {"error": str(e)}


def get_token_price_history(token_id: str, days: int = 30) -> dict:
    """
    Fetch OHLC-style daily price history for a token from CoinGecko.
    Used to compute drawdown from ATH within the period, trend direction.
    token_id: CoinGecko slug. days: 7, 14, 30, 90, 180, 365.
    """
    try:
        r = requests.get(
            f"{COINGECKO_API}/coins/{token_id}/market_chart",
            params={"vs_currency": "usd", "days": days, "interval": "daily"},
            timeout=15
        )
        if r.status_code != 200:
            return {"error": f"CoinGecko returned {r.status_code}"}

        prices = r.json().get("prices", [])
        if not prices:
            return {"error": "No price data returned"}

        price_vals = [p[1] for p in prices]
        period_high = max(price_vals)
        period_low  = min(price_vals)
        first_price = price_vals[0]
        last_price  = price_vals[-1]
        drawdown_from_high = ((last_price - period_high) / period_high) * 100
        period_return      = ((last_price - first_price) / first_price) * 100

        risk_flags = []
        if drawdown_from_high < -50:
            risk_flags.append(f"🔴 {token_id} is {round(drawdown_from_high, 1)}% below its {days}d high")
        elif drawdown_from_high < -25:
            risk_flags.append(f"🟡 {token_id} is {round(drawdown_from_high, 1)}% below its {days}d high")

        return {
            "token_id": token_id,
            "period_days": days,
            "start_price_usd": round(first_price, 4),
            "current_price_usd": round(last_price, 4),
            "period_high_usd": round(period_high, 4),
            "period_low_usd": round(period_low, 4),
            "period_return_pct": round(period_return, 2),
            "drawdown_from_period_high_pct": round(drawdown_from_high, 2),
            "risk_flags": risk_flags
        }
    except Exception as e:
        return {"error": str(e)}


def generate_portfolio_report(analysis_results: dict) -> dict:
    """
    Aggregate all analysis results into a final portfolio health report
    with an overall Green / Yellow / Red rating.

    analysis_results: dict with optional keys:
      - pnl_summary: from calculate_portfolio_pnl
      - allocation_flags: list of risk flag strings
      - sector_flags: list of risk flag strings
      - risk_flags: list of risk flag strings
      - top_positions: list of {"token": str, "allocation_pct": float, "pnl_pct": float|str}
    """
    try:
        red_flags    = []
        yellow_flags = []

        all_flags = (
            analysis_results.get("allocation_flags", []) +
            analysis_results.get("sector_flags", []) +
            analysis_results.get("risk_flags", [])
        )

        for flag in all_flags:
            f = str(flag)
            if "🔴" in f:
                red_flags.append(f)
            elif "🟡" in f or "⚠️" in f:
                yellow_flags.append(f)

        if red_flags:
            score = "🔴 RED - HIGH RISK PORTFOLIO"
            verdict = "Significant concentration or volatility risks. Consider rebalancing."
        elif len(yellow_flags) >= 3:
            score = "🟡 YELLOW - MODERATE RISK"
            verdict = "Several caution signals. Portfolio may benefit from diversification."
        elif yellow_flags:
            score = "🟡 YELLOW - MINOR CONCERNS"
            verdict = "A few areas to watch. Generally manageable risk profile."
        else:
            score = "🟢 GREEN - HEALTHY PORTFOLIO"
            verdict = "Well-diversified with no major concentration or volatility red flags."

        pnl = analysis_results.get("pnl_summary", {})

        return {
            "overall_score": score,
            "verdict": verdict,
            "portfolio_value_usd": pnl.get("total_value_usd", "unknown"),
            "total_pnl_usd": pnl.get("total_pnl_usd", "unknown"),
            "total_pnl_pct": pnl.get("total_pnl_pct", "unknown"),
            "red_flags": red_flags,
            "yellow_flags": yellow_flags,
            "top_positions": analysis_results.get("top_positions", []),
            "disclaimer": "Automated analysis only. Not financial advice. Always DYOR."
        }
    except Exception as e:
        return {"error": str(e)}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_wallet_token_balances",
            "description": "Fetch all ERC-20 tokens and ETH balance held by a wallet address. Good first step to discover what tokens a wallet holds.",
            "parameters": {
                "type": "object",
                "properties": {
                    "wallet_address": {"type": "string", "description": "Ethereum wallet address (0x...)"}
                },
                "required": ["wallet_address"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_token_balance_for_contract",
            "description": "Get exact ERC-20 token balance for a specific token contract in a wallet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "wallet_address": {"type": "string", "description": "Ethereum wallet address"},
                    "contract_address": {"type": "string", "description": "ERC-20 token contract address"},
                    "decimals": {"type": "integer", "description": "Token decimals (default 18)"}
                },
                "required": ["wallet_address", "contract_address"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_prices_and_market_data",
            "description": "Fetch current USD prices and 24h/7d price changes for a list of CoinGecko token IDs. Required before calculating PnL or allocation values.",
            "parameters": {
                "type": "object",
                "properties": {
                    "token_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of CoinGecko token slugs e.g. ['ethereum', 'uniswap', 'chainlink']"
                    }
                },
                "required": ["token_ids"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_portfolio_pnl",
            "description": "Calculate profit/loss for each position and the overall portfolio. Requires quantity, current price, and optionally average buy price per token.",
            "parameters": {
                "type": "object",
                "properties": {
                    "positions": {
                        "type": "array",
                        "description": "List of position objects",
                        "items": {
                            "type": "object",
                            "properties": {
                                "token_id":           {"type": "string", "description": "CoinGecko slug"},
                                "symbol":             {"type": "string", "description": "Token ticker e.g. ETH"},
                                "quantity":           {"type": "number", "description": "Number of tokens held"},
                                "avg_buy_price_usd":  {"type": "number", "description": "Average cost basis per token (0 if unknown)"},
                                "current_price_usd":  {"type": "number", "description": "Current market price per token"}
                            },
                            "required": ["symbol", "quantity", "current_price_usd"]
                        }
                    }
                },
                "required": ["positions"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_allocation",
            "description": "Calculate what percentage of the portfolio each token represents. Flags over-concentration in a single asset.",
            "parameters": {
                "type": "object",
                "properties": {
                    "positions": {
                        "type": "array",
                        "description": "List of {symbol, token_id, value_usd}",
                        "items": {
                            "type": "object",
                            "properties": {
                                "symbol":    {"type": "string"},
                                "token_id":  {"type": "string"},
                                "value_usd": {"type": "number"}
                            },
                            "required": ["symbol", "value_usd"]
                        }
                    }
                },
                "required": ["positions"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_sector_exposure",
            "description": "Group portfolio positions into sectors/narratives (AI, DeFi, L1, L2, Gaming, etc.) and calculate exposure % per sector. Use this when asked about overexposure to a theme like 'AI tokens' or 'DeFi'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "positions": {
                        "type": "array",
                        "description": "List of {symbol, token_id, value_usd}",
                        "items": {
                            "type": "object",
                            "properties": {
                                "symbol":    {"type": "string"},
                                "token_id":  {"type": "string"},
                                "value_usd": {"type": "number"}
                            },
                            "required": ["symbol", "value_usd"]
                        }
                    }
                },
                "required": ["positions"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_portfolio_risk_metrics",
            "description": "Calculate risk metrics: volatility proxy, stablecoin buffer %, and high-volatility position flags. Provide 30d price change per token if available.",
            "parameters": {
                "type": "object",
                "properties": {
                    "positions": {
                        "type": "array",
                        "description": "List of position objects with optional change_30d_pct",
                        "items": {
                            "type": "object",
                            "properties": {
                                "symbol":          {"type": "string"},
                                "token_id":        {"type": "string"},
                                "value_usd":       {"type": "number"},
                                "change_30d_pct":  {"type": "number", "description": "30-day price change % (optional)"}
                            },
                            "required": ["symbol", "value_usd"]
                        }
                    }
                },
                "required": ["positions"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_token_price_history",
            "description": "Fetch daily price history for a token to calculate drawdown from recent high, period return, and trend direction.",
            "parameters": {
                "type": "object",
                "properties": {
                    "token_id": {"type": "string", "description": "CoinGecko token slug"},
                    "days":     {"type": "integer", "description": "Number of days of history: 7, 14, 30, 90, 180, 365 (default 30)"}
                },
                "required": ["token_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_portfolio_report",
            "description": "Aggregate all analysis results into a final Green / Yellow / Red portfolio health report. Call this LAST after running other analyses.",
            "parameters": {
                "type": "object",
                "properties": {
                    "analysis_results": {
                        "type": "object",
                        "description": "Dict containing: allocation_flags (list), sector_flags (list), risk_flags (list), pnl_summary (dict with total_value_usd, total_pnl_usd, total_pnl_pct), top_positions (list)",
                        "properties": {
                            "allocation_flags": {"type": "array", "items": {"type": "string"}},
                            "sector_flags":     {"type": "array", "items": {"type": "string"}},
                            "risk_flags":       {"type": "array", "items": {"type": "string"}},
                            "pnl_summary": {
                                "type": "object",
                                "properties": {
                                    "total_value_usd": {"type": "number"},
                                    "total_pnl_usd":   {"type": "number"},
                                    "total_pnl_pct":   {"type": "number"}
                                }
                            },
                            "top_positions": {"type": "array"}
                        }
                    }
                },
                "required": ["analysis_results"]
            }
        }
    }
]

TOOL_MAP = {
    "get_wallet_token_balances":       get_wallet_token_balances,
    "get_token_balance_for_contract":  get_token_balance_for_contract,
    "get_prices_and_market_data":      get_prices_and_market_data,
    "calculate_portfolio_pnl":         calculate_portfolio_pnl,
    "analyze_allocation":              analyze_allocation,
    "analyze_sector_exposure":         analyze_sector_exposure,
    "calculate_portfolio_risk_metrics": calculate_portfolio_risk_metrics,
    "get_token_price_history":         get_token_price_history,
    "generate_portfolio_report":       generate_portfolio_report,
}

SYSTEM_PROMPT = """You are a crypto portfolio analytics AI agent. You help users understand their portfolio's PnL, allocation, sector exposure, risk, and concentration.

## Two ways users give you portfolio data:

### A) They provide a wallet address
→ Call get_wallet_token_balances(wallet_address) to discover tokens
→ Then get_prices_and_market_data for the tokens found
→ Build positions list and proceed to analysis

### B) They provide positions manually
e.g. "I hold 2 ETH ($3000 each, bought at $2000), 500 UNI ($6 each)"
→ Parse directly into positions, call get_prices_and_market_data to confirm current prices, then analyze

## Full portfolio analysis flow (run IN ORDER):
1. get_prices_and_market_data - get current prices
2. calculate_portfolio_pnl - compute gains/losses
3. analyze_allocation - % per token, concentration flags
4. analyze_sector_exposure - sector/narrative breakdown
5. calculate_portfolio_risk_metrics - volatility, stablecoin buffer
6. generate_portfolio_report - final 🟢/🟡/🔴 score

## Focused queries - only use relevant tools:
- "Am I overexposed to AI tokens?" → get_prices first, then analyze_sector_exposure
- "What's my PnL?" → get_prices, then calculate_portfolio_pnl
- "How risky is my portfolio?" → get_prices, calculate_portfolio_risk_metrics
- "Show my allocation" → get_prices, analyze_allocation
- "ETH price history 90 days" → get_token_price_history

## Output format:
Present a clean report with sections. Lead with the overall score.
Show numbers in a readable way ($12,345 not 12345.12345).
Use 📈 for gains, 📉 for losses.
Always end with: "This is not financial advice. Always DYOR."
"""

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
        message = response["message"]
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

            print(f"  📡 {tool_name}({list(tool_args.keys())})...")
            result = execute_tool(tool_name, tool_args)
            print(f"  ✅ Done")
            messages.append({"role": "tool", "content": result})

    return "Agent reached maximum iterations.", conversation_history

def main():
    print("=" * 65)
    print("  📊 Portfolio Analytics AI Agent")
    print("  Analyzes: PnL · Allocation · Exposure · Risk · Concentration")
    print("  Powered by Ollama")
    print("=" * 65)
    print(f"  Model: {MODEL}")
    print()
    print("  You can provide your portfolio two ways:")
    print()
    print("  1. By wallet address:")
    print("     > Analyze wallet 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045")
    print()
    print("  2. By listing positions manually:")
    print("     > I hold: 2 ETH bought at $2000, 500 UNI bought at $8,")
    print("       1000 LINK bought at $12, 0.05 BTC bought at $40000")
    print()
    print("  Example questions:")
    print("  • Am I overexposed to AI tokens?")
    print("  • What's my total PnL?")
    print("  • Which position is dragging my portfolio down?")
    print("  • How diversified am I across sectors?")
    print("  • What's my stablecoin buffer?")
    print("  • Show ETH price history for the last 90 days")
    print("  • Full portfolio report for my positions")
    print()
    print("  Type 'quit' to exit, 'clear' to reset conversation")
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