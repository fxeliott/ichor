"""finra_short_volume table — daily Reg SHO off-exchange short volume.

Created by migration 0025. One row per (symbol, trade_date), keyed
to support time-series queries on a single symbol.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Date, DateTime, Float, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class FinraShortVolume(Base):
    """One day of off-exchange short-volume aggregates for a symbol."""

    __tablename__ = "finra_short_volume"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    trade_date: Mapped[date] = mapped_column(Date, primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    short_volume: Mapped[int | None] = mapped_column(BigInteger)
    short_exempt_volume: Mapped[int | None] = mapped_column(BigInteger)
    total_volume: Mapped[int | None] = mapped_column(BigInteger)
    short_pct: Mapped[float | None] = mapped_column(Float)
    """short_volume / total_volume, in [0, 1]. NULL if total_volume = 0."""

    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
