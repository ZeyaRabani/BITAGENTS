"""Live yield APIs for Kamino, Save, Drift, and MarginFi.

Jupiter JLP stays on the existing swap path. Kamino lending and vault deposits
are built by the Kamino transaction API and signed by the Circle yield wallet.
Save publishes reserve data we turn into a supply APY. MarginFi and Drift do
not publish a deposit API, so they are reported with their docs URLs.
"""

from __future__ import annotations

import base64
import os
import time
from typing import Any, Optional
from urllib.parse import quote

import requests

SOL_MINT = "So11111111111111111111111111111111111111112"
_USER_AGENT = "BITAGENTS-YieldAgent/1.0"

KAMINO_API_URL = os.environ.get("KAMINO_API_URL", "https://api.kamino.finance").rstrip("/")
SAVE_API_URL = os.environ.get("SAVE_API_URL", "https://api.save.finance").rstrip("/")
DRIFT_DATA_API_URL = os.environ.get("DRIFT_DATA_API_URL", "https://data.velocity.exchange").rstrip("/")

PROTOCOL_DOCS = {
    "kamino": {
        "name": "Kamino Finance",
        "docs_url": "https://kamino.com/build/api-reference/introduction",
        "api_url": KAMINO_API_URL,
        "signup_url": "https://kamino.com/build/api-reference/introduction",
        "key_required": False,
        "note": (
            "Public API. No key is required. Higher rate limits are granted on request "
            "from the API introduction page. Optional KAMINO_API_KEY is sent as x-api-key."
        ),
    },
    "save": {
        "name": "Save Finance",
        "docs_url": "https://docs.save.finance/developers/introduction",
        "api_docs_url": "https://dev.solend.fi/docs/api/",
        "api_url": SAVE_API_URL,
        "signup_url": "https://dev.solend.fi/docs/api/",
        "key_required": False,
        "note": "Public reserves API. It has rates, not a hosted deposit transaction.",
    },
    "drift": {
        "name": "Drift Protocol",
        "docs_url": "https://docs.drift.trade/developers/data-api",
        "sdk_url": "https://docs.drift.trade/developers/drift-sdk",
        "api_url": DRIFT_DATA_API_URL,
        "signup_url": "https://docs.drift.trade/developers/data-api",
        "key_required": False,
        "note": (
            "The old host data.api.drift.trade no longer resolves. The data API is "
            "https://data.velocity.exchange and does not build lending or insurance-fund deposits. "
            "Those use the Drift SDK."
        ),
    },
    "marginfi": {
        "name": "MarginFi",
        "docs_url": "https://docs.marginfi.com/ts-sdk",
        "sdk_url": "https://docs.marginfi.com/sdks",
        "signup_url": "https://docs.marginfi.com/ts-sdk",
        "key_required": False,
        "note": "MarginFi does not publish a REST yield or deposit API. Integration is the TypeScript SDK.",
    },
}

_cache: dict[str, Any] = {"ts": 0.0, "payload": None}
_CACHE_SECONDS = 120


def _kamino_headers() -> dict[str, str]:
    headers = {"Accept": "application/json", "User-Agent": _USER_AGENT}
    key = (os.environ.get("KAMINO_API_KEY") or "").strip()
    if key:
        headers["x-api-key"] = key
    return headers


def _get_json(url: str, *, headers: Optional[dict[str, str]] = None) -> Any:
    res = requests.get(
        url,
        headers=headers or {"Accept": "application/json", "User-Agent": _USER_AGENT},
        timeout=25,
    )
    res.raise_for_status()
    return res.json()


def protocol_api_status() -> dict[str, Any]:
    return {
        "kamino": {
            **PROTOCOL_DOCS["kamino"],
            "configured": True,
            "api_key_set": bool((os.environ.get("KAMINO_API_KEY") or "").strip()),
            "can_deposit": True,
        },
        "save": {
            **PROTOCOL_DOCS["save"],
            "configured": True,
            "can_deposit": False,
        },
        "drift": {
            **PROTOCOL_DOCS["drift"],
            "configured": True,
            "can_deposit": False,
        },
        "marginfi": {
            **PROTOCOL_DOCS["marginfi"],
            "configured": False,
            "can_deposit": False,
        },
    }


