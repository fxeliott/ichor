"""Unit tests for the ADWIN concept-drift CLI module."""

from __future__ import annotations

import pytest
from ichor_api.cli.run_concept_drift import (
    _LOOKBACK_DAYS,
    _MIN_OBS_FOR_FIT,
    _RECENT_WINDOW,
)


def test_lookback_long_enough_for_quarterly_drift() -> None:
    """90d catches drift on the timescale of a Fed cycle."""
    assert _LOOKBACK_DAYS >= 60


def test_min_obs_for_fit_floor() -> None:
    """ADWIN needs >> 30 obs to establish baseline ; 30 is the floor."""
    assert _MIN_OBS_FOR_FIT >= 30


def test_recent_window_short_enough_to_be_actionable() -> None:
    """Drift on the last 100 obs is too historical ; 5-15 obs = the
    recent regime change."""
    assert 5 <= _RECENT_WINDOW <= 20


def test_module_imports() -> None:
    import importlib

    mod = importlib.import_module("ichor_api.cli.run_concept_drift")
    assert hasattr(mod, "run")
    assert hasattr(mod, "main")


def test_help_exits_cleanly() -> None:
    from ichor_api.cli.run_concept_drift import main

    with pytest.raises(SystemExit):
        main(["run_concept_drift", "--help"])
