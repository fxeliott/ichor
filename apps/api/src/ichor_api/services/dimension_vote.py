"""dimension_vote.py — Chantier C slice-0 (ADR-120).

Pure-core, I/O-free, **stdlib only** — the conviction fuser refuses pydantic /
``ichor_brain`` imports to stay a dependency-free unit (``conviction_fusion.py``
imports nothing but ``collections.abc`` / ``dataclasses`` / ``typing``), so this
contract lives here, importable by the fuser without breaking that purity.

It is the canonical shape of ONE analysis dimension's directional vote, so the
verdict can fuse **≥ 9 dimensions** (vs the current 3: confluence / dollar /
theme) with explicit provenance and honest absence — the "verdict plus
intelligent" half of S06 (PLAN_DIRECTEUR §4bis). The goal is a conviction high
enough to be *legitimate* (an earned 85 %), not an over-confident one the
calibration must shrink to ~50 % (ADR-116/118 witness).

**NOT wired.** The fuser integration is a later GATED slice (flag-gated, behind a
golden-card diff-equivalence harness so the migration is byte-identical when the
flag is OFF). This file only defines the contract + pure aggregation helpers.

Doctrine:
- ADR-017: only the buckets set the verdict *direction*; a dimension vote moves
  the conviction MAGNITUDE / agreement. A structurally non-directional layer
  (e.g. market-theme presence) can NEVER carry a long/short tilt.
- ADR-103: an absent dimension contributes EXACTLY 0 — never a fabricated
  neutral (honest absence).
- ADR-022: magnitudes stay bounded; ``signed_contribution`` ∈ [-1, +1].
- ADR-009 (Voie D): pure arithmetic, zero I/O / LLM / spend.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

# Identical string values to ``conviction_fusion.Direction`` by design, so the
# fuser maps one onto the other at the integration seam with no translation.
VoteDirection = Literal["up", "down", "neutral"]


@dataclass(frozen=True, slots=True)
class DimensionVote:
    """One analysis layer's vote into the conviction fusion (PLAN §4bis).

    - ``provenance``: dimension id (e.g. ``"confluence"``, ``"geopolitics"``,
      ``"rates"``, ``"positioning"``) — surfaced for transparency.
    - ``direction_hint``: ``"up"`` / ``"down"`` / ``"neutral"``. A non-directional
      layer MUST use ``"neutral"`` (enforced) and adds anti-uncertainty credit
      only (ADR-017).
    - ``strength``: vote magnitude in ``[0, 1]`` (0 = no conviction).
    - ``freshness``: data-recency weight in ``[0, 1]`` (1 = fresh, 0 = stale) —
      scales the vote so a stale dimension counts less.
    - ``honest_absence``: ``True`` = no usable data (ADR-103) → contributes 0.
    - ``directional``: whether this layer may carry a long/short tilt at all
      (ADR-017: a theme-presence layer is structurally non-directional).
    """

    provenance: str
    direction_hint: VoteDirection
    strength: float
    freshness: float = 1.0
    honest_absence: bool = False
    directional: bool = True

    def __post_init__(self) -> None:
        # Fail-closed on out-of-contract input rather than silently clamping —
        # a bad vote is a bug to surface, not to paper over.
        if not (0.0 <= self.strength <= 1.0):
            raise ValueError(f"strength must be in [0, 1], got {self.strength!r}")
        if not (0.0 <= self.freshness <= 1.0):
            raise ValueError(f"freshness must be in [0, 1], got {self.freshness!r}")
        if not self.directional and self.direction_hint != "neutral":
            raise ValueError("a non-directional vote must have direction_hint='neutral'")

    @property
    def is_effective(self) -> bool:
        """True iff this vote contributes anything: present (not absent), with
        non-zero strength and freshness."""
        return not self.honest_absence and self.strength > 0.0 and self.freshness > 0.0

    def signed_contribution(self) -> float:
        """Net directional contribution in ``[-1, +1]``: ``+`` for up, ``-`` for
        down, ``0`` for neutral / non-directional / absent / stale.
        = ``sign(direction) * strength * freshness``. Mirrors the existing
        confluence / dollar signed-vote shape so the fuser sums these additively
        (a later gated slice)."""
        if not self.is_effective or not self.directional or self.direction_hint == "neutral":
            return 0.0
        sign = 1.0 if self.direction_hint == "up" else -1.0
        return sign * self.strength * self.freshness

    def uncertainty_credit(self) -> float:
        """Non-directional anti-uncertainty credit in ``[0, 1]`` (mirrors
        ``conviction_fusion.THEME_PRESENCE_VOTE``): a present neutral / non-
        directional layer still attests "a real driver exists here", which makes
        a directional read marginally less likely to be noise — but it NEVER
        tilts long/short (ADR-017). = ``strength * freshness`` when effective and
        neutral / non-directional, else 0."""
        if not self.is_effective:
            return 0.0
        if self.directional and self.direction_hint != "neutral":
            return 0.0
        return self.strength * self.freshness


def net_dimension_vote(votes: Sequence[DimensionVote]) -> float:
    """Sum of signed directional contributions across dimensions, in
    ``[-N, +N]``. The fuser will map this onto its agreement factor (a later
    gated slice). Absent / neutral dimensions contribute 0 — honest."""
    return sum(v.signed_contribution() for v in votes)


def total_uncertainty_credit(votes: Sequence[DimensionVote]) -> float:
    """Sum of non-directional anti-uncertainty credits across dimensions."""
    return sum(v.uncertainty_credit() for v in votes)


def effective_provenances(votes: Sequence[DimensionVote]) -> tuple[str, ...]:
    """Provenances of the dimensions that actually contributed (for the
    transparent ``agreeing`` / coach surface), order preserved."""
    return tuple(v.provenance for v in votes if v.is_effective)
