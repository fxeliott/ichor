"""Tests for services/dollar_smile_check.py — DOLLAR_SMILE_BREAK alert."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import pytest
from ichor_api.services import dollar_smile_check as svc


def test_5_input_series_documented():
    """Verify the 5 input series + thresholds are well-defined.

    ADR-055 wave 27: 5-of-5 gate (was 4-of-4 in ADR-043).
    """
    assert svc.TERM_PREMIUM_SERIES == "THREEFYTP10"
    assert svc.DXY_SERIES == "DTWEXBGS"
    assert svc.VIX_SERIES == "VIXCLS"
    assert svc.HY_OAS_SERIES == "BAMLH0A0HYM2"
    assert svc.TERM_PREMIUM_EXPANSION_FLOOR == 2.0
    assert svc.DXY_WEAKNESS_CEILING == -1.0
    assert svc.VIX_NOT_PANIC_CEILING == 1.0
    assert svc.HY_OAS_NOT_STRESS_CEILING == 1.0
    assert svc.SKEW_ELEVATED_FLOOR == 1.0
    assert svc.ALERT_CONDITIONS_FLOOR == 5


def test_zscore_below_min_history_returns_none():
    assert svc._zscore([100.0] * 30, 200.0) is None


def test_zscore_with_zero_std_returns_none():
    assert svc._zscore([100.0] * 70, 100.0) is None


def test_zscore_textbook():
    history = [100.0 + (i % 5 - 2) * 0.1 for i in range(90)]
    z = svc._zscore(history, 105.0)
    assert z is not None and z > 5


def test_evaluate_condition_passes_above_floor():
    cs = svc._evaluate_condition("term_premium_expansion", 2.5, 2.0, ">")
    assert cs.passes is True
    assert cs.z_score == 2.5


def test_evaluate_condition_fails_at_floor():
    """Strict > — at exactly the floor, fails."""
    cs = svc._evaluate_condition("term_premium_expansion", 2.0, 2.0, ">")
    assert cs.passes is False


def test_evaluate_condition_passes_below_ceiling():
    cs = svc._evaluate_condition("dxy_weakness", -1.5, -1.0, "<")
    assert cs.passes is True


def test_evaluate_condition_fails_above_ceiling():
    cs = svc._evaluate_condition("dxy_weakness", -0.5, -1.0, "<")
    assert cs.passes is False


def test_evaluate_condition_handles_none_z():
    cs = svc._evaluate_condition("vix_not_panic", None, 1.0, "<")
    assert cs.z_score is None
    assert cs.passes is False


def test_evaluate_condition_graceful_none_passes():
    """Wave 27: graceful_none=True (used for SKEW during warm-up) must
    treat None z as PASSING. Preserves ADR-043 4-of-4 back-compat
    until cboe_skew_observations has ≥60d history."""
    cs = svc._evaluate_condition("skew_elevated_tail_risk", None, 1.0, ">", graceful_none=True)
    assert cs.z_score is None
    assert cs.passes is True


@pytest.mark.asyncio
async def test_evaluate_no_data_returns_graceful_noop(monkeypatch):
    """Empty DB → all 4 conditions fail (None z), no alert."""
    captured: list[dict[str, Any]] = []

    async def fake_compute(_session, series_id):
        return None

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_compute_zscore_for_series", fake_compute)

    # Wave 27: SKEW gracefully passes when history is missing (None).
    async def fake_compute_skew(_session):
        return None

    monkeypatch.setattr(svc, "_compute_zscore_for_cboe_skew", fake_compute_skew)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_dollar_smile_break(None, persist=True)
    # All 4 FRED z-scores are None → fail. SKEW None gracefully passes.
    # 1 of 5 conditions (skew skip-pass) — far from the floor.
    assert result.n_conditions_passing == 1
    assert result.alert_fired is False
    assert result.smile_regime == ""
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_partial_alignment_no_alert(monkeypatch):
    """4 of 5 conditions pass — gate requires all 5. No alert.

    Wave 27: 3 FRED conditions pass, 1 fails (HY OAS), SKEW skip-passes.
    Net 4/5 — under the 5/5 floor. Stricter than ADR-043 4-of-4 but
    only when SKEW history is warm; here SKEW is None (skip-pass), so
    we need the 4 FRED to all align for fire — same as before.
    """
    captured: list[dict[str, Any]] = []

    z_values = {
        svc.TERM_PREMIUM_SERIES: 2.5,  # term premium expanding ✓
        svc.DXY_SERIES: -1.5,  # DXY weak ✓
        svc.VIX_SERIES: 0.5,  # not panic ✓
        svc.HY_OAS_SERIES: 1.5,  # CREDIT STRESS — fails the gate
    }

    async def fake_compute(_session, series_id):
        return z_values.get(series_id)

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_compute_zscore_for_series", fake_compute)

    # Wave 27: SKEW gracefully passes when history is missing (None).
    async def fake_compute_skew(_session):
        return None

    monkeypatch.setattr(svc, "_compute_zscore_for_cboe_skew", fake_compute_skew)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_dollar_smile_break(None, persist=True)
    # 3 FRED pass + 1 FRED fail + SKEW skip-pass = 4/5 — under floor.
    assert result.n_conditions_passing == 4
    assert result.alert_fired is False
    assert result.smile_regime == ""
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_full_alignment_fires_alert(monkeypatch):
    """All 4 FRED conditions pass + SKEW skip-pass (warm-up) → 5/5 fire.

    Wave 27: preserves ADR-043 back-compat — when SKEW history is
    insufficient (collector warm-up <60d), we treat the 5th condition
    as graceful pass, so the 4 FRED conditions alone still fire the
    alert, exactly as in the original ADR-043.
    """
    captured: list[dict[str, Any]] = []

    z_values = {
        svc.TERM_PREMIUM_SERIES: 2.5,  # ✓ term premium expanding
        svc.DXY_SERIES: -1.5,  # ✓ DXY weak
        svc.VIX_SERIES: 0.5,  # ✓ not panic
        svc.HY_OAS_SERIES: 0.3,  # ✓ no credit stress
    }

    async def fake_compute(_session, series_id):
        return z_values.get(series_id)

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_compute_zscore_for_series", fake_compute)

    # Wave 27: SKEW gracefully passes when history is missing (None).
    async def fake_compute_skew(_session):
        return None

    monkeypatch.setattr(svc, "_compute_zscore_for_cboe_skew", fake_compute_skew)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_dollar_smile_break(None, persist=True)
    # 4 FRED pass + SKEW skip-pass (None) = 5/5 → fire.
    assert result.n_conditions_passing == 5
    assert result.alert_fired is True
    assert result.smile_regime == "us_driven_instability"
    assert len(captured) == 1
    kw = captured[0]
    assert kw["metric_name"] == "dollar_smile_conditions_met"
    assert kw["asset"] is None
    assert kw["current_value"] == 5.0
    payload = kw["extra_payload"]
    assert payload["smile_regime"] == "us_driven_instability"
    assert payload["z_term_premium"] == 2.5
    assert payload["z_dxy"] == -1.5
    assert payload["z_skew"] is None
    assert payload["skew_warm"] is False
    assert payload["tail_amplified"] is False
    assert "FRED:THREEFYTP10+DTWEXBGS+VIXCLS+BAMLH0A0HYM2 + CBOE:SKEW" == payload["source"]
    assert len(payload["conditions"]) == 5
    assert all(c["passes"] for c in payload["conditions"])


@pytest.mark.asyncio
async def test_evaluate_skew_warm_and_passes_amplifies(monkeypatch):
    """ADR-055: when SKEW history is warm AND skew_z > +1.0, the alert
    fires with tail_amplified=True flag (5-of-5 strict)."""
    captured: list[dict[str, Any]] = []

    z_values = {
        svc.TERM_PREMIUM_SERIES: 2.5,
        svc.DXY_SERIES: -1.5,
        svc.VIX_SERIES: 0.5,
        svc.HY_OAS_SERIES: 0.3,
    }

    async def fake_compute(_session, series_id):
        return z_values.get(series_id)

    async def fake_compute_skew(_session):
        return 1.7  # warm, elevated

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_compute_zscore_for_series", fake_compute)
    monkeypatch.setattr(svc, "_compute_zscore_for_cboe_skew", fake_compute_skew)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_dollar_smile_break(None, persist=True)
    assert result.n_conditions_passing == 5
    assert result.alert_fired is True
    assert captured[0]["extra_payload"]["z_skew"] == 1.7
    assert captured[0]["extra_payload"]["skew_warm"] is True
    assert captured[0]["extra_payload"]["tail_amplified"] is True


@pytest.mark.asyncio
async def test_evaluate_skew_warm_but_fails_blocks_alert(monkeypatch):
    """ADR-055 stricter behaviour: when SKEW history is warm AND
    skew_z <= +1.0, only 4 of 5 → no fire. This is the new strictness
    over ADR-043 (4-of-4 would have fired)."""
    captured: list[dict[str, Any]] = []

    z_values = {
        svc.TERM_PREMIUM_SERIES: 2.5,
        svc.DXY_SERIES: -1.5,
        svc.VIX_SERIES: 0.5,
        svc.HY_OAS_SERIES: 0.3,
    }

    async def fake_compute(_session, series_id):
        return z_values.get(series_id)

    async def fake_compute_skew(_session):
        return 0.4  # warm, not elevated → fails

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_compute_zscore_for_series", fake_compute)
    monkeypatch.setattr(svc, "_compute_zscore_for_cboe_skew", fake_compute_skew)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_dollar_smile_break(None, persist=True)
    assert result.n_conditions_passing == 4
    assert result.alert_fired is False
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_classic_left_smile_no_alert(monkeypatch):
    """Classic LEFT-side smile (VIX panic + HY OAS spike + DXY strong) is
    NOT us-driven instability. Should not fire DOLLAR_SMILE_BREAK."""
    captured: list[dict[str, Any]] = []

    z_values = {
        svc.TERM_PREMIUM_SERIES: 0.5,  # neutral
        svc.DXY_SERIES: 2.5,  # USD STRONG (classic safe-haven) — fails dxy_weakness
        svc.VIX_SERIES: 3.0,  # panic — fails vix_not_panic
        svc.HY_OAS_SERIES: 3.0,  # credit stress — fails hy_oas_not_stress
    }

    async def fake_compute(_session, series_id):
        return z_values.get(series_id)

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_compute_zscore_for_series", fake_compute)

    # Wave 27: SKEW gracefully passes when history is missing (None).
    async def fake_compute_skew(_session):
        return None

    monkeypatch.setattr(svc, "_compute_zscore_for_cboe_skew", fake_compute_skew)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_dollar_smile_break(None, persist=True)
    # 0 FRED pass (term flat, DXY strong, VIX panic, HY stress) + SKEW
    # skip-pass (None = warm-up) = 1/5. Far below the 5/5 floor.
    assert result.n_conditions_passing == 1
    assert result.alert_fired is False
    assert captured == []


@pytest.mark.asyncio
async def test_evaluate_persist_false_suppresses_check_metric(monkeypatch):
    captured: list[dict[str, Any]] = []

    z_values = {
        svc.TERM_PREMIUM_SERIES: 2.5,
        svc.DXY_SERIES: -1.5,
        svc.VIX_SERIES: 0.5,
        svc.HY_OAS_SERIES: 0.3,
    }

    async def fake_compute(_session, series_id):
        return z_values.get(series_id)

    async def fake_check_metric(_session, **kw):
        captured.append(kw)

    monkeypatch.setattr(svc, "_compute_zscore_for_series", fake_compute)

    # Wave 27: SKEW gracefully passes when history is missing (None).
    async def fake_compute_skew(_session):
        return None

    monkeypatch.setattr(svc, "_compute_zscore_for_cboe_skew", fake_compute_skew)
    monkeypatch.setattr(svc, "check_metric", fake_check_metric)

    result = await svc.evaluate_dollar_smile_break(None, persist=False)
    # 4 FRED pass + SKEW skip-pass = 5/5 (would fire if persist=True)
    assert result.n_conditions_passing == 5
    assert result.alert_fired is False
    assert captured == []


def test_threshold_constant_matches_catalog():
    from ichor_api.alerts.catalog import get_alert_def

    cat = get_alert_def("DOLLAR_SMILE_BREAK")
    assert cat.default_threshold == svc.ALERT_CONDITIONS_FLOOR
    assert cat.metric_name == "dollar_smile_conditions_met"


def test_dataclass_shapes():
    cs = svc.ConditionState(
        name="term_premium_expansion",
        z_score=2.5,
        threshold=2.0,
        operator=">",
        passes=True,
    )
    assert cs.passes is True

    r = svc.DollarSmileResult(
        n_conditions_passing=4,
        alert_fired=True,
        conditions=[cs],
        note="dollar_smile · 4/4 conditions met",
        smile_regime="us_driven_instability",
    )
    d = asdict(r)
    assert set(d.keys()) == {
        "n_conditions_passing",
        "alert_fired",
        "conditions",
        "note",
        "smile_regime",
    }
    assert r.smile_regime == "us_driven_instability"
