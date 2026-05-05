"""manifold_markets table — periodic Manifold market snapshots."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ManifoldMarket(Base):
    """One poll of one Manifold market.

    Composite PK (id, fetched_at) for TimescaleDB hypertable on `fetched_at`.
    """

    __tablename__ = "manifold_markets"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    slug: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    market_id: Mapped[str] = mapped_column(String(128), nullable=False)
    question: Mapped[str] = mapped_column(String(512), nullable=False)
    probability: Mapped[float | None] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float)
    closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    creator_username: Mapped[str | None] = mapped_column(String(128))
