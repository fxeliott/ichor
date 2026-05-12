"""CI guards for ADR-086 Phase C RAG layer doctrinal invariants (W110e).

Three lines of defense mechanised here :

  1. `rag_chunks_index` is EXCLUDED from the Cap5 query_db allowlist —
     Couche-2 agents cannot grep the RAG store via
     `mcp__ichor__query_db`. That would bypass the embargo discipline
     (a Pass-1 agent could read its OWN session card after persistence
     and use it as an "analogue", training-data-leakage style).
  2. `retrieve_analogues()` enforces `embargo_days >= 1` at the
     service entry — same SQL invariant, defended from a different
     surface.
  3. The migration 0040 schema pins the embedding dimensionality at
     384 (bge-small-en-v1.5 Voie D Invariant 2). Drift here = retrieval
     silently broken (vector cosine across mismatched dims = nonsense).

If any of these tests start failing, do NOT patch the test — fix the
underlying surface or open an ADR superseding ADR-086.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

# Import the canonical allowlist from the service module so the test
# fails noisily if the symbol is renamed or moved.
from ichor_api.services.tool_query_db import ALLOWED_TABLES

# Forbidden tables for the Cap5 query_db surface (must NEVER appear in
# ALLOWED_TABLES). Each entry has a one-line rationale so a future
# reader doesn't accidentally weaken the guard "because it seems
# harmless".
_FORBIDDEN_TABLES_RATIONALE: dict[str, str] = {
    "rag_chunks_index": (
        "ADR-086 Invariant 3 — exposing this would let a Couche-2 agent "
        "read past session-card chunks bypassing the embargo discipline."
    ),
    "trader_notes": (
        "ADR-078 — AMF DOC-2008-23 §3 personnalisation. Trader notes "
        "MUST never feed back into the 4-pass orchestrator."
    ),
    "audit_log": (
        "ADR-029 — audit_log is immutable + write-only from the brain "
        "side ; reading it via query_db would let agents introspect "
        "the system's own history."
    ),
    "tool_call_audit": (
        "ADR-077 — same immutability rationale ; agents cannot read their own past calls."
    ),
    "feature_flags": (
        "Operational kill-switches — agents have no business reading them and acting on them."
    ),
}


@pytest.mark.parametrize(
    "table,rationale",
    sorted(_FORBIDDEN_TABLES_RATIONALE.items()),
)
def test_forbidden_table_not_in_cap5_allowlist(table: str, rationale: str) -> None:
    """Every forbidden table must stay out of ALLOWED_TABLES. The
    rationale is unused by the assertion itself ; it's there so the
    pytest header on failure says exactly *why* the table is forbidden."""
    assert table not in ALLOWED_TABLES, (
        f"Cap5 SECURITY REGRESSION: {table!r} is in ALLOWED_TABLES.\nRationale: {rationale}"
    )


def test_rag_chunks_index_explicitly_forbidden() -> None:
    """ADR-086 Invariant 3 — pin the rag table by name (mirrors the
    parametrized test above so a single-test grep finds the guard)."""
    assert "rag_chunks_index" not in ALLOWED_TABLES


# ─────────────────────────── Embargo enforcement ─────────────────────


@pytest.mark.asyncio
async def test_retrieve_analogues_embargo_one_day_minimum() -> None:
    """ADR-086 Invariant 1 — embargo_days < 1 is rejected at service entry."""
    from ichor_api.services.rag_embeddings import retrieve_analogues

    session = AsyncMock()
    for bad in (0, -1, -7):
        with pytest.raises(ValueError, match="embargo_days must be >= 1"):
            await retrieve_analogues(
                session, query_text="x", query_at=datetime.now(UTC), embargo_days=bad
            )


# ─────────────────────── Embedding dim pinning ───────────────────────


def test_embedding_dim_is_384() -> None:
    """ADR-086 Invariant 2 — bge-small-en-v1.5 has 384 dims. Changing
    this is a model swap = new ADR."""
    from ichor_api.services.rag_embeddings import EMBEDDING_DIM, EMBEDDING_MODEL_NAME

    assert EMBEDDING_DIM == 384
    assert EMBEDDING_MODEL_NAME == "BAAI/bge-small-en-v1.5"


def test_migration_0040_pins_vector_384() -> None:
    """The migration that creates `rag_chunks_index` must request
    `vector(384)`. A future migration changing this MUST also change
    the embedding model — caught here so the two surfaces stay in sync."""
    mig_path = (
        Path(__file__).resolve().parent.parent / "migrations" / "versions" / "0040_rag_pgvector.py"
    )
    assert mig_path.exists(), f"Migration not found: {mig_path}"
    src = mig_path.read_text(encoding="utf-8")
    # Accept either literal `vector(384)` or interpolation through the
    # `_BGE_SMALL_DIM = 384` constant defined at module level.
    assert "vector(384)" in src or re.search(r"_BGE_SMALL_DIM\s*=\s*384", src) is not None, (
        "Migration 0040 must pin the vector dimensionality to 384."
    )
