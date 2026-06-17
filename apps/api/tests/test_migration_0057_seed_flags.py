"""Runtime safety proof for migration 0057 (seed reactive/learning flags).

The migration uses ``INSERT ... ON CONFLICT (key) DO NOTHING`` so it can NEVER
turn a live-ON prod flag off, and a downgrade must preserve any flag an operator
flipped ON. ``ON CONFLICT DO NOTHING`` has identical semantics on SQLite (3.24+)
and Postgres (9.5+), so we prove the LOGIC against an in-memory SQLite mirror of
the ``feature_flags`` table — no Postgres / prod access required.

(The flag KEYS are imported from the migration itself, so a typo in either the
migration or this test surfaces immediately.)
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "0057_seed_reactive_learning_feature_flags.py"
)

# SQLite mirrors of the migration's two statements (Postgres ``false`` → ``0``;
# ON CONFLICT semantics are identical on both engines).
_INSERT = (
    "INSERT INTO feature_flags (key, enabled, description, created_by) "
    "VALUES (:key, 0, :description, 'migration_0057') "
    "ON CONFLICT (key) DO NOTHING"
)
_DELETE = "DELETE FROM feature_flags WHERE key = :key AND enabled = 0"


def _load_migration():
    spec = importlib.util.spec_from_file_location("_mig_0057", _MIGRATION_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_db() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.execute(
        "CREATE TABLE feature_flags ("
        "key TEXT PRIMARY KEY, "
        "enabled INTEGER NOT NULL DEFAULT 0, "
        "description TEXT, "
        "created_by TEXT)"
    )
    return con


def _seed(con: sqlite3.Connection, mod) -> None:
    for key, description in mod._SEEDED_FLAGS:
        con.execute(_INSERT, {"key": key, "description": description})


def test_0057_seeds_the_four_real_flags() -> None:
    mod = _load_migration()
    keys = [k for k, _ in mod._SEEDED_FLAGS]
    assert keys == [
        "streaming_refresh_enabled",
        "scenario_invalidation_monitor_enabled",
        "phase_d_w115c_confluence_enabled",
        "conviction_calibrator_oos_enabled",
    ], "0057 must seed exactly the 4 reactive/learning flags named by the S02 audit"
    assert all(desc.strip() for _k, desc in mod._SEEDED_FLAGS), "every flag needs a description"


def test_0057_upgrade_seeds_fail_closed_and_is_idempotent() -> None:
    mod = _load_migration()
    con = _make_db()
    _seed(con, mod)
    _seed(con, mod)  # run twice — ON CONFLICT DO NOTHING must not raise / duplicate
    rows = con.execute("SELECT key, enabled FROM feature_flags ORDER BY key").fetchall()
    assert len(rows) == 4
    assert all(enabled == 0 for _key, enabled in rows), (
        "every seeded flag is fail-closed (disabled)"
    )


def test_0057_upgrade_never_overrides_a_live_on_flag() -> None:
    """The headline safety property : a flag already flipped ON in prod MUST
    survive the seed untouched (ON CONFLICT DO NOTHING)."""
    mod = _load_migration()
    con = _make_db()
    con.execute(
        "INSERT INTO feature_flags (key, enabled, description) "
        "VALUES ('streaming_refresh_enabled', 1, 'flipped ON in prod')"
    )
    _seed(con, mod)
    enabled = con.execute(
        "SELECT enabled FROM feature_flags WHERE key = 'streaming_refresh_enabled'"
    ).fetchone()[0]
    assert enabled == 1, "0057 must NEVER turn a live-ON feature off"


def test_0057_downgrade_preserves_flags_flipped_on() -> None:
    mod = _load_migration()
    con = _make_db()
    _seed(con, mod)
    con.execute(
        "UPDATE feature_flags SET enabled = 1 WHERE key = 'phase_d_w115c_confluence_enabled'"
    )
    for key, _description in mod._SEEDED_FLAGS:
        con.execute(_DELETE, {"key": key})
    remaining = con.execute("SELECT key FROM feature_flags ORDER BY key").fetchall()
    assert remaining == [("phase_d_w115c_confluence_enabled",)], (
        "downgrade removes only still-default seeds, preserving any flipped ON"
    )
