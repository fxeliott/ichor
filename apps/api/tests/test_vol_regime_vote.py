"""S06 Chantier C — ``vol_regime_vote.build_vol_regime_vote`` DOUBT producer tests."""

from __future__ import annotations

import math

import pytest
from ichor_api.services.conviction_fusion import VOTE_GAIN_K, fuse_conviction
from ichor_api.services.dimension_vote import DimensionVote
from ichor_api.services.vol_regime_vote import (
    PROVENANCE,
    VOL_REGIME_BASELINE_RATIO,
    VOL_REGIME_FULL_STRENGTH_RATIO,
    VOL_REGIME_MAX_AGE_DAYS,
    build_vol_regime_vote,
)


def _vote(*, status: str = "fresh", vix_ratio: float | None = 1.15, age_days: int | None = 0):
    return build_vol_regime_vote(status=status, vix_ratio=vix_ratio, age_days=age_days)


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


def test_is_a_doubt_layer() -> None:
    v = _vote()
    assert v.provenance == PROVENANCE == "vol_regime"
    assert v.directional is False
    assert v.direction_hint == "neutral"
    assert v.increases_uncertainty is True
    assert v.doubt_penalty() > 0.0
    assert v.uncertainty_credit() == 0.0
    assert v.signed_contribution() == 0.0


@pytest.mark.parametrize(
    ("ratio", "expected"),
    [
        (0.80, 0.0),  # stretched contango / calm → no doubt
        (VOL_REGIME_BASELINE_RATIO, 0.0),  # 0.95 flat boundary → 0
        (1.05, (1.05 - 0.95) / (1.15 - 0.95)),  # mild backwardation → 0.5
        (VOL_REGIME_FULL_STRENGTH_RATIO, 1.0),  # 1.15 extreme backwardation → full doubt
        (1.40, 1.0),  # beyond extreme → clamp 1.0
    ],
)
def test_doubt_strength_mapping(ratio: float, expected: float) -> None:
    v = _vote(vix_ratio=ratio)
    assert v.strength == pytest.approx(expected)
    assert 0.0 <= v.strength <= 1.0


def test_calm_market_is_present_but_zero_doubt() -> None:
    v = _vote(vix_ratio=0.85)
    assert v.honest_absence is False
    assert v.strength == 0.0
    assert v.is_effective is False


@pytest.mark.parametrize(
    ("age", "expected"),
    [(0, 1.0), (7, 0.5), (VOL_REGIME_MAX_AGE_DAYS, 0.0)],
)
def test_freshness_decay(age: int, expected: float) -> None:
    v = _vote(vix_ratio=1.15, age_days=age)
    assert v.freshness == pytest.approx(expected)


def _assert_absent(v: DimensionVote) -> None:
    assert v.honest_absence is True
    assert v.directional is False
    assert v.increases_uncertainty is True
    assert v.doubt_penalty() == 0.0


@pytest.mark.parametrize("status", ["stale", "absent", "unknown", ""])
def test_non_fresh_abstains(status: str) -> None:
    _assert_absent(_vote(status=status))


def test_missing_ratio_or_age_abstains() -> None:
    _assert_absent(_vote(vix_ratio=None))
    _assert_absent(_vote(age_days=None))


@pytest.mark.parametrize("bad", [0.0, -1.0, math.nan, math.inf])
def test_corrupted_ratio_abstains(bad: float) -> None:
    _assert_absent(_vote(vix_ratio=bad))


def test_lowers_conviction_in_fuser() -> None:
    base = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40)).conviction_pct
    g = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40), votes=[_vote(vix_ratio=1.15)])
    assert g.conviction_pct == pytest.approx(base * (1.0 - VOTE_GAIN_K))
    assert "vol_regime" in g.doubts
    assert "vol_regime" not in g.disagreeing


def test_never_flips_direction() -> None:
    up = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40), votes=[_vote()])
    down = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.40, 0.60), votes=[_vote()])
    assert up.direction == "up"
    assert down.direction == "down"


def test_calm_doubt_byte_identical_to_no_vote() -> None:
    no_vote = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40))
    calm = fuse_conviction(
        asset="EUR_USD", scenarios=_scn(0.60, 0.40), votes=[_vote(vix_ratio=0.85)]
    )
    assert calm.conviction_pct == no_vote.conviction_pct
