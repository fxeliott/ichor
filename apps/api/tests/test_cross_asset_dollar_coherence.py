"""Tests for cross_asset_dollar_coherence — the 'tout interconnecté' gate.

Covers the stance mapping (incl. the USD/CAD base-currency sign flip), the
2026-05-29 incoherence scenario that motivated the module, neutral/empty
edge cases, conviction weighting, the demote-only suggestion, and the
ADR-017 cleanliness of the generated French coach text.
"""

from __future__ import annotations

import pytest
from ichor_api.services import adr017_filter
from ichor_api.services.cross_asset_dollar_coherence import (
    assess_dollar_coherence,
    implied_usd_stance,
)

# ── implied_usd_stance ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("asset", "bias", "expected"),
    [
        # XXX/USD pairs + gold + indices : long asset → softer USD.
        ("EUR_USD", "long", "usd_down"),
        ("EUR_USD", "short", "usd_up"),
        ("GBP_USD", "long", "usd_down"),
        ("GBP_USD", "short", "usd_up"),
        ("XAU_USD", "long", "usd_down"),
        ("XAU_USD", "short", "usd_up"),
        ("SPX500_USD", "long", "usd_down"),
        ("SPX500_USD", "short", "usd_up"),
        ("NAS100_USD", "long", "usd_down"),
        ("NAS100_USD", "short", "usd_up"),
        # USD/XXX pairs : USD is the BASE → sign flips.
        ("USD_CAD", "long", "usd_up"),
        ("USD_CAD", "short", "usd_down"),
        ("USD_JPY", "long", "usd_up"),
        ("USD_JPY", "short", "usd_down"),
        # neutral / invalid → neutral.
        ("EUR_USD", "neutral", "neutral"),
        ("EUR_USD", "garbage", "neutral"),
    ],
)
def test_implied_usd_stance(asset: str, bias: str, expected: str) -> None:
    assert implied_usd_stance(asset, bias) == expected


# ── the motivating incoherence (2026-05-29 post-mortem) ─────────────────


def test_2026_05_29_incoherence_is_flagged() -> None:
    """bearish EUR + bearish gold (USD↑) but bullish equities (USD↓)."""
    cards = [
        {"asset": "EUR_USD", "bias": "short", "conviction": 60},
        {"asset": "XAU_USD", "bias": "short", "conviction": 55},
        {"asset": "SPX500_USD", "bias": "long", "conviction": 50},
        {"asset": "NAS100_USD", "bias": "long", "conviction": 50},
    ]
    v = assess_dollar_coherence(cards)
    # EUR(1.0)+XAU(0.6) lean USD-up dominates SPX(0.4)+NAS(0.4) USD-down.
    assert v.consensus == "usd_up"
    assert v.coherent is False
    # The two equity cards fight the strong-dollar consensus.
    assert set(v.outliers) == {"SPX500_USD", "NAS100_USD"}
    # Demote-only suggestion present for each outlier, strictly below original.
    for a in v.outliers:
        assert v.recommended_demotions[a] < 50
    assert "Incohérence" in v.coach_explanation


def test_dollar_consistent_view_is_coherent() -> None:
    """bearish EUR + bearish gold + bearish equities = uniformly USD-up."""
    cards = [
        {"asset": "EUR_USD", "bias": "short", "conviction": 60},
        {"asset": "XAU_USD", "bias": "short", "conviction": 50},
        {"asset": "SPX500_USD", "bias": "short", "conviction": 45},
    ]
    v = assess_dollar_coherence(cards)
    assert v.consensus == "usd_up"
    assert v.coherent is True
    assert v.outliers == ()
    assert "cohérents" in v.coach_explanation


def test_risk_on_consistent_view_is_coherent() -> None:
    """bullish EUR + bullish gold + bullish equities = uniformly USD-down."""
    cards = [
        {"asset": "EUR_USD", "bias": "long", "conviction": 55},
        {"asset": "XAU_USD", "bias": "long", "conviction": 50},
        {"asset": "NAS100_USD", "bias": "long", "conviction": 60},
    ]
    v = assess_dollar_coherence(cards)
    assert v.consensus == "usd_down"
    assert v.coherent is True
    assert v.outliers == ()


def test_usd_cad_sign_flip_is_coherent_with_strong_dollar() -> None:
    """USD/CAD long (USD↑) alongside EUR short (USD↑) is COHERENT, not an outlier."""
    cards = [
        {"asset": "EUR_USD", "bias": "short", "conviction": 60},
        {"asset": "USD_CAD", "bias": "long", "conviction": 55},
    ]
    v = assess_dollar_coherence(cards)
    assert v.consensus == "usd_up"
    assert v.coherent is True
    assert v.outliers == ()


# ── consensus shapes ────────────────────────────────────────────────────


