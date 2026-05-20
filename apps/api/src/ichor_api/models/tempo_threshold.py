"""tempo_thresholds — Mission centrale Axis-7 auto-recalibration sink.

Per-asset absolute daily-range bp thresholds for the tempo_label classification
in `<TodaySessionPulse>`. Historical-trace shape (one row per (asset, computed_at)).
Schema in `migrations/0051_tempo_thresholds.py`.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class TempoThreshold(Base):
    """One recalibration snapshot of the per-asset tempo thresholds.

    `breakout_bp` / `active_bp` / `trending_bp` / `range_bound_bp` map to
    p90 / p75 / p50 / p25 of the daily-range distribution over the
    `window_days` rolling window of `polygon_intraday` for `asset`. The
    DB enforces the monotonic ordering via CHECK constraints
    (`breakout >= active >= trending >= range_bound >= 0`) — a violation
    at INSERT time fails-loud rather than silently corrupting the live
    label classifier.

    The historical trail is *not* truncated by the cron — keeps the audit
    surface needed for Eliot to see threshold drift over time (Mission
    centrale Axis-7). The latest-per-asset query uses the
    `ix_tempo_thresholds_asset_computed_at_desc` compound index.
    """

    __tablename__ = "tempo_thresholds"
    __table_args__ = (
        UniqueConstraint("asset", "computed_at", name="uq_tempo_thresholds_asset_computed_at"),
        CheckConstraint(
            "breakout_bp >= active_bp",
            name="ck_tempo_thresholds_monotonic_breakout",
        ),
        CheckConstraint(
            "active_bp >= trending_bp",
            name="ck_tempo_thresholds_monotonic_active",
        ),
        CheckConstraint(
            "trending_bp >= range_bound_bp",
            name="ck_tempo_thresholds_monotonic_trending",
        ),
        CheckConstraint(
            "range_bound_bp >= 0",
            name="ck_tempo_thresholds_nonneg",
        ),
        CheckConstraint(
            "sample_size >= 1",
            name="ck_tempo_thresholds_sample_positive",
        ),
        CheckConstraint(
            "window_days >= 7",
            name="ck_tempo_thresholds_window_min",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    asset: Mapped[str] = mapped_column(String(16), nullable=False)
    breakout_bp: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    active_bp: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    trending_bp: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    range_bound_bp: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
