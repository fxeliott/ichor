"""Smoke tests for the prediction-outlier CLI module."""

from __future__ import annotations

import pytest
from ichor_api.cli.run_prediction_outlier import _LOOKBACK_DAYS, _MIN_OBS


def test_lookback_long_enough_for_quarter() -> None:
    """90d window catches a Fed cycle's prediction drift."""
    assert _LOOKBACK_DAYS >= 60


def test_min_obs_floor() -> None:
    """30 obs is the conventional floor for std-based z-score."""
    assert _MIN_OBS >= 20


def test_module_imports() -> None:
    import importlib

    mod = importlib.import_module("ichor_api.cli.run_prediction_outlier")
    assert hasattr(mod, "run")
    assert hasattr(mod, "main")


def test_help_exits_cleanly() -> None:
    from ichor_api.cli.run_prediction_outlier import main

    with pytest.raises(SystemExit):
        main(["run_prediction_outlier", "--help"])
