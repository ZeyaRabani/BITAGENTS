import json
import requests
from datetime import datetime, timezone, timedelta
from typing import Any

OLLAMA_URL      = "http://localhost:11434/api/chat"
MODEL           = "llama3.1"

ETHERSCAN_API   = "https://api.etherscan.io/api"
ETHERSCAN_KEY   = "YourApiKeyToken"   # ToDo: free → https://etherscan.io/apis
COINGECKO_API   = "https://api.coingecko.com/api/v3"
DEFILLAMA_API   = "https://api.llama.fi"
ETH_RPC         = "https://eth.llamarpc.com"
CRYPTOPANIC_API = "https://cryptopanic.com/api/v1/posts/"
CRYPTOPANIC_KEY = "free"

AIRDROP_DATABASE = {
    "uniswap_uni": {
        "name": "Uniswap UNI",
        "token": "UNI",
        "status": "ended",
        "snapshot_date": "2020-09-01",
        "claim_deadline": "2021-09-01",
        "criteria": ["used Uniswap V1 or V2 before Sep 1 2020", "provided liquidity on Uniswap"],
        "amount": "400 UNI per wallet",
        "checker_url": "https://app.uniswap.org",
        "chain": "ethereum",
        "notes": "One of the most famous airdrops. 400 UNI per address that used the protocol."
    },
    "optimism_op_1": {
        "name": "Optimism OP Airdrop #1",
        "token": "OP",
        "status": "ended",
        "snapshot_date": "2022-03-25",
        "claim_deadline": "2023-01-18",
        "criteria": ["bridged to Optimism", "used dApps on Optimism", "active L1 Ethereum user",
                     "DAO voter", "Gitcoin donor", "multi-sig signer"],
        "amount": "varies 800–8000 OP",
        "checker_url": "https://app.optimism.io/airdrop/check",
        "chain": "optimism",
        "notes": "Multiple eligibility buckets. L2 bridgers and governance participants rewarded."
    },
    "arbitrum_arb": {
        "name": "Arbitrum ARB",
        "token": "ARB",
        "status": "ended",
        "snapshot_date": "2023-02-06",
        "claim_deadline": "2024-03-23",
        "criteria": ["bridged to Arbitrum One or Arbitrum Nova",
                     "made transactions on Arbitrum",
                     "used Arbitrum in multiple months",
                     "interacted with multiple protocols on Arbitrum"],
        "amount": "based on point score (625–10,250 ARB)",
        "checker_url": "https://arbitrum.foundation/airdrop",
        "chain": "arbitrum",
        "notes": "Point-based scoring. More tx volume + protocol diversity = more ARB."
    },
    "ens_ens": {
        "name": "ENS DAO",
        "token": "ENS",
        "status": "ended",
        "snapshot_date": "2021-10-31",
        "claim_deadline": "2022-05-04",
        "criteria": ["owned an ENS name", "longer registration = more ENS"],
        "amount": "based on name registration length",
        "checker_url": "https://claim.ens.domains",
        "chain": "ethereum",
        "notes": "ENS name holders rewarded. Retroactive for prior registrations."
    },
    "dydx_dydx": {
        "name": "dYdX DYDX",
        "token": "DYDX",
        "status": "ended",
        "snapshot_date": "2021-07-26",
        "claim_deadline": "2022-02-14",
        "criteria": ["traded on dYdX", "higher trading volume = more DYDX"],
        "amount": "based on trading volume tiers",
        "checker_url": "https://dydx.exchange",
        "chain": "ethereum",
        "notes": "Volume-based tiered distribution. Active traders rewarded most."
    },
    "1inch_1inch": {
        "name": "1inch 1INCH",
        "token": "1INCH",
        "status": "ended",
        "snapshot_date": "2020-12-24",
        "claim_deadline": "2022-01-14",
        "criteria": ["used 1inch exchange before Dec 24 2020"],
        "amount": "varies by usage",
        "checker_url": "https://1inch.io",
        "chain": "ethereum",
        "notes": "Christmas 2020 airdrop. 1inch V1 users rewarded."
    },
    "zksync_zk": {
        "name": "zkSync ZK",
        "token": "ZK (speculative)",
        "status": "potential",
        "snapshot_date": "TBD",
        "claim_deadline": None,
        "criteria": ["bridged ETH to zkSync Era", "used dApps on zkSync Era",
                     "maintained liquidity on zkSync", "used zkSync in multiple months",
                     "interacted with 5+ unique protocols on zkSync"],
        "checker_url": "https://portal.zksync.io",
        "chain": "zksync",
        "notes": "No token yet as of late 2024. Heavy ecosystem activity is commonly speculated to qualify.",
        "qualifying_protocols": ["SyncSwap", "Mute.io", "zkSync bridge", "SpaceFi", "Velocore"]
    },
    "starknet_strk_2": {
        "name": "StarkNet STRK Season 2",
        "token": "STRK",
        "status": "potential",
        "snapshot_date": "TBD",
        "claim_deadline": None,
        "criteria": ["used StarkNet dApps", "bridged to StarkNet",
                     "held StarkNet-native assets", "interacted with multiple StarkNet protocols"],
        "checker_url": "https://starkgate.starknet.io",
        "chain": "starknet",
        "notes": "STRK was distributed in early 2024. Season 2 speculated. Activity on StarkNet may qualify.",
        "qualifying_protocols": ["JediSwap", "mySwap", "Argent", "Braavos"]
    },
    "scroll_scr": {
        "name": "Scroll SCR",
        "token": "SCR",
        "status": "potential",
        "snapshot_date": "TBD",
        "claim_deadline": None,
        "criteria": ["bridged to Scroll mainnet", "used Scroll ecosystem dApps",
                     "maintained activity across multiple months on Scroll",
                     "interacted with 3+ protocols on Scroll"],
        "checker_url": "https://scroll.io/bridge",
        "chain": "scroll",
        "notes": "Scroll launched mainnet in Oct 2023, no token yet. Activity commonly expected to count.",
        "qualifying_protocols": ["SyncSwap on Scroll", "Ambient Finance", "LayerBank"]
    },
    "linea_linea": {
        "name": "Linea Token",
        "token": "LINEA (speculative)",
        "status": "potential",
        "snapshot_date": "TBD",
        "claim_deadline": None,
        "criteria": ["bridged to Linea", "used Linea ecosystem protocols",
                     "traded on Linea DEXes", "held assets on Linea for multiple months"],
        "checker_url": "https://bridge.linea.build",
        "chain": "linea",
        "notes": "Consensys / MetaMask-backed L2. No token announced but widely expected.",
        "qualifying_protocols": ["Velocore on Linea", "SyncSwap on Linea", "HorizonDEX"]
    },
    "hyperliquid_hype": {
        "name": "Hyperliquid HYPE",
        "token": "HYPE",
        "status": "confirmed",
        "snapshot_date": "2024-11-29",
        "claim_deadline": "2025-12-01",
        "criteria": ["traded on Hyperliquid perps exchange",
                     "higher trading volume = more HYPE",
                     "provided liquidity in HLP vault"],
        "amount": "based on trading points",
        "checker_url": "https://app.hyperliquid.xyz/drip",
        "chain": "hyperliquid",
        "notes": "One of the largest airdrops of 2024. Active perp traders rewarded heavily."
    },
    "layerzero_zro": {
        "name": "LayerZero ZRO",
        "token": "ZRO",
        "status": "ended",
        "snapshot_date": "2024-06-20",
        "claim_deadline": "2024-08-20",
        "criteria": ["used LayerZero-powered bridges or protocols",
                     "bridged across chains using Stargate Finance",
                     "used apps built on LayerZero messaging"],
        "amount": "varies by usage",
        "checker_url": "https://layerzero.network/zro",
        "chain": "ethereum",
        "notes": "Required a $0.10 donation to claim. Used cross-chain messaging protocols."
    },
    "eigen_eigen": {
        "name": "EigenLayer EIGEN",
        "token": "EIGEN",
        "status": "ended",
        "snapshot_date": "2024-03-15",
        "claim_deadline": "2025-09-01",
        "criteria": ["restaked ETH or LSTs on EigenLayer",
                     "staked before snapshot date",
                     "restaked via supported LST tokens"],
        "amount": "proportional to restaked amount",
        "checker_url": "https://claims.eigenfoundation.org",
        "chain": "ethereum",
        "notes": "Restakers of ETH/stETH/rETH on EigenLayer mainnet qualified."
    },
    "pendle_pendle": {
        "name": "Pendle Points Programs",
        "token": "PENDLE",
        "status": "ongoing",
        "snapshot_date": "rolling",
        "claim_deadline": None,
        "criteria": ["provided liquidity on Pendle Finance",
                     "held PT or YT tokens",
                     "staked vePENDLE"],
        "amount": "ongoing rewards",
        "checker_url": "https://app.pendle.finance",
        "chain": "ethereum",
        "notes": "Ongoing points programs. Active LPs earn PENDLE rewards continuously."
    },
    "ambient_crocswap": {
        "name": "Ambient Finance Token",
        "token": "AMBIENT (speculative)",
        "status": "potential",
        "snapshot_date": "TBD",
        "claim_deadline": None,
        "criteria": ["provided liquidity on Ambient Finance (CrocSwap)",
                     "traded on Ambient DEX",
                     "used Ambient on multiple chains (Scroll, Blast, etc.)"],
        "checker_url": "https://ambient.finance",
        "chain": "ethereum",
        "notes": "No token yet. Active LP and traders on Ambient may qualify.",
        "qualifying_protocols": ["Ambient Finance"]
    },
    "blast_blast": {
        "name": "Blast BLAST",
        "token": "BLAST",
        "status": "ended",
        "snapshot_date": "2024-06-26",
        "claim_deadline": "2025-06-26",
        "criteria": ["bridged ETH to Blast L2",
                     "used Blast ecosystem dApps",
                     "earned Blast Gold points",
                     "provided liquidity on Blast DEXes"],
        "amount": "based on Blast Points and Gold",
        "checker_url": "https://blast.io/en/airdrop",
        "chain": "blast",
        "notes": "Points-based. ETH bridgers and active DeFi users on Blast qualified."
    },
    "taiko_taiko": {
        "name": "Taiko TAIKO",
        "token": "TAIKO",
        "status": "ended",
        "snapshot_date": "2024-05-01",
        "claim_deadline": "2025-05-01",
        "criteria": ["bridged to Taiko mainnet",
                     "ran a Taiko node",
                     "participated in Taiko testnets"],
        "amount": "varies",
        "checker_url": "https://taiko.xyz",
        "chain": "taiko",
        "notes": "Node operators and early testnet/mainnet users rewarded."
    },
    "mode_mode": {
        "name": "Mode Network MODE",
        "token": "MODE",
        "status": "ended",
        "snapshot_date": "2024-04-03",
        "claim_deadline": "2025-04-03",
        "criteria": ["bridged to Mode Network",
                     "used Mode ecosystem protocols",
                     "provided liquidity on Mode"],
        "amount": "based on points",
        "checker_url": "https://app.mode.network",
        "chain": "mode",
        "notes": "OP Stack L2 by Mode. Points accrued from ecosystem activity."
    },
}

