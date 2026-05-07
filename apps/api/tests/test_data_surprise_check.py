"""Tests for services/data_surprise_check.py — DATA_SURPRISE_Z alert wiring.

Goal: verify that the bridge layer correctly translates per-series
z-scores from the surprise index into catalog alert calls, with the
right polarity correction and source-stamping.

Strategy: monkey-patch `assess_surprise_index` (the upstream proxy)
and `check_metric` (the downstream catalog dispatcher) so the test
is independent of FRED data and the alert table — we only verify
the *bridge* logic.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import pytest
from ichor_api.services import data_surprise_check
from ichor_api.services.surprise_index import (
    SeriesSurprise,
    SurpriseIndexReading,
)


def _series(
    series_id: str,
    z: float | None,
    *,
    last: float = 100.0,
    mean: float = 100.0,
    std: float = 1.0,
    n_history: int = 24,
) -> SeriesSurprise:
    return SeriesSurprise(
        series_id=series_id,
        label=f"{series_id} test",
        last_value=last,
        rolling_mean=mean,
        rolling_std=std,
        z_score=z,
        n_history=n_history,
    )


@pytest.mark.asyncio
async def test_no_alerts_when_all_z_below_threshold(monkeypatch):
    reading = SurpriseIndexReading(
        region="US",
        composite=0.4,
        band="neutral",
        series=[_series("PAYEMS", 0.5), _series("CPIAUCSL", -0.3)],
        n_series_used=2,
    )
    captured: list[dict[str, Any]] = []

    async def fake_assess(_session):
        return reading

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(data_surprise_check, "assess_surprise_index", fake_assess)
    monkeypatch.setattr(data_surprise_check, "check_metric", fake_check_metric)

    result = await data_surprise_check.evaluate_data_surprise_z(None, persist=True)

    assert result.n_series_evaluated == 2
    assert result.n_series_alerting == 0
    assert result.alerts_fired == []
    assert captured == []


@pytest.mark.asyncio
async def test_alerts_above_threshold_only(monkeypatch):
    reading = SurpriseIndexReading(
        region="US",
        composite=2.4,
        band="strong_positive",
        series=[
            _series("PAYEMS", 2.31),  # alerts
            _series("CPIAUCSL", -2.05),  # alerts (negative side)
            _series("INDPRO", 1.5),  # below floor → no alert
            _series("UNRATE", -2.5),  # alerts (already polarity-corrected upstream)
            _series("PCEPI", None),  # missing → skipped
        ],
        n_series_used=4,
    )
    captured: list[dict[str, Any]] = []

    async def fake_assess(_session):
        return reading

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(data_surprise_check, "assess_surprise_index", fake_assess)
    monkeypatch.setattr(data_surprise_check, "check_metric", fake_check_metric)

    result = await data_surprise_check.evaluate_data_surprise_z(None, persist=True)

    assert result.n_series_alerting == 3
    assert sorted([a.split("=")[0] for a in result.alerts_fired]) == sorted(
        ["PAYEMS", "CPIAUCSL", "UNRATE"]
    )
    assert len(captured) == 3
    metric_names = {c["metric_name"] for c in captured}
    assert metric_names == {"data_surprise_z"}
    sources = {c["extra_payload"]["source"] for c in captured}
    assert sources == {"FRED:PAYEMS", "FRED:CPIAUCSL", "FRED:UNRATE"}
    polarities = {c["extra_payload"]["polarity"] for c in captured}
    assert polarities == {"natural", "inverted"}


@pytest.mark.asyncio
async def test_persist_false_suppresses_check_metric(monkeypatch):
    reading = SurpriseIndexReading(
        region="US",
        composite=2.31,
        band="strong_positive",
        series=[_series("PAYEMS", 2.31)],
        n_series_used=1,
    )
    captured: list[dict[str, Any]] = []

    async def fake_assess(_session):
        return reading

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(data_surprise_check, "assess_surprise_index", fake_assess)
    monkeypatch.setattr(data_surprise_check, "check_metric", fake_check_metric)

    result = await data_surprise_check.evaluate_data_surprise_z(None, persist=False)

    # Result still records the alert as "fired" for human-visible
    # logging, but check_metric is NOT called when persist=False — this
    # is the contract the CLI dry-run mode expects.
    assert result.n_series_alerting == 1
    assert result.alerts_fired == ["PAYEMS=+2.31"]
    assert captured == []


def test_threshold_constant_matches_catalog():
    """Defensive: keep the bridge constant in lock-step with the catalog
    AlertDef default_threshold so a single source of truth remains.
    Failing this test means someone tweaked the catalog without
    updating the bridge.
    """
    from ichor_api.alerts.catalog import get_alert_def

    cat = get_alert_def("DATA_SURPRISE_Z")
    assert cat.default_threshold == data_surprise_check.ALERT_Z_ABS_FLOOR
    assert cat.metric_name == "data_surprise_z"


def test_dataclass_shape():
    r = data_surprise_check.DataSurpriseCheckResult(
        region="US",
        composite_z=1.0,
        composite_band="neutral",
        n_series_evaluated=6,
        n_series_alerting=0,
        alerts_fired=[],
    )
    d = asdict(r)
    assert set(d.keys()) == {
        "region",
        "composite_z",
        "composite_band",
        "n_series_evaluated",
        "n_series_alerting",
        "alerts_fired",
    }
