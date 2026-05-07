"""Tests for services/yield_curve_un_inversion_check.py."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest
from ichor_api.services import yield_curve_un_inversion_check as svc


def test_constants_documented():
    assert svc.T10Y2Y_SERIES_ID == "T10Y2Y"
    assert svc.ALERT_CONDITIONS_FLOOR == 2
    assert svc.LOOKBACK_DAYS == 60
    assert svc.DEEP_INVERSION_DEPTH_PCT == -0.30


@pytest.mark.asyncio
async def test_evaluate_no_data(monkeypatch):
    captured: list[dict[str, Any]] = []

    async def fake_fetch(_session, *, days):
        return []

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_history", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_yield_curve_un_inversion(None, persist=True)
    assert result.n_conditions_met == 0
    assert result.alert_fired is False
    assert "insufficient" in result.note
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_only_one_observation(monkeypatch):
    """Single row → can't compute cross-up → graceful no-op."""
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    async def fake_fetch(_session, *, days):
        return [(today, 0.50)]

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_history", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_yield_curve_un_inversion(None, persist=True)
    assert result.alert_fired is False
    assert "insufficient" in result.note
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_normal_curve_no_event(monkeypatch):
    """No inversion in window, normal curve → no alert."""
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    async def fake_fetch(_session, *, days):
        # 60d of stable +0.50 readings
        return [(today - timedelta(days=60 - i), 0.50) for i in range(61)]

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_history", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_yield_curve_un_inversion(None, persist=True)
    assert result.cross_up_today is False
    assert result.deep_inversion_in_window is False
    assert result.n_conditions_met == 0
    assert result.alert_fired is False
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_cross_up_without_deep_inversion(monkeypatch):
    """Cross-up event but no deep inversion in window → no alert."""
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    async def fake_fetch(_session, *, days):
        # Last 60d: shallow inversion -0.10 max, then today crosses +0.05
        rows = [(today - timedelta(days=60 - i), -0.10) for i in range(60)]
        rows.append((today, 0.05))
        return rows

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_history", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_yield_curve_un_inversion(None, persist=True)
    assert result.cross_up_today is True
    assert result.deep_inversion_in_window is False  # -0.10 > -0.30 floor
    assert result.n_conditions_met == 1
    assert result.alert_fired is False
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_deep_inversion_without_cross_up(monkeypatch):
    """Deep inversion existed but no cross-up today → no alert."""
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    async def fake_fetch(_session, *, days):
        # Deep inversion in window, today still negative
        rows = [(today - timedelta(days=60 - i), -0.50) for i in range(60)]
        rows.append((today, -0.10))  # still negative
        return rows

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_history", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_yield_curve_un_inversion(None, persist=True)
    assert result.cross_up_today is False
    assert result.deep_inversion_in_window is True
    assert result.n_conditions_met == 1
    assert result.alert_fired is False
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_full_un_inversion_event_fires(monkeypatch):
    """Both conditions met → fire."""
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    async def fake_fetch(_session, *, days):
        # 60d of deep inversion (down to -1.00), yesterday still negative,
        # today crosses up to +0.10
        rows = []
        for i in range(60):
            d = today - timedelta(days=60 - i)
            v = -1.00 + i * 0.015  # ramp from -1.00 toward 0
            rows.append((d, v))
        # yesterday at -0.05, today at +0.10
        rows[-1] = (today - timedelta(days=1), -0.05)
        rows.append((today, 0.10))
        return rows

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_history", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_yield_curve_un_inversion(None, persist=True)
    assert result.cross_up_today is True
    assert result.deep_inversion_in_window is True
    assert result.n_conditions_met == 2
    assert result.alert_fired is True
    assert len(captured) == 1
    kw = captured[0]
    assert kw["metric_name"] == "yield_curve_un_inversion_conditions"
    assert kw["current_value"] == 2.0
    payload = kw["extra_payload"]
    assert payload["source"] == "FRED:T10Y2Y"
    assert payload["cross_up_today"] is True
    assert payload["deep_inversion_in_window"] is True
    assert payload["max_inversion_depth_60d_pct"] is not None
    assert payload["max_inversion_depth_60d_pct"] <= -0.30


@pytest.mark.asyncio
async def test_evaluate_persist_false(monkeypatch):
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    async def fake_fetch(_session, *, days):
        rows = [(today - timedelta(days=60 - i), -0.50) for i in range(60)]
        rows[-1] = (today - timedelta(days=1), -0.05)
        rows.append((today, 0.10))
        return rows

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_history", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_yield_curve_un_inversion(None, persist=False)
    assert result.n_conditions_met == 2
    assert result.alert_fired is False
    assert captured == []


def test_threshold_constant_matches_catalog():
    from ichor_api.alerts.catalog import get_alert_def

    cat = get_alert_def("YIELD_CURVE_UN_INVERSION_EVENT")
    assert cat.default_threshold == svc.ALERT_CONDITIONS_FLOOR
    assert cat.metric_name == "yield_curve_un_inversion_conditions"