FARMING_OPPORTUNITIES = [
    {
        "protocol":     "Zora",
        "chain":        "Base / Zora Network",
        "action":       "Mint NFTs, create collections, use Zora's social features",
        "why":          "No token yet. Coinbase-backed. Heavy NFT + social activity likely tracked.",
        "effort":       "Low",
        "url":          "https://zora.co"
    },
    {
        "protocol":     "Lens Protocol",
        "chain":        "Polygon / Lens Chain",
        "action":       "Create Lens profile, post, follow, collect, use Lens apps",
        "why":          "Major social layer with no token. Aave-backed. Profile + social activity likely counts.",
        "effort":       "Low",
        "url":          "https://lens.xyz"
    },
    {
        "protocol":     "Farcaster / Warpcast",
        "chain":        "Base / Optimism",
        "action":       "Cast, follow, build frames, use Farcaster apps",
        "why":          "On-chain social graph with a16z backing. No token, but massive ecosystem growing.",
        "effort":       "Low",
        "url":          "https://warpcast.com"
    },
    {
        "protocol":     "Aztec Network",
        "chain":        "Ethereum (ZK privacy layer)",
        "action":       "Use Aztec for private transactions when mainnet launches",
        "why":          "Privacy L2 with no token. ZK tech similar to zkSync. Mainnet expected soon.",
        "effort":       "Medium",
        "url":          "https://aztec.network"
    },
    {
        "protocol":     "Berachain",
        "chain":        "Berachain (EVM-compatible)",
        "action":       "Use BGT rewards, provide liquidity, use native DEXes (BEX, Berps)",
        "why":          "Novel PoL consensus. BERA launched. BEX, Honey, Berps ecosystem still farming.",
        "effort":       "Medium",
        "url":          "https://berachain.com"
    },
    {
        "protocol":     "Succinct / SP1",
        "chain":        "Ethereum (ZK prover)",
        "action":       "Use SP1 proofs in projects, contribute to ecosystem",
        "why":          "ZK proving infrastructure. Backed by Paradigm. Developer-focused potential airdrop.",
        "effort":       "High",
        "url":          "https://succinct.xyz"
    },
    {
        "protocol":     "Monad",
        "chain":        "Monad (EVM-compatible L1)",
        "action":       "Participate in testnet when available, use ecosystem dApps at launch",
        "why":          "High-performance EVM L1. $225M raised. Testnet activity commonly rewarded.",
        "effort":       "Medium",
        "url":          "https://monad.xyz"
    },
    {
        "protocol":     "MegaETH",
        "chain":        "MegaETH (EVM L2)",
        "action":       "Join waitlist, use testnet, participate in ecosystem",
        "why":          "Real-time blockchain. Heavy VC backing. Early users historically rewarded.",
        "effort":       "Low",
        "url":          "https://megaeth.systems"
    },
    {
        "protocol":     "Uniswap V4 / UniswapX",
        "chain":        "Ethereum / multi-chain",
        "action":       "Use Uniswap V4 hooks and UniswapX when live, provide hooks liquidity",
        "why":          "Uniswap Foundation has a grants program. V4 early LPs may receive additional incentives.",
        "effort":       "Medium",
        "url":          "https://uniswap.org"
    },
    {
        "protocol":     "Symbiotic",
        "chain":        "Ethereum",
        "action":       "Stake/restake assets in Symbiotic vaults, use supported collateral",
        "why":          "EigenLayer competitor backed by Paradigm and Cyber Fund. No token yet.",
        "effort":       "Medium",
        "url":          "https://symbiotic.fi"
    },
]

