"""GDELT 2.0 collector — translingual news + entity events.

GDELT 2.0 is the free-tier substitute for NewsAPI ($449/mo). It indexes
news in 65 languages, updates every 15 min, and exposes :

  1. **GDELT DOC 2.0 API** (this collector) — text article search by keyword,
     theme, location, tone. 3-month rolling window. JSON over HTTPS.
     `https://api.gdeltproject.org/api/v2/doc/doc?...`

  2. **GDELT Events / GKG / Mentions** — flat CSV dumps every 15 min on a
     public bucket. Larger volume but cheaper to query in batch.

For Phase 1 we use DOC 2.0 because it's keyword-targeted (we want news
about EUR, ECB, Fed, oil, etc.) and translingual (catches Reuters DE,
Handelsblatt, Le Figaro, Bloomberg in addition to English Reuters).

Schema reference :
  https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Sequence

import httpx
import structlog

log = structlog.get_logger(__name__)

GDELT_DOC_BASE = "https://api.gdeltproject.org/api/v2/doc/doc"


@dataclass(frozen=True)
class GdeltQuery:
    """One search slice for GDELT — corresponds to one keyword / theme bucket."""

    label: str
    """Internal identifier — e.g. 'fed', 'ecb', 'eurusd', 'china_growth'."""

    query: str
    """GDELT DOC query string (supports `themes:`, `sourcecountry:`, etc.)."""

    timespan: str = "1h"
    """How far back to search. Format : `<n><unit>` where unit ∈ {min, h, d, w}."""

    max_records: int = 25
    """Cap to avoid budget blow-up. GDELT max is 250."""


# Phase 1 keyword bucket — the topics we monitor for our 8 assets.
DEFAULT_QUERIES: tuple[GdeltQuery, ...] = (
    GdeltQuery(
        "fed",
        '("Federal Reserve" OR FOMC OR "Jerome Powell" OR Fed) sourcecountry:US',
        timespan="1h",
    ),
    GdeltQuery(
        "ecb",
        '("European Central Bank" OR ECB OR Lagarde) sourcecountry:US,UK,DE,FR',
        timespan="1h",
    ),
    GdeltQuery(
        "boe",
        '("Bank of England" OR BoE OR "Bailey" OR "Andrew Bailey") sourcecountry:UK',
        timespan="1h",
    ),
    GdeltQuery(
        "boj",
        '("Bank of Japan" OR BoJ OR "Ueda") sourcecountry:JP,US',
        timespan="2h",
    ),
    GdeltQuery(
        "geopolitics",
        '(Iran OR Israel OR Russia OR Ukraine OR China OR Taiwan) (oil OR gold OR sanctions OR strike)',
        timespan="2h",
    ),
    GdeltQuery(
        "us_data",
        '("nonfarm payrolls" OR NFP OR CPI OR "consumer price" OR "PCE inflation" OR "retail sales")',
        timespan="1h",
    ),
    GdeltQuery(
        "oil",
        '(OPEC OR crude OR "oil prices" OR WTI OR Brent) -recipe',
        timespan="2h",
    ),
    GdeltQuery(
        "gold",
        '(gold OR XAUUSD OR "central bank gold" OR PBoC) -jewelry -wedding',
        timespan="2h",
    ),
)


@dataclass
class GdeltArticle:
    """One article returned by GDELT DOC 2.0."""

    fetched_at: datetime
    query_label: str
    url: str
    title: str
    seendate: datetime
    """When GDELT first indexed this article."""

    domain: str
    language: str
    sourcecountry: str
    tone: float
    """GDELT-computed tone, range roughly −10 to +10. Negative = bearish."""

    image_url: str | None = None


def _parse_seendate(s: str) -> datetime:
    """GDELT seendate format : `20260503T093000Z`."""
    try:
        return datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


def _parse_response(query_label: str, payload: dict) -> list[GdeltArticle]:
    fetched = datetime.now(timezone.utc)
    out: list[GdeltArticle] = []
    for art in payload.get("articles", []):
        try:
            out.append(
                GdeltArticle(
                    fetched_at=fetched,
                    query_label=query_label,
                    url=art.get("url", ""),
                    title=art.get("title", "")[:512],
                    seendate=_parse_seendate(art.get("seendate", "")),
                    domain=art.get("domain", ""),
                    language=art.get("language", "")[:32],
                    sourcecountry=art.get("sourcecountry", "")[:32],
                    tone=float(art.get("tone", 0.0)),
                    image_url=art.get("socialimage") or None,
                )
            )
        except (TypeError, ValueError, KeyError) as e:
            log.warning("gdelt.parse_row_failed", query=query_label, error=str(e))
            continue
    return out


async def fetch_query(
    q: GdeltQuery,
    *,
    client: httpx.AsyncClient,
    timeout: float = 20.0,
    max_retries: int = 3,
) -> list[GdeltArticle]:
    """One bucket → JSON → parsed list. Returns [] on any error.

    Retries with exponential backoff on 429 / 5xx. GDELT occasionally
    rate-limits (no documented limit, but ~1 req/s observed) so we
    sleep 1s / 3s / 9s between attempts.
    """
    params = {
        "query": q.query,
        "mode": "ArtList",
        "format": "json",
        "timespan": q.timespan,
        "maxrecords": str(q.max_records),
    }
    backoff = 1.0
    for attempt in range(max_retries + 1):
        try:
            r = await client.get(
                GDELT_DOC_BASE,
                params=params,
                timeout=timeout,
                headers={"User-Agent": "IchorGdeltCollector/0.1"},
            )
            if r.status_code in (429, 502, 503, 504) and attempt < max_retries:
                await asyncio.sleep(backoff)
                backoff *= 3
                continue
            r.raise_for_status()
            if "application/json" not in r.headers.get("content-type", ""):
                log.warning(
                    "gdelt.non_json_response",
                    query=q.label,
                    ct=r.headers.get("content-type"),
                )
                return []
            payload = r.json()
            return _parse_response(q.label, payload)
        except httpx.HTTPError as e:
            if attempt < max_retries:
                await asyncio.sleep(backoff)
                backoff *= 3
                continue
            log.warning("gdelt.fetch_failed", query=q.label, error=str(e))
            return []
    return []


async def poll_all(
    queries: Iterable[GdeltQuery] = DEFAULT_QUERIES,
    *,
    concurrency: int = 4,
) -> list[GdeltArticle]:
    """Fan out the queries in parallel. Dedupe by URL."""
    sem = asyncio.Semaphore(concurrency)

    async def _one(q: GdeltQuery, client: httpx.AsyncClient) -> list[GdeltArticle]:
        async with sem:
            return await fetch_query(q, client=client)

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*(_one(q, client) for q in queries))

    seen_urls: set[str] = set()
    flat: list[GdeltArticle] = []
    for batch in results:
        for art in batch:
            if not art.url or art.url in seen_urls:
                continue
            seen_urls.add(art.url)
            flat.append(art)

    flat.sort(key=lambda a: a.seendate, reverse=True)
    return flat
