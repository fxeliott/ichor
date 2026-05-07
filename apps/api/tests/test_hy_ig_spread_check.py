"""Tests for services/hy_ig_spread_check.py."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from ichor_api.services import hy_ig_spread_check as svc


def _pair(days_ago: int, hy: float, ig: float, *, today=None) -> tuple[datetime, float, float]:
    today = today or datetime(2026, 5, 8, tzinfo=UTC)
    seen = today - timedelta(days=days_ago)
    return (seen, hy, ig)


def test_zscore_below_min_history_returns_none():
    z, mean, std = svc._zscore([1.0] * 30, 2.0)
    assert (z, mean, std) == (None, None, None)


def test_zscore_with_zero_std():
    z, mean, std = svc._zscore([2.5] * 70, 2.5)
    assert z is None
    assert mean == 2.5
    assert std == 0.0


def test_zscore_textbook_compute():
    history = [2.0] * 60
    z, mean, std = svc._zscore(history, 2.0)
    # std == 0 → z None even with sufficient history
    assert z is None
    assert mean == 2.0


def test_classify_regime_expansion():
    assert svc._classify_regime(2.5) == "expansion"


def test_classify_regime_compression():
    assert svc._classify_regime(-2.5) == "compression"


def test_classify_regime_normal():
    assert svc._classify_regime(0.5) == ""
    assert svc._classify_regime(None) == ""


def test_classify_regime_at_floor():
    # Exactly at floor → not extreme (strictly >)
    assert svc._classify_regime(2.0) == ""
    assert svc._classify_regime(-2.0) == ""


@pytest.mark.asyncio
async def test_evaluate_no_data_graceful_noop(monkeypatch):
    captured: list[dict[str, Any]] = []

    async def fake_fetch(_session, *, days):
        return []

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_paired", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_hy_ig_spread_divergence(None, persist=True)
    assert result.differential_pct is None
    assert result.alert_fired is False
    assert "insufficient" in result.note
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_below_threshold_no_alert(monkeypatch):
    captured: list[dict[str, Any]] = []
    today = datetime(2026, 5, 8, tzinfo=UTC)

    async def fake_fetch(_session, *, days):
        # 90d history with diff cycling 2.0 ± 0.3 (mean=2.0, std≈0.21)
        out = []
        for d_ago in range(89, 0, -1):
            noise = (d_ago % 7 - 3) * 0.1
            out.append(_pair(d_ago, 4.5 + noise, 2.5 + noise * 0.3, today=today))
        # Today close to mean → low z
        out.append(_pair(0, 4.5, 2.55, today=today))
        return out

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_paired", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_hy_ig_spread_divergence(None, persist=True)
    assert result.differential_z is not None
    assert abs(result.differential_z) < svc.ALERT_Z_ABS_FLOOR
    assert result.alert_fired is False
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_expansion_fires_alert(monkeypatch):
    """HY widens fast → spread expansion → fire."""
    captured: list[dict[str, Any]] = []
    today = datetime(2026, 5, 8, tzinfo=UTC)

    async def fake_fetch(_session, *, days):
        out = []
        # 90d steady history, HY-IG ~ 2.0
        for d_ago in range(89, 0, -1):
            noise = (d_ago % 5 - 2) * 0.05
            out.append(_pair(d_ago, 4.5 + noise, 2.5, today=today))
        # Today: HY blows out to 7.0, IG stays → diff = 4.5 (>>+ baseline 2.0)
        out.append(_pair(0, 7.0, 2.5, today=today))
        return out

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_paired", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_hy_ig_spread_divergence(None, persist=True)
    assert result.differential_z is not None
    assert result.differential_z > svc.ALERT_Z_ABS_FLOOR
    assert result.regime == "expansion"
    assert result.alert_fired is True
    assert len(captured) == 1
    payload = captured[0]["extra_payload"]
    assert payload["source"] == "FRED:BAMLH0A0HYM2-BAMLC0A0CM"
    assert payload["regime"] == "expansion"
    assert "differential_pct" in payload
    assert "differential_bps" in payload


@pytest.mark.asyncio
async def test_evaluate_compression_fires_alert(monkeypatch):
    """HY tightens fast (or IG widens fast) → compression → fire."""
    captured: list[dict[str, Any]] = []
    today = datetime(2026, 5, 8, tzinfo=UTC)

    async def fake_fetch(_session, *, days):
        out = []
        # 90d steady, diff ~ 2.0
        for d_ago in range(89, 0, -1):
            noise = (d_ago % 5 - 2) * 0.05
            out.append(_pair(d_ago, 4.5 + noise, 2.5, today=today))
        # Today: HY tightens to 3.5, IG stays → diff = 1.0 (<<- baseline 2.0)
        out.append(_pair(0, 3.5, 2.5, today=today))
        return out

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_paired", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_hy_ig_spread_divergence(None, persist=True)
    assert result.differential_z is not None
    assert result.differential_z < -svc.ALERT_Z_ABS_FLOOR
    assert result.regime == "compression"
    assert result.alert_fired is True
    assert len(captured) == 1
    payload = captured[0]["extra_payload"]
    assert payload["regime"] == "compression"


@pytest.mark.asyncio
async def test_evaluate_persist_false_suppresses_check_metric(monkeypatch):
    captured: list[dict[str, Any]] = []
    today = datetime(2026, 5, 8, tzinfo=UTC)

    async def fake_fetch(_session, *, days):
        out = []
        for d_ago in range(89, 0, -1):
            noise = (d_ago % 5 - 2) * 0.05
            out.append(_pair(d_ago, 4.5 + noise, 2.5, today=today))
        out.append(_pair(0, 7.0, 2.5, today=today))
        return out

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_paired", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_hy_ig_spread_divergence(None, persist=False)
    assert result.differential_z is not None
    # Result records what WOULD have fired
    assert result.regime == "expansion"
    assert result.alert_fired is False  # because persist=False
    assert captured == []


def test_threshold_constant_matches_catalog():
    """Single source of truth — bridge constant ↔ catalog default_threshold."""
    from ichor_api.alerts.catalog import get_alert_def

    a = get_alert_def("HY_IG_SPREAD_DIVERGENCE")
    assert a.default_threshold == svc.ALERT_Z_ABS_FLOOR
    assert a.metric_name == "hy_ig_spread_z"


def test_window_is_90d():
    assert svc.ZSCORE_WINDOW_DAYS == 90


def test_dataclass_shape():
    r = svc.HyIgSpreadResult(
        hy_oas_pct=4.5,
        ig_oas_pct=2.5,
        differential_pct=2.0,
        differential_z=0.5,
        baseline_mean=2.0,
        baseline_std=0.3,
        n_history=89,
        regime="",
        alert_fired=False,
        note="ok",
    )
    assert r.differential_pct == 2.0
    assert r.regime == ""
