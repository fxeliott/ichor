# ADR-086: RAG layer — past-only retrieval + bge-small Voie D + Cap5 exclusion

**Status**: Accepted — pre-implementation contract (code lands W110)

**Date**: 2026-05-12

**Supersedes**: none

**Extends**: [ADR-009](ADR-009-voie-d-no-api-consumption.md) (Voie D no metered API), [ADR-017](ADR-017-reset-phase1-living-macro-entity.md) (boundary), [ADR-078](ADR-078-cap5-query-db-excludes-trader-notes.md) (Cap5 allowlist forbidden set), [ADR-081](ADR-081-doctrinal-invariant-ci-guards.md) (CI guards), [ADR-085](ADR-085-pass-6-scenario-decompose-taxonomy.md) (Pass-6 + 7-bucket reconciler — RAG consumer)

## Context

Ichor Pass-1 régime emission today is **stateless** : it sees the current `data_pool` markdown and emits a régime quadrant + rationale. There is no historical memory — the LLM cannot reference what happened in _similar past macro states_ and how those sessions played out.

Round-7 audit (8 dimensions) scored **Couche 8 RAG = 4/10** : `session_card_audit` persistence + W105a scenarios JSONB + W105b calibration bins exist, but pgvector embeddings + retrieval injection into Pass-1 prompt are absent. This is the **single most transformative gap** for Dimensions 3 (Intelligent) + 8 (Précis).

The W110 RAG implementation must respect three doctrinal invariants that this ADR makes contractual.

## Decision

### Invariant 1 — Past-only retrieval (anti-leakage temporal)

The RAG retriever **MUST** filter `chunk_at < query_at - INTERVAL '1 day'` on every query. No same-day or same-session contamination. This is enforced :

- **DB-level** : the `scenario_calibration_bins` PK + `chunk_at` index on `rag_chunks_index` make the filter cheap.
- **Service-level** : `services/rag_embeddings.py:retrieve_analogues(query_state, query_at, k=5, embargo_days=1)` — `embargo_days` parameter is REQUIRED, not optional, and the function `RAISES ValueError` when `embargo_days < 1`.
- **CI-guarded** : new test `test_rag_anti_leakage.py` asserts no chunk with `chunk_at >= query_at - 1day` ever surfaces in retrieval output across a stratified sample.

Reference : _"History Rhymes: Macro-Contextual Retrieval for Robust Financial Forecasting"_ (arXiv 2511.09754, Nov 2025) — past-only macro retrieval for stabilising forecasts under regime shift. **FinSeer** (arXiv 2502.05878) — past-only time-series retrieval.

The W105g realized-outcome reconciler is the natural feedback loop : it writes `realized_scenario_bucket` AFTER the session window closes ; chunks indexed at session-end include the realized outcome, making them informative for future retrievals without contamination.

### Invariant 2 — Voie D embedding model (bge-small-en-v1.5 ONNX CPU)

Default embedding model **MUST** be `BAAI/bge-small-en-v1.5` (384-dim, 33M params), inference via ONNX Runtime CPU with O2 graph optimization + dynamic INT8 quantization. Performance benchmarks 2026 :

- Latency : sub-50ms per chunk on Hetzner CPU (Microsoft VNNI 2.9× speedup vs FP32).
- Quality : MTEB-en ~62, sufficient for English macro narrative.
- Storage : 384 × float32 = 1.5 KB per vector ; 5-year × 6 assets × 4 windows × 365d ≈ 44k chunks → ~200 MB total.
- Voie D compliance : self-hosted, no metered API, no Anthropic SDK consumption (ADR-009 strict).

**Rejected alternatives** :

- `text-embedding-3-small` (OpenAI) — paid API, Voie D violation.
- `voyage-finance-2` / `voyage-3-large` — paid API.
- `cohere-embed-v4` — paid API.
- `bge-large-en-v1.5` (1024d, 335M params) — viable upgrade in W120+ when FinMTEB delta (+1 point retrieval) justifies the 2.7× storage and 4× latency.
- `BGE-M3` multilingual sparse+dense — overkill for English-only Ichor v1 ; revisit if multilingual GDELT events ingestion lands W114+.

### Invariant 3 — Cap5 `query_db` allowlist EXCLUDES `rag_chunks_index`

The W83 Cap5 sqlglot whitelist parser at `apps/api/src/ichor_api/services/tool_query_db.py:ALLOWED_TABLES` (frozenset of 6 tables) **MUST NOT** include `rag_chunks_index` or any future `rag_*` table.

**Why** : if Couche-2 agents (`cb_nlp`, `news_nlp`, `sentiment`, `positioning`, `macro`) could query `rag_chunks_index` directly via `mcp__ichor__query_db`, they would short-circuit the orchestrator's retrieval-injection contract and risk leakage (Couche-2 runs more frequently than Couche-1, with different temporal embargoes). Past-only enforcement is a property of the _retrieval service_, not the SQL grant — exposing the raw table delegates discipline to every consumer, which is the wrong layer.

CI guard test `test_rag_chunks_index_excluded_from_cap5_allowlist` (extends `test_tool_query_db_allowlist_guard.py`) asserts `'rag_chunks_index' not in ALLOWED_TABLES`. Bonus invariant : `'rag_chunks_index' in FORBIDDEN_SET` — explicit denial.

## Implementation roadmap (W110 sub-waves)

