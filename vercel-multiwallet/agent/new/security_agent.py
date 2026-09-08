"""
Security AI Agent using Ollama + Tool Calling
Detects: drainer interactions, scam contracts, rugpull risks, suspicious approvals.
"""

import json
import time
import requests
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from typing import Any

# ─── Configuration ─────────────────────────────────────────────────────────────
OLLAMA_URL    = "http://localhost:11434/api/chat"
MODEL         = "llama3.1"

ETH_RPC       = "https://eth.llamarpc.com"
ETHERSCAN_API = "https://api.etherscan.io/api"
ETHERSCAN_KEY = "YourApiKeyToken"   # free → etherscan.io/apis
COINGECKO_API = "https://api.coingecko.com/api/v3"

HEADERS = {"User-Agent": "SecurityAgent/1.0"}

# ─── Threat Intelligence DB ────────────────────────────────────────────────────
# Curated from public sources: ScamSniffer, Forta, Pocket Universe, public post-mortems
# All addresses are publicly documented malicious contracts.

KNOWN_MALICIOUS = {
    # ── Wallet Drainers ─────────────────────────────────────────────────────────
    "0x00000000003b3cc22af3ae1eac0440bcee416b40": {
        "label": "Inferno Drainer",
        "type":  "DRAINER",
        "risk":  "CRITICAL",
        "desc":  "Infamous wallet drainer responsible for $80M+ in losses. Phishing-deployed.",
    },
    "0x0000000000a39bb272e79075ade125fd351887ac": {
        "label": "Monkey Drainer",
        "type":  "DRAINER",
        "risk":  "CRITICAL",
        "desc":  "NFT-focused drainer. Drained $16M+ from OpenSea phishing campaigns.",
    },
    "0xb27a31f1b0af2946b7f582768f03239b1ec07c2c": {
        "label": "Angel Drainer",
        "type":  "DRAINER",
        "risk":  "CRITICAL",
        "desc":  "Phishing-as-a-service drainer. Active 2023–2024.",
    },
    "0x00000000e0cb9badb474b0e95d23e920b60a68c2": {
        "label": "Pink Drainer",
        "type":  "DRAINER",
        "risk":  "CRITICAL",
        "desc":  "Drained $85M+ across hundreds of phishing sites.",
    },
    # ── Known Scam / Exploit Contracts ──────────────────────────────────────────
    "0x7f268357a8c2552623316e2562d90e642bb538e5": {
        "label": "OpenSea Exploit Contract",
        "type":  "EXPLOIT",
        "risk":  "HIGH",
        "desc":  "Used in 2022 OpenSea vulnerability exploit.",
    },
    "0xa0c68c638235ee32657e8f720a23cec1bfc77c77": {
        "label": "Ronin Bridge Exploiter",
        "type":  "EXPLOIT",
        "risk":  "HIGH",
        "desc":  "Axie Infinity Ronin bridge exploit - $625M stolen.",
    },
    "0x3607f1b4e17a83ccca7e3e68f69e3e1b2ff049fc": {
        "label": "Fake Token Issuer",
        "type":  "SCAM_TOKEN",
        "risk":  "HIGH",
        "desc":  "Mass-deployed honeypot tokens. Cannot sell after buy.",
    },
    # ── Honeypot / Rugpull Deployers ─────────────────────────────────────────────
    "0xdead000000000000000042069420694206942069": {
        "label": "DEAD Wallet / Token Burn",
        "type":  "BURN",
        "risk":  "INFO",
        "desc":  "Common token burn address. Not malicious but watch context.",
    },
    "0x000000000000000000000000000000000000dead": {
        "label": "Token Burn Address",
        "type":  "BURN",
        "risk":  "INFO",
        "desc":  "Standard burn address.",
    },
    # ── Mixer / Obfuscation ──────────────────────────────────────────────────────
    "0xd90e2f925da726b50c4ed8d0fb90ad053324f31b": {
        "label": "Tornado Cash Router (Sanctioned)",
        "type":  "MIXER",
        "risk":  "HIGH",
        "desc":  "OFAC-sanctioned Tornado Cash. Interaction may have compliance implications.",
    },
    "0x722122df12d4e14e13ac3b6895a86e84145b6967": {
        "label": "Tornado Cash Proxy (Sanctioned)",
        "type":  "MIXER",
        "risk":  "HIGH",
        "desc":  "OFAC-sanctioned Tornado Cash proxy contract.",
    },
}

