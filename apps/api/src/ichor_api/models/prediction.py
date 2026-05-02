"""predictions_audit table — every model output, for backtesting + Brier calibration.

Per AUDIT_V3 §4.7 — the auditability mandate. NEVER delete rows; partition by
date instead (TimescaleDB hypertable).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Prediction(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "predictions_audit"

    model_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    """Matches model_registry.yaml id, e.g. 'lightgbm-bias-eurusd-1h-v0'."""

    model_family: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    """lightgbm | xgboost | random_forest | logistic_reg | bayesian_numpyro |
        mlp_torch | hmm | har_rv | vpin | finbert_tone | fomc_roberta"""

    asset: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    horizon_hours: Mapped[int] = mapped_column(Integer, nullable=False)

    # Prediction
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    """long | short | neutral"""

    raw_score: Mapped[float] = mapped_column(Float, nullable=False)
    calibrated_probability: Mapped[float | None] = mapped_column(Float)

    # Reproducibility
    feature_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    """SHA256 of the feature vector. Allows exact re-prediction."""

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    # Realized outcome (filled later when horizon closes)
    realized_direction: Mapped[str | None] = mapped_column(String(8))
    realized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    brier_contribution: Mapped[float | None] = mapped_column(Float)
    """(predicted_prob - realized_outcome)^2; lower = better."""
