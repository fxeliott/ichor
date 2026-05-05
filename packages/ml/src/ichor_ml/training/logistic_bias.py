"""Logistic Regression bias model — sklearn LogisticRegression wrapper.

Linear baseline. The simplest model in the ensemble, and the one that
often dominates when the data has a clean linear separability axis (e.g.
"high momentum + positive macro = up"). Standardizes features via
`StandardScaler` to put all 9 dimensions on a comparable scale (RSI is
~0-100 while returns are ~±0.01 — without scaling, regularization is
dominated by RSI).

Probabilities are well-calibrated by construction (logistic link
function is the inverse of the log-odds), but we still report in-sample
Brier on the artifact for symmetry with the tree models.

ADR-017 boundary : returns probabilities, never BUY/SELL signals.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .features import FEATURE_NAMES, BarLike, FeatureRow, build_features_daily

_MIN_TRAIN_ROWS = 30


@dataclass(frozen=True)
class LogisticBiasArtifact:
    asset: str
    feature_names: tuple[str, ...]
    n_train_rows: int
    train_brier: float
    c_inverse_regularization: float
    """sklearn's `C` parameter — inverse of L2 regularization strength."""


@dataclass
class LogisticBiasModel:
    artifact: LogisticBiasArtifact
    pipeline: Pipeline = field(repr=False)
    """Pipeline = StandardScaler + LogisticRegression."""

    def predict_proba(self, row: FeatureRow) -> float:
        """Return P(target_up == 1) ∈ [0, 1] for one feature row."""
        x = np.array(
            [[row.features[k] for k in self.artifact.feature_names]],
            dtype=np.float64,
        )
        proba = self.pipeline.predict_proba(x)
        return float(proba[0, 1])


def _to_xy(rows: list[FeatureRow]) -> tuple[np.ndarray, np.ndarray]:
    x = np.array([[r.features[k] for k in FEATURE_NAMES] for r in rows], dtype=np.float64)
    y = np.array([r.target_up for r in rows], dtype=np.int32)
    return x, y


def _brier_score(probs: np.ndarray, targets: np.ndarray) -> float:
    if probs.size == 0:
        return 0.0
    return float(np.mean((probs - targets) ** 2))


def train_logistic_bias(
    bars: list[BarLike],
    *,
    c_inverse_regularization: float = 1.0,
    min_history: int = 60,
) -> LogisticBiasModel:
    """Train a logistic regression binary classifier on next-day direction.

    Args:
        c_inverse_regularization: sklearn `C` — smaller = stronger L2.
            1.0 is sklearn's default ; 0.1 if features show overfit.
        min_history: minimum bars before the first feature row.

    Raises:
        ValueError: empty bars list, or < `_MIN_TRAIN_ROWS` feature rows.
    """
    if not bars:
        raise ValueError("train_logistic_bias: empty bars list")
    asset = bars[0].asset

    rows = build_features_daily(bars, min_history=min_history)
    if len(rows) < _MIN_TRAIN_ROWS:
        raise ValueError(
            f"train_logistic_bias: need at least {_MIN_TRAIN_ROWS} feature rows, got {len(rows)}"
        )

    x, y = _to_xy(rows)
    pipeline = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            (
                "logreg",
                LogisticRegression(
                    C=c_inverse_regularization,
                    solver="lbfgs",
                    max_iter=1000,
                    random_state=42,
                ),
            ),
        ]
    )
    pipeline.fit(x, y)

    train_probs = np.asarray(pipeline.predict_proba(x)[:, 1], dtype=np.float64)
    train_brier = _brier_score(train_probs, y)

    artifact = LogisticBiasArtifact(
        asset=asset,
        feature_names=FEATURE_NAMES,
        n_train_rows=len(rows),
        train_brier=train_brier,
        c_inverse_regularization=c_inverse_regularization,
    )
    return LogisticBiasModel(artifact=artifact, pipeline=pipeline)


__all__ = [
    "FEATURE_NAMES",
    "LogisticBiasArtifact",
    "LogisticBiasModel",
    "train_logistic_bias",
]
