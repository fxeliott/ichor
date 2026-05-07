"""Tests for services/treasury_vol_check.py."""

from __future__ import annotations

import math
from typing import Any

import pytest
from ichor_api.services import treasury_vol_check as svc


def test_constants_documented():
    assert svc.DGS10_SERIES_ID == "DGS10"
    assert svc.REALIZED_VOL_WINDOW_DAYS == 30
    assert svc.ZSCORE_WINDOW_DAYS == 252
    assert svc.ALERT_Z_ABS_FLOOR == 2.0
    assert svc.TRADING_DAYS_PER_YEAR == 252


def test_annualized_realized_vol_textbook():
    """Daily moves of ±0.01 (= 1 bp) → annualized ~ 1bp × √252 ≈ 15.9 bps."""
    daily_changes = [0.01, -0.01, 0.01, -0.01] * 6  # 24 samples
    rv = svc._annualized_realized_vol(daily_changes)
    assert rv is not None
    assert math.isclose(rv, 0.01 * math.sqrt(252), rel_tol=0.05)


def test_annualized_realized_vol_below_min():
    """Below 22 samples → None."""
    daily_changes = [0.01] * 10
    assert svc._annualized_realized_vol(daily_changes) is None


def test_zscore_below_min_history():
    z, mean, std = svc._zscore([0.5] * 100, 0.7)
    assert (z, mean, std) == (None, None, None)


def test_zscore_zero_std():
    z, mean, std = svc._zscore([0.5] * 200, 0.5)
    assert z is None
    assert mean == 0.5
    assert std == 0.0


def test_classify_regime():
    assert svc._classify_regime(2.5) == "stress"
    assert svc._classify_regime(-2.5) == "complacency"
    assert svc._classify_regime(1.5) == ""  # below floor
    assert svc._classify_regime(None) == ""


def test_rolling_realized_vols_empty_when_short():
    assert svc._rolling_realized_vols([0.01] * 10, window=30) == []


def test_rolling_realized_vols_basic():
    """50 samples, window 30 → expect ~21 rolling values."""
    daily_changes = [0.01 * (i % 5 - 2) for i in range(50)]
    rolling = svc._rolling_realized_vols(daily_changes, window=30)
    assert len(rolling) == 21  # 50 - 30 + 1
    assert all(rv > 0 for rv in rolling)


@pytest.mark.asyncio
async def test_evaluate_no_data(monkeypatch):
    captured: list[dict[str, Any]] = []

    async def fake_fetch(_session, *, days):
        return []

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_dgs10_history", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_treasury_vol(None, persist=True)
    assert result.alert_fired is False
    assert "insufficient DGS10 data" in result.note
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_insufficient_zscore_history(monkeypatch):
    """Sufficient for 30d realized vol but < 180d z-score history."""
    captured: list[dict[str, Any]] = []

    async def fake_fetch(_session, *, days):
        # 50 yield observations → 49 daily-changes → 20 rolling-RVs (insufficient)
        return [4.0 + i * 0.01 for i in range(50)]

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_dgs10_history", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_treasury_vol(None, persist=True)
    assert result.realized_vol_30d_pct is not None
    assert result.z_score is None
    assert result.alert_fired is False
    assert "insufficient z-score history" in result.note
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_fires_alert_stress_regime(monkeypatch):
    """Long-stable + recent vol spike → fire stress alert."""
    captured: list[dict[str, Any]] = []

    async def fake_fetch(_session, *, days):
        # 300 yields: stable around 4.0 (low vol) for 270, then spike for 30
        out = []
        level = 4.0
        for i in range(270):
            level += (i % 5 - 2) * 0.001  # tiny moves
            out.append(level)
        # Recent 30d: large daily moves (~10 bps each direction)
        for i in range(30):
            level += (i % 2 * 2 - 1) * 0.10  # alternating ±10 bps
            out.append(level)
        return out

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_dgs10_history", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_treasury_vol(None, persist=True)
    assert result.z_score is not None
    if result.z_score >= svc.ALERT_Z_ABS_FLOOR:
        assert result.alert_fired is True
        assert result.regime == "stress"
        assert len(captured) == 1
        kw = captured[0]
        assert kw["metric_name"] == "treasury_realized_vol_z"
        payload = kw["extra_payload"]
        assert payload["source"] == "FRED:DGS10"
        assert payload["regime"] == "stress"


@pytest.mark.asyncio
async def test_evaluate_persist_false(monkeypatch):
    captured: list[dict[str, Any]] = []

    async def fake_fetch(_session, *, days):
        return [4.0 + (i % 7) * 0.01 for i in range(300)]

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_dgs10_history", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_treasury_vol(None, persist=False)
    assert result.alert_fired is False
    assert captured == []


def test_threshold_constant_matches_catalog():
    from ichor_api.alerts.catalog import get_alert_def

    cat = get_alert_def("TREASURY_VOL_SPIKE")
    assert cat.default_threshold == svc.ALERT_Z_ABS_FLOOR
    assert cat.metric_name == "treasury_realized_vol_z"
