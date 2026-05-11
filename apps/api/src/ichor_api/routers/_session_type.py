"""Shared SessionType validation regex (W101e — code-review H2 fix).

Single-source-of-truth for the session_type Query param regex used across
multiple routers (`calibration.py`, `sessions.py`, …). Pre-W101e, every
router hardcoded its own subset (3 windows, 4 windows, drift, etc.),
which silently 422-rejected legitimate cards from missing windows.

Canon : `ichor_brain.types.SessionType` Literal has 5 values. We mirror
them here because the `apps/api` venv does NOT install
`packages/ichor_brain` (kept separate, heavier dep tree). The CI
invariant test `apps/api/tests/test_invariants_ichor.py` parses the
canonical `types.py` and asserts coherence vs this local copy — drift
here will fail CI loudly.

Drift detection :
  - Add a value here → CI passes (no removal in canonical).
  - Remove a value here → CI fails if canonical still has it.
  - Add a value in canonical → CI fails if missing here.
"""

from __future__ import annotations

VALID_SESSION_TYPES: frozenset[str] = frozenset(
    {"pre_londres", "pre_ny", "ny_mid", "ny_close", "event_driven"}
)
"""The 5 canonical session windows. Order-independent set."""

SESSION_TYPE_REGEX: str = rf"^({'|'.join(sorted(VALID_SESSION_TYPES))})$"
"""Pre-built regex pattern for FastAPI `Query(..., regex=...)` /
`pattern=...` Param injection. Sorted for deterministic test snapshots."""
