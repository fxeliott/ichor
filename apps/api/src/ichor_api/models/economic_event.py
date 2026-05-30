"""economic_events table — ForexFactory calendar persistence (migration 0019).

Composite natural key (currency, scheduled_at, title) makes upserts
deterministic when ForexFactory republishes the same event with
revised forecast/previous values.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class EconomicEvent(Base):
    __tablename__ = "economic_events"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    is_all_day: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    impact: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    forecast: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # r141 (migration 0052) -- forecast range envelope + published actual.
    # Classifier `services/economic_event_surprise.py` distinguishes within-
    # range (no repricing) from outside-range (material catalyst). NULL until
    # r142 reconciler populates from free-tier provider.
    forecast_min: Mapped[str | None] = mapped_column(String(64), nullable=True)
    forecast_max: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actual: Mapped[str | None] = mapped_column(String(64), nullable=True)
    previous: Mapped[str | None] = mapped_column(String(64), nullable=True)
    url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="forex_factory")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
