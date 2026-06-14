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

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

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
        # Clamp so the documented [-1, +1] output contract holds even if a field
        # was tampered with after construction (object.__setattr__ defeats frozen).
        return max(-1.0, min(1.0, sign * self.strength * self.freshness))

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
        # Clamp to the documented [0, 1] output contract (defensive vs field tampering).
        return max(0.0, min(1.0, self.strength * self.freshness))


def net_dimension_vote(votes: Sequence[DimensionVote]) -> float:
    """Sum of signed directional contributions across dimensions, in
    ``[-N, +N]``. The fuser will map this onto its agreement factor (a later
    gated slice). Absent / neutral dimensions contribute 0 — honest."""
    return sum((v.signed_contribution() for v in votes), 0.0)


def total_uncertainty_credit(votes: Sequence[DimensionVote]) -> float:
    """Sum of non-directional anti-uncertainty credits across dimensions."""
    return sum((v.uncertainty_credit() for v in votes), 0.0)


def effective_provenances(votes: Sequence[DimensionVote]) -> tuple[str, ...]:
    """Provenances of the dimensions that actually contributed (for the
    transparent ``agreeing`` / coach surface), order preserved."""
    return tuple(v.provenance for v in votes if v.is_effective)


# --------------------------------------------------------------------------- #
# Card snapshot codec (Chantier C-3b prerequisite — reproducibility)           #
# --------------------------------------------------------------------------- #
#
# The verdict must be REPRODUCIBLE from the persisted card: the benchmark gate
# (Chantier A) replays the apex verdict from the card's frozen synthesis snapshots
# (``session_verdict_builder._extract_synthesis_primitives`` →
# ``_derive_direction_and_conviction``), NOT from a live re-fetch. So a dimension
# vote, once computed at card generation, must be FROZEN onto the card (a
# ``dimension_votes`` JSONB column, like the confluence/theme/dollar snapshots of
# migration 0055) and read back verbatim — otherwise the live verdict and the
# benchmark replay would diverge. This codec is that freeze/thaw, kept here in the
# pure contract module so both the write-side (run_session_card) and the read-side
# (build_session_verdict) share one serialization (the migration + wiring is the
# next, gated, slice).

_VALID_DIRECTIONS = ("up", "down", "neutral")


def to_snapshot(vote: DimensionVote) -> dict[str, Any]:
    """Serialize ONE vote to a JSON-safe dict for the card's ``dimension_votes``
    snapshot. All fields are plain JSON scalars (no dates / objects)."""
    return {
        "provenance": vote.provenance,
        "direction_hint": vote.direction_hint,
        "strength": vote.strength,
        "freshness": vote.freshness,
        "honest_absence": vote.honest_absence,
        "directional": vote.directional,
    }


def from_snapshot(data: Mapping[str, Any] | None) -> DimensionVote:
    """Reconstruct ONE vote from a card snapshot dict (read-side, verdict time).

    Defensive (mirrors ``_extract_synthesis_primitives``): a ``None`` / legacy /
    malformed snapshot degrades to an honest-absence vote — which contributes
    EXACTLY 0 (ADR-103), byte-identical to passing no vote — rather than raising.
    A well-formed snapshot round-trips to an equal vote.
    """
    absent = DimensionVote(
        provenance="unknown",
        direction_hint="neutral",
        strength=0.0,
        freshness=0.0,
        honest_absence=True,
        directional=True,
    )
    if not isinstance(data, Mapping):
        return absent
    try:
        direction_hint = data["direction_hint"]
        if direction_hint not in _VALID_DIRECTIONS:
            return absent
        provenance = data["provenance"]
        directional = data.get("directional", True)
        honest_absence = data.get("honest_absence", False)
        # Strict types (fail-closed): a snapshot we wrote always carries str / bool;
        # a tampered one with the wrong type must ABSTAIN, never be silently coerced
        # (e.g. directional "no" → bool("no") == True would wrongly turn a
        # non-directional layer into a long/short tilt — ADR-017).
        if not (
            isinstance(provenance, str)
            and isinstance(directional, bool)
            and isinstance(honest_absence, bool)
        ):
            return absent
        # Enforce ADR-017: a non-directional layer can never carry a tilt.
        if not directional and direction_hint != "neutral":
            return absent
        # Fail-closed on a corrupted magnitude: reject NaN / inf EXPLICITLY (not by
        # the side-effect of the range comparison) and enforce the [0, 1] contract —
        # never clamp a corrupted value to full strength (which would amplify it).
        strength = float(data["strength"])
        freshness = float(data.get("freshness", 1.0))
        if not (math.isfinite(strength) and math.isfinite(freshness)):
            return absent
        if not (0.0 <= strength <= 1.0 and 0.0 <= freshness <= 1.0):
            return absent
        return DimensionVote(
            provenance=provenance,
            direction_hint=direction_hint,
            strength=strength,
            freshness=freshness,
            honest_absence=honest_absence,
            directional=directional,
        )
    except (KeyError, TypeError, ValueError):
        return absent


def votes_to_snapshot(votes: Sequence[DimensionVote]) -> list[dict[str, Any]]:
    """Serialize the dimension votes to the card's ``dimension_votes`` JSONB list
    (write-side, card generation)."""
    return [to_snapshot(v) for v in votes]


def votes_from_snapshot(data: Any) -> tuple[DimensionVote, ...]:
    """Reconstruct the dimension votes from the card snapshot (read-side).

    ``None`` / legacy / non-list (a card generated before the column existed) →
    ``()`` so the fuser stays byte-identical to the no-votes path. Each malformed
    entry degrades to honest-absence rather than dropping the whole list."""
    if not isinstance(data, list):
        return ()
    return tuple(from_snapshot(entry) for entry in data)
