"""S06 Chantier C · C-2a — flag-ON behaviour of the ``votes`` seam in
``conviction_fusion.fuse_conviction``.

C-2a adds ``votes: Sequence[DimensionVote] = ()`` to the fuser (additive). The
flag-OFF byte-identity (``votes == ()``) is proven exhaustively by
``test_fuser_golden_harness`` ; THIS file is the flag-ON contract — that supplying
dimension votes behaves exactly as designed and never breaks the doctrine:

  * ADR-017 — votes scale conviction MAGNITUDE / agreement only ; the direction
    stays bucket-derived, no pile of opposed votes can flip it.
  * ADR-022 — conviction stays clamped to ``[0, 95]`` however many votes align.
  * The bounded agreement factor: aligned votes promote (≤ ``AGREEMENT_CEIL``),
    opposed votes demote (≥ ``AGREEMENT_FLOOR``) — the floor that the 3-layer
    fuser could never reach is now reachable + exercised here.

Pure unit tests — no DB, no LLM (the fuser + ``DimensionVote`` are deterministic
primitives).
"""

from __future__ import annotations

import re

import pytest
from ichor_api.services.conviction_fusion import (
    AGREEMENT_CEIL,
    AGREEMENT_FLOOR,
    CONVICTION_CEIL_PCT,
    VOTE_GAIN_K,
    fuse_conviction,
)
from ichor_api.services.dimension_vote import DimensionVote

# Same proven CI-clean trade-token regex as test_conviction_fusion.py:25-28 (ADR-017).
_FORBIDDEN_RE = re.compile(
    r"\b(BUY|SELL|TP|SL|long entry|short entry|stop loss|take profit)\b",
    re.IGNORECASE,
)


def _scn(bull: float, bear: float) -> list[dict[str, object]]:
    """7-bucket Pass-6 decomposition (mirror of test_conviction_fusion._scn)."""
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


def _up_vote(provenance: str, strength: float = 1.0) -> DimensionVote:
    return DimensionVote(provenance=provenance, direction_hint="up", strength=strength)


def _down_vote(provenance: str, strength: float = 1.0) -> DimensionVote:
    return DimensionVote(provenance=provenance, direction_hint="down", strength=strength)


# 1 — empty votes is byte-identical to not passing votes at all (the flag-OFF seam).
def test_empty_votes_is_byte_identical_to_no_votes() -> None:
    base = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40), confluence_lean="long")
    with_empty = fuse_conviction(
        asset="EUR_USD", scenarios=_scn(0.60, 0.40), confluence_lean="long", votes=()
    )
    assert base == with_empty  # frozen dataclass equality over every field


# 2 — one aligned directional vote promotes conviction (same gain as a confluence vote).
def test_aligned_vote_promotes_like_confluence() -> None:
    g = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40), votes=[_up_vote("rates")])
    assert g.direction == "up"
    assert "rates" in g.agreeing
    assert g.conviction_pct == pytest.approx(60.0 * (1.0 + VOTE_GAIN_K))  # 66.0


# 3 — one opposed directional vote demotes conviction (direction unchanged — ADR-017).
def test_opposed_vote_demotes_but_keeps_direction() -> None:
    g = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40), votes=[_down_vote("rates")])
    assert g.direction == "up"  # bucket-derived; the vote did NOT flip it
    assert "rates" in g.disagreeing
    assert g.conviction_pct == pytest.approx(60.0 * (1.0 - VOTE_GAIN_K))  # 54.0


# 4 — votes stack additively into the SAME agreement-factor math.
def test_votes_stack_additively() -> None:
    g = fuse_conviction(
        asset="EUR_USD",
        scenarios=_scn(0.60, 0.40),
        votes=[_up_vote("rates"), _up_vote("positioning")],
    )
    # net_vote = +2 → factor 1.20 → 60 * 1.20 = 72.0
    assert g.conviction_pct == pytest.approx(72.0)
    assert g.agreement_factor == pytest.approx(1.0 + 2 * VOTE_GAIN_K)
    assert set(g.agreeing) >= {"rates", "positioning"}


# 5 — AGREEMENT_FLOOR is now REACHABLE (it never was with only 3 layers).
def test_many_opposed_votes_hit_agreement_floor() -> None:
    opposed = [_down_vote(p) for p in ("rates", "positioning", "geopolitics", "volume", "breadth")]
    g = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40), votes=opposed)
    # net_vote = -5 → 1 + 0.10*(-5) = 0.50 → clamped UP to the 0.60 floor.
    assert g.agreement_factor == pytest.approx(AGREEMENT_FLOOR)
    assert g.direction == "up"  # ADR-017: 5 opposed votes still cannot flip the bucket edge
    assert g.conviction_pct == pytest.approx(60.0 * AGREEMENT_FLOOR)  # 36.0


