"""GET /v1/calendar/upcoming — economic calendar feed."""

from __future__ import annotations

from datetime import date as DateType
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..services.economic_calendar import (
    assess_calendar,
    filter_for_asset,
)
from ..services.market_session import compute_session_status

router = APIRouter(prefix="/v1/calendar", tags=["calendar"])


class SessionStatusOut(BaseModel):
    now_paris: str
    weekday: str
    state: Literal[
        "weekend",
        "us_holiday",
        "pre_londres",
        "london_active",
        "pre_ny",
        "ny_active",
        "off_hours",
    ]
    market_closed_fx: bool
    market_closed_us_equity: bool
    holiday_name: str | None
    next_open_label: str
    next_open_paris: str
    minutes_until_next_open: int


@router.get("/session-status", response_model=SessionStatusOut)
async def get_session_status() -> SessionStatusOut:
    """ADR-099 Tier 1.3 — DST-correct (zoneinfo) market state + US
    holiday awareness. Pure compute, no DB. Replaces the crude DST-naive
    UTC heuristic that was client-side in SessionStatus.tsx."""
    return SessionStatusOut(**compute_session_status().to_dict())


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
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    horizon_days: Annotated[int, Query(ge=1, le=60)] = 14,
    asset: Annotated[str | None, Query()] = None,
    since_minutes: Annotated[int, Query(ge=0, le=1440)] = 0,
) -> CalendarOut:
    """r140 — `since_minutes` (default 0, max 24h) extends the window
    backward so the `<FreshDataBanner>` polling endpoint can detect
    catalysts whose `scheduled_at` has just elapsed. Backward-compat :
    no `since_minutes` parameter keeps the r68 forward-only behaviour
    (current `<EconomicCalendarPanel>` consumers unaffected).

    HONEST SCOPE : recent-window events indicate "scheduled time elapsed",
    NOT "actual value published". The ForexFactory XML feed does not
    publish actuals (lesson #11 calibrated honesty — frontend banner
    must stamp "actuals à vérifier à la source").
    """
    # r140 code-reviewer S1 fix : Cache-Control: no-store when polling-
    # mode (since_minutes>0). Any browser/CDN cache defeats freshness-
    # detection. Static forward-only queries stay cacheable (no header set).
    if since_minutes > 0:
        response.headers["Cache-Control"] = "no-store"
    report = await assess_calendar(session, horizon_days=horizon_days, since_minutes=since_minutes)
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
