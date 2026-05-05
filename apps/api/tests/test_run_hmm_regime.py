"""Smoke tests for the HMM regime detection CLI."""

from __future__ import annotations

import pytest

from ichor_api.cli.run_hmm_regime import (
    WATCHED_ASSETS,
    _LOOKBACK_DAYS,
    _MIN_DAYS_FOR_FIT,
    _STATE_LABELS,
)


def test_3_state_labels_canonical() -> None:
    assert _STATE_LABELS[0] == "low_vol_trend"
    assert _STATE_LABELS[1] == "high_vol_trend"
    assert _STATE_LABELS[2] == "mean_revert"


def test_lookback_safe_floor() -> None:
    """HMM EM convergence is shaky on <30 obs ; 60d lookback is safe."""
    assert _LOOKBACK_DAYS >= _MIN_DAYS_FOR_FIT * 2


def test_watched_assets_match_har_rv_universe() -> None:
    """HMM and HAR-RV must run on the same universe so the brain can
    consume both signals per asset without fallback."""
    from ichor_api.cli.run_har_rv import WATCHED_ASSETS as HAR_RV_ASSETS

    assert set(WATCHED_ASSETS) == set(HAR_RV_ASSETS)


def test_module_imports() -> None:
    import importlib

    mod = importlib.import_module("ichor_api.cli.run_hmm_regime")
    assert hasattr(mod, "run")


def test_help_exits_cleanly() -> None:
    from ichor_api.cli.run_hmm_regime import main

    with pytest.raises(SystemExit):
        main(["run_hmm_regime", "--help"])
