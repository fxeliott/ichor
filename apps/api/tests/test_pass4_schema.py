"""Tests for Phase 2 SessionCard schema delta + Pass 4 scenario extractor.

Asserts :
  - SessionCardOut still serializes from a minimal ORM-like row (back-compat)
  - The new optional fields default to None when not populated
  - extract_pass4_scenarios is permissive (returns [] on malformed JSONB)
  - extract_pass4_scenarios validates strict shapes (probability range, bias)
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from ichor_api.schemas import (
    CalibrationStat,
    ConfluenceDriver,
    IdeaSet,
    Pass4MagnitudeRange,
    Pass4Scenario,
    SessionCardOut,
    TradePlan,
    extract_pass4_scenarios,
)
from pydantic import ValidationError


def _row(overrides: dict[str, object] | None = None) -> SimpleNamespace:
    """ORM-like row mimicking SessionCardAudit instance attributes."""
    base: dict[str, object] = {
        "id": uuid4(),
        "generated_at": datetime(2026, 5, 5, 7, 0, tzinfo=UTC),
        "session_type": "pre_londres",
        "asset": "EUR_USD",
        "model_id": "claude-opus-4-7",
        "regime_quadrant": "goldilocks",
        "bias_direction": "long",
        "conviction_pct": 72.0,
        "magnitude_pips_low": 18.0,
        "magnitude_pips_high": 32.0,
        "timing_window_start": None,
        "timing_window_end": None,
        "mechanisms": None,
        "invalidations": None,
        "catalysts": None,
        "correlations_snapshot": None,
        "polymarket_overlay": None,
        "source_pool_hash": "deadbeef" * 8,
        "critic_verdict": "approved",
        "critic_findings": None,
        "claude_duration_ms": 14500,
        "realized_close_session": None,
        "realized_at": None,
        "brier_contribution": None,
        "created_at": datetime(2026, 5, 5, 7, 5, tzinfo=UTC),
    }
    if overrides:
        base.update(overrides)
    return SimpleNamespace(**base)


# ─────────────────────── SessionCardOut delta ─────────────────────────


def test_session_card_serializes_from_orm_row_unchanged() -> None:
    """Back-compat : an ORM row that doesn't carry the new fields still
    serializes ; the new typed fields default to None."""
    row = _row()
    out = SessionCardOut.model_validate(row)
    assert out.thesis is None
    assert out.trade_plan is None
    assert out.ideas is None
    assert out.confluence_drivers is None
    assert out.calibration is None


def test_session_card_accepts_typed_trade_plan() -> None:
    plan = TradePlan(
        entry_low=1.0850,
        entry_high=1.0860,
        invalidation_level=1.0820,
        invalidation_condition="close H1",
        tp_rr3=1.0940,
        tp_rr15=1.1300,
        partial_scheme="90 % @ RR3 · trail 10 % vers RR15+",
    )
    row = _row()
    payload = SessionCardOut.model_validate(row).model_dump()
    payload["trade_plan"] = plan.model_dump()
    out = SessionCardOut.model_validate(payload)
    assert out.trade_plan is not None
    assert out.trade_plan.tp_rr3 == pytest.approx(1.0940)
    assert out.trade_plan.partial_scheme.startswith("90 %")


def test_session_card_accepts_confluence_drivers_list() -> None:
    drivers = [
        ConfluenceDriver(factor="DXY directional alignment", contribution=0.28),
        ConfluenceDriver(factor="GDELT EU sentiment", contribution=-0.06),
    ]
    row = _row()
    payload = SessionCardOut.model_validate(row).model_dump()
    payload["confluence_drivers"] = [d.model_dump() for d in drivers]
    out = SessionCardOut.model_validate(payload)
    assert out.confluence_drivers is not None
    assert len(out.confluence_drivers) == 2
    assert out.confluence_drivers[0].contribution == pytest.approx(0.28)


def test_idea_set_default_lists_are_empty() -> None:
    ideas = IdeaSet(top="Long zone 1.0850 retest")
    assert ideas.supporting == []
    assert ideas.risks == []


def test_calibration_stat_trend_literal() -> None:
    stat = CalibrationStat(brier=0.142, sample_size=87, trend="bull")
    assert stat.trend == "bull"
    with pytest.raises(ValidationError):
        CalibrationStat(brier=0.142, sample_size=87, trend="invalid")  # type: ignore[arg-type]


# ─────────────────────────── Pass4Scenario ────────────────────────────


def _scenario_dict(*, sid: str = "s1", proba: float = 0.32) -> dict[str, object]:
    return {
        "id": sid,
        "label": "ECB hawkish + DXY breakdown",
        "probability": proba,
        "bias": "bull",
        "magnitude_pips": {"low": 22, "high": 38},
        "primary_mechanism": "Lagarde 8h30 confirms restrictive bias + US PCE fade",
        "invalidation": "close H1 < 1.0820",
    }


def test_scenario_validates_typed_fields() -> None:
    s = Pass4Scenario.model_validate(_scenario_dict())
    assert s.id == "s1"
    assert s.bias == "bull"
    assert isinstance(s.magnitude_pips, Pass4MagnitudeRange)
    assert s.magnitude_pips.low == 22
    assert s.counterfactual_anchor is None


def test_scenario_rejects_probability_out_of_range() -> None:
    with pytest.raises(ValidationError):
        Pass4Scenario.model_validate(_scenario_dict(proba=1.2))
    with pytest.raises(ValidationError):
        Pass4Scenario.model_validate(_scenario_dict(proba=-0.05))


def test_scenario_accepts_counterfactual_anchor() -> None:
    raw = _scenario_dict()
    raw["counterfactual_anchor"] = "lagarde_dovish"
    s = Pass4Scenario.model_validate(raw)
    assert s.counterfactual_anchor == "lagarde_dovish"


# ────────────────────── extract_pass4_scenarios ──────────────────────


def test_extract_returns_empty_for_none() -> None:
    assert extract_pass4_scenarios(None) == []


def test_extract_returns_empty_for_unrelated_dict() -> None:
    assert extract_pass4_scenarios({"foo": "bar"}) == []


def test_extract_handles_dict_with_scenarios_key() -> None:
    raw = {
        "scenarios": [_scenario_dict(sid="s1", proba=0.32), _scenario_dict(sid="s2", proba=0.24)]
    }
    out = extract_pass4_scenarios(raw)
    assert len(out) == 2
    assert {s.id for s in out} == {"s1", "s2"}


def test_extract_handles_top_level_list() -> None:
    raw = [_scenario_dict(sid="s1"), _scenario_dict(sid="s2"), _scenario_dict(sid="s3")]
    out = extract_pass4_scenarios(raw)
    assert len(out) == 3


def test_extract_skips_malformed_entries_silently() -> None:
    raw = [
        _scenario_dict(sid="s1"),
        {"id": "broken", "no_required_fields": True},
        _scenario_dict(sid="s2"),
    ]
    out = extract_pass4_scenarios(raw)
    assert len(out) == 2
    assert {s.id for s in out} == {"s1", "s2"}


def test_extract_drops_non_dict_items_in_list() -> None:
    raw = [_scenario_dict(sid="s1"), "not-a-dict", 42, _scenario_dict(sid="s2")]
    out = extract_pass4_scenarios(raw)
    assert len(out) == 2


def test_extract_validates_full_seven_scenario_tree() -> None:
    raw = [_scenario_dict(sid=f"s{i}", proba=1.0 / 7) for i in range(1, 8)]
    out = extract_pass4_scenarios(raw)
    assert len(out) == 7
    total = sum(s.probability for s in out)
    assert abs(total - 1.0) < 0.05
