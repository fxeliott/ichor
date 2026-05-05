"""GET /v1/yield-curve — US Treasury yield curve full term structure.

Wires `services.yield_curve.assess_yield_curve` into HTTP. Pulls 10
maturities (3M -> 30Y) + TIPS DFII10 from FRED-stored observations,
returns curve shape, slopes, inversion count, and a short interpretive
note ready for the brain Pass 1 / web2 dashboard.

Phase 2 fix : closes the "/yield-curve page is 100% mock with no router"
gap noted in the 2026-05-05 audit.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..services.yield_curve import assess_yield_curve

router = APIRouter(prefix="/v1/yield-curve", tags=["yield-curve"])


class YieldTenorOut(BaseModel):
    label: str
    tenor_years: float
    series_id: str
    yield_pct: float | None
    observation_date: datetime | None


class YieldCurveOut(BaseModel):
    points: list[YieldTenorOut]
    slope_3m_10y: float | None
    slope_2y_10y: float | None
    slope_5y_30y: float | None
    real_yield_10y: float | None
    inverted_segments: int
    shape: str
    note: str
    sources: list[str]


@router.get("", response_model=YieldCurveOut)
async def get_yield_curve(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> YieldCurveOut:
    reading = await assess_yield_curve(session)
    return YieldCurveOut(
        points=[
            YieldTenorOut(
                label=p.label,
                tenor_years=p.tenor_years,
                series_id=p.series_id,
                yield_pct=p.yield_pct,
                observation_date=p.observation_date,
            )
            for p in reading.points
        ],
        slope_3m_10y=reading.slope_3m_10y,
        slope_2y_10y=reading.slope_2y_10y,
        slope_5y_30y=reading.slope_5y_30y,
        real_yield_10y=reading.real_yield_10y,
        inverted_segments=reading.inverted_segments,
        shape=reading.shape,
        note=reading.note,
        sources=list(reading.sources),
    )
