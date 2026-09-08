"""Shared Solana wallet inspection helpers for agent tools."""

from __future__ import annotations

import os
import re
import time
from typing import Any, Optional

from cache_store import cache_backend, cache_stats, clear_prefix, get_json, set_json
from dca_agent import SOLANA_CLUSTER, get_token_price, resolve_token, sol_rpc

TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"

WALLET_SNAPSHOT_CACHE_TTL_SECONDS = int(
    os.environ.get("WALLET_MONITORING_CACHE_TTL_SECONDS", str(15 * 60))
)
MAX_TOKEN_ACCOUNT_ROWS = int(os.environ.get("WALLET_MAX_TOKEN_ACCOUNT_ROWS", "25000"))

_WALLET_SNAPSHOT_PREFIX = "wallet:snapshot:"
_WALLET_ANALYSIS_PREFIX = "wallet:analysis:"

SOLANA_WHALE_REGISTRY: dict[str, dict[str, str]] = {
    "smart_money": {
        "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1": "Raydium Authority",
        "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "Raydium AMM",
    },
    "exchange": {
        "2ojv9BAiHUrvsm9gxDeTouWgW4Y1GBd2f7b2iP8zY4q3": "Example CEX hot wallet",
    },
    "defi": {
        "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "Jupiter Aggregator v6",
    },
}


