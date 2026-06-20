"""S06 Chantier C — ``geopolitics_vote.build_geopolitics_vote`` producer tests.

Pure unit tests (no DB, no LLM): the mapper is a deterministic primitive
(``geopolitics_vote.py``). Coverage:

  1. the mapper in isolation — the NON-DIRECTIONAL contract (ADR-017), the
     above-baseline AI-GPR z-score strength mapping (anchored on the in-repo
     ``geopol_flash_check.ALERT_Z_ABS_FLOOR`` = 2.0 spike bar), lag-aware freshness
     decay (8-day publication lag), and every honest-absence gate (ADR-103);
  2. the mapper *integrated* into ``conviction_fusion.fuse_conviction(votes=...)`` —
     proving a geo vote moves conviction the right way via anti-uncertainty credit only,
     NEVER flips or sets direction (ADR-017), never appears as a disagreement, cannot
     rescue an honest coin-flip, and that an absent vote is byte-identical to no vote
     (ADR-103).

Doctrine anchors verified 2026-06-20 (Caldara-Iacoviello AI-GPR + IMF GFSR + NY Fed
global-risk-dollar + the in-repo flash check's "direction is regime-dependent" caveat):
geopolitical risk is a market-wide anti-uncertainty MAGNITUDE, NOT a per-asset tilt —
the FX/USD sign flips by regime, so a fixed directional sign would be a fake edge. See
``geopolitics_vote.py`` module docstring for sources.
"""

from __future__ import annotations

import math
import re

import pytest
from ichor_api.services.conviction_fusion import VOTE_GAIN_K, fuse_conviction
from ichor_api.services.dimension_vote import DimensionVote
from ichor_api.services.geopolitics_vote import (
    GPR_BASELINE_Z,
    GPR_FULL_STRENGTH_Z,
    GPR_MAX_AGE_DAYS,
    GPR_PUBLICATION_LAG_DAYS,
    PROVENANCE,
    build_geopolitics_vote,
)

# Same proven CI-clean trade-token regex as test_volume_vote.py / test_cot_vote.py.
_FORBIDDEN_RE = re.compile(
    r"\b(BUY|SELL|TP|SL|long entry|short entry|stop loss|take profit)\b",
    re.IGNORECASE,
)

_FRESH_AGE = GPR_PUBLICATION_LAG_DAYS  # a just-published (~8-day-old) reading → freshness 1.0
_EFFECTIVE_WINDOW = GPR_MAX_AGE_DAYS - GPR_PUBLICATION_LAG_DAYS  # 14 - 8 = 6


def _vote(
    *,
    status: str = "fresh",
    z_score: float | None = GPR_FULL_STRENGTH_Z,  # default = full-strength spike read
    age_days: int | None = _FRESH_AGE,
) -> DimensionVote:
    """Default = a clean full-strength (z = 2.0) just-published AI-GPR spike read."""
    return build_geopolitics_vote(status=status, z_score=z_score, age_days=age_days)


def _scn(bull: float, bear: float) -> list[dict[str, object]]:
    """7-bucket Pass-6 decomposition (mirror test_volume_vote._scn):
    bullish_mass == ``bull``, bearish_mass == ``bear``, sum(p) == 1.0."""
    base = max(0.0, 1.0 - bull - bear)
    return [
        {"label": "crash_flush", "p": 0.0},
        {"label": "strong_bear", "p": bear},
        {"label": "mild_bear", "p": 0.0},
        {"label": "base", "p": base},
        {"label": "mild_bull", "p": 0.0},
        {"label": "strong_bull", "p": bull},
        {"label": "melt_up", "p": 0.0},
    ]


# --------------------------------------------------------------------------- #
# Non-directional contract (ADR-017)                                           #
# --------------------------------------------------------------------------- #


def test_vote_is_always_non_directional() -> None:
    v = _vote()
    assert v.provenance == PROVENANCE == "geopolitics"
    assert v.directional is False
    assert v.direction_hint == "neutral"
    assert v.honest_absence is False
    assert v.is_effective is True


def test_non_directional_contributes_only_uncertainty_credit() -> None:
    """A geo vote NEVER tilts long/short: signed_contribution is 0, the credit ≥ 0."""
    v = _vote()
    assert v.signed_contribution() == 0.0
    assert v.uncertainty_credit() > 0.0
    assert 0.0 <= v.uncertainty_credit() <= 1.0


