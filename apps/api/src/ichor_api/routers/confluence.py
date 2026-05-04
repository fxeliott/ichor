"""GET /v1/confluence/{asset} — multi-factor synthesis endpoint.

Returns the same ConfluenceReport as the data_pool block, but in a
structured JSON form so the frontend can render bars + driver lists.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import ConfluenceHistory
from ..services.confluence_engine import assess_confluence

router = APIRouter(prefix="/v1/confluence", tags=["confluence"])


_VALID_ASSET = {
    "EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD",
    "XAU_USD", "NAS100_USD", "SPX500_USD",
}


class DriverOut(BaseModel):
    factor: str
    contribution: float
    evidence: str
    source: str | None


class ConfluenceOut(BaseModel):
    asset: str
    score_long: float
    score_short: float
    score_neutral: float
    dominant_direction: Literal["long", "short", "neutral"]
    confluence_count: int
    drivers: list[DriverOut]
    rationale: str


class HistoryPointOut(BaseModel):
    captured_at: datetime
    score_long: float
    score_short: float
    score_neutral: float
    dominant_direction: str
    confluence_count: int


class HistoryOut(BaseModel):
    asset: str
    window_days: int
    n_points: int
    points: list[HistoryPointOut]


@router.get("/{asset}/history", response_model=HistoryOut)
async def get_confluence_history(
    asset: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    window_days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> HistoryOut:
    """Time-series of confluence snapshots for `asset`."""
    asset_norm = asset.upper().replace("-", "_")
    if asset_norm not in _VALID_ASSET:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown asset {asset_norm!r}",
        )
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    rows = list(
        (
            await session.execute(
                select(ConfluenceHistory)
                .where(
                    ConfluenceHistory.asset == asset_norm,
                    ConfluenceHistory.captured_at >= cutoff,
                )
                .order_by(ConfluenceHistory.captured_at.asc())
            )
        ).scalars().all()
    )
    points = [
        HistoryPointOut(
            captured_at=r.captured_at,
            score_long=r.score_long,
            score_short=r.score_short,
            score_neutral=r.score_neutral,
            dominant_direction=r.dominant_direction,
            confluence_count=r.confluence_count,
        )
        for r in rows
    ]
    return HistoryOut(
        asset=asset_norm,
        window_days=window_days,
        n_points=len(points),
        points=points,
    )


@router.get("/{asset}", response_model=ConfluenceOut)
async def get_confluence(
    asset: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ConfluenceOut:
    asset_norm = asset.upper().replace("-", "_")
    if asset_norm not in _VALID_ASSET:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown asset {asset_norm!r}",
        )
    report = await assess_confluence(session, asset_norm)
    return ConfluenceOut(
        asset=report.asset,
        score_long=report.score_long,
        score_short=report.score_short,
        score_neutral=report.score_neutral,
        dominant_direction=report.dominant_direction,
        confluence_count=report.confluence_count,
        drivers=[
            DriverOut(
                factor=d.factor,
                contribution=d.contribution,
                evidence=d.evidence,
                source=d.source,
            )
            for d in report.drivers
        ],
        rationale=report.rationale,
    )
