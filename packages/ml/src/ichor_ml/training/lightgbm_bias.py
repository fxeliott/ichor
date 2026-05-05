"""LightGBM bias model — binary classifier for next-day direction.

The trainer consumes the 9-feature daily pipeline from `features.py` and
fits a LightGBM gradient-boosted classifier on the `target_up` column
(1 = next bar's close > today's close, 0 = otherwise).

Usage :
    bars = await load_market_data_bars("EUR_USD", years=5)
    model = train_lightgbm_bias(bars, n_estimators=200)
    proba_up = model.predict_proba(latest_feature_row)
    # → [0.0, 1.0] probability that tomorrow closes above today's close

Calibration : the trainer reports `train_brier` (in-sample Brier score)
on the artifact ; production should refit weekly and track Brier on the
held-out next 7 days as part of the post-mortem reconciliation.

ADR-017 boundary : this model produces a PROBABILITY, never a "BUY/SELL"
signal. The brain pipeline can use it as one input among many in the
confluence engine ; the user retains discretionary authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import lightgbm as lgb
import numpy as np

from .features import FEATURE_NAMES, BarLike, FeatureRow, build_features_daily

# Minimum rows post feature-engineering to attempt a fit. Below this we
# refuse rather than overfit a tiny series.
_MIN_TRAIN_ROWS = 30


@dataclass(frozen=True)
class LightGBMBiasArtifact:
    """Everything needed to reproduce + audit a fit.

    The fitted model is held by the wrapping `LightGBMBiasModel` ; the
    artifact captures only inputs / metadata so it can be persisted +
    diffed cheaply.
    """

    asset: str
    feature_names: tuple[str, ...]
    n_train_rows: int
    train_brier: float
    """In-sample Brier score on the training set (sanity check, not a
    generalization metric — use weekly held-out evals for that)."""
    n_estimators: int
    learning_rate: float
    max_depth: int


@dataclass
class LightGBMBiasModel:
    """Wrapper exposing artifact + predict_proba on a single feature row."""

    artifact: LightGBMBiasArtifact
    booster: lgb.Booster = field(repr=False)

    def predict_proba(self, row: FeatureRow) -> float:
        """Return P(target_up == 1) ∈ [0, 1] for one feature row."""
        x = np.array(
            [[row.features[k] for k in self.artifact.feature_names]],
            dtype=np.float64,
        )
        raw = self.booster.predict(x)
        # LightGBM with `binary` objective returns the positive-class proba.
        return float(raw[0])


def _to_xy(rows: list[FeatureRow]) -> tuple[np.ndarray, np.ndarray]:
    x = np.array(
        [[r.features[k] for k in FEATURE_NAMES] for r in rows],
        dtype=np.float64,
    )
    y = np.array([r.target_up for r in rows], dtype=np.int32)
    return x, y


def _brier_score(probs: np.ndarray, targets: np.ndarray) -> float:
    """Mean (p - y)² ∈ [0, 1]. Smaller = better."""
    if probs.size == 0:
        return 0.0
    return float(np.mean((probs - targets) ** 2))


def train_lightgbm_bias(
    bars: list[BarLike],
    *,
    n_estimators: int = 200,
    learning_rate: float = 0.05,
    max_depth: int = -1,
    num_leaves: int = 31,
    min_history: int = 60,
) -> LightGBMBiasModel:
    """Train a LightGBM binary classifier on next-day direction.

    Args:
        bars: chronological daily OHLC bars for one asset.
        n_estimators: number of boosting iterations.
        learning_rate: shrinkage applied to each tree's contribution.
        max_depth: -1 = unlimited (controlled by num_leaves instead).
        num_leaves: max leaves per tree (LightGBM's primary capacity knob).
        min_history: minimum bars before the first feature row (default 60
            to support `momentum_60d`).

    Raises:
        ValueError: if fewer than `_MIN_TRAIN_ROWS` feature rows can be
            built — refusing here is safer than overfitting a tiny series.

    Returns:
        Fitted `LightGBMBiasModel` carrying the booster + artifact.
    """
    if not bars:
        raise ValueError("train_lightgbm_bias: empty bars list")
    asset = bars[0].asset

    rows = build_features_daily(bars, min_history=min_history)
    if len(rows) < _MIN_TRAIN_ROWS:
        raise ValueError(
            f"train_lightgbm_bias: need at least {_MIN_TRAIN_ROWS} feature rows, "
            f"got {len(rows)} (extend `bars` history)"
        )

    x, y = _to_xy(rows)
    dataset = lgb.Dataset(x, label=y, feature_name=list(FEATURE_NAMES))

    params: dict[str, object] = {
        "objective": "binary",
        "metric": "binary_logloss",
        "learning_rate": learning_rate,
        "num_leaves": num_leaves,
        "max_depth": max_depth,
        "verbose": -1,
        # Deterministic so re-runs of train_lightgbm_bias are reproducible
        # for the same `bars` input.
        "feature_fraction_seed": 42,
        "bagging_seed": 42,
        "data_random_seed": 42,
        "deterministic": True,
    }
    booster = lgb.train(params, dataset, num_boost_round=n_estimators)

    train_probs = np.asarray(booster.predict(x), dtype=np.float64)
    train_brier = _brier_score(train_probs, y)

    artifact = LightGBMBiasArtifact(
        asset=asset,
        feature_names=FEATURE_NAMES,
        n_train_rows=len(rows),
        train_brier=train_brier,
        n_estimators=n_estimators,
        learning_rate=learning_rate,
        max_depth=max_depth,
    )
    return LightGBMBiasModel(artifact=artifact, booster=booster)


__all__ = [
    "FEATURE_NAMES",
    "LightGBMBiasArtifact",
    "LightGBMBiasModel",
    "train_lightgbm_bias",
]
