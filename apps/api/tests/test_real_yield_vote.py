"""S06 Chantier C — ``real_yield_vote`` (real-yield→gold FUNDAMENTAL) producer tests."""

from __future__ import annotations

import math
from datetime import date

import pytest
from ichor_api.services.conviction_fusion import VOTE_GAIN_K, fuse_conviction
from ichor_api.services.dimension_vote import DimensionVote
from ichor_api.services.dimension_vote_builders import _real_yield_delta_pp
from ichor_api.services.real_yield_vote import (
    PROVENANCE,
    REAL_YIELD_FULL_STRENGTH_PP,
    REAL_YIELD_MAX_AGE_DAYS,
    REAL_YIELD_NOISE_FLOOR_PP,
    build_real_yield_vote,
)


def _vote(
    *,
    asset: str = "XAU_USD",
    status: str = "fresh",
    real_yield_delta_pp: float | None = 0.40,  # +40bp → full strength, gold DOWN
    divergence_z: float | None = None,
    age_days: int | None = 0,
):
    return build_real_yield_vote(
        asset=asset,
        status=status,
        real_yield_delta_pp=real_yield_delta_pp,
        divergence_z=divergence_z,
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


# ── Direction (inverse carry law: rising real yield → gold DOWN) ────────────


def test_rising_real_yield_votes_gold_down() -> None:
    v = _vote(real_yield_delta_pp=0.40)
    assert v.provenance == PROVENANCE == "real_yield"
    assert v.direction_hint == "down"
    assert v.directional is True
    assert v.strength == pytest.approx(1.0)
    assert v.honest_absence is False


def test_falling_real_yield_votes_gold_up() -> None:
    v = _vote(real_yield_delta_pp=-0.40)
    assert v.direction_hint == "up"
    assert v.strength == pytest.approx(1.0)


# ── XAU-only ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("asset", ["EUR_USD", "GBP_USD", "SPX500_USD", "NAS100_USD", "ZZZ_ZZZ"])
def test_non_gold_assets_abstain(asset: str) -> None:
    v = _vote(asset=asset)
    assert v.honest_absence is True
    assert v.direction_hint == "neutral"
    assert v.strength == 0.0


# ── Strength mapping ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (0.20, 0.5),  # 20bp → half
        (REAL_YIELD_FULL_STRENGTH_PP, 1.0),  # 40bp → full
        (0.80, 1.0),  # huge → clamp
        (-0.20, 0.5),  # magnitude symmetric (direction flips, strength same)
    ],
)
def test_strength_mapping(delta: float, expected: float) -> None:
    v = _vote(real_yield_delta_pp=delta)
    assert v.strength == pytest.approx(expected)
    assert 0.0 <= v.strength <= 1.0


def test_sub_noise_move_abstains() -> None:
    v = _vote(real_yield_delta_pp=REAL_YIELD_NOISE_FLOOR_PP - 0.01)  # 4bp < 5bp floor
    assert v.honest_absence is True


# ── Carry-divergence reliability gate ───────────────────────────────────────


def test_divergence_extreme_abstains() -> None:
    # |z| >= 2 → gold decoupled from real yields → directional read unreliable → abstain.
    assert _vote(divergence_z=2.5).honest_absence is True
    assert _vote(divergence_z=-2.0).honest_absence is True


def test_divergence_within_band_votes() -> None:
    assert _vote(divergence_z=1.5).honest_absence is False


def test_divergence_none_does_not_gate() -> None:
    # Unknown z (not-yet-warm) → fail-open: the directional move still stands.
    assert _vote(divergence_z=None).honest_absence is False


@pytest.mark.parametrize("bad", [math.nan, math.inf])
def test_non_finite_divergence_does_not_gate(bad: float) -> None:
    # A corrupted z must not gate (fail-open on an unusable reliability signal).
    assert _vote(divergence_z=bad).honest_absence is False


# ── Fail-closed status + freshness ──────────────────────────────────────────


def _assert_absent(v: DimensionVote) -> None:
    assert v.honest_absence is True
    assert v.signed_contribution() == 0.0


@pytest.mark.parametrize("status", ["stale", "absent", "unknown", ""])
def test_non_fresh_abstains(status: str) -> None:
    _assert_absent(_vote(status=status))


def test_missing_delta_or_age_abstains() -> None:
    _assert_absent(_vote(real_yield_delta_pp=None))
    _assert_absent(_vote(age_days=None))


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_corrupted_delta_abstains(bad: float) -> None:
    _assert_absent(_vote(real_yield_delta_pp=bad))


@pytest.mark.parametrize(("age", "expected"), [(0, 1.0), (7, 0.5), (REAL_YIELD_MAX_AGE_DAYS, 0.0)])
def test_freshness_decay(age: int, expected: float) -> None:
    v = _vote(real_yield_delta_pp=0.40, age_days=age)
    assert v.freshness == pytest.approx(expected)


# ── _real_yield_delta_pp band-selection helper ──────────────────────────────


def test_delta_helper_picks_nearest_to_one_month() -> None:
    # newest-first; current 2.50 on D, prior 2.10 ~28d back → Δ = +0.40.
    rows = [
        (date(2026, 6, 9), 2.50),
        (date(2026, 6, 2), 2.45),  # 7d → outside [21,42]
        (date(2026, 5, 12), 2.10),  # 28d → in band, nearest
    ]
    assert _real_yield_delta_pp(rows) == pytest.approx(0.40)


def test_delta_helper_abstains_when_no_obs_in_band() -> None:
    rows = [(date(2026, 6, 9), 2.50), (date(2026, 4, 1), 2.10)]  # 69d > 42
    assert _real_yield_delta_pp(rows) is None
    assert _real_yield_delta_pp([]) is None
    assert _real_yield_delta_pp([(date(2026, 6, 9), 2.5)]) is None  # single obs


# ── Fuser integration ───────────────────────────────────────────────────────


def test_agreeing_lifts_keeps_direction() -> None:
    # rising real yield → vote down → agrees with a bearish XAU bucket → promotes.
    vote = _vote(real_yield_delta_pp=0.40)  # down, strength 1.0
    g = fuse_conviction(asset="XAU_USD", scenarios=_scn(0.40, 0.60), votes=[vote])
    assert g.direction == "down"
    assert "real_yield" in g.agreeing
    assert g.conviction_pct == pytest.approx(60.0 * (1.0 + VOTE_GAIN_K))


def test_opposing_shaves_keeps_direction() -> None:
    vote = _vote(real_yield_delta_pp=0.40)  # down vote on an up bucket → disagrees
    g = fuse_conviction(asset="XAU_USD", scenarios=_scn(0.60, 0.40), votes=[vote])
    assert g.direction == "up"  # bucket-derived (ADR-017)
    assert "real_yield" in g.disagreeing
    assert g.conviction_pct == pytest.approx(60.0 * (1.0 - VOTE_GAIN_K))


def test_absent_byte_identical_to_no_vote() -> None:
    absent = _vote(asset="EUR_USD")
    with_absent = fuse_conviction(asset="XAU_USD", scenarios=_scn(0.60, 0.40), votes=[absent])
    no_votes = fuse_conviction(asset="XAU_USD", scenarios=_scn(0.60, 0.40))
    assert with_absent == no_votes
