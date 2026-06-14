"""S06 Chantier C · C-3 slice — ``volume_vote.build_volume_vote`` producer tests.

Pure unit tests (no DB, no LLM): the mapper is a deterministic primitive
(``volume_vote.py``). Coverage:

  1. the mapper in isolation — the NON-DIRECTIONAL contract (ADR-017), the
     above-baseline RVOL strength mapping (anchored on the in-repo ``_volume_bucket``
     "elevated" cut + the web "strong interest" band), linear freshness decay, and
     every honest-absence gate (ADR-103);
  2. the mapper *integrated* into ``conviction_fusion.fuse_conviction(votes=...)`` —
     proving a volume vote moves conviction the right way via anti-uncertainty credit
     only, NEVER flips or sets direction (ADR-017), never appears as a disagreement,
     cannot rescue an honest coin-flip, and that an absent vote is byte-identical to no
     vote (ADR-103).

Doctrine anchors verified 2026-06-14 (StockCharts RVOL + Dow-theory volume-confirms-
trend + FX-has-no-venue-volume): volume is non-directional participation; below the
"elevated" cut adds no confirmation; full credit only at a 3× strong-participation read.
See ``volume_vote.py`` module docstring for sources.
"""

from __future__ import annotations

import math
import re

import pytest
from ichor_api.services.conviction_fusion import VOTE_GAIN_K, fuse_conviction
from ichor_api.services.dimension_vote import DimensionVote
from ichor_api.services.volume_vote import (
    PROVENANCE,
    VOLUME_BASELINE_RVOL,
    VOLUME_FULL_STRENGTH_RVOL,
    VOLUME_MAX_AGE_DAYS,
    build_volume_vote,
)

# Same proven CI-clean trade-token regex as test_conviction_fusion.py / test_cot_vote.py.
_FORBIDDEN_RE = re.compile(
    r"\b(BUY|SELL|TP|SL|long entry|short entry|stop loss|take profit)\b",
    re.IGNORECASE,
)

_FRESH_AGE = 0  # a same-day bar → freshness 1.0


def _vote(
    *,
    asset: str = "SPX500_USD",
    status: str = "fresh",
    volume_available: bool = True,
    rvol_ratio: float | None = VOLUME_FULL_STRENGTH_RVOL,  # default = full-strength read
    age_days: int | None = _FRESH_AGE,
    volume_zscore: float | None = None,
) -> DimensionVote:
    """Default = a clean full-strength (3.0×) fresh SPX500 participation read."""
    return build_volume_vote(
        asset=asset,
        status=status,
        volume_available=volume_available,
        rvol_ratio=rvol_ratio,
        age_days=age_days,
        volume_zscore=volume_zscore,
    )


