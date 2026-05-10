"""Tests for services/geopol_regime_check.py — GEOPOL_REGIME_STRUCTURAL alert."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta
from typing import Any

import pytest
from ichor_api.services import geopol_regime_check as svc


def test_zscore_below_min_history_returns_none():
    """_MIN_ZSCORE_HISTORY = 180 — below this, no z-score (warmup)."""
    z, mean, std = svc._zscore([100.0] * 100, 200.0)
    assert (z, mean, std) == (None, None, None)


def test_zscore_with_zero_std_returns_none_z():
    z, mean, std = svc._zscore([100.0] * 200, 100.0)
    assert z is None
    assert mean == 100.0
    assert std == 0.0


def test_zscore_textbook_252d():
    history = [100.0 + (i % 10 - 4) for i in range(252)]
    z, mean, std = svc._zscore(history, 130.0)
    assert z is not None and z > 5
    assert mean is not None
    assert std is not None and std > 0


@pytest.mark.asyncio
async def test_evaluate_no_observations_returns_graceful_noop(monkeypatch):
    captured: list[dict[str, Any]] = []

    async def fake_fetch(_session, *, days):
        return []

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_observations", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_geopol_regime_structural(None, persist=True)
    assert result.current_value is None
    assert result.alert_fired is False
    assert "no AI-GPR observations" in result.note
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_insufficient_history_returns_no_alert(monkeypatch):
    """< _MIN_ZSCORE_HISTORY (180) usable history → structured note, no alert."""
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    async def fake_fetch(_session, *, days):
        # Only 50 observations — way below 180 floor
        return [(today - timedelta(days=50 - i), 90.0 + i) for i in range(50)]

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_observations", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_geopol_regime_structural(None, persist=True)
    assert result.current_value is not None
    assert result.z_score is None
    assert result.alert_fired is False
    assert "insufficient history" in result.note
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_below_threshold_no_alert(monkeypatch):
    """|z| < 2.0 → no alert."""
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    async def fake_fetch(_session, *, days):
        # 252+ stable values around 100, current=101 → small z
        return [
            (today - timedelta(days=252 - i), 100.0 + (i % 10 - 4) * 0.5) for i in range(252)
        ] + [(today, 101.0)]

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_observations", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_geopol_regime_structural(None, persist=True)
    assert result.z_score is not None
    assert abs(result.z_score) < svc.ALERT_Z_ABS_FLOOR
    assert result.alert_fired is False
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_fires_alert_above_threshold(monkeypatch):
    """|z| >= 2.0 → alert fired with proper source-stamping."""
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    async def fake_fetch(_session, *, days):
        # 252 values around 100 with small variance, current = 200 → huge z
        history = [(today - timedelta(days=252 - i), 100.0 + (i % 5 - 2) * 0.1) for i in range(252)]
        history.append((today, 200.0))
        return history

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_observations", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_geopol_regime_structural(None, persist=True)
    assert result.z_score is not None
    assert abs(result.z_score) >= svc.ALERT_Z_ABS_FLOOR
    assert result.alert_fired is True
    assert len(captured) == 1
    kw = captured[0]
    assert kw["metric_name"] == "ai_gpr_z_252d"
    assert kw["asset"] is None
    payload = kw["extra_payload"]
    assert payload["source"] == "ai_gpr:caldara_iacoviello"
    assert payload["window_days"] == svc.ZSCORE_WINDOW_DAYS == 252
    assert payload["ai_gpr_value"] == 200.0
    assert "regimes_signaled" in payload
    assert "Russia-Ukraine cumulative escalation" in payload["regimes_signaled"]
    assert "Taiwan-strait militarization" in payload["regimes_signaled"]


@pytest.mark.asyncio
async def test_evaluate_persist_false_suppresses_check_metric(monkeypatch):
    """`persist=False` → no alert table writes."""
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    async def fake_fetch(_session, *, days):
        history = [(today - timedelta(days=252 - i), 100.0 + (i % 5 - 2) * 0.1) for i in range(252)]
        history.append((today, 250.0))
        return history

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_observations", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_geopol_regime_structural(None, persist=False)
    assert result.z_score is not None
    assert abs(result.z_score) >= svc.ALERT_Z_ABS_FLOOR
    assert result.alert_fired is False
    assert result.regimes_signaled == []
    assert captured == []


def test_threshold_constant_matches_catalog():
    """Single source of truth — bridge constant ↔ catalog default_threshold."""
    from ichor_api.alerts.catalog import get_alert_def

    cat = get_alert_def("GEOPOL_REGIME_STRUCTURAL")
    assert cat.default_threshold == svc.ALERT_Z_ABS_FLOOR
    assert cat.metric_name == "ai_gpr_z_252d"


def test_window_is_one_trading_year():
    """252 = standard 1 trading year window in finance — verify constant."""
    assert svc.ZSCORE_WINDOW_DAYS == 252
    assert svc._MIN_ZSCORE_HISTORY == 180  # ~71% warmup floor


def test_dataclass_shape():
    r = svc.GeopolRegimeResult(
        current_value=100.0,
        current_date=date(2026, 5, 7),
        baseline_mean=95.0,
        baseline_std=2.5,
        z_score=2.0,
        n_history=252,
        alert_fired=True,
        note="ai_gpr=100.00 baseline_252d=95.00±2.50 z=+2.00",
        regimes_signaled=["Russia-Ukraine cumulative escalation"],
    )
    d = asdict(r)
    assert set(d.keys()) == {
        "current_value",
        "current_date",
        "baseline_mean",
        "baseline_std",
        "z_score",
        "n_history",
        "alert_fired",
        "note",
        "regimes_signaled",
    }
    assert r.alert_fired is True