| Sub-wave | Title                                                                                                                | Effort                               |
| -------- | -------------------------------------------------------------------------------------------------------------------- | ------------------------------------ |
| W110a    | Migration 0040 + ORM `RagChunkIndex`                                                                                 | **DONE round 10** (commit `12ee377`) |
| W110b    | `services/rag_embeddings.py` — bge-small ONNX backend + embed_text + retrieve_analogues                              | 1d                                   |
| W110c    | CLI runner `cli/embed_session_cards.py` — bulk embed 44k past cards + idempotent on chunk_id + ONNX batch=32         | 0.5d                                 |
| W110d    | `passes/regime.py` Pass-1 prompt builder injection — `## Historical analogues (k=5, past-only, embargo 1d)` section  | 0.5d                                 |
| W110e    | CI guards `test_rag_anti_leakage.py` + `test_rag_retrieval_determinism.py` + `test_rag_embargo_boundary.py`          | 0.5d                                 |
| W110f    | RAGAS triad evaluation (Faithfulness + Context Precision + Context Recall ≥ 0.8) with local Haiku low judge (Voie D) | 1d                                   |
| W110g    | Systemd timer `ichor-rag-incremental-embed.timer` — nightly catch-up on new session_card_audit rows                  | 0.5d                                 |

**Total** : ~4-5 dev-days.

### Pass-1 prompt injection format (W110d)

The Pass-1 régime prompt gains a new section between `data_pool` and the closing instruction :

```markdown
## Historical analogues (k=5, past-only, embargo 1d)

The following past sessions had similar macro states (cosine similarity

> 0.85 against current data_pool embedding) :

1. **2024-11-08 pre_londres EUR_USD** — regime: usd_complacency,
   bias: short, conviction: 32%, realized: mild_bear (Brier 0.21).
   Mechanism extract: "Powell dovish-leaning press conf …"

2. **2024-09-12 pre_londres EUR_USD** — regime: goldilocks, bias: long,
   conviction: 58%, realized: mild_bull (Brier 0.14).
   …

These analogues are descriptive — they do not prescribe today's bias.
Use them as a sanity check : if your régime call diverges from 4/5
analogues that converged on a different bucket, increase your stress-
test weight (Pass-3).
```

## Open questions resolved by web research 2026

- **HNSW vs IVFFlat** : HNSW everywhere (15.5× QPS at 99% recall, pgvector 0.7+ benchmark). `m=16 + ef_construction=64` default for 44k vectors ; tune up to `m=24 + ef_construction=100` if recall drops on hold-out evaluation.
- **Chunking strategy** : 1 session_card = 1 chunk. The markdown narrative (~512 tokens) is self-contained ; intra-card recursive split breaks Pass-1→Pass-4 cohesion.
- **Reranker** : `bge-reranker-v2-m3` (0.6B, multilingual, Voie D OK) optional W120 — lifts Hit@1 from 62% → 83% on top-100 → top-10. Skip for W110 v1.
- **Hybrid BM25 + dense + RRF** : skip W110 v1 (dense-only is acceptable for k=5 retrieval) ; revisit W120 if recall@5 < 0.75 on RAGAS eval.
- **Latency budget Pass-1** : embed query (50ms) + HNSW search 44k vec (5ms) + Postgres roundtrip (5ms) + prompt assembly (10ms) = ~70ms. Acceptable for nightly cron path ; intraday hot path stays sub-100ms.

## Acceptance criteria (W110 ship gate)

1. Migration 0040 deployed Hetzner ; `rag_chunks_index` table exists with HNSW index. **DONE round 10.**
2. `services/rag_embeddings.py` implements `embed_text` + `retrieve_analogues(..., embargo_days=1)` ; CI guard `test_rag_anti_leakage.py` green.
3. CLI `embed_session_cards.py` ingests all past `session_card_audit` rows with `realized_at IS NOT NULL` (reconciled cards have richer payload).
4. Pass-1 prompt builder injects the `## Historical analogues` section ; `passes/regime.py:build_prompt` extended.
5. RAGAS triad on a 200-question golden set ≥ 0.8 on Faithfulness + Context Precision + Context Recall.
6. CI guard `test_rag_chunks_index_excluded_from_cap5_allowlist` green ; ADR-078 forbidden set extended.
7. Systemd timer `ichor-rag-incremental-embed.timer` enabled — nightly idempotent catch-up.
8. RAG retrieval skill score : 7-bucket Brier improves by ≥ 5% absolute on cards generated WITH RAG vs WITHOUT (A/B over 30 cards rolling).

## References

- ADR-009 (Voie D — no metered API)
- ADR-017 (Boundary)
- ADR-078 (Cap5 query_db forbidden set)
- ADR-081 (CI-guarded doctrinal invariants)
- ADR-085 (Pass-6 7-bucket — RAG consumer)
- [History Rhymes: Macro-Contextual Retrieval — arXiv 2511.09754](https://arxiv.org/html/2511.09754v1) (Nov 2025)
- [FinSeer: Retrieval-augmented LLMs for Financial Time Series — arXiv 2502.05878](https://arxiv.org/abs/2502.05878) (Feb 2025)
- [BAAI/bge-small-en-v1.5 model card](https://huggingface.co/BAAI/bge-small-en-v1.5)
- [pgvector HNSW vs IVFFlat benchmarks 2026](https://www.crunchydata.com/blog/hnsw-indexes-with-postgres-and-pgvector)
- [Sentence Transformers ONNX backend efficiency](https://sbert.net/docs/sentence_transformer/usage/efficiency.html)
- [RAGAS Faithfulness + Context Precision metrics](https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/faithfulness/)