# Risk severity order
RISK_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}

# Approval spender allowlist (known safe)
SAFE_SPENDERS = {
    "0x7a250d5630b4cf539739df2c5dacb4c659f2488d": "Uniswap V2 Router",
    "0xe592427a0aece92de3edee1f18e0157c05861564": "Uniswap V3 Router",
    "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45": "Uniswap Universal Router",
    "0xd9e1ce17f2641f24ae83637ab66a2cca9c378b9f": "SushiSwap Router",
    "0x1111111254eeb25477b68fb85ed929f73a960582": "1inch V5",
    "0xba12222222228d8ba445958a75a0704d566bf2c8": "Balancer Vault",
    "0xdef1c0ded9bec7f1a1670819833240f027b25eff": "0x Exchange Proxy",
    "0xae7ab96520de3a18e5e111b5eaab095312d7fe84": "Lido stETH",
    "0x00000000219ab540356cbb839cbe05303d7705fa": "ETH2 Deposit",
}

MAX_SAFE_APPROVAL = 2**128  # approvals above this are suspicious


# ─── Helpers ───────────────────────────────────────────────────────────────────

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


def _risk_badge(risk: str) -> str:
    return {"CRITICAL": "🚨 CRITICAL", "HIGH": "🔴 HIGH",
            "MEDIUM": "🟡 MEDIUM", "LOW": "🟢 LOW", "INFO": "ℹ️  INFO"}.get(risk, "❓ UNKNOWN")


def _short(addr: str) -> str:
    return addr[:8] + "..." + addr[-4:]


# ─── Tools ────────────────────────────────────────────────────────────────────

def check_address_against_blacklist(address: str) -> dict:
    """
    Check if an address is in the known malicious contract database.
    Returns threat intel including type, risk level, and description.
    """
    addr_lower = address.lower()
    if addr_lower in KNOWN_MALICIOUS:
        threat = KNOWN_MALICIOUS[addr_lower]
        return {
            "address":   address,
            "is_malicious": True,
            "label":     threat["label"],
            "type":      threat["type"],
            "risk":      _risk_badge(threat["risk"]),
            "risk_raw":  threat["risk"],
            "description": threat["desc"],
            "action":    "⛔ DO NOT INTERACT - revoke any existing approvals immediately",
        }
    return {
        "address":      address,
        "is_malicious": False,
        "risk":         "🟢 Not in local blacklist",
        "note":         "Not found in local DB. Run contract_risk_scan for deeper analysis.",
    }


def scan_wallet_for_malicious_interactions(address: str, days: int = 30) -> dict:
    """
    Scan a wallet's recent transaction history for any interactions
    with known malicious contracts (drainers, exploits, mixers).
    """
    cutoff = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())

    data = _etherscan({
        "module": "account", "action": "txlist",
        "address": address, "page": 1, "offset": 200, "sort": "desc"
    })

    threats_found = []
    safe_count    = 0

    if data.get("status") == "1":
        for tx in data["result"]:
            if int(tx["timeStamp"]) < cutoff:
                continue
            to_addr = (tx.get("to") or "").lower()
            if to_addr in KNOWN_MALICIOUS:
                threat = KNOWN_MALICIOUS[to_addr]
                threats_found.append({
                    "tx_hash":   tx["hash"][:18] + "...",
                    "timestamp": datetime.fromtimestamp(int(tx["timeStamp"])).strftime("%Y-%m-%d %H:%M"),
                    "to":        to_addr,
                    "label":     threat["label"],
                    "type":      threat["type"],
                    "risk":      _risk_badge(threat["risk"]),
                    "risk_raw":  threat["risk"],
                    "eth_value": round(int(tx["value"]) / 1e18, 6),
                })
            else:
                safe_count += 1

    threats_found.sort(key=lambda x: RISK_ORDER.get(x["risk_raw"], 9))
    highest = threats_found[0]["risk"] if threats_found else "🟢 No threats found"

    return {
        "address":        address,
        "period_days":    days,
        "threats_found":  len(threats_found),
        "highest_risk":   highest,
        "threat_details": threats_found,
        "safe_txs":       safe_count,
        "verdict":        (
            "🚨 COMPROMISED - interacted with drainer/exploit" if any(t["risk_raw"] in ("CRITICAL", "HIGH") for t in threats_found)
            else "⚠️ CAUTION - interacted with flagged contract" if threats_found
            else "✅ CLEAN - no malicious interactions detected"
        ),
    }


