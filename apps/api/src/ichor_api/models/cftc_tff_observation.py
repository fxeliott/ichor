"""cftc_tff_observations table — CFTC TFF weekly positioning observations."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Date, DateTime, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class CftcTffObservation(Base):
    """One TFF row: 1 market × 1 weekly report = 1 row.

    Composite PK (id, report_date) for TimescaleDB hypertable on
    `report_date` (weekly cadence, ample headroom). UniqueConstraint
    on (report_date, market_code) for app-level dedup.

    All position fields are stored as BigInteger because some markets
    can have > 2 billion contracts in extreme regimes (especially
    Treasuries) and Postgres `Integer` only fits 2.1 B.
    """

    __tablename__ = "cftc_tff_observations"
    __table_args__ = (
        UniqueConstraint(
            "report_date",
            "market_code",
            name="uq_cftc_tff_report_date_market_code",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    report_date: Mapped[date] = mapped_column(Date, primary_key=True, index=True)

    market_code: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    market_name: Mapped[str] = mapped_column(String(200), nullable=False)
    commodity_name: Mapped[str] = mapped_column(String(64), nullable=False)

    open_interest: Mapped[int] = mapped_column(BigInteger, nullable=False)

    dealer_long: Mapped[int] = mapped_column(BigInteger, nullable=False)
    dealer_short: Mapped[int] = mapped_column(BigInteger, nullable=False)
    asset_mgr_long: Mapped[int] = mapped_column(BigInteger, nullable=False)
    asset_mgr_short: Mapped[int] = mapped_column(BigInteger, nullable=False)
    lev_money_long: Mapped[int] = mapped_column(BigInteger, nullable=False)
    lev_money_short: Mapped[int] = mapped_column(BigInteger, nullable=False)
    other_rept_long: Mapped[int] = mapped_column(BigInteger, nullable=False)
    other_rept_short: Mapped[int] = mapped_column(BigInteger, nullable=False)
    nonrept_long: Mapped[int] = mapped_column(BigInteger, nullable=False)
    nonrept_short: Mapped[int] = mapped_column(BigInteger, nullable=False)

    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
