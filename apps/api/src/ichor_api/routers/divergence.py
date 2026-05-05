"""GET /v1/divergences — cross-venue prediction-market divergence scan.

Wires `services.divergence.scan_divergences` into HTTP. The scan is
read-mostly: it loads the freshest snapshot per market across the 3
prediction-market venues and runs the matcher + detector.

Phase 2 fix for SPEC.md §2.2 #8 (divergence cross-venue codée mais aucun
consommateur live).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..services.divergence import scan_divergences

router = APIRouter(prefix="/v1/divergences", tags=["divergences"])


class DivergenceItem(BaseModel):
    question: str
    gap: float
    high_venue: str
    high_price: float
    low_venue: str
    low_price: float
    similarity: float
    by_venue: dict[str, dict[str, Any]]


class DivergenceListOut(BaseModel):
    since_hours: int
    match_threshold: float
    gap_threshold: float
    n_alerts: int
    alerts: list[DivergenceItem]


@router.get("", response_model=DivergenceListOut)
async def list_divergences(
    session: Annotated[AsyncSession, Depends(get_session)],
    since_hours: Annotated[int, Query(ge=1, le=168)] = 6,
    match_threshold: Annotated[float, Query(ge=0.0, le=1.0)] = 0.55,
    gap_threshold: Annotated[float, Query(ge=0.0, le=1.0)] = 0.05,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> DivergenceListOut:
    alerts = await scan_divergences(
        session,
        since_hours=since_hours,
        match_threshold=match_threshold,
        gap_threshold=gap_threshold,
        limit=limit,
    )
    return DivergenceListOut(
        since_hours=since_hours,
        match_threshold=match_threshold,
        gap_threshold=gap_threshold,
        n_alerts=len(alerts),
        alerts=[DivergenceItem(**a) for a in alerts],
    )
