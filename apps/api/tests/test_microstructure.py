"""Pure tests for the microstructure service math."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ichor_api.services.microstructure import (
    IntradayBar,
    MicrostructureReading,
    amihud,
    kyles_lambda,
    realized_vol_pct,
    render_microstructure_block,
    value_area,
    vwap,
)


def _bar(
    close: float, volume: float, *, high: float | None = None, low: float | None = None
) -> IntradayBar:
    return IntradayBar(
        ts=datetime(2026, 5, 4, tzinfo=UTC),
        open=close,
        high=high if high is not None else close,
        low=low if low is not None else close,
        close=close,
        volume=volume,
    )


# ─────────────────────────── amihud ────────────────────────────────────


def test_amihud_returns_none_on_empty() -> None:
    assert amihud([]) is None


def test_amihud_returns_none_on_single_bar() -> None:
    assert amihud([_bar(1.0, 100)]) is None


def test_amihud_zero_volume_skipped() -> None:
    bars = [_bar(1.0, 0), _bar(1.01, 0)]
    assert amihud(bars) is None


def test_amihud_basic_positive() -> None:
    bars = [
        _bar(1.0, 100),
        _bar(1.01, 100),
        _bar(0.99, 100),
        _bar(1.005, 100),
    ]
    val = amihud(bars)
    assert val is not None and val > 0


def test_amihud_higher_for_thinner_market() -> None:
    """Same returns, smaller volume → higher illiquidity."""
    thin = [_bar(1.0, 10), _bar(1.01, 10), _bar(0.99, 10)]
    deep = [_bar(1.0, 1000), _bar(1.01, 1000), _bar(0.99, 1000)]
    assert amihud(thin) > amihud(deep)  # type: ignore[operator]


# ─────────────────────────── kyles_lambda ──────────────────────────────


def test_kyles_lambda_returns_none_on_short_window() -> None:
    assert kyles_lambda([_bar(1.0, 100)] * 3) is None


def test_kyles_lambda_zero_when_no_volume_variation() -> None:
    """Same volume on every bar → no signal in signed_volume → lambda
    is degenerate."""
    bars = [_bar(1.0 + 0.01 * i, 100) for i in range(10)]
    val = kyles_lambda(bars)
    # When all signed volumes are equal, variance is 0 → returns None
    assert val is None


def test_kyles_lambda_positive_when_buys_lift_price() -> None:
    """Constructed series where up-ticks coincide with high volume."""
    bars = [
        _bar(1.000, 100),
        _bar(1.005, 200),
        _bar(1.010, 300),
        _bar(1.015, 400),
        _bar(1.020, 500),
    ]
    val = kyles_lambda(bars)
    assert val is not None and val > 0


# ─────────────────────────── realized_vol ──────────────────────────────


def test_realized_vol_returns_none_on_too_few_bars() -> None:
    assert realized_vol_pct([_bar(1.0, 100)]) is None


def test_realized_vol_zero_on_constant_price() -> None:
    bars = [_bar(1.0, 100) for _ in range(10)]
    val = realized_vol_pct(bars)
    assert val == pytest.approx(0.0)


def test_realized_vol_positive_on_movement() -> None:
    bars = [_bar(1.0 + 0.005 * (i % 2), 100) for i in range(20)]
    val = realized_vol_pct(bars)
    assert val is not None and val > 0


# ─────────────────────────── vwap ──────────────────────────────────────


def test_vwap_returns_none_on_zero_volume_only() -> None:
    bars = [_bar(1.0, 0)]
    assert vwap(bars) is None


def test_vwap_equals_typical_price_on_constant_bars() -> None:
    bars = [_bar(1.0, 100) for _ in range(5)]
    assert vwap(bars) == pytest.approx(1.0)


def test_vwap_weights_by_volume() -> None:
    """Big volume on price=2 should pull VWAP toward 2."""
    bars = [_bar(1.0, 1), _bar(2.0, 1000)]
    val = vwap(bars)
    assert val is not None and val > 1.99


# ─────────────────────────── value_area ────────────────────────────────


def test_value_area_returns_nones_on_empty() -> None:
    assert value_area([]) == (None, None, None)


def test_value_area_collapses_on_constant_price() -> None:
    bars = [_bar(1.0, 100) for _ in range(5)]
    poc, lo, hi = value_area(bars)
    assert poc == pytest.approx(1.0)
    assert lo == pytest.approx(1.0)
    assert hi == pytest.approx(1.0)


def test_value_area_poc_near_high_volume_cluster() -> None:
    bars = (
        [_bar(1.0 + 0.01 * i, 1) for i in range(10)]  # spread thin
        + [_bar(1.05, 1000) for _ in range(5)]  # cluster
    )
    poc, lo, hi = value_area(bars)
    assert poc is not None and abs(poc - 1.05) < 0.05
    assert lo is not None and hi is not None
    assert lo <= poc <= hi


# ─────────────────────────── render_block ──────────────────────────────


def test_render_block_no_bars() -> None:
    r = MicrostructureReading(
        asset="EUR_USD",
        n_bars=0,
        window_minutes=240,
        amihud_illiquidity=None,
        kyles_lambda=None,
        realized_vol_pct=None,
        vwap=None,
        poc=None,
        value_area_low=None,
        value_area_high=None,
    )
    md, sources = render_microstructure_block(r)
    assert "no bars" in md.lower()
    assert sources == []


def test_render_block_with_data_includes_sources() -> None:
    r = MicrostructureReading(
        asset="EUR_USD",
        n_bars=120,
        window_minutes=240,
        amihud_illiquidity=1.234e-9,
        kyles_lambda=2.5e-7,
        realized_vol_pct=8.4,
        vwap=1.1734,
        poc=1.1735,
        value_area_low=1.1729,
        value_area_high=1.1740,
    )
    md, sources = render_microstructure_block(r)
    assert "EUR_USD" in md
    assert "Amihud" in md
    assert "Kyle" in md
    assert "VWAP" in md
    assert "POC" in md
    assert sources == ["polygon_intraday:EUR_USD@last240min"]
