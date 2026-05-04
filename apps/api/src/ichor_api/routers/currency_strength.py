"""GET /v1/currency-strength — ranked basket strength last 24h."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..services.currency_strength import assess_currency_strength

router = APIRouter(prefix="/v1/currency-strength", tags=["currency-strength"])


class StrengthEntryOut(BaseModel):
    currency: str
    score: float
    rank: int
    n_pairs_contributing: int
    contributions: list[tuple[str, float]]


class StrengthOut(BaseModel):
    window_hours: float
    generated_at: datetime
    entries: list[StrengthEntryOut]


@router.get("", response_model=StrengthOut)
async def get_currency_strength(
    session: Annotated[AsyncSession, Depends(get_session)],
    window_hours: Annotated[float, Query(ge=1.0, le=168.0)] = 24.0,
) -> StrengthOut:
    r = await assess_currency_strength(session, window_hours=window_hours)
    return StrengthOut(
        window_hours=r.window_hours,
        generated_at=r.generated_at,
        entries=[
            StrengthEntryOut(
                currency=e.currency,
                score=e.score,
                rank=e.rank,
                n_pairs_contributing=e.n_pairs_contributing,
                contributions=e.contributions,
            )
            for e in r.entries
        ],
    )
