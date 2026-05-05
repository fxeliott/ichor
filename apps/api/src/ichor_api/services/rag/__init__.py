"""RAG (Retrieval-Augmented Generation) layer for Phase 2.

Provides:
  - `embedding`     : BGE-small-en-v1.5 ONNX inference (CPU, optimum)
  - `ingestion`     : embed cards/briefings/post_mortems → rag_chunks_index
  - `retrieval`     : hybrid RRF (dense pgvector HNSW + BM25 tsvector)

Cf docs/SPEC_V2_AUTOEVO.md §1, ADR-019 (HNSW), ADR-020 (BGE-small).
"""

from .embedding import (
    EMBED_DIM,
    BgeSmallEmbedder,
    embed_one,
    get_default_embedder,
)
from .retrieval import RagHit, hybrid_retrieve

__all__ = [
    "EMBED_DIM",
    "BgeSmallEmbedder",
    "RagHit",
    "embed_one",
    "get_default_embedder",
    "hybrid_retrieve",
]