def _eth_balance(address: str) -> float:
    try:
        payload = {"jsonrpc": "2.0", "method": "eth_getBalance",
                   "params": [address, "latest"], "id": 1}
        r = requests.post(ETH_RPC, json=payload, timeout=10)
        return int(r.json().get("result", "0x0"), 16) / 1e18
    except Exception:
        return 0.0


def _tx_count(address: str) -> int:
    try:
        payload = {"jsonrpc": "2.0", "method": "eth_getTransactionCount",
                   "params": [address, "latest"], "id": 1}
        r = requests.post(ETH_RPC, json=payload, timeout=10)
        return int(r.json().get("result", "0x0"), 16)
    except Exception:
        return 0


def _first_tx_date(address: str) -> str | None:
    try:
        params = {
            "module": "account", "action": "txlist",
            "address": address, "startblock": 0,
            "endblock": 99999999, "page": 1, "offset": 1,
            "sort": "asc", "apikey": ETHERSCAN_KEY
        }
        r = requests.get(ETHERSCAN_API, params=params, timeout=10)
        d = r.json()
        if d.get("status") == "1" and d["result"]:
            ts = int(d["result"][0]["timeStamp"])
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        pass
    return None


def _token_activity(address: str) -> dict:
    """Return set of token contracts interacted with."""
    try:
        params = {
            "module": "account", "action": "tokentx",
            "address": address, "page": 1, "offset": 200,
            "sort": "desc", "apikey": ETHERSCAN_KEY
        }
        r = requests.get(ETHERSCAN_API, params=params, timeout=15)
        d = r.json()
        contracts = set()
        symbols   = set()
        if d.get("status") == "1":
            for tx in d["result"]:
                contracts.add(tx["contractAddress"].lower())
                symbols.add(tx["tokenSymbol"].upper())
        return {"contracts": contracts, "symbols": symbols}
    except Exception:
        return {"contracts": set(), "symbols": set()}


