"""Per-pass prompt assembly + parser tests (no LLM calls)."""

from __future__ import annotations

import json

import pytest
from ichor_brain.passes import (
    AssetPass,
    InvalidationPass,
    PassError,
    RegimePass,
    StressPass,
)
from ichor_brain.passes.asset import supported_assets
from ichor_brain.types import AssetSpecialization, StressTest

from .fixtures import (
    ASSET_OK_JSON,
    INVALIDATION_OK_JSON,
    REGIME_OK_JSON,
    STRESS_OK_JSON,
)


def _wrap(obj: dict) -> str:
    return f"```json\n{json.dumps(obj)}\n```"


# ─────────────────────────── Pass 1 — régime ──────────────────────────


def test_regime_system_prompt_lists_quadrants() -> None:
    p = RegimePass()
    sys = p.system_prompt
    for quadrant in ("haven_bid", "funding_stress", "goldilocks", "usd_complacency"):
        assert quadrant in sys


def test_regime_build_prompt_inlines_data_pool() -> None:
    p = RegimePass()
    prompt = p.build_prompt(data_pool="DXY=105.3 VIX=18.2")
    assert "DXY=105.3" in prompt
    assert "VIX=18.2" in prompt


def test_regime_build_prompt_omits_analogues_section_when_empty() -> None:
    """W110d ADR-086 — empty/missing analogues_section is byte-identical
    to the pre-W110d prompt shape."""
    p = RegimePass()
    a = p.build_prompt(data_pool="DXY=105 VIX=18")
    b = p.build_prompt(data_pool="DXY=105 VIX=18", analogues_section="")
    c = p.build_prompt(data_pool="DXY=105 VIX=18", analogues_section="   \n")
    assert a == b == c
    assert "Historical analogues" not in a


def test_regime_build_prompt_injects_analogues_before_data_pool() -> None:
    """W110d ADR-086 — analogues_section is injected before the data
    pool block. The model sees analogues as sanity-check context, not
    as evidence."""
    p = RegimePass()
    section = (
        "## Historical analogues (k=2, past-only)\n"
        "1. **2024-11-08** — asset=EUR_USD, regime=goldilocks, cos_dist=0.123\n"
        "   Régime usd_complacency 72% confidence\n"
    )
    prompt = p.build_prompt(data_pool="DXY=105 VIX=18", analogues_section=section)
    assert "Historical analogues" in prompt
    assert "DXY=105" in prompt
    # analogues come BEFORE data pool
    assert prompt.index("Historical analogues") < prompt.index("DXY=105")


def test_regime_parse_ok() -> None:
    p = RegimePass()
    out = p.parse(_wrap(REGIME_OK_JSON))
    assert out.quadrant == "haven_bid"
    assert 0 <= out.confidence_pct <= 95


def test_regime_parse_rejects_garbage() -> None:
    p = RegimePass()
    with pytest.raises(PassError):
        p.parse("nothing useful here")


def test_regime_parse_rejects_invalid_quadrant() -> None:
    p = RegimePass()
    bad = dict(REGIME_OK_JSON)
    bad["quadrant"] = "made_up_quadrant"
    with pytest.raises(PassError):
        p.parse(_wrap(bad))


# ─────────────────────────── Pass 2 — asset ───────────────────────────


def test_asset_supported_set_covers_all_phase1_assets() -> None:
    """Phase 1.2 (CHUNK 8 2026-05-03) shipped the 7 missing frameworks
    so no Phase-1 asset falls back to the generic rubric anymore."""
    expected = {
        "EUR_USD",
        "GBP_USD",
        "USD_JPY",
        "AUD_USD",
        "USD_CAD",
        "XAU_USD",
        "NAS100_USD",
        "SPX500_USD",
        "US100",
        "US30",  # ADR-017 ticker aliases
    }
    assert expected.issubset(set(supported_assets()))


def test_asset_build_prompt_uses_dedicated_framework_for_eur_usd() -> None:
    p = AssetPass()
    prompt = p.build_prompt(
        asset="EUR_USD",
        regime_block="Quadrant: haven_bid",
        asset_data="DGS10=4.18 IRLTLT01DEM156N=2.45",
    )
    assert "EUR/USD framework" in prompt
    assert "US-DE 10Y differential" in prompt
    assert "DGS10=4.18" in prompt


@pytest.mark.parametrize(
    "asset, expected_signature",
    [
        ("XAU_USD", "10Y TIPS real yield"),
        ("USD_JPY", "BoJ YCC stance"),
        ("NAS100_USD", "Mega-cap 7 earnings"),
        ("SPX500_USD", "VIX term slope"),
        ("GBP_USD", "BoE NLP hawk/dove"),
        ("AUD_USD", "Iron ore"),
        ("USD_CAD", "WTI crude"),
        ("US30", "Cyclical earnings"),
    ],
)
def test_asset_build_prompt_uses_dedicated_framework_for_each_asset(
    asset: str, expected_signature: str
) -> None:
    p = AssetPass()
    prompt = p.build_prompt(
        asset=asset,
        regime_block="Quadrant: goldilocks",
        asset_data="...",
    )
    assert expected_signature in prompt, (
        f"{asset} framework should mention {expected_signature!r} but didn't"
    )
    assert "Generic framework" not in prompt


