"""S04 — verdict-builder ↔ conviction-fusion integration seam (« kill the 50/50 »).

Pure unit tests on the two seam helpers added in increment 2 :
``_extract_synthesis_primitives`` (reads the migration-0055 snapshots off the
card defensively) and ``_derive_direction_and_conviction`` (now delegates to
``conviction_fusion.fuse_conviction`` and returns the French grounding). No DB,
no LLM. The heavy ``build_session_verdict`` integration (DB row → Pydantic
SessionVerdict with the appended rationale) is exercised by the live deploy
witness, NOT mocked here ; these unit tests guard the deterministic core of the
wiring (an async-DB integration test is a tracked follow-up).
"""

from __future__ import annotations

from types import SimpleNamespace

from ichor_api.services.session_verdict_builder import (
    _build_coach_explanation_populated,
    _derive_direction_and_conviction,
    _extract_synthesis_primitives,
)


def _scn(bull: float, bear: float) -> list[dict[str, object]]:
    """7-bucket Pass-6 decomposition. ``bull`` → mild_bull, ``bear`` →
    mild_bear, the remainder → ``base`` (neutral). bullish_mass == bull,
    bearish_mass == bear, sum(p) == 1.0 (the fuser's invariant)."""
    base = max(0.0, 1.0 - bull - bear)
    return [
        {"label": "melt_up", "p": 0.0},
        {"label": "strong_bull", "p": 0.0},
        {"label": "mild_bull", "p": bull},
        {"label": "base", "p": base},
        {"label": "mild_bear", "p": bear},
        {"label": "strong_bear", "p": 0.0},
        {"label": "crash_flush", "p": 0.0},
    ]


def _card(*, confluence=None, theme=None, dollar=None):  # type: ignore[no-untyped-def]
    """Minimal stand-in exposing only the three S04 snapshot columns the
    extractor reads (so the unit test needs no ORM row / DB)."""
    return SimpleNamespace(
        confluence_snapshot=confluence,
        theme_snapshot=theme,
        dollar_snapshot=dollar,
    )


# ── _extract_synthesis_primitives ──────────────────────────────────────────


def test_extract_primitives_null_snapshots_default_to_no_evidence() -> None:
    lean, theme_present, consensus, strength = _extract_synthesis_primitives(_card())
    assert lean is None
    assert theme_present is False
    assert consensus is None
    assert strength == 0.0


def test_extract_primitives_reads_valid_snapshots() -> None:
    card = _card(
        confluence={"dominant_direction": "long", "score_long": 72.0},
        theme={"present": True, "top_theme": "monetary_policy"},
        dollar={"consensus": "usd_down", "consensus_strength": 0.8},
    )
    lean, theme_present, consensus, strength = _extract_synthesis_primitives(card)
    assert lean == "long"
    assert theme_present is True
    assert consensus == "usd_down"
    assert strength == 0.8


def test_extract_primitives_rejects_malformed_values() -> None:
    card = _card(
        confluence={"dominant_direction": "garbage"},
        theme={"present": False},
        dollar={"consensus": "moon", "consensus_strength": "n/a"},
    )
    lean, _theme_present, consensus, strength = _extract_synthesis_primitives(card)
    assert lean is None  # invalid lean rejected, defaults to no-evidence
    assert consensus is None  # invalid consensus rejected
    assert strength == 0.0  # non-float strength → 0.0, never raises


def test_extract_primitives_non_dict_snapshot_is_safe() -> None:
    # A malformed JSONB that deserialized to a list / scalar must not crash.
    card = _card(confluence=["x"], theme=42, dollar="nope")
    assert _extract_synthesis_primitives(card) == (None, False, None, 0.0)


# ── _derive_direction_and_conviction (delegates to fuse_conviction) ─────────