# Known contract addresses for eligibility checks
PROTOCOL_CONTRACTS = {
    # DEX routers / pools
    "uniswap_v2":   "0x7a250d5630b4cf539739df2c5dacb4c659f2488d",
    "uniswap_v3":   "0xe592427a0aece92de3edee1f18e0157c05861564",
    "1inch_v4":     "0x1111111254fb6c44bac0bed2854e76f90643097d",
    "sushiswap":    "0xd9e1ce17f2641f24ae83637ab66a2cca9c378b9f",
    # Bridges
    "arb_bridge":   "0x8315177ab297ba92a06054ce80a67ed4dbd7ed3a",
    "op_bridge":    "0x99c9fc46f92e8a1c0dec1b1747d010903e884be1",
    "zksync_bridge":"0x32400084c286cf3e17e7b677ea9583e60a000324",
    "stargate":     "0x8731d54e9d02c286767d56ac03e8037c07e01e98",
    # Lending
    "aave_v2":      "0x7d2768de32b0b80b7a3454c06bdac94a69ddc7a9",
    "aave_v3":      "0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2",
    "compound":     "0x3d9819210a31b4961b30ef54be2aed79b9c9cd3b",
    # Restaking
    "eigenlayer":   "0x858646372cc42e1a627be943df703adc26537d5",
}


# ─── Tool Functions ────────────────────────────────────────────────────────────

def get_airdrop_database(status_filter: str = "all") -> dict:
    """
    Return the full airdrop knowledge base, optionally filtered by status.
    status_filter: 'all' | 'potential' | 'confirmed' | 'ongoing' | 'ended'
    """
    filtered = {}
    for key, info in AIRDROP_DATABASE.items():
        if status_filter == "all" or info["status"] == status_filter:
            filtered[key] = {k: v for k, v in info.items() if k != "criteria"}

    return {
        "airdrops":       filtered,
        "count":          len(filtered),
        "status_filter":  status_filter,
        "categories": {
            "potential":  sum(1 for v in AIRDROP_DATABASE.values() if v["status"] == "potential"),
            "confirmed":  sum(1 for v in AIRDROP_DATABASE.values() if v["status"] == "confirmed"),
            "ongoing":    sum(1 for v in AIRDROP_DATABASE.values() if v["status"] == "ongoing"),
            "ended":      sum(1 for v in AIRDROP_DATABASE.values() if v["status"] == "ended"),
        }
    }


