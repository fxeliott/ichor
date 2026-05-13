"""estr_observations — ADR-090 P0 step-4 (€STR Euro Short-Term Rate).

Daily €STR (volume-weighted trimmed mean rate) from ECB Data Portal
SDMX flow `EST/B.EU000A2X2A25.WT`. Schema in
`migrations/0048_estr_observations.py`.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Date, DateTime, Numeric, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class EstrObservation(Base):
    """One daily €STR rate reading.

    `observation_date` is the natural primary key (one row per
    business day — ECB publishes on TARGET business days only).
    `rate_pct` is in PROZENT (% direct), not basis points. CHECK
    constraint clamps to [-1.5, +10.0] — historical extremes around
    -0.62% (2021 ECB QE peak) and +4.0% (2023 hiking peak).
    """

    __tablename__ = "estr_observations"
    __table_args__ = (
        UniqueConstraint("observation_date", name="uq_estr_observation_date"),
        CheckConstraint(
            "rate_pct BETWEEN -1.5 AND 10.0",
            name="ck_estr_rate_range",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, default=uuid4)
    observation_date: Mapped[date] = mapped_column(Date, primary_key=True, nullable=False)
    rate_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
