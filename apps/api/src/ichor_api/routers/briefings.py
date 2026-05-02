"""GET /v1/briefings (list + detail)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Briefing
from ..schemas import BriefingListOut, BriefingOut

router = APIRouter(prefix="/v1/briefings", tags=["briefings"])


@router.get("", response_model=BriefingListOut)
async def list_briefings(
    session: Annotated[AsyncSession, Depends(get_session)],
    briefing_type: str | None = Query(None, regex=r"^(pre_londres|pre_ny|ny_mid|ny_close|weekly|crisis)$"),
    asset: str | None = Query(None, regex=r"^[A-Z0-9_]{3,16}$"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> BriefingListOut:
    """Paginated newest-first listing. Filter by type and/or asset."""
    stmt = select(Briefing).order_by(desc(Briefing.triggered_at))

    if briefing_type:
        stmt = stmt.where(Briefing.briefing_type == briefing_type)
    if asset:
        # Postgres ARRAY contains
        stmt = stmt.where(Briefing.assets.any(asset))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar_one()

    stmt = stmt.offset(offset).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()

    return BriefingListOut(total=total, items=[BriefingOut.model_validate(r) for r in rows])


@router.get("/{briefing_id}", response_model=BriefingOut)
async def get_briefing(
    briefing_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BriefingOut:
    row = await session.get(Briefing, briefing_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Briefing not found")
    return BriefingOut.model_validate(row)
