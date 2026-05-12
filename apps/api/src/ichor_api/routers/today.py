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


# ────────────────── G11 — /today/diff "what changed overnight" ──────────────────


class DiffDeltaOut(BaseModel):
    """One field's J vs J-1 delta. Numeric fields are signed differences ;
    string fields use a `transition` shape `"prev → curr"` (or null when
    the value hasn't changed)."""

    field: str
    prev: float | str | None
    curr: float | str | None
    delta: float | str | None


class AssetDiffOut(BaseModel):
    """One asset's today-vs-yesterday card delta."""

    asset: str
    session_type: str
    has_today: bool
    has_yesterday: bool
    today_card: SessionPreview | None
    yesterday_card: SessionPreview | None
    deltas: list[DiffDeltaOut]


class TodayDiffOut(BaseModel):
    """`/v1/today/diff` response — per-asset deltas vs yesterday's
    equivalent session for the 6-asset universe."""

    generated_at: datetime
    session_type: str
    n_assets: int
    assets: list[AssetDiffOut]


def _diff_session_cards(
    *,
    today: SessionCardAudit | None,
    yesterday: SessionCardAudit | None,
) -> list[DiffDeltaOut]:
    """Compute per-field deltas between two cards. Skip fields where
    `prev == curr` so the UI only renders changed deltas."""
    if today is None or yesterday is None:
        return []
    out: list[DiffDeltaOut] = []
    if today.conviction_pct is not None and yesterday.conviction_pct is not None:
        delta = float(today.conviction_pct) - float(yesterday.conviction_pct)
        if abs(delta) >= 0.5:
            out.append(
                DiffDeltaOut(
                    field="conviction_pct",
                    prev=float(yesterday.conviction_pct),
                    curr=float(today.conviction_pct),
                    delta=delta,
                )
            )
    if today.bias_direction and yesterday.bias_direction:
        if today.bias_direction != yesterday.bias_direction:
            out.append(
                DiffDeltaOut(
                    field="bias_direction",
                    prev=yesterday.bias_direction,
                    curr=today.bias_direction,
                    delta=f"{yesterday.bias_direction} → {today.bias_direction}",
                )
            )
    if today.regime_quadrant and yesterday.regime_quadrant:
        if today.regime_quadrant != yesterday.regime_quadrant:
            out.append(
                DiffDeltaOut(
                    field="regime_quadrant",
                    prev=yesterday.regime_quadrant,
                    curr=today.regime_quadrant,
                    delta=f"{yesterday.regime_quadrant} → {today.regime_quadrant}",
                )
            )
    return out


@router.get("/diff", response_model=TodayDiffOut)
async def today_diff(
    session: Annotated[AsyncSession, Depends(get_session)],
    session_type: Annotated[
        str,
        Query(pattern=r"^(pre_londres|pre_ny|ny_mid|ny_close|event_driven)$"),
    ] = "pre_londres",
) -> TodayDiffOut:
    """Server-side J vs J-1 delta for the 6-asset universe (G11 closure).

    For each asset, fetches the latest card with the requested
    `session_type` AND the previous calendar day's card with the same
    `session_type`, then computes meaningful deltas (conviction_pct
    ≥ 0.5pp, bias_direction change, regime_quadrant change). Empty
    `deltas` array = no meaningful change overnight.

    Used by `/today` page to surface "what changed overnight" without
    forcing the client to fetch two days of cards and diff client-side.
    """
    from datetime import timedelta

    now = datetime.now(UTC)
    assets = (
        "EUR_USD",
        "GBP_USD",
        "USD_CAD",
        "XAU_USD",
        "NAS100_USD",
        "SPX500_USD",
    )
    out_assets: list[AssetDiffOut] = []
    today_cutoff = now - timedelta(hours=36)
    yest_cutoff_start = now - timedelta(hours=60)
    yest_cutoff_end = today_cutoff
    for asset in assets:
        t_stmt = (
            select(SessionCardAudit)
            .where(
                SessionCardAudit.asset == asset,
                SessionCardAudit.session_type == session_type,
                SessionCardAudit.generated_at >= today_cutoff,
            )
            .order_by(desc(SessionCardAudit.generated_at))
            .limit(1)
        )
        today_card = (await session.execute(t_stmt)).scalar_one_or_none()
        y_stmt = (
            select(SessionCardAudit)
            .where(
                SessionCardAudit.asset == asset,
                SessionCardAudit.session_type == session_type,
                SessionCardAudit.generated_at >= yest_cutoff_start,
                SessionCardAudit.generated_at < yest_cutoff_end,
            )
            .order_by(desc(SessionCardAudit.generated_at))
            .limit(1)
        )
        yest_card = (await session.execute(y_stmt)).scalar_one_or_none()

        deltas = _diff_session_cards(today=today_card, yesterday=yest_card)
        out_assets.append(
            AssetDiffOut(
                asset=asset,
                session_type=session_type,
                has_today=today_card is not None,
                has_yesterday=yest_card is not None,
                today_card=_serialize_session(today_card) if today_card else None,
                yesterday_card=_serialize_session(yest_card) if yest_card else None,
                deltas=deltas,
            )
        )

    return TodayDiffOut(
        generated_at=now,
        session_type=session_type,
        n_assets=len(out_assets),
        assets=out_assets,
    )


# `SessionCardOut` re-exported for legacy clients that imported it via this
# module before the dedicated /v1/sessions router landed. Kept to avoid
# breaking imports.
__all__ = ["SessionCardOut", "TodayDiffOut", "TodaySnapshotOut"]
