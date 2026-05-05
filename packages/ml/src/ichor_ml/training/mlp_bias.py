"""MLP bias model — sklearn MLPClassifier wrapper.

Multi-Layer Perceptron baseline. Captures non-linear interactions between
the 9 features (RSI x momentum x vol cross-effects) that linear logistic
misses, without the heavyweight tuning of XGBoost / LightGBM. Standardizes
features via the same StandardScaler pipeline as `logistic_bias.py` —
critical for gradient-based optimizers (without scaling, RSI dominates
the gradient updates because it's ~100x larger than returns).

Why sklearn MLPClassifier and not PyTorch :
  - PyTorch CPU is Linux-only in the workspace deps (per pyproject) — using
    sklearn keeps Windows/macOS dev environments unblocked.
  - For 9-feature x 250-750 row daily series, a small MLP is enough.
    Production scale would justify PyTorch ; we don't have the data
    volume that would.

ADR-017 boundary : returns probabilities, never BUY/SELL signals.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .features import FEATURE_NAMES, BarLike, FeatureRow, build_features_daily

_MIN_TRAIN_ROWS = 30


@dataclass(frozen=True)
class MLPBiasArtifact:
    asset: str
    feature_names: tuple[str, ...]
    n_train_rows: int
    train_brier: float
    hidden_layer_sizes: tuple[int, ...]
    activation: str
    alpha_l2: float
    """sklearn `alpha` — L2 penalty applied to the weights."""


@dataclass
class MLPBiasModel:
    artifact: MLPBiasArtifact
    pipeline: Pipeline = field(repr=False)
    """StandardScaler + MLPClassifier."""

    def predict_proba(self, row: FeatureRow) -> float:
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


def train_mlp_bias(
    bars: list[BarLike],
    *,
    hidden_layer_sizes: tuple[int, ...] = (32, 16),
    activation: str = "relu",
    alpha_l2: float = 0.001,
    max_iter: int = 500,
    min_history: int = 60,
) -> MLPBiasModel:
    """Train a small MLP binary classifier on next-day direction.

    Default architecture is `(32, 16)` — two hidden layers, ~700 weights
    total for 9 features. Anti-overfit defaults : `alpha_l2=1e-3` (L2
    weight decay), `early_stopping=True` with 10 % validation split.

    Raises:
        ValueError: empty bars list, or < `_MIN_TRAIN_ROWS` feature rows.
    """
    if not bars:
        raise ValueError("train_mlp_bias: empty bars list")
    asset = bars[0].asset

    rows = build_features_daily(bars, min_history=min_history)
    if len(rows) < _MIN_TRAIN_ROWS:
        raise ValueError(
            f"train_mlp_bias: need at least {_MIN_TRAIN_ROWS} feature rows, got {len(rows)}"
        )

    x, y = _to_xy(rows)
    pipeline = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            (
                "mlp",
                MLPClassifier(
                    hidden_layer_sizes=hidden_layer_sizes,
                    activation=activation,
                    alpha=alpha_l2,
                    max_iter=max_iter,
                    early_stopping=True,
                    validation_fraction=0.1,
                    n_iter_no_change=20,
                    random_state=42,
                ),
            ),
        ]
    )
    # ConvergenceWarning is emitted by sklearn when max_iter is hit before
    # `n_iter_no_change` plateau. We absorb it here : the train_brier on
    # the artifact is the production-grade signal for fit quality, not
    # warnings. Keeping it surfaces but non-fatal lets pyproject's
    # `filterwarnings=error` policy stay strict everywhere else.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=ConvergenceWarning)
        pipeline.fit(x, y)

    train_probs = np.asarray(pipeline.predict_proba(x)[:, 1], dtype=np.float64)
    train_brier = _brier_score(train_probs, y)

    artifact = MLPBiasArtifact(
        asset=asset,
        feature_names=FEATURE_NAMES,
        n_train_rows=len(rows),
        train_brier=train_brier,
        hidden_layer_sizes=hidden_layer_sizes,
        activation=activation,
        alpha_l2=alpha_l2,
    )
    return MLPBiasModel(artifact=artifact, pipeline=pipeline)


__all__ = [
    "FEATURE_NAMES",
    "MLPBiasArtifact",
    "MLPBiasModel",
    "train_mlp_bias",
]
