"""nyfed_mct_observations table — monthly NY Fed Multivariate Core Trend.

Captures the NY Fed Multivariate Core Trend Inflation (MCT) decomposition,
a dynamic-factor estimate of persistent inflation trend across 17 PCE
sectors. Used by Ichor to triangulate the Fed's likely reaction function
versus headline / core PCE prints (which are noisier).

Source: https://www.newyorkfed.org/medialibrary/Research/Interactives/Data/mct/mct-chart-data.csv
License: US Federal Reserve publication, public domain.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, Float, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class NyfedMctObservation(Base):
    """One monthly NY Fed MCT observation.

    Composite PK (id, observation_month) for TimescaleDB hypertable
    partitioning. UniqueConstraint on observation_month for app-level
    dedup across multiple poll runs.
    """

    __tablename__ = "nyfed_mct_observations"
    __table_args__ = (
        UniqueConstraint(
            "observation_month",
            name="uq_nyfed_mct_observation_month",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    observation_month: Mapped[date] = mapped_column(Date, primary_key=True, index=True)

    mct_trend_pct: Mapped[float] = mapped_column(Float, nullable=False)
    """MCT central trend annualised inflation (PCE basis), percent."""

    headline_pce_yoy: Mapped[float | None] = mapped_column(Float, nullable=True)
    """Headline PCE YoY inflation, percent. Realised, not nowcast."""

    core_pce_yoy: Mapped[float | None] = mapped_column(Float, nullable=True)
    """Core PCE YoY inflation (ex food + energy), percent."""

    goods_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    """MCT trend contribution from Goods sector, percent."""

    services_ex_housing_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    """MCT trend contribution from Services ex. housing, percent."""

    housing_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    """MCT trend contribution from Housing sector, percent."""

    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
