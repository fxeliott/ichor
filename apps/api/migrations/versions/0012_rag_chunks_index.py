"""rag_chunks_index — RAG storage with pgvector HNSW + tsvector hybrid retrieval.

Schema follows docs/SPEC_V2_AUTOEVO.md §1 (RAG state-of-art) and §6.5:
- 1 chunk = 1 card (no intra-card splitting)
- Embeddings = `bge-small-en-v1.5` (384 dims) self-host CPU
- HNSW index `m=16, ef_construction=64` (NOT ivfflat — pgvector 0.7+ benchmarks
  show ~30× QPS at 99% recall vs ivfflat)
- BM25 via tsvector + GIN for hybrid RRF retrieval (k=60, top-30 each side
  fused to top-5)
- Anti-leakage: composite index `(asset, regime, created_at DESC)` for
  WHERE clause `created_at < :as_of_timestamp`

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-04
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBED_DIM = 384  # bge-small-en-v1.5

SOURCE_TYPE_CHECK = "source_type IN ('card', 'briefing', 'post_mortem', 'critic_finding')"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE rag_chunks_index (
            id UUID PRIMARY KEY,
            source_type TEXT NOT NULL CHECK ({SOURCE_TYPE_CHECK}),
            source_id UUID NOT NULL,
            asset TEXT,
            regime TEXT,
            section TEXT,
            content TEXT NOT NULL,
            embedding vector({EMBED_DIM}) NOT NULL,
            content_tsv tsvector
                GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
            metadata JSONB,
            created_at TIMESTAMPTZ NOT NULL,
            indexed_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    # HNSW index for cosine ANN — m=16, ef_construction=64 (cf AUTOEVO §1.3).
    # ef_search is set at query time (40-100 range, default 40 for prod).
    op.execute(
        """
        CREATE INDEX ix_rag_chunks_embedding_hnsw
        ON rag_chunks_index
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);
        """
    )
    # BM25 via tsvector + GIN for hybrid RRF.
    op.execute(
        "CREATE INDEX ix_rag_chunks_content_tsv ON rag_chunks_index USING gin (content_tsv);"
    )
    # Composite filter for anti-leakage temporal queries.
    op.execute(
        "CREATE INDEX ix_rag_chunks_asset_regime_created "
        "ON rag_chunks_index (asset, regime, created_at DESC);"
    )
    # Source lookup for upsert/replace on re-indexing.
    op.create_index(
        "ix_rag_chunks_source",
        "rag_chunks_index",
        ["source_type", "source_id"],
    )


def downgrade() -> None:
    op.drop_table("rag_chunks_index")