def _save_supply_apy_pct(reserve: dict[str, Any]) -> Optional[float]:
    liquidity = reserve.get("liquidity") or {}
    config = reserve.get("config") or {}
    try:
        available = float(liquidity.get("availableAmount") or 0)
        borrowed = float(liquidity.get("borrowedAmountWads") or 0) / 1e18
    except (TypeError, ValueError):
        return None
    total = available + borrowed
    if total <= 0:
        return None
    util = borrowed / total
    try:
        optimal_util = float(config.get("optimalUtilizationRate") or 0) / 100
        min_borrow = float(config.get("minBorrowRate") or 0) / 100
        optimal_borrow = float(config.get("optimalBorrowRate") or 0) / 100
        max_borrow = float(config.get("maxBorrowRate") or 0) / 100
        take = float(config.get("protocolTakeRate") or 0) / 100
    except (TypeError, ValueError):
        return None
    if optimal_util <= 0:
        return None
    if util < optimal_util:
        borrow_apy = (util / optimal_util) * (optimal_borrow - min_borrow) + min_borrow
    else:
        span = 1 - optimal_util
        factor = 0.0 if span <= 0 else (util - optimal_util) / span
        borrow_apy = factor * (max_borrow - optimal_borrow) + optimal_borrow
    supply = util * borrow_apy * max(0.0, 1 - take)
    if supply <= 0:
        return None
    return supply * 100


def _kamino_lending_rows() -> list[dict[str, Any]]:
    markets = _get_json(f"{KAMINO_API_URL}/v2/kamino-market", headers=_kamino_headers())
    if not isinstance(markets, list):
        return []
    ordered = sorted(markets, key=lambda row: not bool(row.get("isPrimary")))
    rows: list[dict[str, Any]] = []
    for market in ordered[:4]:
        market_pk = str(market.get("lendingMarket") or "")
        if not market_pk:
            continue
        metrics = _get_json(
            f"{KAMINO_API_URL}/kamino-market/{market_pk}/reserves/metrics?env=mainnet-beta",
            headers=_kamino_headers(),
        )
        if not isinstance(metrics, list):
            continue
        for reserve in metrics:
            mint = str(reserve.get("liquidityTokenMint") or "")
            symbol = str(reserve.get("liquidityToken") or "")
            if mint != SOL_MINT and symbol.upper() not in {"SOL", "WSOL"}:
                continue
            try:
                apy = float(reserve.get("supplyApy") or 0) * 100
            except (TypeError, ValueError):
                continue
            if apy <= 0:
                continue
            try:
                tvl = float(reserve.get("totalSupplyUsd") or 0)
            except (TypeError, ValueError):
                tvl = 0
            rows.append(
                {
                    "protocol_id": "kamino",
                    "protocol_name": "Kamino Finance",
                    "yield_type": "lending",
                    "kind": "lending",
                    "symbol": "SOL",
                    "apy": round(apy, 3),
                    "score": round(apy, 3),
                    "tvl_usd": round(tvl, 0),
                    "executable": True,
                    "deposit_route": "kamino_lend",
                    "market": market_pk,
                    "reserve": str(reserve.get("reserve") or ""),
                    "source": "kamino_api",
                    "docs_url": PROTOCOL_DOCS["kamino"]["docs_url"],
                }
            )
    return rows


def _kamino_vault_metrics() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    token: Optional[str] = None
    for _ in range(6):
        url = f"{KAMINO_API_URL}/kvaults/vaults/metrics"
        if token:
            url += f"?paginationToken={quote(token, safe='')}"
        payload = _get_json(url, headers=_kamino_headers())
        batch = payload.get("result") if isinstance(payload, dict) else payload
        if isinstance(batch, list):
            rows.extend(batch)
        token = payload.get("paginationToken") if isinstance(payload, dict) else None
        if not token:
            break
    return rows


def _kamino_vault_rows() -> list[dict[str, Any]]:
    vaults = _get_json(f"{KAMINO_API_URL}/kvaults/vaults", headers=_kamino_headers())
    metric_rows = _kamino_vault_metrics()
    if not isinstance(vaults, list):
        return []
    by_address = {str(item.get("address") or ""): item for item in vaults}
    rows: list[dict[str, Any]] = []
    for metric in metric_rows:
        address = str(metric.get("kvault") or "")
        state = (by_address.get(address) or {}).get("state") or {}
        if str(state.get("tokenMint") or "") != SOL_MINT:
            continue
        try:
            apy = float(metric.get("apy") or metric.get("apy30d") or 0) * 100
            tvl = float(metric.get("tokensInvestedUsd") or 0) + float(metric.get("tokensAvailableUsd") or 0)
        except (TypeError, ValueError):
            continue
        if apy <= 0 or tvl <= 0:
            continue
        rows.append(
            {
                "protocol_id": "kamino-vault",
                "protocol_name": "Kamino Finance",
                "yield_type": "liquidity_vault",
                "kind": "liquidity_vault",
                "symbol": "SOL",
                "apy": round(apy, 3),
                "score": round(apy, 3),
                "tvl_usd": round(tvl, 0),
                "executable": True,
                "deposit_route": "kamino_vault",
                "kvault": address,
                "source": "kamino_api",
                "docs_url": PROTOCOL_DOCS["kamino"]["docs_url"],
            }
        )
    return rows


