"""Tests for services/term_premium_structural_check.py."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest
from ichor_api.services import term_premium_structural_check as svc


def test_window_is_one_trading_year():
    assert svc.ZSCORE_WINDOW_DAYS == 252
    assert svc._MIN_ZSCORE_HISTORY == 180
    assert svc.ALERT_Z_ABS_FLOOR == 2.0


def test_classify_regime():
    assert svc._classify_regime(2.5) == "expansion_structural"
    assert svc._classify_regime(-2.5) == "contraction_structural"
    assert svc._classify_regime(None) == ""


def test_assets_for_regime():
    expansion_assets = svc._assets_for_regime("expansion_structural")
    assert "XAU_USD" in expansion_assets
    assert "MORTGAGE" in expansion_assets
    contraction_assets = svc._assets_for_regime("contraction_structural")
    assert "DGS10" in contraction_assets
    assert svc._assets_for_regime("") == []


def test_zscore_below_min_history_returns_none():
    z, mean, std = svc._zscore([0.5] * 100, 0.7)
    assert (z, mean, std) == (None, None, None)


def test_zscore_textbook_252d():
    history = [0.5 + (i % 10 - 4) * 0.001 for i in range(252)]
    z, mean, std = svc._zscore(history, 1.0)
    assert z is not None and z > 5


@pytest.mark.asyncio
async def test_evaluate_no_observations(monkeypatch):
    captured: list[dict[str, Any]] = []

    async def fake_fetch(_session, *, days):
        return []

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_observations", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_term_premium_structural(None, persist=True)
    assert result.current_value_pct is None
    assert result.alert_fired is False
    assert "no THREEFYTP10 observations" in result.note
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_insufficient_history(monkeypatch):
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    async def fake_fetch(_session, *, days):
        return [(today - timedelta(days=50 - i), 0.5 + i * 0.01) for i in range(50)]

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_observations", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_term_premium_structural(None, persist=True)
    assert result.z_score is None
    assert result.alert_fired is False
    assert "insufficient history" in result.note


@pytest.mark.asyncio
async def test_evaluate_fires_expansion_structural(monkeypatch):
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    async def fake_fetch(_session, *, days):
        history = [
            (today - timedelta(days=252 - i), 0.45 + (i % 5 - 2) * 0.001) for i in range(252)
        ]
        history.append((today, 1.5))  # huge spike up
        return history

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_observations", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_term_premium_structural(None, persist=True)
    assert result.z_score is not None and result.z_score > 0
    assert result.alert_fired is True
    assert result.regime == "expansion_structural"
    assert "XAU_USD" in result.assets_likely_to_move
    assert len(captured) == 1
    kw = captured[0]
    assert kw["metric_name"] == "term_premium_z_252d"
    assert kw["asset"] is None
    payload = kw["extra_payload"]
    assert payload["source"] == "FRED:THREEFYTP10"
    assert payload["window_days"] == 252
    assert payload["regime"] == "expansion_structural"


@pytest.mark.asyncio
async def test_evaluate_persist_false_suppresses(monkeypatch):
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    async def fake_fetch(_session, *, days):
        history = [
            (today - timedelta(days=252 - i), 0.45 + (i % 5 - 2) * 0.001) for i in range(252)
        ]
        history.append((today, 1.5))
        return history

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_observations", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_term_premium_structural(None, persist=False)
    assert result.alert_fired is False
    assert captured == []


def test_threshold_constant_matches_catalog():
    from ichor_api.alerts.catalog import get_alert_def

    cat = get_alert_def("TERM_PREMIUM_STRUCTURAL_252D")
    assert cat.default_threshold == svc.ALERT_Z_ABS_FLOOR
    assert cat.metric_name == "term_premium_z_252d"
