"""VIX live collector — pulls the latest CBOE VIX index value via yfinance.

The Phase-1 stack only had VIX term structure (FRED VIXCLS daily, lagged
by 1 trading day). Real-time intraday is essential for Crisis Mode
detection (`alerts.py:VIX_PANIC` rule needs current vs prior tick).

Yahoo Finance ticker `^VIX` exposes the underlying SPX 30-day implied
vol; ETN tickers (UVXY, VXX) drift from VIX over time and are rejected.

Free, no API key. Rate limit: ~2k req/h soft; we poll every 5 min during
US session window (13:30-22:00 UTC), idle otherwise. Total ~108 calls/day.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

YF_QUOTE_URL = "https://query2.finance.yahoo.com/v7/finance/quote"


@dataclass(frozen=True)
class VixSnapshot:
    """One VIX live snapshot."""

    value: float
    """Current VIX level (e.g. 14.32, 35.00)."""

    change_abs: float | None
    change_pct: float | None
    market_state: str  # "REGULAR", "POST", "CLOSED", "PRE"
    fetched_at: datetime
    raw: dict


async def fetch_vix(*, timeout_s: float = 10.0) -> VixSnapshot | None:
    """Single fetch. Returns None on any error."""
    headers = {
        "User-Agent": "IchorVixCollector/0.1 (https://github.com/fxeliott/ichor)",
        "Accept": "application/json",
    }
    params = {"symbols": "^VIX"}
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.get(YF_QUOTE_URL, params=params, headers=headers)
            if r.status_code != 200:
                return None
            body = r.json()
    except (httpx.HTTPError, ValueError):
        return None

    results = (body.get("quoteResponse") or {}).get("result") or []
    if not results:
        return None
    q = results[0]
    price = q.get("regularMarketPrice")
    if price is None:
        return None
    return VixSnapshot(
        value=float(price),
        change_abs=(
            float(q["regularMarketChange"]) if q.get("regularMarketChange") is not None else None
        ),
        change_pct=(
            float(q["regularMarketChangePercent"])
            if q.get("regularMarketChangePercent") is not None
            else None
        ),
        market_state=str(q.get("marketState", "UNKNOWN")),
        fetched_at=datetime.now(UTC),
        raw=q,
    )


def crisis_threshold_breached(snap: VixSnapshot, *, threshold: float = 30.0) -> bool:
    """True if VIX absolute level + intraday change qualifies as panic."""
    return snap.value >= threshold or (snap.change_pct is not None and snap.change_pct >= 30.0)
