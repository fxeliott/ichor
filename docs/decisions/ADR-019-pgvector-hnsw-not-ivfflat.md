# ADR-019: pgvector index = HNSW (not IVFFlat) with `m=16, ef_construction=64`

- **Status**: Accepted
- **Date**: 2026-05-04
- **Decider**: Eliot (validated 2026-05-04 §14)

## Context

Phase 2 introduces a RAG layer for the 5-year history of cards / briefings
/ post-mortems (cf [`SPEC.md §3.7`](../../SPEC.md)). Postgres + the
`pgvector` extension is the chosen vector store (zero new dependency, leans
on existing wal-g backups and Hetzner host).

`pgvector` ships two index types:

| Index   | Build time | Query QPS @ 99% recall  | Memory | Build precondition |
| ------- | ---------- | ----------------------- | ------ | ------------------ |
| IVFFlat | fast       | low                     | low    | needs trained data |
| HNSW    | slower     | high (1.4×–30× IVFFlat) | 2-5×   | builds on empty    |

Recent (2026-Q1) `pgvector 0.7+` benchmarks (cf
[Instaclustr](https://www.instaclustr.com/education/vector-database/pgvector-performance-benchmark-results-and-5-ways-to-boost-performance/)
and [Tembo](https://www.tembo.io/blog/vector-indexes-in-pgvector)) show
HNSW reaching ~40 QPS at 0.998 recall vs ~2.6 QPS for IVFFlat, on
single-instance Postgres with parallel HNSW builds and quantization.

## Decision

**Use HNSW with `m=16, ef_construction=64`.** `ef_search` is set at query
time in the 40–100 range (default 40 in production, raised to 80 for
analyst-driven counterfactual queries).

Migration: [`apps/api/migrations/versions/0011_pgvector_extension.py`](../../apps/api/migrations/versions/0011_pgvector_extension.py)
installs the extension; [`0012_rag_chunks_index.py`](../../apps/api/migrations/versions/0012_rag_chunks_index.py)
creates the table with the HNSW index inline.

Embedding dimension is 384 (BGE-small-en-v1.5 — see ADR-020).

## Consequences

**Easier**:

- Higher recall at production QPS without parameter sweeps.
- Index can be built incrementally on a populated table without re-training.
- Behavior is stable across dataset sizes; we don't need to revisit
  `lists` parameter when the corpus grows.

**Harder**:

- 2-5× memory footprint vs. IVFFlat (acceptable for current corpus size,
  forecast 50k chunks max for the 5-year history).
- Build time on bulk re-index is longer; mitigated by `0.7+` parallel HNSW
  builds.

**Trade-offs**:

- We lock in HNSW now even though IVFFlat would be cheaper at very-large
  scale. If the corpus exceeds ~5M chunks, revisit and consider hybrid
  HNSW + IVFFlat partitioning.

## Alternatives considered

- **IVFFlat** with `lists = sqrt(rows)`: rejected. Lower recall at our
  target QPS, requires re-indexing as corpus grows.
- **Qdrant / Weaviate / Milvus** as a separate service: rejected.
  Operational overhead (separate process, separate backup) without
  marginal benefit at our scale.
- **No index** (sequential cosine scan): rejected. Latency budget for
  Pass 1 RAG retrieval is <300 ms p99; sequential scan exceeds that
  past ~5k chunks.

## References

- [`SPEC.md §3.7, §10`](../../SPEC.md)
- [`docs/SPEC_V2_AUTOEVO.md §1.3, §6.5`](../SPEC_V2_AUTOEVO.md)
- pgvector docs: <https://github.com/pgvector/pgvector>
- 2026 benchmarks: Instaclustr, Tembo (linked above)
