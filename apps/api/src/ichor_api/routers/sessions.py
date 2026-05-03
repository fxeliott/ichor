"""GET /v1/sessions — Phase 1 session-card readout.

Reads from `session_card_audit` (the table that backs every Claude
4-pass run). The list endpoint returns the latest card per asset
(newest-first), matching the dashboard grid layout. The detail
endpoint returns the full card history for one asset, paginated.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import SessionCardAudit
from ..schemas import SessionCardListOut, SessionCardOut

router = APIRouter(prefix="/v1/sessions", tags=["sessions"])

_ASSET_RE = r"^[A-Z0-9_]{3,16}$"
_SESSION_TYPE_RE = r"^(pre_londres|pre_ny|event_driven)$"


@router.get("", response_model=SessionCardListOut)
async def list_latest_sessions(
    session: Annotated[AsyncSession, Depends(get_session)],
    session_type: str | None = Query(None, regex=_SESSION_TYPE_RE),
    limit: int = Query(8, ge=1, le=64),
) -> SessionCardListOut:
    """Latest session card per asset (one row per asset).

    Implementation : DISTINCT ON (asset) ordered by `generated_at` DESC.
    Postgres-specific but cheap and the only correct way to get
    "newest per group" without a window function on a hypertable.
    """
    base = select(SessionCardAudit)
    if session_type:
        base = base.where(SessionCardAudit.session_type == session_type)

    stmt = (
        base.distinct(SessionCardAudit.asset)
        .order_by(SessionCardAudit.asset, desc(SessionCardAudit.generated_at))
    )

    rows = (await session.execute(stmt)).scalars().all()
    rows_sorted = sorted(rows, key=lambda r: r.generated_at, reverse=True)[:limit]

    return SessionCardListOut(
        total=len(rows),
        items=[SessionCardOut.model_validate(r) for r in rows_sorted],
    )


@router.get("/{asset}", response_model=SessionCardListOut)
async def list_sessions_for_asset(
    asset: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> SessionCardListOut:
    """Full history for one asset, newest-first."""
    import re

    if not re.match(_ASSET_RE, asset):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"asset must match {_ASSET_RE}",
        )

    stmt = (
        select(SessionCardAudit)
        .where(SessionCardAudit.asset == asset)
        .order_by(desc(SessionCardAudit.generated_at))
    )
    total = (
        await session.execute(
            select(func.count()).select_from(stmt.subquery())
        )
    ).scalar_one()

    rows = (
        await session.execute(stmt.offset(offset).limit(limit))
    ).scalars().all()

    return SessionCardListOut(
        total=total,
        items=[SessionCardOut.model_validate(r) for r in rows],
    )