def _save_rows() -> list[dict[str, Any]]:
    markets = _get_json(
        f"{SAVE_API_URL}/v1/markets/configs?scope=all&deployment=production"
    )
    if not isinstance(markets, list):
        return []
    primary = next((item for item in markets if item.get("isPrimary")), None)
    if not primary:
        return []
    ids = [
        str(reserve.get("address"))
        for reserve in primary.get("reserves") or []
        if str((reserve.get("liquidityToken") or {}).get("symbol") or "").upper() == "SOL"
        and reserve.get("address")
    ]
    if not ids:
        return []
    payload = _get_json(f"{SAVE_API_URL}/v1/reserves?ids={','.join(ids[:8])}")
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in results:
        reserve = item.get("reserve") or {}
        apy = _save_supply_apy_pct(reserve)
        if apy is None:
            continue
        liquidity = reserve.get("liquidity") or {}
        try:
            supplied = float(liquidity.get("availableAmount") or 0) / 1e9
            borrowed = float(liquidity.get("borrowedAmountWads") or 0) / 1e18 / 1e9
        except (TypeError, ValueError):
            supplied, borrowed = 0.0, 0.0
        rows.append(
            {
                "protocol_id": "save",
                "protocol_name": "Save Finance",
                "yield_type": "lending",
                "kind": "lending",
                "symbol": "SOL",
                "apy": round(apy, 3),
                "score": round(apy, 3),
                "tvl_usd": round((supplied + borrowed) * 150, 0),
                "executable": False,
                "source": "save_api",
                "docs_url": PROTOCOL_DOCS["save"]["docs_url"],
            }
        )
    return rows


def fetch_protocol_markets() -> dict[str, Any]:
    now = time.time()
    cached = _cache.get("payload")
    if cached and now - float(_cache.get("ts") or 0) < _CACHE_SECONDS:
        return cached
    markets: list[dict[str, Any]] = []
    errors: dict[str, str] = {}
    for name, loader in (
        ("kamino_lending", _kamino_lending_rows),
        ("kamino_vaults", _kamino_vault_rows),
        ("save", _save_rows),
    ):
        try:
            markets.extend(loader())
        except Exception as exc:
            errors[name] = str(exc)
    payload = {"markets": markets, "errors": errors, "status": protocol_api_status()}
    _cache["ts"] = now
    _cache["payload"] = payload
    return payload


def build_kamino_deposit(
    *,
    agent_wallet: str,
    amount: float,
    venue: dict[str, Any],
) -> dict[str, Any]:
    route = str(venue.get("deposit_route") or "")
    amount_text = f"{float(amount):.9f}".rstrip("0").rstrip(".")
    if route == "kamino_lend":
        url = f"{KAMINO_API_URL}/ktx/klend/deposit"
        body = {
            "wallet": agent_wallet,
            "market": venue.get("market"),
            "reserve": venue.get("reserve"),
            "amount": amount_text,
        }
    elif route == "kamino_vault":
        url = f"{KAMINO_API_URL}/ktx/kvault/deposit"
        body = {
            "wallet": agent_wallet,
            "kvault": venue.get("kvault"),
            "amount": amount_text,
        }
    else:
        return {"error": "This venue has no Kamino deposit route."}
    res = requests.post(url, json=body, headers={**_kamino_headers(), "Content-Type": "application/json"}, timeout=30)
    try:
        data = res.json()
    except Exception:
        data = {"message": res.text[:300]}
    if res.status_code >= 400:
        return {"error": data.get("message") or data.get("error") or "Kamino deposit build failed.", "details": data}
    tx = data.get("transaction")
    if not tx:
        return {"error": "Kamino did not return a transaction.", "details": data}
    return {"transaction": tx}


