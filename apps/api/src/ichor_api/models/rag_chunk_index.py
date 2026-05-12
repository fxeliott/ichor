"""RagChunkIndex ORM — Phase C foundation (round 10 2026-05-12).

One row per ingested chunk (session_card / post_mortem / briefing /
ADR / RUNBOOK). The `embedding` column is a pgvector(384) — typed as
`Any` in the ORM because SQLAlchemy doesn't ship pgvector natively.

Use raw SQL via `text()` for similarity searches in
`services/rag_embeddings.py` (W110 candidate) :

    SELECT id, chunk_text, embedding <=> :query_vec AS distance
    FROM rag_chunks_index
    WHERE asset = :asset AND session_type = :session_type
      AND chunk_at < :embargo_cutoff
    ORDER BY distance ASC
    LIMIT 5

The HNSW index `ix_rag_chunks_embedding_hnsw` makes this <50ms on
~10k rows (pgvector 0.7+ benchmark).

Migration 0040 installs the pgvector extension + this table.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class RagChunkIndex(Base):
    """One embedded chunk available for Pass-1 retrieval-augmentation."""

    __tablename__ = "rag_chunks_index"
    __table_args__ = (
        CheckConstraint(
            "source_kind IN ('session_card','post_mortem','briefing','adr','runbook')",
            name="ck_rag_chunks_source_kind",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    """When source_kind='session_card', this is the session_card_audit.id.
    Other source_kinds may reference different tables (post_mortem.id,
    etc.) or be NULL for static documents (ADRs, RUNBOOKs)."""

    chunk_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    """Timestamp the chunk content REPRESENTS. For session_card chunks
    this is `card.generated_at`. Used for past-only retrieval +
    embargo enforcement (anti-leakage temporal pattern)."""

    asset: Mapped[str | None] = mapped_column(String(16), index=True)
    session_type: Mapped[str | None] = mapped_column(String(16), index=True)
    regime_quadrant: Mapped[str | None] = mapped_column(String(32))

    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    """The raw text content that was embedded. Stored alongside the
    vector so hybrid dense+BM25 RRF retrieval can be added in W110+."""

    # NOTE : The `embedding` column (`vector(384)` from migration 0040)
    # is INTENTIONALLY NOT mapped in this ORM. SQLAlchemy 2 doesn't
    # ship a pgvector type, and the `Mapped[Any]` workaround triggers
    # `MappedAnnotationError`. Vector ops are done via raw SQL
    # (`text("SELECT ... ORDER BY embedding <=> :q LIMIT k")`) in
    # `services/rag_embeddings.py`. The column still exists at DB
    # level (managed by alembic migration 0040) ; only its ORM
    # mapping is deferred.

    embedding_model: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="bge-small-en-v1.5",
    )

    metadata_: Mapped[Any] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
