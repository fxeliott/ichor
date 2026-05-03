"""Tests for the feature engineering pipeline + LightGBM bias model.

Feature tests are pure-Python ; LightGBM tests are gated on the
optional lightgbm + numpy installs (skip cleanly if missing).
"""

from __future__ import annotations

import importlib.util
import math
import pathlib
import sys
from datetime import date, timedelta

import pytest

# Direct module import so we don't trigger ichor_ml.__init__ which pulls
# in heavy ML deps.
_FEATURES_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "src" / "ichor_ml" / "training" / "features.py"
)
_spec = importlib.util.spec_from_file_location(
    "ichor_ml_features_test", _FEATURES_PATH
)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)
build_features_daily = _mod.build_features_daily
BarLike = _mod.BarLike


def _bars(n: int, *, start_price: float = 1.0, drift: float = 0.0001) -> list[BarLike]:
    """Make a deterministic monotonic-drift series of bars."""
    bars = []
    cursor = date(2024, 1, 1)
    price = start_price
    for i in range(n):
        op = price
        cl = price * (1 + drift + 0.0005 * (i % 5 - 2))
        hi = max(op, cl) + 0.001
        lo = min(op, cl) - 0.001
        bars.append(BarLike(
            bar_date=cursor + timedelta(days=i),
            asset="EUR_USD",
            open=op,
            high=hi,
            low=lo,
            close=cl,
        ))
        price = cl
    return bars


def test_features_drops_first_n_and_last_bar() -> None:
    bars = _bars(120)
    rows = build_features_daily(bars, min_history=60)
    # 120 bars - 60 history - 1 last (no t+1) = 59 rows
    assert len(rows) == 59


def test_features_returns_empty_when_history_too_short() -> None:
    bars = _bars(50)
    rows = build_features_daily(bars, min_history=60)
    assert rows == []


def test_features_per_row_keys_are_complete() -> None:
    bars = _bars(150)
    rows = build_features_daily(bars)
    expected = {
        "returns_1d", "returns_5d", "returns_20d",
        "vol_5d", "vol_20d", "rsi_14",
        "macd_diff", "momentum_60d", "close_over_sma_50",
    }
    assert set(rows[0].features.keys()) == expected


def test_target_up_correct() -> None:
    bars = _bars(100)
    rows = build_features_daily(bars)
    for r in rows:
        i = next(idx for idx, b in enumerate(bars) if b.bar_date == r.bar_date)
        expected = 1 if bars[i + 1].close > bars[i].close else 0
        assert r.target_up == expected


def test_features_no_nan_no_inf() -> None:
    bars = _bars(200)
    rows = build_features_daily(bars)
    for r in rows:
        for k, v in r.features.items():
            assert math.isfinite(v), f"non-finite {k}={v} at {r.bar_date}"


def test_features_leakage_no_future_data() -> None:
    """For every row at bar t, features must be derivable from bars ≤ t.

    We assert this via construction : the only data passed to feature
    helpers is `bars[:i+1]` where i is the row index. Any future-leakage
    bug would show up as a feature value that depends on bars[i+1:].

    This regression test compares features computed on the FULL series
    vs features computed on the truncated series ending at bar t. They
    must match.
    """
    bars = _bars(150)
    full_rows = build_features_daily(bars)
    for r in full_rows:
        i = next(idx for idx, b in enumerate(bars) if b.bar_date == r.bar_date)
        truncated = build_features_daily(bars[: i + 2])  # +2: include t and t+1 for target
        # Find the same row in the truncated series
        match = next((tr for tr in truncated if tr.bar_date == r.bar_date), None)
        assert match is not None, f"missing row {r.bar_date} in truncated"
        for k in r.features:
            assert abs(r.features[k] - match.features[k]) < 1e-9, (
                f"feature {k} differs at {r.bar_date}: "
                f"full={r.features[k]} truncated={match.features[k]}"
            )


# ───────────────────────── LightGBM (optional) ─────────────────────────


lightgbm_available = importlib.util.find_spec("lightgbm") is not None


@pytest.mark.skipif(not lightgbm_available, reason="lightgbm not installed")
def test_lightgbm_train_runs_and_predicts() -> None:
    # Heavy import : only when LightGBM is installed
    sys.path.insert(0, str(_FEATURES_PATH.parent.parent.parent))
    from ichor_ml.training.lightgbm_bias import (  # type: ignore
        train_lightgbm_bias, FEATURE_NAMES,
    )

    bars = _bars(500)
    model = train_lightgbm_bias(bars, n_estimators=20)
    assert model.artifact.asset == "EUR_USD"
    assert model.artifact.feature_names == FEATURE_NAMES
    assert 0 <= model.artifact.train_brier <= 1.0
    # Predict on a synthetic feature row
    rows = build_features_daily(bars[-100:])
    p = model.predict_proba(rows[-1])
    assert 0.0 <= p <= 1.0


@pytest.mark.skipif(not lightgbm_available, reason="lightgbm not installed")
def test_lightgbm_refuses_with_too_few_rows() -> None:
    sys.path.insert(0, str(_FEATURES_PATH.parent.parent.parent))
    from ichor_ml.training.lightgbm_bias import train_lightgbm_bias  # type: ignore

    bars = _bars(70)  # just above min_history=60, but only ~9 rows
    with pytest.raises(ValueError):
        train_lightgbm_bias(bars)
