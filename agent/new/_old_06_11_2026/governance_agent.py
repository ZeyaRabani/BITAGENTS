"""
Governance AI Agent using Ollama + Tool Calling
Tracks: DAO proposals, voting deadlines, governance changes.
Data sources: Snapshot (off-chain), Tally (on-chain), direct contract calls.
"""

import json
import requests
from datetime import datetime, timezone
from typing import Any

# ─── Configuration ────────────────────────────────────────────────────────────
OLLAMA_URL    = "http://localhost:11434/api/chat"
MODEL         = "llama3.1"

ETH_RPC          = "https://eth.llamarpc.com"
ETHERSCAN_API    = "https://api.etherscan.io/api"
ETHERSCAN_KEY    = "YourApiKeyToken"   # free → https://etherscan.io/apis

# Snapshot GraphQL (free, no key)
SNAPSHOT_GQL     = "https://hub.snapshot.org/graphql"

# Tally GraphQL (free tier, no key needed for basic queries)
TALLY_GQL        = "https://api.tally.xyz/query"
TALLY_API_KEY    = ""   # optional - get free key at https://www.tally.xyz/

# ─── Known DAO registry ───────────────────────────────────────────────────────
# Maps token symbol / protocol name → Snapshot space ID + Tally governor address
DAO_REGISTRY = {
    "uniswap":    {"snapshot": "uniswapgovernance.eth",  "tally": "eip155:1:0x408ED6354d4973f66138C91495F2f2FCbd8724C3", "token": "UNI"},
    "aave":       {"snapshot": "aave.eth",               "tally": "eip155:1:0xEC568fffba86c094cf06b22134B23074DFE2252c", "token": "AAVE"},
    "compound":   {"snapshot": "comp-vote.eth",          "tally": "eip155:1:0xc0Da02939E1441F497fd74F78cE7Decb17B66529", "token": "COMP"},
    "curve":      {"snapshot": "curve.eth",              "tally": None,                                                  "token": "CRV"},
    "maker":      {"snapshot": "makerdao.eth",           "tally": None,                                                  "token": "MKR"},
    "balancer":   {"snapshot": "balancer.eth",           "tally": "eip155:1:0x1b3C9aD7BBC2b55005d04C18e5ee86E43a7F5D8e", "token": "BAL"},
    "1inch":      {"snapshot": "1inch.eth",              "tally": None,                                                  "token": "1INCH"},
    "optimism":   {"snapshot": "opcollective.eth",       "tally": "eip155:10:0xcDF27F107725988f2261Ce2256bDfCdE8B382B10", "token": "OP"},
    "arbitrum":   {"snapshot": "arbitrumfoundation.eth", "tally": "eip155:42161:0xf07DeD9dC292157749B6Fd268E37DF6EA38395B9","token": "ARB"},
    "ens":        {"snapshot": "ens.eth",                "tally": "eip155:1:0x323A76393544d5ecca80cd6ef2A560C6a395b7E3", "token": "ENS"},
    "gitcoin":    {"snapshot": "gitcoindao.eth",         "tally": "eip155:1:0xDbD27635A534A3d3169Ef0498beB56Fb9c937489", "token": "GTC"},
    "sushi":      {"snapshot": "sushigov.eth",           "tally": None,                                                  "token": "SUSHI"},
    "yearn":      {"snapshot": "yearn.eth",              "tally": None,                                                  "token": "YFI"},
    "lido":       {"snapshot": "lido-snapshot.eth",      "tally": None,                                                  "token": "LDO"},
    "frax":       {"snapshot": "frax.eth",               "tally": None,                                                  "token": "FRAX"},
    "synthetix":  {"snapshot": "synthetix.eth",          "tally": None,                                                  "token": "SNX"},
    "decentraland":{"snapshot": "snapshot.dcl.eth",      "tally": None,                                                  "token": "MANA"},
    "the-graph":  {"snapshot": "graphprotocol.eth",      "tally": None,                                                  "token": "GRT"},
    "fetch-ai":   {"snapshot": "fetchai.eth",            "tally": None,                                                  "token": "FET"},
    "render-token":{"snapshot": "render.eth",            "tally": None,                                                  "token": "RNDR"},
}

# Reverse lookup: token symbol → DAO key
TOKEN_TO_DAO = {v["token"].upper(): k for k, v in DAO_REGISTRY.items()}


