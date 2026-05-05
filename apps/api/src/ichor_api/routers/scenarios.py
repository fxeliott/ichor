"""GET /v1/scenarios/{asset} — 3-scenario continuation/reversal/sideways probabilities.

Powers the `/scenarios/[asset]` Next.js drill-down page. Wraps the existing
`services.session_scenarios.assess_session_scenarios` empirical model and
optionally enriches its inputs from the latest `session_card_audit` row
for the asset (so the regime + conviction reflect the freshest brain
verdict instead of caller-supplied defaults).

NOTE — this endpoint exposes the **3-scenario empirical model** that's
already shipped (Continuation / Reversal / Sideways from SMC structure
+ régime + conviction). The richer 7-scenario tree produced by Pass 4
of the brain pipeline is persisted inside `session_card_audit.mechanisms`
but isn't yet flattened into a typed schema ; surfacing that one is
deferred until a Pass 4 schema delta lands.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import SessionCardAudit
from ..services.daily_levels import assess_daily_levels
from ..services.session_scenarios import assess_session_scenarios

router = APIRouter(prefix="/v1/scenarios", tags=["scenarios"])

SessionType = Literal["pre_londres", "pre_ny", "ny_mid", "ny_close", "event_driven"]
RegimeQuadrant = Literal["haven_bid", "funding_stress", "goldilocks", "usd_complacency"]

_VALID_ASSETS = {
    "EUR_USD",
    "GBP_USD",
    "USD_JPY",
    "AUD_USD",
    "USD_CAD",
    "XAU_USD",
    "NAS100_USD",
    "SPX500_USD",
}
_VALID_SESSION_TYPES: set[str] = {
    "pre_londres",
    "pre_ny",
    "ny_mid",
    "ny_close",
    "event_driven",
}


class ScenarioRow(BaseModel):
    kind: Literal["continuation", "reversal", "sideways"]
    probability: float = Field(ge=0.0, le=1.0)
    triggers: list[str]


class ScenariosLevelsOut(BaseModel):
    spot: float | None
    pdh: float | None
    pdl: float | None
    asian_high: float | None
    asian_low: float | None


class ScenariosOut(BaseModel):
    asset: str
    session_type: SessionType
    regime: RegimeQuadrant | None
    conviction_pct: float
    sources: list[Literal["latest_session_card", "caller_default"]]
    """Tells the caller which inputs came from a persisted card vs defaults."""
    generated_at: datetime
    rationale: str
    levels: ScenariosLevelsOut
    scenarios: list[ScenarioRow]
    notes: list[str]
    """Caveats / non-deferred-but-mock fields, surfaced inline so the
    frontend doesn't have to encode them separately."""
    latest_card_id: UUID | None = None


def _normalize_asset(asset: str) -> str:
    return asset.upper().replace("-", "_")


async def _latest_card(session: AsyncSession, asset: str) -> SessionCardAudit | None:
    return (
        await session.execute(
            select(SessionCardAudit)
            .where(SessionCardAudit.asset == asset)
            .order_by(desc(SessionCardAudit.generated_at))
            .limit(1)
        )
    ).scalar_one_or_none()


@router.get("/{asset}", response_model=ScenariosOut)
async def get_scenarios(
    asset: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    session_type: Annotated[SessionType, Query()] = "pre_londres",
    regime: Annotated[RegimeQuadrant | None, Query()] = None,
    conviction_pct: Annotated[float, Query(ge=0.0, le=95.0)] = 50.0,
) -> ScenariosOut:
    """Return the 3-scenario probabilities for `asset` upcoming session.

    By default the regime + conviction are pulled from the most recent
    `session_card_audit` row for the asset — this matches what the brain
    "sees" right now. Caller can override either with the explicit query
    params for what-if probing (e.g. `?regime=funding_stress&conviction_pct=80`).
    """
    asset_norm = _normalize_asset(asset)
    if asset_norm not in _VALID_ASSETS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown asset {asset_norm!r}",
        )
    if session_type not in _VALID_SESSION_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown session_type {session_type!r}",
        )

    # Pull the latest persisted card to default regime + conviction from
    # what the brain saw most recently. Caller params override.
    sources: list[Literal["latest_session_card", "caller_default"]] = []
    latest_card_id: UUID | None = None
    card = await _latest_card(session, asset_norm)
    effective_regime: RegimeQuadrant | None = regime
    effective_conviction = conviction_pct
    if card is not None:
        latest_card_id = card.id
        if regime is None and card.regime_quadrant in (
            "haven_bid",
            "funding_stress",
            "goldilocks",
            "usd_complacency",
        ):
            effective_regime = card.regime_quadrant  # type: ignore[assignment]
            sources.append("latest_session_card")
        if conviction_pct == 50.0 and card.conviction_pct is not None:
            effective_conviction = float(card.conviction_pct)
            if "latest_session_card" not in sources:
                sources.append("latest_session_card")
    if not sources:
        sources.append("caller_default")

    levels = await assess_daily_levels(session, asset_norm)
    sc = assess_session_scenarios(
        levels,
        session_type=session_type,
        regime=effective_regime,
        conviction_pct=effective_conviction,
    )

    notes: list[str] = []
    if levels.spot is None or levels.pdh is None or levels.pdl is None:
        notes.append(
            "Insufficient intraday history for asset — probabilities are a "
            "neutral fallback (1/3 each)."
        )
    if card is None:
        notes.append("No session_card_audit row for asset — using caller defaults.")

    return ScenariosOut(
        asset=asset_norm,
        session_type=session_type,
        regime=effective_regime,
        conviction_pct=effective_conviction,
        sources=sources,
        generated_at=datetime.now().astimezone(),
        rationale=sc.rationale,
        levels=ScenariosLevelsOut(
            spot=levels.spot,
            pdh=levels.pdh,
            pdl=levels.pdl,
            asian_high=levels.asian_high,
            asian_low=levels.asian_low,
        ),
        scenarios=[
            ScenarioRow(
                kind="continuation",
                probability=sc.p_continuation,
                triggers=list(sc.triggers_continuation),
            ),
            ScenarioRow(
                kind="reversal",
                probability=sc.p_reversal,
                triggers=list(sc.triggers_reversal),
            ),
            ScenarioRow(kind="sideways", probability=sc.p_sideways, triggers=[]),
        ],
        notes=notes,
        latest_card_id=latest_card_id,
    )
