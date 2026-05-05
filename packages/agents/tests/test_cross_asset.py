"""Cross-asset coherence tests for the extended Critic."""

from __future__ import annotations

from ichor_agents.critic import CardSnapshot, review_cards


def _snap(asset: str, dir_: str, conv: float, regime: str | None = None):
    return CardSnapshot(
        asset=asset,
        bias_direction=dir_,  # type: ignore[arg-type]
        conviction_pct=conv,
        regime_quadrant=regime,
    )


def test_empty_input_yields_no_findings() -> None:
    v = review_cards([])
    assert v.is_coherent
    assert v.n_cards_reviewed == 0


def test_single_card_no_cross_check_possible() -> None:
    v = review_cards([_snap("EUR_USD", "long", 65)])
    assert v.is_coherent


def test_dxy_legs_disagree_when_eur_long_and_usdjpy_short() -> None:
    """EUR/USD long ⇒ USD↓ ; USD/JPY short ⇒ USD↓ — coherent."""
    v = review_cards([_snap("EUR_USD", "long", 60), _snap("USD_JPY", "short", 60)])
    assert v.is_coherent


def test_dxy_legs_disagree_when_eur_long_and_usdjpy_long() -> None:
    """EUR/USD long ⇒ USD↓ ; USD/JPY long ⇒ USD↑ — contradictory."""
    v = review_cards([_snap("EUR_USD", "long", 60), _snap("USD_JPY", "long", 60)])
    assert not v.is_coherent
    assert any(f.rule == "dxy_legs_disagree" for f in v.findings)


def test_dxy_disagreement_ignores_low_conviction() -> None:
    """Convictions <40 % should not trigger the rule."""
    v = review_cards([_snap("EUR_USD", "long", 30), _snap("USD_JPY", "long", 30)])
    assert v.is_coherent


def test_xau_and_dxy_double_long_flagged_as_info() -> None:
    """XAU long + EUR/USD short + USD/JPY long = implicit DXY long."""
    v = review_cards(
        [
            _snap("XAU_USD", "long", 60),
            _snap("EUR_USD", "short", 60),
            _snap("USD_JPY", "long", 60),
            _snap("AUD_USD", "short", 60),
        ]
    )
    assert any(f.rule == "xau_and_dxy_both_long" for f in v.findings)
    info_finding = next(f for f in v.findings if f.rule == "xau_and_dxy_both_long")
    assert info_finding.severity == "info"


def test_spx_long_in_funding_stress_flagged_as_warning() -> None:
    v = review_cards([_snap("SPX500_USD", "long", 65, regime="funding_stress")])
    assert any(f.rule == "risk_long_in_funding_stress" for f in v.findings)


def test_spx_long_outside_funding_stress_is_fine() -> None:
    v = review_cards([_snap("SPX500_USD", "long", 65, regime="goldilocks")])
    assert v.is_coherent
