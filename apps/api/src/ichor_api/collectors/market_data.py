"""Market data collector — daily OHLCV from free public sources.

Two adapters, used as fallback chain:

  1. **Stooq** — direct CSV via HTTP, no API key, no rate limit, full
     historical coverage for FX majors / metals / indices since the 1980s.
     Format : `https://stooq.com/q/d/l/?s={symbol}&i=d` returns
     `Date,Open,High,Low,Close,Volume` CSV.

  2. **yfinance** — optional fallback when Stooq is unreachable / serving
     truncated data. Lazy-imported to keep the dep optional. Daily 1d bars.

Each adapter normalizes its output into `MarketDataPoint` records keyed by
the canonical Ichor asset code (EUR_USD, XAU_USD, NAS100_USD, …). The
canonical → upstream mapping is per-source.

No API key required. Free for both sources. Dataset suitable for
walk-forward backtests; sufficient resolution for daily briefings — but
NOT for sub-daily microstructure (use OANDA M1 in Phase 1+ when a key is
available).
"""

from __future__ import annotations

import asyncio
import csv
import io
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx
import structlog

log = structlog.get_logger(__name__)

STOOQ_BASE = "https://stooq.com/q/d/l/"

# Canonical Ichor asset code → Stooq symbol. Stooq uses lowercase tickers
# for FX + metals, `^index` for cash indices. Verified manually 2026-05-03.
STOOQ_SYMBOLS: dict[str, str] = {
    "EUR_USD": "eurusd",
    "GBP_USD": "gbpusd",
    "USD_JPY": "usdjpy",
    "AUD_USD": "audusd",
    "USD_CAD": "usdcad",
    "XAU_USD": "xauusd",
    "NAS100_USD": "^ndx",
    "SPX500_USD": "^spx",
}

# yfinance ticker mapping — `=X` suffix for FX, plain index name otherwise.
YFINANCE_SYMBOLS: dict[str, str] = {
    "EUR_USD": "EURUSD=X",
    "GBP_USD": "GBPUSD=X",
    "USD_JPY": "USDJPY=X",
    "AUD_USD": "AUDUSD=X",
    "USD_CAD": "USDCAD=X",
    # Yahoo has no XAUUSD=X spot ticker. Use gold front-month future
    # GC=F as a close proxy — daily settle is within ~0.1 % of spot
    # for briefing-context use.
    "XAU_USD": "GC=F",
    "NAS100_USD": "^NDX",
    "SPX500_USD": "^GSPC",
}


@dataclass(frozen=True)
class MarketDataPoint:
    """Daily OHLCV bar for a single asset."""

    asset: str
    bar_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float | None
    source: str
    fetched_at: datetime


def parse_stooq_csv(asset: str, body: bytes) -> list[MarketDataPoint]:
    """Parse a Stooq daily-CSV response into normalized rows.

    Stooq returns either real CSV or `No data` plain text on bad symbols /
    rate-limit. Defensive parsing : returns [] on any unexpected shape.
    """
    text = body.decode("utf-8", errors="replace").strip()
    if not text or text.lower().startswith("no data"):
        log.warning("stooq.no_data", asset=asset)
        return []

    fetched = datetime.now(UTC)
    rows: list[MarketDataPoint] = []

    reader = csv.DictReader(io.StringIO(text))
    expected = {"Date", "Open", "High", "Low", "Close"}
    if not expected.issubset(set(reader.fieldnames or [])):
        log.warning(
            "stooq.unexpected_header",
            asset=asset,
            header=reader.fieldnames,
        )
        return []

    for row in reader:
        try:
            bar = MarketDataPoint(
                asset=asset,
                bar_date=date.fromisoformat(row["Date"]),
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row["Volume"]) if row.get("Volume") else None,
                source="stooq",
                fetched_at=fetched,
            )
        except (KeyError, ValueError) as e:
            log.warning("stooq.parse_row_failed", asset=asset, error=str(e))
            continue
        rows.append(bar)

    return rows