# 6 — promotion stays bounded by AGREEMENT_CEIL and the cap-95 (ADR-022).
def test_many_aligned_votes_respect_ceil_and_cap95() -> None:
    aligned = [_up_vote(f"dim_{i}") for i in range(10)]
    g = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.90, 0.05), votes=aligned)
    assert g.agreement_factor == pytest.approx(AGREEMENT_CEIL)  # bounded, not 1+10*0.1
    assert g.conviction_pct == pytest.approx(CONVICTION_CEIL_PCT)  # 90*1.25=112.5 → clamp 95
    assert g.conviction_pct <= CONVICTION_CEIL_PCT


# 7 — a non-directional vote adds anti-uncertainty credit only, never a tilt (ADR-017).
def test_non_directional_vote_adds_credit_only() -> None:
    vote = DimensionVote(
        provenance="macro_theme", direction_hint="neutral", strength=0.8, directional=False
    )
    g = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40), votes=[vote])
    assert g.direction == "up"
    assert "macro_theme" in g.agreeing  # presence credit, like theme
    assert "macro_theme" not in g.disagreeing
    # credit = strength*freshness = 0.8 → factor 1.08 → 64.8
    assert g.conviction_pct == pytest.approx(60.0 * (1.0 + VOTE_GAIN_K * 0.8))


# 8 — an absent (honest_absence) vote contributes EXACTLY 0 (ADR-103).
def test_absent_vote_contributes_zero() -> None:
    absent = DimensionVote(
        provenance="rates", direction_hint="up", strength=1.0, honest_absence=True
    )
    g = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40), votes=[absent])
    base = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40))
    assert g.conviction_pct == base.conviction_pct  # 60.0, untouched
    assert "rates" not in g.agreeing and "rates" not in g.disagreeing


# 9 — stale vote (freshness 0) contributes 0 even if strong + directional.
def test_stale_vote_contributes_zero() -> None:
    stale = DimensionVote(provenance="rates", direction_hint="up", strength=1.0, freshness=0.0)
    g = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40), votes=[stale])
    assert g.conviction_pct == pytest.approx(60.0)
    assert "rates" not in g.agreeing


# 10 — ADR-017: even an overwhelming opposed-vote stack never flips the direction.
def test_votes_never_flip_direction() -> None:
    flood = [_down_vote(f"dim_{i}") for i in range(20)]
    up = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40), votes=flood)
    assert up.direction == "up"
    down = fuse_conviction(
        asset="EUR_USD", scenarios=_scn(0.40, 0.60), votes=[_up_vote(f"d{i}") for i in range(20)]
    )
    assert down.direction == "down"


# 11 — freshness scales a vote's contribution proportionally.
def test_freshness_scales_contribution() -> None:
    half = DimensionVote(provenance="rates", direction_hint="up", strength=1.0, freshness=0.5)
    g = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40), votes=[half])
    # contribution = 1.0 * 0.5 = 0.5 → factor 1.05 → 63.0
    assert g.conviction_pct == pytest.approx(60.0 * (1.0 + VOTE_GAIN_K * 0.5))


# 12 — ADR-017: votes never inject a trade-signal token into the rationale.
@pytest.mark.parametrize(
    "votes",
    [
        [_up_vote("rates"), _down_vote("positioning")],
        [DimensionVote("theme", "neutral", 0.9, directional=False)],
        [_down_vote(f"d{i}") for i in range(6)],
    ],
)
def test_votes_emit_no_trade_tokens(votes: list[DimensionVote]) -> None:
    g = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40), votes=votes)
    assert _FORBIDDEN_RE.search(g.rationale_fr) is None


# 13 — per-asset dollar sign still composes correctly with votes (regression guard).
def test_votes_compose_with_dollar_sign() -> None:
    # USD_CAD: usd_up → asset up → agrees an up bias; an aligned vote stacks on top.
    g = fuse_conviction(
        asset="USD_CAD",
        scenarios=_scn(0.60, 0.40),
        dollar_consensus="usd_up",
        dollar_strength=1.0,
        votes=[_up_vote("rates")],
    )
    assert g.direction == "up"
    assert "dollar_coherence" in g.agreeing and "rates" in g.agreeing
    # net_vote = dollar(+1) + rates(+1) = +2 → factor 1.20 → 72.0
    assert g.conviction_pct == pytest.approx(72.0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
