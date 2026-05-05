"""GET /v1/hourly-volatility/{asset} — hour-of-day vol heatmap."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..services.hourly_volatility import assess_hourly_volatility

router = APIRouter(prefix="/v1/hourly-volatility", tags=["hourly-volatility"])

_VALID_ASSET = {
    "EUR_USD",
    "GBP_USD",
    "USD_JPY",
    "AUD_USD",
    "USD_CAD",
    "XAU_USD",
    "NAS100_USD",
    "SPX500_USD",
}


class HourlyVolEntryOut(BaseModel):
    hour_utc: int
    median_bp: float
    p75_bp: float
    n_samples: int


class HourlyVolOut(BaseModel):
    asset: str
    window_days: int
    entries: list[HourlyVolEntryOut]
    best_hour_utc: int | None
    worst_hour_utc: int | None
    london_session_avg_bp: float | None
    asian_session_avg_bp: float | None
    generated_at: datetime


@router.get("/{asset}", response_model=HourlyVolOut)
async def get_hourly_volatility(
    asset: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    window_days: Annotated[int, Query(ge=3, le=180)] = 30,
) -> HourlyVolOut:
    asset_norm = asset.upper().replace("-", "_")
    if asset_norm not in _VALID_ASSET:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown asset {asset_norm!r}",
        )
    r = await assess_hourly_volatility(session, asset_norm, window_days=window_days)
    return HourlyVolOut(
        asset=r.asset,
        window_days=r.window_days,
        entries=[
            HourlyVolEntryOut(
                hour_utc=e.hour_utc,
                median_bp=e.median_bp,
                p75_bp=e.p75_bp,
                n_samples=e.n_samples,
            )
            for e in r.entries
        ],
        best_hour_utc=r.best_hour_utc,
        worst_hour_utc=r.worst_hour_utc,
        london_session_avg_bp=r.london_session_avg_bp,
        asian_session_avg_bp=r.asian_session_avg_bp,
        generated_at=r.generated_at,
    )
