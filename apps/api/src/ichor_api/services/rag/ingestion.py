"""RAG ingestion — embed cards/briefings/post_mortems → rag_chunks_index.

Chunking strategy per AUTOEVO §1.4:
  - 1 card = 1 chunk (no intra-card splitting)
  - Briefings + post_mortems: recursive split @ 512 tokens with 10-20 % overlap
    (V0 approximation: split on paragraphs, hard cap on chars)

Anti-leakage: every row carries `created_at` = source's original timestamp,
NOT now(). Retrieval queries enforce `WHERE created_at < as_of`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .embedding import get_default_embedder

# 512 tokens ≈ 2000-2500 chars depending on language. Conservative cap.
_MAX_CHUNK_CHARS = 2400
_OVERLAP_CHARS = 360  # ~15 %


def _split_by_paragraphs(
    content: str,
    *,
    max_chars: int = _MAX_CHUNK_CHARS,
    overlap: int = _OVERLAP_CHARS,
) -> list[str]:
    """Greedy paragraph-aware split. If a paragraph > max_chars, hard-cut.

    Raises ValueError if `overlap >= max_chars` (caller bug — would loop
    infinitely on the hard-split path).
    """
    if overlap >= max_chars:
        raise ValueError(f"overlap ({overlap}) must be < max_chars ({max_chars})")
    # Step size for the hard-split fallback. Always advances ≥ 1 char.
    step = max(1, max_chars - overlap)

    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paragraphs:
        if len(buf) + len(p) + 2 <= max_chars:
            buf = (buf + "\n\n" + p) if buf else p
            continue
        if buf:
            chunks.append(buf)
            # Carry overlap from end of previous chunk
            buf = buf[-overlap:] + "\n\n" + p if overlap > 0 else p
        else:
            buf = p
        # If single paragraph exceeds max, hard-split with safe step.
        while len(buf) > max_chars:
            chunks.append(buf[:max_chars])
            buf = buf[step:]
    if buf:
        chunks.append(buf)
    return chunks


async def upsert_chunks(
    session: AsyncSession,
    *,
    source_type: str,  # 'card' | 'briefing' | 'post_mortem' | 'critic_finding'
    source_id: UUID,
    asset: str | None,
    regime: str | None,
    sections: list[tuple[str, str]],  # list of (section_label, content)
    created_at: datetime,
    metadata: dict[str, Any] | None = None,
) -> int:
    """Embed and insert/replace all chunks for one source.

    Strategy: delete-then-insert keyed on (source_type, source_id) to make
    re-indexing idempotent. The delete is a single DELETE; the insert is
    a batch.

    Returns the number of chunks written.
    """
    # 1) Delete previous chunks for this source.
    await session.execute(
        text("DELETE FROM rag_chunks_index WHERE source_type = :st AND source_id = :sid"),
        {"st": source_type, "sid": str(source_id)},
    )

    # 2) Build (label, content) per chunk — split long ones.
    expanded: list[tuple[str, str]] = []
    if source_type == "card":
        # 1 card = 1 chunk (per AUTOEVO §1.4): concat all sections.
        joined = "\n\n".join(f"### {label}\n{content}" for label, content in sections)
        expanded.append(("card_full", joined[: _MAX_CHUNK_CHARS * 2]))
    else:
        for label, content in sections:
            for piece in _split_by_paragraphs(content):
                expanded.append((label, piece))

    if not expanded:
        return 0

    # 3) Embed in batch (single ONNX session call).
    contents = [c for _, c in expanded]
    embedder = get_default_embedder()
    embs = embedder.embed(contents)

    # 4) Insert rows.
    # Note: `metadata` is JSON-serialized here so the SQL `CAST(:metadata AS jsonb)`
    # gets a string. Passing a Python dict directly fails with
    # `invalid input syntax for type jsonb` on some asyncpg adapters.
    metadata_str = json.dumps(metadata) if metadata is not None else None
    rows: list[dict[str, Any]] = []
    for (label, content), emb in zip(expanded, embs, strict=False):
        emb_literal = "[" + ",".join(f"{v:.6f}" for v in emb.tolist()) + "]"
        rows.append(
            {
                "id": str(uuid4()),
                "source_type": source_type,
                "source_id": str(source_id),
                "asset": asset,
                "regime": regime,
                "section": label,
                "content": content,
                "embedding": emb_literal,
                "metadata": metadata_str,
                "created_at": created_at,
                "indexed_at": datetime.now(UTC),
            }
        )

    insert_sql = text(
        """
        INSERT INTO rag_chunks_index
            (id, source_type, source_id, asset, regime, section, content,
             embedding, metadata, created_at, indexed_at)
        VALUES
            (:id, :source_type, :source_id, :asset, :regime, :section, :content,
             CAST(:embedding AS vector), CAST(:metadata AS jsonb), :created_at, :indexed_at)
        """
    )
    await session.execute(insert_sql, rows)
    return len(rows)


async def reindex_source(
    session: AsyncSession,
    *,
    source_type: str,
    source_id: UUID,
    full_text: str,
    asset: str | None = None,
    regime: str | None = None,
    created_at: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    """Convenience wrapper for the common 'one source = one big text' case."""
    return await upsert_chunks(
        session,
        source_type=source_type,
        source_id=source_id,
        asset=asset,
        regime=regime,
        sections=[("body", full_text)],
        created_at=created_at or datetime.now(UTC),
        metadata=metadata,
    )


async def count_indexed(session: AsyncSession) -> dict[str, int]:
    """Total chunks indexed by source_type. Useful for monitoring."""
    rows = (
        (
            await session.execute(
                text("SELECT source_type, COUNT(*) AS n FROM rag_chunks_index GROUP BY source_type")
            )
        )
        .mappings()
        .all()
    )
    return {r["source_type"]: int(r["n"]) for r in rows}
