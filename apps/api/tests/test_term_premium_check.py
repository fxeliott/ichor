"""Tests for services/term_premium_check.py — TERM_PREMIUM_REPRICING alert."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta
from typing import Any

import pytest
from ichor_api.services import term_premium_check as svc


def test_zscore_below_min_history_returns_none():
    """_MIN_ZSCORE_HISTORY = 60."""
    z, mean, std = svc._zscore([0.5] * 30, 0.7)
    assert (z, mean, std) == (None, None, None)


def test_zscore_with_zero_std_returns_none_z():
    z, mean, std = svc._zscore([0.5] * 70, 0.5)
    assert z is None
    assert mean == 0.5
    assert std == 0.0


def test_zscore_textbook_expansion():
    """Term premium 0.5% baseline, current 1.0% → ~+5σ."""
    history = [0.5 + (i % 5 - 2) * 0.001 for i in range(90)]
    z, mean, std = svc._zscore(history, 1.0)
    assert z is not None and z > 5
    assert std is not None and std > 0


def test_classify_regime():
    assert svc._classify_regime(2.5) == "expansion"
    assert svc._classify_regime(-2.5) == "contraction"
    assert svc._classify_regime(0.5) == "expansion"  # any positive
    assert svc._classify_regime(-0.5) == "contraction"  # any negative
    assert svc._classify_regime(None) == ""


def test_assets_for_regime():
    expansion_assets = svc._assets_for_regime("expansion")
    assert "XAU_USD" in expansion_assets
    assert "DXY" in expansion_assets
    assert "MORTGAGE" in expansion_assets
    contraction_assets = svc._assets_for_regime("contraction")
    assert "DGS10" in contraction_assets
    # contraction = flight-to-quality, gold not a primary mover
    assert "BAMLH0A0HYM2" in contraction_assets
    assert svc._assets_for_regime("") == []


@pytest.mark.asyncio
async def test_evaluate_no_observations_returns_graceful_noop(monkeypatch):
    captured: list[dict[str, Any]] = []

    async def fake_fetch(_session, *, days):
        return []

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_observations", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_term_premium_repricing(None, persist=True)
    assert result.current_value_pct is None
    assert result.alert_fired is False
    assert "no THREEFYTP10 observations" in result.note
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_insufficient_history_returns_no_alert(monkeypatch):
    """< _MIN_ZSCORE_HISTORY (60) usable history → no alert."""
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    async def fake_fetch(_session, *, days):
        return [(today - timedelta(days=30 - i), 0.5 + i * 0.01) for i in range(30)]

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_observations", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_term_premium_repricing(None, persist=True)
    assert result.current_value_pct is not None
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
        # 90 days of stable values around 0.45 with small noise, current = 0.46
        return [
            (today - timedelta(days=90 - i), 0.45 + (i % 10 - 5) * 0.005)
            for i in range(90)
        ] + [(today, 0.46)]

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_observations", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_term_premium_repricing(None, persist=True)
    assert result.z_score is not None
    assert abs(result.z_score) < svc.ALERT_Z_ABS_FLOOR
    assert result.alert_fired is False
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_fires_alert_expansion_regime(monkeypatch):
    """+2σ expansion → alert fired with regime='expansion' + assets list."""
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    async def fake_fetch(_session, *, days):
        # 90 stable values around 0.45, current = 1.5 (huge spike up)
        history = [
            (today - timedelta(days=90 - i), 0.45 + (i % 5 - 2) * 0.001)
            for i in range(90)
        ]
        history.append((today, 1.5))
        return history

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_observations", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_term_premium_repricing(None, persist=True)
    assert result.z_score is not None and result.z_score > 0
    assert result.alert_fired is True
    assert result.regime == "expansion"
    assert "XAU_USD" in result.assets_likely_to_move
    assert "MORTGAGE" in result.assets_likely_to_move
    assert len(captured) == 1
    kw = captured[0]
    assert kw["metric_name"] == "term_premium_z"
    assert kw["asset"] is None
    payload = kw["extra_payload"]
    assert payload["source"] == "FRED:THREEFYTP10"
    assert payload["term_premium_pct"] == 1.5
    # FRED reports in %, so 1.5% = 150 bps
    assert payload["term_premium_bps"] == 150.0
    assert payload["regime"] == "expansion"


@pytest.mark.asyncio
async def test_evaluate_fires_alert_contraction_regime(monkeypatch):
    """-2σ contraction → alert fired with regime='contraction' + flight-to-quality assets."""
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    async def fake_fetch(_session, *, days):
        history = [
            (today - timedelta(days=90 - i), 0.45 + (i % 5 - 2) * 0.001)
            for i in range(90)
        ]
        history.append((today, -1.0))  # huge contraction
        return history

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_observations", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_term_premium_repricing(None, persist=True)
    assert result.z_score is not None and result.z_score < 0
    assert result.alert_fired is True
    assert result.regime == "contraction"
    assert "DGS10" in result.assets_likely_to_move
    # Contraction-specific (not in expansion list)
    assert "BAMLH0A0HYM2" in result.assets_likely_to_move


@pytest.mark.asyncio
async def test_evaluate_persist_false_suppresses_check_metric(monkeypatch):
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    async def fake_fetch(_session, *, days):
        history = [
            (today - timedelta(days=90 - i), 0.45 + (i % 5 - 2) * 0.001)
            for i in range(90)
        ]
        history.append((today, 1.5))
        return history

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_recent_observations", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_term_premium_repricing(None, persist=False)
    assert result.z_score is not None
    assert abs(result.z_score) >= svc.ALERT_Z_ABS_FLOOR
    assert result.alert_fired is False
    assert result.assets_likely_to_move == []
    assert captured == []


def test_threshold_constant_matches_catalog():
    """Single source of truth — bridge ↔ catalog default_threshold."""
    from ichor_api.alerts.catalog import get_alert_def

    cat = get_alert_def("TERM_PREMIUM_REPRICING")
    assert cat.default_threshold == svc.ALERT_Z_ABS_FLOOR
    assert cat.metric_name == "term_premium_z"


def test_window_is_90d():
    """90d trailing for narrative-shift detection."""
    assert svc.ZSCORE_WINDOW_DAYS == 90
    assert svc._MIN_ZSCORE_HISTORY == 60


def test_dataclass_shape():
    r = svc.TermPremiumResult(
        current_value_pct=0.85,
        current_date=date(2026, 5, 7),
        baseline_mean=0.45,
        baseline_std=0.15,
        z_score=2.67,
        n_history=90,
        alert_fired=True,
        regime="expansion",
        note="term_premium=0.85 baseline=0.45±0.15 z=+2.67 (expansion)",
        assets_likely_to_move=["XAU_USD", "DXY", "MORTGAGE"],
    )
    d = asdict(r)
    assert set(d.keys()) == {
        "current_value_pct",
        "current_date",
        "baseline_mean",
        "baseline_std",
        "z_score",
        "n_history",
        "alert_fired",
        "regime",
        "note",
        "assets_likely_to_move",
    }
    assert r.regime == "expansion"
    assert "XAU_USD" in r.assets_likely_to_move
