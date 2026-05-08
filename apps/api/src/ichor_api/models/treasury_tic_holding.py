"""treasury_tic_holdings table — monthly Major Foreign Holders snapshot."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, Float, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class TreasuryTicHolding(Base):
    """One country × month holdings snapshot from the TIC MFH report.

    Composite PK (id, observation_month) for TimescaleDB hypertable
    partitioning on observation_month. UniqueConstraint on
    (country, observation_month) for app-level dedup across multiple
    poll runs.
    """

    __tablename__ = "treasury_tic_holdings"
    __table_args__ = (
        UniqueConstraint(
            "country",
            "observation_month",
            name="uq_treasury_tic_country_month",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    observation_month: Mapped[date] = mapped_column(Date, primary_key=True, index=True)

    country: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    """Canonical country label as printed in the TIC MFH table."""

    holdings_bn_usd: Mapped[float] = mapped_column(Float, nullable=False)
    """End-of-period Treasury holdings in billions USD."""

    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
