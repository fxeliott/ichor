"""Tests for the card coherence gate + thesis synthesis (content-correctness).

Anchored on the 5 real live cards from the 2026-05-30 audit so the gate's
behaviour is pinned against ground truth, not invented fixtures.
"""

from __future__ import annotations

import pytest
from ichor_api.services.adr017_filter import is_adr017_clean
from ichor_api.services.card_coherence import (
    BEAR_BUCKETS,
    BULL_BUCKETS,
    NEUTRAL_BUCKETS,
    reconcile_coherence,
    scenario_masses,
    synthesize_thesis,
)


def _scen(**masses: float) -> list[dict]:
    """Build a 7-bucket scenario list from per-label probabilities."""
    return [{"label": k, "p": v, "magnitude_pips": [-50.0, 50.0]} for k, v in masses.items()]


# Real distributions pulled from the live DB on 2026-05-30 (ny_close).
EUR_SCEN = _scen(
    crash_flush=0.02,
    strong_bear=0.12,
    mild_bear=0.22,
    base=0.35,
    mild_bull=0.19,
    strong_bull=0.08,
    melt_up=0.02,
)
GBP_SCEN = _scen(
    crash_flush=0.02,
    strong_bear=0.09,
    mild_bear=0.20,
    base=0.38,
    mild_bull=0.20,
    strong_bull=0.09,
    melt_up=0.02,
)
XAU_SCEN = _scen(
    crash_flush=0.02,
    strong_bear=0.12,
    mild_bear=0.21,
    base=0.31,
    mild_bull=0.22,
    strong_bull=0.09,
    melt_up=0.03,
)
NAS_SCEN = _scen(
    crash_flush=0.03,
    strong_bear=0.10,
    mild_bear=0.22,
    base=0.30,
    mild_bull=0.22,
    strong_bull=0.10,
    melt_up=0.03,
)
SPX_SCEN = _scen(
    crash_flush=0.02,
    strong_bear=0.07,
    mild_bear=0.15,
    base=0.42,
    mild_bull=0.22,
    strong_bull=0.10,
    melt_up=0.02,
)
# EUR drivers summed net-negative (~-0.69) on the live card.
EUR_DRIVERS = [
    {"factor": "daily_levels", "contribution": 0.357},
    {"factor": "inflation_surprise", "contribution": -0.566},
    {"factor": "surprise_index", "contribution": -0.192},
    {"factor": "risk_appetite", "contribution": -0.14},
    {"factor": "vix_term", "contribution": -0.076},
    {"factor": "funding_stress", "contribution": -0.04},
    {"factor": "microstructure_ofi", "contribution": -0.032},
]


def test_bucket_partition_covers_canonical() -> None:
    """The bull/bear/neutral partition must equal the canonical 7 labels."""
    from ichor_brain.scenarios import BUCKET_LABELS

    partition = BULL_BUCKETS | BEAR_BUCKETS | NEUTRAL_BUCKETS
    assert partition == set(BUCKET_LABELS)
    # disjoint
    assert not (BULL_BUCKETS & BEAR_BUCKETS)
    assert not (BULL_BUCKETS & NEUTRAL_BUCKETS)
    assert not (BEAR_BUCKETS & NEUTRAL_BUCKETS)


def test_scenario_masses_eur() -> None:
    bull, bear, base, _ = scenario_masses(EUR_SCEN)
    assert round(bull, 2) == 0.29
    assert round(bear, 2) == 0.36
    assert round(base, 2) == 0.35


def test_eur_long_demoted_to_neutral() -> None:
    """EUR/USD long with net-bearish mass → demoted to neutral (mission-2)."""
    v = reconcile_coherence(
        asset="EUR_USD",
        session_type="ny_close",
        bias="long",
        conviction=21.5,
        scenarios=EUR_SCEN,
        drivers=EUR_DRIVERS,
    )
    assert v.bias == "neutral"
    assert v.agreement == "contradicted"
    assert v.adjusted is True
    assert v.conviction <= 35.0


def test_spx_and_nas_both_neutral_on_overnight() -> None:
    """Mission-4 : SPX (neutral) and NAS (long) converge to neutral overnight."""
    spx = reconcile_coherence(
        asset="SPX500_USD",
        session_type="ny_close",
        bias="neutral",
        conviction=37.5,
        scenarios=SPX_SCEN,
        drivers=None,
    )
    nas = reconcile_coherence(
        asset="NAS100_USD",
        session_type="ny_close",
        bias="long",
        conviction=26.5,
        scenarios=NAS_SCEN,
        drivers=None,
    )
    assert spx.bias == "neutral"
    assert nas.bias == "neutral"  # demoted: equity overnight, lean below 0.12
    assert nas.agreement == "equity_overnight_clamp"
    assert spx.bias == nas.bias  # symmetric treatment