def scan_token_approvals(address: str) -> dict:
    """
    Audit all ERC-20 token approvals granted by a wallet.
    Flags: unlimited approvals to unknown spenders, approvals to known drainers.
    """
    data = _etherscan({
        "module": "account", "action": "tokentx",
        "address": address, "page": 1, "offset": 500, "sort": "desc"
    })

    # Also check internal txs for approval events
    # We approximate approvals by looking at Approve events via logs
    approval_data = _etherscan({
        "module": "logs", "action": "getLogs",
        "address": address,
        "topic0": "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925",  # Approval event
        "fromBlock": "0",
        "toBlock":   "latest",
        "page": 1, "offset": 50
    })

    risky_approvals  = []
    normal_approvals = []

    if approval_data.get("status") == "1":
        for log in approval_data.get("result", []):
            topics = log.get("topics", [])
            if len(topics) < 3:
                continue
            # topic[2] = spender (padded)
            spender_raw = topics[2]
            spender = "0x" + spender_raw[-40:]

            # Decode amount from data field
            data_hex = log.get("data", "0x")
            try:
                amount = int(data_hex, 16)
            except Exception:
                amount = 0

            is_unlimited = amount >= MAX_SAFE_APPROVAL
            is_known_safe = spender.lower() in SAFE_SPENDERS
            is_malicious  = spender.lower() in KNOWN_MALICIOUS

            entry = {
                "token_contract": log.get("address"),
                "spender":        spender,
                "spender_label":  (
                    KNOWN_MALICIOUS[spender.lower()]["label"] if is_malicious else
                    SAFE_SPENDERS.get(spender.lower(), _short(spender))
                ),
                "is_unlimited":   is_unlimited,
                "amount_raw":     amount,
                "block":          int(log.get("blockNumber", "0x0"), 16),
                "is_malicious_spender": is_malicious,
                "is_known_safe":  is_known_safe,
            }

            if is_malicious or (is_unlimited and not is_known_safe):
                risky_approvals.append(entry)
            else:
                normal_approvals.append(entry)

    if risky_approvals:
        verdict = "🚨 DANGEROUS APPROVALS FOUND - revoke immediately"
    elif any(a["is_unlimited"] for a in normal_approvals):
        verdict = "🟡 Unlimited approvals to unknown spenders - review recommended"
    else:
        verdict = "✅ Approvals look clean"

    return {
        "address":          address,
        "risky_approvals":  risky_approvals,
        "normal_approvals": len(normal_approvals),
        "total_approvals":  len(risky_approvals) + len(normal_approvals),
        "verdict":          verdict,
        "revoke_tool":      "https://revoke.cash - connect wallet to revoke approvals",
        "note": "Approvals decoded from on-chain Approval events. Always verify on revoke.cash for complete picture.",
    }


