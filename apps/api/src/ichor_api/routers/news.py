"""GET /v1/news — list recent news items collected from public RSS feeds.

r138 — Asset-conditioned feed (ADR-099 §Impl, lesson #32 lit up the
existing-but-broken asset filter that lived only inside the 4-pass
LLM data-pool reader). When `?asset=` is set the endpoint applies the
SAME ticker-keyword affinity logic used by `services/data_pool.py`
(re-homed to `services/asset_news_affinity.py`), with the SAME scarce-
fallback discipline (below `min_required` matches → fall back to the
global feed, surface `applied=False` honestly).

Backward-compat : without `?asset=`, the response shape and contents
are unchanged versus r137 — the legacy bare-list contract is wrapped in
an envelope where `filter=None` and `items` is the same list a r137
caller would have received. Frontend consumers must unwrap `.items`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import NewsItem
from ..services.asset_news_affinity import (
    ASSET_QUERY_REGEX as _ASSET_REGEX,
)
from ..services.asset_news_affinity import (
    NEWS_KEYWORDS,
    filter_rows_by_asset_affinity,
)

router = APIRouter(prefix="/v1/news", tags=["news"])

# r138 — must be high enough that filter is meaningful, low enough that
# common assets in a thin news window still surface. Aligns with
# data_pool._section_news minimum (3).
_MIN_ASSET_MATCHES = 3
# r138 — when filtering, pull a wider candidate pool than the requested
# limit so the keyword filter has options before being capped. 4× hits
# a sweet spot empirically (50 candidates × 4 = up to 200, capped at
# 500 = upstream `limit` ceiling).
_FILTER_FETCH_MULTIPLIER = 4
_FILTER_MAX_FETCH = 500
# r138 — `_ASSET_REGEX` now re-imported from
# `services/asset_news_affinity.ASSET_QUERY_REGEX` (code-reviewer N3 SSOT).


class NewsItemOut(BaseModel):
    id: str
    fetched_at: datetime
    source: str
    source_kind: str
    title: str
    summary: str | None
    url: str
    published_at: datetime
    tone_label: str | None
    tone_score: float | None

    model_config = {"from_attributes": True}


class NewsFilterMeta(BaseModel):
    """r138 — disclosed asset-filter status (lesson #11 calibrated honesty).

    `applied=True`  → the response was narrowed to asset-matching items.
    `applied=False` AND `matched < min_required` → scarce fallback fired,
        the response is the GLOBAL feed (frontend should surface this).
    `applied=False` AND `matched=0` AND asset unknown → asset not in
        the keyword map ; global feed, no filter attempted.
    """

    asset: str
    matched: int
    applied: bool
    min_required: int = _MIN_ASSET_MATCHES
    known_asset: bool = True


class NewsListEnvelope(BaseModel):
    """r138 — envelope wrapping the historical bare-list response so
    the asset-filter metadata can be surfaced without polluting per-item
    payloads. When `?asset=` is omitted, `filter` is `None` and `items`
    matches the pre-r138 shape."""

    items: list[NewsItemOut]
    filter: NewsFilterMeta | None = None


@router.get("", response_model=NewsListEnvelope)
async def list_news(
    session: Annotated[AsyncSession, Depends(get_session)],
    source_kind: str | None = Query(
        None, pattern=r"^(news|central_bank|regulator|social|academic)$"
    ),
    source: str | None = Query(None, max_length=64),
    tone: str | None = Query(None, pattern=r"^(positive|neutral|negative)$"),
    since_minutes: int = Query(1440, ge=1, le=10080),  # 1 min .. 7 days
    limit: int = Query(50, ge=1, le=500),
    asset: str | None = Query(None, pattern=_ASSET_REGEX),
) -> NewsListEnvelope:
    """Newest-first listing, default last 24h. Filterable by source kind /
    source / tone / asset. `since_minutes` caps the lookback (defaults
    1 day).

    r138 — `asset` (optional) narrows the feed to items whose title OR
    URL matches the asset's keyword tuple (cf
    `services/asset_news_affinity.NEWS_KEYWORDS`). If fewer than
    `_MIN_ASSET_MATCHES` items match, falls back to the unfiltered
    global feed and surfaces `filter.applied=False` for honest UI
    disclosure (lesson #11).
    """
    cutoff = datetime.now(UTC) - timedelta(minutes=since_minutes)
    stmt = (
        select(NewsItem)
        .where(NewsItem.published_at >= cutoff)
        .order_by(desc(NewsItem.published_at))
    )
    if source_kind:
        stmt = stmt.where(NewsItem.source_kind == source_kind)
    if source:
        stmt = stmt.where(NewsItem.source == source)
    if tone:
        stmt = stmt.where(NewsItem.tone_label == tone)
    # r138 — when filtering by asset we need a wider candidate pool so
    # the post-DB keyword filter has enough options before being capped
    # at `limit`. Without asset, behaviour is identical to r137.
    fetch_cap = limit
    if asset:
        fetch_cap = min(
            _FILTER_MAX_FETCH, max(limit * _FILTER_FETCH_MULTIPLIER, _MIN_ASSET_MATCHES * 4)
        )
    stmt = stmt.limit(fetch_cap)
    rows = list((await session.execute(stmt)).scalars().all())

    filter_meta: NewsFilterMeta | None = None
    if asset:
        asset_uc = asset.upper()
        known = asset_uc in NEWS_KEYWORDS
        filtered_rows, matched, applied = filter_rows_by_asset_affinity(
            rows,
            asset_uc,
            # r139 — pass summary as a 3rd field. Empirical Hetzner survey
            # 2026-05-22 found ~70% of macro-vocabulary content (FOMC/PMI/CPI/
            # real-yields/Treasury/etc.) lives in news_items.summary, NOT
            # title/url. Including summary in the matcher blob makes the
            # r139 keyword precision pass functionally non-zero for SPX/XAU.
            key=lambda r: (r.title or "", r.url or "", r.summary or ""),
            min_required=_MIN_ASSET_MATCHES,
        )
        rows = filtered_rows[:limit]
        filter_meta = NewsFilterMeta(
            asset=asset_uc,
            matched=matched,
            applied=applied,
            min_required=_MIN_ASSET_MATCHES,
            known_asset=known,
        )
    else:
        rows = rows[:limit]

    items = [
        NewsItemOut(
            id=str(r.id),
            fetched_at=r.fetched_at,
            source=r.source,
            source_kind=r.source_kind,
            title=r.title,
            summary=r.summary,
            url=r.url,
            published_at=r.published_at,
            tone_label=r.tone_label,
            tone_score=r.tone_score,
        )
        for r in rows
    ]
    return NewsListEnvelope(items=items, filter=filter_meta)
