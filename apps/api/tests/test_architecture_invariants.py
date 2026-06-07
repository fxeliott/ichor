"""Architecture-of-record invariants (Session 02, 2026-06-05).

Mechanically enforces ``docs/ARCHITECTURE.md`` so the as-built map can never
silently drift from the code — the same W90 / ADR-081 lockstep doctrine the
project already applies to ADR-017 / Voie D, now applied to the *architecture*.

Two kinds of guard:

1. **Seam existence** — the anchor points ARCHITECTURE.md §9 promises to
   Sessions 04 / 05 must actually exist in the code. If a refactor removes or
   renames a seam, the documented hand-off breaks → this test fails → doc and
   code are forced back into sync.

2. **Gap-tracking lockstep** — ARCHITECTURE.md §4/§5 track two interconnection
   gaps. Session 04 CLOSED the first (the apex verdict now FUSES the synthesis
   via ``conviction_fusion.fuse_conviction``) — its guard is inverted to assert
   the seam STAYS wired. The second (the learning loop is not wired) is STILL
   open and its guard asserts so. The moment a guard's invariant breaks — a
   closed gap re-opens, or the still-open loop closes in Session 05 — the test
   fails **on purpose**, forcing whoever did it to update ARCHITECTURE.md so the
   as-built record stays true. The failure message says exactly what to do.

Pure file reads — no imports of app code, no DB, no network. Fast.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# apps/api/tests/ -> apps/api/ -> apps/ -> <repo root>
_REPO_ROOT = Path(__file__).resolve().parents[3]

_ARCH = _REPO_ROOT / "docs" / "ARCHITECTURE.md"
_ARCH_CIBLE = _REPO_ROOT / "docs" / "ARCHITECTURE_CIBLE.md"
_VERDICT_BUILDER = (
    _REPO_ROOT / "apps" / "api" / "src" / "ichor_api" / "services" / "session_verdict_builder.py"
)
_RUN_SESSION_CARD = (
    _REPO_ROOT / "apps" / "api" / "src" / "ichor_api" / "cli" / "run_session_card.py"
)
_ORCHESTRATOR = _REPO_ROOT / "packages" / "ichor_brain" / "src" / "ichor_brain" / "orchestrator.py"

# Session 04 CLOSED the "50/50": the apex verdict conviction is now FUSED from
# the synthesis snapshots (confluence / theme / dollar) frozen on the card, via
# ``services.conviction_fusion.fuse_conviction`` read through
# ``_extract_synthesis_primitives``. These markers are the fusion seam the
# lockstep below asserts STAYS wired (inverted from the pre-S04 "must NOT
# reference synthesis" guard).
_FUSION_SEAM_MARKERS = (
    "conviction_fusion",
    "fuse_conviction",
    "_extract_synthesis_primitives",
)


def _read(path: Path) -> str:
    assert path.exists(), f"architecture invariant target missing: {path}"
    return path.read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────
# 1 — Canonical doc + supersede chain
# ─────────────────────────────────────────────────────────────────────────


def test_architecture_record_is_canonical() -> None:
    """ARCHITECTURE.md exists and announces itself as the AS-BUILT record."""
    text = _read(_ARCH)
    assert "AS-BUILT" in text
    assert "Architecture-of-record" in text


def test_architecture_cible_is_marked_superseded() -> None:
    """The stale TARGET doc must point forward, so it is never mistaken for
    the current architecture again (the Session-02 anti-doublon resolution)."""
    text = _read(_ARCH_CIBLE)
    assert "SUPERSEDED" in text
    assert "ARCHITECTURE.md" in text


# ─────────────────────────────────────────────────────────────────────────
# 2 — Anchor seams S04 / S05 must exist (ARCHITECTURE.md §9)
# ─────────────────────────────────────────────────────────────────────────


def test_s04_conviction_seam_exists() -> None:
    """ARCHITECTURE.md §9 hands Session 04 the verdict-conviction seam. It must
    exist so the conviction-fusion work has a defined entry point."""
    text = _read(_VERDICT_BUILDER)
    assert "def _derive_direction_and_conviction" in text, (
        "The S04 conviction seam `_derive_direction_and_conviction` is gone — "
        "update ARCHITECTURE.md §9 if the verdict derivation was refactored."
    )


def test_s05_learning_loop_seam_exists() -> None:
    """ARCHITECTURE.md §9 hands Session 05 the `confluence_section` orchestrator
    seam (where learned pocket-skill weights would be injected)."""
    text = _read(_ORCHESTRATOR)
    assert "confluence_section" in text, (
        "The S05 learning-loop seam `confluence_section` is gone from the "
        "orchestrator — update ARCHITECTURE.md §5/§9 if the contract changed."
    )


# ─────────────────────────────────────────────────────────────────────────
# 3 — Gap-tracking lockstep (these FAIL ON PURPOSE when a gap is closed)
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("marker", _FUSION_SEAM_MARKERS)
def test_apex_verdict_fuses_synthesis(marker: str) -> None:
    """ARCHITECTURE.md §0/§4 (S04 — « kill the 50/50 »): the apex SessionVerdict
    conviction is now FUSED from the synthesis evidence (confluence lean +
    dominant-theme presence + cross-asset dollar consensus) frozen on the card
    at generation, not a bare ``max()`` over the Pass-6 buckets. This guard
    asserts the fusion seam is present.

    If `{marker}` disappears from the builder, the apex may be regressing toward
    the bucket-only "50/50" — UPDATE ARCHITECTURE.md §0/§4 and re-scope this
    guard rather than silently deleting the assertion.
    """
    text = _read(_VERDICT_BUILDER)
    assert marker in text, (
        f"session_verdict_builder no longer references `{marker}` — the S04 "
        f"conviction fusion may be regressing toward the bucket-only '50/50'. "
        f"UPDATE ARCHITECTURE.md §0/§4 and re-scope this guard."
    )


def test_learning_loop_still_open() -> None:
    """ARCHITECTURE.md §5: Phase-D measures skill (Vovk/Brier/ADWIN persist
    weights) but `pocket_skill_reader` is built-NOT-wired — the live
    `run_session_card` path never reads the pocket skill nor passes
    `confluence_section`. That open loop is why Ichor logs but does not yet act
    on its learning.

    When Session 05 closes the loop (wires read_pocket / confluence_section into
    run_session_card), this test fails on purpose → update ARCHITECTURE.md §5.
    """
    text = _read(_RUN_SESSION_CARD)
    assert "read_pocket" not in text and "confluence_section" not in text, (
        "run_session_card now wires the pocket-skill loop — Ichor may finally "
        "ACT on its learning (Session 05). UPDATE ARCHITECTURE.md §5 (the "
        "learning loop is closing) and re-scope this guard."
    )
