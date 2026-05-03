"""LightGBM bias model — first end-to-end model on real data.

Trained per asset, per-fold. Output : calibrated probability that
the next bar closes higher than the current bar.

Calibration : isotonic regression on the training-fold predictions
(fit-on-train, apply-on-test — no cross-fold leakage).

Plays nicely with `packages/backtest/runner.run_backtest` :

```python
from ichor_ml.training.lightgbm_bias import train_lightgbm_bias
from ichor_backtest import run_backtest

def predict_fn(train_bars, fold):
    return train_lightgbm_bias(train_bars, predict_dates=test_dates_in(fold))

run_backtest(bars, predict_fn, cfg)
```
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Sequence

from .features import BarLike, FeatureRow, build_features_daily


FEATURE_NAMES = [
    "returns_1d",
    "returns_5d",
    "returns_20d",
    "vol_5d",
    "vol_20d",
    "rsi_14",
    "macd_diff",
    "momentum_60d",
    "close_over_sma_50",
]


@dataclass
class LightGBMBiasArtifact:
    """Saveable model state."""

    asset: str
    feature_names: list[str]
    booster_text: str
    """LightGBM booster.model_to_string() output."""

    isotonic_x: list[float]
    """Isotonic calibration breakpoints (sorted ascending)."""
    isotonic_y: list[float]
    """Isotonic calibration values at breakpoints."""

    train_n: int
    train_brier: float
    """Brier on training set after calibration. Sanity check only."""

    metadata: dict[str, str] = field(default_factory=dict)


def _train_isotonic(probs: Sequence[float], targets: Sequence[int]) -> tuple[list[float], list[float]]:
    """Pool Adjacent Violators isotonic regression.

    Returns (x_breakpoints, y_values) suitable for piecewise-constant
    interpolation. Pure-Python — no sklearn dep.
    """
    if not probs:
        return [], []
    pairs = sorted(zip(probs, targets), key=lambda x: x[0])
    xs = [p for p, _ in pairs]
    ys = [float(t) for _, t in pairs]
    weights = [1.0] * len(ys)

    # PAV
    i = 0
    while i < len(ys) - 1:
        if ys[i] <= ys[i + 1]:
            i += 1
            continue
        # Pool
        new_y = (ys[i] * weights[i] + ys[i + 1] * weights[i + 1]) / (weights[i] + weights[i + 1])
        new_w = weights[i] + weights[i + 1]
        ys[i] = new_y
        weights[i] = new_w
        del ys[i + 1]
        del weights[i + 1]
        del xs[i + 1]
        if i > 0:
            i -= 1
    return xs, ys


def _apply_isotonic(prob: float, xs: Sequence[float], ys: Sequence[float]) -> float:
    """Piecewise-constant interpolation with edge clamping."""
    if not xs:
        return prob
    if prob <= xs[0]:
        return ys[0]
    if prob >= xs[-1]:
        return ys[-1]
    # Linear interp between adjacent breakpoints
    for i in range(len(xs) - 1):
        if xs[i] <= prob <= xs[i + 1]:
            x0, x1 = xs[i], xs[i + 1]
            y0, y1 = ys[i], ys[i + 1]
            if x1 == x0:
                return y0
            return y0 + (y1 - y0) * (prob - x0) / (x1 - x0)
    return ys[-1]


@dataclass
class LightGBMBiasModel:
    """In-memory wrapper around a LightGBM booster + isotonic calibrator."""

    artifact: LightGBMBiasArtifact

    def predict_proba(self, feature_row: FeatureRow) -> float:
        """Return the calibrated P(up) for the row's features."""
        import lightgbm as lgb

        booster = lgb.Booster(model_str=self.artifact.booster_text)
        x = [[feature_row.features[name] for name in self.artifact.feature_names]]
        raw = float(booster.predict(x)[0])
        return _apply_isotonic(raw, self.artifact.isotonic_x, self.artifact.isotonic_y)


def _brier(probs: Sequence[float], targets: Sequence[int]) -> float:
    if not probs:
        return 0.0
    return sum((p - t) ** 2 for p, t in zip(probs, targets)) / len(probs)


def train_lightgbm_bias(
    bars: Sequence[BarLike],
    *,
    num_leaves: int = 31,
    learning_rate: float = 0.05,
    n_estimators: int = 200,
    min_data_in_leaf: int = 20,
    seed: int = 42,
) -> LightGBMBiasModel:
    """Train one LightGBM bias model on the given bars.

    Returns a LightGBMBiasModel ready to call predict_proba on a
    FeatureRow. Caller is responsible for not feeding it future data
    (use the leakage guard at the backtest runner level).
    """
    import lightgbm as lgb
    import numpy as np

    rows = build_features_daily(bars)
    if len(rows) < 50:
        raise ValueError(
            f"Not enough feature rows to train: {len(rows)} (need ≥ 50). "
            "Increase the bar history or lower min_history in build_features_daily."
        )

    X = np.array(
        [[r.features[name] for name in FEATURE_NAMES] for r in rows],
        dtype=np.float64,
    )
    y = np.array([r.target_up for r in rows], dtype=np.int32)

    train_ds = lgb.Dataset(X, label=y, feature_name=FEATURE_NAMES)
    params = {
        "objective": "binary",
        "metric": "binary_logloss",
        "verbose": -1,
        "num_leaves": num_leaves,
        "learning_rate": learning_rate,
        "min_data_in_leaf": min_data_in_leaf,
        "feature_fraction": 0.9,
        "bagging_fraction": 0.9,
        "bagging_freq": 5,
        "seed": seed,
    }
    booster = lgb.train(params, train_ds, num_boost_round=n_estimators)

    raw_train = booster.predict(X).tolist()
    iso_x, iso_y = _train_isotonic(raw_train, y.tolist())
    calibrated = [_apply_isotonic(p, iso_x, iso_y) for p in raw_train]
    train_brier = _brier(calibrated, y.tolist())

    artifact = LightGBMBiasArtifact(
        asset=bars[0].asset if bars else "",
        feature_names=FEATURE_NAMES,
        booster_text=booster.model_to_string(),
        isotonic_x=iso_x,
        isotonic_y=iso_y,
        train_n=len(rows),
        train_brier=train_brier,
        metadata={
            "num_leaves": str(num_leaves),
            "learning_rate": str(learning_rate),
            "n_estimators": str(n_estimators),
            "seed": str(seed),
        },
    )
    return LightGBMBiasModel(artifact=artifact)
