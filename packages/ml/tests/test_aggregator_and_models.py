"""Smoke tests for the ML scaffold — verify imports + minimal happy paths."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ichor_ml.bias_aggregator import AggregatorConfig, BiasAggregator
from ichor_ml.regime import HMMRegimeDetector
from ichor_ml.types import Prediction
from ichor_ml.vol import HARRVModel


def test_imports_all_packages() -> None:
    """If this passes, the package layout + __init__ exports are sane."""
    from ichor_ml import __version__
    from ichor_ml.microstructure import VPINEstimator
    from ichor_ml.nlp import score_tone  # noqa: F401

    assert __version__ == "0.0.0"
    assert VPINEstimator is not None


def test_hmm_fits_synthetic_regime_data() -> None:
    rng = np.random.default_rng(0)
    # Build 2-regime synthetic series: 100 low-vol + 100 high-vol
    low = rng.normal(0, 0.5, size=(100, 3))
    high = rng.normal(0, 2.5, size=(100, 3))
    features = np.vstack([low, high])

    det = HMMRegimeDetector(n_states=2, n_iter=100, random_state=42)
    det.fit(features)
    res = det.predict(features)

    assert res.states.shape == (200,)
    assert res.state_probs.shape == (200, 2)
    # State assignment in second half should be mostly state 1 (high vol)
    high_assign_pct = (res.states[100:] == 1).mean()
    assert high_assign_pct > 0.6


def test_har_rv_fits_and_predicts() -> None:
    # 100 days of synthetic RV (positive, with some persistence)
    rng = np.random.default_rng(1)
    rv = pd.Series(
        np.abs(rng.normal(0.01, 0.005, size=100)).cumsum() / np.arange(1, 101) * 0.5,
        index=pd.date_range("2025-01-01", periods=100),
    )
    model = HARRVModel()
    model.fit(rv)
    pred = model.predict()

    assert pred.next_day_rv > 0
    assert pred.next_week_rv > 0
    assert pred.next_month_rv > 0
    assert pred.confidence_band_low[0] < pred.next_day_rv < pred.confidence_band_high[0]


def test_aggregator_combines_two_models() -> None:
    preds = [
        Prediction(
            model_id="m1", model_family="lightgbm", asset="EUR_USD",
            horizon_hours=24, direction="long", raw_score=0.7,
            calibrated_probability=0.65,
            feature_snapshot_hash="h1",
        ),
        Prediction(
            model_id="m2", model_family="xgboost", asset="EUR_USD",
            horizon_hours=24, direction="long", raw_score=0.6,
            calibrated_probability=0.60,
            feature_snapshot_hash="h2",
        ),
    ]
    weights = {"lightgbm": 0.18, "xgboost": 0.20}

    agg = BiasAggregator(AggregatorConfig(min_models_required=2))
    sig = agg.aggregate(preds, asset="EUR_USD", horizon_hours=24, brier_weights=weights)

    assert sig is not None
    assert sig.direction == "long"
    assert 0.6 <= sig.probability <= 0.7
    assert len(sig.contributing_predictions) == 2


def test_aggregator_returns_none_when_too_few_models() -> None:
    preds = [
        Prediction(
            model_id="m1", model_family="lightgbm", asset="EUR_USD",
            horizon_hours=24, direction="long", raw_score=0.6,
            calibrated_probability=0.55,
            feature_snapshot_hash="h",
        ),
    ]
    agg = BiasAggregator(AggregatorConfig(min_models_required=2))
    sig = agg.aggregate(preds, asset="EUR_USD", horizon_hours=24, brier_weights={"lightgbm": 0.2})
    assert sig is None
