"""Tests for services/geopol_flash_check.py — GEOPOL_FLASH alert wiring."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta
from typing import Any

import pytest
from ichor_api.services import geopol_flash_check as svc


def test_zscore_below_min_history_returns_none():
    z, mean, std = svc._zscore([100.0] * 10, 200.0)
    assert (z, mean, std) == (None, None, None)


def test_zscore_with_zero_std_returns_none_z():
    z, mean, std = svc._zscore([100.0] * 25, 100.0)
    # All values identical → std == 0 → z is None, mean and std reported
    assert z is None
    assert mean == 100.0
    assert std == 0.0


def test_zscore_textbook_positive_spike():
    # Build 25 values around 100, then current = 150 should yield large z
    history = [100.0 + (i % 5 - 2) for i in range(25)]
    z, mean, std = svc._zscore(history, 150.0)
    assert z is not None
    assert mean is not None
    assert std is not None
    assert std > 0
    # 150 is many σ above ~100 mean
    assert z > 5


def test_zscore_textbook_negative_excursion():
    history = [100.0 + (i % 5 - 2) for i in range(25)]
    z, mean, std = svc._zscore(history, 50.0)
    assert z is not None
    # 50 is many σ below ~100 mean
    assert z < -5


@pytest.mark.asyncio
async def test_evaluate_no_observations_returns_graceful_noop(monkeypatch):
    """Empty DB → no alert, structured note pointing at the collector."""
    captured: list[dict[str, Any]] = []

    async def fake_fetch(_session, *, days):
        return []

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_observations", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_geopol_flash(None, persist=True)
    assert result.current_value is None
    assert result.z_score is None
    assert result.alert_fired is False
    assert "no AI-GPR observations" in result.note
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_insufficient_history_returns_no_alert(monkeypatch):
    """< _MIN_ZSCORE_HISTORY (20d) usable history → no alert, structured note."""
    captured: list[dict[str, Any]] = []

    async def fake_fetch(_session, *, days):
        # 10 days of observations — current + 9 history; 9 < 20
        today = date(2026, 5, 7)
        return [(today - timedelta(days=10 - i), 90.0 + i) for i in range(10)]

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_observations", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_geopol_flash(None, persist=True)
    assert result.current_value is not None
    assert result.z_score is None
    assert result.alert_fired is False
    assert "insufficient history" in result.note
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_below_threshold_no_alert(monkeypatch):
    """|z| < 2.0 → no alert fired even with full history."""
    captured: list[dict[str, Any]] = []

    async def fake_fetch(_session, *, days):
        # 30d of stable values around 100 ± small noise, current = 101
        today = date(2026, 5, 7)
        return [(today - timedelta(days=30 - i), 100.0 + (i % 5 - 2) * 0.5) for i in range(30)] + [
            (today, 101.0)
        ]

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_observations", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_geopol_flash(None, persist=True)
    assert result.z_score is not None
    assert abs(result.z_score) < svc.ALERT_Z_ABS_FLOOR
    assert result.alert_fired is False
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_fires_alert_above_threshold_with_source_stamp(monkeypatch):
    """|z| >= 2.0 → alert fired with proper source-stamping."""
    captured: list[dict[str, Any]] = []

    async def fake_fetch(_session, *, days):
        # 30d of low values then a sudden spike — guaranteed |z| >> 2
        today = date(2026, 5, 7)
        history = [(today - timedelta(days=30 - i), 100.0 + (i % 3 - 1) * 0.1) for i in range(30)]
        history.append((today, 150.0))
        return history

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_observations", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_geopol_flash(None, persist=True)
    assert result.z_score is not None
    assert abs(result.z_score) >= svc.ALERT_Z_ABS_FLOOR
    assert result.alert_fired is True
    assert len(captured) == 1
    kw = captured[0]
    assert kw["metric_name"] == "ai_gpr_z"
    assert kw["asset"] is None
    payload = kw["extra_payload"]
    assert payload["source"] == "ai_gpr:caldara_iacoviello"
    assert payload["ai_gpr_value"] == 150.0
    assert payload["ai_gpr_date"] == "2026-05-07"
    assert "havens_likely_to_move" in payload
    assert "XAU_USD" in payload["havens_likely_to_move"]
    assert "USD_JPY" in payload["havens_likely_to_move"]
    # havens_signaled mirrored on the result for CLI-level visibility
    assert "XAU_USD" in result.havens_signaled


@pytest.mark.asyncio
async def test_evaluate_persist_false_suppresses_check_metric(monkeypatch):
    """`persist=False` (CLI dry-run) MUST NOT touch the alert table."""
    captured: list[dict[str, Any]] = []

    async def fake_fetch(_session, *, days):
        today = date(2026, 5, 7)
        history = [(today - timedelta(days=30 - i), 100.0 + (i % 3 - 1) * 0.1) for i in range(30)]
        history.append((today, 200.0))
        return history

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_observations", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_geopol_flash(None, persist=False)
    # z is computed and threshold is crossed, but `persist=False`
    # contractually means "do not call check_metric" (CLI dry-run).
    assert result.z_score is not None
    assert abs(result.z_score) >= svc.ALERT_Z_ABS_FLOOR
    assert result.alert_fired is False
    assert result.havens_signaled == []
    assert captured == []


def test_threshold_constant_matches_catalog():
    """Single source of truth — bridge constant ↔ catalog default_threshold."""
    from ichor_api.alerts.catalog import get_alert_def

    cat = get_alert_def("GEOPOL_FLASH")
    assert cat.default_threshold == svc.ALERT_Z_ABS_FLOOR
    assert cat.metric_name == "ai_gpr_z"


def test_dataclass_shape():
    r = svc.GeopolFlashResult(
        current_value=100.0,
        current_date=date(2026, 5, 7),
        baseline_mean=95.0,
        baseline_std=2.5,
        z_score=2.0,
        n_history=30,
        alert_fired=True,
        note="ai_gpr=100.00 baseline=95.00±2.50 z=+2.00",
        havens_signaled=["XAU_USD", "USD_JPY", "USD_CHF", "DXY"],
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
        "havens_signaled",
    }
    assert r.alert_fired is True
    assert r.havens_signaled[0] == "XAU_USD"