def test_full_strength_read_scores_one() -> None:
    v = _vote(z_score=GPR_FULL_STRENGTH_Z, age_days=_FRESH_AGE)
    assert v.strength == pytest.approx(1.0)
    assert v.freshness == pytest.approx(1.0)
    assert v.uncertainty_credit() == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# Strength mapping (anchored on the GEOPOL_FLASH |z|>=2.0 spike bar)           #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("z", "expected"),
    [
        (-2.0, 0.0),  # unusually CALM GPR → not a driver → 0 (signed, not |z|)
        (0.0, 0.0),  # at the mean → 0
        (GPR_BASELINE_Z, 0.0),  # 0.5σ baseline → still 0 (no new pressure)
        (1.0, (1.0 - 0.5) / (2.0 - 0.5)),  # ~0.3333
        (1.25, 0.5),  # midpoint → 0.5
        (GPR_FULL_STRENGTH_Z, 1.0),  # 2.0σ spike (alert floor) → full
        (3.0, 1.0),  # spike beyond full → clamped to 1.0
        (50.0, 1.0),  # absurd spike → still clamped (never > 1)
    ],
)
def test_strength_mapping(z: float, expected: float) -> None:
    v = _vote(z_score=z, age_days=_FRESH_AGE)
    assert v.strength == pytest.approx(expected)
    assert 0.0 <= v.strength <= 1.0


def test_below_baseline_is_present_but_zero_strength_not_absent() -> None:
    """A near-mean reading is HONEST "no elevated driver": present, strength 0, contributes
    0 — but NOT honest_absence (the data exists, geopolitical risk is just calm)."""
    v = _vote(z_score=0.0)
    assert v.honest_absence is False
    assert v.strength == 0.0
    assert v.is_effective is False  # strength 0 → ineffective
    assert v.uncertainty_credit() == 0.0
    assert v.signed_contribution() == 0.0


def test_negative_z_is_calm_not_a_credit() -> None:
    """A deeply-negative z (GPR far below baseline) is the absence of a driver, never a
    credit — the signed-z design (NOT |z|) makes calm score 0, unlike the alert's |z|."""
    v = _vote(z_score=-3.0)
    assert v.strength == 0.0
    assert v.is_effective is False


# --------------------------------------------------------------------------- #
# Freshness decay (lag-aware: 8-day publication lag, 14-day window)            #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("age", "expected"),
    [
        (0, 1.0),  # impossibly fresh → 1.0
        (GPR_PUBLICATION_LAG_DAYS, 1.0),  # just-published (~8d) → 1.0 (lag absorbed)
        (GPR_PUBLICATION_LAG_DAYS + 3, 1.0 - 3.0 / _EFFECTIVE_WINDOW),  # 0.5
        (GPR_MAX_AGE_DAYS, 0.0),  # at the window edge → 0
    ],
)
def test_freshness_lag_aware_decay(age: int, expected: float) -> None:
    v = _vote(z_score=GPR_FULL_STRENGTH_Z, age_days=age)
    assert v.freshness == pytest.approx(expected)


def test_window_edge_age_makes_vote_ineffective() -> None:
    """age == max_age → freshness 0 → contributes 0 even at a full-strength spike."""
    v = _vote(z_score=GPR_FULL_STRENGTH_Z, age_days=GPR_MAX_AGE_DAYS)
    assert v.freshness == 0.0
    assert v.is_effective is False
    assert v.uncertainty_credit() == 0.0


# --------------------------------------------------------------------------- #
# Honest-absence gates (ADR-103) — each contributes EXACTLY 0                  #
# --------------------------------------------------------------------------- #


def _assert_absent(v: DimensionVote) -> None:
    assert v.honest_absence is True
    assert v.directional is False
    assert v.direction_hint == "neutral"
    assert v.strength == 0.0
    assert v.is_effective is False
    assert v.signed_contribution() == 0.0
    assert v.uncertainty_credit() == 0.0


@pytest.mark.parametrize("status", ["stale", "absent", "unknown", ""])
def test_non_fresh_status_abstains_fail_closed(status: str) -> None:
    _assert_absent(_vote(status=status))


def test_missing_age_abstains() -> None:
    _assert_absent(_vote(age_days=None))


def test_missing_zscore_abstains() -> None:
    """z_score=None = not-yet-warm window (< 20 obs) or degenerate zero-std baseline."""
    _assert_absent(_vote(z_score=None))


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_corrupted_zscore_abstains(bad: float) -> None:
    _assert_absent(_vote(z_score=bad))


