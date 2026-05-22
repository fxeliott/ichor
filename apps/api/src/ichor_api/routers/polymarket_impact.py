"""GET /v1/polymarket-impact — themed cluster + per-asset directional impact."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..services.polymarket_impact import assess_polymarket_impact

router = APIRouter(prefix="/v1/polymarket-impact", tags=["polymarket-impact"])


class MarketHitOut(BaseModel):
    slug: str
    question: str
    yes: float
    weight: float
    yes_24h_ago: float | None = None
    """r131 axis-8 Δ-YES manipulation watch — YES from oldest snapshot in
    24h-48h-ago window for this slug. `None` if no history (market <24h
    or cron gap). Frontend uses this + yes_velocity_pp for velocity badge."""
    yes_velocity_pp: float | None = None
    """r131 axis-8 Δ-YES manipulation watch primitive — signed shift in
    percentage points over the last 24h : `(yes - yes_24h_ago) * 100`.
    `None` if yes_24h_ago is None (honest silent absence per doctrine
    #11). Tone escalation : `|v| ≥ 5pp` = "shift rapide", `≥ 10pp` =
    "shift majeur" (descriptive magnitude, NEVER causal "manipulation"
    label per trader CRITICAL-1 — reserved until r132+ ships cross-
    venue divergence). ADR-017 boundary preserved."""
    yes_24h_ago_at: datetime | None = None
    """r131 trader MUST-FIX-2 — ISO timestamp of the snapshot used as
    the 24h-ago reference for velocity computation. Honest dual-stamp :
    `generated_at` stamps the YES_now batch, `yes_24h_ago_at` stamps
    the comparison point. `None` if `yes_24h_ago` is None."""


class ThemeHitOut(BaseModel):
    theme_key: str
    label: str
    n_markets: int
    avg_yes: float
    markets: list[MarketHitOut]
    impact_per_asset: dict[str, float]


class ImpactOut(BaseModel):
    generated_at: datetime
    n_markets_scanned: int
    themes: list[ThemeHitOut]
    asset_aggregate: dict[str, float]


@router.get("", response_model=ImpactOut)
async def get_impact(
    session: Annotated[AsyncSession, Depends(get_session)],
    hours: Annotated[int, Query(ge=1, le=168)] = 24,
    limit: Annotated[int, Query(ge=10, le=500)] = 100,
) -> ImpactOut:
    r = await assess_polymarket_impact(session, hours=hours, limit=limit)
    return ImpactOut(
        generated_at=r.generated_at,
        n_markets_scanned=r.n_markets_scanned,
        themes=[
            ThemeHitOut(
                theme_key=t.theme_key,
                label=t.label,
                n_markets=t.n_markets,
                avg_yes=t.avg_yes,
                markets=[
                    MarketHitOut(
                        slug=m.slug,
                        question=m.question,
                        yes=m.yes,
                        weight=m.weight,
                        yes_24h_ago=m.yes_24h_ago,
                        yes_velocity_pp=m.yes_velocity_pp,
                        yes_24h_ago_at=m.yes_24h_ago_at,
                    )
                    for m in t.markets
                ],
                impact_per_asset=t.impact_per_asset,
            )
            for t in r.themes
        ],
        asset_aggregate=r.asset_aggregate,
    )
