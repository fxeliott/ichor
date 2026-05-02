# `packages/agents` — Claude + Pydantic AI agent definitions

Phase 0 V1 stack: **Claude Agent SDK + Pydantic AI only** (per `docs/AUDIT_V3.md` §4.7).
DSPy / LlamaIndex / Letta deferred to Phase 2-6.

## Agent map

| Agent | Default model | Layer |
|------|---------------|-------|
| Orchestrator | Opus 4.7 | Couche 1 (Claude qualitative) |
| Journalist | Opus 4.7 | Couche 1 |
| Critic | Sonnet 4.6 | Couche 1 |
| Macro | Cerebras Llama 3.3-70B (fallback Sonnet 4.6) | Couche 2 |
| Sentiment | Cerebras (fallback Sonnet 4.6) | Couche 2 |
| Positioning | Cerebras (fallback Sonnet 4.6) | Couche 2 |
| CB-NLP | Cerebras (fallback Sonnet 4.6) + FOMC-RoBERTa + FinBERT-tone | Couche 2 + Couche 3 ML |
| News-NLP | Groq Llama 3.1 8B Instant (fallback Haiku 4.5) | Couche 2 |

## Phase 0 status

🚧 Skeleton only. Persona Ichor v1 prompt + agent factories in Phase 0 Week 4 (step 31).
