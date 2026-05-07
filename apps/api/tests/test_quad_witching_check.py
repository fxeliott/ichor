"""Tests for services/quad_witching_check.py."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from ichor_api.services import quad_witching_check as svc


def test_third_friday_known_2026_dates():
    # Known quad-witching Fridays for 2026:
    # March 20, June 19, September 18, December 18 (per CME/CBOE calendar).
    assert svc._third_friday(2026, 3) == date(2026, 3, 20)
    assert svc._third_friday(2026, 6) == date(2026, 6, 19)
    assert svc._third_friday(2026, 9) == date(2026, 9, 18)
    assert svc._third_friday(2026, 12) == date(2026, 12, 18)


def test_third_friday_january_2027_known():
    # Cross-year sanity: January 2027 third Friday = January 15.
    assert svc._third_friday(2027, 1) == date(2027, 1, 15)


def test_next_quad_witching_today_is_first_of_march():
    today = date(2026, 3, 1)
    assert svc.next_quad_witching(today) == date(2026, 3, 20)


def test_next_quad_witching_today_is_quad_witching_day():
    today = date(2026, 3, 20)
    # The 3rd Friday IS today — should still return that day (>= today).
    assert svc.next_quad_witching(today) == date(2026, 3, 20)


def test_next_quad_witching_after_march_returns_june():
    today = date(2026, 3, 21)
    assert svc.next_quad_witching(today) == date(2026, 6, 19)


def test_next_quad_witching_late_december_rolls_to_march_next_year():
    today = date(2026, 12, 19)
    assert svc.next_quad_witching(today) == date(2027, 3, 19)


def test_next_opex_january_2026_third_friday():
    # 3rd Friday of January 2026 = January 16.
    assert svc.next_opex(date(2026, 1, 1)) == date(2026, 1, 16)


def test_next_opex_after_third_friday_rolls_to_next_month():
    today = date(2026, 1, 17)  # day after 3rd Friday
    assert svc.next_opex(today) == date(2026, 2, 20)


def test_next_opex_december_rolls_to_january_next_year():
    today = date(2026, 12, 19)  # day after Dec 3rd Friday (Dec 18)
    assert svc.next_opex(today) == date(2027, 1, 15)


@pytest.mark.asyncio
async def test_evaluate_inside_quad_window_fires_alert(monkeypatch):
    # March 16, 2026 (Monday) → quad-witching is March 20 (Friday) = T-4
    captured: list[dict[str, Any]] = []

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_quad_witching_proximity(
        None, persist=True, today=date(2026, 3, 16)
    )
    assert result.is_quad_witching_window is True
    assert result.quad_witching_alert_fired is True
    assert result.days_to_quad == 4

    # That same date is also pre-OPEX (3rd Friday of March = Mar 20 = the same as quad).
    # Per the OPEX_FLOOR_DAYS=2 rule, T-4 is OUTSIDE the OPEX window (which is T-2 through T-0).
    assert result.is_opex_window is False
    assert result.opex_alert_fired is False

    # 1 quad alert fired, no OPEX alert.
    assert len(captured) == 1
    assert captured[0]["metric_name"] == "quad_witching_t_minus"
    assert captured[0]["asset"] == "SPX500_USD"
    assert captured[0]["extra_payload"]["event_type"] == "quad_witching"
    assert captured[0]["extra_payload"]["source"] == "calendar:third_friday"


@pytest.mark.asyncio
async def test_evaluate_inside_opex_window_only(monkeypatch):
    # February 19, 2026 (Thursday) → next OPEX = Feb 20 = T-1
    # Quad-witching is March 20 = T-29 (way outside window)
    captured: list[dict[str, Any]] = []

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_quad_witching_proximity(
        None, persist=True, today=date(2026, 2, 19)
    )
    assert result.is_opex_window is True
    assert result.opex_alert_fired is True
    assert result.days_to_opex == 1
    assert result.is_quad_witching_window is False
    assert len(captured) == 1
    assert captured[0]["metric_name"] == "opex_t_minus"
    assert captured[0]["extra_payload"]["event_type"] == "monthly_opex"


@pytest.mark.asyncio
async def test_evaluate_outside_both_windows_no_alerts(monkeypatch):
    # April 1, 2026 (mid-month, no proximity)
    # Next quad-witching = June 19 = T-79 (outside)
    # Next OPEX = April 17 = T-16 (outside)
    captured: list[dict[str, Any]] = []

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_quad_witching_proximity(
        None, persist=True, today=date(2026, 4, 1)
    )
    assert result.is_quad_witching_window is False
    assert result.is_opex_window is False
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_quad_and_opex_same_day(monkeypatch):
    # March 20, 2026 = both quad-witching AND March monthly OPEX
    # (every quad-witching Friday IS also the monthly OPEX of that month)
    captured: list[dict[str, Any]] = []

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_quad_witching_proximity(
        None, persist=True, today=date(2026, 3, 20)
    )
    assert result.days_to_quad == 0
    assert result.days_to_opex == 0
    assert result.is_quad_witching_window is True
    assert result.is_opex_window is True
    # Both alerts fire.
    assert len(captured) == 2
    metric_names = {c["metric_name"] for c in captured}
    assert metric_names == {"quad_witching_t_minus", "opex_t_minus"}


@pytest.mark.asyncio
async def test_evaluate_persist_false_suppresses_check_metric(monkeypatch):
    captured: list[dict[str, Any]] = []

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_quad_witching_proximity(
        None, persist=False, today=date(2026, 3, 20)
    )
    # Result still records that we WOULD have fired, but the catalog
    # dispatcher was NOT called (CLI dry-run contract).
    assert result.is_quad_witching_window is True
    assert result.quad_witching_alert_fired is False  # because persist=False
    assert captured == []


def test_threshold_constants_match_catalog():
    """Single source of truth — bridge constants ↔ catalog default_threshold."""
    from ichor_api.alerts.catalog import get_alert_def

    qw = get_alert_def("QUAD_WITCHING")
    assert qw.default_threshold == svc.QUAD_WITCHING_FLOOR_DAYS
    assert qw.metric_name == "quad_witching_t_minus"

    opex = get_alert_def("OPEX_GAMMA_PEAK")
    assert opex.default_threshold == svc.OPEX_FLOOR_DAYS
    assert opex.metric_name == "opex_t_minus"
