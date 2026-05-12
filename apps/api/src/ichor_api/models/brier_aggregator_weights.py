"""brier_aggregator_weights — Phase D W115 Vovk-Zhdanov AA pockets.

One row per `(asset, regime, expert_kind, pocket_version)`. Mutable :
`update()` rewrites `weight`, `n_observations`, `cumulative_loss`,
`updated_at` on every Vovk nightly step. Audit lives in
`auto_improvement_log` (immutable).

Schema details + rationale in `migrations/0043_brier_aggregator_weights.py`.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Float, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class BrierAggregatorWeight(Base):
    """One Vovk-AA expert weight inside one `(asset, regime,
    pocket_version)` pocket."""

    __tablename__ = "brier_aggregator_weights"
    __table_args__ = (
        CheckConstraint(
            "weight >= 0.0 AND weight <= 1.0",
            name="ck_brier_agg_weight_unit_interval",
        ),
        CheckConstraint(
            "n_observations >= 0",
            name="ck_brier_agg_n_observations_nonneg",
        ),
        CheckConstraint(
            "cumulative_loss >= 0.0",
            name="ck_brier_agg_cumulative_loss_nonneg",
        ),
        CheckConstraint(
            "pocket_version >= 1",
            name="ck_brier_agg_pocket_version_positive",
        ),
        UniqueConstraint(
            "asset",
            "regime",
            "expert_kind",
            "pocket_version",
            name="uq_brier_agg_pocket_expert",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    asset: Mapped[str] = mapped_column(String(16), nullable=False)
    regime: Mapped[str] = mapped_column(String(64), nullable=False)
    expert_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    n_observations: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    cumulative_loss: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("0.0")
    )
    pocket_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )
