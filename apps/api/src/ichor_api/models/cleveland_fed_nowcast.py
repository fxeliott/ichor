"""cleveland_fed_nowcasts table — daily inflation nowcast snapshots.

Cleveland Fed publishes a daily nowcast of CPI / Core CPI / PCE / Core
PCE inflation across three horizons (MoM annualised, QoQ SAAR, YoY).
Each row is one (measure × horizon × target_period × revision_date)
observation.

Source: webcharts JSON endpoints discovered W72 audit.
License: US Federal Reserve publication, public domain.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, Float, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ClevelandFedNowcast(Base):
    """One Cleveland Fed inflation nowcast observation.

    Composite PK (id, revision_date) for TimescaleDB hypertable
    partitioning on revision_date. UniqueConstraint on
    (measure, horizon, target_period, revision_date) for app-level dedup.
    """

    __tablename__ = "cleveland_fed_nowcasts"
    __table_args__ = (
        UniqueConstraint(
            "measure",
            "horizon",
            "target_period",
            "revision_date",
            name="uq_cleveland_fed_nowcast_measure_horizon_target_revision",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    revision_date: Mapped[date] = mapped_column(Date, primary_key=True, index=True)

    measure: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    """One of: CPI, CoreCPI, PCE, CorePCE."""

    horizon: Mapped[str] = mapped_column(String(8), nullable=False)
    """One of: mom (month-over-month annualised), qoq (quarter-over-quarter
    SAAR), yoy (year-over-year)."""

    target_period: Mapped[date] = mapped_column(Date, nullable=False)
    """First day of the target month or quarter being nowcasted."""

    nowcast_value: Mapped[float] = mapped_column(Float, nullable=False)
    """Nowcast value, percent (annualised for mom/qoq, simple YoY otherwise)."""

    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
