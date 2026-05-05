"""XGBoost bias model — companion to LightGBM, same training interface.

Mirrors `lightgbm_bias.py` so the bias_aggregator (Brier-weighted ensemble
in `ichor_ml.bias_aggregator`) can swap learners without rewriting the
caller. Differences worth noting :

  - XGBoost defaults to `binary:logistic` objective ; we keep `logloss`
    as the eval metric for parity with LightGBM.
  - Reproducibility relies on `seed` + single-thread + `tree_method=hist`
    (parallel-tree-split nondeterminism is the main repro-blocker).
  - In-sample Brier reported on the artifact ; weekly held-out Brier is
    the production calibration KPI.

ADR-017 boundary : returns probabilities, never BUY/SELL signals.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import xgboost as xgb

from .features import FEATURE_NAMES, BarLike, FeatureRow, build_features_daily

_MIN_TRAIN_ROWS = 30


@dataclass(frozen=True)
class XGBoostBiasArtifact:
    asset: str
    feature_names: tuple[str, ...]
    n_train_rows: int
    train_brier: float
    n_estimators: int
    learning_rate: float
    max_depth: int


@dataclass
class XGBoostBiasModel:
    artifact: XGBoostBiasArtifact
    booster: xgb.Booster = field(repr=False)

    def predict_proba(self, row: FeatureRow) -> float:
        """Return P(target_up == 1) ∈ [0, 1] for one feature row."""
        x = np.array(
            [[row.features[k] for k in self.artifact.feature_names]],
            dtype=np.float64,
        )
        dmat = xgb.DMatrix(x, feature_names=list(self.artifact.feature_names))
        raw = self.booster.predict(dmat)
        return float(raw[0])


def _to_xy(rows: list[FeatureRow]) -> tuple[np.ndarray, np.ndarray]:
    x = np.array([[r.features[k] for k in FEATURE_NAMES] for r in rows], dtype=np.float64)
    y = np.array([r.target_up for r in rows], dtype=np.int32)
    return x, y


def _brier_score(probs: np.ndarray, targets: np.ndarray) -> float:
    if probs.size == 0:
        return 0.0
    return float(np.mean((probs - targets) ** 2))


def train_xgboost_bias(
    bars: list[BarLike],
    *,
    n_estimators: int = 200,
    learning_rate: float = 0.05,
    max_depth: int = 6,
    min_history: int = 60,
) -> XGBoostBiasModel:
    """Train an XGBoost binary classifier on next-day direction.

    Raises:
        ValueError: empty bars list, or < `_MIN_TRAIN_ROWS` feature rows.
    """
    if not bars:
        raise ValueError("train_xgboost_bias: empty bars list")
    asset = bars[0].asset

    rows = build_features_daily(bars, min_history=min_history)
    if len(rows) < _MIN_TRAIN_ROWS:
        raise ValueError(
            f"train_xgboost_bias: need at least {_MIN_TRAIN_ROWS} feature rows, got {len(rows)}"
        )

    x, y = _to_xy(rows)
    dtrain = xgb.DMatrix(x, label=y, feature_names=list(FEATURE_NAMES))

    params: dict[str, object] = {
        "objective": "binary:logistic",
        "eval_metric": "logloss",
        "learning_rate": learning_rate,
        "max_depth": max_depth,
        "verbosity": 0,
        "seed": 42,
        "tree_method": "hist",
        "nthread": 1,
    }
    booster = xgb.train(params, dtrain, num_boost_round=n_estimators)

    train_probs = np.asarray(booster.predict(dtrain), dtype=np.float64)
    train_brier = _brier_score(train_probs, y)

    artifact = XGBoostBiasArtifact(
        asset=asset,
        feature_names=FEATURE_NAMES,
        n_train_rows=len(rows),
        train_brier=train_brier,
        n_estimators=n_estimators,
        learning_rate=learning_rate,
        max_depth=max_depth,
    )
    return XGBoostBiasModel(artifact=artifact, booster=booster)


__all__ = [
    "FEATURE_NAMES",
    "XGBoostBiasArtifact",
    "XGBoostBiasModel",
    "train_xgboost_bias",
]
