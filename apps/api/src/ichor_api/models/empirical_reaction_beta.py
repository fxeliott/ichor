"""empirical_reaction_betas — Engine 8 axis-4 +1 LEVEL DEPTH r160 foundation.

Per-(event_class, instrument) empirical reaction-beta storage : the |drift|bp
magnitude observed in a fixed pre-event window over an N-event history.
When a row exists for (event_class, instrument), Engine 8 reads p50_drift_bp
from here instead of `EVENT_CLASS_BASELINE_BP` literature_prior dict.

Historical-trace shape — one row per (event_class, instrument, computed_at).
Schema in `migrations/0053_empirical_reaction_betas.py`.

ADR refs : ADR-099 §Impl(r160) — Mission centrale Axis-4 +1 LEVEL DEPTH
foundation ; Pattern #17 formal DOCTRINE r159 graduates to empirical
calibration path here.
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


class EmpiricalReactionBeta(Base):
    """One empirical reaction-beta calibration snapshot per (event_class,
    instrument, window, computed_at).

    `p50_drift_bp` / `p75_drift_bp` / `p90_drift_bp` are absolute-value
    magnitudes (sign stripped at this layer per ADR-017 boundary + r142
    trader RED-1 doctrine). The Engine 8 caller applies business_cycle_sign
    downstream — same architecture as the literature_prior fallback path.

    The DB enforces invariants via CHECK constraints (n_observations >= 1 ;
    monotonic p50 <= p75 <= p90 ; window endpoints positive). A violation
    at INSERT time fails-loud rather than silently corrupting Engine 8
    magnitude output.

    Historical trail is NOT truncated by future backfill recomputes — keeps
    the audit surface needed for Eliot to see calibration drift over time
    (Pattern #17 formal DOCTRINE r159 ; Mission centrale Axis-4). The
    latest-per-(event_class, instrument) query uses the
    `ix_empirical_reaction_betas_class_instrument_computed_at_desc`
    compound index.

    methodology stamps : window_minutes_before + window_minutes_after
    explicitly record the event-window methodology (e.g., r161+ ABDV-2003
    canonical 5min-pre + 0min-post — Andersen, Bollerslev, Diebold & Vega
    2003, *American Economic Review* 93(1):38-62, DOI
    10.1257/000282803321455151). Future r170+ granularity refinements
    (1-min vs 5-min) recorded directly in the row without schema migration.
    """

    __tablename__ = "empirical_reaction_betas"
    __table_args__ = (
        UniqueConstraint(
            "event_class",
            "instrument",
            "window_minutes_before",
            "window_minutes_after",
            "computed_at",
            name="uq_empirical_reaction_betas_full_key",
        ),
        CheckConstraint(
            "n_observations >= 1",
            name="ck_empirical_reaction_betas_sample_positive",
        ),
        CheckConstraint(
            "p50_drift_bp >= 0",
            name="ck_empirical_reaction_betas_p50_nonneg",
        ),
        CheckConstraint(
            "p75_drift_bp >= p50_drift_bp",
            name="ck_empirical_reaction_betas_p75_monotonic",
        ),
        CheckConstraint(
            "p90_drift_bp >= p75_drift_bp",
            name="ck_empirical_reaction_betas_p90_monotonic",
        ),
        CheckConstraint(
            "window_minutes_before >= 1",
            name="ck_empirical_reaction_betas_window_before_min",
        ),
        CheckConstraint(
            "window_minutes_after >= 0",
            name="ck_empirical_reaction_betas_window_after_nonneg",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    event_class: Mapped[str] = mapped_column(String(64), nullable=False)
    instrument: Mapped[str] = mapped_column(String(32), nullable=False)
    window_minutes_before: Mapped[int] = mapped_column(Integer, nullable=False)
    window_minutes_after: Mapped[int] = mapped_column(Integer, nullable=False)
    n_observations: Mapped[int] = mapped_column(Integer, nullable=False)
    p50_drift_bp: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False)
    p75_drift_bp: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False)
    p90_drift_bp: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
