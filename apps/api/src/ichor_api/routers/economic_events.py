"""GET /v1/economic-events — ForexFactory persisted calendar events.

Reads from the `economic_events` table populated by the `forex_factory`
collector (see migration 0019). This endpoint is the parser-fed
counterpart to /v1/calendar/upcoming (which projects FRED release dates).
The two are complementary: FRED gives canonical scheduled US releases,
ForexFactory gives the broader cross-currency calendar with consensus +
previous values.

Filters :
  - `currency` : ISO code (USD, EUR, GBP, JPY, ...). Defaults to all.
  - `impact`   : low / medium / high / holiday. Defaults to all.
  - `since_minutes` and `horizon_minutes` define the [now-since, now+horizon]
    window. Defaults to (60 min back, 7 days forward) — typical
    "what's happening near me" pre-session view.
  - `limit`    : 1..200 rows.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import EconomicEvent

router = APIRouter(prefix="/v1/economic-events", tags=["economic-events"])

ImpactLevel = Literal["low", "medium", "high", "holiday"]


class EconomicEventOut(BaseModel):
    id: str
    currency: str
    scheduled_at: datetime | None
    is_all_day: bool
    title: str
    impact: ImpactLevel
    forecast: str | None
    previous: str | None
    url: str | None
    source: str
    fetched_at: datetime


class EconomicEventListOut(BaseModel):
    generated_at: datetime
    window_back_minutes: int
    window_forward_minutes: int
    n_events: int = Field(ge=0)
    events: list[EconomicEventOut]


@router.get("", response_model=EconomicEventListOut)
async def list_events(
    session: Annotated[AsyncSession, Depends(get_session)],
    currency: Annotated[str | None, Query(max_length=8, pattern=r"^[A-Z]{3}$")] = None,
    impact: Annotated[ImpactLevel | None, Query()] = None,
    since_minutes: Annotated[int, Query(ge=0, le=10080)] = 60,
    horizon_minutes: Annotated[int, Query(ge=1, le=20160)] = 60 * 24 * 7,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> EconomicEventListOut:
    """Newest-first list of ForexFactory events in the [-since, +horizon] window."""
    now = datetime.now(UTC)
    lo = now - timedelta(minutes=since_minutes)
    hi = now + timedelta(minutes=horizon_minutes)

    stmt = select(EconomicEvent).where(
        EconomicEvent.scheduled_at.is_not(None),
        EconomicEvent.scheduled_at >= lo,
        EconomicEvent.scheduled_at <= hi,
    )
    if currency:
        stmt = stmt.where(EconomicEvent.currency == currency.upper())
    if impact:
        stmt = stmt.where(EconomicEvent.impact == impact)

    rows = (
        (await session.execute(stmt.order_by(desc(EconomicEvent.scheduled_at)).limit(limit)))
        .scalars()
        .all()
    )

    return EconomicEventListOut(
        generated_at=now,
        window_back_minutes=since_minutes,
        window_forward_minutes=horizon_minutes,
        n_events=len(rows),
        events=[
            EconomicEventOut(
                id=str(r.id),
                currency=r.currency,
                scheduled_at=r.scheduled_at,
                is_all_day=r.is_all_day,
                title=r.title,
                impact=r.impact,  # type: ignore[arg-type]
                forecast=r.forecast,
                previous=r.previous,
                url=r.url,
                source=r.source,
                fetched_at=r.fetched_at,
            )
            for r in rows
        ],
    )
