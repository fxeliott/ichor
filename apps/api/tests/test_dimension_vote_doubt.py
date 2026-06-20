"""S06 Chantier C — DimensionVote DOUBT term (increases_uncertainty) contract tests.

The doubt term is the calibrated-humility half of the fusion (vision §B « pas de
pile-ou-face ») : a non-directional layer whose honest read is "the outcome distribution
is wider right now" LOWERS conviction (``doubt_penalty``), the symmetric counterpart of
the corroborating ``uncertainty_credit``. These tests lock:

  1. the contract — a doubt vote is non-directional, contributes ``doubt_penalty`` and ZERO
     ``uncertainty_credit`` / ``signed_contribution`` (ADR-017), and the __post_init__ guard;
  2. the aggregation helpers (``total_doubt_penalty``);
  3. the fuser — a doubt vote LOWERS conviction, is surfaced in ``doubts`` (not agreeing/
     disagreeing), bounded by AGREEMENT_FLOOR, never flips direction, and an absent /
     corroborating-only set leaves ``doubts`` empty (byte-identical to the pre-doubt path).
"""

from __future__ import annotations

import re

import pytest
from ichor_api.services.conviction_fusion import (
    AGREEMENT_FLOOR,
    VOTE_GAIN_K,
    fuse_conviction,
)
from ichor_api.services.dimension_vote import (
    DimensionVote,
    total_doubt_penalty,
    total_uncertainty_credit,
)

_FORBIDDEN_RE = re.compile(
    r"\b(BUY|SELL|TP|SL|long entry|short entry|stop loss|take profit)\b",
    re.IGNORECASE,
)


def _doubt(
    strength: float = 1.0, freshness: float = 1.0, provenance: str = "vol_regime"
) -> DimensionVote:
    return DimensionVote(
        provenance=provenance,
        direction_hint="neutral",
        strength=strength,
        freshness=freshness,
        directional=False,
        increases_uncertainty=True,
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
# Contract                                                                     #
# --------------------------------------------------------------------------- #


def test_doubt_vote_contributes_only_doubt_penalty() -> None:
    v = _doubt(strength=0.7, freshness=0.8)
    assert v.doubt_penalty() == pytest.approx(0.56)
    assert v.uncertainty_credit() == 0.0  # a doubt layer never adds positive credit
    assert v.signed_contribution() == 0.0  # never directional (ADR-017)
    assert v.is_effective is True


def test_doubt_vote_must_be_non_directional() -> None:
    with pytest.raises(ValueError, match="non-directional"):
        DimensionVote(
            provenance="vol_regime",
            direction_hint="neutral",
            strength=0.5,
            directional=True,  # contradiction: a doubt layer cannot be directional
            increases_uncertainty=True,
        )


def test_absent_doubt_contributes_zero() -> None:
    absent = DimensionVote(
        provenance="vol_regime",
        direction_hint="neutral",
        strength=0.0,
        directional=False,
        increases_uncertainty=True,
        honest_absence=True,
    )
    assert absent.doubt_penalty() == 0.0


def test_total_doubt_penalty_sums() -> None:
    votes = [
        _doubt(0.5),
        _doubt(1.0),
        DimensionVote(
            provenance="theme", direction_hint="neutral", strength=1.0, directional=False
        ),
    ]
    assert total_doubt_penalty(votes) == pytest.approx(1.5)
    assert total_uncertainty_credit(votes) == pytest.approx(1.0)  # only the corroborating theme


# --------------------------------------------------------------------------- #
# Fuser integration                                                           #
# --------------------------------------------------------------------------- #


def test_doubt_vote_lowers_conviction() -> None:
    base = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40)).conviction_pct
    doubted = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40), votes=[_doubt()])
    assert base == pytest.approx(60.0)
    # net_vote -= 1.0 → agreement_factor 1 - VOTE_GAIN_K = 0.90.
    assert doubted.conviction_pct == pytest.approx(60.0 * (1.0 - VOTE_GAIN_K))
    assert doubted.conviction_pct < base


def test_doubt_vote_surfaced_in_doubts_not_agreeing_or_disagreeing() -> None:
    g = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40), votes=[_doubt()])
    assert "vol_regime" in g.doubts
    assert "vol_regime" not in g.agreeing
    assert "vol_regime" not in g.disagreeing


def test_doubt_vote_never_flips_direction() -> None:
    up = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40), votes=[_doubt()])
    down = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.40, 0.60), votes=[_doubt()])
    assert up.direction == "up"
    assert down.direction == "down"


def test_stacked_doubt_bounded_by_agreement_floor() -> None:
    # Five full doubt votes would drive net_vote to -5 → factor 0.50, but the floor is 0.60.
    many = [_doubt(provenance=f"d{i}") for i in range(5)]
    g = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40), votes=many)
    assert g.agreement_factor == pytest.approx(AGREEMENT_FLOOR)
    assert g.conviction_pct == pytest.approx(60.0 * AGREEMENT_FLOOR)


def test_no_doubts_keeps_field_empty_byte_identical() -> None:
    g = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40))
    assert g.doubts == ()


def test_doubt_clause_in_rationale_no_trade_tokens() -> None:
    g = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40), votes=[_doubt()])
    assert "Incertitude élevée" in g.rationale_fr
    assert _FORBIDDEN_RE.search(g.rationale_fr) is None
