"""Polygon / Massive News API collector — ticker-linked news flow.

The Currencies $49 plan grants access to `/v2/reference/news` which is a
much richer stream than the RSS pollers we already run :

  - structured publisher metadata (name, logo, favicon)
  - clean published_utc timestamp
  - **ticker linkage** : each story tagged with the affected tickers
    (e.g. NVDA/AAPL/SPX for a tech earnings story) — RSS doesn't do this
  - de-duplicated id (idempotent ingest)
  - sentiment / insights blobs for some stories (via "insights" key)

The collector is read-only. Persistence into `news_items` is handled by
the same path RSS uses, with `source_kind = 'news'` and
`source = 'polygon_news'`. Ticker linkage is stored in the `tickers`
field of the news_items JSONB context (extended below if not present).

Massive doesn't publicly document news rate limits but the Currencies
plan is "unlimited" for Currencies endpoints. News is in /reference/
which historically allowed ~100 req/min on paid plans. We poll every
5 minutes (12/h = 288/day) — well below any conceivable cap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx

POLYGON_BASE_URL = "https://api.polygon.io"


@dataclass(frozen=True)
class PolygonNewsItem:
    """One news article parsed from /v2/reference/news."""

    id: str
    title: str
    url: str
    published_at: datetime
    publisher_name: str
    publisher_url: str | None
    description: str | None
    tickers: tuple[str, ...]
    keywords: tuple[str, ...]
    image_url: str | None
    insights: tuple[dict[str, Any], ...] = field(default=())


def _parse_iso8601_z(s: str) -> datetime:
    """Massive emits 'YYYY-MM-DDTHH:MM:SSZ' — Python 3.11+ fromisoformat
    handles the 'Z' suffix natively but we keep the manual fallback for
    older runtimes still seen in some collector boxes."""
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def parse_news_response(body: dict[str, Any]) -> list[PolygonNewsItem]:
    """Convert a /v2/reference/news JSON body into news items.

    Drops rows missing id / title / article_url / published_utc. All
    other fields gracefully degrade to None / empty tuple.
    """
    results = body.get("results") or []
    out: list[PolygonNewsItem] = []
    for r in results:
        item_id = r.get("id")
        title = r.get("title")
        url = r.get("article_url")
        published = r.get("published_utc")
        if not (item_id and title and url and published):
            continue
        try:
            published_dt = _parse_iso8601_z(published)
        except (ValueError, TypeError):
            continue
        publisher = r.get("publisher") or {}
        tickers_raw = r.get("tickers") or []
        keywords_raw = r.get("keywords") or []
        insights_raw = r.get("insights") or []
        # Defensive : Massive sometimes returns scalars instead of arrays
        if not isinstance(tickers_raw, list):
            tickers_raw = []
        if not isinstance(keywords_raw, list):
            keywords_raw = []
        if not isinstance(insights_raw, list):
            insights_raw = []
        out.append(
            PolygonNewsItem(
                id=str(item_id),
                title=str(title).strip(),
                url=str(url),
                published_at=published_dt,
                publisher_name=str(publisher.get("name") or "unknown"),
                publisher_url=publisher.get("homepage_url"),
                description=(r.get("description") or None),
                tickers=tuple(str(t) for t in tickers_raw if t),
                keywords=tuple(str(k) for k in keywords_raw if k),
                image_url=(r.get("image_url") or None),
                insights=tuple(insights_raw),
            )
        )
    return out


async def fetch_news(
    *,
    api_key: str,
    limit: int = 100,
    ticker: str | None = None,
    published_after: datetime | None = None,
    timeout_s: float = 15.0,
) -> list[PolygonNewsItem]:
    """Fetch the latest /v2/reference/news page.

    Single-page fetch (Massive supports cursor pagination via `next_url`
    if we need it) — Phase 1 goal is "freshest 100 items every 5 min",
    which is more than enough headroom.
    """
    params: dict[str, Any] = {
        "limit": min(max(1, limit), 1000),
        "order": "desc",
        "sort": "published_utc",
        "apiKey": api_key,
    }
    if ticker:
        params["ticker"] = ticker
    if published_after:
        params["published_utc.gte"] = published_after.strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    url = f"{POLYGON_BASE_URL}/v2/reference/news"
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return parse_news_response(resp.json())


def relevant_to_ichor_universe(item: PolygonNewsItem) -> bool:
    """Filter : keep items whose tickers intersect the Ichor universe.

    Ichor cares about the 8 Phase-1 assets (FX + XAU + indices), but
    Massive tags news mostly with US equities. We accept either :
      - a known FX/index ticker explicitly,
      - mega-cap 7 names (AAPL/MSFT/GOOGL/AMZN/META/NVDA/TSLA — drive
        NAS100/SPX500 narrative),
      - SPDR Gold ETF (GLD) as XAU proxy,
      - DXY (US Dollar Index) directly.

    Items with no ticker are kept (macro / geopolitical news without
    explicit ticker tags are still useful for narrative tracker).
    """
    if not item.tickers:
        return True  # macro / geopolitical without ticker = keep
    universe = {
        # mega-cap 7 (AI capex narrative for NAS100 framework)
        "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "NVDA", "TSLA",
        # XAU proxies
        "GLD", "IAU", "SPDR", "GDX",
        # broad indices
        "SPY", "QQQ", "DIA", "IWM",
        # USD index
        "DXY", "UUP",
        # FX direct (rare but happens)
        "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "XAUUSD",
        "C:EURUSD", "C:GBPUSD", "C:USDJPY", "C:AUDUSD", "C:USDCAD", "C:XAUUSD",
    }
    return any(t.upper() in universe for t in item.tickers)
