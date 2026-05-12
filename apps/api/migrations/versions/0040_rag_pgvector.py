"""rag_pgvector — install pgvector extension + rag_chunks_index table.

Phase C foundation (round 10 2026-05-12 — Eliot directive "construire
architecture globale interconnectée", ADR-085 §"Bayesian predictive
synthesis Phase 3+" + SPEC.md §3.7 "RAG sur historique 5 ans").

Adds the storage substrate for the Ichor RAG (Retrieval-Augmented
Generation) layer that Pass-1 régime will use to inject "## Historical
analogues" sections into its prompt — top-5 similar past macro states
+ their realized outcomes (Brier-graded). This is the **single most
transformative feature** for Dimensions 3 (Intelligent) + 8 (Précis)
per the round-7 audit (current score 4/10 → projected 8/10).

Schema choices per researcher 2026-05-12 round 10 web review :
  * **pgvector HNSW index** (NOT IVFFlat). m=16 + ef_construction=64
    benchmarks 30× QPS vs IVFFlat at 99 % recall (pgvector 0.7+).
  * **384-dim vectors** : bge-small-en-v1.5 default. CPU-friendly
    inference, suffices for English macro narrative (BGE-M3
    multilingual upgrade is W110+ candidate).
  * **One row per session_card_audit** = one chunk. The session card
    narrative is short (≤ 4KB) so per-card chunking is the cleanest
    anti-leakage path (chunk_at = card.generated_at + embargo).
  * **Hybrid retrieval ready** : `chunk_text` stored alongside vector
    so callers can do dense + BM25 RRF (k=60) if needed.

Boundary recap (ADR-017) : the RAG layer **describes** past macro
states + outcomes. It never suggests trades. The Pass-1 prompt
consuming RAG retrievals stays bounded by the no-BUY/SELL system
prompt + Critic gate.

Revision ID: 0040
Revises: 0039
Create Date: 2026-05-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "0040"
down_revision: str | None = "0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Vector dimensionality for bge-small-en-v1.5. Hardcoded here because
# changing it requires re-embedding the entire 5-year history (~44k
# rows ÷ asset×session×year), which is a separate W110+ wave.
_BGE_SMALL_DIM = 384


def upgrade() -> None:
    # 1. Install pgvector extension at the database level. Idempotent.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2. rag_chunks_index : one row per session_card_audit (1-card-1-chunk
    #    strategy per Anthropic context-engineering 2026 best practice).
    op.create_table(
        "rag_chunks_index",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("source_kind", sa.Text(), nullable=False),
        # Foreign-key-ish but kept nullable + soft-deletable so a card
        # rotation doesn't break the index. The `source_id` column
        # holds the session_card_audit.id when source_kind='session_card'.
        sa.Column("source_id", PG_UUID(as_uuid=True), nullable=True),
        sa.Column(
            "chunk_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment=(
                "Timestamp the chunk content represents (= card.generated_at "
                "for session_card source). Used for past-only retrieval + "
                "embargo enforcement."
            ),
        ),
        sa.Column("asset", sa.String(16), nullable=True, index=True),
        sa.Column("session_type", sa.String(16), nullable=True, index=True),
        sa.Column("regime_quadrant", sa.String(32), nullable=True),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        # The vector column. Use sa.Column with the type expressed as
        # raw SQL since `sa.Vector` doesn't exist out of the box —
        # SQLAlchemy doesn't ship pgvector type natively.
        sa.Column(
            "embedding",
            sa.dialects.postgresql.ARRAY(sa.Float),  # placeholder ; will be replaced
            nullable=True,
        ),
        sa.Column(
            "embedding_model",
            sa.String(64),
            nullable=False,
            server_default=sa.text("'bge-small-en-v1.5'"),
        ),
        sa.Column(
            "metadata",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "source_kind IN ('session_card','post_mortem','briefing','adr','runbook')",
            name="ck_rag_chunks_source_kind",
        ),
    )

    # 3. Replace the ARRAY(Float) placeholder with the actual vector
    #    type. Done via raw SQL because SQLAlchemy doesn't ship pgvector
    #    natively — we drop the placeholder column and add the proper
    #    `vector(384)` typed one.
    op.drop_column("rag_chunks_index", "embedding")
    op.execute(f"ALTER TABLE rag_chunks_index ADD COLUMN embedding vector({_BGE_SMALL_DIM})")

    # 4. HNSW index for fast cosine-similarity retrieval. m=16 +
    #    ef_construction=64 per pgvector 0.7+ benchmarks (30× QPS vs
    #    IVFFlat at 99% recall on ~10k vectors).
    op.execute(
        "CREATE INDEX ix_rag_chunks_embedding_hnsw "
        "ON rag_chunks_index USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )

    # 5. Composite index for the dominant access pattern :
    #    "give me past chunks for this (asset, session_type) before
    #    chunk_at < now() - embargo". Anti-leakage temporal pattern.
    op.create_index(
        "ix_rag_chunks_asset_session_time",
        "rag_chunks_index",
        ["asset", "session_type", sa.text("chunk_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_rag_chunks_asset_session_time", table_name="rag_chunks_index")
    op.execute("DROP INDEX IF EXISTS ix_rag_chunks_embedding_hnsw")
    op.drop_table("rag_chunks_index")
    # pgvector extension is NOT dropped on downgrade — other features
    # may rely on it (W110+ pgvector-on-narrative). Manual `DROP
    # EXTENSION vector` if explicitly desired.
