"""Smoke tests for the run_vpin_compute CLI module.

The actual VPIN math lives in packages/ml/microstructure/vpin and
has its own dedicated tests. Here we just verify the CLI module
imports clean + argparse defaults look sane.
"""

from __future__ import annotations

import importlib

import pytest


def test_module_imports() -> None:
    mod = importlib.import_module("ichor_api.cli.run_vpin_compute")
    assert hasattr(mod, "run")
    assert hasattr(mod, "main")
    assert hasattr(mod, "_LOOKBACK_HOURS")
    assert hasattr(mod, "_MIN_TICKS")


def test_default_lookback_is_reasonable() -> None:
    """4h is the Couche-2 News-NLP cadence — VPIN refreshes per cycle."""
    from ichor_api.cli.run_vpin_compute import _LOOKBACK_HOURS

    assert 1 <= _LOOKBACK_HOURS <= 24


def test_min_ticks_floor() -> None:
    """At 200 ticks/bucket, we need at least ~3 buckets for VPIN."""
    from ichor_api.cli.run_vpin_compute import _MIN_TICKS

    assert _MIN_TICKS >= 600


def test_help_exits_cleanly() -> None:
    from ichor_api.cli.run_vpin_compute import main

    with pytest.raises(SystemExit):
        main(["run_vpin_compute", "--help"])
