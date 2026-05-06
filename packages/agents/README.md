# `packages/agents` — Couche-2 + Critic agents (Pydantic AI + Claude runner)

Production-grade Couche-2 24/7 automation agents and the Critic Agent
gate that polices Couche-1 session cards before they land in
`session_card_audit`. Stack : `pydantic-ai-slim[openai]` (Voie D
constraint, no `anthropic` SDK) + a Claude path through the local
Win11 runner (cf. `claude_runner.py`).

## Agent map (current — supersedes the original Phase 0 plan)

Routing decisions :

- [ADR-009](../../docs/decisions/ADR-009-voie-d-no-api-consumption.md)
  Voie D : everything goes through Eliot's Max 20x subscription via
  `apps/claude-runner` subprocess; Cerebras + Groq free tiers stay
  installed as transparent fallback.
- [ADR-021](../../docs/decisions/ADR-021-couche2-via-claude-not-fallback.md)
  Couche-2 → Claude primary, Cerebras / Groq fallback only.
- [ADR-023](../../docs/decisions/ADR-023-couche2-haiku-not-sonnet-on-free-cf-tunnel.md)
  Couche-2 → Haiku 4.5 effort=low (CF Free tunnel 100 s edge cap
  rules out Sonnet medium for the time being).

| Agent        | Primary model       | Fallback chain         | Cadence                  | Layer        |
| ------------ | ------------------- | ---------------------- | ------------------------ | ------------ |
| Macro        | Claude Haiku 4.5    | Cerebras → Groq        | every 4h offset +75 min  | Couche 2     |
| CB-NLP       | Claude Haiku 4.5    | Cerebras → Groq        | every 4h offset +15 min  | Couche 2     |
| News-NLP     | Claude Haiku 4.5    | Cerebras → Groq        | every 4h offset +45 min  | Couche 2     |
| Sentiment    | Claude Haiku 4.5    | Cerebras → Groq HV     | every 6h offset +30 min  | Couche 2     |
| Positioning  | Claude Haiku 4.5    | Cerebras → Groq HV     | every 6h offset +90 min  | Couche 2     |
| Critic       | (in `critic/`)      | local Pydantic AI Agent (no runner) | per session-card  | Couche 1 gate |

The 5 Couche-2 agents share the `FallbackChain` adapter
(`fallback.py`). When `claude=ClaudeRunnerConfig.from_env()` is set,
the chain tries Claude first and treats Cerebras + Groq as a
strict fallback. Each agent's factory passes `model="haiku",
effort="low"` (cf. agent files).

`HttpRunnerClient` (in `packages/ichor_brain/runner_client.py`) and
`call_agent_task` (in `claude_runner.py`) both ship with a
5 / 15 / 45 s exponential-backoff retry on HTTP 503 (`Another
briefing/task in flight`) and 429 (rate-limited). 524 (Cloudflare
edge timeout) fails fast — retrying would hit the same wall.

## Wire contract

Couche-2 calls go through `apps/claude-runner`:

  `POST /v1/agent-task`
  Body: `{ system, prompt, model, effort }` →
  Response: `{ status, output_text, raw_claude_json, duration_ms }`

The adapter injects the JSON Schema of the agent's `output_type`
into the prompt tail so Claude returns valid `MacroAgentOutput` /
`CbNlpAgentOutput` / etc. that `model_validate_json` can ingest.

## What's in this package

```
packages/agents/src/ichor_agents/
├── claude_runner.py           ClaudeRunnerConfig + call_agent_task adapter
├── fallback.py                FallbackChain orchestrator
├── providers.py               Cerebras / Groq Pydantic AI providers
├── agents/                    5 Couche-2 chain factories + output schemas
│   ├── macro.py
│   ├── cb_nlp.py
│   ├── news_nlp.py
│   ├── sentiment.py
│   └── positioning.py
├── critic/                    Couche-1 Critic Agent (gate before persistence)
│   ├── reviewer.py
│   └── cross_asset.py
├── predictions/divergence.py  Couche-1 ↔ Couche-2 divergence detector
└── voice/                     TTS pipeline (text_normalize, tts)
```

## Tests

`pytest tests/` covers the 5 chain factories' schema validity, the
Claude path adapter (config / fence-strip / retry), the
FallbackChain integration, and edge cases (503 retry, 524 fail-fast).
82+ tests, fast and deterministic.
