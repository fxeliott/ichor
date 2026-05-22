"""r62 — CI invariant guards for SessionCard.key_levels persistence.

Mechanises the architectural invariants r62 introduced so they fail
the build instead of relying on human code review or implicit trust :

  1. **Single source of truth (router ↔ persistence)** — `routers/key_levels.py`
     MUST call `compose_key_levels_snapshot()` and MUST NOT directly call
     any `compute_*_levels(` function. If a future contributor adds a
     new KeyLevel computer and wires it INLINE in the router (forgetting
     to update the orchestration service), the persistence path silently
     misses it — D4 frontend replay would show N items but historical
     session card would show N-1, a subtle data loss bug.

  2. **Schema column present** — `session_card_audit.key_levels` MUST
     exist in the ORM model with JSONB type + nullable=False. Catches
     accidental migration revert / ORM drift.

  3. **SessionCard Pydantic field present** — `SessionCard` MUST have
     `key_levels` field with the right type. Catches drift between the
     brain and the persistence mapper.

  4. **to_audit_row maps key_levels to []-not-None** — the migration
     0049 column is NOT NULL DEFAULT `'[]'::jsonb` ; passing None from
     the mapper would shadow the server default and INSERT NULL,
     violating the constraint. Pin the mapper contract mechanically.

ADR-081 codifies the policy of pushing invariants out of prose into
mechanical CI guards. r62 = third extension after r61 ADR-097 (FRED
liveness CI) + W90 base set.

These tests run in <1s on every CI run + every developer pre-commit.
"""

from __future__ import annotations

import re
import tokenize
from pathlib import Path

# Repo root resolution : this file lives at
# apps/api/tests/test_invariants_r62_key_levels_persistence.py — climb three levels.
_REPO_ROOT = Path(__file__).resolve().parents[3]


# ──────────────── Invariant 1 : single source of truth ───────────────


def test_key_levels_router_uses_orchestration_service_only() -> None:
    """`routers/key_levels.py` MUST import `compose_key_levels_snapshot`
    and MUST NOT directly import any `compute_*_levels` function.

    Drift class caught : a future contributor adds a new KeyLevel
    computer X and wires `compute_X_levels` INLINE in the router via
    `from ..services.key_levels import compute_X_levels` ; the
    `compose_key_levels_snapshot` service is forgotten, so the
    persistence path silently misses X. /v1/key-levels would render
    N+1 items but session_card_audit.key_levels would only contain N.

    The mechanical guard : parse the router source, scan its imports,
    assert the only key_levels-related import is the orchestration
    service.
    """
    router_path = _REPO_ROOT / "apps" / "api" / "src" / "ichor_api" / "routers" / "key_levels.py"
    assert router_path.exists(), f"router file moved : {router_path}"
    source = router_path.read_text(encoding="utf-8")

    # Allowed import : the orchestration service.
    assert (
        "from ..services.key_levels.orchestration import compose_key_levels_snapshot" in source
    ), "router must import compose_key_levels_snapshot from the orchestration service"

    # Forbidden : any direct compute_*_levels import. The Pydantic
    # KeyLevelOut model can stay here — it's the HTTP wrap layer.
    forbidden = re.findall(r"\bfrom \.\.services\.key_levels import \w+", source)
    for line in forbidden:
        assert "compose_key_levels_snapshot" in line or "KeyLevel" == line.split()[-1], (
            f"router must NOT import compute_*_levels directly — found : {line!r} ; "
            f"add the new computer to compose_key_levels_snapshot instead"
        )

    # Forbidden : any direct call to a compute_* function in the router
    # body. Tokenize-aware scan to avoid false positives in docstrings.
    with open(router_path, "rb") as f:
        tokens = list(tokenize.tokenize(f.readline))
    for tok in tokens:
        if tok.type == tokenize.NAME and re.fullmatch(r"compute_\w+_levels?", tok.string):
            raise AssertionError(
                f"router uses direct computer call {tok.string!r} at line {tok.start[0]} — "
                f"r62 invariant : ALL KeyLevel computers MUST be called via "
                f"compose_key_levels_snapshot() to keep router and persistence in sync."
            )


def test_compose_key_levels_snapshot_is_async_function() -> None:
    """The orchestration service MUST be async-callable. Synchronous
    drift would force the router to await None or block the event loop."""
    import inspect

    from ichor_api.services.key_levels.orchestration import compose_key_levels_snapshot

    assert inspect.iscoroutinefunction(compose_key_levels_snapshot), (
        "compose_key_levels_snapshot must be `async def` — the persistence "
        "path runs inside `async with sm() as session` and the router runs "
        "inside FastAPI's async handler ; sync drift would corrupt both."
    )


# ──────────────── Invariant 2 : ORM column present ───────────────


def test_session_card_audit_has_key_levels_column() -> None:
    """`session_card_audit.key_levels` MUST exist in the ORM model with
    JSONB type + nullable=False. Catches accidental migration revert
    or ORM drift that would leave the persistence path raising
    `'key_levels' is an invalid keyword argument for SessionCardAudit`.
    """
    from ichor_api.models.session_card_audit import SessionCardAudit
    from sqlalchemy.dialects.postgresql import JSONB

    cols = {c.name: c for c in SessionCardAudit.__table__.columns}
    assert "key_levels" in cols, (
        "ORM regression : SessionCardAudit lost the key_levels column. "
        "Verify migration 0049 hasn't been reverted."
    )

    col = cols["key_levels"]
    assert isinstance(col.type, JSONB), f"key_levels must be JSONB ; got {type(col.type).__name__}"
    assert not col.nullable, (
        "key_levels must be NOT NULL (migration 0049 server_default '[]'::jsonb)"
    )


# ──────────────── Invariant 3 : SessionCard Pydantic field present ───────────────


def test_session_card_pydantic_has_key_levels_field() -> None:
    """`SessionCard` Pydantic MUST have `key_levels` field. Catches
    drift between the brain card type and the persistence mapper."""
    from ichor_brain.types import SessionCard

    fields = SessionCard.model_fields
    assert "key_levels" in fields, (
        "SessionCard.key_levels field missing — to_audit_row would "
        "raise AttributeError on card.key_levels access."
    )


# ──────────────── Invariant 4 : mapper contract ───────────────


def test_to_audit_row_maps_none_key_levels_to_empty_list() -> None:
    """`to_audit_row` MUST map `card.key_levels = None` → `row.key_levels = []`.
    The migration 0049 column is NOT NULL DEFAULT `'[]'::jsonb` ; passing
    None would shadow the server default and INSERT NULL, raising
    `IntegrityError: null value in column "key_levels"`.

    Source-inspection guard : reads persistence.py, asserts the line
    `key_levels=_dump_list(card.key_levels) or []` is present (or
    equivalent `or []` fallback)."""
    persistence_path = (
        _REPO_ROOT / "packages" / "ichor_brain" / "src" / "ichor_brain" / "persistence.py"
    )
    source = persistence_path.read_text(encoding="utf-8")
    # Normalise whitespace then look for the canonical mapper line.
    normalised = re.sub(r"\s+", " ", source)
    assert (
        "key_levels=_dump_list(card.key_levels) or []" in normalised
        or "key_levels = _dump_list(card.key_levels) or []" in normalised
    ), (
        "persistence.py must map card.key_levels via `_dump_list(...) or []` "
        "— the `or []` fallback is mandatory to avoid INSERT NULL on the "
        "NOT NULL column (migration 0049)."
    )
