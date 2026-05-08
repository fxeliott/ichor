"""Tests for services/macro_quintet_check.py."""

from __future__ import annotations

from typing import Any

import pytest
from ichor_api.services import macro_quintet_check as svc


def test_quintet_has_5_dimensions():
    assert len(svc.QUINTET_SERIES) == 5
    labels = [d[1] for d in svc.QUINTET_SERIES]
    # First 4 are quartet, 5th is TREASURY_VOL
    assert "TREASURY_VOL" in labels


def test_zscore_below_min_history():
    assert svc._zscore([1.0] * 30, 2.0) is None


def test_zscore_zero_std():
    assert svc._zscore([2.0] * 70, 2.0) is None


def test_zscore_textbook():
    # 60 vals around 0 ± 1 → mean=0, std≈1. Current=3 → z≈3
    history = [(-1) ** i for i in range(60)]
    z = svc._zscore(history, 3.0)
    assert z is not None and z > 2.5


def test_compute_realized_vol_series_short_input():
    assert svc._compute_realized_vol_series([1.0, 2.0]) == []


def test_compute_realized_vol_series_constant_zero_vol():
    # Constant series → log-changes = 0 → vol = 0
    levels = [4.5] * 60
    rv = svc._compute_realized_vol_series(levels)
    assert all(v == 0.0 for v in rv)


def test_compute_realized_vol_series_known_size():
    # 100 levels → rv series length = 100 - REALIZED_VOL_WINDOW (=30)
    levels = [4.5 + 0.01 * i for i in range(100)]
    rv = svc._compute_realized_vol_series(levels)
    assert len(rv) == 100 - svc._REALIZED_VOL_WINDOW


def test_classify_regime_stress():
    assert svc._classify_regime(4, 0, 4) == "stress"


def test_classify_regime_complacency():
    assert svc._classify_regime(0, 4, 4) == "complacency"


def test_classify_regime_mixed():
    # 4 extreme but split 2/2 → mixed
    assert svc._classify_regime(2, 2, 4) == "mixed"


def test_classify_regime_normal_below_floor():
    # 3 extreme < 4 floor → normal
    assert svc._classify_regime(3, 0, 3) == ""


@pytest.mark.asyncio
async def test_evaluate_no_data_returns_zero(monkeypatch):
    captured: list[dict[str, Any]] = []

    async def fake_fetch(_session, *, series_id, days):
        return []

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_series_history", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_macro_quintet(None, persist=True)
    assert result.n_dimensions_evaluated == 0
    assert result.n_stressed_extreme == 0
    assert result.alert_fired is False
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_below_threshold_no_alert(monkeypatch):
    """Synthetic data: all 5 dims have z near 0 → no alert."""
    captured: list[dict[str, Any]] = []

    async def fake_fetch(_session, *, series_id, days):
        # 130 vals around mean with noise → low z when current ≈ mean
        return [4.5 + 0.05 * ((i % 7) - 3) for i in range(130)]

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_series_history", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_macro_quintet(None, persist=True)
    # Each dim has small z if any (because data is noise)
    assert result.alert_fired is False
    assert result.regime == ""
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_4_of_5_stress_fires_alert(monkeypatch):
    """Synthesize history where current spike pushes 4-of-5 dims above +2σ."""
    captured: list[dict[str, Any]] = []

    async def fake_fetch(_session, *, series_id, days):
        # 130d history near mean=4.5 ± 0.05, last value spikes to 5.5 (very high z)
        # Will produce z >> 2 for all 5 dims (level + realized_vol)
        history = [4.5 + 0.05 * ((i % 5) - 2) for i in range(129)]
        history.append(5.5)  # large spike
        return history

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_series_history", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_macro_quintet(None, persist=True)
    # All 5 dims share the same fake_fetch → all extreme positive
    assert result.n_stressed_extreme >= svc.ALERT_COUNT_FLOOR
    assert result.regime == "stress"
    assert result.alert_fired is True
    assert len(captured) == 1
    payload = captured[0]["extra_payload"]
    assert payload["source"].startswith("FRED:DTWEXBGS")
    assert "DGS10_realized_vol" in payload["source"]
    assert payload["regime"] == "stress"
    assert "per_dim" in payload
    assert len(payload["per_dim"]) == 5


@pytest.mark.asyncio
async def test_evaluate_persist_false_suppresses(monkeypatch):
    captured: list[dict[str, Any]] = []

    async def fake_fetch(_session, *, series_id, days):
        history = [4.5 + 0.05 * ((i % 5) - 2) for i in range(129)]
        history.append(5.5)
        return history

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_series_history", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_macro_quintet(None, persist=False)
    assert result.alert_fired is False  # because persist=False
    assert captured == []


def test_threshold_constant_matches_catalog():
    from ichor_api.alerts.catalog import get_alert_def
    a = get_alert_def("MACRO_QUINTET_STRESS")
    assert a.default_threshold == svc.ALERT_COUNT_FLOOR
    assert a.metric_name == "quintet_stress_count"


def test_window_is_90d():
    assert svc.ZSCORE_WINDOW_DAYS == 90


def test_per_dim_floor_is_2_sigma():
    assert svc.PER_DIM_Z_FLOOR == 2.0


def test_alert_count_floor_is_4_of_5():
    assert svc.ALERT_COUNT_FLOOR == 4
    assert len(svc.QUINTET_SERIES) == 5
