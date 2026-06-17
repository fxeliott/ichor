"""ADR-017 boundary filter — boundary-side re-export of the canonical SSOT.

The canonical home of the ADR-017 filter is now
``packages/ichor_brain/src/ichor_brain/adr017.py`` (relocated 2026-06-18, S02
socle audit). It was moved DOWN into ``ichor_brain`` — the lower architectural
layer, importable without ``ichor_api`` on the path — so that the brain-side
construction validators (``scenarios`` / ``session_verdict`` /
``passes.counterfactual``) and the ``apps/api`` persistence-gating consumers
share ONE source of truth instead of drifting byte-identical copies.

This module re-exports the canonical surface verbatim (byte-equivalent) so the
~39 existing ``from ...services.adr017_filter import ...`` call-sites keep
working unchanged. Mirror of the ``services/session_verdict.py`` +
``services/scenarios.py`` re-export pattern.

See ``ichor_brain.adr017`` for the full doctrine, the round-32 hardening, and
the distinction between :func:`is_adr017_clean` (STRONG persistence gate) and
:func:`contains_trade_signal` (NARROW construction-validator gate).
"""

from __future__ import annotations

from ichor_brain.adr017 import (
    _ADR017_FORBIDDEN_RE,
    ADR017_FORBIDDEN_PATTERN_LABELS,
    ADR017_FORBIDDEN_REGEX_SOURCE,
    _normalize_for_match,
    contains_trade_signal,
    count_violations,
    find_violations,
    is_adr017_clean,
    scrub_adr017,
)

__all__ = [
    "ADR017_FORBIDDEN_PATTERN_LABELS",
    "ADR017_FORBIDDEN_REGEX_SOURCE",
    "_ADR017_FORBIDDEN_RE",
    "_normalize_for_match",
    "contains_trade_signal",
    "count_violations",
    "find_violations",
    "is_adr017_clean",
    "scrub_adr017",
]
