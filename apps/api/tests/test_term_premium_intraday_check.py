"""Tests for services/term_premium_intraday_check.py."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from ichor_api.services import term_premium_intraday_check as svc


def _obs(days_ago: int, value: float, *, today=None) -> tuple[datetime, float]:
    today = today or datetime(2026, 5, 8, tzinfo=UTC)
    return (today - timedelta(days=days_ago), value)


def test_zscore_below_min_history():
    z, mean, std = svc._zscore([1.0] * 10, 2.0)
    assert (z, mean, std) == (None, None, None)


def test_zscore_zero_std():
    z, mean, std = svc._zscore([0.7] * 25, 0.7)
    assert z is None
    assert mean == 0.7
    assert std == 0.0


def test_zscore_textbook():
    history = [0.5, 0.6, 0.7, 0.6, 0.5] * 5  # 25 vals
    z, mean, std = svc._zscore(history, 1.5)
    assert z is not None
    assert z > 5  # 1.5 vs mean ~0.58 std small → high z


def test_classify_regime_expansion():
    assert svc._classify_regime(2.5) == "expansion"


def test_classify_regime_contraction():
    assert svc._classify_regime(-2.5) == "contraction"


def test_classify_regime_normal():
    assert svc._classify_regime(0.5) == ""
    assert svc._classify_regime(None) == ""


@pytest.mark.asyncio
async def test_evaluate_no_data(monkeypatch):
    captured: list[dict[str, Any]] = []

    async def fake_fetch(_session, *, days):
        return []

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_observations", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_term_premium_intraday(None, persist=True)
    assert result.term_premium_pct is None
    assert result.alert_fired is False
    assert "no THREEFYTP10" in result.note


@pytest.mark.asyncio
async def test_evaluate_below_threshold(monkeypatch):
    """Steady ~0.7 ± 0.05 → today=0.72 → low z → no alert."""
    captured: list[dict[str, Any]] = []
    today = datetime(2026, 5, 8, tzinfo=UTC)

    async def fake_fetch(_session, *, days):
        # 30 days history near 0.7 ± 0.05
        out = [_obs(d, 0.7 + 0.05 * ((d % 5) - 2), today=today) for d in range(30, 0, -1)]
        out.append(_obs(0, 0.72, today=today))
        return out

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_observations", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_term_premium_intraday(None, persist=True)
    assert result.term_premium_z is not None
    assert abs(result.term_premium_z) < svc.ALERT_Z_ABS_FLOOR
    assert result.alert_fired is False
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_expansion_fires(monkeypatch):
    """Today term premium spikes to 1.5% (vs steady 0.7%) → expansion fire."""
    captured: list[dict[str, Any]] = []
    today = datetime(2026, 5, 8, tzinfo=UTC)

    async def fake_fetch(_session, *, days):
        out = [_obs(d, 0.7 + 0.02 * ((d % 5) - 2), today=today) for d in range(30, 0, -1)]
        out.append(_obs(0, 1.5, today=today))
        return out

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_observations", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_term_premium_intraday(None, persist=True)
    assert result.term_premium_z is not None
    assert result.term_premium_z > svc.ALERT_Z_ABS_FLOOR
    assert result.regime == "expansion"
    assert result.alert_fired is True
    assert len(captured) == 1
    payload = captured[0]["extra_payload"]
    assert payload["source"] == "FRED:THREEFYTP10"
    assert payload["window_days"] == 30
    assert payload["regime"] == "expansion"
    assert "sister_alerts" in payload
    assert len(payload["sister_alerts"]) == 2


@pytest.mark.asyncio
async def test_evaluate_persist_false(monkeypatch):
    captured: list[dict[str, Any]] = []
    today = datetime(2026, 5, 8, tzinfo=UTC)

    async def fake_fetch(_session, *, days):
        out = [_obs(d, 0.7 + 0.02 * ((d % 5) - 2), today=today) for d in range(30, 0, -1)]
        out.append(_obs(0, 1.5, today=today))
        return out

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_observations", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_term_premium_intraday(None, persist=False)
    assert result.regime == "expansion"
    assert result.alert_fired is False  # persist=False
    assert captured == []


def test_threshold_constant_matches_catalog():
    from ichor_api.alerts.catalog import get_alert_def
    a = get_alert_def("TERM_PREMIUM_INTRADAY_30D")
    assert a.default_threshold == svc.ALERT_Z_ABS_FLOOR
    assert a.metric_name == "term_premium_z_30d"


def test_window_is_30d():
    assert svc.ZSCORE_WINDOW_DAYS == 30


def test_min_history_is_20():
    assert svc._MIN_ZSCORE_HISTORY == 20


def test_uses_kw_term_premium_series():
    assert svc.SERIES_ID == "THREEFYTP10"
