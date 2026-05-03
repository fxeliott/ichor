"""GET /v1/news — list recent news items collected from public RSS feeds."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import NewsItem

router = APIRouter(prefix="/v1/news", tags=["news"])


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


@router.get("", response_model=list[NewsItemOut])
async def list_news(
    session: Annotated[AsyncSession, Depends(get_session)],
    source_kind: str | None = Query(
        None, regex=r"^(news|central_bank|regulator|social|academic)$"
    ),
    source: str | None = Query(None, max_length=64),
    tone: str | None = Query(None, regex=r"^(positive|neutral|negative)$"),
    since_minutes: int = Query(1440, ge=1, le=10080),  # 1 min .. 7 days
    limit: int = Query(50, ge=1, le=500),
) -> list[NewsItemOut]:
    """Newest-first listing, default last 24h. Filterable by source kind /
    source / tone. `since_minutes` caps the lookback (defaults 1 day)."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
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
    stmt = stmt.limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return [
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
