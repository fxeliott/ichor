"""GET /v1/polymarket-impact — themed cluster + per-asset directional impact."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..services.polymarket_impact import assess_polymarket_impact

router = APIRouter(
    prefix="/v1/polymarket-impact", tags=["polymarket-impact"]
)


class MarketHitOut(BaseModel):
    slug: str
    question: str
    yes: float
    weight: float


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
                    )
                    for m in t.markets
                ],
                impact_per_asset=t.impact_per_asset,
            )
            for t in r.themes
        ],
        asset_aggregate=r.asset_aggregate,
    )
