"""S06 Chantier C · C-3b prerequisite — DimensionVote card-snapshot codec.

The verdict must be REPRODUCIBLE from the persisted card: the benchmark gate
(Chantier A) replays the apex verdict from the card's frozen snapshots, NOT from a
live re-fetch. So a dimension vote computed at card generation must be FROZEN onto
the card and read back verbatim — otherwise the live verdict and the benchmark
replay diverge. These tests pin that freeze/thaw (``to_snapshot`` / ``from_snapshot``
+ the list-level ``votes_to_snapshot`` / ``votes_from_snapshot``):

  * round-trip identity for well-formed votes (every field preserved);
  * JSON-safety (survives an actual ``json.dumps``/``loads`` = the JSONB column);
  * defensive thaw — NULL / legacy / corrupted snapshot → honest-absence (contributes
    EXACTLY 0, ADR-103), never raises;
  * byte-identical fusion — a thawed snapshot fuses identically to the original vote.

Pure unit tests — no DB, no LLM.
"""

from __future__ import annotations

import json

import pytest
from ichor_api.services.conviction_fusion import fuse_conviction
from ichor_api.services.dimension_vote import (
    DimensionVote,
    from_snapshot,
    to_snapshot,
    votes_from_snapshot,
    votes_to_snapshot,
)

_SAMPLE_VOTES = [
    DimensionVote(provenance="cot", direction_hint="up", strength=0.8, freshness=0.9),
    DimensionVote(provenance="rates", direction_hint="down", strength=1.0, freshness=1.0),
    DimensionVote(provenance="cot", direction_hint="up", strength=0.5, freshness=0.5),
    DimensionVote(provenance="theme", direction_hint="neutral", strength=0.6, directional=False),
    DimensionVote(provenance="cot", direction_hint="up", strength=1.0, honest_absence=True),
    DimensionVote(provenance="cot", direction_hint="neutral", strength=0.0),
    DimensionVote(  # a DOUBT layer (non-directional, lowers conviction) — round-trip it too
        provenance="vol_regime",
        direction_hint="neutral",
        strength=0.7,
        freshness=0.8,
        directional=False,
        increases_uncertainty=True,
    ),
]


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
# Round-trip identity                                                          #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("vote", _SAMPLE_VOTES)
def test_round_trip_is_identity(vote: DimensionVote) -> None:
    assert from_snapshot(to_snapshot(vote)) == vote


@pytest.mark.parametrize("vote", _SAMPLE_VOTES)
def test_round_trip_survives_json(vote: DimensionVote) -> None:
    # The snapshot lives in a JSONB column → it must survive a real JSON round-trip.
    restored = from_snapshot(json.loads(json.dumps(to_snapshot(vote))))
    assert restored == vote


def test_snapshot_is_plain_json_scalars() -> None:
    snap = to_snapshot(_SAMPLE_VOTES[0])
    assert set(snap) == {
        "provenance",
        "direction_hint",
        "strength",
        "freshness",
        "honest_absence",
        "directional",
        "increases_uncertainty",
    }
    json.dumps(snap)  # must not raise


def test_legacy_snapshot_without_doubt_key_thaws_to_corroborating() -> None:
    """A snapshot written before the doubt term (no ``increases_uncertainty`` key) must
    thaw to a corroborating vote (increases_uncertainty=False) — byte-identical to the
    pre-doubt behaviour (ADR backward-compat)."""
    legacy = {
        "provenance": "cot",
        "direction_hint": "up",
        "strength": 0.8,
        "freshness": 0.9,
        "honest_absence": False,
        "directional": True,
        # no "increases_uncertainty" key
    }
    v = from_snapshot(legacy)
    assert v.increases_uncertainty is False
    assert v.doubt_penalty() == 0.0
    assert v == DimensionVote(provenance="cot", direction_hint="up", strength=0.8, freshness=0.9)


def test_corrupted_doubt_flag_type_abstains() -> None:
    """A tampered snapshot with a non-bool increases_uncertainty must ABSTAIN (fail-closed),
    never be silently coerced."""
    bad = {
        "provenance": "vol_regime",
        "direction_hint": "neutral",
        "strength": 0.7,
        "freshness": 0.8,
        "honest_absence": False,
        "directional": False,
        "increases_uncertainty": "yes",  # not a bool
    }
    assert from_snapshot(bad).honest_absence is True