def find_kamino_market(reserve: str) -> Optional[str]:
    """Find the lending market that owns a reserve. Used when unwinding a deposit."""
    reserve = (reserve or "").strip()
    if not reserve:
        return None
    cached = (_cache.get("payload") or {}).get("markets") or []
    for row in cached:
        if str(row.get("reserve") or "") == reserve and row.get("market"):
            return str(row["market"])
    markets = _get_json(f"{KAMINO_API_URL}/v2/kamino-market", headers=_kamino_headers())
    if not isinstance(markets, list):
        return None
    ordered = sorted(markets, key=lambda row: not bool(row.get("isPrimary")))
    for market in ordered:
        market_pk = str(market.get("lendingMarket") or "")
        if not market_pk:
            continue
        metrics = _get_json(
            f"{KAMINO_API_URL}/kamino-market/{market_pk}/reserves/metrics?env=mainnet-beta",
            headers=_kamino_headers(),
        )
        if not isinstance(metrics, list):
            continue
        if any(str(item.get("reserve") or "") == reserve for item in metrics):
            return market_pk
    return None


def build_kamino_withdraw(
    *,
    agent_wallet: str,
    amount: float,
    venue: dict[str, Any],
) -> dict[str, Any]:
    route = str(venue.get("deposit_route") or "")
    amount_text = f"{float(amount):.9f}".rstrip("0").rstrip(".")
    if route == "kamino_lend":
        market = venue.get("market") or find_kamino_market(str(venue.get("reserve") or ""))
        if not market:
            return {"error": "Could not find the Kamino market for this reserve."}
        url = f"{KAMINO_API_URL}/ktx/klend/withdraw"
        body = {
            "wallet": agent_wallet,
            "market": market,
            "reserve": venue.get("reserve"),
            "amount": amount_text,
        }
    elif route == "kamino_vault":
        url = f"{KAMINO_API_URL}/ktx/kvault/withdraw"
        body = {
            "wallet": agent_wallet,
            "kvault": venue.get("kvault"),
            "amount": amount_text,
        }
    else:
        return {"error": "This venue has no Kamino withdraw route."}
    res = requests.post(
        url,
        json=body,
        headers={**_kamino_headers(), "Content-Type": "application/json"},
        timeout=30,
    )
    try:
        data = res.json()
    except Exception:
        data = {"message": res.text[:300]}
    if res.status_code >= 400:
        return {"error": data.get("message") or data.get("error") or "Kamino withdraw build failed.", "details": data}
    tx = data.get("transaction")
    if not tx:
        return {"error": "Kamino did not return a withdraw transaction.", "details": data}
    return {"transaction": tx}


def submit_protocol_transaction(user_wallet: str, tx_b64: str) -> dict[str, Any]:
    """Sign a protocol-built transaction with the yield wallet, send it, and wait until it lands.

    Kamino returns a transaction that already contains a blockhash. Circle signing can
    outlast that blockhash. sendTransaction still returns a signature in that case, so
    success is only reported after the signature is confirmed on-chain.
    """
    from circle_dca_wallets import circle_sign_raw_transaction, resolve_agent_signing_context
    from dca_agent import _confirm_transaction, _is_blockhash_error, sol_rpc

    signing = resolve_agent_signing_context(user_wallet, "yield")
    wallet_id = signing.get("wallet_id") if signing.get("mode") == "circle" else None
    keypair = signing.get("keypair") if signing.get("mode") == "local" else None
    try:
        if wallet_id:
            encoded = circle_sign_raw_transaction(str(wallet_id), tx_b64)
        elif keypair:
            encoded = _sign_local(tx_b64, keypair)
        else:
            return {"status": "failed", "error": "Yield wallet is not configured (Circle)."}
        signature = sol_rpc(
            "sendTransaction",
            [
                encoded,
                {
                    "encoding": "base64",
                    "skipPreflight": True,
                    "preflightCommitment": "confirmed",
                    "maxRetries": 5,
                },
            ],
        )
    except Exception as exc:
        text = str(exc)
        return {
            "status": "failed",
            "error": text,
            "retryable": _is_blockhash_error(text),
        }

    if not signature:
        return {"status": "failed", "error": "RPC did not return a transaction signature.", "retryable": True}

    confirm = _confirm_transaction(str(signature), timeout_s=75, encoded_tx=encoded)
    explorer = f"https://solscan.io/tx/{signature}"
    if not confirm.get("confirmed"):
        err = confirm.get("error") or "Transaction did not confirm"
        return {
            "status": "failed",
            "error": str(err),
            "signature": signature,
            "explorer_url": explorer,
            "retryable": bool(confirm.get("retryable")) or _is_blockhash_error(err),
        }
    return {
        "status": "success",
        "signature": signature,
        "explorer_url": explorer,
    }


def _sign_local(tx_b64: str, keypair: Any) -> str:
    raw = base64.b64decode(tx_b64)
    from solders.transaction import VersionedTransaction

    unsigned = VersionedTransaction.from_bytes(raw)
    signed = VersionedTransaction(unsigned.message, [keypair])
    return base64.b64encode(bytes(signed)).decode("ascii")