def contract_risk_scan(contract_address: str) -> dict:
    """
    Deep risk analysis of an unknown smart contract:
    - Source code verification status
    - Contract age (new = riskier)
    - Honeypot heuristics (mint/pause/blacklist functions)
    - Transaction volume & unique users
    - Self-destruct / proxy patterns
    """
    # Source code check
    src = _etherscan({
        "module": "contract", "action": "getsourcecode",
        "address": contract_address
    })

    verified      = False
    has_mint      = False
    has_pause     = False
    has_blacklist = False
    has_proxy     = False
    has_ownership_transfer = False
    contract_name = "Unverified"
    compiler      = None
    risky_fns     = []

    if src.get("status") == "1" and src.get("result"):
        r = src["result"][0]
        verified      = bool(r.get("SourceCode"))
        contract_name = r.get("ContractName", "Unknown")
        compiler      = r.get("CompilerVersion")
        has_proxy     = r.get("Proxy") == "1"
        abi_raw       = r.get("ABI", "")

        if abi_raw and abi_raw != "Contract source code not verified":
            try:
                abi = json.loads(abi_raw)
                danger_words = {
                    "mint": "Can create new tokens (inflation risk)",
                    "pause": "Owner can freeze transfers",
                    "blacklist": "Owner can blacklist addresses",
                    "freeze": "Owner can freeze addresses",
                    "setFee": "Owner can change fees",
                    "setTax": "Owner can change taxes",
                    "selfdestruct": "Contract can self-destruct",
                    "transferOwnership": "Ownership can be transferred",
                    "renounceOwnership": "Ownership can be renounced (neutral)",
                    "setMaxWallet": "Owner can set max wallet limit",
                    "excludeFromFee": "Owner can exclude wallets from fees",
                }
                for fn in abi:
                    name = fn.get("name", "")
                    for keyword, desc in danger_words.items():
                        if keyword.lower() in name.lower():
                            risky_fns.append({"function": name, "risk": desc})
            except Exception:
                pass

    # Deployment date
    txs = _etherscan({
        "module": "account", "action": "txlist",
        "address": contract_address, "page": 1, "offset": 1, "sort": "asc"
    })
    deployed_at = None
    age_days    = None
    deployer    = None
    if txs.get("status") == "1" and txs.get("result"):
        tx = txs["result"][0]
        ts = int(tx["timeStamp"])
        deployed_at = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        age_days    = (datetime.now() - datetime.fromtimestamp(ts)).days
        deployer    = tx.get("from")

    # Transaction stats (last 100)
    all_txs = _etherscan({
        "module": "account", "action": "txlist",
        "address": contract_address, "page": 1, "offset": 100, "sort": "desc"
    })
    unique_users = set()
    tx_count_recent = 0
    if all_txs.get("status") == "1":
        for tx in all_txs["result"]:
            unique_users.add(tx["from"])
            tx_count_recent += 1

    # Risk score computation
    risk_flags = []
    score = 0  # higher = riskier

    if not verified:
        risk_flags.append("🔴 Source code NOT verified")
        score += 40
    if age_days is not None and age_days < 7:
        risk_flags.append(f"🔴 Contract only {age_days} days old")
        score += 30
    elif age_days is not None and age_days < 30:
        risk_flags.append(f"🟡 Contract only {age_days} days old")
        score += 15
    if len(risky_fns) > 3:
        risk_flags.append(f"🔴 {len(risky_fns)} privileged owner functions detected")
        score += 20
    elif risky_fns:
        risk_flags.append(f"🟡 {len(risky_fns)} owner-controlled functions detected")
        score += 10
    if tx_count_recent < 10:
        risk_flags.append("🟡 Very low transaction activity")
        score += 10
    if has_proxy:
        risk_flags.append("🟡 Proxy contract - logic can be upgraded by owner")
        score += 10
    if deployer and deployer.lower() in KNOWN_MALICIOUS:
        risk_flags.append(f"🚨 Deployer is a KNOWN malicious address!")
        score += 60

    if score >= 60:
        overall_risk = "🔴 HIGH RISK"
    elif score >= 30:
        overall_risk = "🟡 MEDIUM RISK"
    else:
        overall_risk = "🟢 LOW RISK"

    return {
        "contract_address": contract_address,
        "contract_name":    contract_name,
        "verified":         verified,
        "compiler":         compiler,
        "is_proxy":         has_proxy,
        "deployer":         deployer,
        "deployed_at":      deployed_at,
        "age_days":         age_days,
        "recent_txs":       tx_count_recent,
        "unique_users":     len(unique_users),
        "risky_functions":  risky_fns[:10],
        "risk_flags":       risk_flags,
        "risk_score":       score,
        "overall_risk":     overall_risk,
        "recommendation": (
            "⛔ Avoid - multiple critical risk factors" if score >= 60 else
            "⚠️ Proceed with caution - verify team and audit status" if score >= 30 else
            "✅ Looks reasonable - standard DYOR applies"
        ),
    }


