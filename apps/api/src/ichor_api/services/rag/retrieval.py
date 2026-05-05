"""Hybrid RRF retrieval over `rag_chunks_index`.

Per ADR-019 + AUTOEVO §1.5: combine dense pgvector HNSW retrieval (cosine)
with BM25-equivalent tsvector retrieval, fuse via Reciprocal Rank Fusion
(RRF) with k=60 (standard).

The RAG block injected into Pass 1 uses the top-5 of this fused list,
filtered by `created_at < as_of_timestamp` for anti-leakage.

Reranker step (BGE-v2-m3 CPU) is a follow-up sprint.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .embedding import EMBED_DIM, embed_one


@dataclass(frozen=True)
class RagHit:
    """One retrieved chunk with fused RRF score and metadata."""

    chunk_id: UUID
    source_type: str
    source_id: UUID
    asset: str | None
    regime: str | None
    section: str | None
    content: str
    rrf_score: float
    dense_rank: int | None
    bm25_rank: int | None
    created_at: datetime


_RRF_K = 60


async def hybrid_retrieve(
    session: AsyncSession,
    query: str,
    *,
    asset: str | None = None,
    regime: str | None = None,
    as_of: datetime | None = None,
    top_dense: int = 30,
    top_bm25: int = 30,
    top_k: int = 5,
    ef_search: int = 60,
) -> list[RagHit]:
    """Hybrid RRF retrieval. Returns top-K chunks sorted by RRF score.

    - `asset`/`regime`: optional filters (None = no filter).
    - `as_of`: anti-leakage cutoff. None = now (no filter).
    - `top_dense`/`top_bm25`: shortlist sizes per branch.
    - `top_k`: final fused list size.
    - `ef_search`: pgvector HNSW runtime parameter (40-100 typical).
    """
    embedding = embed_one(query)
    if len(embedding) != EMBED_DIM:
        raise RuntimeError(f"Embedding dim mismatch: got {len(embedding)}, expected {EMBED_DIM}.")

    # Format embedding for pgvector cast.
    emb_literal = "[" + ",".join(f"{v:.6f}" for v in embedding.tolist()) + "]"

    # Build WHERE clauses dynamically.
    where_parts: list[str] = []
    params: dict[str, Any] = {}
    if asset is not None:
        where_parts.append("asset = :asset")
        params["asset"] = asset
    if regime is not None:
        where_parts.append("regime = :regime")
        params["regime"] = regime
    if as_of is not None:
        where_parts.append("created_at < :as_of")
        params["as_of"] = as_of
    where_clause = " AND ".join(where_parts) if where_parts else "TRUE"

    # Set HNSW ef_search for this transaction.
    await session.execute(text(f"SET LOCAL hnsw.ef_search = {int(ef_search)}"))

    dense_sql = text(
        f"""
        SELECT id, source_type, source_id, asset, regime, section,
               content, created_at,
               (embedding <=> '{emb_literal}'::vector) AS distance
        FROM rag_chunks_index
        WHERE {where_clause}
        ORDER BY embedding <=> '{emb_literal}'::vector
        LIMIT :top_dense
        """
    )
    params["top_dense"] = top_dense
    dense_rows = (await session.execute(dense_sql, params)).mappings().all()

    bm25_sql = text(
        f"""
        SELECT id, source_type, source_id, asset, regime, section,
               content, created_at,
               ts_rank(content_tsv, plainto_tsquery('english', :q)) AS score
        FROM rag_chunks_index
        WHERE {where_clause}
          AND content_tsv @@ plainto_tsquery('english', :q)
        ORDER BY score DESC
        LIMIT :top_bm25
        """
    )
    params2 = dict(params)
    params2["q"] = query
    params2["top_bm25"] = top_bm25
    bm25_rows = (await session.execute(bm25_sql, params2)).mappings().all()

    # RRF fusion: score(d) = sum_over_branches[1 / (k + rank_in_branch)]
    fused: dict[UUID, dict[str, Any]] = {}
    for rank, row in enumerate(dense_rows):
        cid: UUID = row["id"]
        bucket = fused.setdefault(
            cid,
            {
                "row": row,
                "dense_rank": rank + 1,
                "bm25_rank": None,
                "rrf": 0.0,
            },
        )
        bucket["rrf"] += 1.0 / (_RRF_K + rank + 1)

    for rank, row in enumerate(bm25_rows):
        cid = row["id"]
        if cid not in fused:
            fused[cid] = {
                "row": row,
                "dense_rank": None,
                "bm25_rank": rank + 1,
                "rrf": 0.0,
            }
        fused[cid]["bm25_rank"] = rank + 1
        fused[cid]["rrf"] += 1.0 / (_RRF_K + rank + 1)

    sorted_hits = sorted(fused.values(), key=lambda h: h["rrf"], reverse=True)[:top_k]
    out: list[RagHit] = []
    for h in sorted_hits:
        row = h["row"]
        out.append(
            RagHit(
                chunk_id=row["id"],
                source_type=row["source_type"],
                source_id=row["source_id"],
                asset=row.get("asset"),
                regime=row.get("regime"),
                section=row.get("section"),
                content=row["content"],
                rrf_score=round(h["rrf"], 6),
                dense_rank=h["dense_rank"],
                bm25_rank=h["bm25_rank"],
                created_at=row["created_at"],
            )
        )
    return out


def render_rag_block(hits: list[RagHit], *, max_chars_per_chunk: int = 600) -> str:
    """Format RAG hits as a markdown `<analogues>` block for Pass 1.

    The format intentionally cites `chunk_id` so Claude must explicitly
    reference past cards by ID in its synthesis.
    """
    if not hits:
        return "## Historical analogues (RAG)\n- (no relevant past cards retrieved)"
    lines = [
        f"## Historical analogues (RAG, top-{len(hits)} hybrid RRF)",
        "",
        "<analogues>",
    ]
    for h in hits:
        excerpt = h.content[:max_chars_per_chunk]
        if len(h.content) > max_chars_per_chunk:
            excerpt += "…"
        lines.append(
            f"  [chunk_id={h.chunk_id} type={h.source_type} "
            f"asset={h.asset or '-'} regime={h.regime or '-'} "
            f"date={h.created_at.date().isoformat()} rrf={h.rrf_score:.4f}]"
        )
        lines.append(f"  {excerpt}")
        lines.append("")
    lines.append("</analogues>")
    return "\n".join(lines)
