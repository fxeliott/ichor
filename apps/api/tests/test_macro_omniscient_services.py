"""Pure tests for confluence_engine + currency_strength + economic_calendar
+ yield_curve.

Tests the math + branching logic that doesn't require a live Postgres.
DB-backed factor builders are exercised in `test_data_pool.py` integration.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import pytest

from ichor_api.services.confluence_engine import (
    ConfluenceReport,
    Driver,
    _factor_daily_levels,
    render_confluence_block,
)
from ichor_api.services.daily_levels import DailyLevels
from ichor_api.services.economic_calendar import (
    CalendarEvent,
    CalendarReport,
    _next_recurring_date,
    filter_for_asset,
    render_calendar_block,
)
from ichor_api.services.yield_curve import (
    TenorPoint,
    YieldCurveReading,
    _shape,
    render_yield_curve_block,
)


# ─────────────────── confluence_engine — daily-levels factor ───────────


def _levels(spot: float, pdh: float = 1.0750, pdl: float = 1.0700) -> DailyLevels:
    return DailyLevels(
        asset="EUR_USD",
        spot=spot, pdh=pdh, pdl=pdl, pd_close=(pdh + pdl) / 2,
        asian_high=None, asian_low=None,
        weekly_high=None, weekly_low=None,
        pivot=None, r1=None, r2=None, r3=None, s1=None, s2=None, s3=None,
        round_levels=[],
    )


def test_daily_levels_factor_mid_range_returns_neutral_contribution() -> None:
    d = _factor_daily_levels("EUR_USD", _levels(1.0725))
    assert d is not None
    assert abs(d.contribution) < 0.05


def test_daily_levels_factor_near_pdh_returns_long_bias() -> None:
    d = _factor_daily_levels("EUR_USD", _levels(1.0748))
    assert d is not None
    assert d.contribution > 0.2


def test_daily_levels_factor_near_pdl_returns_short_bias() -> None:
    d = _factor_daily_levels("EUR_USD", _levels(1.0703))
    assert d is not None
    assert d.contribution < -0.2


def test_daily_levels_factor_swept_above_pdh_returns_short_reversal() -> None:
    d = _factor_daily_levels("EUR_USD", _levels(1.0760))
    assert d is not None
    assert d.contribution < 0
    assert "swept" in d.evidence.lower() or "above" in d.evidence.lower()


def test_daily_levels_factor_swept_below_pdl_returns_long_reversal() -> None:
    d = _factor_daily_levels("EUR_USD", _levels(1.0690))
    assert d is not None
    assert d.contribution > 0
    assert "swept" in d.evidence.lower() or "below" in d.evidence.lower()


def test_daily_levels_factor_returns_none_on_missing_data() -> None:
    d = _factor_daily_levels(
        "EUR_USD",
        DailyLevels(
            asset="EUR_USD",
            spot=None, pdh=None, pdl=None, pd_close=None,
            asian_high=None, asian_low=None,
            weekly_high=None, weekly_low=None,
            pivot=None, r1=None, r2=None, r3=None,
            s1=None, s2=None, s3=None,
            round_levels=[],
        ),
    )
    assert d is None


def test_render_confluence_block_renders_drivers() -> None:
    drivers = [
        Driver(
            factor="rate_diff",
            contribution=+0.30,
            evidence="US10Y - DE10Y = +1.50%",
            source="FRED:DGS10",
        ),
        Driver(
            factor="cot",
            contribution=-0.40,
            evidence="z=-0.80",
            source="CFTC:099741",
        ),
    ]
    r = ConfluenceReport(
        asset="EUR_USD",
        score_long=52.4,
        score_short=53.2,
        score_neutral=46.8,
        dominant_direction="neutral",
        confluence_count=0,
        drivers=drivers,
        rationale="2 drivers évalués",
    )
    md, sources = render_confluence_block(r)
    assert "EUR_USD" in md
    assert "Score LONG" in md
    assert "Drivers" in md
    assert "rate_diff" in md
    assert "FRED:DGS10" in sources


# ─────────────────── currency_strength (math is straightforward) ───────


# (the heavy lifting is DB-bound ; smoke-test would need fixtures.
# Pure-math sanity check : ensure exported helpers exist.)


def test_currency_strength_module_exports() -> None:
    from ichor_api.services import currency_strength as mod
    assert hasattr(mod, "assess_currency_strength")
    assert hasattr(mod, "render_currency_strength_block")
    assert hasattr(mod, "CurrencyStrengthReport")
    assert hasattr(mod, "CurrencyStrengthEntry")


# ─────────────────── economic_calendar ─────────────────────────────────


def test_next_recurring_date_same_month_if_day_in_future() -> None:
    today = date(2026, 5, 3)
    out = _next_recurring_date(today, 12)
    assert out == date(2026, 5, 12)


def test_next_recurring_date_rolls_to_next_month_if_day_passed() -> None:
    today = date(2026, 5, 20)
    out = _next_recurring_date(today, 12)
    assert out == date(2026, 6, 12)


def test_next_recurring_date_year_rollover() -> None:
    today = date(2026, 12, 30)
    out = _next_recurring_date(today, 12)
    assert out == date(2027, 1, 12)


def test_filter_for_asset_subsets_correctly() -> None:
    events = [
        CalendarEvent(
            when=date(2026, 5, 5),
            when_time_utc="13:30",
            region="US",
            label="NFP",
            impact="high",
            affected_assets=["EUR_USD", "USD_JPY"],
        ),
        CalendarEvent(
            when=date(2026, 5, 6),
            when_time_utc="11:00",
            region="UK",
            label="BoE",
            impact="high",
            affected_assets=["GBP_USD"],
        ),
    ]
    report = CalendarReport(
        generated_at=datetime.now(timezone.utc),
        horizon_days=14,
        events=events,
    )
    eur = filter_for_asset(report, "EUR_USD")
    assert len(eur) == 1
    assert eur[0].label == "NFP"

    gbp = filter_for_asset(report, "GBP_USD")
    assert len(gbp) == 1
    assert gbp[0].label == "BoE"

    nas = filter_for_asset(report, "NAS100_USD")
    assert nas == []


def test_render_calendar_empty_returns_friendly_message() -> None:
    report = CalendarReport(
        generated_at=datetime.now(timezone.utc),
        horizon_days=14,
        events=[],
    )
    md, sources = render_calendar_block(report, asset="EUR_USD")
    assert "Economic calendar" in md
    assert "no upcoming" in md.lower()
    assert sources == []


def test_render_calendar_with_events() -> None:
    events = [
        CalendarEvent(
            when=date(2026, 5, 7),
            when_time_utc="13:30",
            region="US",
            label="US CPI YoY",
            impact="high",
            affected_assets=["EUR_USD", "XAU_USD"],
            note="projected from FRED:CPIAUCSL",
            source="FRED:CPIAUCSL",
        ),
    ]
    report = CalendarReport(
        generated_at=datetime.now(timezone.utc),
        horizon_days=14,
        events=events,
    )
    md, sources = render_calendar_block(report, asset="EUR_USD")
    assert "US CPI YoY" in md
    assert "13:30" in md
    assert "HIGH" in md
    assert "FRED:CPIAUCSL" in sources


# ─────────────────── yield_curve shape detection ──────────────────────


def _tenor(label: str, y: float | None) -> TenorPoint:
    return TenorPoint(
        tenor_years=1.0,
        label=label,
        series_id="DGS_X",
        yield_pct=y,
        observation_date=datetime.now(timezone.utc),
    )


def test_shape_detects_fully_inverted() -> None:
    pts = [
        _tenor("3M", 5.5), _tenor("6M", 5.4), _tenor("1Y", 5.2),
        _tenor("2Y", 4.9), _tenor("5Y", 4.5), _tenor("10Y", 4.2),
        _tenor("30Y", 4.0),
    ]
    shape = _shape(pts, slope_2y_10y=-0.7)
    assert shape == "inverted_full"


def test_shape_detects_steep() -> None:
    pts = [
        _tenor("3M", 4.5), _tenor("6M", 4.6), _tenor("2Y", 4.7),
        _tenor("10Y", 6.5), _tenor("30Y", 7.0),
    ]
    shape = _shape(pts, slope_2y_10y=1.8)
    assert shape == "steep"


def test_shape_detects_inverted_short_segment() -> None:
    # Only one tenor pair inverted at the short end ; rest curve upward.
    # Need < (len - 2) inversions to avoid being classified inverted_full.
    pts = [
        _tenor("3M", 5.4), _tenor("6M", 5.0), _tenor("2Y", 5.1),
        _tenor("5Y", 5.2), _tenor("10Y", 5.3), _tenor("30Y", 5.5),
    ]
    shape = _shape(pts, slope_2y_10y=-0.3)
    assert shape == "inverted_short"


def test_shape_detects_normal() -> None:
    pts = [
        _tenor("3M", 4.0), _tenor("2Y", 4.3), _tenor("5Y", 4.5),
        _tenor("10Y", 4.7), _tenor("30Y", 5.0),
    ]
    shape = _shape(pts, slope_2y_10y=0.4)
    assert shape == "normal"


def test_shape_detects_flat() -> None:
    pts = [
        _tenor("3M", 4.0), _tenor("2Y", 4.05), _tenor("5Y", 4.1),
        _tenor("10Y", 4.15), _tenor("30Y", 4.18),
    ]
    shape = _shape(pts, slope_2y_10y=0.10)
    assert shape == "flat"


def test_render_yield_curve_no_data() -> None:
    r = YieldCurveReading(
        points=[],
        slope_3m_10y=None,
        slope_2y_10y=None,
        slope_5y_30y=None,
        real_yield_10y=None,
        inverted_segments=0,
        shape="flat",
        sources=[],
    )
    md, sources = render_yield_curve_block(r)
    assert "no fred yields" in md.lower()
    assert sources == []


def test_render_yield_curve_full_payload() -> None:
    r = YieldCurveReading(
        points=[
            _tenor("3M", 5.30), _tenor("2Y", 4.85),
            _tenor("10Y", 4.45), _tenor("30Y", 4.65),
        ],
        slope_3m_10y=-0.85,
        slope_2y_10y=-0.40,
        slope_5y_30y=+0.30,
        real_yield_10y=1.85,
        inverted_segments=2,
        shape="inverted_short",
        note="3M-10Y inverted",
        sources=["FRED:DGS10", "FRED:DGS2"],
    )
    md, sources = render_yield_curve_block(r)
    assert "shape: inverted_short" in md
    assert "Slope 3M-10Y" in md
    assert "Slope 2Y-10Y" in md
    assert "TIPS DFII10" in md
    assert "FRED:DGS10" in sources