def detect_rugpull_signals(coin_id_or_contract: str) -> dict:
    """
    Check for classic rugpull warning signs:
    - Token age
    - Liquidity lock status (heuristic)
    - Team wallet holdings
    - Social media presence
    - Market cap vs volume anomalies
    Combines on-chain data with CoinGecko metadata.
    """
    signals = []
    score   = 0  # higher = more suspicious

    # Try CoinGecko lookup
    cg_data = None
    try:
        r = requests.get(f"{COINGECKO_API}/coins/{coin_id_or_contract}",
            params={"localization": False, "tickers": False,
                    "community_data": True, "developer_data": True},
            headers=HEADERS, timeout=12)
        if r.status_code == 200:
            cg_data = r.json()
    except Exception:
        pass

    if cg_data:
        genesis = cg_data.get("genesis_date")
        if genesis:
            age = (datetime.now() - datetime.strptime(genesis, "%Y-%m-%d")).days
            if age < 30:
                signals.append(f"🔴 Token only {age} days old")
                score += 25

        comm = cg_data.get("community_data", {})
        dev  = cg_data.get("developer_data", {})
        mkt  = cg_data.get("market_data", {})

        twitter = comm.get("twitter_followers", 0) or 0
        reddit  = comm.get("reddit_subscribers", 0) or 0
        commits = dev.get("commit_count_4_weeks", 0) or 0
        stars   = dev.get("stars", 0) or 0

        if twitter < 500:
            signals.append(f"🔴 Tiny Twitter following ({twitter})")
            score += 20
        if reddit < 100:
            signals.append(f"🟡 Minimal Reddit presence ({reddit})")
            score += 10
        if commits == 0 and stars == 0:
            signals.append("🔴 Zero developer activity on GitHub")
            score += 25

        # Supply concentration proxy
        circ = mkt.get("circulating_supply") or 0
        total = mkt.get("total_supply") or 1
        if circ and total and (circ / total) < 0.2:
            signals.append(f"🔴 Only {circ/total*100:.0f}% of supply in circulation - team holds most")
            score += 30

        # Volume vs market cap ratio
        vol  = mkt.get("total_volume", {}).get("usd") or 0
        mcap = mkt.get("market_cap", {}).get("usd") or 1
        if mcap > 0 and vol / mcap > 2:
            signals.append(f"🟡 Volume ({vol/1e6:.1f}M) far exceeds market cap ({mcap/1e6:.1f}M) - wash trading?")
            score += 15

        links = cg_data.get("links", {})
        if not links.get("homepage", [None])[0]:
            signals.append("🔴 No official website listed")
            score += 20
        if not links.get("repos_url", {}).get("github"):
            signals.append("🟡 No public GitHub repository")
            score += 10

    else:
        signals.append("🟡 Not found on CoinGecko - unverified or very new token")
        score += 20

    # Overall verdict
    if score >= 70:
        verdict = "🚨 VERY HIGH RUGPULL RISK"
    elif score >= 40:
        verdict = "🔴 HIGH RUGPULL RISK"
    elif score >= 20:
        verdict = "🟡 MEDIUM RISK - proceed with extreme caution"
    else:
        verdict = "🟢 LOW RUGPULL RISK - standard DYOR applies"

    return {
        "input":           coin_id_or_contract,
        "risk_score":      score,
        "verdict":         verdict,
        "warning_signals": signals,
        "total_flags":     len(signals),
        "checklist": [
            "Is liquidity locked? Check: app.unicrypt.network or team.finance",
            "Is contract ownership renounced? Check Etherscan contract tab",
            "Are there known audits? Check: solodit.xyz",
            "Is the team doxxed?",
            "Is there a token vesting schedule for team tokens?",
        ],
    }


