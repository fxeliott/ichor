"""GET /v1/confluence/{asset} — multi-factor synthesis endpoint.

Returns the same ConfluenceReport as the data_pool block, but in a
structured JSON form so the frontend can render bars + driver lists.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
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