def check_wallet_eligibility(wallet_address: str) -> dict:
    """
    Analyse a wallet's on-chain history and cross-reference against
    known airdrop eligibility criteria in the database.
    Returns a scored eligibility report:
    - likely_eligible: airdrops you probably qualify for
    - possibly_eligible: partial criteria met
    - missed: ended airdrops you didn't claim
    - farming_score: how airdrop-optimised this wallet looks (0-100)
    """
    wallet_address = wallet_address.lower()

    # Gather wallet signals
    eth_bal    = _eth_balance(wallet_address)
    tx_count   = _tx_count(wallet_address)
    first_seen = _first_tx_date(wallet_address)
    tok_data   = _token_activity(wallet_address)
    token_syms = tok_data["symbols"]

    wallet_age_days = 0
    if first_seen:
        first_dt = datetime.strptime(first_seen, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        wallet_age_days = (datetime.now(timezone.utc) - first_dt).days

    # Fetch recent tx list for protocol interaction checks
    interacted_protocols = set()
    try:
        params = {
            "module": "account", "action": "txlist",
            "address": wallet_address,
            "startblock": 0, "endblock": 99999999,
            "page": 1, "offset": 200, "sort": "desc",
            "apikey": ETHERSCAN_KEY
        }
        r = requests.get(ETHERSCAN_API, params=params, timeout=15)
        data = r.json()
        if data.get("status") == "1":
            for tx in data["result"]:
                to = (tx.get("to") or "").lower()
                for proto, addr in PROTOCOL_CONTRACTS.items():
                    if to == addr.lower():
                        interacted_protocols.add(proto)
    except Exception:
        pass

    likely_eligible   = []
    possibly_eligible = []
    missed_airdrops   = []
    not_eligible      = []

    for key, airdrop in AIRDROP_DATABASE.items():
        status   = airdrop["status"]
        criteria = airdrop.get("criteria", [])
        matched  = []
        missed_c = []

        for c in criteria:
            c_lower = c.lower()
            hit = False

            # Bridge / protocol usage checks
            if "uniswap" in c_lower and ("uniswap_v2" in interacted_protocols or "uniswap_v3" in interacted_protocols):
                hit = True
            elif "1inch" in c_lower and "1inch_v4" in interacted_protocols:
                hit = True
            elif "aave" in c_lower and ("aave_v2" in interacted_protocols or "aave_v3" in interacted_protocols):
                hit = True
            elif "compound" in c_lower and "compound" in interacted_protocols:
                hit = True
            elif "arbitrum" in c_lower and ("ARB" in token_syms or "arb_bridge" in interacted_protocols):
                hit = True
            elif "optimism" in c_lower and ("OP" in token_syms or "op_bridge" in interacted_protocols):
                hit = True
            elif "zksync" in c_lower and "zksync_bridge" in interacted_protocols:
                hit = True
            elif "eigenlayer" in c_lower and "eigenlayer" in interacted_protocols:
                hit = True
            elif "stargate" in c_lower and "stargate" in interacted_protocols:
                hit = True
            elif "ens" in c_lower and "ENS" in token_syms:
                hit = True
            elif "dydx" in c_lower and "DYDX" in token_syms:
                hit = True
            elif "sushiswap" in c_lower and "sushiswap" in interacted_protocols:
                hit = True
            elif "transaction" in c_lower and tx_count > 10:
                hit = True
            elif "wallet age" in c_lower and wallet_age_days > 180:
                hit = True
            elif "multiple months" in c_lower and wallet_age_days > 90 and tx_count > 20:
                hit = True

            if hit:
                matched.append(c)
            else:
                missed_c.append(c)

        match_ratio = len(matched) / max(len(criteria), 1)

        if status == "ended":
            if match_ratio >= 0.5:
                missed_airdrops.append({
                    "airdrop":       airdrop["name"],
                    "token":         airdrop["token"],
                    "criteria_met":  matched,
                    "criteria_missed": missed_c,
                    "snapshot_date": airdrop["snapshot_date"],
                    "claim_deadline": airdrop.get("claim_deadline"),
                    "amount":        airdrop.get("amount", "unknown"),
                    "checker_url":   airdrop.get("checker_url"),
                    "notes":         airdrop.get("notes", ""),
                    "status":        "ended - claim period over"
                })
        elif status in ("potential", "confirmed", "ongoing"):
            if match_ratio >= 0.5:
                likely_eligible.append({
                    "airdrop":         airdrop["name"],
                    "token":           airdrop["token"],
                    "status":          status,
                    "criteria_met":    matched,
                    "criteria_missing": missed_c,
                    "snapshot_date":   airdrop["snapshot_date"],
                    "checker_url":     airdrop.get("checker_url"),
                    "qualifying_protocols": airdrop.get("qualifying_protocols", []),
                    "notes":           airdrop.get("notes", ""),
                    "confidence":      "HIGH" if match_ratio >= 0.75 else "MEDIUM"
                })
            elif match_ratio >= 0.25:
                possibly_eligible.append({
                    "airdrop":         airdrop["name"],
                    "token":           airdrop["token"],
                    "status":          status,
                    "criteria_met":    matched,
                    "criteria_missing": missed_c,
                    "actions_to_qualify": missed_c[:3],
                    "checker_url":     airdrop.get("checker_url"),
                    "notes":           airdrop.get("notes", ""),
                    "confidence":      "LOW"
                })

    # Farming score (0-100)
    score = 0
    if wallet_age_days > 365:  score += 20
    elif wallet_age_days > 180: score += 10
    if tx_count > 500:   score += 20
    elif tx_count > 100: score += 10
    if len(interacted_protocols) >= 5: score += 20
    elif len(interacted_protocols) >= 2: score += 10
    if len(token_syms) > 20: score += 20
    elif len(token_syms) > 5: score += 10
    if eth_bal > 0.5: score += 10
    if "ARB" in token_syms or "OP" in token_syms: score += 10

    return {
        "wallet":              wallet_address,
        "wallet_profile": {
            "eth_balance":         round(eth_bal, 4),
            "total_txs":           tx_count,
            "wallet_age_days":     wallet_age_days,
            "first_seen":          first_seen,
            "protocols_detected":  list(interacted_protocols),
            "tokens_interacted":   list(token_syms)[:20],
        },
        "likely_eligible":    likely_eligible,
        "possibly_eligible":  possibly_eligible,
        "missed_airdrops":    missed_airdrops,
        "airdrop_farming_score": min(score, 100),
        "farming_score_label": (
            "🏆 Expert Airdrop Farmer" if score >= 80 else
            "🟢 Active Farmer"        if score >= 60 else
            "🟡 Moderate Activity"    if score >= 40 else
            "🔴 Low Activity - Likely Missing Airdrops"
        ),
        "summary": (
            f"Found {len(likely_eligible)} likely + {len(possibly_eligible)} possible airdrops. "
            f"Missed {len(missed_airdrops)} historical airdrops."
        )
    }


def get_potential_airdrops() -> dict:
    """
    Return all potential / unconfirmed airdrops from the database
    with full criteria. These are protocols without a token that
    reward on-chain activity - what to farm RIGHT NOW.
    """
    potentials = {}
    for key, info in AIRDROP_DATABASE.items():
        if info["status"] in ("potential", "ongoing"):
            potentials[key] = info

    return {
        "potential_airdrops": potentials,
        "count":              len(potentials),
        "tip":                "Focus on protocols with no token yet. Interact with them across multiple months for best results."
    }


def get_missed_airdrops(wallet_address: str) -> dict:
    """
    Quick scan for historical (ended) airdrops the wallet may have
    been eligible for but didn't claim. Educational - helps understand
    what activity patterns to replicate for future drops.
    """
    result = check_wallet_eligibility(wallet_address)
    missed = result.get("missed_airdrops", [])

    # Estimate rough USD value at peak prices
    peak_prices = {
        "UNI": 40,    # peak ~$45
        "OP": 4.5,    # peak ~$4.8
        "ARB": 2.3,   # peak ~$2.4
        "ENS": 70,    # peak ~$85
        "DYDX": 7,    # peak ~$8
        "1INCH": 8,   # peak ~$8
        "ZRO": 4,
        "EIGEN": 5,
        "BLAST": 0.03,
        "TAIKO": 2,
    }

    for m in missed:
        sym = m.get("token", "").split()[0].replace("(speculative)", "").strip()
        px  = peak_prices.get(sym, 0)
        if px:
            m["estimated_peak_value_note"] = f"~${px}/token at peak price"

    estimated_total_missed = sum(
        peak_prices.get(m.get("token", "").split()[0], 0) * 400
        for m in missed
    )

    return {
        "wallet":           wallet_address,
        "missed_airdrops":  missed,
        "count":            len(missed),
        "rough_value_note": f"Rough estimate based on historical peak prices: could have been worth $X (highly variable by amount received)",
        "lesson":           "Replicate the on-chain patterns: use DEXes, bridge to L2s, use lending protocols, participate in governance."
    }


def get_farming_guide() -> dict:
    """
    Return a prioritised list of active farming opportunities -
    protocols worth interacting with NOW to maximise future airdrop chances.
    Includes effort level, reasoning, and direct links.
    """
    return {
        "farming_opportunities": FARMING_OPPORTUNITIES,
        "count":                 len(FARMING_OPPORTUNITIES),
        "general_tips": [
            "💡 Interact with protocols across MULTIPLE months - one-time interactions are often excluded",
            "💡 Use genuine DeFi activity: swap, provide liquidity, borrow/lend - don't just bridge and hold",
            "💡 Don't create multiple wallets and bridge between them - Sybil detection is sophisticated",
            "💡 Keep your wallet funded and active - dormant wallets after farming often disqualify",
            "💡 Use protocols on both mainnet AND their L2 deployments for maximum coverage",
            "💡 Participate in governance (vote on proposals) - many airdrops reward governance activity",
            "💡 Join protocol Discord/Telegram - insider info on snapshot dates appears there first",
            "💡 Testnet activity often counts - participate in testnets before mainnet launches",
        ],
        "priority_order": "Effort: Low → do immediately. Medium → schedule weekly. High → research first."
    }


def get_airdrop_news() -> dict:
    """
    Fetch latest airdrop-related news from CryptoPanic.
    Surfaces new airdrop announcements, eligibility checkers going live,
    snapshot date announcements.
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
        keywords = ["airdrop", "snapshot", "eligib", "claim", "token launch",
                    "token distribution", "retroactive", "points program", "farm"]

        airdrop_news = []
        for post in results:
            title = post.get("title", "").lower()
            if any(kw in title for kw in keywords):
                tokens = [c.get("code", "") for c in post.get("currencies", [])]
                airdrop_news.append({
                    "title":     post.get("title", ""),
                    "tokens":    tokens,
                    "source":    post.get("source", {}).get("title", ""),
                    "published": post.get("published_at", "")[:16].replace("T", " "),
                    "url":       post.get("url", "")
                })

        return {
            "airdrop_news": airdrop_news[:20],
            "count":        len(airdrop_news),
            "fetched_at":   datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        }
    except Exception as e:
        return {"error": str(e)}


def check_specific_airdrop(airdrop_key: str, wallet_address: str = None) -> dict:
    """
    Get detailed information about one specific airdrop by key,
    and optionally check a wallet's eligibility for it.
    airdrop_key: key from AIRDROP_DATABASE e.g. 'arbitrum_arb', 'zksync_zk'
    """
    airdrop = AIRDROP_DATABASE.get(airdrop_key)
    if not airdrop:
        available = list(AIRDROP_DATABASE.keys())
        return {"error": f"Unknown airdrop key '{airdrop_key}'.", "available_keys": available}

    result = dict(airdrop)

    if wallet_address:
        wallet_address = wallet_address.lower()
        tok_data   = _token_activity(wallet_address)
        tx_count   = _tx_count(wallet_address)
        first_seen = _first_tx_date(wallet_address)
        syms       = tok_data["symbols"]

        wallet_age_days = 0
        if first_seen:
            first_dt = datetime.strptime(first_seen, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            wallet_age_days = (datetime.now(timezone.utc) - first_dt).days

        # Fetch protocols interacted with
        interacted = set()
        try:
            params = {
                "module": "account", "action": "txlist",
                "address": wallet_address,
                "startblock": 0, "endblock": 99999999,
                "page": 1, "offset": 100, "sort": "desc",
                "apikey": ETHERSCAN_KEY
            }
            r = requests.get(ETHERSCAN_API, params=params, timeout=12)
            d = r.json()
            if d.get("status") == "1":
                for tx in d["result"]:
                    to = (tx.get("to") or "").lower()
                    for proto, addr in PROTOCOL_CONTRACTS.items():
                        if to == addr.lower():
                            interacted.add(proto)
        except Exception:
            pass

        criteria  = airdrop.get("criteria", [])
        met       = []
        not_met   = []

        for c in criteria:
            cl = c.lower()
            hit = any([
                "uniswap" in cl and ("uniswap_v2" in interacted or "uniswap_v3" in interacted),
                "1inch"   in cl and "1inch_v4" in interacted,
                "aave"    in cl and ("aave_v2" in interacted or "aave_v3" in interacted),
                "arb"     in cl and ("ARB" in syms or "arb_bridge" in interacted),
                "optimism" in cl and ("OP" in syms or "op_bridge" in interacted),
                "zksync"  in cl and "zksync_bridge" in interacted,
                "eigen"   in cl and "eigenlayer" in interacted,
                "ens"     in cl and "ENS" in syms,
                "transaction" in cl and tx_count > 10,
                "multiple months" in cl and wallet_age_days > 90,
            ])
            (met if hit else not_met).append(c)

        match_pct = round(len(met) / max(len(criteria), 1) * 100)
        result["wallet_check"] = {
            "wallet":        wallet_address,
            "criteria_met":  met,
            "criteria_unmet": not_met,
            "match_pct":     match_pct,
            "verdict": (
                "✅ LIKELY ELIGIBLE"     if match_pct >= 60 else
                "🟡 POSSIBLY ELIGIBLE"  if match_pct >= 30 else
                "❌ LIKELY NOT ELIGIBLE"
            ),
            "checker_url": airdrop.get("checker_url")
        }

    return result


def get_active_claim_windows() -> dict:
    """
    Return all airdrops that are currently in an active claim window
    (confirmed and not yet past claim deadline). URGENT - claim before deadline!
    """
    now = datetime.now(timezone.utc).date()
    claimable = []
    expired   = []

    for key, info in AIRDROP_DATABASE.items():
        if info["status"] not in ("confirmed", "ended"):
            continue

        deadline = info.get("claim_deadline")
        if not deadline:
            continue

        try:
            dl_date = datetime.strptime(deadline, "%Y-%m-%d").date()
        except Exception:
            continue

        days_left = (dl_date - now).days

        entry = {
            "airdrop":        info["name"],
            "token":          info["token"],
            "claim_deadline": deadline,
            "days_remaining": days_left,
            "checker_url":    info.get("checker_url"),
            "amount":         info.get("amount", "varies"),
            "urgency": (
                "🔴 URGENT - expires soon!" if 0 < days_left <= 14 else
                "🟡 Claim soon"             if 0 < days_left <= 60 else
                "🟢 Plenty of time"
            ) if days_left > 0 else "❌ EXPIRED"
        }

        if days_left > 0:
            claimable.append(entry)
        else:
            expired.append(entry)

    claimable.sort(key=lambda x: x["days_remaining"])

    return {
        "active_claim_windows": claimable,
        "recently_expired":     expired[-5:],
        "claimable_count":      len(claimable),
        "urgent_count":         sum(1 for c in claimable if "URGENT" in c["urgency"]),
        "tip":                  "Check each checker_url with your wallet to verify eligibility."
    }


def get_wallet_farming_score(wallet_address: str) -> dict:
    """
    Score a wallet's airdrop farming readiness and suggest
    specific actions to improve eligibility for potential airdrops.
    Returns score 0-100 with improvement recommendations.
    """
    result     = check_wallet_eligibility(wallet_address)
    profile    = result.get("wallet_profile", {})
    score      = result.get("airdrop_farming_score", 0)
    interacted = set(profile.get("protocols_detected", []))
    syms       = set(profile.get("tokens_interacted", []))
    age        = profile.get("wallet_age_days", 0)
    txs        = profile.get("total_txs", 0)

    recommendations = []

    if age < 180:
        recommendations.append({
            "action":  "Age your wallet",
            "detail":  "Wallet is less than 6 months old. Use it consistently for 6-12 months.",
            "impact":  "HIGH - most airdrops exclude brand-new wallets"
        })
    if txs < 50:
        recommendations.append({
            "action":  "Increase transaction count",
            "detail":  f"Only {txs} txs. Aim for 100+ by using DEXes and DeFi protocols regularly.",
            "impact":  "HIGH"
        })
    if "uniswap_v3" not in interacted:
        recommendations.append({
            "action":  "Use Uniswap V3",
            "detail":  "Swap tokens on Uniswap V3. One of the most common eligibility criteria.",
            "impact":  "HIGH"
        })
    if "aave_v3" not in interacted:
        recommendations.append({
            "action":  "Use Aave V3",
            "detail":  "Deposit or borrow on Aave V3. Lending protocol usage often rewarded.",
            "impact":  "MEDIUM"
        })
    if "arb_bridge" not in interacted and "ARB" not in syms:
        recommendations.append({
            "action":  "Bridge to Arbitrum",
            "detail":  "Use the official Arbitrum bridge. Arbitrum ecosystem activity is heavily tracked.",
            "impact":  "HIGH"
        })
    if "op_bridge" not in interacted and "OP" not in syms:
        recommendations.append({
            "action":  "Bridge to Optimism",
            "detail":  "Use the Optimism bridge and use Optimism dApps monthly.",
            "impact":  "HIGH"
        })
    if "zksync_bridge" not in interacted:
        recommendations.append({
            "action":  "Use zkSync Era",
            "detail":  "Bridge to zkSync Era, swap on SyncSwap, use protocol 3-4x/month.",
            "impact":  "HIGH - major potential airdrop"
        })
    if "eigenlayer" not in interacted:
        recommendations.append({
            "action":  "Restake on EigenLayer or Symbiotic",
            "detail":  "Restaking is a major trend. Use EigenLayer for restaking ETH or LSTs.",
            "impact":  "MEDIUM"
        })
    if "ENS" not in syms:
        recommendations.append({
            "action":  "Register an ENS name",
            "detail":  "Register yourname.eth. ENS ownership was a core qualifier for the ENS airdrop.",
            "impact":  "MEDIUM - signals serious ETH user"
        })

    return {
        "wallet":                wallet_address,
        "farming_score":         score,
        "farming_label":         result.get("farming_score_label"),
        "protocols_detected":    list(interacted),
        "tokens_seen":           list(syms)[:15],
        "wallet_age_days":       age,
        "total_txs":             txs,
        "recommendations":       recommendations,
        "priority_actions":      [r["action"] for r in recommendations[:3]],
        "likely_eligible_count": len(result.get("likely_eligible", [])),
        "possibly_eligible_count": len(result.get("possibly_eligible", []))
    }


# ─── Tool Registry ─────────────────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_airdrop_database",
            "description": "Return the full list of tracked airdrops with status, criteria, and links. Use status_filter='potential' for unconfirmed drops to farm, 'confirmed' for ones with live claim windows.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status_filter": {
                        "type": "string",
                        "description": "'all', 'potential', 'confirmed', 'ongoing', 'ended' (default 'all')"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_wallet_eligibility",
            "description": "Full eligibility scan for a wallet against all known airdrops. Returns likely_eligible, possibly_eligible, and missed airdrops based on on-chain activity. THE primary tool when asked 'which airdrops am I eligible for?'.",
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
            "name": "get_potential_airdrops",
            "description": "Return all potential/unconfirmed airdrops from protocols that haven't launched a token yet - what to farm RIGHT NOW for future eligibility.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_missed_airdrops",
            "description": "Check which historical airdrops a wallet likely missed, with estimated value and lessons learned for future farming.",
            "parameters": {
                "type": "object",
                "properties": {
                    "wallet_address": {"type": "string", "description": "Ethereum wallet address"}
                },
                "required": ["wallet_address"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_farming_guide",
            "description": "Return a prioritised guide of active farming opportunities - protocols to interact with NOW for future airdrops. Includes effort level and reasoning.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_airdrop_news",
            "description": "Fetch latest airdrop-related news: new announcements, snapshot dates going live, eligibility checker launches.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_specific_airdrop",
            "description": "Get full details about one specific airdrop by key (e.g. 'arbitrum_arb', 'zksync_zk') and optionally check a wallet's eligibility for it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "airdrop_key":    {"type": "string", "description": "Airdrop key from the database e.g. 'arbitrum_arb', 'zksync_zk', 'eigenlayer_eigen'"},
                    "wallet_address": {"type": "string", "description": "Optional wallet address to check eligibility"}
                },
                "required": ["airdrop_key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_active_claim_windows",
            "description": "Return all airdrops currently in an active claim window (can still be claimed). Sorted by deadline urgency - check FIRST if someone asks about claiming.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_wallet_farming_score",
            "description": "Score a wallet 0-100 on airdrop farming readiness and give specific improvement recommendations. Use when someone asks 'how can I improve my airdrop chances?' or 'how good is my wallet for airdrops?'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "wallet_address": {"type": "string", "description": "Ethereum wallet address"}
                },
                "required": ["wallet_address"]
            }
        }
    }
]

TOOL_MAP = {
    "get_airdrop_database":      get_airdrop_database,
    "check_wallet_eligibility":  check_wallet_eligibility,
    "get_potential_airdrops":    get_potential_airdrops,
    "get_missed_airdrops":       get_missed_airdrops,
    "get_farming_guide":         get_farming_guide,
    "get_airdrop_news":          get_airdrop_news,
    "check_specific_airdrop":    check_specific_airdrop,
    "get_active_claim_windows":  get_active_claim_windows,
    "get_wallet_farming_score":  get_wallet_farming_score,
}

SYSTEM_PROMPT = """You are a crypto airdrop hunter AI agent. You track potential airdrops, check wallet eligibility, surface missed opportunities, and guide users on how to maximise future airdrop chances.

## Query flows:

### "Which airdrops am I eligible for?" / eligibility check
1. check_wallet_eligibility(wallet_address)
2. get_active_claim_windows()  ← check for urgent claims
→ Present: likely eligible, possibly eligible, missed, farming score

### "What airdrops can I still claim?"
→ get_active_claim_windows()  ← sorted by urgency

### "What did I miss?" / missed opportunities
→ get_missed_airdrops(wallet_address)

### "How can I improve my airdrop chances?" / farming score
→ get_wallet_farming_score(wallet_address)

### "What should I farm right now?"
→ get_potential_airdrops()
→ get_farming_guide()

### "Tell me about [specific airdrop]"
→ check_specific_airdrop(airdrop_key)
→ Use get_airdrop_database() first if unsure of the key

### "Latest airdrop news"
→ get_airdrop_news()

## Output style:
- Lead with the most actionable info: urgent claims first, then eligible drops
- Use ✅ LIKELY / 🟡 POSSIBLE / ❌ UNLIKELY for eligibility
- For missed airdrops, include estimated value and lesson
- For farming guide, group by effort level (Low / Medium / High)
- Always include checker URLs so users can verify themselves
- Flag 🔴 URGENT for claim windows closing within 14 days
- End with: "Always verify eligibility on official checker URLs. This is not financial advice."
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
        return json.dumps(result, default=lambda o: list(o) if isinstance(o, set) else str(o), indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


def run_agent(user_input: str, conversation_history: list) -> tuple[str, list]:
    conversation_history.append({"role": "user", "content": user_input})
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + conversation_history

    max_iterations = 10
    for _ in range(max_iterations):
        response   = call_ollama(messages)
        message    = response["message"]
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
    print("  🪂 Airdrop Hunter AI Agent")
    print("  Tracks: Eligibility · Missed Drops · Farming Opportunities")
    print("  Powered by Ollama + Etherscan + CoinGecko + CryptoPanic")
    print("=" * 65)
    print(f"  Model: {MODEL}")
    print()
    print("  Tracked airdrops: UNI, OP, ARB, ENS, DYDX, 1INCH,")
    print("  ZRO, EIGEN, BLAST, TAIKO, HYPE + potential: zkSync,")
    print("  StarkNet S2, Scroll, Linea, Ambient, and more")
    print()
    print("  Example queries:")
    print("  • Which airdrops am I likely eligible for?")
    print("    (wallet: 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045)")
    print("  • What airdrops can I still claim?")
    print("  • What did I miss? (wallet: 0x...)")
    print("  • How can I improve my airdrop farming score?")
    print("  • What should I farm right now?")
    print("  • Tell me about the zkSync airdrop")
    print("  • Latest airdrop news")
    print("  • Show all potential airdrops")
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