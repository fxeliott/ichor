"""GET /v1/alerts (list, filter, acknowledge)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Alert
from ..schemas import AlertOut

router = APIRouter(prefix="/v1/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertOut])
async def list_alerts(
    session: Annotated[AsyncSession, Depends(get_session)],
    severity: str | None = Query(None, regex=r"^(info|warning|critical)$"),
    asset: str | None = Query(None, regex=r"^[A-Z0-9_]{3,16}$"),
    unacknowledged_only: bool = False,
    limit: int = Query(50, ge=1, le=500),
) -> list[AlertOut]:
    stmt = select(Alert).order_by(desc(Alert.triggered_at))
    if severity:
        stmt = stmt.where(Alert.severity == severity)
    if asset:
        stmt = stmt.where(Alert.asset == asset)
    if unacknowledged_only:
        stmt = stmt.where(Alert.acknowledged_at.is_(None))

    rows = (await session.execute(stmt.limit(limit))).scalars().all()
    return [AlertOut.model_validate(r) for r in rows]


@router.post("/{alert_id}/acknowledge", response_model=AlertOut)
async def acknowledge_alert(
    alert_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AlertOut:
    row = await session.get(Alert, alert_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    row.acknowledged_at = datetime.now(UTC)
    await session.flush()
    return AlertOut.model_validate(row)
