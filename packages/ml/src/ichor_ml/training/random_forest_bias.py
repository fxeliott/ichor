"""Random Forest bias model — sklearn RandomForestClassifier wrapper.

Less sensitive to hyperparameter tuning than gradient-boosted ensembles ;
useful as an honest baseline + as one of the inputs to the Brier-weighted
ensemble in `ichor_ml.bias_aggregator`. We keep the interface symmetric
with `lightgbm_bias.py` and `xgboost_bias.py` so the caller can swap
learners with a single import change.

Reproducibility : `random_state=42` + single-thread (`n_jobs=1`).

ADR-017 boundary : returns probabilities, never BUY/SELL signals.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sklearn.ensemble import RandomForestClassifier

from .features import FEATURE_NAMES, BarLike, FeatureRow, build_features_daily

_MIN_TRAIN_ROWS = 30


@dataclass(frozen=True)
class RandomForestBiasArtifact:
    asset: str
    feature_names: tuple[str, ...]
    n_train_rows: int
    train_brier: float
    n_estimators: int
    max_depth: int | None
    min_samples_leaf: int


@dataclass
class RandomForestBiasModel:
    artifact: RandomForestBiasArtifact
    estimator: RandomForestClassifier = field(repr=False)

    def predict_proba(self, row: FeatureRow) -> float:
        """Return P(target_up == 1) ∈ [0, 1] for one feature row."""
        x = np.array(
            [[row.features[k] for k in self.artifact.feature_names]],
            dtype=np.float64,
        )
        # `predict_proba` returns shape (1, 2) ; column 1 is the
        # positive-class proba.
        proba = self.estimator.predict_proba(x)
        return float(proba[0, 1])


def _to_xy(rows: list[FeatureRow]) -> tuple[np.ndarray, np.ndarray]:
    x = np.array([[r.features[k] for k in FEATURE_NAMES] for r in rows], dtype=np.float64)
    y = np.array([r.target_up for r in rows], dtype=np.int32)
    return x, y


def _brier_score(probs: np.ndarray, targets: np.ndarray) -> float:
    if probs.size == 0:
        return 0.0
    return float(np.mean((probs - targets) ** 2))


def train_random_forest_bias(
    bars: list[BarLike],
    *,
    n_estimators: int = 200,
    max_depth: int | None = 8,
    min_samples_leaf: int = 5,
    min_history: int = 60,
) -> RandomForestBiasModel:
    """Train a Random Forest binary classifier on next-day direction.

    Default `max_depth=8` + `min_samples_leaf=5` are conservative anti-
    overfit choices for typical 1-3y daily bar histories (~250-750 rows).

    Raises:
        ValueError: empty bars list, or < `_MIN_TRAIN_ROWS` feature rows.
    """
    if not bars:
        raise ValueError("train_random_forest_bias: empty bars list")
    asset = bars[0].asset

    rows = build_features_daily(bars, min_history=min_history)
    if len(rows) < _MIN_TRAIN_ROWS:
        raise ValueError(
            f"train_random_forest_bias: need at least {_MIN_TRAIN_ROWS} feature rows, "
            f"got {len(rows)}"
        )

    x, y = _to_xy(rows)
    estimator = RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        min_samples_leaf=min_samples_leaf,
        random_state=42,
        n_jobs=1,
    )
    estimator.fit(x, y)

    train_probs = np.asarray(estimator.predict_proba(x)[:, 1], dtype=np.float64)
    train_brier = _brier_score(train_probs, y)

    artifact = RandomForestBiasArtifact(
        asset=asset,
        feature_names=FEATURE_NAMES,
        n_train_rows=len(rows),
        train_brier=train_brier,
        n_estimators=n_estimators,
        max_depth=max_depth,
        min_samples_leaf=min_samples_leaf,
    )
    return RandomForestBiasModel(artifact=artifact, estimator=estimator)


__all__ = [
    "FEATURE_NAMES",
    "RandomForestBiasArtifact",
    "RandomForestBiasModel",
    "train_random_forest_bias",
]
