"""Yahoo Finance market data helpers — open ticker resolution for any Yahoo asset."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

# Display / natural-language aliases -> Yahoo Finance ticker
YAHOO_TICKER_MAP: dict[str, str] = {
    # Crypto
    "BTC": "BTC-USD",
    "BITCOIN": "BTC-USD",
    "ETH": "ETH-USD",
    "ETHEREUM": "ETH-USD",
    "SOL": "SOL-USD",
    "SOLANA": "SOL-USD",
    "XRP": "XRP-USD",
    "RIPPLE": "XRP-USD",
    "DOGE": "DOGE-USD",
    "DOGECOIN": "DOGE-USD",
    "ADA": "ADA-USD",
    "CARDANO": "ADA-USD",
    "AVAX": "AVAX-USD",
    "LINK": "LINK-USD",
    "DOT": "DOT-USD",
    "MATIC": "MATIC-USD",
    "POLYGON": "MATIC-USD",
    "BNB": "BNB-USD",
    "LTC": "LTC-USD",
    "LITECOIN": "LTC-USD",
    "ATOM": "ATOM-USD",
    "NEAR": "NEAR-USD",
    "APT": "APT-USD",
    "ARB": "ARB-USD",
    "OP": "OP-USD",
    "SUI": "SUI-USD",
    "PEPE": "PEPE-USD",
    "SHIB": "SHIB-USD",
    "UNI": "UNI-USD",
    "AAVE": "AAVE-USD",
    "BTC-USD": "BTC-USD",
    "ETH-USD": "ETH-USD",
    "SOL-USD": "SOL-USD",
    "XRP-USD": "XRP-USD",
    # Indices / S&P (trade via liquid ETF SPY for paper fills)
    "SPY": "SPY",
    "SPX": "SPY",
    "GSPC": "SPY",
    "^GSPC": "^GSPC",
    "S&P": "SPY",
    "S&P500": "SPY",
    "S&P5OO": "SPY",  # OCR-ish
    "SP500": "SPY",
    "SPX500": "SPY",
    "SNP": "SPY",
    "SNP500": "SPY",
    "STANDARDANDPOORS": "SPY",
    "STANDARDPOORS": "SPY",
    "US500": "SPY",
    "QQQ": "QQQ",
    "NASDAQ": "QQQ",
    "NDX": "QQQ",
    "DIA": "DIA",
    "DOW": "DIA",
    "DJIA": "DIA",
    "IWM": "IWM",
    "RUSSELL2000": "IWM",
}

# Phrase aliases matched in free text (order matters — longer first)
PHRASE_ALIASES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bs\s*&\s*p\s*500\b", re.I), "SPY"),
    (re.compile(r"\bs\s*and\s*p\s*500\b", re.I), "SPY"),
    (re.compile(r"\bsp\s*500\b", re.I), "SPY"),
    (re.compile(r"\bspx\s*500\b", re.I), "SPY"),
    (re.compile(r"\bs&p\b", re.I), "SPY"),
    (re.compile(r"\bstandard\s*&\s*poor'?s?\b", re.I), "SPY"),
    (re.compile(r"\bnasdaq\s*100\b", re.I), "QQQ"),
    (re.compile(r"\bdow\s*jones\b", re.I), "DIA"),
    (re.compile(r"\brussell\s*2000\b", re.I), "IWM"),
]

DEFAULT_STOCK_CRYPTO_BOOK: list[str] = [
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "BTC",
    "ETH",
    "SOL",
]

CANDIDATE_UNIVERSE: list[str] = [
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "GOOGL",
    "META",
    "TSLA",
    "NFLX",
    "AMD",
    "AVGO",
    "CRM",
    "ORCL",
    "JPM",
    "BAC",
    "GS",
    "V",
    "MA",
    "XOM",
    "CVX",
    "KO",
    "PEP",
    "WMT",
    "COST",
    "DIS",
    "UNH",
    "JNJ",
    "LLY",
    "PLTR",
    "COIN",
    "MSTR",
    "UBER",
    "SHOP",
    "BA",
    "CAT",
    "GE",
    "QQQ",
    "IWM",
    "GLD",
    "TLT",
    "ARKK",
    "SPY",
    "BTC",
    "ETH",
    "SOL",
    "XRP",
    "AVAX",
    "LINK",
]

KNOWN_STOCK_TICKERS = frozenset(
    {
        *CANDIDATE_UNIVERSE,
        "GOOG",
        "INTC",
        "IBM",
        "DIA",
        "SLV",
        "UNG",
        "HYG",
        "HOOD",
        "SOFI",
        "ABNB",
        "SQ",
        "PYPL",
        "BABA",
        "NKE",
        "SBUX",
        "F",
        "GM",
        "DOT",
        "MATIC",
        "DOGE",
        "ADA",
        "BNB",
        "LTC",
        "ATOM",
        "NEAR",
        "APT",
        "ARB",
        "SUI",
        "UNI",
        "AAVE",
        "SPX",
        "SP500",
    }
)

_CRYPTO_USD = frozenset(
    {
        "BTC-USD",
        "ETH-USD",
        "SOL-USD",
        "XRP-USD",
        "DOGE-USD",
        "ADA-USD",
        "AVAX-USD",
        "LINK-USD",
        "DOT-USD",
        "MATIC-USD",
        "BNB-USD",
        "LTC-USD",
        "ATOM-USD",
        "NEAR-USD",
        "APT-USD",
        "ARB-USD",
        "OP-USD",
        "SUI-USD",
        "PEPE-USD",
        "SHIB-USD",
        "UNI-USD",
        "AAVE-USD",
    }
)

_yahoo_probe_cache: dict[str, Optional[str]] = {}


def _normalize_raw(token: str) -> str:
    t = (token or "").strip().upper()
    t = t.replace(" ", "").replace("_", "")
    # Keep ^ for indices; strip $ prefix
    if t.startswith("$"):
        t = t[1:]
    return t


def re_fullmatch_ticker(raw: str) -> bool:
    return bool(re.fullmatch(r"\^?[A-Z]{1,6}(?:[.=-][A-Z0-9]{1,6})?", raw))


def to_yahoo_symbol(token: str) -> Optional[str]:
    raw = _normalize_raw(token)
    if not raw:
        return None
    # Phrase-like keys already normalized without spaces
    if raw in YAHOO_TICKER_MAP:
        return YAHOO_TICKER_MAP[raw]
    # Handle S&P500 with ampersand retained
    amp = (token or "").strip().upper().replace(" ", "")
    if amp in YAHOO_TICKER_MAP:
        return YAHOO_TICKER_MAP[amp]
    if raw.endswith("-USD") and len(raw) <= 16:
        return raw
    if re_fullmatch_ticker(raw):
        return raw
    return None


def display_symbol(yahoo_symbol: str) -> str:
    reverse = {
        "BTC-USD": "BTC",
        "ETH-USD": "ETH",
        "SOL-USD": "SOL",
        "XRP-USD": "XRP",
        "DOGE-USD": "DOGE",
        "ADA-USD": "ADA",
        "AVAX-USD": "AVAX",
        "LINK-USD": "LINK",
        "DOT-USD": "DOT",
        "MATIC-USD": "MATIC",
        "BNB-USD": "BNB",
        "LTC-USD": "LTC",
        "ATOM-USD": "ATOM",
        "NEAR-USD": "NEAR",
        "APT-USD": "APT",
        "ARB-USD": "ARB",
        "OP-USD": "OP",
        "SUI-USD": "SUI",
        "PEPE-USD": "PEPE",
        "SHIB-USD": "SHIB",
        "UNI-USD": "UNI",
        "AAVE-USD": "AAVE",
        "^GSPC": "SPX",
        "SPY": "SPY",
    }
    return reverse.get(yahoo_symbol, yahoo_symbol)


def probe_yahoo_ticker(candidate: str) -> Optional[str]:
    """Confirm a ticker exists on Yahoo (cached). Returns yahoo symbol or None."""
    key = candidate.strip()
    if not key:
        return None
    if key in _yahoo_probe_cache:
        return _yahoo_probe_cache[key]
    try:
        import yfinance as yf
    except ImportError:
        _yahoo_probe_cache[key] = None
        return None
    try:
        hist = yf.Ticker(key).history(period="5d", auto_adjust=True)
        ok = hist is not None and not hist.empty
        _yahoo_probe_cache[key] = key if ok else None
    except Exception:
        _yahoo_probe_cache[key] = None
    return _yahoo_probe_cache[key]


def resolve_yahoo_asset(token: str, probe: bool = True) -> dict[str, Any]:
    """
    Resolve any user asset to a Yahoo ticker.
    Tries aliases, then standard ticker form, then live Yahoo probe
    (SYMBOL, SYMBOL-USD, ^SYMBOL).
    """
    raw_in = (token or "").strip()
    if not raw_in:
        return {"error": "Empty ticker"}

    yahoo = to_yahoo_symbol(raw_in)
    if not yahoo and probe:
        raw = _normalize_raw(raw_in)
        # Try as-is, crypto -USD, and index ^
        for candidate in (raw, f"{raw}-USD", f"^{raw}" if not raw.startswith("^") else raw):
            if not re_fullmatch_ticker(candidate) and not candidate.endswith("-USD"):
                continue
            found = probe_yahoo_ticker(candidate)
            if found:
                yahoo = found
                break

    if not yahoo:
        return {
            "error": (
                f"Unrecognized ticker '{token}' on Yahoo Finance. "
                "Try a Yahoo symbol e.g. XRP, AAPL, SPY, BTC-USD, ^GSPC."
            )
        }

    # Prefer probing known map targets too (catch dead aliases)
    if probe and yahoo not in _yahoo_probe_cache:
        if not probe_yahoo_ticker(yahoo):
            # Fallback: crypto form
            if not yahoo.endswith("-USD") and not yahoo.startswith("^"):
                alt = probe_yahoo_ticker(f"{yahoo}-USD")
                if alt:
                    yahoo = alt
                else:
                    return {"error": f"Yahoo Finance has no recent data for '{token}' ({yahoo})."}

    crypto = yahoo.endswith("-USD") or yahoo in _CRYPTO_USD
    index = yahoo.startswith("^")
    return {
        "symbol": display_symbol(yahoo),
        "yahoo_symbol": yahoo,
        "asset_class": "crypto" if crypto else ("index" if index else "equity"),
    }


def extract_tickers_from_text(text: str) -> list[str]:
    """Pull Yahoo-eligible tickers / aliases from free-form user text."""
    if not text:
        return []
    found: list[str] = []

    def add(sym: str) -> None:
        s = sym.strip().upper()
        if not s or s in found:
            return
        found.append(s)

    for pattern, sym in PHRASE_ALIASES:
        if pattern.search(text):
            add(sym)

    for m in re.findall(r"\$([A-Za-z]{1,6})\b", text):
        add(m)

    # Explicit mapped names (XRP, BITCOIN, SP500, …)
    allow = set(YAHOO_TICKER_MAP) | set(KNOWN_STOCK_TICKERS)
    for s in re.findall(r"\b([A-Za-z]{1,6})\b", text.upper()):
        if s in allow:
            add(s)

    # Yahoo crypto form BTC-USD
    for m in re.findall(r"\b([A-Za-z]{1,6}-USD)\b", text.upper()):
        add(m)

    # Index ^GSPC
    for m in re.findall(r"(\^[A-Za-z]{1,6})\b", text.upper()):
        add(m)

    # Natural language crypto
    if re.search(r"\bbitcoin\b", text, re.I):
        add("BTC")
    if re.search(r"\bethereum\b", text, re.I):
        add("ETH")
    if re.search(r"\bripple\b|\bxrp\b", text, re.I):
        add("XRP")

    return found[:12]


def fetch_yahoo_daily_prices(yahoo_symbol: str, start_date: str, end_date: str) -> dict[str, Any]:
    """Return prices as [[ms_epoch, close], ...] via yfinance."""
    try:
        import yfinance as yf
    except ImportError:
        return {"error": "yfinance is not installed. Run: pip install yfinance"}

    try:
        end_plus = (datetime.strptime(end_date[:10], "%Y-%m-%d") + timedelta(days=2)).strftime("%Y-%m-%d")
        ticker = yf.Ticker(yahoo_symbol)
        hist = ticker.history(start=start_date[:10], end=end_plus, auto_adjust=True)
        if hist is None or hist.empty:
            return {"error": f"Yahoo Finance returned no bars for {yahoo_symbol}"}

        closes = hist["Close"].dropna()
        if len(closes) < 2:
            return {"error": f"Insufficient Yahoo history for {yahoo_symbol}"}

        prices: list[list[float]] = []
        for idx, value in closes.items():
            ts = idx.to_pydatetime()
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            prices.append([ts.timestamp() * 1000, float(value)])
        return {"prices": prices, "source": "yahoo_finance"}
    except Exception as exc:
        return {"error": f"Yahoo Finance fetch failed for {yahoo_symbol}: {exc}"}


def fetch_yahoo_news(symbols: list[str], limit_per_symbol: int = 3) -> list[dict[str, Any]]:
    """Recent Yahoo Finance headlines for the selected assets."""
    try:
        import yfinance as yf
    except ImportError:
        return []

    out: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for raw in symbols[:8]:
        resolved = resolve_yahoo_asset(raw)
        if resolved.get("error"):
            continue
        yahoo = resolved["yahoo_symbol"]
        try:
            items = yf.Ticker(yahoo).news or []
        except Exception:
            items = []
        count = 0
        for item in items:
            content = item.get("content") if isinstance(item.get("content"), dict) else None
            title = (
                item.get("title")
                or (content or {}).get("title")
                or item.get("headline")
                or ""
            )
            title = str(title).strip()
            if not title or title in seen_titles:
                continue
            link = (
                item.get("link")
                or item.get("url")
                or ((content or {}).get("clickThroughUrl") or {}).get("url")
                or ""
            )
            publisher = item.get("publisher") or (content or {}).get("provider", {}).get("displayName") or "Yahoo"
            seen_titles.add(title)
            out.append(
                {
                    "symbol": resolved["symbol"],
                    "title": title[:180],
                    "publisher": publisher,
                    "link": link,
                }
            )
            count += 1
            if count >= limit_per_symbol:
                break
    return out
