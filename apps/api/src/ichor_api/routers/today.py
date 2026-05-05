"""GET /v1/today — bundled pre-session snapshot for the dashboard home.

Single fetch that powers the entire `/today` Next.js page : macro
regime + calendar (FRED + ForexFactory merged) + top-3 latest session
cards. Reduces the dashboard's network roundtrips from 3 to 1 and
guarantees the macro / calendar / sessions are evaluated against the
same instant.

The bundle is read-only and cheap : it reuses the same services that
back /v1/macro-pulse, /v1/calendar/upcoming, and /v1/sessions, so the
business logic lives in exactly one place.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import SessionCardAudit
from ..schemas import (
    ConfluenceDriver,
    IdeaSet,
    SessionCardOut,
    TradePlan,
    extract_confluence_drivers,
    extract_ideas,
    extract_thesis,
    extract_trade_plan,
)
from ..services.economic_calendar import (
    CalendarEvent as ServiceCalendarEvent,
)
from ..services.economic_calendar import (
    assess_calendar,
)
from ..services.funding_stress import assess_funding_stress
from ..services.risk_appetite import assess_risk_appetite
from ..services.vix_term_structure import assess_vix_term

router = APIRouter(prefix="/v1/today", tags=["today"])


class MacroSummary(BaseModel):
    """Distilled macro pulse — only the fields /today needs."""

    risk_composite: float
    risk_band: str
    funding_stress: float
    vix_regime: str
    vix_1m: float | None


class CalendarEventOut(BaseModel):
    when: str  # ISO date YYYY-MM-DD
    when_time_utc: str | None
    region: str
    label: str
    impact: Literal["high", "medium", "low"]
    affected_assets: list[str]
    note: str
    source: str | None


class SessionPreview(BaseModel):
    asset: str
    bias_direction: Literal["long", "short", "neutral"]
    conviction_pct: float
    magnitude_pips_low: float | None
    magnitude_pips_high: float | None
    regime_quadrant: str | None
    generated_at: datetime
    # Phase 2 typed enrichment — projected from claude_raw_response when
    # the brain runner has populated the structured shape ; null otherwise.
    thesis: str | None = None
    trade_plan: TradePlan | None = None
    ideas: IdeaSet | None = None
    confluence_drivers: list[ConfluenceDriver] | None = None


class TodaySnapshotOut(BaseModel):
    generated_at: datetime
    macro: MacroSummary
    calendar_window_days: int
    n_calendar_events: int
    calendar_events: list[CalendarEventOut]
    n_session_cards: int
    top_sessions: list[SessionPreview]


def _serialize_event(e: ServiceCalendarEvent) -> CalendarEventOut:
    return CalendarEventOut(
        when=e.when.isoformat(),
        when_time_utc=e.when_time_utc,
        region=e.region,
        label=e.label,
        impact=e.impact,
        affected_assets=list(e.affected_assets),
        note=e.note,
        source=e.source,
    )


def _serialize_session(c: SessionCardAudit) -> SessionPreview:
    raw = getattr(c, "claude_raw_response", None)
    return SessionPreview(
        asset=c.asset,
        bias_direction=c.bias_direction,  # type: ignore[arg-type]
        conviction_pct=c.conviction_pct,
        magnitude_pips_low=c.magnitude_pips_low,
        magnitude_pips_high=c.magnitude_pips_high,
        regime_quadrant=c.regime_quadrant,
        generated_at=c.generated_at,
        thesis=extract_thesis(raw),
        trade_plan=extract_trade_plan(raw),
        ideas=extract_ideas(raw),
        confluence_drivers=extract_confluence_drivers(raw),
    )


@router.get("", response_model=TodaySnapshotOut)
async def today_snapshot(
    session: Annotated[AsyncSession, Depends(get_session)],
    horizon_days: Annotated[int, Query(ge=1, le=14)] = 2,
    top_n: Annotated[int, Query(ge=1, le=8)] = 3,
) -> TodaySnapshotOut:
    """Bundled snapshot : macro summary + merged calendar + top-N sessions."""
    # ── Macro summary (re-uses the live services without going through
    #    /v1/macro-pulse — same data, no HTTP hop).
    vix = await assess_vix_term(session)
    risk = await assess_risk_appetite(session)
    fs = await assess_funding_stress(session)
    macro = MacroSummary(
        risk_composite=risk.composite,
        risk_band=risk.band,
        funding_stress=fs.stress_score,
        vix_regime=vix.regime,
        vix_1m=vix.vix_1m,
    )

    # ── Merged calendar (FRED + CB + ForexFactory).
    cal = await assess_calendar(session, horizon_days=horizon_days)
    # Filter to medium/high impact (low events are noise on /today).
    impactful = [e for e in cal.events if e.impact in ("medium", "high")]
    calendar_events = [_serialize_event(e) for e in impactful]

    # ── Top-N latest session cards (DISTINCT ON (asset)).
    stmt = (
        select(SessionCardAudit)
        .distinct(SessionCardAudit.asset)
        .order_by(SessionCardAudit.asset, desc(SessionCardAudit.generated_at))
    )
    rows = list((await session.execute(stmt)).scalars().all())
    rows_sorted = sorted(rows, key=lambda r: r.generated_at, reverse=True)[:top_n]
    top_sessions = [_serialize_session(c) for c in rows_sorted]

    return TodaySnapshotOut(
        generated_at=datetime.now(UTC),
        macro=macro,
        calendar_window_days=horizon_days,
        n_calendar_events=len(calendar_events),
        calendar_events=calendar_events,
        n_session_cards=len(rows),
        top_sessions=top_sessions,
    )


# `SessionCardOut` re-exported for legacy clients that imported it via this
# module before the dedicated /v1/sessions router landed. Kept to avoid
# breaking imports.
__all__ = ["SessionCardOut", "TodaySnapshotOut"]