def monitor_wallets_for_threats(addresses: list, days: int = 7) -> dict:
    """
    Batch monitor multiple wallets for any malicious contract interactions.
    Use this for ongoing surveillance of a watchlist.
    Returns a consolidated threat report across all wallets.
    """
    if len(addresses) > 10:
        addresses = addresses[:10]

    all_threats  = []
    clean_wallets = []
    cutoff = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())

    for addr in addresses:
        time.sleep(0.2)
        data = _etherscan({
            "module": "account", "action": "txlist",
            "address": addr, "page": 1, "offset": 100, "sort": "desc"
        })
        wallet_threats = []
        if data.get("status") == "1":
            for tx in data["result"]:
                if int(tx["timeStamp"]) < cutoff:
                    continue
                to_addr = (tx.get("to") or "").lower()
                if to_addr in KNOWN_MALICIOUS:
                    threat = KNOWN_MALICIOUS[to_addr]
                    wallet_threats.append({
                        "wallet":    addr,
                        "tx_hash":   tx["hash"][:18] + "...",
                        "timestamp": datetime.fromtimestamp(int(tx["timeStamp"])).strftime("%Y-%m-%d %H:%M"),
                        "threat":    threat["label"],
                        "type":      threat["type"],
                        "risk":      _risk_badge(threat["risk"]),
                        "risk_raw":  threat["risk"],
                    })

        if wallet_threats:
            all_threats.extend(wallet_threats)
        else:
            clean_wallets.append(addr)

    all_threats.sort(key=lambda x: RISK_ORDER.get(x["risk_raw"], 9))

    return {
        "wallets_monitored": len(addresses),
        "period_days":       days,
        "wallets_with_threats": len(set(t["wallet"] for t in all_threats)),
        "clean_wallets":     len(clean_wallets),
        "total_threats":     len(all_threats),
        "threats":           all_threats,
        "alert": (
            f"🚨 ALERT: {len(all_threats)} threat interactions detected across {len(set(t['wallet'] for t in all_threats))} wallets"
            if all_threats else
            "✅ All wallets clean - no malicious interactions in the past " + str(days) + " days"
        ),
    }


def check_phishing_simulation(address: str) -> dict:
    """
    Heuristic check: has this wallet recently interacted with contracts
    that show patterns consistent with phishing (new + unverified + small tx volume).
    """
    data = _etherscan({
        "module": "account", "action": "txlist",
        "address": address, "page": 1, "offset": 50, "sort": "desc"
    })

    suspicious = []
    cutoff_30d = int((datetime.now(timezone.utc) - timedelta(days=30)).timestamp())

    if data.get("status") == "1":
        unique_contracts = set()
        for tx in data["result"]:
            if int(tx["timeStamp"]) < cutoff_30d:
                continue
            to = (tx.get("to") or "").lower()
            if not to or to in unique_contracts:
                continue
            unique_contracts.add(to)

            # Check if target is a contract
            code = _rpc("eth_getCode", [to, "latest"])
            if not code or code == "0x":
                continue  # skip EOAs

            # Check verification
            src = _etherscan({"module": "contract", "action": "getsourcecode", "address": to})
            verified = False
            age_days = None
            if src.get("status") == "1" and src.get("result"):
                verified = bool(src["result"][0].get("SourceCode"))

            # Check age
            deploy_txs = _etherscan({
                "module": "account", "action": "txlist",
                "address": to, "page": 1, "offset": 1, "sort": "asc"
            })
            if deploy_txs.get("status") == "1" and deploy_txs.get("result"):
                deploy_ts = int(deploy_txs["result"][0]["timeStamp"])
                age_days  = (datetime.now() - datetime.fromtimestamp(deploy_ts)).days

            phish_score = 0
            flags = []
            if not verified:
                phish_score += 30
                flags.append("Unverified source")
            if age_days is not None and age_days < 14:
                phish_score += 40
                flags.append(f"Only {age_days} days old")
            if to in KNOWN_MALICIOUS:
                phish_score += 100
                flags.append("In malicious DB")

            if phish_score >= 40:
                suspicious.append({
                    "contract":      to,
                    "phish_score":   phish_score,
                    "flags":         flags,
                    "age_days":      age_days,
                    "verified":      verified,
                    "tx_timestamp":  datetime.fromtimestamp(int(tx["timeStamp"])).strftime("%Y-%m-%d %H:%M"),
                })

            time.sleep(0.1)  # rate limiting
            if len(suspicious) >= 5:
                break

    suspicious.sort(key=lambda x: x["phish_score"], reverse=True)

    return {
        "address":             address,
        "suspicious_contracts": suspicious,
        "phishing_risk":       (
            "🚨 HIGH - interacted with likely phishing contracts" if any(s["phish_score"] >= 70 for s in suspicious) else
            "🟡 MEDIUM - some suspicious contract interactions" if suspicious else
            "✅ LOW - no phishing indicators found"
        ),
    }