def test_doubt_snapshot_directional_true_abstains() -> None:
    """A forged snapshot claiming both directional AND increases_uncertainty is
    self-contradictory → abstain (a doubt layer can never be directional)."""
    forged = {
        "provenance": "vol_regime",
        "direction_hint": "neutral",
        "strength": 0.7,
        "freshness": 0.8,
        "honest_absence": False,
        "directional": True,
        "increases_uncertainty": True,
    }
    assert from_snapshot(forged).honest_absence is True


# --------------------------------------------------------------------------- #
# Defensive thaw (legacy / corrupted) → honest absence, never raises           #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "bad",
    [
        None,  # legacy card (column absent / NULL)
        {},  # empty
        {"direction_hint": "up"},  # missing strength/provenance
        {"provenance": "cot", "direction_hint": "sideways", "strength": 0.5},  # bad dir
        {"provenance": "cot", "direction_hint": "up", "strength": 5.0},  # out of range
        {"provenance": "cot", "direction_hint": "up", "strength": -0.1},  # negative
        {"provenance": "cot", "direction_hint": "up", "strength": "x"},  # non-numeric
        {  # ADR-017 violation: non-directional with a tilt
            "provenance": "x",
            "direction_hint": "up",
            "strength": 0.5,
            "directional": False,
        },
        # corrupted directional as a string would coerce to True (a tilt) — must abstain
        {"provenance": "x", "direction_hint": "up", "strength": 0.5, "directional": "no"},
        {"provenance": "x", "direction_hint": "up", "strength": 0.5, "directional": 1},
        # corrupted honest_absence / provenance types → abstain (strict)
        {"provenance": "x", "direction_hint": "up", "strength": 0.5, "honest_absence": "yes"},
        {"provenance": 123, "direction_hint": "up", "strength": 0.5},
        # NaN / inf magnitude → abstain (explicit math.isfinite guard)
        {"provenance": "x", "direction_hint": "up", "strength": float("nan")},
        {"provenance": "x", "direction_hint": "up", "strength": float("inf")},
        {"provenance": "x", "direction_hint": "up", "strength": 0.5, "freshness": float("nan")},
        "not-a-mapping",  # wrong type
        [1, 2, 3],  # wrong type
    ],
)
def test_malformed_snapshot_degrades_to_honest_absence(bad: object) -> None:
    v = from_snapshot(bad)  # type: ignore[arg-type]
    assert v.honest_absence is True
    assert v.is_effective is False
    assert v.signed_contribution() == pytest.approx(0.0)
    assert v.uncertainty_credit() == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# List-level codec (the card's ``dimension_votes`` JSONB)                       #
# --------------------------------------------------------------------------- #


def test_votes_round_trip() -> None:
    restored = votes_from_snapshot(json.loads(json.dumps(votes_to_snapshot(_SAMPLE_VOTES))))
    assert list(restored) == _SAMPLE_VOTES


@pytest.mark.parametrize("legacy", [None, "nope", {}, 42])
def test_votes_from_legacy_is_empty(legacy: object) -> None:
    # A card generated before the column existed → no votes → byte-identical path.
    assert votes_from_snapshot(legacy) == ()


def test_votes_empty_list_is_empty() -> None:
    assert votes_from_snapshot([]) == ()


def test_votes_one_bad_entry_degrades_only_that_entry() -> None:
    snap = votes_to_snapshot([_SAMPLE_VOTES[0]]) + [{"garbage": True}]
    restored = votes_from_snapshot(snap)
    assert len(restored) == 2
    assert restored[0] == _SAMPLE_VOTES[0]
    assert restored[1].honest_absence is True  # the bad entry, not the whole list


# --------------------------------------------------------------------------- #
# Byte-identical fusion (the property that makes the snapshot reproducible)     #
# --------------------------------------------------------------------------- #


def test_thawed_votes_fuse_identically_to_originals() -> None:
    votes = [_SAMPLE_VOTES[0], _SAMPLE_VOTES[1]]
    thawed = list(votes_from_snapshot(json.loads(json.dumps(votes_to_snapshot(votes)))))
    direct = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40), votes=votes)
    via_snapshot = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40), votes=thawed)
    assert direct == via_snapshot  # frozen dataclass equality over every field


def test_legacy_snapshot_fuses_byte_identical_to_no_votes() -> None:
    legacy = fuse_conviction(
        asset="EUR_USD", scenarios=_scn(0.60, 0.40), votes=votes_from_snapshot(None)
    )
    no_votes = fuse_conviction(asset="EUR_USD", scenarios=_scn(0.60, 0.40))
    assert legacy == no_votes


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
