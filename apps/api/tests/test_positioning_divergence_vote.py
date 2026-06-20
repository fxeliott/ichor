"""S06 Chantier C — ``positioning_divergence_vote`` DOUBT producer tests."""

from __future__ import annotations

import pytest
from ichor_api.services.conviction_fusion import VOTE_GAIN_K, fuse_conviction
from ichor_api.services.dimension_vote import DimensionVote
from ichor_api.services.positioning_divergence_vote import (
    DIVERGENCE_FULL_STRENGTH_OI_FRACTION,
    DIVERGENCE_MAX_AGE_DAYS,
    DIVERGENCE_PUBLICATION_LAG_DAYS,
    PROVENANCE,
    build_positioning_divergence_vote,
)

_OI = 100_000


def _vote(
    *,
    asset: str = "EUR_USD",
    status: str = "fresh",
    lev_net: int | None = 12_000,
    am_net: int | None = -12_000,  # opposite sides → full-ish divergence
    oi: int | None = _OI,
    age_days: int | None = DIVERGENCE_PUBLICATION_LAG_DAYS,
):
    return build_positioning_divergence_vote(
        asset=asset,
        status=status,
        lev_net=lev_net,
        am_net=am_net,
        open_interest=oi,
        age_days=age_days,
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


def test_is_a_doubt_layer() -> None:
    v = _vote()
    assert v.provenance == PROVENANCE == "positioning_divergence"
    assert v.directional is False
    assert v.increases_uncertainty is True
    assert v.doubt_penalty() > 0.0
    assert v.signed_contribution() == 0.0


def test_opposite_sides_create_doubt_scaled_by_smaller_net() -> None:
    # smaller opposing net = 10_000 = 10 % of OI → full doubt.
    v = _vote(lev_net=20_000, am_net=-10_000)
    assert v.strength == pytest.approx(1.0)
    # smaller opposing net = 5_000 = 5 % of OI → 0.5.
    v2 = _vote(lev_net=5_000, am_net=-30_000)
    assert v2.strength == pytest.approx(0.5)


def test_same_side_cohorts_are_present_but_zero_doubt() -> None:
    v = _vote(lev_net=20_000, am_net=15_000)  # both long → no divergence
    assert v.honest_absence is False
    assert v.strength == 0.0
    assert v.is_effective is False


def test_full_strength_at_documented_oi_fraction() -> None:
    delta = int(DIVERGENCE_FULL_STRENGTH_OI_FRACTION * _OI)  # 10_000
    v = _vote(lev_net=delta, am_net=-delta)
    assert v.strength == pytest.approx(1.0)


@pytest.mark.parametrize("asset", ["EUR_USD", "GBP_USD", "XAU_USD", "NAS100_USD", "SPX500_USD"])
def test_all_tff_assets_can_vote(asset: str) -> None:
    assert _vote(asset=asset).honest_absence is False


def test_unknown_asset_abstains() -> None:
    assert _vote(asset="ZZZ_ZZZ").honest_absence is True


def _assert_absent(v: DimensionVote) -> None:
    assert v.honest_absence is True
    assert v.increases_uncertainty is True
    assert v.doubt_penalty() == 0.0


@pytest.mark.parametrize("status", ["stale", "absent", "unknown", ""])
def test_non_fresh_abstains(status: str) -> None:
    _assert_absent(_vote(status=status))


def test_missing_fields_abstain() -> None:
    _assert_absent(_vote(oi=None))
    _assert_absent(_vote(oi=0))
    _assert_absent(_vote(age_days=None))
    _assert_absent(_vote(lev_net=None))
    _assert_absent(_vote(am_net=None))


def test_freshness_lag_aware() -> None:
    assert _vote(age_days=DIVERGENCE_PUBLICATION_LAG_DAYS).freshness == pytest.approx(1.0)
    assert _vote(age_days=DIVERGENCE_MAX_AGE_DAYS).freshness == pytest.approx(0.0)


def test_lowers_conviction_in_fuser() -> None:
    base = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40)).conviction_pct
    g = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40), votes=[_vote()])
    assert g.conviction_pct == pytest.approx(base * (1.0 - VOTE_GAIN_K))
    assert "positioning_divergence" in g.doubts
    assert "positioning_divergence" not in g.disagreeing


def test_never_flips_direction() -> None:
    up = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40), votes=[_vote()])
    down = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.40, 0.60), votes=[_vote()])
    assert up.direction == "up"
    assert down.direction == "down"