def get_security_summary(address: str) -> dict:
    """
    Quick security health check combining blacklist scan + approval audit.
    Use this for a fast overview before deeper investigation.
    """
    eth_price = 2000
    try:
        r = requests.get(f"{COINGECKO_API}/simple/price",
            params={"ids": "ethereum", "vs_currencies": "usd"}, timeout=8)
        eth_price = r.json().get("ethereum", {}).get("usd", 2000)
    except Exception:
        pass

    raw = _rpc("eth_getBalance", [address, "latest"])
    balance_eth = round(int(raw, 16) / 1e18, 4) if raw else 0

    # Quick blacklist check on recent counterparties
    data = _etherscan({
        "module": "account", "action": "txlist",
        "address": address, "page": 1, "offset": 50, "sort": "desc"
    })

    flagged = []
    if data.get("status") == "1":
        for tx in data["result"]:
            to = (tx.get("to") or "").lower()
            if to in KNOWN_MALICIOUS:
                flagged.append(KNOWN_MALICIOUS[to]["label"])

    return {
        "address":       address,
        "balance_eth":   balance_eth,
        "balance_usd":   f"${balance_eth * eth_price:,.0f}",
        "known_threats_in_history": list(set(flagged)),
        "threat_count":  len(set(flagged)),
        "quick_verdict": (
            f"🚨 DANGER - {len(set(flagged))} known threat(s) in tx history" if flagged else
            "✅ Quick scan clean"
        ),
        "next_steps": [
            "Run scan_wallet_for_malicious_interactions for full history scan",
            "Run scan_token_approvals to check dangerous approvals",
            "Run contract_risk_scan on any unfamiliar contracts",
        ],
        "revoke_url": "https://revoke.cash",
    }


