"""GET /v1/portfolio-exposure — net basket exposure across all 8 cards."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..services.portfolio_exposure import assess_portfolio_exposure

router = APIRouter(
    prefix="/v1/portfolio-exposure", tags=["portfolio-exposure"]
)


class CardLiteOut(BaseModel):
    asset: str
    bias: str
    conviction_pct: float
    magnitude_pips_low: float | None
    magnitude_pips_high: float | None
    session_type: str
    created_at: datetime


class ExposureAxisOut(BaseModel):
    name: str
    score: float
    contributors: list[tuple[str, float]]


class ExposureOut(BaseModel):
    n_cards: int
    cards: list[CardLiteOut]
    axes: list[ExposureAxisOut]
    concentration_warnings: list[str]
    generated_at: datetime


@router.get("", response_model=ExposureOut)
async def get_portfolio_exposure(
    session: Annotated[AsyncSession, Depends(get_session)],
    max_age_hours: Annotated[int, Query(ge=1, le=168)] = 24,
) -> ExposureOut:
    r = await assess_portfolio_exposure(session, max_age_hours=max_age_hours)
    return ExposureOut(
        n_cards=r.n_cards,
        cards=[
            CardLiteOut(
                asset=c.asset,
                bias=c.bias,
                conviction_pct=c.conviction_pct,
                magnitude_pips_low=c.magnitude_pips_low,
                magnitude_pips_high=c.magnitude_pips_high,
                session_type=c.session_type,
                created_at=c.created_at,
            )
            for c in r.cards
        ],
        axes=[
            ExposureAxisOut(
                name=ax.name,
                score=ax.score,
                contributors=ax.contributors,
            )
            for ax in r.axes
        ],
        concentration_warnings=r.concentration_warnings,
        generated_at=r.generated_at,
    )