def test_derive_returns_three_tuple_with_rationale() -> None:
    direction, conviction, rationale = _derive_direction_and_conviction(
        _scn(0.60, 0.30), asset="EUR_USD"
    )
    assert direction == "up"
    assert 0.0 < conviction <= 95.0
    assert isinstance(rationale, str) and rationale  # non-empty FR grounding


def test_derive_no_evidence_matches_legacy_above_soft_zone() -> None:
    # spread 0.30 ≥ 0.15 soft-zone → no-evidence conviction == max(mass)*100.
    _, conviction, _ = _derive_direction_and_conviction(_scn(0.60, 0.30), asset="EUR_USD")
    assert conviction == 60.0


def test_derive_confluence_agreement_lifts_conviction() -> None:
    _, base, _ = _derive_direction_and_conviction(_scn(0.60, 0.30), asset="EUR_USD")
    _, lifted, _ = _derive_direction_and_conviction(
        _scn(0.60, 0.30), asset="EUR_USD", confluence_lean="long"
    )
    assert lifted > base  # corroborating evidence strengthens the edge


def test_derive_hard_dead_zone_is_neutral_zero() -> None:
    direction, conviction, rationale = _derive_direction_and_conviction(
        _scn(0.40, 0.38),
        asset="EUR_USD",  # spread 0.02 < 0.05 hard
    )
    assert direction == "neutral"
    assert conviction == 0.0
    assert "pile ou face" in rationale  # honest coin-flip grounding


def test_derive_exact_hard_deadzone_boundary_is_neutral() -> None:
    # spread == 0.05 exactly (0.05 - 0.0, a single float literal — no rounding
    # error): the `<=` boundary resolves to neutral/0 rather than a "biais
    # haussier à 0 %" directional label (doctrine #11 honesty).
    direction, conviction, _ = _derive_direction_and_conviction(_scn(0.05, 0.0), asset="EUR_USD")
    assert direction == "neutral"
    assert conviction == 0.0


def test_derive_graded_zone_attenuates_then_corroboration_rescues() -> None:
    # spread 0.10 in the [0.05, 0.15) graded band : weak edge, attenuated.
    _, weak, _ = _derive_direction_and_conviction(_scn(0.40, 0.30), asset="EUR_USD")
    _, corroborated, _ = _derive_direction_and_conviction(
        _scn(0.40, 0.30), asset="EUR_USD", confluence_lean="long"
    )
    assert 0.0 < weak < 40.0  # attenuated by the soft-zone scale
    assert corroborated > weak  # corroboration rescues the weak edge


def test_derive_conviction_never_exceeds_cap95() -> None:
    _, conviction, _ = _derive_direction_and_conviction(
        _scn(0.95, 0.0),
        asset="EUR_USD",
        confluence_lean="long",
        theme_present=True,
        dollar_consensus="usd_down",  # EUR_USD: usd_down → asset up → agrees
        dollar_strength=1.0,
    )
    assert conviction <= 95.0


def test_derive_opposing_evidence_shaves_but_keeps_direction() -> None:
    # ADR-017 : evidence scales magnitude, never sign. Opposed confluence on an
    # up edge lowers conviction but the direction stays bucket-derived 'up'.
    direction, conviction, _ = _derive_direction_and_conviction(
        _scn(0.60, 0.30), asset="EUR_USD", confluence_lean="short"
    )
    assert direction == "up"
    assert conviction < 60.0


# ── coach explanation surfaces the grounding ───────────────────────────────


def test_coach_explanation_appends_rationale_within_ceiling() -> None:
    rationale = (
        "Conviction 60 % (biais haussier). Preuves concordantes : confluence "
        "des facteurs et cohérence dollar ; aucun désaccord."
    )
    text = _build_coach_explanation_populated(
        asset="EUR_USD",
        direction="up",
        conviction_pct=60.0,
        nature="structured",
        scenarios=_scn(0.60, 0.30),
        conviction_rationale_fr=rationale,
    )
    assert rationale in text
    assert len(text) <= 800  # never breach the SessionVerdict Pydantic ceiling
