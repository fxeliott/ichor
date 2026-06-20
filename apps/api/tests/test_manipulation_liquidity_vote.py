"""S06 Chantier C — ``manipulation_liquidity_vote`` DOUBT producer tests."""

from __future__ import annotations

import math

import pytest
from ichor_api.services.conviction_fusion import VOTE_GAIN_K, fuse_conviction
from ichor_api.services.dimension_vote import DimensionVote
from ichor_api.services.manipulation_liquidity_vote import (
    LIQUIDITY_FULL_STRENGTH_DRAIN_BN,
    LIQUIDITY_MAX_AGE_DAYS,
    PROVENANCE,
    build_manipulation_liquidity_vote,
)


def _vote(*, status: str = "fresh", delta_bn: float | None = -200.0, age_days: int | None = 0):
    return build_manipulation_liquidity_vote(status=status, delta_bn=delta_bn, age_days=age_days)


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


def test_full_strength_anchor_matches_alert_threshold() -> None:
    assert LIQUIDITY_FULL_STRENGTH_DRAIN_BN == 200.0  # lock-step with LIQ_TIGHTENING_THRESHOLD_BN


def test_is_a_doubt_layer() -> None:
    v = _vote()
    assert v.provenance == PROVENANCE == "manipulation_liquidity"
    assert v.directional is False
    assert v.increases_uncertainty is True
    assert v.doubt_penalty() > 0.0
    assert v.signed_contribution() == 0.0


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (100.0, 0.0),  # liquidity RISING (injection) → no doubt
        (0.0, 0.0),  # flat → no doubt
        (-100.0, 0.5),  # 100bn drain → half
        (-200.0, 1.0),  # 200bn drain (alert threshold) → full doubt
        (-500.0, 1.0),  # huge drain → clamp 1.0
    ],
)
def test_drain_strength_mapping(delta: float, expected: float) -> None:
    v = _vote(delta_bn=delta)
    assert v.strength == pytest.approx(expected)
    assert 0.0 <= v.strength <= 1.0


def test_rising_liquidity_is_present_but_zero_doubt() -> None:
    v = _vote(delta_bn=50.0)
    assert v.honest_absence is False
    assert v.strength == 0.0
    assert v.is_effective is False


@pytest.mark.parametrize(("age", "expected"), [(0, 1.0), (4, 0.5), (LIQUIDITY_MAX_AGE_DAYS, 0.0)])
def test_freshness_decay(age: int, expected: float) -> None:
    v = _vote(delta_bn=-200.0, age_days=age)
    assert v.freshness == pytest.approx(expected)


def _assert_absent(v: DimensionVote) -> None:
    assert v.honest_absence is True
    assert v.increases_uncertainty is True
    assert v.doubt_penalty() == 0.0


@pytest.mark.parametrize("status", ["stale", "absent", "unknown", ""])
def test_non_fresh_abstains(status: str) -> None:
    _assert_absent(_vote(status=status))


def test_missing_delta_or_age_abstains() -> None:
    _assert_absent(_vote(delta_bn=None))
    _assert_absent(_vote(age_days=None))


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_corrupted_delta_abstains(bad: float) -> None:
    _assert_absent(_vote(delta_bn=bad))


def test_lowers_conviction_in_fuser() -> None:
    base = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40)).conviction_pct
    g = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40), votes=[_vote(delta_bn=-200.0)])
    assert g.conviction_pct == pytest.approx(base * (1.0 - VOTE_GAIN_K))
    assert "manipulation_liquidity" in g.doubts
    assert "manipulation_liquidity" not in g.disagreeing
