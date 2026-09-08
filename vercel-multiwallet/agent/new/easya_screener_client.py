"""
EASY Screener public API client for EasyA Analysis Agent.

Docs: https://easyscreener.xyz/llms.txt
Spec: https://easyscreener.xyz/api/public/v1/openapi.json
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Optional

import requests

BASE_URL = (
    os.environ.get("EASY_SCREENER_API_URL", "")
    or os.environ.get("EZSCREENER_BASE_URL", "")
    or "https://easyscreener.xyz/api/public/v1"
).rstrip("/")
EZ_API_KEY = (
    os.environ.get("EZ_API_KEY", "")
    or os.environ.get("EASY_SCREENER_API_KEY", "")
    or os.environ.get("EZSCREENER_API_KEY", "")
).strip()
CACHE_TTL_SECONDS = int(os.environ.get("EASY_SCREENER_CACHE_TTL_SECONDS", "3600"))
ATTRIBUTION = "Market and diligence data from EASY Screener (easyscreener.xyz)."

_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, Any]] = {}
_fatal_auth_error: Optional[str] = None


class EasyScreenerError(Exception):
    def __init__(self, code: str, message: str, *, fatal: bool = False, retry_after: Optional[int] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.fatal = fatal
        self.retry_after = retry_after


def screener_configured() -> bool:
    return bool(EZ_API_KEY)


def _cache_get(key: str) -> Optional[Any]:
    now = time.time()
    with _cache_lock:
        entry = _cache.get(key)
        if not entry:
            return None
        expires_at, value = entry
        if expires_at <= now:
            _cache.pop(key, None)
            return None
        return value


def _cache_set(key: str, value: Any, ttl: int = CACHE_TTL_SECONDS) -> None:
    with _cache_lock:
        _cache[key] = (time.time() + ttl, value)


def clear_screener_cache() -> None:
    global _fatal_auth_error
    with _cache_lock:
        _cache.clear()
    _fatal_auth_error = None


def _headers() -> dict[str, str]:
    if not EZ_API_KEY:
        raise EasyScreenerError(
            "INVALID_KEY",
            "EZ_API_KEY is not set. Add it to agent/new/.env",
            fatal=True,
        )
    return {
        "Authorization": f"Bearer {EZ_API_KEY}",
        "Accept": "application/json",
        "User-Agent": "BITAgents-EasyAAnalysis/1.0",
    }


def _parse_error(resp: requests.Response) -> EasyScreenerError:
    code = "UPSTREAM_ERROR"
    message = resp.text or resp.reason or "Request failed"
    retry_after: Optional[int] = None
    try:
        body = resp.json()
        err = body.get("error") or {}
        if isinstance(err, dict):
            code = str(err.get("code") or code)
            message = str(err.get("message") or message)
            if err.get("retryAfter") is not None:
                retry_after = int(err["retryAfter"])
    except Exception:
        pass

    if resp.status_code == 429:
        code = "RATE_LIMITED"
        if retry_after is None and resp.headers.get("Retry-After"):
            try:
                retry_after = int(resp.headers["Retry-After"])
            except ValueError:
                pass
    elif resp.status_code == 401:
        code = code if code != "UPSTREAM_ERROR" else "INVALID_KEY"
    elif resp.status_code == 403:
        code = code if code != "UPSTREAM_ERROR" else "SCOPE_MISSING"
    elif resp.status_code == 404:
        code = "NOT_FOUND"

    fatal = code in {
        "INVALID_KEY",
        "TERMS_NOT_ACCEPTED",
        "KEY_DISABLED",
    } or resp.status_code == 401
    return EasyScreenerError(code, message, fatal=fatal, retry_after=retry_after)


def _request(
    method: str,
    path: str,
    *,
    params: Optional[dict[str, Any]] = None,
    cache_key: Optional[str] = None,
    cache_ttl: int = CACHE_TTL_SECONDS,
    max_attempts: int = 3,
) -> Any:
    global _fatal_auth_error
    if _fatal_auth_error:
        raise EasyScreenerError(_fatal_auth_error, _fatal_auth_error, fatal=True)

    if cache_key:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

    url = f"{BASE_URL}{path}"
    last_exc: Optional[Exception] = None

    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.request(
                method,
                url,
                headers=_headers(),
                params=params,
                timeout=30,
            )
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < max_attempts:
                time.sleep(min(2 * attempt, 6))
                continue
            raise EasyScreenerError("UPSTREAM_ERROR", str(exc)) from exc

        if resp.status_code == 429 and attempt < max_attempts:
            err = _parse_error(resp)
            time.sleep(err.retry_after or min(2 * attempt, 10))
            continue

        if resp.status_code >= 400:
            err = _parse_error(resp)
            if err.fatal:
                _fatal_auth_error = err.code
            raise err

        try:
            data = resp.json()
        except ValueError as exc:
            raise EasyScreenerError("UPSTREAM_ERROR", "Invalid JSON from EASY Screener") from exc

        if cache_key:
            _cache_set(cache_key, data, ttl=cache_ttl)
        return data

    if last_exc:
        raise EasyScreenerError("UPSTREAM_ERROR", str(last_exc))
    raise EasyScreenerError("UPSTREAM_ERROR", "Request failed")


def _looks_like_mint(value: str) -> bool:
    value = (value or "").strip()
    return len(value) >= 32 and len(value) <= 44


def _normalize_token_row(row: dict[str, Any]) -> dict[str, Any]:
    social = row.get("social") or {}
    return {
        "mint": row.get("mint"),
        "symbol": row.get("symbol"),
        "name": row.get("name"),
        "icon": row.get("icon"),
        "chain": row.get("chain") or "solana",
        "dex": row.get("dex"),
        "created_at": row.get("createdAt"),
        "price_usd": row.get("price"),
        "market_cap_usd": row.get("mcap"),
        "fdv_usd": row.get("fdv"),
        "liquidity_usd": row.get("liquidity"),
        "volume_24h_usd": row.get("volume24h"),
        "holder_count": row.get("holderCount"),
        "price_change_5m_pct": row.get("priceChange5m"),
        "price_change_1h_pct": row.get("priceChange1h"),
        "price_change_6h_pct": row.get("priceChange6h"),
        "price_change_24h_pct": row.get("priceChange24h"),
        "is_verified": row.get("isVerified"),
        "tags": row.get("tags") or [],
        "social": social,
        "website": social.get("website"),
        "twitter": social.get("twitter"),
        "telegram": social.get("telegram"),
        "github": social.get("github"),
        "attribution": ATTRIBUTION,
    }


def _pick_best_match(tokens: list[dict[str, Any]]) -> dict[str, Any]:
    if not tokens:
        raise EasyScreenerError("NOT_FOUND", "Token not found on EASY Screener.")
    if len(tokens) == 1:
        return tokens[0]

    def _mcap(t: dict[str, Any]) -> float:
        val = t.get("mcap")
        return float(val) if val is not None else -1.0

    ranked = sorted(tokens, key=_mcap, reverse=True)
    return ranked[0]


def lookup_by_symbol(symbol: str) -> dict[str, Any]:
    sym = (symbol or "").strip().lstrip("$")
    if not sym:
        return {"error": "Symbol is required."}
    cache_key = f"symbol:{sym.upper()}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        data = _request("GET", f"/tokens/by-symbol/{sym}", cache_key=f"raw:symbol:{sym.upper()}")
    except EasyScreenerError as exc:
        return {"error": exc.message, "code": exc.code, "fatal": exc.fatal}

    if data.get("multipleMatches"):
        tokens = [_normalize_token_row(t) for t in (data.get("tokens") or [])]
        best = _pick_best_match(data.get("tokens") or [])
        result = {
            "multiple_matches": True,
            "symbol": data.get("symbol") or sym.upper(),
            "token": _normalize_token_row(best),
            "alternatives": tokens,
            "note": "Multiple Kickstart tokens share this symbol - picked highest mcap. Disambiguate by mint if needed.",
            "attribution": ATTRIBUTION,
        }
    else:
        token = data.get("token") or {}
        result = {
            "multiple_matches": False,
            "symbol": token.get("symbol") or sym.upper(),
            "token": _normalize_token_row(token),
            "attribution": ATTRIBUTION,
        }

    _cache_set(cache_key, result)
    return result


def lookup_by_mint(mint: str) -> dict[str, Any]:
    mint = (mint or "").strip()
    if not mint:
        return {"error": "Mint address is required."}
    cache_key = f"mint:{mint}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        data = _request("GET", f"/tokens/by-mint/{mint}", cache_key=f"raw:mint:{mint}")
    except EasyScreenerError as exc:
        return {"error": exc.message, "code": exc.code, "fatal": exc.fatal}

    token = _normalize_token_row(data.get("token") or {})
    result = {"token": token, "attribution": ATTRIBUTION}
    _cache_set(cache_key, result)
    return result


def search_tokens(query: str, limit: int = 10) -> dict[str, Any]:
    q = (query or "").strip()
    if not q:
        return {"error": "Search query is required.", "tokens": []}
    limit = max(1, min(int(limit), 20))
    cache_key = f"search:{q.lower()}:{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        data = _request(
            "GET",
            "/tokens/search",
            params={"q": q, "limit": limit},
            cache_key=f"raw:search:{q.lower()}:{limit}",
            cache_ttl=min(CACHE_TTL_SECONDS, 900),
        )
    except EasyScreenerError as exc:
        return {"error": exc.message, "code": exc.code, "tokens": []}

    rows = data.get("tokens") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        rows = data.get("results") if isinstance(data, dict) else []
    tokens = [_normalize_token_row(t) for t in (rows or [])[:limit]]
    result = {
        "query": q,
        "count": len(tokens),
        "tokens": tokens,
        "source": "easy_screener",
        "attribution": ATTRIBUTION,
    }
    _cache_set(cache_key, result, ttl=min(CACHE_TTL_SECONDS, 900))
    return result


def list_tokens(
    page: int = 0,
    limit: int = 50,
    sort: str = "mcap",
    verified_only: bool = True,
) -> dict[str, Any]:
    limit = max(1, min(int(limit), 100))
    page = max(0, int(page))
    cache_key = f"list:{page}:{limit}:{sort}:{verified_only}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    params: dict[str, Any] = {"page": page, "limit": limit, "sort": sort}
    if verified_only:
        params["verified"] = "true"

    try:
        data = _request(
            "GET",
            "/tokens",
            params=params,
            cache_key=f"raw:list:{page}:{limit}:{sort}:{verified_only}",
            cache_ttl=min(CACHE_TTL_SECONDS, 900),
        )
    except EasyScreenerError as exc:
        return {"error": exc.message, "code": exc.code, "tokens": []}

    tokens = [_normalize_token_row(t) for t in (data.get("tokens") or [])]
    result = {
        "tokens": tokens,
        "pagination": data.get("pagination"),
        "count": len(tokens),
        "source": "easy_screener",
        "verified_only": verified_only,
        "attribution": ATTRIBUTION,
    }
    _cache_set(cache_key, result, ttl=min(CACHE_TTL_SECONDS, 900))
    return result


def get_locked_supply(mint: str) -> dict[str, Any]:
    mint = (mint or "").strip()
    cache_key = f"locked:{mint}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        data = _request("GET", f"/tokens/{mint}/locked-supply", cache_key=f"raw:locked:{mint}")
    except EasyScreenerError as exc:
        return {"error": exc.message, "code": exc.code, "mint": mint}

    if isinstance(data, dict):
        data.setdefault("attribution", ATTRIBUTION)
    _cache_set(cache_key, data)
    return data


def get_token_summary(mint: str) -> dict[str, Any]:
    mint = (mint or "").strip()
    cache_key = f"summary:{mint}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        data = _request("GET", f"/tokens/{mint}/summary", cache_key=f"raw:summary:{mint}")
    except EasyScreenerError as exc:
        return {"error": exc.message, "code": exc.code, "mint": mint}

    if isinstance(data, dict):
        data.setdefault("attribution", ATTRIBUTION)
    _cache_set(cache_key, data)
    return data


def resolve_token(token: str) -> dict[str, Any]:
    """Resolve symbol or mint to a normalized EASY Screener token row."""
    raw = (token or "").strip()
    if not raw:
        return {"error": "Token symbol or mint is required."}

    if _looks_like_mint(raw):
        result = lookup_by_mint(raw)
    else:
        result = lookup_by_symbol(raw)

    if result.get("error"):
        return result
    return result.get("token") or result


def get_token_bundle(
    token: str,
    *,
    include_summary: bool = False,
    include_locked: bool = True,
) -> dict[str, Any]:
    """
    Full diligence bundle for a token - cached 1hr per mint.
    Combines token row + optional AI summary + locked supply.
    """
    resolved = resolve_token(token)
    if resolved.get("error"):
        return resolved

    mint = resolved.get("mint")
    if not mint:
        return {"error": "Could not resolve mint from EASY Screener."}

    bundle_key = f"bundle:{mint}:s{int(include_summary)}:l{int(include_locked)}"
    cached = _cache_get(bundle_key)
    if cached is not None:
        return cached

    bundle: dict[str, Any] = {
        "token": resolved,
        "mint": mint,
        "symbol": resolved.get("symbol"),
        "name": resolved.get("name"),
        "attribution": ATTRIBUTION,
    }

    if include_summary:
        summary = get_token_summary(mint)
        if "error" not in summary:
            bundle["summary"] = summary
        elif summary.get("code") == "SCOPE_MISSING":
            bundle["summary_unavailable"] = summary.get("message") or "AI summary requires summary:read scope."

    if include_locked:
        locked = get_locked_supply(mint)
        if "error" not in locked:
            bundle["locked_supply"] = locked

    _cache_set(bundle_key, bundle)
    return bundle


def get_allowlist_prompt_block() -> str:
    listed = list_tokens(page=0, limit=20, verified_only=True)
    if listed.get("error"):
        return (
            "## EASY Screener\n"
            f"Could not load token sample: {listed['error']}\n"
            "Use search_tokens or get_token_overview after EZ_API_KEY is configured."
        )

    tokens = listed.get("tokens") or []
    lines = [
        "## EASY Screener (easyscreener.xyz)",
        "All token analysis uses live EASY Screener data (cached 1h per mint).",
        "Use **get_token_overview** for any symbol/mint, or **search_tokens** to discover tokens.",
        "",
    ]
    if tokens:
        lines.append(f"Sample verified Kickstart tokens ({len(tokens)}):")
        lines.append("")
        for t in tokens:
            mcap = t.get("market_cap_usd")
            mcap_label = f"${mcap:,.0f}" if isinstance(mcap, (int, float)) else "n/a"
            lines.append(
                f"- **{t.get('symbol')}** ({t.get('name')}) · mint `{t.get('mint')}` · mcap {mcap_label}"
            )
    else:
        lines.append("No verified sample tokens returned - use search_tokens for discovery.")
    lines.append("")
    lines.append("If NOT_FOUND by symbol, search or ask for mint to disambiguate.")
    return "\n".join(lines)