def test_fx_balanced_keeps_direction_shaves_conviction() -> None:
    """GBP/XAU long on a balanced distribution: kept, conviction reduced."""
    gbp = reconcile_coherence(
        asset="GBP_USD",
        session_type="ny_close",
        bias="long",
        conviction=26.0,
        scenarios=GBP_SCEN,
        drivers=None,
    )
    assert gbp.bias == "long"
    assert gbp.conviction < 26.0
    assert gbp.agreement in ("weak", "weak_driver_disagree")


def test_neutral_bias_never_promoted() -> None:
    """A neutral bias is never promoted to directional, even on a leaning mass."""
    v = reconcile_coherence(
        asset="EUR_USD",
        session_type="pre_ny",
        bias="neutral",
        conviction=40.0,
        scenarios=XAU_SCEN,
        drivers=None,
    )
    assert v.bias == "neutral"
    assert v.adjusted is False


def test_aligned_bias_unchanged() -> None:
    """A long bias on a clearly bullish mass with no driver conflict is kept."""
    bullish = _scen(
        crash_flush=0.01,
        strong_bear=0.04,
        mild_bear=0.10,
        base=0.25,
        mild_bull=0.30,
        strong_bull=0.20,
        melt_up=0.10,
    )
    v = reconcile_coherence(
        asset="EUR_USD",
        session_type="pre_ny",
        bias="long",
        conviction=60.0,
        scenarios=bullish,
        drivers=[{"factor": "x", "contribution": 0.5}],
    )
    assert v.bias == "long"
    assert v.agreement == "aligned"
    assert v.conviction == 60.0


def test_conviction_never_exceeds_95() -> None:
    v = reconcile_coherence(
        asset="EUR_USD",
        session_type="pre_ny",
        bias="long",
        conviction=99.0,
        scenarios=None,
        drivers=None,
    )
    assert v.conviction <= 95.0


def test_empty_scenarios_safe() -> None:
    v = reconcile_coherence(
        asset="EUR_USD",
        session_type="pre_ny",
        bias="long",
        conviction=50.0,
        scenarios=[],
        drivers=None,
    )
    # no scenario signal → balanced lean → kept, conviction shaved
    assert v.bias == "long"


def test_thesis_describes_stored_bias_and_flags_tension() -> None:
    """Old card stored as long with bearish mass: thesis flags tension, keeps badge."""
    thesis = synthesize_thesis(
        asset="EUR_USD",
        session_type="ny_close",
        bias="long",
        conviction=21.5,
        regime="usd_complacency",
        scenarios=EUR_SCEN,
        drivers=EUR_DRIVERS,
    )
    assert "EUR/USD" in thesis
    assert "haussier" in thesis  # stored bias described, not flipped
    assert "Tension" in thesis  # disagreement surfaced
    assert len(thesis) <= 512


def test_thesis_neutral_card_coherent() -> None:
    """A reconciled (neutral) card's thesis has no tension flag."""
    thesis = synthesize_thesis(
        asset="EUR_USD",
        session_type="ny_close",
        bias="neutral",
        conviction=21.5,
        regime="usd_complacency",
        scenarios=EUR_SCEN,
        drivers=EUR_DRIVERS,
    )
    assert "neutre" in thesis
    assert "Tension" not in thesis


@pytest.mark.parametrize(
    "asset,bias,scen,drivers",
    [
        ("EUR_USD", "long", EUR_SCEN, EUR_DRIVERS),
        ("GBP_USD", "long", GBP_SCEN, None),
        ("XAU_USD", "long", XAU_SCEN, None),
        ("NAS100_USD", "long", NAS_SCEN, None),
        ("SPX500_USD", "neutral", SPX_SCEN, None),
    ],
)
def test_thesis_is_adr017_clean(asset: str, bias: str, scen: list, drivers: list | None) -> None:
    """The synthesized thesis must never contain ADR-017 forbidden tokens."""
    thesis = synthesize_thesis(
        asset=asset,
        session_type="ny_close",
        bias=bias,
        conviction=25.0,
        regime="usd_complacency",
        scenarios=scen,
        drivers=drivers,
    )
    assert is_adr017_clean(thesis)
