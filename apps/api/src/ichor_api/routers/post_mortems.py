"""GET /v1/post-mortems — weekly post-mortem listings.

Reads from the `post_mortems` table (migration 0010). Each row is the
structured-data index for one ISO-week post-mortem, with the actual
markdown stored on disk under `docs/post_mortem/{YYYY-Www}.md`.

The list endpoint exposes summary stats only (counts, Brier-30d, drift
flags, actionable progression) — the full markdown is fetched via the
detail endpoint or read from disk by the caller.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import PostMortem

router = APIRouter(prefix="/v1/post-mortems", tags=["post_mortems"])


class PostMortemSummaryOut(BaseModel):
    id: UUID
    iso_year: int
    iso_week: int
    generated_at: datetime
    markdown_path: str
    n_top_hits: int = Field(ge=0)
    n_top_miss: int = Field(ge=0)
    n_drift_flags: int = Field(ge=0)
    brier_30d: float | None
    actionable_count: int = Field(ge=0)
    actionable_resolved: int = Field(ge=0)


class PostMortemListOut(BaseModel):
    total: int
    items: list[PostMortemSummaryOut]


def _list_len(payload: object) -> int:
    """Length of a JSONB list field, or 0 if None / not a list."""
    return len(payload) if isinstance(payload, list) else 0


def _brier_from(calibration: object) -> float | None:
    """Extract `brier_30d` from the JSONB calibration block, if present."""
    if not isinstance(calibration, dict):
        return None
    val = calibration.get("brier_30d")
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _summarize(pm: PostMortem) -> PostMortemSummaryOut:
    return PostMortemSummaryOut(
        id=pm.id,
        iso_year=pm.iso_year,
        iso_week=pm.iso_week,
        generated_at=pm.generated_at,
        markdown_path=pm.markdown_path,
        n_top_hits=_list_len(pm.top_hits),
        n_top_miss=_list_len(pm.top_miss),
        n_drift_flags=_list_len(pm.drift_detected),
        brier_30d=_brier_from(pm.calibration),
        actionable_count=pm.actionable_count,
        actionable_resolved=pm.actionable_count_resolved,
    )


@router.get("", response_model=PostMortemListOut)
async def list_post_mortems(
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PostMortemListOut:
    """Newest-first list of weekly post-mortems with summary metadata."""
    base = select(PostMortem).order_by(desc(PostMortem.generated_at))
    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await session.execute(base.offset(offset).limit(limit))).scalars().all()
    return PostMortemListOut(total=int(total), items=[_summarize(r) for r in rows])


@router.get("/{iso_year}-W{iso_week}", response_model=PostMortemSummaryOut)
async def get_post_mortem(
    iso_year: int,
    iso_week: int,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PostMortemSummaryOut:
    """One specific week (URL-friendly slug `2026-W18`)."""
    if iso_week < 1 or iso_week > 53 or iso_year < 2025:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid ISO year/week",
        )
    row = (
        await session.execute(
            select(PostMortem).where(
                PostMortem.iso_year == iso_year, PostMortem.iso_week == iso_week
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No post-mortem for {iso_year}-W{iso_week:02d}",
        )
    return _summarize(row)
