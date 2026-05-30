"""GET /v1/stir — market-implied Fed-funds path + repricing delta (CME ZQ).

Wires `services.stir.assess_stir` into HTTP. Surfaces the implied EFFR forward
curve (front month → Jan-2027), the cumulative basis points priced vs the front
month, and the ~5-session repricing delta (the anticipation signal) that was
previously buried in Pass-2 markdown with no endpoint.

ADR-017 : market-implied path, not a forecast — pure-data route, deliberately
OUT of the AI-watermark prefix set.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..services.stir import assess_stir

router = APIRouter(prefix="/v1/stir", tags=["stir"])


class StirPointOut(BaseModel):
    series_id: str
    month_label: str
    implied_effr: float | None
    observation_date: datetime | None
    cum_bps_vs_front: float | None
    repricing_bps: float | None
    sessions_in_window: int


class StirMeetingOut(BaseModel):
    label: str
    decision_date: str
    implied_change_bps: float | None
    p_cut: float | None
    p_hold: float | None
    p_hike: float | None


class StirOut(BaseModel):
    as_of: datetime | None
    policy_rate_effr: float | None
    front_implied_effr: float | None
    points: list[StirPointOut]
    meetings: list[StirMeetingOut]
    horizon_label: str | None
    net_bps_to_horizon: float | None
    cuts_priced_to_horizon: float | None
    tone: str
    repricing_bps_horizon: float | None
    note: str
    sources: list[str]


@router.get("", response_model=StirOut)
async def get_stir(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StirOut:
    reading = await assess_stir(session)
    return StirOut(
        as_of=reading.as_of,
        policy_rate_effr=reading.policy_rate_effr,
        front_implied_effr=reading.front_implied_effr,
        points=[
            StirPointOut(
                series_id=p.series_id,
                month_label=p.month_label,
                implied_effr=p.implied_effr,
                observation_date=p.observation_date,
                cum_bps_vs_front=p.cum_bps_vs_front,
                repricing_bps=p.repricing_bps,
                sessions_in_window=p.sessions_in_window,
            )
            for p in reading.points
        ],
        meetings=[
            StirMeetingOut(
                label=m.label,
                decision_date=m.decision_date,
                implied_change_bps=m.implied_change_bps,
                p_cut=m.p_cut,
                p_hold=m.p_hold,
                p_hike=m.p_hike,
            )
            for m in reading.meetings
        ],
        horizon_label=reading.horizon_label,
        net_bps_to_horizon=reading.net_bps_to_horizon,
        cuts_priced_to_horizon=reading.cuts_priced_to_horizon,
        tone=reading.tone,
        repricing_bps_horizon=reading.repricing_bps_horizon,
        note=reading.note,
        sources=list(reading.sources),
    )