def test_asset_build_prompt_falls_back_for_unknown_asset() -> None:
    p = AssetPass()
    prompt = p.build_prompt(
        asset="BTC_USD",  # not part of Phase-1 universe — should hit fallback
        regime_block="Quadrant: goldilocks",
        asset_data="btc_funding=0.012",
    )
    assert "Generic framework" in prompt


def test_asset_parse_caps_conviction_at_95() -> None:
    p = AssetPass()
    bad = dict(ASSET_OK_JSON)
    bad["conviction_pct"] = 99.0  # > 95 cap
    with pytest.raises(PassError):
        p.parse(_wrap(bad))


def test_asset_parse_rejects_invalid_bias() -> None:
    p = AssetPass()
    bad = dict(ASSET_OK_JSON)
    bad["bias_direction"] = "moonshot"
    with pytest.raises(PassError):
        p.parse(_wrap(bad))


# ─────────────────────────── Pass 3 — stress ──────────────────────────


def test_stress_build_prompt_includes_specialization_json() -> None:
    p = StressPass()
    spec = AssetSpecialization.model_validate(ASSET_OK_JSON)
    prompt = p.build_prompt(specialization=spec, asset_data="...")
    assert "EUR_USD" in prompt
    assert "Pass 2 specialization" in prompt


def test_stress_build_prompt_empty_addenda_section_byte_identical() -> None:
    """W116c regression guard : passing empty addenda_section must
    produce the same prompt text as omitting the kwarg entirely.
    Pre-W116c byte-identical contract."""
    p = StressPass()
    spec = AssetSpecialization.model_validate(ASSET_OK_JSON)
    prompt_without = p.build_prompt(specialization=spec, asset_data="...")
    prompt_with_empty = p.build_prompt(specialization=spec, asset_data="...", addenda_section="")
    prompt_with_whitespace = p.build_prompt(
        specialization=spec, asset_data="...", addenda_section="   \n\n  "
    )
    assert prompt_without == prompt_with_empty
    assert prompt_without == prompt_with_whitespace


def test_stress_build_prompt_injects_addenda_section_when_non_empty() -> None:
    """W116c : non-empty addenda_section renders the "## Operator
    addenda" header before the steelman instruction."""
    p = StressPass()
    spec = AssetSpecialization.model_validate(ASSET_OK_JSON)
    addenda_text = (
        "- Pocket EUR_USD/usd_complacency shows no skill over last 30 d ; "
        "consider widening stress counter-claims on USD strength.\n"
        "- Pocket GBP_USD/goldilocks Brier baseline-equivalent ; addenda "
        "from W116b PBS post-mortem 2026-05-12."
    )
    prompt = p.build_prompt(
        specialization=spec,
        asset_data="...",
        addenda_section=addenda_text,
    )
    assert "## Operator addenda (Phase D W116b post-mortem)" in prompt
    assert "Pocket EUR_USD/usd_complacency shows no skill" in prompt
    # Addenda block must appear BEFORE the steelman instruction (so the
    # model takes them as adversarial context, not after-thought).
    addenda_idx = prompt.index("## Operator addenda")
    steelman_idx = prompt.index("Steelman the OPPOSITE bias")
    assert addenda_idx < steelman_idx
    # Pre-existing Pass 2 specialization section remains.
    assert "Pass 2 specialization" in prompt


def test_stress_parse_ok() -> None:
    p = StressPass()
    out = p.parse(_wrap(STRESS_OK_JSON))
    assert len(out.counter_claims) >= 1
    assert 0 <= out.revised_conviction_pct <= 95


def test_stress_parse_rejects_revised_above_95() -> None:
    p = StressPass()
    bad = dict(STRESS_OK_JSON)
    bad["revised_conviction_pct"] = 99.0
    with pytest.raises(PassError):
        p.parse(_wrap(bad))


# ─────────────────────── Pass 4 — invalidation ────────────────────────


def test_invalidation_build_prompt_includes_both_inputs() -> None:
    p = InvalidationPass()
    spec = AssetSpecialization.model_validate(ASSET_OK_JSON)
    stress = StressTest.model_validate(STRESS_OK_JSON)
    prompt = p.build_prompt(specialization=spec, stress=stress)
    assert "Specialization" in prompt
    assert "Stress-test" in prompt


def test_invalidation_parse_ok() -> None:
    p = InvalidationPass()
    out = p.parse(_wrap(INVALIDATION_OK_JSON))
    assert len(out.conditions) >= 1
    assert 1 <= out.review_window_hours <= 168


def test_invalidation_parse_rejects_empty_conditions() -> None:
    p = InvalidationPass()
    bad = {"conditions": [], "review_window_hours": 8}
    with pytest.raises(PassError):
        p.parse(_wrap(bad))
