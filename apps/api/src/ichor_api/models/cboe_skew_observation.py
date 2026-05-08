"""cboe_skew_observations table — daily CBOE SKEW Index closes."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, Float, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class CboeSkewObservation(Base):
    """One daily CBOE SKEW reading.

    Composite PK (id, observation_date) for TimescaleDB hypertable
    partitioning on observation_date. UniqueConstraint on
    observation_date alone for app-level dedup (one row per day).
    """

    __tablename__ = "cboe_skew_observations"
    __table_args__ = (
        UniqueConstraint(
            "observation_date",
            name="uq_cboe_skew_observation_date",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    observation_date: Mapped[date] = mapped_column(Date, primary_key=True, index=True)

    skew_value: Mapped[float] = mapped_column(Float, nullable=False)
    """SKEW index level. 100 = neutral; >130 = elevated tail risk."""

    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
