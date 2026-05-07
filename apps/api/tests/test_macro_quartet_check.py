"""Tests for services/macro_quartet_check.py — MACRO_QUARTET_STRESS alert."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import pytest
from ichor_api.services import macro_quartet_check as svc


def test_quartet_series_has_4_dimensions():
    assert len(svc.QUARTET_SERIES) == 4
    series_ids = {sid for sid, _ in svc.QUARTET_SERIES}
    assert series_ids == {"DTWEXBGS", "DGS10", "VIXCLS", "BAMLH0A0HYM2"}


def test_zscore_below_min_history_returns_none():
    assert svc._zscore([100.0] * 30, 200.0) is None


def test_zscore_with_zero_std_returns_none():
    assert svc._zscore([100.0] * 70, 100.0) is None


def test_zscore_textbook_spike():
    history = [100.0 + (i % 5 - 2) * 0.1 for i in range(90)]
    z = svc._zscore(history, 200.0)
    assert z is not None
    assert z > 5


def test_classify_regime_stress():
    """N pos >= 3 → stress regime."""
    assert svc._classify_regime(n_pos=3, n_neg=0, n_extreme=3) == "stress"
    assert svc._classify_regime(n_pos=4, n_neg=0, n_extreme=4) == "stress"


def test_classify_regime_complacency():
    """N neg >= 3 → complacency regime."""
    assert svc._classify_regime(n_pos=0, n_neg=3, n_extreme=3) == "complacency"


def test_classify_regime_mixed():
    """Extreme >= 3 but no positive/negative consensus → mixed."""
    assert svc._classify_regime(n_pos=2, n_neg=2, n_extreme=4) == "mixed"
    assert svc._classify_regime(n_pos=2, n_neg=1, n_extreme=3) == "mixed"


def test_classify_regime_normal():
    """N extreme < 3 → no regime tag."""
    assert svc._classify_regime(n_pos=2, n_neg=0, n_extreme=2) == ""
    assert svc._classify_regime(n_pos=0, n_neg=0, n_extreme=0) == ""


@pytest.mark.asyncio
async def test_evaluate_no_data_returns_graceful_noop(monkeypatch):
    captured: list[dict[str, Any]] = []

    async def fake_fetch(_session, *, series_id, days):
        return []

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_series_history", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_macro_quartet(None, persist=True)
    assert result.n_dimensions_evaluated == 0
    assert result.alert_fired is False
    assert all(d.z_score is None for d in result.per_dim)
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_below_threshold_no_alert(monkeypatch):
    """Only 1 dim in extreme territory → no alert."""
    captured: list[dict[str, Any]] = []

    # Larger noise so a small delta on current doesn't accidentally cross 2.0σ.
    series_data = {
        "DTWEXBGS": [100.0 + (i % 7 - 3) * 1.0 for i in range(90)] + [100.5],  # z low
        "DGS10": [4.0 + (i % 7 - 3) * 0.10 for i in range(90)] + [4.05],  # z low
        "VIXCLS": [15.0 + (i % 7 - 3) * 0.5 for i in range(90)] + [25.0],  # z high
        "BAMLH0A0HYM2": [3.5 + (i % 7 - 3) * 0.20 for i in range(90)] + [3.6],  # z low
    }

    async def fake_fetch(_session, *, series_id, days):
        return series_data.get(series_id, [])

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_series_history", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_macro_quartet(None, persist=True)
    assert result.n_dimensions_evaluated == 4
    assert result.n_stressed_extreme < svc.ALERT_COUNT_FLOOR
    assert result.alert_fired is False
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_fires_stress_regime(monkeypatch):
    """3 of 4 dims aligned positive → stress regime alert."""
    captured: list[dict[str, Any]] = []

    series_data = {
        # 3-of-4 stressed: VIX, HY OAS, 10Y all spike up
        "DTWEXBGS": [100.0 + (i % 5 - 2) * 0.1 for i in range(90)] + [100.5],  # z low
        "DGS10": [4.0 + (i % 5 - 2) * 0.001 for i in range(90)] + [5.0],  # z high
        "VIXCLS": [15.0 + (i % 5 - 2) * 0.1 for i in range(90)] + [40.0],  # z high
        "BAMLH0A0HYM2": [3.5 + (i % 5 - 2) * 0.01 for i in range(90)] + [6.0],  # z high
    }

    async def fake_fetch(_session, *, series_id, days):
        return series_data.get(series_id, [])

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_series_history", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_macro_quartet(None, persist=True)
    assert result.n_dimensions_evaluated == 4
    assert result.n_stressed_extreme >= svc.ALERT_COUNT_FLOOR
    assert result.n_aligned_positive >= 3
    assert result.regime == "stress"
    assert result.alert_fired is True
    assert len(captured) == 1
    kw = captured[0]
    assert kw["metric_name"] == "quartet_stress_count"
    assert kw["asset"] is None
    payload = kw["extra_payload"]
    assert payload["regime"] == "stress"
    assert payload["n_aligned_positive"] >= 3
    assert "FRED:DTWEXBGS+DGS10+VIXCLS+BAMLH0A0HYM2" in payload["source"]
    assert len(payload["per_dim"]) == 4


@pytest.mark.asyncio
async def test_evaluate_fires_complacency_regime(monkeypatch):
    """3 of 4 dims aligned negative → complacency regime alert."""
    captured: list[dict[str, Any]] = []

    series_data = {
        "DTWEXBGS": [110.0 + (i % 5 - 2) * 0.001 for i in range(90)] + [99.0],  # z very low
        "DGS10": [5.0 + (i % 5 - 2) * 0.001 for i in range(90)] + [3.0],  # z very low
        "VIXCLS": [20.0 + (i % 5 - 2) * 0.001 for i in range(90)] + [10.0],  # z very low
        "BAMLH0A0HYM2": [4.0 + (i % 5 - 2) * 0.1 for i in range(90)] + [4.1],  # z low
    }

    async def fake_fetch(_session, *, series_id, days):
        return series_data.get(series_id, [])

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_series_history", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_macro_quartet(None, persist=True)
    assert result.n_aligned_negative >= 3
    assert result.regime == "complacency"
    assert result.alert_fired is True
    payload = captured[0]["extra_payload"]
    assert payload["regime"] == "complacency"


@pytest.mark.asyncio
async def test_evaluate_persist_false_suppresses_check_metric(monkeypatch):
    captured: list[dict[str, Any]] = []

    series_data = {
        "DTWEXBGS": [100.0 + (i % 5 - 2) * 0.1 for i in range(90)] + [100.5],
        "DGS10": [4.0 + (i % 5 - 2) * 0.001 for i in range(90)] + [5.0],
        "VIXCLS": [15.0 + (i % 5 - 2) * 0.1 for i in range(90)] + [40.0],
        "BAMLH0A0HYM2": [3.5 + (i % 5 - 2) * 0.01 for i in range(90)] + [6.0],
    }

    async def fake_fetch(_session, *, series_id, days):
        return series_data.get(series_id, [])

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_series_history", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_macro_quartet(None, persist=False)
    assert result.alert_fired is False
    assert captured == []


def test_threshold_constant_matches_catalog():
    from ichor_api.alerts.catalog import get_alert_def

    cat = get_alert_def("MACRO_QUARTET_STRESS")
    assert cat.default_threshold == svc.ALERT_COUNT_FLOOR
    assert cat.metric_name == "quartet_stress_count"


def test_window_is_90d():
    assert svc.ZSCORE_WINDOW_DAYS == 90
    assert svc._MIN_ZSCORE_HISTORY == 60
    assert svc.PER_DIM_Z_FLOOR == 2.0
    assert svc.ALERT_COUNT_FLOOR == 3


def test_dataclass_shapes():
    dim = svc.DimensionState(
        series_id="VIXCLS",
        dim_label="VIX",
        current_value=40.0,
        z_score=2.5,
        sign=1,
    )
    assert dim.sign == 1

    r = svc.MacroQuartetResult(
        n_dimensions_evaluated=4,
        n_stressed_extreme=3,
        n_aligned_positive=3,
        n_aligned_negative=0,
        regime="stress",
        alert_fired=True,
        per_dim=[dim],
        note="quartet evaluated=4/4 stressed_extreme=3 (pos=3 neg=0) regime=stress",
    )
    d = asdict(r)
    assert set(d.keys()) == {
        "n_dimensions_evaluated",
        "n_stressed_extreme",
        "n_aligned_positive",
        "n_aligned_negative",
        "regime",
        "alert_fired",
        "per_dim",
        "note",
    }
    assert r.regime == "stress"