def _scn(bull: float, bear: float) -> list[dict[str, object]]:
    """7-bucket Pass-6 decomposition (mirror test_fuser_golden_harness._scn):
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
    assert v.provenance == PROVENANCE == "volume"
    assert v.directional is False
    assert v.direction_hint == "neutral"
    assert v.honest_absence is False
    assert v.is_effective is True


def test_non_directional_contributes_only_uncertainty_credit() -> None:
    """A volume vote NEVER tilts long/short: signed_contribution is 0, the credit ≥ 0."""
    v = _vote()
    assert v.signed_contribution() == 0.0
    assert v.uncertainty_credit() > 0.0
    assert 0.0 <= v.uncertainty_credit() <= 1.0


def test_full_strength_read_scores_one() -> None:
    v = _vote(rvol_ratio=VOLUME_FULL_STRENGTH_RVOL, age_days=_FRESH_AGE)
    assert v.strength == pytest.approx(1.0)
    assert v.freshness == pytest.approx(1.0)
    assert v.uncertainty_credit() == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# Strength mapping (anchored on _volume_bucket cut + web "strong interest")    #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("rvol", "expected"),
    [
        (0.5, 0.0),  # very light → below baseline → 0
        (1.0, 0.0),  # exactly average → 0
        (VOLUME_BASELINE_RVOL, 0.0),  # 1.25 "elevated" cut → still 0 (no extra confirmation)
        (2.0, (2.0 - 1.25) / (3.0 - 1.25)),  # web "elevated floor" → ~0.4286
        (2.125, 0.5),  # midpoint → 0.5
        (VOLUME_FULL_STRENGTH_RVOL, 1.0),  # 3.0 "strong interest" → full
        (5.0, 1.0),  # spike beyond full → clamped to 1.0
        (50.0, 1.0),  # absurd spike → still clamped (never > 1)
    ],
)
def test_strength_mapping(rvol: float, expected: float) -> None:
    v = _vote(rvol_ratio=rvol, age_days=_FRESH_AGE)
    assert v.strength == pytest.approx(expected)
    assert 0.0 <= v.strength <= 1.0


def test_below_baseline_is_present_but_zero_strength_not_absent() -> None:
    """A thin / average read is HONEST "no confirmation": present, strength 0, contributes
    0 — but NOT honest_absence (the data exists, it just corroborates nothing)."""
    v = _vote(rvol_ratio=1.0)
    assert v.honest_absence is False
    assert v.strength == 0.0
    assert v.is_effective is False  # strength 0 → ineffective
    assert v.uncertainty_credit() == 0.0
    assert v.signed_contribution() == 0.0


# --------------------------------------------------------------------------- #
# Freshness decay (daily data, no publication lag)                            #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("age", "expected"),
    [
        (0, 1.0),
        (1, 1.0 - 1.0 / VOLUME_MAX_AGE_DAYS),  # 0.8
        (3, 1.0 - 3.0 / VOLUME_MAX_AGE_DAYS),  # 0.4
        (VOLUME_MAX_AGE_DAYS, 0.0),  # at the window edge → 0
    ],
)
def test_freshness_decay(age: int, expected: float) -> None:
    v = _vote(rvol_ratio=VOLUME_FULL_STRENGTH_RVOL, age_days=age)
    assert v.freshness == pytest.approx(expected)


def test_window_edge_age_makes_vote_ineffective() -> None:
    """age == max_age → freshness 0 → contributes 0 (a barely-fresh read corroborates
    nothing), even at full RVOL strength. Honest, not absent."""
    v = _vote(rvol_ratio=VOLUME_FULL_STRENGTH_RVOL, age_days=VOLUME_MAX_AGE_DAYS)
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


def test_fx_asset_abstains() -> None:
    _assert_absent(_vote(asset="EUR_USD"))
    _assert_absent(_vote(asset="USD_JPY"))


def test_unknown_asset_abstains() -> None:
    _assert_absent(_vote(asset="ZZZ_ZZZ"))


def test_spx500_off_whitelist_guard_is_explicit() -> None:
    """The three volume-bearing assets vote; everything else abstains."""
    for asset in ("SPX500_USD", "NAS100_USD", "XAU_USD"):
        assert _vote(asset=asset).honest_absence is False
    for asset in ("EUR_USD", "GBP_USD", "AUD_USD", "USD_CAD", "USD_JPY"):
        assert _vote(asset=asset).honest_absence is True


def test_volume_unavailable_abstains() -> None:
    _assert_absent(_vote(volume_available=False))


@pytest.mark.parametrize("status", ["stale", "absent", "unknown", ""])
def test_non_fresh_status_abstains_fail_closed(status: str) -> None:
    _assert_absent(_vote(status=status))


def test_missing_age_abstains() -> None:
    _assert_absent(_vote(age_days=None))


def test_missing_rvol_ratio_abstains() -> None:
    _assert_absent(_vote(rvol_ratio=None))


@pytest.mark.parametrize("bad", [0.0, -1.0, -0.5, math.nan, math.inf, -math.inf])
def test_corrupted_rvol_ratio_abstains(bad: float) -> None:
    _assert_absent(_vote(rvol_ratio=bad))


# --------------------------------------------------------------------------- #
# Construction safety — strength/freshness always in [0, 1] across a sweep     #
# --------------------------------------------------------------------------- #


def test_strength_freshness_always_bounded() -> None:
    for rvol in (0.01, 0.5, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0, 10.0, 100.0):
        for age in range(VOLUME_MAX_AGE_DAYS + 1):
            v = _vote(rvol_ratio=rvol, age_days=age)
            assert 0.0 <= v.strength <= 1.0
            assert 0.0 <= v.freshness <= 1.0


def test_zscore_param_accepted_but_dormant() -> None:
    """The optional z-score is accepted (reserved for S05 Brier-fit) and does NOT change
    today's output — the smooth rvol_ratio is the sole magnitude driver."""
    base = _vote(rvol_ratio=2.0, volume_zscore=None)
    with_z = _vote(rvol_ratio=2.0, volume_zscore=5.0)
    assert base.strength == with_z.strength
    assert base.freshness == with_z.freshness


