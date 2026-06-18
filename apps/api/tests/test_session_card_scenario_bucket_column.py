"""S02 socle drift guard — session_card_audit ORM ↔ migration 0039.

`realized_scenario_bucket` MUST stay `Text()` (what migration 0039 actually
built the DB column as), NOT `String(16)`. The String(16) was ORM-only drift
that advertised a length cap absent from the DB (the 7-label whitelist is
enforced by the CHECK constraint, not a varchar length) and produced a
spurious alembic-autogenerate diff. DB is the source of truth.

Mirrors the per-migration column-guard pattern used by
test_invariants_r62_key_levels_persistence.py — fails the build if a future
edit re-introduces the drift.
"""

from __future__ import annotations

from sqlalchemy import String, Text


def _cols() -> dict[str, object]:
    from ichor_api.models import SessionCardAudit

    return {c.name: c for c in SessionCardAudit.__table__.columns}


def test_realized_scenario_bucket_is_text_not_varchar() -> None:
    col = _cols()["realized_scenario_bucket"]
    assert isinstance(col.type, Text), (
        "realized_scenario_bucket must be Text() to match migration 0039:72-79 "
        f"(sa.Text()) ; got {type(col.type).__name__} — ORM drift re-introduced."
    )
    # Text() is unbounded ; String(16) drift would set length == 16.
    assert col.type.length is None, (
        "realized_scenario_bucket must have NO length cap (Text). A non-None "
        "length means the String(16) drift came back vs the DB (migration 0039)."
    )


def test_realized_scenario_bucket_is_nullable() -> None:
    col = _cols()["realized_scenario_bucket"]
    # NULL while the session window is still open (migration 0039:77 nullable=True).
    assert col.nullable is True


def test_scenarios_sibling_column_not_null_jsonb() -> None:
    from sqlalchemy.dialects.postgresql import JSONB

    col = _cols()["scenarios"]
    assert isinstance(col.type, JSONB), f"scenarios must be JSONB ; got {type(col.type).__name__}"
    # migration 0039:63-71 — JSONB NOT NULL server_default '[]'::jsonb.
    assert col.nullable is False


def test_realized_scenario_bucket_is_the_sole_string_drift() -> None:
    """The 7 String-typed columns keep the lengths set by creation migration
    0005 — documents that realized_scenario_bucket was the only drift."""
    cols = _cols()
    expected_lengths = {
        "session_type": 32,
        "asset": 16,
        "model_id": 64,
        "regime_quadrant": 32,
        "bias_direction": 8,
        "source_pool_hash": 64,
        "critic_verdict": 32,
    }
    for name, length in expected_lengths.items():
        col = cols[name]
        # Text subclasses String, so guard against an accidental Text drift too.
        assert isinstance(col.type, String) and not isinstance(col.type, Text), (
            f"{name} must stay a bounded String ; got {type(col.type).__name__}"
        )
        assert col.type.length == length, (
            f"{name} length {col.type.length} != {length} (creation migration 0005)"
        )
