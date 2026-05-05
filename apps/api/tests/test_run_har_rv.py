"""Smoke tests for run_har_rv CLI module + the daily-RV aggregator."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from ichor_api.cli.run_har_rv import (
    WATCHED_ASSETS,
    _LOOKBACK_DAYS,
    _MIN_DAYS_FOR_FIT,
    _daily_rv_from_bars,
)


def test_watched_assets_covers_phase1_universe() -> None:
    assert "EUR_USD" in WATCHED_ASSETS
    assert "XAU_USD" in WATCHED_ASSETS
    assert len(WATCHED_ASSETS) == 8  # ADR-017 Phase 1


def test_lookback_at_least_har_rv_minimum() -> None:
    """HAR-RV needs ≥ 30 daily obs ; we lookback 60 to survive
    weekends + holidays."""
    assert _LOOKBACK_DAYS >= _MIN_DAYS_FOR_FIT * 2


def _ts(year, month, day, hour=12, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def test_daily_rv_aggregates_squared_log_returns() -> None:
    """3 ticks per day for 2 days → 2 daily RV values."""
    rows = [
        (_ts(2026, 5, 1, 0, 0), 100.0),
        (_ts(2026, 5, 1, 12, 0), 101.0),
        (_ts(2026, 5, 1, 23, 30), 100.5),
        (_ts(2026, 5, 2, 0, 30), 100.5),
        (_ts(2026, 5, 2, 12, 0), 102.0),
        (_ts(2026, 5, 2, 23, 30), 101.0),
    ]
    out = _daily_rv_from_bars(rows)
    assert len(out) == 2
    # Each RV is sqrt of sum of squared log returns intraday — must be > 0
    for d, rv in out:
        assert rv > 0


def test_daily_rv_handles_empty_input() -> None:
    assert _daily_rv_from_bars([]) == []


def test_daily_rv_skips_invalid_closes() -> None:
    """Negative or zero closes get filtered."""
    rows = [
        (_ts(2026, 5, 1, 0, 0), 100.0),
        (_ts(2026, 5, 1, 1, 0), 0.0),  # invalid
        (_ts(2026, 5, 1, 2, 0), -1.0),  # invalid
        (_ts(2026, 5, 1, 3, 0), 101.0),
    ]
    out = _daily_rv_from_bars(rows)
    assert len(out) == 1
    assert out[0][1] > 0