# --------------------------------------------------------------------------- #
# Construction safety — strength/freshness always in [0, 1] across a sweep     #
# --------------------------------------------------------------------------- #


def test_strength_freshness_always_bounded() -> None:
    for z in (-5.0, -1.0, 0.0, 0.5, 1.0, 2.0, 3.0, 10.0, 100.0):
        for age in range(GPR_MAX_AGE_DAYS + 5):
            v = _vote(z_score=z, age_days=age)
            assert 0.0 <= v.strength <= 1.0
            assert 0.0 <= v.freshness <= 1.0


# --------------------------------------------------------------------------- #
# Fuser integration (conviction_fusion.fuse_conviction(votes=...))            #
# --------------------------------------------------------------------------- #


def _conv(votes: tuple[DimensionVote, ...]) -> float:
    """Conviction for a clean up-edge (60/40), no legacy evidence, with given votes."""
    return fuse_conviction(asset="XAU_USD", scenarios=_scn(0.60, 0.40), votes=votes).conviction_pct


def test_geo_vote_raises_conviction_via_anti_uncertainty() -> None:
    """A full-strength geo vote lifts conviction by the agreement factor (anti-uncertainty
    credit), exactly like the ``theme`` / ``volume`` presence layers — bounded, never
    manufacturing certainty."""
    base = _conv(())
    boosted = _conv((_vote(),))  # full credit 1.0
    assert base == pytest.approx(60.0)
    # net_vote += uncertainty_credit (1.0) → agreement_factor 1 + VOTE_GAIN_K*1.0.
    assert boosted == pytest.approx(60.0 * (1.0 + VOTE_GAIN_K))
    assert boosted > base


def test_geo_vote_never_sets_or_flips_direction() -> None:
    """ADR-017: direction is bucket-derived. A geo vote present on a down-edge keeps the
    direction down, and on an up-edge keeps it up — for every asset (global vote)."""
    for asset in ("XAU_USD", "SPX500_USD", "EUR_USD", "GBP_USD", "NAS100_USD"):
        up = fuse_conviction(asset=asset, scenarios=_scn(0.60, 0.40), votes=(_vote(),))
        down = fuse_conviction(asset=asset, scenarios=_scn(0.40, 0.60), votes=(_vote(),))
        assert up.direction == "up"
        assert down.direction == "down"


def test_geo_vote_appears_as_agreeing_never_disagreeing() -> None:
    g = fuse_conviction(asset="XAU_USD", scenarios=_scn(0.60, 0.40), votes=(_vote(),))
    assert PROVENANCE in g.agreeing
    assert PROVENANCE not in g.disagreeing


def test_absent_geo_vote_is_byte_identical_to_no_vote() -> None:
    """ADR-103: an absent vote contributes EXACTLY 0 → same conviction as votes=()."""
    no_vote = fuse_conviction(asset="XAU_USD", scenarios=_scn(0.60, 0.40), votes=())
    absent = fuse_conviction(
        asset="XAU_USD", scenarios=_scn(0.60, 0.40), votes=(_vote(status="stale"),)
    )
    assert absent.conviction_pct == no_vote.conviction_pct
    assert absent.direction == no_vote.direction
    assert absent.agreeing == no_vote.agreeing
    assert absent.disagreeing == no_vote.disagreeing


def test_geo_vote_cannot_rescue_an_honest_coinflip() -> None:
    """A hard dead-zone (spread ≤ 0.05) stays neutral/0 even with a full geo vote —
    evidence cannot manufacture a direction out of a coin-flip (doctrine #11)."""
    g = fuse_conviction(asset="XAU_USD", scenarios=_scn(0.50, 0.48), votes=(_vote(),))
    assert g.direction == "neutral"
    assert g.conviction_pct == 0.0


def test_below_baseline_vote_does_not_change_conviction() -> None:
    """A present-but-strength-0 read (≤ 0.5σ baseline) contributes 0 → conviction unchanged."""
    base = _conv(())
    flat = _conv((_vote(z_score=0.0),))
    assert flat == pytest.approx(base)


def test_no_trade_tokens_in_fused_rationale_with_geo_vote() -> None:
    g = fuse_conviction(asset="XAU_USD", scenarios=_scn(0.60, 0.40), votes=(_vote(),))
    assert _FORBIDDEN_RE.search(g.rationale_fr) is None
