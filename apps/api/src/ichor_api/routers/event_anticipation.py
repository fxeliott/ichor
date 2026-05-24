"""GET /v1/event-anticipation/{asset} — Engine 8 forward-looking surface.

r152 ADR-099 §Impl — dedicated user-visible surface for Engine 8 (Event-
Driven anticipation factor, shipped r147 + extended r149/r150/r152). The
endpoint composes :

- ENGAGED mode : full `EventProximityFactor` projection (Engine 8 fired
  because event in 48h window).
- STANDBY mode : next 1-3 upcoming high/medium-impact events for the
  asset's relevant currencies (Engine 8 silent).
- SILENT mode : nothing in 14d window for any of the asset's currencies.

ADR-017 boundary preserved : output is DESCRIPTIVE (event title +
magnitude_bp + direction + confidence + caveat) ; NEVER imperative ;
frontend strips sign at UI boundary per r142 trader RED-1 discipline.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..services.event_anticipation_view import (
    EventAnticipationMode,
    assess_event_anticipation_view,
)

router = APIRouter(prefix="/v1/event-anticipation", tags=["event-anticipation"])


DriftDirection = Literal["up", "down", "unknown"]
EventConfidence = Literal["high", "medium", "low", "unavailable"]
VixRegimeGate = Literal["above_p75", "p50_to_p75", "below_p50", "unavailable"]
ImpactLevel = Literal["high", "medium"]


class EventProximityFactorOut(BaseModel):
    """Wire shape mirroring `services.event_proximity_engine.EventProximityFactor`.

    All fields verbatim from the dataclass to preserve doctrine #4 SSOT (the
    engine is single truth source, router never re-derives).
    """

    next_event_id: str | None
    next_event_title: str | None
    next_event_currency: str | None
    next_event_minutes_until: int | None
    next_event_impact: Literal["high", "medium", "low"] | None
    next_event_class: str | None
    expected_drift_direction: DriftDirection
    expected_drift_magnitude_bp: float | None
    confidence: EventConfidence
    vix_regime_gate: VixRegimeGate
    caveat: str
    literature_anchor: str
    parse_failures: list[str] = Field(default_factory=list)


class UpcomingEventOut(BaseModel):
    """STANDBY mode entry — one upcoming high/medium-impact event."""

    event_id: str
    currency: str
    scheduled_at_utc: datetime
    title: str
    impact: ImpactLevel
    event_class: str | None
    minutes_until: int = Field(..., ge=0)


class EventAnticipationOut(BaseModel):
    """Composed wire response for `/v1/event-anticipation/{asset}`."""

    generated_at: datetime
    asset: str
    mode: EventAnticipationMode  # "engaged" | "standby" | "silent"
    engaged: EventProximityFactorOut | None
    standby_events: list[UpcomingEventOut]
    parse_failures: list[str] = Field(default_factory=list)


@router.get("/{asset}", response_model=EventAnticipationOut)
async def get_event_anticipation(
    asset: Annotated[
        str,
        Path(
            # r152 Phase 2 code-reviewer CRIT-1 fix : original pattern
            # `^[A-Z]{3,8}_[A-Z]{3,8}$|^[A-Z]{3,8}$` REJECTED digits in the
            # prefix → silent HTTP 422 on NAS100_USD / SPX500_USD (2 of 6
            # priority assets). Empirically witnessed via TestClient. The
            # prefix MUST accept `[A-Z0-9]` to cover index-style codes ;
            # the suffix remains alpha-only (currency codes are 3 letters).
            # Matches the established `phase_d.py:176` pattern `[A-Z0-9_]{3,16}`
            # discipline.
            pattern=r"^[A-Z0-9]{3,8}_[A-Z]{3,8}$|^[A-Z0-9]{3,8}$",
            description="Ichor asset code, e.g. EUR_USD / USD_CAD / XAU_USD / NAS100_USD / SPX500_USD",
        ),
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EventAnticipationOut:
    """Forward-looking Engine 8 surface for the given asset.

    Returns one of 3 modes :

    - **engaged** — Engine 8 has a future event in the 48h window AND mapped
      it to an event_class. Renders the full `EventProximityFactor` with
      countdown / magnitude / direction / confidence / caveat / literature
      anchor / parse_failures sentinel set.
    - **standby** — no event in 48h, but next 1-3 high/medium-impact events
      in the next 14d for the asset's relevant currencies. Renders a mini
      forward calendar with countdown context (Engine 8 will engage T-48h
      before each event).
    - **silent** — nothing in 14d window. Honest empty state ; frontend
      renders explanatory chrome (no blank/dead-end UI).

    Calls `assess_event_proximity()` directly (re-runs the engine) instead
    of reading the digested `Driver` row from `session_card_audit.drivers`
    because the dedicated panel needs the rich `EventProximityFactor`
    fields (vix_regime_gate, confidence ladder, literature_anchor) that
    aren't persisted in the Driver wire shape.
    """
    asset_normalized = asset.upper().replace("-", "_")
    view = await assess_event_anticipation_view(session, asset=asset_normalized)

    engaged_out: EventProximityFactorOut | None = None
    if view.engaged is not None:
        f = view.engaged
        engaged_out = EventProximityFactorOut(
            next_event_id=f.next_event_id,
            next_event_title=f.next_event_title,
            next_event_currency=f.next_event_currency,
            next_event_minutes_until=f.next_event_minutes_until,
            next_event_impact=f.next_event_impact,
            next_event_class=f.next_event_class,
            expected_drift_direction=f.expected_drift_direction,
            expected_drift_magnitude_bp=f.expected_drift_magnitude_bp,
            confidence=f.confidence,
            vix_regime_gate=f.vix_regime_gate,
            caveat=f.caveat,
            literature_anchor=f.literature_anchor,
            parse_failures=sorted(f.parse_failures),
        )

    return EventAnticipationOut(
        generated_at=view.generated_at,
        asset=view.asset,
        mode=view.mode,
        engaged=engaged_out,
        standby_events=[
            UpcomingEventOut(
                event_id=ev.event_id,
                currency=ev.currency,
                scheduled_at_utc=ev.scheduled_at_utc,
                title=ev.title,
                impact=ev.impact,
                event_class=ev.event_class,
                minutes_until=ev.minutes_until,
            )
            for ev in view.standby_events
        ],
        parse_failures=sorted(view.parse_failures),
    )
