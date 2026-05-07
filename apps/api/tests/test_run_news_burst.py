"""Smoke tests for the news-burst scanner."""

from __future__ import annotations

import pytest
from ichor_api.cli.run_news_burst_scan import (
    _BASELINE_HOURS,
    _BURST_WINDOW_MIN,
    _MIN_RAW_COUNT,
    _NEG_TONE_FLOOR,
)


def test_burst_window_is_5_minutes() -> None:
    assert _BURST_WINDOW_MIN == 5


def test_baseline_window_is_24h() -> None:
    """24h baseline is the conventional period to detect bursts."""
    assert _BASELINE_HOURS == 24


def test_negative_tone_floor_strict_enough() -> None:
    """Score < -0.5 = clearly negative (FinBERT scale [-1, 1])."""
    assert _NEG_TONE_FLOOR <= -0.5


def test_min_raw_count_floors_alert() -> None:
    """Avoid alerting on 1-2 outlier negatives in news-light periods."""
    assert _MIN_RAW_COUNT >= 3


def test_module_imports() -> None:
    import importlib

    mod = importlib.import_module("ichor_api.cli.run_news_burst_scan")
    assert hasattr(mod, "run")
    assert hasattr(mod, "main")


def test_help_exits_cleanly() -> None:
    from ichor_api.cli.run_news_burst_scan import main

    with pytest.raises(SystemExit):
        main(["run_news_burst_scan", "--help"])
