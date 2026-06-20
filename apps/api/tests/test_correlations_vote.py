"""S06 Chantier C — ``correlations_vote`` DOUBT producer tests."""

from __future__ import annotations

import math

import pytest
from ichor_api.services.conviction_fusion import VOTE_GAIN_K, fuse_conviction
from ichor_api.services.correlations_vote import (
    CORR_BASELINE_ABS,
    CORR_FULL_CONFIDENCE_RETURNS,
    CORR_FULL_STRENGTH_ABS,
    CORR_MIN_RETURNS,
    PROVENANCE,
    build_correlations_vote,
)
from ichor_api.services.dimension_vote import DimensionVote


def _vote(
    *,
    status: str = "fresh",
    avg_abs_corr: float | None = 0.80,
    n_returns_used: int | None = CORR_FULL_CONFIDENCE_RETURNS,
):
    return build_correlations_vote(
        status=status, avg_abs_corr=avg_abs_corr, n_returns_used=n_returns_used
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
    assert v.provenance == PROVENANCE == "correlations"
    assert v.directional is False
    assert v.increases_uncertainty is True
    assert v.doubt_penalty() > 0.0
    assert v.signed_contribution() == 0.0


@pytest.mark.parametrize(
    ("avg", "expected"),
    [
        (0.20, 0.0),  # low correlation → no doubt
        (CORR_BASELINE_ABS, 0.0),  # 0.40 baseline → 0
        (0.60, 0.5),  # midpoint → 0.5
        (CORR_FULL_STRENGTH_ABS, 1.0),  # 0.80 systemic convergence → full
        (0.95, 1.0),  # near-perfect → clamp 1.0
    ],
)
def test_strength_mapping(avg: float, expected: float) -> None:
    v = _vote(avg_abs_corr=avg)
    assert v.strength == pytest.approx(expected)
    assert 0.0 <= v.strength <= 1.0


def test_normal_correlation_is_present_but_zero_doubt() -> None:
    v = _vote(avg_abs_corr=0.30)
    assert v.honest_absence is False
    assert v.strength == 0.0
    assert v.is_effective is False


def test_freshness_scales_with_overlap() -> None:
    # Thin matrix (min overlap) → weak freshness; full confidence at CORR_FULL_CONFIDENCE_RETURNS.
    assert _vote(n_returns_used=CORR_MIN_RETURNS).freshness == pytest.approx(
        CORR_MIN_RETURNS / CORR_FULL_CONFIDENCE_RETURNS
    )
    assert _vote(n_returns_used=CORR_FULL_CONFIDENCE_RETURNS).freshness == pytest.approx(1.0)
    assert _vote(n_returns_used=10 * CORR_FULL_CONFIDENCE_RETURNS).freshness == pytest.approx(1.0)


def _assert_absent(v: DimensionVote) -> None:
    assert v.honest_absence is True
    assert v.increases_uncertainty is True
    assert v.doubt_penalty() == 0.0


@pytest.mark.parametrize("status", ["stale", "absent", "unknown", ""])
def test_non_fresh_abstains(status: str) -> None:
    _assert_absent(_vote(status=status))


def test_thin_matrix_abstains() -> None:
    _assert_absent(_vote(n_returns_used=CORR_MIN_RETURNS - 1))
    _assert_absent(_vote(n_returns_used=None))


def test_missing_or_corrupted_avg_abstains() -> None:
    _assert_absent(_vote(avg_abs_corr=None))
    _assert_absent(_vote(avg_abs_corr=math.nan))
    _assert_absent(_vote(avg_abs_corr=1.5))  # out of [0,1]
    _assert_absent(_vote(avg_abs_corr=-0.1))


def test_lowers_conviction_in_fuser() -> None:
    base = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40)).conviction_pct
    g = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40), votes=[_vote()])
    # full strength (avg 0.80) + full freshness → full doubt → -VOTE_GAIN_K.
    assert g.conviction_pct == pytest.approx(base * (1.0 - VOTE_GAIN_K))
    assert "correlations" in g.doubts
    assert "correlations" not in g.disagreeing
