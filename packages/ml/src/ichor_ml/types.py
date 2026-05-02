"""Pydantic schemas shared across ML modules.

These are the canonical types written to the `predictions_audit` Postgres
table (see Phase 0 W2 step 17) and consumed by the Bias Aggregator + UI.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

AssetCode = Literal[
    "EUR_USD", "XAU_USD", "NAS100_USD", "USD_JPY", "SPX500_USD",
    "GBP_USD", "AUD_USD", "USD_CAD",
]

Direction = Literal["long", "short", "neutral"]


class Prediction(BaseModel):
    """A single model's prediction at a point in time, before aggregation."""

    prediction_id: UUID = Field(default_factory=uuid4)
    model_id: str  # e.g. "lightgbm-v0.3-eurusd-1h"
    model_family: Literal[
        "lightgbm", "xgboost", "random_forest", "logistic_reg",
        "bayesian_numpyro", "mlp_torch", "hmm", "har_rv", "vpin",
        "finbert_tone", "fomc_roberta",
    ]
    asset: AssetCode
    horizon_hours: int = Field(ge=1, le=168)
    """Forecast horizon in hours (1h, 6h, 24h, 168h=1w typical)."""

    direction: Direction
    raw_score: float
    """Pre-calibration model output (probability or signed return)."""
    calibrated_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    """Post-isotonic-calibration probability of `direction` materializing."""

    feature_snapshot_hash: str
    """SHA256 of the feature vector used. Enables exact reproduction."""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BiasSignal(BaseModel):
    """Output of the Bias Aggregator — Brier-weighted ensemble of N models."""

    aggregator_run_id: UUID = Field(default_factory=uuid4)
    asset: AssetCode
    horizon_hours: int

    direction: Direction
    probability: float = Field(ge=0.0, le=1.0)
    """Calibrated ensemble probability."""

    credible_interval_low: float = Field(ge=0.0, le=1.0)
    credible_interval_high: float = Field(ge=0.0, le=1.0)
    """80% CI (10th & 90th percentiles of bootstrap distribution)."""

    contributing_predictions: list[UUID] = Field(min_length=1)
    """Foreign keys into Prediction. Audit trail."""

    weights_snapshot: dict[str, float]
    """Brier-weight applied to each model_family at this run."""

    notes: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ModelCard(BaseModel):
    """Lightweight model card per AUDIT_V3 §4.7 compliance requirement."""

    model_id: str
    model_family: str
    intended_use: str
    training_data_window: str  # e.g. "2010-01-01 to 2026-04-30"
    target_label: str
    eval_metric: str  # e.g. "Brier score 0.18"
    known_failure_modes: list[str]
    last_recalibrated: datetime
    license: str
    owner: str = "Eliot Delahousse"