def test_mixed_consensus_when_split() -> None:
    """One USD-up vs one USD-down at equal weight/conviction → genuinely split."""
    cards = [
        {"asset": "EUR_USD", "bias": "short", "conviction": 50},  # usd_up 1.0
        {"asset": "GBP_USD", "bias": "long", "conviction": 50},  # usd_down 0.9
    ]
    v = assess_dollar_coherence(cards)
    # net = 0.5 - 0.45 = 0.05 ; total = 0.95 ; strength ≈ 0.053 < 0.20 → mixed.
    assert v.consensus == "mixed"
    # mixed is not "clean" → no outliers flagged (we don't punish on a split).
    assert v.outliers == ()
    assert "tiraillé" in v.coach_explanation


def test_low_conviction_contrarian_is_not_an_outlier() -> None:
    """A 15%-conviction card against the consensus is noise, not a contradiction."""
    cards = [
        {"asset": "EUR_USD", "bias": "short", "conviction": 70},
        {"asset": "GBP_USD", "bias": "short", "conviction": 65},
        {"asset": "XAU_USD", "bias": "long", "conviction": 15},  # weak contrarian
    ]
    v = assess_dollar_coherence(cards)
    assert v.consensus == "usd_up"
    assert "XAU_USD" not in v.outliers


# ── edge cases (never fabricate a contradiction) ────────────────────────


def test_empty_input_is_coherent_neutral() -> None:
    v = assess_dollar_coherence([])
    assert v.consensus == "neutral"
    assert v.coherent is True
    assert v.outliers == ()
    assert v.n_directional == 0


def test_none_input_is_coherent_neutral() -> None:
    v = assess_dollar_coherence(None)
    assert v.consensus == "neutral"
    assert v.coherent is True


def test_single_directional_card_no_consensus() -> None:
    v = assess_dollar_coherence([{"asset": "EUR_USD", "bias": "short", "conviction": 80}])
    assert v.consensus == "neutral"  # < 2 directional votes → nothing to reconcile
    assert v.coherent is True
    assert v.n_directional == 1


def test_all_neutral_cards() -> None:
    cards = [
        {"asset": "EUR_USD", "bias": "neutral", "conviction": 30},
        {"asset": "XAU_USD", "bias": "neutral", "conviction": 20},
    ]
    v = assess_dollar_coherence(cards)
    assert v.consensus == "neutral"
    assert v.n_directional == 0


def test_alternate_key_names_and_fraction_conviction() -> None:
    """Accept bias_direction / conviction_pct + 0..1 fraction conviction."""
    cards = [
        {"asset": "EUR_USD", "bias_direction": "short", "conviction_pct": 0.6},
        {"asset": "XAU_USD", "bias_direction": "short", "conviction_pct": 0.5},
    ]
    v = assess_dollar_coherence(cards)
    assert v.consensus == "usd_up"
    # 0.6 fraction must have been scaled to 60 %, not treated as ~0.
    eur = next(x for x in v.views if x.asset == "EUR_USD")
    assert eur.conviction == pytest.approx(60.0)


def test_duplicate_asset_is_deduped() -> None:
    cards = [
        {"asset": "EUR_USD", "bias": "short", "conviction": 60},
        {"asset": "EUR_USD", "bias": "long", "conviction": 90},  # ignored
        {"asset": "XAU_USD", "bias": "short", "conviction": 50},
    ]
    v = assess_dollar_coherence(cards)
    assert len([x for x in v.views if x.asset == "EUR_USD"]) == 1
    assert v.consensus == "usd_up"


def test_malformed_entries_are_skipped() -> None:
    cards = [
        "not a mapping",  # type: ignore[list-item]
        {"no_asset": True},
        {"asset": 123, "bias": "short"},  # asset not a str
        {"asset": "EUR_USD", "bias": "short", "conviction": 60},
        {"asset": "XAU_USD", "bias": "short", "conviction": 50},
    ]
    v = assess_dollar_coherence(cards)  # type: ignore[arg-type]
    assert {x.asset for x in v.views} == {"EUR_USD", "XAU_USD"}


# ── ADR-017 boundary ────────────────────────────────────────────────────


def test_coach_explanation_is_adr017_clean_across_scenarios() -> None:
    scenarios = [
        [
            {"asset": "EUR_USD", "bias": "short", "conviction": 60},
            {"asset": "XAU_USD", "bias": "short", "conviction": 55},
            {"asset": "SPX500_USD", "bias": "long", "conviction": 50},
        ],
        [
            {"asset": "EUR_USD", "bias": "long", "conviction": 55},
            {"asset": "GBP_USD", "bias": "long", "conviction": 50},
        ],
        [
            {"asset": "EUR_USD", "bias": "short", "conviction": 50},
            {"asset": "GBP_USD", "bias": "long", "conviction": 50},
        ],
        [],
    ]
    for cards in scenarios:
        v = assess_dollar_coherence(cards)
        # find_violations returns an (empty) list — assert falsy, not `== ()`.
        assert not adr017_filter.find_violations(v.coach_explanation)
