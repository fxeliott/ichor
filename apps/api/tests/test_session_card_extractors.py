"""Tests for the Phase-2 SessionCardOut extractors + from_orm_row.

Wave 4.1 added permissive extractors that project typed sub-objects
(thesis, trade_plan, ideas, confluence_drivers, calibration) from the
loosely-typed `claude_raw_response` JSONB. They must :
  - Return None on missing / non-dict / wrong-shape inputs (never raise)
  - Handle 4 candidate nesting locations: root, `session_card`, `output`, `session`
  - Reject malformed sub-objects (Pydantic ValidationError caught silently)

`SessionCardOut.from_orm_row` chains the extractors onto the base shape
and must remain idempotent on rows that have no claude_raw_response.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import uuid4

from ichor_api.schemas import (
    CalibrationStat,
    ConfluenceDriver,
    DegradedInputOut,
    IdeaSet,
    SessionCardOut,
    TradePlan,
    extract_calibration_stat,
    extract_confluence_drivers,
    extract_ideas,
    extract_thesis,
    extract_trade_plan,
)


def _row(**overrides: object) -> SimpleNamespace:
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
        "claude_raw_response": None,
        "claude_duration_ms": 14500,
        "realized_close_session": None,
        "realized_at": None,
        "brier_contribution": None,
        "created_at": datetime(2026, 5, 5, 7, 5, tzinfo=UTC),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _full_payload() -> dict[str, object]:
    return {
        "thesis": "EUR support 1.0820 + ECB hawkish bias",
        "trade_plan": {
            "entry_low": 1.0850,
            "entry_high": 1.0860,
            "invalidation_level": 1.0820,
            "invalidation_condition": "close H1",
            "tp_rr3": 1.0940,
            "tp_rr15": 1.1300,
            "partial_scheme": "90 % @ RR3 · trail 10 %",
        },
        "ideas": {
            "top": "Long retest 1.0850-1.0860",
            "supporting": ["DXY breakdown", "Real yield diff"],
            "risks": ["Lagarde dovish surprise"],
        },
        "confluence_drivers": [
            {"factor": "DXY directional alignment", "contribution": 0.28},
            {"factor": "Real yields differential", "contribution": 0.22},
        ],
        "calibration": {"brier": 0.142, "sample_size": 87, "trend": "bull"},
    }


# ────────────────────────── extract_thesis ──────────────────────────


def test_extract_thesis_returns_str_at_root() -> None:
    assert extract_thesis(_full_payload()) == "EUR support 1.0820 + ECB hawkish bias"


def test_extract_thesis_returns_none_for_none_input() -> None:
    assert extract_thesis(None) is None


def test_extract_thesis_returns_none_for_non_dict() -> None:
    assert extract_thesis("a string") is None
    assert extract_thesis([1, 2, 3]) is None
    assert extract_thesis(42) is None


def test_extract_thesis_handles_nested_session_card_key() -> None:
    nested = {"session_card": {"thesis": "Nested thesis ok"}}
    assert extract_thesis(nested) == "Nested thesis ok"


def test_extract_thesis_handles_nested_output_key() -> None:
    nested = {"output": {"thesis": "Output-keyed"}}
    assert extract_thesis(nested) == "Output-keyed"


def test_extract_thesis_caps_at_512_chars() -> None:
    long = "x" * 1024
    out = extract_thesis({"thesis": long})
    assert out is not None and len(out) == 512


def test_extract_thesis_returns_none_for_empty_or_whitespace() -> None:
    assert extract_thesis({"thesis": ""}) is None
    assert extract_thesis({"thesis": "   "}) is None


def test_extract_thesis_returns_none_for_non_str_value() -> None:
    assert extract_thesis({"thesis": 42}) is None
    assert extract_thesis({"thesis": ["list"]}) is None


# ────────────────────────── extract_trade_plan ──────────────────────


def test_extract_trade_plan_returns_typed_object() -> None:
    plan = extract_trade_plan(_full_payload())
    assert isinstance(plan, TradePlan)
    assert plan.entry_low == 1.0850
    assert plan.tp_rr3 == 1.0940


def test_extract_trade_plan_returns_none_for_missing() -> None:
    assert extract_trade_plan({"thesis": "no plan here"}) is None
    assert extract_trade_plan(None) is None


def test_extract_trade_plan_returns_none_for_malformed() -> None:
    bad = {"trade_plan": {"entry_low": "not-a-number"}}
    assert extract_trade_plan(bad) is None


def test_extract_trade_plan_handles_nested_payload() -> None:
    nested = {"output": _full_payload()}
    plan = extract_trade_plan(nested)
    assert isinstance(plan, TradePlan)


# ────────────────────────── extract_ideas ──────────────────────────


def test_extract_ideas_returns_typed_object() -> None:
    ideas = extract_ideas(_full_payload())
    assert isinstance(ideas, IdeaSet)
    assert ideas.top == "Long retest 1.0850-1.0860"
    assert "DXY breakdown" in ideas.supporting


def test_extract_ideas_returns_none_for_missing() -> None:
    assert extract_ideas({"trade_plan": {}}) is None


def test_extract_ideas_returns_none_for_non_dict() -> None:
    assert extract_ideas({"ideas": "string"}) is None


# ──────────────────── extract_confluence_drivers ────────────────────


def test_extract_drivers_returns_list_of_typed() -> None:
    drivers = extract_confluence_drivers(_full_payload())
    assert drivers is not None
    assert len(drivers) == 2
    assert isinstance(drivers[0], ConfluenceDriver)
    assert drivers[0].contribution == 0.28


def test_extract_drivers_returns_none_for_empty_list() -> None:
    """Empty list = no informative drivers ; returns None to match pattern."""
    assert extract_confluence_drivers({"confluence_drivers": []}) is None


def test_extract_drivers_skips_malformed_items() -> None:
    raw = {
        "confluence_drivers": [
            {"factor": "ok", "contribution": 0.1},
            {"factor": "missing-contribution"},  # malformed
            "not-a-dict",
            42,
            {"factor": "ok-2", "contribution": -0.05},
        ]
    }
    out = extract_confluence_drivers(raw)
    assert out is not None
    assert len(out) == 2
    assert [d.factor for d in out] == ["ok", "ok-2"]


def test_extract_drivers_returns_none_for_missing_key() -> None:
    assert extract_confluence_drivers({"thesis": "x"}) is None


# ──────────────────── extract_calibration_stat ────────────────────


def test_extract_calibration_returns_typed() -> None:
    stat = extract_calibration_stat(_full_payload())
    assert isinstance(stat, CalibrationStat)
    assert stat.brier == 0.142
    assert stat.trend == "bull"


def test_extract_calibration_returns_none_for_invalid_trend() -> None:
    bad = {"calibration": {"brier": 0.1, "sample_size": 10, "trend": "skyrocket"}}
    assert extract_calibration_stat(bad) is None


# ────────────────────── SessionCardOut.from_orm_row ──────────────────────


def test_from_orm_row_falls_through_when_no_raw_response() -> None:
    out = SessionCardOut.from_orm_row(_row())
    assert out.thesis is None
    assert out.trade_plan is None
    assert out.ideas is None
    assert out.confluence_drivers is None
    assert out.calibration is None


def test_from_orm_row_enriches_from_root_payload() -> None:
    out = SessionCardOut.from_orm_row(_row(claude_raw_response=_full_payload()))
    assert out.thesis is not None
    assert out.trade_plan is not None and out.trade_plan.tp_rr3 == 1.0940
    assert out.ideas is not None and len(out.ideas.supporting) == 2
    assert out.confluence_drivers is not None and len(out.confluence_drivers) == 2
    assert out.calibration is not None and out.calibration.trend == "bull"


def test_from_orm_row_enriches_from_session_card_nested() -> None:
    raw = {"session_card": _full_payload()}
    out = SessionCardOut.from_orm_row(_row(claude_raw_response=raw))
    assert out.thesis == "EUR support 1.0820 + ECB hawkish bias"
    assert out.trade_plan is not None


def test_from_orm_row_partial_payload_only_fills_present_fields() -> None:
    raw = {"thesis": "Only thesis present"}
    out = SessionCardOut.from_orm_row(_row(claude_raw_response=raw))
    assert out.thesis == "Only thesis present"
    assert out.trade_plan is None
    assert out.confluence_drivers is None


def test_from_orm_row_preserves_base_columns() -> None:
    out = SessionCardOut.from_orm_row(_row(claude_raw_response=_full_payload()))
    assert out.asset == "EUR_USD"
    assert out.bias_direction == "long"
    assert out.conviction_pct == 72.0
    assert out.regime_quadrant == "goldilocks"


def test_from_orm_row_silently_skips_corrupt_payload() -> None:
    """A claude_raw_response shaped like none of the candidates returns base."""
    out = SessionCardOut.from_orm_row(_row(claude_raw_response={"random_unrelated_key": [1, 2, 3]}))
    assert out.thesis is None
    assert out.trade_plan is None


# ───────── SessionCardOut.degraded_inputs tri-state (ADR-104) ─────────
# r95 : the ADR-103 FRED-liveness manifest persisted by migration 0050
# projects with deliberate tri-state semantics — None (legacy / not
# tracked) vs [] (tracked, all fresh) vs [...] (degraded). The end-user
# surface leg of the r93→r94 data-honesty arc.


def test_degraded_inputs_projects_none_for_legacy_row() -> None:
    """Back-compat + honesty : a pre-0050 row has no degraded_inputs
    attribute → projects None ("liveness not tracked at generation"),
    NOT [] ("all fresh"). Protects every r72-r84 /v1/sessions consumer
    (no crash, no shape break on legacy rows)."""
    out = SessionCardOut.from_orm_row(_row())
    assert out.degraded_inputs is None


def test_degraded_inputs_projects_empty_as_tracked_fresh() -> None:
    """[] is semantically distinct from None : "tracked at generation,
    all critical anchors fresh" — must round-trip as [] not None."""
    out = SessionCardOut.from_orm_row(_row(degraded_inputs=[]))
    assert out.degraded_inputs == []


def test_degraded_inputs_projects_degraded_manifest_typed() -> None:
    """A degraded row (the real China-M1 ADR-093 §r49 scenario, exactly
    as run_session_card serialises it via the schemas SSOT model
    model_dump(mode="json")) round-trips to a typed DegradedInputOut
    with latest_date coerced back from the ISO string."""
    serialised = {
        "series_id": "MYAGM1CNM189N",
        "status": "stale",
        "latest_date": "2019-08-01",
        "age_days": 2481,
        "max_age_days": 60,
        "impacted": "AUD composite — China M1 credit-impulse driver",
    }
    out = SessionCardOut.from_orm_row(_row(degraded_inputs=[serialised]))
    assert out.degraded_inputs is not None
    assert len(out.degraded_inputs) == 1
    di = out.degraded_inputs[0]
    assert isinstance(di, DegradedInputOut)
    assert di.series_id == "MYAGM1CNM189N"
    assert di.status == "stale"
    assert di.latest_date == date(2019, 8, 1)  # ISO str coerced back to date
    assert di.age_days == 2481
    assert di.max_age_days == 60
    assert "China" in di.impacted