async def fetch_stooq(
    asset: str,
    *,
    client: httpx.AsyncClient,
    interval: str = "d",
    timeout: float = 30.0,
) -> list[MarketDataPoint]:
    """Fetch full available history for `asset` from Stooq."""
    symbol = STOOQ_SYMBOLS.get(asset)
    if symbol is None:
        log.warning("stooq.unknown_asset", asset=asset)
        return []

    try:
        r = await client.get(
            STOOQ_BASE,
            params={"s": symbol, "i": interval},
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": "IchorMarketDataCollector/0.1",
                "Accept": "text/csv, text/plain, */*",
            },
        )
        r.raise_for_status()
    except httpx.HTTPError as e:
        log.warning("stooq.fetch_failed", asset=asset, error=str(e))
        return []

    return parse_stooq_csv(asset, r.content)


async def fetch_yfinance(
    asset: str,
    *,
    period: str = "10y",
    interval: str = "1d",
) -> list[MarketDataPoint]:
    """Fallback to yfinance. Lazy-imported : if the dep isn't installed,
    log + return []. Designed for "Stooq down today, fall back" use.
    """
    try:
        import yfinance as yf  # type: ignore[import-not-found]
    except ImportError:
        log.warning("yfinance.not_installed", asset=asset)
        return []

    symbol = YFINANCE_SYMBOLS.get(asset)
    if symbol is None:
        log.warning("yfinance.unknown_asset", asset=asset)
        return []

    def _blocking() -> list[MarketDataPoint]:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval, auto_adjust=False)
        if df.empty:
            return []
        fetched = datetime.now(UTC)
        out: list[MarketDataPoint] = []
        for ts, row in df.iterrows():
            try:
                bar_date = ts.date() if hasattr(ts, "date") else ts
                o, h, l, c = (
                    float(row["Open"]),
                    float(row["High"]),
                    float(row["Low"]),
                    float(row["Close"]),
                )
                # yfinance occasionally returns rows where low > close or
                # high < open by a few ulps (rounding from upstream). Pin
                # high/low to the actual OHLC envelope so the DB check
                # constraint never trips.
                lo = min(o, h, l, c)
                hi = max(o, h, l, c)
                out.append(
                    MarketDataPoint(
                        asset=asset,
                        bar_date=bar_date,
                        open=o,
                        high=hi,
                        low=lo,
                        close=c,
                        volume=(
                            float(row["Volume"])
                            if "Volume" in row and row["Volume"] == row["Volume"]
                            else None
                        ),
                        source="yfinance",
                        fetched_at=fetched,
                    )
                )
            except (KeyError, ValueError) as e:
                log.warning("yfinance.parse_row_failed", asset=asset, error=str(e))
                continue
        return out

    # yfinance is sync HTTP under the hood — run in a thread.
    return await asyncio.to_thread(_blocking)


async def fetch_one(asset: str, *, client: httpx.AsyncClient) -> list[MarketDataPoint]:
    """Try Stooq first, fall back to yfinance on empty / transient failure."""
    rows = await fetch_stooq(asset, client=client)
    if rows:
        return rows
    log.info("market_data.fallback_yfinance", asset=asset)
    return await fetch_yfinance(asset)


async def poll_all(
    assets: Iterable[str] = tuple(STOOQ_SYMBOLS.keys()),
    *,
    concurrency: int = 4,
) -> dict[str, list[MarketDataPoint]]:
    """Fetch all assets in parallel (bounded). Returns asset → bars dict."""
    sem = asyncio.Semaphore(concurrency)

    async def _one(asset: str, client: httpx.AsyncClient) -> tuple[str, list[MarketDataPoint]]:
        async with sem:
            return asset, await fetch_one(asset, client=client)

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*(_one(a, client) for a in assets))

    return dict(results)


def latest_per_asset(
    bars_by_asset: dict[str, Sequence[MarketDataPoint]],
) -> dict[str, MarketDataPoint | None]:
    """Convenience: extract the most recent bar per asset."""
    out: dict[str, MarketDataPoint | None] = {}
    for asset, bars in bars_by_asset.items():
        out[asset] = max(bars, key=lambda b: b.bar_date) if bars else None
    return out
