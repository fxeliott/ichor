"""fred_observations table — daily/weekly FRED series observations."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, Float, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class FredObservation(Base):
    """One observation of one FRED series.

    Composite PK (id, observation_date) for TimescaleDB hypertable
    partitioning on `observation_date`.
    """

    __tablename__ = "fred_observations"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    observation_date: Mapped[date] = mapped_column(
        Date, primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    series_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    value: Mapped[float | None] = mapped_column(Float)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