def _rpc_u64(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    if isinstance(value, dict):
        for key in ("value", "amount", "lamports"):
            if key in value:
                return _rpc_u64(value[key])
    return 0


def _looks_like_wallet(value: str) -> bool:
    value = (value or "").strip()
    return 32 <= len(value) <= 44 and bool(re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]+", value))


def _wallet_label(address: str) -> Optional[str]:
    for wallets in SOLANA_WHALE_REGISTRY.values():
        if address in wallets:
            return wallets[address]
    return None


def _cache_get(address: str) -> Optional[dict[str, Any]]:
    return get_json(f"{_WALLET_SNAPSHOT_PREFIX}{address.strip()}")


def _cache_set(address: str, snapshot: dict[str, Any]) -> None:
    set_json(
        f"{_WALLET_SNAPSHOT_PREFIX}{address.strip()}",
        snapshot,
        WALLET_SNAPSHOT_CACHE_TTL_SECONDS,
    )


def clear_wallet_snapshot_cache() -> None:
    clear_prefix(_WALLET_SNAPSHOT_PREFIX)
    clear_prefix(_WALLET_ANALYSIS_PREFIX)


def get_wallet_cache_stats() -> dict[str, Any]:
    stats = cache_stats(_WALLET_SNAPSHOT_PREFIX, WALLET_SNAPSHOT_CACHE_TTL_SECONDS)
    stats["backend"] = cache_backend()
    return stats


def get_wallet_analysis_cached(address: str) -> Optional[str]:
    value = get_json(f"{_WALLET_ANALYSIS_PREFIX}{address.strip()}")
    return value if isinstance(value, str) else None


def set_wallet_analysis_cached(address: str, text: str) -> None:
    set_json(
        f"{_WALLET_ANALYSIS_PREFIX}{address.strip()}",
        text,
        WALLET_SNAPSHOT_CACHE_TTL_SECONDS,
    )


def list_tracked_wallets(category: str = "all") -> dict[str, Any]:
    cat = (category or "all").strip().lower()
    if cat == "all":
        out: dict[str, list[dict[str, str]]] = {}
        total = 0
        for name, wallets in SOLANA_WHALE_REGISTRY.items():
            out[name] = [{"address": a, "label": l} for a, l in wallets.items()]
            total += len(wallets)
        return {"registry": out, "total": total, "cluster": SOLANA_CLUSTER}
    if cat not in SOLANA_WHALE_REGISTRY:
        return {"error": f"Unknown category. Choose: all, {', '.join(SOLANA_WHALE_REGISTRY)}"}
    wallets = SOLANA_WHALE_REGISTRY[cat]
    return {
        "category": cat,
        "wallets": [{"address": a, "label": l} for a, l in wallets.items()],
        "count": len(wallets),
        "cluster": SOLANA_CLUSTER,
    }


def get_wallet_sol_balance(address: str) -> dict[str, Any]:
    address = (address or "").strip()
    if not _looks_like_wallet(address):
        return {"error": "Provide a valid Solana wallet address (32–44 character base58)."}
    try:
        result = sol_rpc("getBalance", [address, {"commitment": "confirmed"}])
        lamports = _rpc_u64(result)
    except Exception as exc:
        return {"error": f"Solana RPC getBalance failed: {exc}", "address": address}
    return {
        "address": address,
        "sol": round(lamports / 1_000_000_000, 9),
        "lamports": lamports,
        "cluster": SOLANA_CLUSTER,
        "source": "solana_rpc",
    }


def _fetch_token_accounts(address: str, program_id: str) -> list[dict[str, Any]]:
    try:
        resp = sol_rpc(
            "getTokenAccountsByOwner",
            [
                address,
                {"programId": program_id},
                {"encoding": "jsonParsed", "commitment": "confirmed"},
            ],
        )
    except Exception:
        return []
    return (resp or {}).get("value") or []


def get_wallet_token_balances(address: str, limit: int = 25) -> dict[str, Any]:
    address = (address or "").strip()
    if not _looks_like_wallet(address):
        return {"error": "Provide a valid Solana wallet address."}
    limit = max(1, min(int(limit), 50))

    rows = _fetch_token_accounts(address, TOKEN_PROGRAM)
    rows.extend(_fetch_token_accounts(address, TOKEN_2022_PROGRAM))

    if len(rows) > MAX_TOKEN_ACCOUNT_ROWS:
        return {
            "address": address,
            "token_count": None,
            "tokens": [],
            "token_accounts_skipped": len(rows),
            "partial": True,
            "note": (
                f"Wallet has {len(rows):,} token accounts — SPL breakdown omitted for performance. "
                "Use a personal wallet address for a full holdings view."
            ),
            "cluster": SOLANA_CLUSTER,
            "source": "solana_rpc",
        }

    by_mint: dict[str, dict[str, Any]] = {}
    for entry in rows:
        info = (((entry.get("account") or {}).get("data") or {}).get("parsed") or {}).get("info") or {}
        token_amount = info.get("tokenAmount") or {}
        mint = info.get("mint")
        if not mint:
            continue
        ui = float(token_amount.get("uiAmount") or 0)
        if ui <= 0:
            continue
        if mint in by_mint:
            by_mint[mint]["amount"] = float(by_mint[mint]["amount"]) + ui
        else:
            by_mint[mint] = {
                "mint": mint,
                "symbol": _short_mint(mint),
                "amount": ui,
                "decimals": token_amount.get("decimals"),
            }

    ranked = sorted(by_mint.values(), key=lambda x: x.get("amount") or 0, reverse=True)[:limit]
    for row in ranked:
        resolved = resolve_token(row["mint"])
        if isinstance(resolved, dict) and "error" not in resolved and resolved.get("symbol"):
            row["symbol"] = resolved["symbol"]

    tokens = ranked
    return {
        "address": address,
        "token_count": len(by_mint),
        "tokens": tokens,
        "cluster": SOLANA_CLUSTER,
        "source": "solana_rpc",
    }


def _short_mint(mint: str) -> str:
    if len(mint) <= 12:
        return mint
    return f"{mint[:4]}...{mint[-4:]}"


def get_wallet_recent_activity(address: str, limit: int = 12) -> dict[str, Any]:
    address = (address or "").strip()
    if not _looks_like_wallet(address):
        return {"error": "Provide a valid Solana wallet address."}
    limit = max(1, min(int(limit), 25))
    try:
        sigs = sol_rpc(
            "getSignaturesForAddress",
            [address, {"limit": limit, "commitment": "confirmed"}],
        ) or []
    except Exception as exc:
        return {"error": f"Solana RPC getSignaturesForAddress failed: {exc}", "address": address}

    activity = []
    for sig in sigs:
        activity.append(
            {
                "signature": sig.get("signature"),
                "slot": sig.get("slot"),
                "block_time": sig.get("blockTime"),
                "err": sig.get("err"),
                "explorer": f"https://solscan.io/tx/{sig.get('signature')}" if sig.get("signature") else None,
            }
        )
    return {
        "address": address,
        "recent_signatures": activity,
        "count": len(activity),
        "cluster": SOLANA_CLUSTER,
        "source": "solana_rpc",
    }


def analyze_wallet_profile(address: str) -> dict[str, Any]:
    balance = get_wallet_sol_balance(address)
    if balance.get("error"):
        return balance
    tokens = get_wallet_token_balances(address, limit=15)
    activity = get_wallet_recent_activity(address, limit=5)
    return {
        "address": address,
        "label": _wallet_label(address),
        "sol_balance": balance.get("sol"),
        "top_tokens": (tokens.get("tokens") or [])[:5],
        "recent_activity_count": activity.get("count"),
        "recent_signatures": activity.get("recent_signatures"),
        "cluster": SOLANA_CLUSTER,
        "source": "solana_rpc",
    }


def _enrich_holdings_with_prices(tokens: list[dict[str, Any]], top_n: int = 8) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for row in tokens[:top_n]:
        symbol = row.get("symbol")
        mint = row.get("mint")
        price_usd = None
        if symbol and symbol not in ("?", "SOL") and not str(symbol).startswith("..."):
            price = get_token_price(str(symbol))
            if not price.get("error"):
                price_usd = price.get("price_usd")
        elif mint:
            price = get_token_price(str(mint))
            if not price.get("error"):
                price_usd = price.get("price_usd")
        amount = float(row.get("amount") or 0)
        value_usd = float(price_usd) * amount if price_usd is not None else None
        enriched.append({**row, "price_usd": price_usd, "estimated_value_usd": value_usd})
    return enriched


def _build_trade_suggestions(snapshot: dict[str, Any], risk_profile: str = "balanced") -> list[dict[str, str]]:
    sol = float(snapshot.get("sol_balance") or 0)
    holdings = snapshot.get("tokens") or []
    suggestions: list[dict[str, str]] = []

    if sol > 0.5 and len(holdings) < 3:
        suggestions.append(
            {
                "type": "diversification",
                "idea": "Consider DCA into established Solana tokens via the DCA Agent.",
                "rationale": f"Wallet holds {sol:.3f} SOL with few SPL positions.",
            }
        )
    if len(holdings) >= 5:
        top = holdings[0]
        suggestions.append(
            {
                "type": "rebalance",
                "idea": f"Review overweight {top.get('symbol')} ({top.get('amount')} tokens).",
                "rationale": "Large single-token exposure increases idiosyncratic risk.",
            }
        )
    if sol < 0.05 and holdings:
        suggestions.append(
            {
                "type": "gas",
                "idea": "Top up SOL for transaction fees before executing swaps.",
                "rationale": "Low SOL balance may block future trades.",
            }
        )
    if not suggestions:
        suggestions.append(
            {
                "type": "monitor",
                "idea": "No urgent rebalance flags — consider DCA or alerts for systematic entries.",
                "rationale": f"Risk profile: {risk_profile}.",
            }
        )
    return suggestions


def _fetch_wallet_snapshot_uncached(address: str) -> dict[str, Any]:
    from concurrent.futures import ThreadPoolExecutor

    address = (address or "").strip()

    with ThreadPoolExecutor(max_workers=3) as pool:
        fut_balance = pool.submit(get_wallet_sol_balance, address)
        fut_tokens = pool.submit(get_wallet_token_balances, address, 30)
        fut_activity = pool.submit(get_wallet_recent_activity, address, 12)
        balance = fut_balance.result()
        tokens_payload = fut_tokens.result()
        activity = fut_activity.result()

    if balance.get("error"):
        return {**balance, "needs_valid_address": True}
    if tokens_payload.get("error"):
        return tokens_payload

    tokens = tokens_payload.get("tokens") or []
    enriched = _enrich_holdings_with_prices(tokens)

    snapshot: dict[str, Any] = {
        "address": address,
        "label": _wallet_label(address),
        "cluster": SOLANA_CLUSTER,
        "sol_balance": balance.get("sol"),
        "sol_lamports": balance.get("lamports"),
        "token_count": tokens_payload.get("token_count"),
        "tokens": tokens,
        "holdings_with_prices": enriched,
        "recent_activity": activity,
        "explorer_url": f"https://solscan.io/account/{address}",
        "data_sources": ["solana_rpc", "jupiter"],
        "fetched_at_unix": time.time(),
        "cache_ttl_seconds": WALLET_SNAPSHOT_CACHE_TTL_SECONDS,
    }
    if tokens_payload.get("partial"):
        snapshot["partial"] = True
        snapshot["token_accounts_skipped"] = tokens_payload.get("token_accounts_skipped")
        snapshot["note"] = tokens_payload.get("note")
        snapshot["trade_suggestions"] = [
            {
                "type": "program_wallet",
                "idea": "This address holds a very large number of token accounts (likely a program or pool authority).",
                "rationale": tokens_payload.get("note") or "Use a personal wallet for portfolio-style analysis.",
            }
        ]
    else:
        total_est_usd = sum(float(h.get("estimated_value_usd") or 0) for h in enriched if h.get("estimated_value_usd"))
        sol_usd = None
        try:
            sol_price = get_token_price("SOL")
            if not sol_price.get("error") and sol_price.get("price_usd") is not None:
                sol_usd = float(balance.get("sol") or 0) * float(sol_price["price_usd"])
                total_est_usd += sol_usd
        except Exception:
            pass
        snapshot["estimated_sol_value_usd"] = round(sol_usd, 2) if sol_usd is not None else None
        snapshot["estimated_portfolio_value_usd"] = round(total_est_usd, 2) if total_est_usd else None
        snapshot["trade_suggestions"] = _build_trade_suggestions(
            {"sol_balance": balance.get("sol"), "tokens": tokens},
        )
    return snapshot


def get_wallet_snapshot(address: str) -> dict[str, Any]:
    """Full on-chain wallet snapshot with 15-minute cache keyed by address."""
    address = (address or "").strip()
    if not _looks_like_wallet(address):
        return {
            "error": "Provide a valid Solana wallet address (32–44 character base58).",
            "needs_valid_address": True,
        }

    cached = _cache_get(address)
    if cached is not None:
        return {**cached, "cached": True}

    snapshot = _fetch_wallet_snapshot_uncached(address)
    if not snapshot.get("error"):
        _cache_set(address, snapshot)
        snapshot = {**snapshot, "cached": False}
    return snapshot


def extract_wallet_query(user_input: str, connected_wallet: Optional[str] = None) -> Optional[str]:
    text = (user_input or "").strip()
    if not text:
        return None

    mint_match = re.search(r"\b([1-9A-HJ-NP-Za-km-z]{32,44})\b", text)
    if mint_match:
        return mint_match.group(1)

    if re.search(r"\b(my|connected|own)\s+wallet\b", text, re.I) and connected_wallet:
        return connected_wallet.strip()

    patterns = [
        r"\b(?:wallet|address|account)\s+(?:for|of|at)?\s*([1-9A-HJ-NP-Za-km-z]{32,44})\b",
        r"\banalyze\s+(?:wallet\s+)?([1-9A-HJ-NP-Za-km-z]{32,44})\b",
        r"\bmonitor\s+(?:wallet\s+)?([1-9A-HJ-NP-Za-km-z]{32,44})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(1)

    if re.search(r"\b(my|connected|own)\s+wallet\b", text, re.I):
        return connected_wallet

    return None


def format_wallet_snapshot_reply(snapshot: dict[str, Any]) -> str:
    if snapshot.get("error"):
        return (
            f"I couldn't fetch on-chain data: {snapshot.get('error')}\n\n"
            "Paste a **Solana wallet address** (32–44 chars) to analyze any wallet, "
            "or connect your wallet and ask about **my wallet**."
        )

    lines = [
        f"**Wallet Snapshot — `{snapshot.get('address')}`**",
    ]
    if snapshot.get("label"):
        lines.append(f"Known label: {snapshot['label']}")
    if snapshot.get("partial") and snapshot.get("note"):
        lines.append(f"_{snapshot['note']}_")
    if snapshot.get("cached"):
        ttl = int(snapshot.get("cache_ttl_seconds") or WALLET_SNAPSHOT_CACHE_TTL_SECONDS)
        lines.append(f"_Cached on-chain snapshot (refreshes every {ttl // 60} minutes)._")
    lines.extend(
        [
            f"Explorer: {snapshot.get('explorer_url')}",
            "",
            "**Balances (Solana RPC)**",
            f"- SOL: {snapshot.get('sol_balance')} "
            + (
                f"(~${snapshot.get('estimated_sol_value_usd'):,.2f})"
                if snapshot.get("estimated_sol_value_usd") is not None
                else ""
            ),
            f"- SPL tokens: {snapshot.get('token_count')}",
        ]
    )
    if snapshot.get("estimated_portfolio_value_usd") is not None:
        lines.append(f"- Est. portfolio value (priced holdings + SOL): ${snapshot['estimated_portfolio_value_usd']:,.2f}")

    holdings = snapshot.get("holdings_with_prices") or snapshot.get("tokens") or []
    if holdings:
        lines.extend(["", "**Top holdings**"])
        for row in holdings[:10]:
            val = row.get("estimated_value_usd")
            val_s = f" · ~${val:,.2f}" if val is not None else ""
            price = row.get("price_usd")
            price_s = f" @ ${price:.6g}" if price is not None else ""
            lines.append(f"- {row.get('symbol')}: {row.get('amount')}{price_s}{val_s}")

    activity = (snapshot.get("recent_activity") or {}).get("recent_signatures") or []
    if activity:
        lines.extend(["", "**Recent activity**"])
        for row in activity[:5]:
            err = "failed" if row.get("err") else "ok"
            lines.append(f"- {row.get('signature', '')[:16]}… ({err})")

    suggestions = snapshot.get("trade_suggestions") or []
    if suggestions:
        lines.extend(["", "**Suggestions (informational)**"])
        for s in suggestions:
            lines.append(f"- [{s.get('type')}] {s.get('idea')}")

    lines.extend(["", "Data: Solana RPC + Jupiter prices where available.", "Not financial advice. DYOR."])
    return "\n".join(lines)
