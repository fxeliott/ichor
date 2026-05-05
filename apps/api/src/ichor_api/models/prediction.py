"""predictions_audit table — every model output, for backtesting + Brier calibration.

Per AUDIT_V3 §4.7 — the auditability mandate. NEVER delete rows; partition by
date instead (TimescaleDB hypertable).

Composite primary key (id, generated_at) is required by TimescaleDB:
the partitioning column must be part of the PK.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Prediction(Base, TimestampMixin):
    __tablename__ = "predictions_audit"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,  # TimescaleDB requires partition col in PK
        default=lambda: datetime.now(UTC),
        index=True,
    )

    model_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    model_family: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    asset: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    horizon_hours: Mapped[int] = mapped_column(Integer, nullable=False)

    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    raw_score: Mapped[float] = mapped_column(Float, nullable=False)
    calibrated_probability: Mapped[float | None] = mapped_column(Float)

    feature_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    realized_direction: Mapped[str | None] = mapped_column(String(8))
    realized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    brier_contribution: Mapped[float | None] = mapped_column(Float)
