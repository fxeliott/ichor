"""ADR-017 SSOT re-export enforcement (apps/api side).

S02 socle audit (2026-06-18). The canonical ADR-017 filter was relocated to
``ichor_brain.adr017`` ; ``apps/api/.../services/adr017_filter.py`` re-exports it
verbatim so the ~39 existing consumers keep working AND there is exactly ONE
filter object (no drifting byte-identical copy — the `adr017-regex-unenforced`
finding). This test runs in the apps/api venv where both packages are present.
"""

from __future__ import annotations

from ichor_api.services.adr017_filter import (
    contains_trade_signal,
    count_violations,
    find_violations,
    is_adr017_clean,
    scrub_adr017,
)
from ichor_brain.adr017 import contains_trade_signal as brain_contains
from ichor_brain.adr017 import is_adr017_clean as brain_clean


def test_reexport_is_identical_object() -> None:
    """Identity, not equality — proves a single SSOT object, not a copy."""
    assert contains_trade_signal is brain_contains
    assert is_adr017_clean is brain_clean


def test_strong_gate_catches_obfuscation_on_persistence_path() -> None:
    assert is_adr017_clean("ＢＵＹ EUR_USD") is False  # full-width
    assert is_adr017_clean("acheter EUR maintenant") is False  # FR imperative
    assert is_adr017_clean("leverage is elevated") is False  # broad pattern
    assert is_adr017_clean("La BCE confirme une pause monétaire.") is True


def test_scrub_is_guaranteed_clean() -> None:
    dirty = "Strong sell-off; the desk leans buy-side toward TARGET 1.0850."
    cleaned = scrub_adr017(dirty)
    assert is_adr017_clean(cleaned) is True


def test_find_and_count_violations_agree() -> None:
    text = "acheter EUR and BUY gold"
    assert count_violations(text) == len(find_violations(text))
    assert count_violations(text) >= 2
