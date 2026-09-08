"""Yahoo Finance market data helpers for hedge-fund backtests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

# Display symbol -> Yahoo Finance ticker
YAHOO_TICKER_MAP: dict[str, str] = {
    "BTC": "BTC-USD",
    "BITCOIN": "BTC-USD",
    "ETH": "ETH-USD",
    "ETHEREUM": "ETH-USD",
    "SOL": "SOL-USD",
    "SOLANA": "SOL-USD",
    "BTC-USD": "BTC-USD",
    "ETH-USD": "ETH-USD",
    "SOL-USD": "SOL-USD",
}

# Default diversified book when the user says "whatever stocks or crypto"
DEFAULT_STOCK_CRYPTO_BOOK: list[str] = [
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "BTC",
    "ETH",
    "SOL",
]

KNOWN_STOCK_TICKERS = frozenset(
    {
        "AAPL",
        "MSFT",
        "NVDA",
        "AMZN",
        "GOOGL",
        "GOOG",
        "META",
        "TSLA",
        "NFLX",
        "AMD",
        "INTC",
        "CRM",
        "ORCL",
        "IBM",
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
        "SPY",
        "QQQ",
        "IWM",
        "DIA",
        "GLD",
        "SLV",
        "UNG",
        "TLT",
        "HYG",
        "ARKK",
        "COIN",
        "MSTR",
        "HOOD",
        "PLTR",
        "SOFI",
        "UBER",
        "ABNB",
        "SHOP",
        "SQ",
        "PYPL",
        "BABA",
        "NKE",
        "SBUX",
        "BA",
        "CAT",
        "GE",
        "F",
        "GM",
    }
)


def to_yahoo_symbol(token: str) -> Optional[str]:
    raw = (token or "").strip().upper().replace(" ", "")
    if not raw:
        return None
    if raw in YAHOO_TICKER_MAP:
        return YAHOO_TICKER_MAP[raw]
    if raw.endswith("-USD") and len(raw) <= 12:
        return raw
    # Common stock / ETF tickers
    if re_fullmatch_ticker(raw):
        return raw
    return None


def re_fullmatch_ticker(raw: str) -> bool:
    import re

    return bool(re.fullmatch(r"[A-Z]{1,5}(?:\.[A-Z])?", raw))


def display_symbol(yahoo_symbol: str) -> str:
    reverse = {v: k for k, v in (("BTC", "BTC-USD"), ("ETH", "ETH-USD"), ("SOL", "SOL-USD"))}
    return reverse.get(yahoo_symbol, yahoo_symbol)


def resolve_yahoo_asset(token: str) -> dict[str, Any]:
    yahoo = to_yahoo_symbol(token)
    if not yahoo:
        return {"error": f"Unrecognized ticker '{token}' for Yahoo Finance."}
    return {
        "symbol": display_symbol(yahoo),
        "yahoo_symbol": yahoo,
        "asset_class": "crypto" if yahoo.endswith("-USD") and yahoo in {"BTC-USD", "ETH-USD", "SOL-USD"} else (
            "crypto" if yahoo.endswith("-USD") else "equity"
        ),
    }


def fetch_yahoo_daily_prices(yahoo_symbol: str, start_date: str, end_date: str) -> dict[str, Any]:
    """Return prices as [[ms_epoch, close], ...] via yfinance."""
    try:
        import yfinance as yf
    except ImportError:
        return {"error": "yfinance is not installed. Run: pip install yfinance"}

    try:
        # yfinance end is exclusive — pad one day
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
            # yfinance shapes vary by version
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
