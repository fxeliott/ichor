"""confluence_history — TimescaleDB hypertable of per-asset confluence snapshots.

Each row captures the output of `assess_confluence` for one asset at one
point in time. A nightly cron persists 8 rows (one per phase-1 asset).
The /v1/confluence/{asset}/history endpoint queries this table.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ConfluenceHistory(Base):
    """One snapshot of /v1/confluence for one asset."""

    __tablename__ = "confluence_history"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    asset: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    score_long: Mapped[float] = mapped_column(Float, nullable=False)
    score_short: Mapped[float] = mapped_column(Float, nullable=False)
    score_neutral: Mapped[float] = mapped_column(Float, nullable=False)
    dominant_direction: Mapped[str] = mapped_column(String(8), nullable=False)
    confluence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    n_drivers: Mapped[int] = mapped_column(Integer, nullable=False)
    drivers: Mapped[Any | None] = mapped_column(JSONB)
