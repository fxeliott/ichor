"""Pass-1 RAG retrieval service — W110b ADR-086.

Provides two pure async functions :
  * `embed_text(text: str) -> list[float]` — bge-small-en-v1.5 ONNX CPU.
  * `retrieve_analogues(session, *, query_text, query_at, asset=None,
        session_type=None, k=5, embargo_days=1) -> list[Analogue]` —
        past-only top-K retrieval against `rag_chunks_index`.

The model loads lazily (first call), caches as module singleton. CPU
inference target <50ms/chunk per round-10 researcher web review.

ADR-086 invariants enforced :
  1. **Past-only** : `WHERE created_at < query_at - INTERVAL 'N days'`
     where `embargo_days >= 1` is required (ValueError otherwise).
  2. **Voie D** : bge-small-en-v1.5 self-hosted ONNX CPU, no paid API.
  3. **Cap5 exclusion** : `rag_chunks_index` is NOT in
     `services/tool_query_db.ALLOWED_TABLES` — Couche-2 agents cannot
     query this table via `mcp__ichor__query_db` (would bypass the
     embargo discipline). The W83 CI guard test enforces this.

Tests :
  * `tests/test_rag_embeddings.py` — `test_retrieve_analogues_embargo_rejects_zero`
    + `test_retrieve_analogues_past_only_filter`
    + `test_embed_text_returns_384_dim`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Lazy-loaded module singleton. ONNX-backed bge-small-en-v1.5.
_MODEL: Any = None

# Embedding model spec (ADR-086 Invariant 2 — Voie D).
EMBEDDING_MODEL_NAME: str = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM: int = 384


@dataclass(frozen=True)
class Analogue:
    """One retrieved past chunk + similarity score."""

    chunk_id: str
    source_type: str
    source_id: str
    asset: str | None
    regime: str | None
    section: str | None
    content: str
    created_at: datetime
    cosine_distance: float
    """Lower is more similar. pgvector `<=>` operator returns cosine
    distance ∈ [0, 2] where 0 = identical, 1 = orthogonal, 2 = opposite."""


def _load_model() -> Any:
    """Lazy-load sentence-transformers model with ONNX backend. CPU only.

    Cached as module singleton so the model loads once per process. The
    first call pays ~5-10s warmup ; subsequent calls are sub-50ms per
    chunk on Hetzner CPU per round-10 researcher web review.

    Voie D : the model is downloaded from HuggingFace Hub on first use
    + cached in `~/.cache/huggingface/`. No paid API. No Anthropic SDK.
    """
    global _MODEL
    if _MODEL is None:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "sentence-transformers not installed. Run on Hetzner : "
                "`/opt/ichor/api/.venv/bin/pip install "
                "'sentence-transformers[onnx]'`. ADR-086 Invariant 2 "
                "requires self-hosted bge-small-en-v1.5 ONNX CPU."
            ) from e
        # `backend="onnx"` requires sentence-transformers >= 3.2 +
        # `optimum[onnxruntime]`. Falls back to PyTorch if unavailable.
        try:
            _MODEL = SentenceTransformer(EMBEDDING_MODEL_NAME, backend="onnx")
        except Exception:  # noqa: BLE001 — fall back to PyTorch CPU
            _MODEL = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _MODEL


def embed_text(text_content: str) -> list[float]:
    """Embed a single text chunk. Returns 384-dim float vector.

    Pure synchronous function — the encoding is CPU-bound and short
    (<50ms), so wrapping in asyncio.to_thread is overkill for the
    typical Pass-1 call path (1 query embedding per session).
    """
    if not text_content or not text_content.strip():
        raise ValueError("embed_text: text must be non-empty")
    model = _load_model()
    # `normalize_embeddings=True` makes cosine similarity == dot product
    # numerically stable (||v|| = 1) — required for pgvector `<=>`
    # cosine-distance operator to behave as expected.
    vec = model.encode(text_content, normalize_embeddings=True)
    return [float(x) for x in vec]


def _format_vector_for_pgvector(vec: list[float]) -> str:
    """Format a Python float list as a pgvector literal `'[v1,v2,...]'`.

    pgvector accepts the bracketed string form via parametrized query.
    SQLAlchemy's text() binding handles the cast automatically when the
    column type is `vector(N)`.
    """
    return "[" + ",".join(f"{v:.8f}" for v in vec) + "]"


async def retrieve_analogues(
    session: AsyncSession,
    *,
    query_text: str,
    query_at: datetime,
    asset: str | None = None,
    session_type: str | None = None,
    k: int = 5,
    embargo_days: int = 1,
) -> list[Analogue]:
    """Past-only top-K retrieval from `rag_chunks_index`.

    Embargo enforcement : ADR-086 Invariant 1. `embargo_days` MUST be
    >= 1 (raises ValueError otherwise — defense against accidentally
    fetching same-session contamination).

    Filters :
      * `created_at < query_at - INTERVAL 'embargo_days days'` (past-only)
      * Optional `asset = :asset` (sharpens for per-asset analogues)
      * Optional `regime = ...` (future W120 — regime-conditional retrieval)
      * Excludes `source_type IN ('adr','runbook')` by default (those are
        for ad-hoc reference, not historical session analogy)
    """
    if embargo_days < 1:
        raise ValueError(
            f"embargo_days must be >= 1 (got {embargo_days}). ADR-086 "
            "Invariant 1 forbids same-day or same-session retrieval."
        )
    if k < 1 or k > 50:
        raise ValueError(f"k must be in [1, 50] (got {k})")

    query_vec = embed_text(query_text)
    vec_literal = _format_vector_for_pgvector(query_vec)

    cutoff = query_at - timedelta(days=embargo_days)

    where_clauses = [
        "created_at < :cutoff",
        "source_type IN ('session_card','post_mortem','briefing')",
    ]
    params: dict[str, Any] = {"cutoff": cutoff, "k": k, "qv": vec_literal}
    if asset:
        where_clauses.append("asset = :asset")
        params["asset"] = asset.upper()
    if session_type:
        where_clauses.append(
            "metadata->>'session_type' = :session_type "
            "OR metadata IS NULL"  # be tolerant on legacy rows
        )
        params["session_type"] = session_type

    sql = text(
        f"""
        SELECT
            id::text AS chunk_id,
            source_type,
            source_id::text AS source_id,
            asset,
            regime,
            section,
            content,
            created_at,
            embedding <=> CAST(:qv AS vector) AS cosine_distance
        FROM rag_chunks_index
        WHERE {" AND ".join(where_clauses)}
        ORDER BY embedding <=> CAST(:qv AS vector) ASC
        LIMIT :k
        """
    )

    rows = (await session.execute(sql, params)).mappings().all()
    return [
        Analogue(
            chunk_id=r["chunk_id"],
            source_type=r["source_type"],
            source_id=r["source_id"],
            asset=r["asset"],
            regime=r["regime"],
            section=r["section"],
            content=r["content"],
            created_at=r["created_at"],
            cosine_distance=float(r["cosine_distance"]),
        )
        for r in rows
    ]


def format_analogues_prompt_section(analogues: list[Analogue]) -> str:
    """Render a Pass-1 prompt section for the retrieved analogues.

    ADR-086 §"Pass-1 prompt injection format". The format is descriptive
    (past states + outcomes), never prescriptive (no BUY/SELL inference
    suggested) — boundary respected.

    Empty list = returns an empty string (Pass-1 prompt builder skips
    the section gracefully).
    """
    if not analogues:
        return ""
    lines = ["## Historical analogues (k=" + str(len(analogues)) + ", past-only)\n"]
    for i, a in enumerate(analogues, start=1):
        date_str = a.created_at.strftime("%Y-%m-%d")
        regime_str = f"regime={a.regime}, " if a.regime else ""
        asset_str = f"asset={a.asset}, " if a.asset else ""
        # Truncate long content for prompt budget — full text remains in
        # the DB ; Pass-1 only needs the gist.
        snippet = a.content[:400].replace("\n", " ").strip()
        if len(a.content) > 400:
            snippet += " …"
        lines.append(
            f"{i}. **{date_str}** — {asset_str}{regime_str}"
            f"cos_dist={a.cosine_distance:.3f}\n"
            f"   {snippet}\n"
        )
    lines.append(
        "\n*These analogues are descriptive — they do not prescribe today's bias "
        "(ADR-017 boundary). Use as sanity check vs your régime call.*\n"
    )
    return "\n".join(lines)
