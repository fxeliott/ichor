"""Tests for services/vix_term_check.py — VIX_TERM_INVERSION alert."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Any

import pytest
from ichor_api.services import vix_term_check as svc


def test_input_series_and_thresholds():
    assert svc.VIX_1M_SERIES == "VIXCLS"
    assert svc.VIX_3M_SERIES == "VXVCLS"
    assert svc.RATIO_INVERSION_FLOOR == 1.0
    assert svc.RATIO_VOL_SHOCK_FLOOR == 1.05


def test_classify_regime_contango():
    assert svc._classify_regime(0.85) == "contango"
    assert svc._classify_regime(0.94) == "contango"


def test_classify_regime_neutral():
    assert svc._classify_regime(0.95) == "neutral"
    assert svc._classify_regime(0.99) == "neutral"


def test_classify_regime_backwardation():
    assert svc._classify_regime(1.00) == "backwardation"
    assert svc._classify_regime(1.04) == "backwardation"


def test_classify_regime_shock():
    assert svc._classify_regime(1.05) == "backwardation_shock"
    assert svc._classify_regime(1.15) == "backwardation_shock"


def test_classify_regime_degenerate():
    assert svc._classify_regime(None) == ""


@pytest.mark.asyncio
async def test_evaluate_no_data_graceful_noop(monkeypatch):
    captured: list[dict[str, Any]] = []

    async def fake_fetch(_session, *, series_id):
        return None

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_latest", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_vix_term_inversion(None, persist=True)
    assert result.ratio is None
    assert result.alert_fired is False
    assert "missing latest observations" in result.note
    assert "VIXCLS" in result.note and "VXVCLS" in result.note
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_zero_vxv_degenerate(monkeypatch):
    """VXVCLS = 0 must not crash — return graceful no-op."""
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    rows_by_id = {
        svc.VIX_1M_SERIES: (today, 17.0),
        svc.VIX_3M_SERIES: (today, 0.0),
    }

    async def fake_fetch(_session, *, series_id):
        return rows_by_id.get(series_id)

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_latest", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_vix_term_inversion(None, persist=True)
    assert result.ratio is None
    assert result.alert_fired is False
    assert "VXVCLS=0" in result.note
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_contango_no_alert(monkeypatch):
    """Normal calm regime — VIX 1M < VXV 3M, ratio < 1.0, no alert."""
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    rows_by_id = {
        svc.VIX_1M_SERIES: (today, 17.39),  # VIX 17.39
        svc.VIX_3M_SERIES: (today, 19.5),  # VXV 19.5 — contango
    }

    async def fake_fetch(_session, *, series_id):
        return rows_by_id.get(series_id)

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_latest", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_vix_term_inversion(None, persist=True)
    assert result.ratio is not None
    assert result.ratio < svc.RATIO_INVERSION_FLOOR
    assert result.regime == "contango"
    assert result.alert_fired is False
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_backwardation_fires_alert(monkeypatch):
    """Inversion: VIX 1M > VXV 3M, ratio > 1.0 → fire (pure backwardation, not shock)."""
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    # 33 / 32 = 1.03125 → backwardation (between 1.00 and 1.05) but not shock
    rows_by_id = {
        svc.VIX_1M_SERIES: (today, 33.0),
        svc.VIX_3M_SERIES: (today, 32.0),
    }

    async def fake_fetch(_session, *, series_id):
        return rows_by_id.get(series_id)

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_latest", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_vix_term_inversion(None, persist=True)
    assert result.ratio is not None
    assert result.ratio > svc.RATIO_INVERSION_FLOOR
    assert result.ratio < svc.RATIO_VOL_SHOCK_FLOOR  # below shock — pure backwardation
    assert result.regime == "backwardation"
    assert result.alert_fired is True
    assert len(captured) == 1
    kw = captured[0]
    assert kw["metric_name"] == "vix_term_ratio"
    assert kw["asset"] is None
    payload = kw["extra_payload"]
    assert payload["source"] == "FRED:VIXCLS+VXVCLS"
    assert payload["vix_1m"] == 33.0
    assert payload["vix_3m"] == 32.0
    assert payload["regime"] == "backwardation"
    assert payload["is_vol_shock"] is False


@pytest.mark.asyncio
async def test_evaluate_vol_shock_regime(monkeypatch):
    """Steep inversion >= 1.05 → backwardation_shock + is_vol_shock True."""
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    rows_by_id = {
        svc.VIX_1M_SERIES: (today, 60.0),  # COVID-style spike
        svc.VIX_3M_SERIES: (today, 45.0),  # VXV lagging
    }

    async def fake_fetch(_session, *, series_id):
        return rows_by_id.get(series_id)

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_latest", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_vix_term_inversion(None, persist=True)
    assert result.ratio is not None
    assert result.ratio >= svc.RATIO_VOL_SHOCK_FLOOR
    assert result.regime == "backwardation_shock"
    assert result.alert_fired is True
    payload = captured[0]["extra_payload"]
    assert payload["is_vol_shock"] is True
    assert payload["regime"] == "backwardation_shock"


@pytest.mark.asyncio
async def test_evaluate_persist_false_suppresses_check_metric(monkeypatch):
    captured: list[dict[str, Any]] = []
    today = date(2026, 5, 7)

    rows_by_id = {
        svc.VIX_1M_SERIES: (today, 35.0),
        svc.VIX_3M_SERIES: (today, 32.0),
    }

    async def fake_fetch(_session, *, series_id):
        return rows_by_id.get(series_id)

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_fetch_latest", fake_fetch)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_vix_term_inversion(None, persist=False)
    assert result.ratio > svc.RATIO_INVERSION_FLOOR
    assert result.alert_fired is False
    assert captured == []


def test_threshold_constant_matches_catalog():
    from ichor_api.alerts.catalog import get_alert_def

    cat = get_alert_def("VIX_TERM_INVERSION")
    assert cat.default_threshold == svc.RATIO_INVERSION_FLOOR
    assert cat.metric_name == "vix_term_ratio"


def test_dataclass_shape():
    r = svc.VixTermResult(
        vix_1m=35.0,
        vix_3m=32.0,
        ratio=1.0938,
        observation_date=date(2026, 5, 7),
        regime="backwardation_shock",
        alert_fired=True,
        note="vix_term · 1M=35.00 ratio=1.0938",
    )
    d = asdict(r)
    assert set(d.keys()) == {
        "vix_1m",
        "vix_3m",
        "ratio",
        "observation_date",
        "regime",
        "alert_fired",
        "note",
    }
    assert r.regime == "backwardation_shock"
