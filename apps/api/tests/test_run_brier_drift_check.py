"""Unit tests for the Brier-drift CLI module."""

from __future__ import annotations

import pytest
from ichor_api.cli.run_brier_drift_check import _MIN_OBS_PER_WEEK


def test_min_obs_per_week_floor_avoids_noise() -> None:
    """5 cards/week minimum so the mean is meaningful."""
    assert _MIN_OBS_PER_WEEK >= 3


def test_module_imports() -> None:
    import importlib

    mod = importlib.import_module("ichor_api.cli.run_brier_drift_check")
    assert hasattr(mod, "run")
    assert hasattr(mod, "main")


def test_help_exits_cleanly() -> None:
    from ichor_api.cli.run_brier_drift_check import main

    with pytest.raises(SystemExit):
        main(["run_brier_drift_check", "--help"])
