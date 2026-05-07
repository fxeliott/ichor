"""Tests for services/yield_curve_inversion_check.py."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from ichor_api.services import yield_curve_inversion_check as svc


def test_thresholds_documented():
    assert svc.T10Y2Y_SERIES_ID == "T10Y2Y"
    assert svc.DEEP_INVERSION_FLOOR_PCT == -0.50
    assert svc.SEVERE_INVERSION_FLOOR_PCT == -1.00
    assert svc.SHALLOW_INVERSION_FLOOR_PCT == 0.0


def test_classify_regime_severe():
    assert svc._classify_regime(-1.50) == "severe_inversion"
    assert svc._classify_regime(-1.00) == "severe_inversion"


def test_classify_regime_deep():
    assert svc._classify_regime(-0.99) == "deep_inversion"
    assert svc._classify_regime(-0.50) == "deep_inversion"


def test_classify_regime_shallow():
    assert svc._classify_regime(-0.49) == "shallow_inversion"
    assert svc._classify_regime(-0.10) == "shallow_inversion"


def test_classify_regime_flat():
    assert svc._classify_regime(0.0) == "flat"
    assert svc._classify_regime(0.20) == "flat"


def test_classify_regime_normal():
    assert svc._classify_regime(0.25) == "normal"
    assert svc._classify_regime(1.50) == "normal"


def test_classify_regime_degenerate():
    assert svc._classify_regime(None) == ""


@pytest.mark.asyncio
async def test_evaluate_no_data(monkeypatch):
    captured: list[dict[str, Any]] = []

    async def fake_fetch(_session):
        return None

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_latest_spread", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_yield_curve_inversion(None, persist=True)
    assert result.spread_pct is None
    assert result.alert_fired is False
    assert "no T10Y2Y observations" in result.note
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_normal_curve_no_alert(monkeypatch):
    """Positive spread = normal curve = no alert."""
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    async def fake_fetch(_session):
        return (today, 0.52)  # +52 bps current 2026 state

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_latest_spread", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_yield_curve_inversion(None, persist=True)
    assert result.spread_pct == 0.52
    assert result.spread_bps == 52.0
    assert result.regime == "normal"
    assert result.alert_fired is False
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_shallow_inversion_no_alert(monkeypatch):
    """Inverted but shallow (above -50 bps) → no alert."""
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    async def fake_fetch(_session):
        return (today, -0.30)  # -30 bps shallow inversion

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_latest_spread", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_yield_curve_inversion(None, persist=True)
    assert result.regime == "shallow_inversion"
    assert result.alert_fired is False
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_deep_inversion_fires_alert(monkeypatch):
    """Inverted ≤ -50 bps → fire."""
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    async def fake_fetch(_session):
        return (today, -0.75)  # -75 bps deep inversion

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_latest_spread", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_yield_curve_inversion(None, persist=True)
    assert result.regime == "deep_inversion"
    assert result.alert_fired is True
    assert len(captured) == 1
    kw = captured[0]
    assert kw["metric_name"] == "t10y2y_spread_pct"
    assert kw["asset"] is None
    payload = kw["extra_payload"]
    assert payload["source"] == "FRED:T10Y2Y"
    assert payload["spread_pct"] == -0.75
    assert payload["spread_bps"] == -75.0
    assert payload["regime"] == "deep_inversion"
    assert payload["is_severe"] is False


@pytest.mark.asyncio
async def test_evaluate_severe_inversion(monkeypatch):
    """Severe inversion ≤ -100 bps → fire with is_severe=True."""
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    async def fake_fetch(_session):
        return (today, -1.08)  # COVID-style -108 bps trough

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_latest_spread", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_yield_curve_inversion(None, persist=True)
    assert result.regime == "severe_inversion"
    assert result.alert_fired is True
    payload = captured[0]["extra_payload"]
    assert payload["is_severe"] is True
    assert payload["regime"] == "severe_inversion"


@pytest.mark.asyncio
async def test_evaluate_persist_false(monkeypatch):
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    async def fake_fetch(_session):
        return (today, -0.75)

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_latest_spread", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_yield_curve_inversion(None, persist=False)
    assert result.alert_fired is False
    assert captured == []


def test_threshold_constant_matches_catalog():
    from ichor_api.alerts.catalog import get_alert_def

    cat = get_alert_def("YIELD_CURVE_INVERSION_DEEP")
    assert cat.default_threshold == svc.DEEP_INVERSION_FLOOR_PCT
    assert cat.metric_name == "t10y2y_spread_pct"
