"""``GET /v1/dollar-coherence`` — cross-asset USD coherence read-time surface.

Surfaces the "tout interconnecté" reconciliation: the day's per-asset bias
cards are not five independent coin-flips — they are five windows onto the
same dollar/risk regime. This endpoint reads the latest persisted card per
asset (the same ``DISTINCT ON (asset)`` projection ``/v1/today`` uses),
derives each card's implied USD stance, computes the dollar consensus, and
flags the assets whose bias contradicts it.

Deterministic (no LLM call ; Voie D-clean) — but DERIVED from LLM-origin
``session_card_audit.bias_direction`` / ``conviction_pct`` (the 4-pass
pipeline), so the route prefix ``/v1/dollar-coherence`` IS watermarked
(ADR-079 / W90 invariant lockstep with ``Settings.ai_watermarked_route_
prefixes`` — same posture as ``/v1/verdict`` + ``/v1/coach-macro-context``).

**Surface contract** : always 200 + ``DollarCoherenceOut`` — when fewer
than two cards cast a directional vote there is nothing to reconcile and the
service returns ``coherent=True`` + ``consensus="neutral"`` + an honest FR
explanation (doctrine #11 calibrated honesty). No 404 (unlike
``/v1/verdict``) : an empty/neutral read is a legitimate output, not an
absence.

**ADR-017 boundary** : the response carries only descriptive geometry
(``usd_up`` / ``usd_down`` / ``mixed`` / ``neutral`` + biais haussier/
baissier) and a FR coach explanation — never BUY/SELL/TP/SL. Guarded by the
service's own ADR-017 test + the watermark invariant.

**Caching** : ``Cache-Control: private, no-store`` — LIVE state (mirror of
``routers/coach_macro_context.py:85`` + ``routers/verdict.py:128``).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models.session_card_audit import SessionCardAudit
from ..services.cross_asset_dollar_coherence import assess_dollar_coherence

router = APIRouter(prefix="/v1/dollar-coherence", tags=["dollar-coherence"])


class AssetUsdViewOut(BaseModel):
    """One asset's contribution to the cross-asset dollar read."""

    asset: str
    bias: str
    conviction: float
    stance: str  # usd_up | usd_down | neutral
    weight: float


class DollarCoherenceOut(BaseModel):
    """Cross-asset USD reconciliation — descriptive, ADR-017-clean."""

    consensus: str  # usd_up | usd_down | mixed | neutral
    consensus_strength: float = Field(ge=0.0, le=1.0)
    coherent: bool
    n_directional: int
    outliers: list[str]
    recommended_demotions: dict[str, float]
    views: list[AssetUsdViewOut]
    coach_explanation: str


@router.get(
    "",
    response_model=DollarCoherenceOut,
    summary="Cross-asset USD coherence — dollar consensus + incoherent outliers + FR coach read",
)
async def get_dollar_coherence(
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DollarCoherenceOut:
    """Reconcile the latest per-asset bias cards into one dollar read.

    Uses the same ``DISTINCT ON (asset)`` latest-card projection as
    ``/v1/today`` so the reconciliation reflects the standing per-asset
    biases. Degrades honestly when too few directional cards exist.
    """
    stmt = (
        select(SessionCardAudit)
        .distinct(SessionCardAudit.asset)
        .order_by(SessionCardAudit.asset, desc(SessionCardAudit.generated_at))
    )
    rows = list((await session.execute(stmt)).scalars().all())
    cards = [
        {
            "asset": r.asset,
            "bias_direction": r.bias_direction,
            "conviction_pct": r.conviction_pct,
        }
        for r in rows
    ]

    verdict = assess_dollar_coherence(cards)

    response.headers["Cache-Control"] = "private, no-store"
    return DollarCoherenceOut(
        consensus=verdict.consensus,
        consensus_strength=verdict.consensus_strength,
        coherent=verdict.coherent,
        n_directional=verdict.n_directional,
        outliers=list(verdict.outliers),
        recommended_demotions=dict(verdict.recommended_demotions),
        views=[
            AssetUsdViewOut(
                asset=v.asset,
                bias=v.bias,
                conviction=v.conviction,
                stance=v.stance,
                weight=v.weight,
            )
            for v in verdict.views
        ],
        coach_explanation=verdict.coach_explanation,
    )
