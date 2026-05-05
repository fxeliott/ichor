"""Pure-function tests for ml_signals.py compute helpers.

The async adapters need an AsyncSession so they're covered in integration
tests. These tests cover the sync compute paths that are dispatched via
`asyncio.to_thread`. Skips gracefully if `[ml]` extras aren't installed.
"""

from __future__ import annotations

import importlib.util

import pytest
from ichor_api.services.ml_signals import (
    MlSignal,
    _adwin_compute,
    _harrv_compute,
    _hmm_compute,
)

ML_INSTALLED = (
    importlib.util.find_spec("ichor_ml") is not None
    and importlib.util.find_spec("hmmlearn") is not None
    and importlib.util.find_spec("river") is not None
)
needs_ml = pytest.mark.skipif(not ML_INSTALLED, reason="ichor_ml [ml] extras not installed")


# ──────────────────────── MlSignal dataclass ─────────────────────────


def test_mlsignal_default_status_is_ok() -> None:
    s = MlSignal(name="x", value="y")
    assert s.status == "ok"
    assert s.horizon is None


def test_mlsignal_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    s = MlSignal(name="x", value="y")
    with pytest.raises(FrozenInstanceError):
        s.value = "z"  # type: ignore[misc]


# ──────────────────────────── _hmm_compute ───────────────────────────


@needs_ml
def test_hmm_compute_returns_state_and_prob_on_synthetic_returns() -> None:
    import random

    rng = random.Random(42)  # noqa: S311 — synthetic test data, not crypto
    # 200 fake daily returns: a calm regime then a vol spike then back.
    rets = (
        [rng.gauss(0.0, 0.005) for _ in range(80)]
        + [rng.gauss(0.0, 0.025) for _ in range(60)]
        + [rng.gauss(0.0, 0.005) for _ in range(60)]
    )
    out = _hmm_compute(rets)
    assert out is not None, "HMM compute returned None on 200-obs synthetic series"
    state, prob, converged = out
    assert state in (0, 1, 2)
    assert 0.0 <= prob <= 1.0
    assert isinstance(converged, bool)


def test_hmm_compute_returns_none_on_short_series() -> None:
    # 10 obs is way under the 60 threshold.
    out = _hmm_compute([0.001] * 10)
    assert out is None


# ─────────────────────────── _harrv_compute ──────────────────────────


@needs_ml
def test_harrv_compute_returns_three_horizons() -> None:
    import random

    rng = random.Random(7)  # noqa: S311 — synthetic test data, not crypto
    rets = [rng.gauss(0.0, 0.01) for _ in range(120)]
    out = _harrv_compute(rets)
    assert out is not None
    h1, h5, h22 = out
    # All annualized vols should be small positive numbers (< 5 = 500%).
    assert 0.0 < h1 < 5.0
    assert 0.0 < h5 < 5.0
    assert 0.0 < h22 < 5.0


def test_harrv_compute_returns_none_on_short_series() -> None:
    out = _harrv_compute([0.001] * 20)
    assert out is None


# ─────────────────────────── _adwin_compute ──────────────────────────


@needs_ml
def test_adwin_compute_no_drift_on_constant_series() -> None:
    out = _adwin_compute([0.10] * 200)
    assert out is not None
    drift, idx = out
    assert drift is False
    assert idx is None


@needs_ml
def test_adwin_compute_detects_drift_on_step_change() -> None:
    # 100 obs at 0.05 then 100 obs at 0.50 — drastic step.
    series = [0.05] * 100 + [0.50] * 100
    out = _adwin_compute(series)
    assert out is not None
    drift, idx = out
    assert drift is True
    assert idx is not None and idx >= 100  # drift detected after the step
