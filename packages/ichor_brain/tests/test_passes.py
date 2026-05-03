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
        "EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD",
        "XAU_USD", "NAS100_USD", "SPX500_USD",
        "US100", "US30",  # ADR-017 ticker aliases
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