# ─── Tool Functions ────────────────────────────────────────────────────────────

def list_supported_daos() -> dict:
    """Return all DAOs tracked by this agent with their token symbols."""
    return {
        "supported_daos": [
            {"dao": k, "token": v["token"],
             "snapshot_space": v["snapshot"],
             "has_tally": v["tally"] is not None}
            for k, v in DAO_REGISTRY.items()
        ],
        "total": len(DAO_REGISTRY),
        "tip": "Use the dao name (e.g. 'uniswap') or token symbol (e.g. 'UNI') in other tools."
    }


def get_active_proposals(dao_name: str, limit: int = 10) -> dict:
    """
    Fetch currently active (open for voting) proposals from Snapshot
    for a given DAO. Returns proposal title, state, vote counts,
    quorum, start/end times, and a direct link.
    dao_name: key from DAO_REGISTRY e.g. 'uniswap', 'aave', or token symbol 'UNI'.
    """
    dao_name = dao_name.lower().strip()
    # Allow token symbol lookup
    if dao_name.upper() in TOKEN_TO_DAO:
        dao_name = TOKEN_TO_DAO[dao_name.upper()]

    dao = DAO_REGISTRY.get(dao_name)
    if not dao:
        return {"error": f"DAO '{dao_name}' not in registry. Call list_supported_daos() to see options."}

    space = dao["snapshot"]
    query = """
    query ActiveProposals($space: String!, $limit: Int!) {
      proposals(
        first: $limit,
        skip: 0,
        where: { space: $space, state: "active" },
        orderBy: "end", orderDirection: asc
      ) {
        id title state author body
        start end
        scores scores_total scores_by_strategy
        quorum votes
        choices
        space { id name }
      }
    }
    """
    try:
        r = requests.post(SNAPSHOT_GQL,
                          json={"query": query, "variables": {"space": space, "limit": limit}},
                          timeout=15)
        data = r.json()
        proposals = data.get("data", {}).get("proposals", [])

        now = datetime.now(timezone.utc).timestamp()
        enriched = []
        for p in proposals:
            end_ts   = p.get("end", 0)
            hours_left = (end_ts - now) / 3600
            choices  = p.get("choices", [])
            scores   = p.get("scores", [])
            total    = p.get("scores_total", 0) or 1

            vote_breakdown = {
                choices[i]: {"votes": round(scores[i], 2),
                             "pct": round(scores[i] / total * 100, 1)}
                for i in range(min(len(choices), len(scores)))
            }
            enriched.append({
                "id": p["id"],
                "title": p["title"],
                "state": p["state"],
                "author": p.get("author", ""),
                "hours_remaining": round(hours_left, 1),
                "deadline": datetime.fromtimestamp(end_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                "started": datetime.fromtimestamp(p.get("start", 0), tz=timezone.utc).strftime("%Y-%m-%d"),
                "total_votes": p.get("votes", 0),
                "total_voting_power": round(total, 2),
                "quorum": p.get("quorum", 0),
                "quorum_reached": total >= (p.get("quorum") or 0),
                "vote_breakdown": vote_breakdown,
                "leading_choice": max(vote_breakdown, key=lambda c: vote_breakdown[c]["votes"]) if vote_breakdown else "N/A",
                "link": f"https://snapshot.org/#/{space}/proposal/{p['id']}"
            })

        return {
            "dao": dao_name,
            "space": space,
            "active_proposals": enriched,
            "count": len(enriched),
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        }
    except Exception as e:
        return {"error": str(e)}


def get_recent_proposals(dao_name: str, limit: int = 10, state: str = "closed") -> dict:
    """
    Fetch recently closed or pending proposals from Snapshot.
    state: 'closed' (recently decided) or 'pending' (not yet started).
    dao_name: DAO name or token symbol.
    """
    dao_name = dao_name.lower().strip()
    if dao_name.upper() in TOKEN_TO_DAO:
        dao_name = TOKEN_TO_DAO[dao_name.upper()]

    dao = DAO_REGISTRY.get(dao_name)
    if not dao:
        return {"error": f"DAO '{dao_name}' not found."}

    space = dao["snapshot"]
    query = """
    query RecentProposals($space: String!, $limit: Int!, $state: String!) {
      proposals(
        first: $limit,
        where: { space: $space, state: $state },
        orderBy: "end", orderDirection: desc
      ) {
        id title state author
        start end
        scores scores_total votes choices quorum
      }
    }
    """
    try:
        r = requests.post(SNAPSHOT_GQL,
                          json={"query": query,
                                "variables": {"space": space, "limit": limit, "state": state}},
                          timeout=15)
        data = r.json()
        proposals = data.get("data", {}).get("proposals", [])

        results = []
        for p in proposals:
            choices = p.get("choices", [])
            scores  = p.get("scores", [])
            total   = p.get("scores_total", 0) or 1
            winner  = None
            if choices and scores:
                winner = choices[scores.index(max(scores))] if scores else None

            results.append({
                "id": p["id"],
                "title": p["title"],
                "state": p["state"],
                "ended": datetime.fromtimestamp(p.get("end", 0), tz=timezone.utc).strftime("%Y-%m-%d"),
                "total_votes": p.get("votes", 0),
                "winning_choice": winner,
                "winning_pct": round(max(scores) / total * 100, 1) if scores else None,
                "quorum_reached": total >= (p.get("quorum") or 0),
                "link": f"https://snapshot.org/#/{space}/proposal/{p['id']}"
            })

        return {
            "dao": dao_name,
            "state_filter": state,
            "proposals": results,
            "count": len(results)
        }
    except Exception as e:
        return {"error": str(e)}


def get_proposal_detail(dao_name: str, proposal_id: str) -> dict:
    """
    Fetch full detail for a single Snapshot proposal including
    the full description body, all vote scores, and metadata.
    proposal_id: the Snapshot proposal ID (from get_active_proposals).
    """
    dao_name = dao_name.lower().strip()
    if dao_name.upper() in TOKEN_TO_DAO:
        dao_name = TOKEN_TO_DAO[dao_name.upper()]

    dao = DAO_REGISTRY.get(dao_name)
    if not dao:
        return {"error": f"DAO '{dao_name}' not found."}

    query = """
    query Proposal($id: String!) {
      proposal(id: $id) {
        id title body state author
        start end created
        choices scores scores_total votes quorum
        strategies { name params }
        space { id name }
      }
    }
    """
    try:
        r = requests.post(SNAPSHOT_GQL,
                          json={"query": query, "variables": {"id": proposal_id}},
                          timeout=15)
        p = r.json().get("data", {}).get("proposal")
        if not p:
            return {"error": f"Proposal {proposal_id} not found"}

        choices = p.get("choices", [])
        scores  = p.get("scores", [])
        total   = p.get("scores_total", 0) or 1

        return {
            "id": p["id"],
            "title": p["title"],
            "body": (p.get("body") or "")[:1500] + ("..." if len(p.get("body") or "") > 1500 else ""),
            "state": p["state"],
            "author": p.get("author"),
            "created": datetime.fromtimestamp(p.get("created", 0), tz=timezone.utc).strftime("%Y-%m-%d"),
            "voting_start": datetime.fromtimestamp(p.get("start", 0), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "voting_end": datetime.fromtimestamp(p.get("end", 0), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "total_votes_cast": p.get("votes", 0),
            "total_voting_power": round(total, 2),
            "quorum": p.get("quorum", 0),
            "quorum_reached": total >= (p.get("quorum") or 0),
            "vote_breakdown": {
                choices[i]: {
                    "power": round(scores[i], 2),
                    "pct": round(scores[i] / total * 100, 1)
                }
                for i in range(min(len(choices), len(scores)))
            },
            "link": f"https://snapshot.org/#/{dao['snapshot']}/proposal/{p['id']}"
        }
    except Exception as e:
        return {"error": str(e)}


def get_voting_deadlines(dao_names: list) -> dict:
    """
    Get a consolidated deadline calendar across multiple DAOs.
    Shows all active proposals ordered by soonest deadline.
    dao_names: list of DAO names or token symbols e.g. ['uniswap', 'aave', 'UNI']
    """
    all_deadlines = []
    errors = []
    now_ts = datetime.now(timezone.utc).timestamp()

    for name in dao_names:
        name = name.lower().strip()
        if name.upper() in TOKEN_TO_DAO:
            name = TOKEN_TO_DAO[name.upper()]

        dao = DAO_REGISTRY.get(name)
        if not dao:
            errors.append(f"'{name}' not in registry")
            continue

        space = dao["snapshot"]
        query = """
        query($space: String!) {
          proposals(first: 5, where: {space: $space, state: "active"},
                    orderBy: "end", orderDirection: asc) {
            id title end votes scores_total quorum
          }
        }
        """
        try:
            r = requests.post(SNAPSHOT_GQL,
                              json={"query": query, "variables": {"space": space}},
                              timeout=12)
            proposals = r.json().get("data", {}).get("proposals", [])
            for p in proposals:
                end_ts     = p.get("end", 0)
                hours_left = (end_ts - now_ts) / 3600
                urgency    = (
                    "🔴 URGENT (<6h)" if hours_left < 6 else
                    "🟡 Soon (<24h)"  if hours_left < 24 else
                    "🟢 Upcoming"
                )
                all_deadlines.append({
                    "dao": name.upper(),
                    "token": dao["token"],
                    "title": p["title"],
                    "deadline": datetime.fromtimestamp(end_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                    "hours_remaining": round(hours_left, 1),
                    "urgency": urgency,
                    "votes_cast": p.get("votes", 0),
                    "link": f"https://snapshot.org/#/{space}/proposal/{p['id']}"
                })
        except Exception as e:
            errors.append(f"{name}: {e}")

    all_deadlines.sort(key=lambda x: x["hours_remaining"])

    return {
        "voting_deadlines": all_deadlines,
        "total_active": len(all_deadlines),
        "daos_checked": len(dao_names),
        "errors": errors,
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    }


def get_portfolio_governance_summary(token_symbols: list) -> dict:
    """
    Given a list of token symbols held in a portfolio, find all active
    governance votes that affect those tokens.
    Example: token_symbols=['UNI','AAVE','CRV','ARB']
    Returns all active proposals the user should be aware of and vote on.
    """
    results = {}
    no_dao  = []
    now_ts  = datetime.now(timezone.utc).timestamp()

    for sym in token_symbols:
        sym_up = sym.upper().strip()
        dao_key = TOKEN_TO_DAO.get(sym_up)
        if not dao_key:
            no_dao.append(sym_up)
            continue

        dao = DAO_REGISTRY[dao_key]
        space = dao["snapshot"]
        query = """
        query($space: String!) {
          proposals(first: 5, where: {space: $space, state: "active"},
                    orderBy: "end", orderDirection: asc) {
            id title end votes scores_total quorum choices scores
          }
        }
        """
        try:
            r = requests.post(SNAPSHOT_GQL,
                              json={"query": query, "variables": {"space": space}},
                              timeout=12)
            proposals = r.json().get("data", {}).get("proposals", [])

            active = []
            for p in proposals:
                end_ts     = p.get("end", 0)
                hours_left = (end_ts - now_ts) / 3600
                choices    = p.get("choices", [])
                scores     = p.get("scores", [])
                total      = p.get("scores_total", 0) or 1
                leading    = choices[scores.index(max(scores))] if scores and choices else "N/A"

                active.append({
                    "title": p["title"],
                    "hours_remaining": round(hours_left, 1),
                    "deadline": datetime.fromtimestamp(end_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                    "leading_choice": leading,
                    "leading_pct": round(max(scores) / total * 100, 1) if scores else None,
                    "votes_cast": p.get("votes", 0),
                    "link": f"https://snapshot.org/#/{space}/proposal/{p['id']}"
                })

            results[sym_up] = {
                "dao": dao_key,
                "active_proposals": active,
                "count": len(active)
            }
        except Exception as e:
            results[sym_up] = {"error": str(e)}

    total_active = sum(v.get("count", 0) for v in results.values() if "count" in v)

    return {
        "portfolio_tokens_checked": list(results.keys()),
        "tokens_without_dao": no_dao,
        "results_by_token": results,
        "total_active_votes": total_active,
        "action_needed": total_active > 0,
        "summary": (
            f"⚠️ {total_active} active governance vote(s) affecting your portfolio - review and vote!"
            if total_active > 0
            else "✅ No active governance votes for your portfolio tokens right now."
        )
    }


def get_governance_changes_history(dao_name: str, limit: int = 10) -> dict:
    """
    Fetch recently passed/failed proposals to track what governance
    changes have been made to a protocol. Returns the outcome of each
    recent vote and whether it passed.
    """
    dao_name = dao_name.lower().strip()
    if dao_name.upper() in TOKEN_TO_DAO:
        dao_name = TOKEN_TO_DAO[dao_name.upper()]

    dao = DAO_REGISTRY.get(dao_name)
    if not dao:
        return {"error": f"DAO '{dao_name}' not found."}

    space = dao["snapshot"]
    query = """
    query($space: String!, $limit: Int!) {
      proposals(
        first: $limit,
        where: { space: $space, state: "closed" },
        orderBy: "end", orderDirection: desc
      ) {
        id title state end votes
        choices scores scores_total quorum
      }
    }
    """
    try:
        r = requests.post(SNAPSHOT_GQL,
                          json={"query": query, "variables": {"space": space, "limit": limit}},
                          timeout=15)
        proposals = r.json().get("data", {}).get("proposals", [])

        changes = []
        for p in proposals:
            choices = p.get("choices", [])
            scores  = p.get("scores", [])
            total   = p.get("scores_total", 0) or 1
            quorum  = p.get("quorum") or 0

            passed_quorum = total >= quorum
            winner = None
            winner_pct = None
            if scores and choices:
                max_score = max(scores)
                winner = choices[scores.index(max_score)]
                winner_pct = round(max_score / total * 100, 1)

            # Rough pass/fail: quorum reached + "For"/"Yes"/"Yae" variant winning
            likely_passed = (
                passed_quorum and
                winner and
                any(k in winner.lower() for k in ["for", "yes", "yae", "yea", "approve", "accept"])
            )

            changes.append({
                "title": p["title"],
                "ended": datetime.fromtimestamp(p.get("end", 0), tz=timezone.utc).strftime("%Y-%m-%d"),
                "outcome": winner,
                "outcome_pct": winner_pct,
                "quorum_reached": passed_quorum,
                "likely_passed": likely_passed,
                "total_votes": p.get("votes", 0),
                "result_label": "✅ Passed" if likely_passed else ("❌ Failed" if passed_quorum else "⚠️ No quorum"),
                "link": f"https://snapshot.org/#/{space}/proposal/{p['id']}"
            })

        return {
            "dao": dao_name,
            "token": dao["token"],
            "recent_governance_changes": changes,
            "count": len(changes),
            "note": "Pass/fail detection is heuristic - verify on the Snapshot link for official result."
        }
    except Exception as e:
        return {"error": str(e)}


def search_proposals(dao_name: str, keyword: str, limit: int = 10) -> dict:
    """
    Search proposals in a DAO by keyword in the title.
    Useful for finding proposals about specific topics
    e.g. 'fee', 'treasury', 'risk', 'upgrade', 'grant'.
    """
    dao_name = dao_name.lower().strip()
    if dao_name.upper() in TOKEN_TO_DAO:
        dao_name = TOKEN_TO_DAO[dao_name.upper()]

    dao = DAO_REGISTRY.get(dao_name)
    if not dao:
        return {"error": f"DAO '{dao_name}' not found."}

    space = dao["snapshot"]
    # Snapshot doesn't support full-text search via GraphQL, so we fetch
    # recent proposals and filter client-side
    query = """
    query($space: String!, $limit: Int!) {
      proposals(
        first: $limit,
        where: { space: $space },
        orderBy: "created", orderDirection: desc
      ) {
        id title state end votes scores_total choices scores
      }
    }
    """
    try:
        r = requests.post(SNAPSHOT_GQL,
                          json={"query": query, "variables": {"space": space, "limit": 50}},
                          timeout=15)
        all_proposals = r.json().get("data", {}).get("proposals", [])

        keyword_lower = keyword.lower()
        matched = [p for p in all_proposals if keyword_lower in p.get("title", "").lower()][:limit]

        results = []
        for p in matched:
            choices = p.get("choices", [])
            scores  = p.get("scores", [])
            total   = p.get("scores_total", 0) or 1
            winner  = choices[scores.index(max(scores))] if scores and choices else "N/A"

            results.append({
                "title": p["title"],
                "state": p["state"],
                "ended_or_ends": datetime.fromtimestamp(p.get("end", 0), tz=timezone.utc).strftime("%Y-%m-%d"),
                "outcome": winner,
                "outcome_pct": round(max(scores) / total * 100, 1) if scores else None,
                "total_votes": p.get("votes", 0),
                "link": f"https://snapshot.org/#/{space}/proposal/{p['id']}"
            })

        return {
            "dao": dao_name,
            "keyword": keyword,
            "matched_proposals": results,
            "count": len(results)
        }
    except Exception as e:
        return {"error": str(e)}


def get_dao_voter_stats(dao_name: str, voter_address: str) -> dict:
    """
    Check how an address has voted in a DAO's recent proposals.
    Shows voting history and participation rate for a wallet.
    Useful for checking if you've voted, or analyzing a whale's voting pattern.
    """
    dao_name = dao_name.lower().strip()
    if dao_name.upper() in TOKEN_TO_DAO:
        dao_name = TOKEN_TO_DAO[dao_name.upper()]

    dao = DAO_REGISTRY.get(dao_name)
    if not dao:
        return {"error": f"DAO '{dao_name}' not found."}

    space = dao["snapshot"]
    query = """
    query($space: String!, $voter: String!) {
      votes(
        first: 20,
        where: { space: $space, voter: $voter },
        orderBy: "created", orderDirection: desc
      ) {
        id choice created
        proposal { id title state end choices }
        vp
      }
    }
    """
    try:
        r = requests.post(SNAPSHOT_GQL,
                          json={"query": query,
                                "variables": {"space": space, "voter": voter_address}},
                          timeout=15)
        votes = r.json().get("data", {}).get("votes", [])

        vote_history = []
        for v in votes:
            prop    = v.get("proposal", {})
            choices = prop.get("choices", [])
            choice_idx = v.get("choice", 1)
            # Snapshot choice is 1-indexed
            choice_label = choices[choice_idx - 1] if isinstance(choice_idx, int) and choices else str(choice_idx)

            vote_history.append({
                "proposal": prop.get("title", "Unknown"),
                "voted": choice_label,
                "voting_power_used": round(v.get("vp", 0), 2),
                "date": datetime.fromtimestamp(v.get("created", 0), tz=timezone.utc).strftime("%Y-%m-%d"),
                "proposal_state": prop.get("state"),
                "link": f"https://snapshot.org/#/{space}/proposal/{prop.get('id', '')}"
            })

        return {
            "dao": dao_name,
            "voter": voter_address,
            "votes_found": len(vote_history),
            "vote_history": vote_history,
            "note": "Shows last 20 votes in this DAO's Snapshot space."
        }
    except Exception as e:
        return {"error": str(e)}


# ─── Tool Registry ─────────────────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_supported_daos",
            "description": "List all DAOs tracked by this agent with token symbols and Snapshot spaces. Call this if unsure which DAOs are available.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_active_proposals",
            "description": "Fetch currently active (open for voting) proposals for a DAO from Snapshot. Returns deadline, vote counts, leading choice, and direct links.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dao_name": {"type": "string", "description": "DAO name (e.g. 'uniswap', 'aave') or token symbol (e.g. 'UNI', 'AAVE')"},
                    "limit":    {"type": "integer", "description": "Max proposals to return (default 10)"}
                },
                "required": ["dao_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_proposals",
            "description": "Fetch recently closed or pending proposals for a DAO. Use state='closed' for past votes, 'pending' for upcoming.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dao_name": {"type": "string"},
                    "limit":    {"type": "integer", "description": "Number of proposals (default 10)"},
                    "state":    {"type": "string",  "description": "'closed' or 'pending' (default 'closed')"}
                },
                "required": ["dao_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_proposal_detail",
            "description": "Fetch the full description, vote breakdown, and metadata for a single Snapshot proposal by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dao_name":    {"type": "string", "description": "DAO name or token symbol"},
                    "proposal_id": {"type": "string", "description": "Snapshot proposal ID (from get_active_proposals)"}
                },
                "required": ["dao_name", "proposal_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_voting_deadlines",
            "description": "Get a consolidated voting deadline calendar across multiple DAOs, sorted by soonest deadline. Use when asked about upcoming votes or deadlines across a portfolio.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dao_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of DAO names or token symbols e.g. ['uniswap', 'aave', 'ARB']"
                    }
                },
                "required": ["dao_names"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_portfolio_governance_summary",
            "description": "Given a list of token symbols, find ALL active governance votes affecting those tokens. The key tool for 'summarize governance votes for my portfolio'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "token_symbols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of token symbols held e.g. ['UNI', 'AAVE', 'CRV', 'ARB', 'ENS']"
                    }
                },
                "required": ["token_symbols"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_governance_changes_history",
            "description": "Fetch recently passed/failed proposals to see what governance changes have been made to a protocol. Shows outcomes of past votes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dao_name": {"type": "string"},
                    "limit":    {"type": "integer", "description": "Number of past proposals (default 10)"}
                },
                "required": ["dao_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_proposals",
            "description": "Search a DAO's proposals by keyword in the title. Useful for finding proposals about 'fee', 'treasury', 'upgrade', 'risk', 'grant', etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dao_name": {"type": "string"},
                    "keyword":  {"type": "string", "description": "Keyword to search in proposal titles"},
                    "limit":    {"type": "integer", "description": "Max results (default 10)"}
                },
                "required": ["dao_name", "keyword"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_dao_voter_stats",
            "description": "Check a wallet's voting history in a specific DAO. Shows which proposals they voted on, what they voted, and their voting power used.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dao_name":       {"type": "string"},
                    "voter_address":  {"type": "string", "description": "Ethereum wallet address (0x...)"}
                },
                "required": ["dao_name", "voter_address"]
            }
        }
    }
]

