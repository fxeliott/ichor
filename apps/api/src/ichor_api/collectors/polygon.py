"""Polygon.io Starter — 1-min OHLCV collector.

Polygon Starter ($29/mo) covers all 8 Phase-1 assets at 1-minute
granularity with end-of-day delay (no realtime feed). Endpoint :

    GET /v2/aggs/ticker/{ticker}/range/1/minute/{from}/{to}
        ?adjusted=true&sort=asc&limit=50000

Ticker conventions in Polygon's (Massive 2026) namespace :
  C:EURUSD          forex pairs
  C:XAUUSD          spot metals (gold, silver — Currencies namespace, NOT crypto)
  X:BTCUSD          crypto pairs (X: prefix, distinct from forex)
  I:NDX / I:SPX     indices
  AAPL / SPY        equities (not used here)

Source: massive.com/blog/real-time-forex-data-plans (Currencies plan covers
forex pairs + XAU/XAG via the C: prefix). The X: prefix is reserved for
cryptocurrencies. Earlier versions of this collector mistakenly mapped
XAU_USD to "X:XAUUSD" — fixed 2026-05-03.

The collector is pure-Python (httpx). The persistence layer lives in
`collectors/persistence.py` (added separately).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import httpx

POLYGON_BASE_URL = "https://api.polygon.io"


# Polygon ticker code per Phase-1 asset. Mapping is explicit because
# the namespace prefix (C: / X: / I:) drives endpoint selection on
# Polygon's side.
ASSET_TO_TICKER: dict[str, str] = {
    "EUR_USD": "C:EURUSD",
    "GBP_USD": "C:GBPUSD",
    "USD_JPY": "C:USDJPY",
    "AUD_USD": "C:AUDUSD",
    "USD_CAD": "C:USDCAD",
    "XAU_USD": "C:XAUUSD",
    "NAS100_USD": "I:NDX",
    "SPX500_USD": "I:SPX",
    # ── Cross-asset risk-on/off proxy (not a Phase-1 trading asset) ──
    "BTC_USD": "X:BTCUSD",
}


@dataclass(frozen=True)
class PolygonBar:
    """One 1-min OHLCV bar parsed from a Polygon /v2/aggs response."""

    asset: str
    ticker: str
    bar_ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int | None
    vwap: float | None
    transactions: int | None


def _epoch_ms_to_dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000.0, tz=UTC)


def _safe_float(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _safe_int(v: Any) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def parse_aggs_response(asset: str, ticker: str, body: dict[str, Any]) -> list[PolygonBar]:
    """Convert a Polygon /v2/aggs JSON body into PolygonBar dataclasses.

    Polygon shape :
        {"status": "OK", "ticker": "...", "results": [{"t": <ms>, "o": ..., "h": ..., "l": ..., "c": ..., "v": ..., "vw": ..., "n": ...}, ...]}

    Discards rows missing any of OHLC. Volume / vwap / transactions are
    optional (some non-FX tickers omit them).
    """
    results = body.get("results") or []
    out: list[PolygonBar] = []
    for r in results:
        try:
            o = float(r["o"])
            h = float(r["h"])
            lo = float(r["l"])
            c = float(r["c"])
        except (KeyError, TypeError, ValueError):
            continue
        ts_ms = r.get("t")
        if not isinstance(ts_ms, int):
            continue
        # OHLC envelope normalization — Polygon is generally clean but
        # we keep the same defensive guard the Phase-0 collector uses
        # (some sources emit low > close by ulps).
        lo_n = min(o, h, lo, c)
        hi_n = max(o, h, lo, c)
        out.append(
            PolygonBar(
                asset=asset,
                ticker=ticker,
                bar_ts=_epoch_ms_to_dt(ts_ms),
                open=o,
                high=hi_n,
                low=lo_n,
                close=c,
                volume=_safe_int(r.get("v")),
                vwap=_safe_float(r.get("vw")),
                transactions=_safe_int(r.get("n")),
            )
        )
    return out


async def fetch_aggs(
    asset: str,
    *,
    api_key: str,
    from_date: date,
    to_date: date,
    multiplier: int = 1,
    timespan: str = "minute",
    limit: int = 50_000,
    client: httpx.AsyncClient | None = None,
) -> list[PolygonBar]:
    """Fetch and parse aggregate bars for one asset over a date window.

    Uses an injected `httpx.AsyncClient` when provided (lets the caller
    pool connections across many assets); otherwise opens a one-shot
    client.
    """
    ticker = ASSET_TO_TICKER.get(asset)
    if ticker is None:
        raise ValueError(f"unknown asset code for Polygon: {asset!r}")

    url = (
        f"{POLYGON_BASE_URL}/v2/aggs/ticker/{ticker}/range/"
        f"{multiplier}/{timespan}/{from_date.isoformat()}/{to_date.isoformat()}"
    )
    params = {
        "adjusted": "true",
        "sort": "asc",
        "limit": str(limit),
        "apiKey": api_key,
    }

    own_client = client is None
    cli = client or httpx.AsyncClient(timeout=30.0)
    try:
        r = await cli.get(url, params=params)
        r.raise_for_status()
        body = r.json()
    finally:
        if own_client:
            await cli.aclose()

    return parse_aggs_response(asset, ticker, body)


def supported_assets() -> tuple[str, ...]:
    return tuple(sorted(ASSET_TO_TICKER.keys()))
