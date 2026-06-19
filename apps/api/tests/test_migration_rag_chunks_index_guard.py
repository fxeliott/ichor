"""S02 socle residual audit (2026-06-19) — guard the rag_chunks_index double-CREATE.

Migrations 0012 AND 0040 both create `rag_chunks_index` (with divergent schemas:
0012 = source_type/section/content [the CANONICAL one used by the live raw-SQL
writer/reader + 0041]; 0040 = source_kind/chunk_text/chunk_at [a dead ORM-only
schema]). On a fresh DB, `alembic upgrade head` crashed at 0040 with
`DuplicateTableError: relation "rag_chunks_index" already exists`
(runtime-reproduced this session against timescaledb-ha pg17 — prod survived only
because the table pre-existed Alembic, see 0041's header).

The fix makes 0040 idempotent: it skips the superseded re-creation when 0012's
canonical table already exists. `conftest` stubs the DB session, so the real
migration chain never runs in CI — hence this SOURCE-level guard pins the fix so
the crash cannot silently regress. (Runtime proof: `alembic upgrade head` ->
`0058 (head)` clean, with `rag_chunks_index` retaining 0012's schema A.)
"""

from __future__ import annotations

from pathlib import Path

_VERSIONS = Path(__file__).resolve().parents[1] / "migrations" / "versions"
_M0012 = _VERSIONS / "0012_rag_chunks_index.py"
_M0040 = _VERSIONS / "0040_rag_pgvector.py"


def test_both_migrations_exist() -> None:
    assert _M0012.exists() and _M0040.exists()


def test_both_migrations_target_rag_chunks_index() -> None:
    assert "rag_chunks_index" in _M0012.read_text(encoding="utf-8")
    assert "rag_chunks_index" in _M0040.read_text(encoding="utf-8")


def test_0040_inspector_guards_the_rag_chunks_index_recreation() -> None:
    """0040 must skip its (superseded) create when 0012's table exists, else a
    fresh-DB `alembic upgrade head` crashes with DuplicateTable."""
    src = _M0040.read_text(encoding="utf-8")
    assert 'has_table("rag_chunks_index")' in src, (
        "0040 must inspector-guard the rag_chunks_index re-creation (idempotency) "
        "— without it a fresh DB / DR rebuild crashes on the 0012 duplicate."
    )
    # The guard must sit BEFORE the create_table call it protects.
    guard_pos = src.index('has_table("rag_chunks_index")')
    create_pos = src.index("op.create_table(")
    assert guard_pos < create_pos, (
        "the has_table guard must precede op.create_table(rag_chunks_index)"
    )
