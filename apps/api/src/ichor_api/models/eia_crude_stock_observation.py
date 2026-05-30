"""eia_crude_stocks — ADR-107 (EIA weekly petroleum crude stocks).

Weekly US petroleum inventory levels (thousand barrels) from EIA
OpenData v2 `petroleum/stoc/wstk`. Feeds the theme_classifier
`supply_demand` driver (Eliot Fathom transcript étape 1) : a large
weekly inventory swing (build or draw) at/above the 80th percentile of
its rolling 365-day window marks a supply/demand-driven regime.
Schema in `migrations/0054_eia_crude_stocks.py`.

ADR-017 boundary : descriptive physical-balance context, NEVER a
trade signal. A crude build > expected is bearish for oil — a
context input, not an order.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Date, DateTime, Numeric, Text, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class EiaCrudeStockObservation(Base):
    """One weekly EIA petroleum-stock reading for one series.

    Composite PK ``(series_id, observation_date)`` : EIA publishes
    several weekly stock series (``WCESTUS1`` crude ending stocks,
    ``WCRSTUS1`` commercial crude, ``WTTSTUS1`` total products) — one
    row per (series, week). ``observation_date`` is part of the PK
    because TimescaleDB requires the partition column to appear in any
    unique index.

    ``value`` is the inventory level in thousand barrels (kbbl),
    nullable because EIA can publish empty cells ; CHECK clamps to
    ``>= 0`` (a negative inventory is impossible — a parse error).
    """

    __tablename__ = "eia_crude_stocks"
    __table_args__ = (
        CheckConstraint(
            "value IS NULL OR value >= 0",
            name="ck_eia_crude_value_nonneg",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, default=uuid4)
    series_id: Mapped[str] = mapped_column(Text, primary_key=True, nullable=False)
    observation_date: Mapped[date] = mapped_column(Date, primary_key=True, nullable=False)
    value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
