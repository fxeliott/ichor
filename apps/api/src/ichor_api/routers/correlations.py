"""GET /v1/correlations — cross-asset correlation matrix endpoint."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..services.correlations import assess_correlations

router = APIRouter(prefix="/v1/correlations", tags=["correlations"])


class CorrelationOut(BaseModel):
    window_days: int
    assets: list[str]
    matrix: list[list[float | None]]
    n_returns_used: int
    generated_at: datetime
    flags: list[str]


@router.get("", response_model=CorrelationOut)
async def get_correlations(
    session: Annotated[AsyncSession, Depends(get_session)],
    window_days: Annotated[int, Query(ge=3, le=180)] = 30,
) -> CorrelationOut:
    m = await assess_correlations(session, window_days=window_days)
    return CorrelationOut(
        window_days=m.window_days,
        assets=m.assets,
        matrix=m.matrix,
        n_returns_used=m.n_returns_used,
        generated_at=m.generated_at,
        flags=m.flags,
    )
