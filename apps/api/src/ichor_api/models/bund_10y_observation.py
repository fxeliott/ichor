"""bund_10y_observations — ADR-090 P0 step-1 (EUR_USD data-pool extension).

Daily Bund 10Y yield from Bundesbank SDMX flow
`BBSIS/D.I.ZAR.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A`. Schema in
`migrations/0046_bund_10y_observations.py`.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Date, DateTime, Numeric, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class BundYieldObservation(Base):
    """One daily Bund 10Y yield reading.

    `observation_date` is the natural primary key (one row per trading
    day). `yield_pct` is in PROZENT (% direct), not basis points. The
    CHECK constraint clamps to [-2.0, +10.0] — historical extremes
    -0.85% (Q3 2020) and +9.5% (1981).
    """

    __tablename__ = "bund_10y_observations"
    __table_args__ = (
        UniqueConstraint("observation_date", name="uq_bund_10y_observation_date"),
        CheckConstraint(
            "yield_pct BETWEEN -2.0 AND 10.0",
            name="ck_bund_10y_yield_range",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, default=uuid4)
    observation_date: Mapped[date] = mapped_column(Date, primary_key=True, nullable=False)
    yield_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
