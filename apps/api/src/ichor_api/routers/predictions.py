"""GET /v1/predictions — read predictions_audit for the dashboard."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Prediction

router = APIRouter(prefix="/v1/predictions", tags=["predictions"])


class PredictionOut(BaseModel):
    id: UUID
    generated_at: datetime
    model_id: str
    model_family: str
    asset: str
    horizon_hours: int
    direction: Literal["long", "short", "neutral"]
    raw_score: float
    calibrated_probability: float | None
    realized_direction: str | None
    brier_contribution: float | None

    model_config = {"from_attributes": True}


class ModelSummary(BaseModel):
    model_id: str
    n_predictions: int
    earliest: datetime | None
    latest: datetime | None
    asset: str | None
    avg_brier: float | None


@router.get("", response_model=list[PredictionOut])
async def list_predictions(
    session: Annotated[AsyncSession, Depends(get_session)],
    asset: str | None = Query(None, regex=r"^[A-Z0-9_]{3,16}$"),
    model_id: str | None = Query(None, max_length=128),
    since_days: int = Query(30, ge=1, le=3650),
    limit: int = Query(100, ge=1, le=2000),
) -> list[PredictionOut]:
    cutoff = datetime.now(UTC) - timedelta(days=since_days)
    stmt = (
        select(Prediction)
        .where(Prediction.generated_at >= cutoff)
        .order_by(desc(Prediction.generated_at))
    )
    if asset:
        stmt = stmt.where(Prediction.asset == asset)
    if model_id:
        stmt = stmt.where(Prediction.model_id == model_id)
    rows = (await session.execute(stmt.limit(limit))).scalars().all()
    return [PredictionOut.model_validate(r) for r in rows]


@router.get("/models", response_model=list[ModelSummary])
async def list_models(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ModelSummary]:
    """Aggregate per model_id : count + earliest/latest + avg Brier."""
    stmt = (
        select(
            Prediction.model_id,
            func.count(Prediction.id).label("n"),
            func.min(Prediction.generated_at).label("earliest"),
            func.max(Prediction.generated_at).label("latest"),
            func.max(Prediction.asset).label("asset"),
            func.avg(Prediction.brier_contribution).label("avg_brier"),
        )
        .group_by(Prediction.model_id)
        .order_by(desc(func.max(Prediction.generated_at)))
    )
    rows = (await session.execute(stmt)).all()
    return [
        ModelSummary(
            model_id=r[0],
            n_predictions=r[1],
            earliest=r[2],
            latest=r[3],
            asset=r[4],
            avg_brier=float(r[5]) if r[5] is not None else None,
        )
        for r in rows
    ]
