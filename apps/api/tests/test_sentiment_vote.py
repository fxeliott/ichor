"""S06 Chantier C — ``sentiment_vote.build_sentiment_vote`` producer tests.

Pure unit tests (no DB, no LLM). Coverage:

  1. the mapper in isolation — the CONTRARIAN directional read (fade the crowd, the
     OPPOSITE sign to cot_vote), the per-asset whitelist (FX + XAU only), the
     above-floor one-side-% strength, linear freshness decay, and every honest-absence
     gate (ADR-103);
  2. the mapper *integrated* into ``conviction_fusion.fuse_conviction(votes=...)`` —
     contrarian promote/demote, never flips direction (ADR-017), absent == no vote.

Doctrine anchors verified 2026-06-20 (retail = exit liquidity, fade 60-85 % extremes,
< ~65 % = noise). See ``sentiment_vote.py`` module docstring for sources.
"""

from __future__ import annotations

import math
import re

import pytest
from ichor_api.services.conviction_fusion import VOTE_GAIN_K, fuse_conviction
from ichor_api.services.dimension_vote import DimensionVote
from ichor_api.services.sentiment_vote import (
    PROVENANCE,
    SENTIMENT_EXTREME_FLOOR,
    SENTIMENT_FULL_STRENGTH,
    SENTIMENT_MAX_AGE_DAYS,
    build_sentiment_vote,
)

_FORBIDDEN_RE = re.compile(
    r"\b(BUY|SELL|TP|SL|long entry|short entry|stop loss|take profit)\b",
    re.IGNORECASE,
)


def _vote(
    *,
    asset: str = "EUR_USD",
    status: str = "fresh",
    long_pct: float | None = 85.0,  # default: crowd-long extreme → contrarian "down", full
    short_pct: float | None = 15.0,
    age_days: int | None = 0,
):
    return build_sentiment_vote(
        asset=asset, status=status, long_pct=long_pct, short_pct=short_pct, age_days=age_days
    )


def _scn(bull: float, bear: float) -> list[dict[str, object]]:
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
# CONTRARIAN direction (fade the crowd) — the OPPOSITE sign to cot_vote        #
# --------------------------------------------------------------------------- #


def test_crowd_long_extreme_votes_down() -> None:
    v = _vote(long_pct=85.0, short_pct=15.0)
    assert v.provenance == PROVENANCE == "sentiment"
    assert v.direction_hint == "down"  # contrarian: fade the long crowd
    assert v.directional is True
    assert v.strength == pytest.approx(1.0)
    assert v.honest_absence is False


def test_crowd_short_extreme_votes_up() -> None:
    v = _vote(long_pct=12.0, short_pct=88.0)
    assert v.direction_hint == "up"  # contrarian: fade the short crowd
    assert v.strength == pytest.approx(1.0)


def test_no_foreign_leg_reversal_for_xau() -> None:
    # The pair IS the asset (XAUUSD == XAU_USD) → crowd-long gold → contrarian down. No
    # reversal (unlike cot_vote's foreign-leg flip).
    v = _vote(asset="XAU_USD", long_pct=80.0, short_pct=20.0)
    assert v.direction_hint == "down"


# --------------------------------------------------------------------------- #
# Per-asset whitelist (FX + XAU only)                                          #
# --------------------------------------------------------------------------- #


def test_covered_fx_and_gold_vote() -> None:
    for asset in ("EUR_USD", "GBP_USD", "XAU_USD"):
        assert _vote(asset=asset).honest_absence is False


@pytest.mark.parametrize("asset", ["SPX500_USD", "NAS100_USD", "USD_JPY", "ZZZ_ZZZ"])
def test_indices_and_unsupported_assets_abstain(asset: str) -> None:
    v = _vote(asset=asset)
    assert v.honest_absence is True
    assert v.direction_hint == "neutral"
    assert v.strength == 0.0


# --------------------------------------------------------------------------- #
# Strength mapping (60 % floor → 0 ; 85 % → full)                             #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("one_side", "expected"),
    [
        (50.0, 0.0),  # balanced → 0
        (SENTIMENT_EXTREME_FLOOR, 0.0),  # 60 floor → 0
        (72.5, 0.5),  # midpoint → 0.5
        (75.0, (75.0 - 60.0) / (85.0 - 60.0)),  # in-repo extreme flag → 0.6
        (SENTIMENT_FULL_STRENGTH, 1.0),  # 85 → full
        (95.0, 1.0),  # beyond full → clamp 1.0
    ],
)
def test_strength_mapping_crowd_long(one_side: float, expected: float) -> None:
    v = _vote(long_pct=one_side, short_pct=100.0 - one_side)
    assert v.strength == pytest.approx(expected)
    assert 0.0 <= v.strength <= 1.0


