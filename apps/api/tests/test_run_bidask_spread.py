"""Unit tests for the bid-ask spread monitor CLI."""

from __future__ import annotations

import pytest

from ichor_api.cli.run_bidask_spread_check import (
    _BASELINE_HOURS,
    _PIP_MULTIPLIER,
    _RECENT_MINUTES,
    _spread_pips,
)


def test_spread_pips_eurusd_canonical() -> None:
    """EUR/USD spread of 0.0001 = 1 pip."""
    assert _spread_pips("EURUSD", 1.0850, 1.0851) == pytest.approx(1.0, rel=1e-9)


def test_spread_pips_usdjpy_uses_2dp() -> None:
    """USD/JPY 0.01 = 1 pip (different multiplier)."""
    assert _spread_pips("USDJPY", 157.86, 157.89) == pytest.approx(3.0, rel=1e-9)


def test_spread_pips_xauusd_quoted_in_dollars() -> None:
    """Gold quoted $/oz, 1 pip = $0.10 → multiplier 1e1."""
    assert _spread_pips("XAUUSD", 2400.0, 2400.5) == pytest.approx(5.0, rel=1e-9)


def test_spread_pips_handles_unknown_asset_with_default() -> None:
    """Default multiplier 1e4 for unknown assets."""
    assert _spread_pips("NZDCHF", 0.5500, 0.5503) == pytest.approx(3.0, rel=1e-9)


def test_spread_pips_rejects_negative_inputs() -> None:
    assert _spread_pips("EURUSD", 0, 1.0) is None
    assert _spread_pips("EURUSD", 1.0, 0) is None
    assert _spread_pips("EURUSD", -1.0, 1.0) is None


def test_spread_pips_rejects_inverted_quote() -> None:
    """ask < bid is malformed (real venues never quote this)."""
    assert _spread_pips("EURUSD", 1.0851, 1.0850) is None


def test_baseline_4h_recent_5min_sane_ratio() -> None:
    """The baseline must be at least 12× the recent window so the
    z-score has a meaningful denominator."""
    assert (_BASELINE_HOURS * 60) >= _RECENT_MINUTES * 12


def test_pip_multipliers_cover_phase1_pairs() -> None:
    for pair in ("EURUSD", "GBPUSD", "USDJPY", "USDCAD", "AUDUSD", "XAUUSD"):
        assert pair in _PIP_MULTIPLIER, f"missing multiplier for {pair}"


def test_module_imports() -> None:
    import importlib

    mod = importlib.import_module("ichor_api.cli.run_bidask_spread_check")
    assert hasattr(mod, "run")


def test_help_exits_cleanly() -> None:
    from ichor_api.cli.run_bidask_spread_check import main

    with pytest.raises(SystemExit):
        main(["run_bidask_spread_check", "--help"])