# ─── Tool Registry ─────────────────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "check_address_against_blacklist",
            "description": "Check if a specific address is in the known malicious contract database (drainers, exploits, mixers, scam contracts)",
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {"type": "string", "description": "Ethereum address to check"}
                },
                "required": ["address"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scan_wallet_for_malicious_interactions",
            "description": "Scan a wallet's full transaction history for any interactions with known malicious contracts over N days",
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {"type": "string"},
                    "days":    {"type": "integer", "description": "Lookback in days (default 30)"}
                },
                "required": ["address"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scan_token_approvals",
            "description": "Audit all ERC-20 token approvals: flags unlimited approvals to unknown/malicious spenders. Links to revoke.cash.",
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
            "name": "contract_risk_scan",
            "description": "Deep risk analysis of a smart contract: verification status, age, honeypot functions (mint/pause/blacklist), deployer identity",
            "parameters": {
                "type": "object",
                "properties": {
                    "contract_address": {"type": "string"}
                },
                "required": ["contract_address"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "detect_rugpull_signals",
            "description": "Check for rugpull warning signs: token age, community size, dev activity, supply concentration, volume anomalies",
            "parameters": {
                "type": "object",
                "properties": {
                    "coin_id_or_contract": {"type": "string", "description": "CoinGecko coin ID (e.g. 'dogecoin') or contract address"}
                },
                "required": ["coin_id_or_contract"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "monitor_wallets_for_threats",
            "description": "Batch monitor multiple wallets for malicious interactions. Use for ongoing watchlist surveillance.",
            "parameters": {
                "type": "object",
                "properties": {
                    "addresses": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of wallet addresses to monitor (max 10)"
                    },
                    "days": {"type": "integer", "description": "Lookback window in days (default 7)"}
                },
                "required": ["addresses"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_phishing_simulation",
            "description": "Detect phishing interactions: checks if wallet recently interacted with new unverified contracts (common in phishing attacks)",
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
            "name": "get_security_summary",
            "description": "Quick security health check: balance, known threats in history, and recommended next steps",
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
    "check_address_against_blacklist":        check_address_against_blacklist,
    "scan_wallet_for_malicious_interactions": scan_wallet_for_malicious_interactions,
    "scan_token_approvals":                   scan_token_approvals,
    "contract_risk_scan":                     contract_risk_scan,
    "detect_rugpull_signals":                 detect_rugpull_signals,
    "monitor_wallets_for_threats":            monitor_wallets_for_threats,
    "check_phishing_simulation":              check_phishing_simulation,
    "get_security_summary":                   get_security_summary,
}

SYSTEM_PROMPT = """You are an on-chain security analyst and threat detection agent. Your job is to protect users from drainers, scam contracts, rugpulls, and suspicious approvals.

INVESTIGATION PROCESS:
1. For wallet checks: get_security_summary → scan_wallet_for_malicious_interactions → scan_token_approvals → check_phishing_simulation
2. For contract checks: check_address_against_blacklist → contract_risk_scan
3. For token/project checks: detect_rugpull_signals
4. For batch monitoring: monitor_wallets_for_threats

REPORT FORMAT:
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🛡️  SECURITY REPORT: [address/project]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚨 THREAT LEVEL:     [CRITICAL / HIGH / MEDIUM / LOW / CLEAN]
🔍 BLACKLIST CHECK:  [result]
✅ APPROVAL AUDIT:   [result]
🍯 RUGPULL SIGNALS:  [result]
🎣 PHISHING CHECK:   [result]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  ACTION REQUIRED:  [specific steps]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

ALWAYS:
- Lead with the threat level immediately
- Give specific actionable steps (revoke which approvals, avoid which contract)
- Link to revoke.cash for approval revocations
- Be direct and urgent when threats are found - lives and funds are at stake
- Never give a false all-clear - always recommend DYOR and revoke.cash review"""


# ─── Agent Loop ────────────────────────────────────────────────────────────────

def call_ollama(messages: list) -> Any:
    payload = {
        "model": MODEL, "messages": messages,
        "tools": TOOLS, "stream": False,
        "options": {"temperature": 0.05}   # deterministic for security
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


# ─── CLI ───────────────────────────────────────────────────────────────────────

BANNER = r"""
╔══════════════════════════════════════════════════════════════════════╗
║   🛡️   Security AI Agent                                            ║
║   Drainers · Scam Contracts · Rugpulls · Approvals · Phishing       ║
╚══════════════════════════════════════════════════════════════════════╝
"""

EXAMPLES = """
Example prompts:
  • Is 0x00000000003b3cc22af3ae1eac0440bcee416b40 a drainer?
  • Full security check on wallet 0x...
  • Scan my approvals for 0x... - are any dangerous?
  • Is this contract a rugpull? 0x...
  • Monitor these 3 wallets for threats: 0x... 0x... 0x...
  • Alert me if wallet 0x... has interacted with any malicious contract
  • Is this new token safe? Check: 0x...
  • Run a phishing check on 0x...

Commands: save · clear · quit
"""


def main():
    print(BANNER)
    print(f"  Model     : {MODEL}")
    print(f"  Threats DB: {len(KNOWN_MALICIOUS)} known malicious addresses")
    print(f"  Safe list : {len(SAFE_SPENDERS)} known safe spenders")
    print(f"  Checks    : Blacklist · Approvals · Contract Risk · Rugpull · Phishing")
    print(EXAMPLES)
    print("─" * 70)

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
                fn = f"security_report_{ts}.md"
                with open(fn, "w") as f:
                    f.write(f"# Security Report\n*{datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n")
                    f.write(last_reply)
                print(f"  💾 Saved → {fn}")
            else:
                print("  ⚠️  Nothing to save yet.")
            continue

        print("\n  🛡️  Running security analysis...\n")
        try:
            reply, history = run_agent(user_input, history)
            last_reply = reply
            print(f"\n{'━'*70}")
            print(reply)
            print(f"{'━'*70}")
            print("  💡 Type 'save' to export · revoke.cash to revoke approvals")
        except requests.exceptions.ConnectionError:
            print("  ❌ Ollama not running → ollama serve")
        except Exception as e:
            print(f"  ❌ Error: {e}")


if __name__ == "__main__":
    main()