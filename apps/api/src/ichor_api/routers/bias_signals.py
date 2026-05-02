"""GET /v1/bias-signals — current + historical aggregator outputs."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import BiasSignal
from ..schemas import BiasSignalOut

router = APIRouter(prefix="/v1/bias-signals", tags=["bias-signals"])


@router.get("/current", response_model=list[BiasSignalOut])
async def current_signals(
    session: Annotated[AsyncSession, Depends(get_session)],
    horizon_hours: int = Query(24, ge=1, le=168),
) -> list[BiasSignalOut]:
    """One signal per asset for the requested horizon: the latest row per asset."""
    # `DISTINCT ON (asset)` ordered by generated_at DESC = latest per asset
    stmt = (
        select(BiasSignal)
        .where(BiasSignal.horizon_hours == horizon_hours)
        .order_by(BiasSignal.asset, desc(BiasSignal.generated_at))
        .distinct(BiasSignal.asset)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [BiasSignalOut.model_validate(r) for r in rows]


@router.get("/history", response_model=list[BiasSignalOut])
async def signal_history(
    session: Annotated[AsyncSession, Depends(get_session)],
    asset: str = Query(..., regex=r"^[A-Z0-9_]{3,16}$"),
    horizon_hours: int = Query(24, ge=1, le=168),
    limit: int = Query(100, ge=1, le=1000),
) -> list[BiasSignalOut]:
    stmt = (
        select(BiasSignal)
        .where(BiasSignal.asset == asset, BiasSignal.horizon_hours == horizon_hours)
        .order_by(desc(BiasSignal.generated_at))
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [BiasSignalOut.model_validate(r) for r in rows]
