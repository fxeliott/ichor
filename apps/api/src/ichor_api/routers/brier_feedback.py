"""GET /v1/brier-feedback — auto-introspection on past verdicts."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..services.brier_feedback import assess_brier_feedback

router = APIRouter(prefix="/v1/brier-feedback", tags=["brier-feedback"])


class GroupStatOut(BaseModel):
    key: str
    n: int
    avg_brier: float
    win_rate: float | None


class BrierFeedbackOut(BaseModel):
    n_cards_reconciled: int
    window_days: int
    overall_avg_brier: float | None
    by_asset: list[GroupStatOut]
    by_session_type: list[GroupStatOut]
    by_regime: list[GroupStatOut]
    high_conviction_win_rate: float | None
    low_conviction_win_rate: float | None
    flags: list[str]
    generated_at: datetime


@router.get("", response_model=BrierFeedbackOut)
async def get_brier_feedback(
    session: Annotated[AsyncSession, Depends(get_session)],
    window_days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> BrierFeedbackOut:
    r = await assess_brier_feedback(session, window_days=window_days)
    return BrierFeedbackOut(
        n_cards_reconciled=r.n_cards_reconciled,
        window_days=r.window_days,
        overall_avg_brier=r.overall_avg_brier,
        by_asset=[
            GroupStatOut(
                key=s.key, n=s.n, avg_brier=s.avg_brier, win_rate=s.win_rate
            )
            for s in r.by_asset
        ],
        by_session_type=[
            GroupStatOut(
                key=s.key, n=s.n, avg_brier=s.avg_brier, win_rate=s.win_rate
            )
            for s in r.by_session_type
        ],
        by_regime=[
            GroupStatOut(
                key=s.key, n=s.n, avg_brier=s.avg_brier, win_rate=s.win_rate
            )
            for s in r.by_regime
        ],
        high_conviction_win_rate=r.high_conviction_win_rate,
        low_conviction_win_rate=r.low_conviction_win_rate,
        flags=r.flags,
        generated_at=r.generated_at,
    )
