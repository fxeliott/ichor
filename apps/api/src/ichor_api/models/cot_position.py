"""cot_positions table — weekly CFTC Disaggregated Futures Only."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class CotPosition(Base):
    """One weekly CFTC Disaggregated Futures Only row for one market.

    Composite PK (id, report_date) for TimescaleDB hypertable.
    Net columns are (longs - shorts) per trader category.
    """

    __tablename__ = "cot_positions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    report_date: Mapped[date] = mapped_column(Date, primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    market_code: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    market_name: Mapped[str | None] = mapped_column(String(128))
    producer_net: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    swap_dealer_net: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    managed_money_net: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    other_reportable_net: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    non_reportable_net: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    open_interest: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
