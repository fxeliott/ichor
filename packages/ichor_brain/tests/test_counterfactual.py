"""Pure tests for Pass 5 — counterfactual reasoning."""

from __future__ import annotations

import json

import pytest
from ichor_brain.passes import CounterfactualPass, PassError
from ichor_brain.passes.counterfactual import CounterfactualReading


def _wrap(obj: dict) -> str:
    return f"```json\n{json.dumps(obj)}\n```"


_OK = {
    "scrubbed_event": "Powell hawkish surprise on May 2",
    "counterfactual_bias": "neutral",
    "counterfactual_conviction_pct": 30.0,
    "delta_narrative": (
        "Without the Powell hawkish line, the rate-diff narrative "
        "loses its main driver. ECB-Fed expectations re-balance and "
        "the bias compresses toward neutral."
    ),
    "new_dominant_drivers": ["EZ HICP services", "DXY positioning"],
    "confidence_delta": -0.15,
}


def test_counterfactual_system_prompt_mentions_scrub() -> None:
    p = CounterfactualPass()
    assert "scrub" in p.system_prompt.lower()
    assert "JSON" in p.system_prompt


def test_counterfactual_build_prompt_inlines_inputs() -> None:
    p = CounterfactualPass()
    prompt = p.build_prompt(
        original_card_json='{"asset":"EUR_USD"}',
        data_pool="DXY 105.30; US10Y 4.18",
        scrubbed_event="Powell hawkish",
    )
    assert "EUR_USD" in prompt
    assert "Powell hawkish" in prompt
    assert "DXY 105.30" in prompt


def test_counterfactual_parse_ok() -> None:
    p = CounterfactualPass()
    out = p.parse(_wrap(_OK))
    assert isinstance(out, CounterfactualReading)
    assert out.counterfactual_bias == "neutral"
    assert out.counterfactual_conviction_pct == 30.0
    assert "Powell" in out.scrubbed_event
    assert len(out.new_dominant_drivers) == 2


def test_counterfactual_parse_rejects_invalid_bias() -> None:
    p = CounterfactualPass()
    bad = dict(_OK)
    bad["counterfactual_bias"] = "moonshot"
    with pytest.raises(PassError):
        p.parse(_wrap(bad))


def test_counterfactual_parse_caps_conviction_at_95() -> None:
    p = CounterfactualPass()
    bad = dict(_OK)
    bad["counterfactual_conviction_pct"] = 99.0
    with pytest.raises(PassError):
        p.parse(_wrap(bad))


def test_counterfactual_parse_clamps_confidence_delta() -> None:
    p = CounterfactualPass()
    bad = dict(_OK)
    bad["confidence_delta"] = 2.5  # > 1.0 cap
    with pytest.raises(PassError):
        p.parse(_wrap(bad))


def test_counterfactual_parse_rejects_short_delta_narrative() -> None:
    p = CounterfactualPass()
    bad = dict(_OK)
    bad["delta_narrative"] = "too short"
    with pytest.raises(PassError):
        p.parse(_wrap(bad))


def test_counterfactual_parse_rejects_garbage() -> None:
    p = CounterfactualPass()
    with pytest.raises(PassError):
        p.parse("nothing useful here")


def test_counterfactual_default_drivers_empty() -> None:
    p = CounterfactualPass()
    minimal = {**_OK, "new_dominant_drivers": []}
    out = p.parse(_wrap(minimal))
    assert out.new_dominant_drivers == []
