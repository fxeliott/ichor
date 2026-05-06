# ADR-020: RAG embeddings = `bge-small-en-v1.5` self-hosted on Hetzner CPU

- **Status**: Accepted
- **Date**: 2026-05-04
- **Decider**: Eliot (validated 2026-05-04 §14)

## Context

Phase 2 RAG layer (cf [`SPEC.md §3.7`](../../SPEC.md) +
[`docs/SPEC_V2_AUTOEVO.md §1`](../SPEC_V2_AUTOEVO.md)) needs an embedding
model. Constraints:

- ADR-009 forbids paid API embeddings (no Voyage, no OpenAI text-embedding-3,
  no Cohere). Self-host or nothing.
- Hetzner CX32 = CPU-only, 16 GB RAM. No GPU.
- Latency budget: <120 ms per chunk (we re-embed cards on each post-mortem
  and on Brier reconciliation; corpus expected ~50k chunks @ 5y horizon).
- Quality target: enough recall to not lose Phase 1 Brier skill.

## Decision

**Use `bge-small-en-v1.5` (BAAI, 384 dimensions).** Served via either
HuggingFace TEI (Text Embeddings Inference) or `optimum`/ONNX runtime — both
CPU-friendly. Default to TEI for V1 simplicity; revisit ONNX if CPU
saturation under load.

Storage in `pgvector` 384-dim column with HNSW index per
[ADR-019](ADR-019-pgvector-hnsw-not-ivfflat.md).

Phase 2 stays at `bge-small`. Upgrade gate to `bge-large-en-v1.5` (1024-dim)
documented at [`SPEC.md §3.7`](../../SPEC.md): triggered if
RAGAS `recall@5 < 0.7` sustained for 30 days, or if Brier skill degrades
≥5% attributable to retrieval (per RAGAS faithfulness root-cause).

## Consequences

**Easier**:

- Zero ongoing cost. No API key to rotate.
- 384-dim is 2.6× smaller than 1024-dim → less RAM pressure on HNSW index
  (~600 MB index for 50k chunks vs 1.5 GB).
- Stable behavior — no surprise deprecation by a vendor.

**Harder**:

- Recall ceiling lower than `bge-large` or paid alternatives. Mitigated
  by hybrid RRF (dense + BM25) which compensates for embedding-only weakness
  on rare-term queries.
- HuggingFace model download is a network egress dependency on first boot.
  Cached locally afterwards.

**Trade-offs**:

- We accept ~5-8% recall@5 below `bge-large` in exchange for $0/mo and
  stable on-device inference. The hybrid RRF mitigates most of the gap.

## Alternatives considered

- **`bge-large-en-v1.5` (1024d)**: deferred to Phase 2.5+ if recall floor
  not met. 4× memory for ~5-8% recall improvement, not worth it on Day 1.
- **`gte-small` / `gte-base`**: rejected. Equivalent quality, slightly
  worse Massive Text Embedding Benchmark (MTEB) scores at the same size.
- **Voyage / OpenAI / Cohere**: rejected by ADR-009 (paid API).
- **`mxbai-embed-large`**: candidate for Phase 2.5 upgrade alongside
  `bge-large`; benchmarks similar.

## References

- [`SPEC.md §3.7, §10, §4`](../../SPEC.md)
- [`docs/SPEC_V2_AUTOEVO.md §1.4, §1.5, §6.5`](../SPEC_V2_AUTOEVO.md)
- [ADR-009 (Voie D)](ADR-009-voie-d-no-api-consumption.md)
- [ADR-019 (HNSW)](ADR-019-pgvector-hnsw-not-ivfflat.md)
- BGE model card: <https://huggingface.co/BAAI/bge-small-en-v1.5>
