"""polymarket_snapshots table — periodic price snapshots of watched markets."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PolymarketSnapshot(Base):
    """One poll of one Polymarket binary/multi-outcome market.

    Composite PK (id, fetched_at) for TimescaleDB hypertable on `fetched_at`.
    """

    __tablename__ = "polymarket_snapshots"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    slug: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    market_id: Mapped[str] = mapped_column(String(128), nullable=False)
    question: Mapped[str] = mapped_column(String(512), nullable=False)
    closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    outcomes: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    last_prices: Mapped[list[float]] = mapped_column(JSONB, nullable=False)
    volume_usd: Mapped[float | None] = mapped_column(Float)