TOOL_MAP = {
    "list_supported_daos":             list_supported_daos,
    "get_active_proposals":            get_active_proposals,
    "get_recent_proposals":            get_recent_proposals,
    "get_proposal_detail":             get_proposal_detail,
    "get_voting_deadlines":            get_voting_deadlines,
    "get_portfolio_governance_summary": get_portfolio_governance_summary,
    "get_governance_changes_history":  get_governance_changes_history,
    "search_proposals":                search_proposals,
    "get_dao_voter_stats":             get_dao_voter_stats,
}

SYSTEM_PROMPT = """You are a crypto governance AI agent. You track DAO proposals, voting deadlines, and governance changes across major DeFi protocols.

## Key flows:

### "Summarize governance votes for my portfolio"
→ Ask the user for their token list if not provided, then call:
   get_portfolio_governance_summary(token_symbols=[...])
→ For each DAO with active votes, present a clean summary with deadline and link.

### "What's happening in [DAO] governance?"
→ get_active_proposals(dao_name) for live votes
→ get_recent_proposals(dao_name, state='closed') for recent decisions

### "What are my voting deadlines?"
→ get_voting_deadlines(dao_names=[...]) - pass all relevant DAOs

### "What changed in [DAO] recently?"
→ get_governance_changes_history(dao_name)

### "Summarize this proposal" / "What does proposal X say?"
→ get_proposal_detail(dao_name, proposal_id)

### "Find proposals about fees / treasury / risk"
→ search_proposals(dao_name, keyword)

### "Has wallet 0x... voted in [DAO]?"
→ get_dao_voter_stats(dao_name, voter_address)

## Output style:
- Lead with urgency: 🔴 votes closing soon first
- Use a clean table or bullet format for multiple proposals
- Always include the direct Snapshot link for each proposal
- For portfolio summaries, group by token/DAO
- Be concise: title, deadline, leading choice, link - that's the minimum per proposal
- Flag 🔴 URGENT for proposals closing within 6 hours
- End portfolio summaries with total count: "X active votes need your attention"
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

    max_iterations = 10
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

            print(f"  📡 {tool_name}({list(tool_args.values())[:2]})...")
            result = execute_tool(tool_name, tool_args)
            print("  ✅ Done")
            messages.append({"role": "tool", "content": result})

    return "Agent reached maximum iterations.", conversation_history


# ─── CLI ───────────────────────────────────────────────────────────────────────

def main():
    print("=" * 65)
    print("  🗳️  Governance AI Agent")
    print("  Tracks: Proposals · Deadlines · Votes · Changes")
    print("  Powered by Ollama + Snapshot")
    print("=" * 65)
    print(f"  Model: {MODEL}")
    print()
    print("  Supported DAOs: UNI, AAVE, COMP, CRV, MKR, BAL, 1INCH,")
    print("  OP, ARB, ENS, GTC, SUSHI, YFI, LDO, SNX, GRT + more")
    print()
    print("  Example queries:")
    print("  • Summarize all governance votes affecting my portfolio")
    print("    (UNI, AAVE, ARB, ENS, CRV)")
    print("  • What's active in Uniswap governance right now?")
    print("  • Show my voting deadlines for UNI, AAVE and OP")
    print("  • What governance changes happened in Aave recently?")
    print("  • Find Uniswap proposals about fees")
    print("  • Summarize the top active Compound proposal")
    print("  • Has 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045 voted in ENS?")
    print("  • What DAOs do you support?")
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