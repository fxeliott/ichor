"""GET /v1/calendar/upcoming — economic calendar feed."""

from __future__ import annotations

from datetime import UTC, datetime
from datetime import date as DateType
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..services.economic_calendar import (
    assess_calendar,
    filter_for_asset,
)
from ..services.economic_event_surprise import SurpriseState
from ..services.market_session import compute_session_status
from ..services.recent_actuals import fetch_recent_actuals

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


# r145 (ADR-099 §Impl) -- recent-actuals surface for Mission centrale axis-5.
# Surfaces past N-day events that have a published `actual` (lit by r144
# FRED ALFRED reconciler) classified via r141 `classify_surprise()`.
#
# code-reviewer r145 SHOULD-FIX #2 : reuse the r141 service-layer `SurpriseState`
# Literal verbatim instead of duplicating it here -- the two could silently
# drift if either side adds/renames a state. Single source of truth lives at
# `services/economic_event_surprise.py:50` ; CI guard in
# `tests/test_invariants_ichor.py` (r145 extension) pins them in lockstep.
SurpriseStateLiteral = SurpriseState


class SurpriseClassificationOut(BaseModel):
    """r141 SurpriseClassification projected to wire shape.

    `state` is the 5-state geometric verdict. `magnitude_pct` is the signed
    deviation as % of |consensus| -- populated whenever both `actual` and
    `consensus` parse, INDEPENDENT of state (per r141 design : magnitude is
    useful even when state is `unavailable` because the range envelope is
    missing). `parse_failures` is sorted list (frozenset->list for JSON).

    ADR-017 : all fields are descriptive geometric scalars, NEVER directional.
    Per-asset transmission left to verdict/confluence layers.
    """

    state: SurpriseStateLiteral
    actual_value: float | None
    consensus_value: float | None
    forecast_min_value: float | None
    forecast_max_value: float | None
    magnitude_pct: float | None
    range_breach: float | None
    parse_failures: list[str]


class RecentActualOut(BaseModel):
    """Single past event row with classifier projection.

    Carries BOTH raw text (display-ready) AND classifier verdict so the
    frontend can render raw values + magnitude_pct token even when state
    is `unavailable` (no range data live yet, r146+).
    """

    event_id: str
    currency: str
    scheduled_at_utc: str
    title: str
    impact: Literal["high", "medium", "low"]
    actual: str
    forecast: str | None
    forecast_min: str | None
    forecast_max: str | None
    previous: str | None
    url: str | None
    classification: SurpriseClassificationOut


class RecentActualsOut(BaseModel):
    generated_at: datetime
    lookback_days: int
    currency: str | None
    rows: list[RecentActualOut]


@router.get("/recent-actuals", response_model=RecentActualsOut)
async def get_recent_actuals(
    session: Annotated[AsyncSession, Depends(get_session)],
    lookback_days: Annotated[int, Query(ge=1, le=90)] = 30,
    currency: Annotated[str | None, Query(min_length=2, max_length=8)] = "USD",
    limit: Annotated[int, Query(ge=1, le=200)] = 25,
) -> RecentActualsOut:
    """r145 -- past N-day economic events with published `actual` +
    classifier verdict.

    HONEST SCOPE today (r145) : only USD events have `actual` populated
    (r144 FRED ALFRED reconciler is US-only). `state=unavailable` for all
    rows because the analyst range envelope provider is not yet wired
    (r141 `forecast_min`/`forecast_max` columns are NULL across the board).
    `magnitude_pct` IS populated (computed from FF `forecast` consensus
    point), preserving useful "how far from consensus" info. When the
    range provider lands r146+, state badges auto-light up.

    ADR-017 boundary : descriptive geometric labels + scalars only. NEVER
    directional. Per-asset transmission lives in verdict/confluence layers.

    Args :
        lookback_days  : window depth (default 30 to match r144 cadence).
        currency       : 3-letter ISO filter (default "USD"). Pydantic rejects
                         empty string with 422 (`min_length=2`). To skip the
                         filter and get all currencies, simply omit the param
                         (which defaults to "USD"); a future r146+ revision
                         can add a sentinel like "ALL" if needed.
        limit          : cap rows returned (default 25, max 200).

    No Cache-Control header set : the dataset changes on cron fire (r144
    timer 4x/day), the endpoint is cheap to recompute (small N, pure
    classifier) so no explicit caching today. Clients may layer their own
    cache if needed.
    """
    now = datetime.now(UTC)
    # The Query validator enforces `min_length=2` so a None here means the
    # caller explicitly omitted the param. Empty string is already 422'd
    # upstream (code-reviewer r145 SHOULD-FIX #7 : docstring corrected to
    # match the actual contract rather than the inverted promise).
    currency_filter = currency
    rows = await fetch_recent_actuals(
        session,
        lookback_days=lookback_days,
        currency=currency_filter,
        limit=limit,
        now=now,
    )
    return RecentActualsOut(
        generated_at=now,
        lookback_days=lookback_days,
        currency=currency_filter,
        rows=[
            RecentActualOut(
                event_id=r.event_id,
                currency=r.currency,
                scheduled_at_utc=r.scheduled_at.isoformat(),
                title=r.title,
                # code-reviewer r145 SHOULD-FIX #1 : prior version downcast
                # any unexpected ORM impact to "low" via silent fallback,
                # violating doctrine #11 (calibrated honesty -- fabricating
                # data we don't have). The Pydantic Literal now fail-fasts
                # on bad data ; ORM contract (forex_factory.py collector +
                # economic_calendar invariants) emits only {high,medium,low}.
                # If a future provider emits something else, a 500 here is
                # honest -- alerts ops rather than silently misclassifying.
                impact=r.impact,  # type: ignore[arg-type]
                actual=r.actual,
                forecast=r.forecast,
                forecast_min=r.forecast_min,
                forecast_max=r.forecast_max,
                previous=r.previous,
                url=r.url,
                classification=SurpriseClassificationOut(
                    state=r.classification.state,
                    actual_value=r.classification.actual,
                    consensus_value=r.classification.consensus,
                    forecast_min_value=r.classification.forecast_min,
                    forecast_max_value=r.classification.forecast_max,
                    magnitude_pct=r.classification.magnitude_pct,
                    range_breach=r.classification.range_breach,
                    parse_failures=sorted(r.classification.parse_failures),
                ),
            )
            for r in rows
        ],
    )