# --------------------------------------------------------------------------- #
# Fuser integration (conviction_fusion.fuse_conviction(votes=...))            #
# --------------------------------------------------------------------------- #


def _conv(votes: tuple[DimensionVote, ...]) -> float:
    """Conviction for a clean up-edge (60/40), no legacy evidence, with given votes."""
    return fuse_conviction(
        asset="SPX500_USD", scenarios=_scn(0.60, 0.40), votes=votes
    ).conviction_pct


def test_volume_vote_raises_conviction_via_anti_uncertainty() -> None:
    """A full-strength volume vote lifts conviction by the agreement factor (anti-
    uncertainty credit), exactly like the ``theme`` presence layer — bounded, never
    manufacturing certainty."""
    base = _conv(())
    boosted = _conv((_vote(),))  # full credit 1.0
    assert base == pytest.approx(60.0)
    # net_vote += uncertainty_credit (1.0) → agreement_factor 1 + VOTE_GAIN_K*1.0 = 1.10.
    assert boosted == pytest.approx(60.0 * (1.0 + VOTE_GAIN_K))
    assert boosted > base


def test_volume_vote_never_sets_or_flips_direction() -> None:
    """ADR-017: direction is bucket-derived. A volume vote present on a down-edge keeps
    the direction down, and on an up-edge keeps it up."""
    up = fuse_conviction(asset="SPX500_USD", scenarios=_scn(0.60, 0.40), votes=(_vote(),))
    down = fuse_conviction(asset="SPX500_USD", scenarios=_scn(0.40, 0.60), votes=(_vote(),))
    assert up.direction == "up"
    assert down.direction == "down"


def test_volume_vote_appears_as_agreeing_never_disagreeing() -> None:
    g = fuse_conviction(asset="SPX500_USD", scenarios=_scn(0.60, 0.40), votes=(_vote(),))
    assert PROVENANCE in g.agreeing
    assert PROVENANCE not in g.disagreeing


def test_absent_volume_vote_is_byte_identical_to_no_vote() -> None:
    """ADR-103: an absent vote contributes EXACTLY 0 → same conviction as votes=()."""
    no_vote = fuse_conviction(asset="SPX500_USD", scenarios=_scn(0.60, 0.40), votes=())
    absent = fuse_conviction(
        asset="SPX500_USD", scenarios=_scn(0.60, 0.40), votes=(_vote(asset="EUR_USD"),)
    )
    assert absent.conviction_pct == no_vote.conviction_pct
    assert absent.direction == no_vote.direction
    assert absent.agreeing == no_vote.agreeing
    assert absent.disagreeing == no_vote.disagreeing


def test_volume_vote_cannot_rescue_an_honest_coinflip() -> None:
    """A hard dead-zone (spread ≤ 0.05) stays neutral/0 even with a full volume vote —
    evidence cannot manufacture a direction out of a coin-flip (doctrine #11)."""
    g = fuse_conviction(asset="SPX500_USD", scenarios=_scn(0.50, 0.48), votes=(_vote(),))
    assert g.direction == "neutral"
    assert g.conviction_pct == 0.0


def test_below_baseline_vote_does_not_change_conviction() -> None:
    """A present-but-strength-0 read (≤ elevated cut) contributes 0 → conviction unchanged."""
    base = _conv(())
    flat = _conv((_vote(rvol_ratio=1.0),))
    assert flat == pytest.approx(base)


def test_no_trade_tokens_in_fused_rationale_with_volume_vote() -> None:
    g = fuse_conviction(asset="SPX500_USD", scenarios=_scn(0.60, 0.40), votes=(_vote(),))
    assert _FORBIDDEN_RE.search(g.rationale_fr) is None
