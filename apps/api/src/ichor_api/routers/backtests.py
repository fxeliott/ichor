"""GET /v1/backtests — read backtest_runs for the dashboard."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import BacktestRun

router = APIRouter(prefix="/v1/backtests", tags=["backtests"])


class BacktestRunOut(BaseModel):
    id: UUID
    created_at: datetime
    model_id: str
    asset: str
    started_at: datetime
    finished_at: datetime
    config: dict[str, Any]
    metrics: dict[str, Any]
    n_folds: int
    n_signals: int
    n_trades: int
    equity_curve_summary: list[Any] | None
    notes: list[Any] | None
    paper_only: bool

    model_config = {"from_attributes": True}


@router.get("", response_model=list[BacktestRunOut])
async def list_runs(
    session: Annotated[AsyncSession, Depends(get_session)],
    asset: str | None = Query(None, regex=r"^[A-Z0-9_]{3,16}$"),
    model_id: str | None = Query(None, max_length=128),
    limit: int = Query(50, ge=1, le=500),
) -> list[BacktestRunOut]:
    stmt = select(BacktestRun).order_by(desc(BacktestRun.finished_at))
    if asset:
        stmt = stmt.where(BacktestRun.asset == asset)
    if model_id:
        stmt = stmt.where(BacktestRun.model_id == model_id)
    rows = (await session.execute(stmt.limit(limit))).scalars().all()
    return [BacktestRunOut.model_validate(r) for r in rows]


@router.get("/{run_id}", response_model=BacktestRunOut)
async def get_run(
    run_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BacktestRunOut:
    row = await session.get(BacktestRun, run_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Backtest run not found",
        )
    return BacktestRunOut.model_validate(row)
