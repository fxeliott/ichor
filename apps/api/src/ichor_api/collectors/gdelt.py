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
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

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
# S03 (2026-06-11) — extended with per-asset slices (PER_ASSET_QUERIES below):
# the 2026-06-09 S04 session proved per-asset geopolitics differentiation is
# DATA-GATED on per-asset GDELT density (24h window yields 0-1 affinity
# matches per asset → systematic global fallback). The fix lives HERE, at
# the collector: asset-targeted queries whose labels AND article titles
# carry the asset's NEWS_KEYWORDS vocabulary, so the downstream
# `filter_rows_by_asset_affinity` (title + query_label + domain + url blob)
# crosses its min_required threshold on real density, not on a loosened gate.
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
        "(Iran OR Israel OR Russia OR Ukraine OR China OR Taiwan) (oil OR gold OR sanctions OR strike)",
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

# S03 per-asset slices — close the asset-coverage holes the global bucket
# left open (NO query existed for CAD, AUD, UK-economy-beyond-BoE,
# eurozone-beyond-ECB, or US equity indices). Label naming contract:
# each label embeds its asset's `NEWS_KEYWORDS` vocabulary (lowercase
# substring match, see `services/asset_news_affinity.matches_asset`) so the
# label itself contributes to downstream affinity matching — pinned by
# `test_per_asset_query_labels_match_their_asset`. Query syntax constraints
# (verified against the GDELT DOC 2.0 docs 2026-06-11): exact phrases in
# double quotes, OR groups in parentheses (non-nestable), `sourcelang:`
# filter, timespan >= 15min.
PER_ASSET_QUERIES: tuple[GdeltQuery, ...] = (
    GdeltQuery(
        "eurusd_eurozone",
        '(eurozone OR "euro area" OR Bundesbank OR "German economy") sourcelang:english',
        timespan="2h",
    ),
    GdeltQuery(
        "gbpusd_uk_economy",
        '("UK economy" OR "pound sterling" OR "British economy" OR gilts) sourcelang:english',
        timespan="2h",
    ),
    GdeltQuery(
        "usdcad_boc_canada",
        '("Bank of Canada" OR "Canadian dollar" OR "Canada economy" OR Macklem)',
        timespan="2h",
    ),
    GdeltQuery(
        "audusd_rba_china",
        '("Reserve Bank of Australia" OR "Australian dollar" OR "China stimulus" OR "iron ore")',
        timespan="2h",
    ),
    GdeltQuery(
        "spx500_spx_us_equities",
        '("S&P 500" OR "Wall Street" OR "US stocks") sourcelang:english',
        timespan="1h",
    ),
    GdeltQuery(
        "nas100_nasdaq_tech",
        '(Nasdaq OR Nvidia OR "tech stocks" OR semiconductor) sourcelang:english',
        timespan="1h",
    ),
)

# What `poll_all` actually polls each cycle: 8 global + 6 per-asset = 14
# queries / 30 min ≈ 672 req/day — far under GDELT's observed tolerance,
# and the fetch path already backs off exponentially on 429 (1s/3s/9s).
ALL_QUERIES: tuple[GdeltQuery, ...] = DEFAULT_QUERIES + PER_ASSET_QUERIES


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
        return datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except ValueError:
        return datetime.now(UTC)


def _parse_response(query_label: str, payload: dict) -> list[GdeltArticle]:
    fetched = datetime.now(UTC)
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

    Retries with exponential backoff on 429 / 5xx — 5 s / 15 s / 45 s:
    the original 1/3/9 ladder retried INSIDE the same rate-limit window
    and burned its retries (429s on 6/14 queries witnessed prod
    2026-06-11 21:33 evening peak).
    """
    params = {
        "query": q.query,
        "mode": "ArtList",
        "format": "json",
        "timespan": q.timespan,
        "maxrecords": str(q.max_records),
    }
    backoff = 5.0
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
    queries: Iterable[GdeltQuery] = ALL_QUERIES,
    *,
    concurrency: int = 1,
    politeness_delay_s: float = 5.0,
) -> list[GdeltArticle]:
    """Run the queries strictly sequentially. Dedupe by URL.

    S03 hardening — concurrency 1 at ~1 req/5 s (the community-observed
    polite rate): the first cut (concurrency 2 + 2 s delay) still drew
    429s on 6/14 queries at the evening-peak run (witnessed prod
    2026-06-11 21:33) and burned its retries. 14 queries ≈ 90-120 s per
    cycle — trivial against the 30-min timer.
    """
    sem = asyncio.Semaphore(concurrency)

    async def _one(q: GdeltQuery, client: httpx.AsyncClient) -> list[GdeltArticle]:
        async with sem:
            out = await fetch_query(q, client=client)
            if politeness_delay_s > 0:
                await asyncio.sleep(politeness_delay_s)
            return out

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*(_one(q, client) for q in queries))

    # Dedup on (url, query_label), NOT url alone: the same article can legitimately
    # surface under a global query AND a per-asset query. URL-only dedup let the
    # first-issued (global) query win the race and silently dropped the per-asset
    # label → starved the PER_ASSET_QUERIES density that feeds S04 geo. The
    # (url, query_label) key matches the persist uniqueness (uq_gdelt_url_query_seen)
    # so no extra DB churn. A truly identical (url, label) repeat is still deduped.
    seen: set[tuple[str, str]] = set()
    flat: list[GdeltArticle] = []
    for batch in results:
        for art in batch:
            key = (art.url, art.query_label)
            if not art.url or key in seen:
                continue
            seen.add(key)
            flat.append(art)

    flat.sort(key=lambda a: a.seendate, reverse=True)
    return flat