def test_below_floor_is_present_but_zero_strength_not_absent() -> None:
    v = _vote(long_pct=55.0, short_pct=45.0)  # mild tilt → noise
    assert v.honest_absence is False
    assert v.strength == 0.0
    assert v.is_effective is False
    assert v.signed_contribution() == 0.0


# --------------------------------------------------------------------------- #
# Freshness decay (window 3, no publication lag)                              #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("age", "expected"),
    [
        (0, 1.0),
        (1, 1.0 - 1.0 / SENTIMENT_MAX_AGE_DAYS),
        (SENTIMENT_MAX_AGE_DAYS, 0.0),
    ],
)
def test_freshness_decay(age: int, expected: float) -> None:
    v = _vote(age_days=age)
    assert v.freshness == pytest.approx(expected)


# --------------------------------------------------------------------------- #
# Honest-absence gates (ADR-103)                                              #
# --------------------------------------------------------------------------- #


def _assert_absent(v: DimensionVote) -> None:
    assert v.honest_absence is True
    assert v.strength == 0.0
    assert v.signed_contribution() == 0.0
    assert v.uncertainty_credit() == 0.0


@pytest.mark.parametrize("status", ["stale", "absent", "unknown", ""])
def test_non_fresh_status_abstains_fail_closed(status: str) -> None:
    _assert_absent(_vote(status=status))


def test_missing_age_abstains() -> None:
    _assert_absent(_vote(age_days=None))


def test_missing_percentages_abstain() -> None:
    _assert_absent(_vote(long_pct=None))
    _assert_absent(_vote(short_pct=None))


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_corrupted_percentages_abstain(bad: float) -> None:
    _assert_absent(_vote(long_pct=bad, short_pct=50.0))


@pytest.mark.parametrize(
    ("lp", "sp"),
    [
        (80.0, 80.0),  # sum 160 → not complementary
        (10.0, 10.0),  # sum 20 → not complementary
        (120.0, -20.0),  # out of range
        (-5.0, 105.0),  # out of range
    ],
)
def test_non_complementary_or_out_of_range_abstain(lp: float, sp: float) -> None:
    _assert_absent(_vote(long_pct=lp, short_pct=sp))


def test_strength_freshness_always_bounded() -> None:
    for one in (50.0, 60.0, 70.0, 85.0, 99.0):
        for age in range(SENTIMENT_MAX_AGE_DAYS + 2):
            v = _vote(long_pct=one, short_pct=100.0 - one, age_days=age)
            assert 0.0 <= v.strength <= 1.0
            assert 0.0 <= v.freshness <= 1.0


# --------------------------------------------------------------------------- #
# Fuser integration                                                          #
# --------------------------------------------------------------------------- #


def test_contrarian_vote_promotes_when_aligned_with_bucket() -> None:
    # Crowd-long EUR → vote "down" → AGREES with a bearish (down) bucket edge → promotes.
    vote = _vote(long_pct=85.0, short_pct=15.0)  # down, strength 1.0
    g = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.40, 0.60), votes=[vote])
    assert g.direction == "down"
    assert "sentiment" in g.agreeing
    assert g.conviction_pct == pytest.approx(60.0 * (1.0 + VOTE_GAIN_K))


def test_contrarian_vote_demotes_but_keeps_direction() -> None:
    # Crowd-long EUR → vote "down" → CONTRADICTS an up bucket edge → demotes, no flip.
    vote = _vote(long_pct=85.0, short_pct=15.0)
    g = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40), votes=[vote])
    assert g.direction == "up"  # bucket-derived (ADR-017)
    assert "sentiment" in g.disagreeing
    assert g.conviction_pct == pytest.approx(60.0 * (1.0 - VOTE_GAIN_K))


def test_absent_sentiment_vote_is_byte_identical_to_no_vote() -> None:
    absent = _vote(asset="SPX500_USD")  # honest_absence (no MyFXBook source)
    with_absent = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40), votes=[absent])
    no_votes = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40))
    assert with_absent == no_votes


def test_no_trade_tokens_in_rationale() -> None:
    g = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.40, 0.60), votes=[_vote()])
    assert _FORBIDDEN_RE.search(g.rationale_fr) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
