"""Wikipedia Pageviews — geopolitical/macro public attention proxy.

Why this exists for Ichor :
  - Wikipedia article pageviews are an underused proxy for public
    attention. A spike on "Recession" or "Bank run" articles
    correlates with a regime shift in retail sentiment 24-48h before
    AAII/Reddit catch up.
  - We poll a small watchlist of macro-charged articles daily.

Endpoint (verified 2026-05-05, free no-auth) :
  https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/
    {project}/{access}/{agent}/{article}/{granularity}/{start}/{end}

Source :
  - https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/
"""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

WIKIMEDIA_BASE = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"

# Articles we watch — chosen for their direct mapping to Ichor regime
# quadrants and trader concerns. Add curated, not exhaustive.
WATCHED_ARTICLES: tuple[tuple[str, str], ...] = (
    ("en.wikipedia.org", "Recession"),
    ("en.wikipedia.org", "Bank_run"),
    ("en.wikipedia.org", "Inflation"),
    ("en.wikipedia.org", "Yield_curve"),
    ("en.wikipedia.org", "Federal_Reserve"),
    ("en.wikipedia.org", "European_Central_Bank"),
    ("en.wikipedia.org", "Quantitative_easing"),
    ("en.wikipedia.org", "Stock_market_crash"),
    ("en.wikipedia.org", "Cryptocurrency"),
    ("en.wikipedia.org", "Geopolitics"),
)


@dataclass(frozen=True)
class PageviewObservation:
    project: str
    article: str
    observation_date: date
    views: int
    fetched_at: datetime


def _parse_ts_yyyymmdd(s: Any) -> date | None:
    if not s or len(str(s)) < 8:
        return None
    try:
        return datetime.strptime(str(s)[:8], "%Y%m%d").date()
    except ValueError:
        return None


def parse_pageviews_response(
    project: str, article: str, body: dict[str, Any]
) -> list[PageviewObservation]:
    """Wikimedia returns {items: [{project, article, granularity,
    timestamp, access, agent, views}, ...]}."""
    out: list[PageviewObservation] = []
    items = body.get("items") if isinstance(body, dict) else None
    if not isinstance(items, list):
        return out
    now = datetime.now(UTC)
    for it in items:
        if not isinstance(it, dict):
            continue
        d = _parse_ts_yyyymmdd(it.get("timestamp"))
        v = it.get("views")
        if d is None or v is None:
            continue
        try:
            views = int(v)
        except (TypeError, ValueError):
            continue
        out.append(
            PageviewObservation(
                project=project,
                article=article,
                observation_date=d,
                views=views,
                fetched_at=now,
            )
        )
    return out


async def fetch_article_pageviews(
    project: str,
    article: str,
    *,
    days: int = 30,
    access: str = "all-access",
    agent: str = "all-agents",
    timeout_s: float = 20.0,
) -> list[PageviewObservation]:
    """Pull daily pageviews for one article over the trailing `days`."""
    end = date.today()
    start = end - timedelta(days=days)
    # The endpoint is path-based (not query-based) — encode article carefully.
    article_enc = urllib.parse.quote(article, safe="")
    url = (
        f"{WIKIMEDIA_BASE}/{project}/{access}/{agent}/"
        f"{article_enc}/daily/{start.strftime('%Y%m%d')}/{end.strftime('%Y%m%d')}"
    )
    headers = {
        "User-Agent": "IchorWikipediaPageviewsCollector/0.1 (https://github.com/fxeliott/ichor)",
        "Accept": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            return parse_pageviews_response(project, article, r.json())
    except httpx.HTTPError:
        return []


async def poll_all(
    *,
    articles: tuple[tuple[str, str], ...] = WATCHED_ARTICLES,
    days: int = 30,
) -> list[PageviewObservation]:
    """Fan-out over all watched articles — sequentially to be polite
    to Wikimedia (they recommend ≤ 200 req/s ; sequential is safe)."""
    out: list[PageviewObservation] = []
    for project, article in articles:
        rows = await fetch_article_pageviews(project, article, days=days)
        out.extend(rows)
    return out


def supported_articles() -> tuple[tuple[str, str], ...]:
    return WATCHED_ARTICLES
