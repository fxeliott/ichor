"""GET /v1/calendar/upcoming — economic calendar feed."""

from __future__ import annotations

from datetime import date as DateType
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..services.economic_calendar import (
    assess_calendar,
    filter_for_asset,
)

router = APIRouter(prefix="/v1/calendar", tags=["calendar"])


class CalendarEventOut(BaseModel):
    when: DateType
    when_time_utc: str | None
    region: str
    label: str
    impact: Literal["high", "medium", "low"]
    affected_assets: list[str]
    note: str
    source: str | None


class CalendarOut(BaseModel):
    generated_at: datetime
    horizon_days: int
    events: list[CalendarEventOut]


@router.get("/upcoming", response_model=CalendarOut)
async def get_upcoming(
    session: Annotated[AsyncSession, Depends(get_session)],
    horizon_days: Annotated[int, Query(ge=1, le=60)] = 14,
    asset: Annotated[str | None, Query()] = None,
) -> CalendarOut:
    report = await assess_calendar(session, horizon_days=horizon_days)
    events = filter_for_asset(report, asset.upper().replace("-", "_")) if asset else report.events
    return CalendarOut(
        generated_at=report.generated_at,
        horizon_days=report.horizon_days,
        events=[
            CalendarEventOut(
                when=e.when,
                when_time_utc=e.when_time_utc,
                region=e.region,
                label=e.label,
                impact=e.impact,
                affected_assets=e.affected_assets,
                note=e.note,
                source=e.source,
            )
            for e in events
        ],
    )
