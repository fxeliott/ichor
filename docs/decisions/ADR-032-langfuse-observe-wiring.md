# ADR-032: Langfuse `@observe` wiring on 4-pass + Couche-2

- **Status**: Accepted
- **Date**: 2026-05-07
- **Deciders**: Eliot
- **Implements**: ROADMAP Phase A.4.c — "Langfuse `@observe` decorator
  sur les 4 passes + 5 agents Couche-2 (couverture actuelle = 1 fichier
  sur des dizaines)" (`docs/ROADMAP_2026-05-06.md:98`).

## Context

Langfuse v3 has been running on Hetzner since Phase 0
(`infra/ansible/roles/langfuse/` provisions Postgres + ClickHouse +
MinIO + Langfuse), and `apps/api/src/ichor_api/config.py:115-117`
already exposes `langfuse_public_key`, `langfuse_secret_key`,
`langfuse_host` settings — yet **no Python code in the repo ever
imports `langfuse`** (verified by grep 2026-05-07). Every 4-pass run
that hits Hetzner is invisible: no input/output capture, no
duration histograms, no per-pass token usage, no parent-child trace
hierarchy linking the 4 passes of a single session card.

The Langfuse Python SDK was rewritten as **v4 (March 2026)**. The
new public API exposes a bare `from langfuse import observe`
decorator (no longer namespaced under `langfuse.decorators.observe`)
and a worker-thread queue that requires explicit `flush()` in
short-lived hosts (FastAPI, AWS Lambda).

## Decision

**Wire `@observe` at three semantic layers**, with one trace per
session card and per-LLM-call generations linked beneath:

| Trace level     | Decorator                                        | Where                                                              |
|-----------------|--------------------------------------------------|--------------------------------------------------------------------|
| Trace 4-pass    | `@observe(name="session_card_4pass")`            | `ichor_brain.orchestrator.Orchestrator.run`                        |
| Generation L1   | `@observe(as_type="generation", name="couche1_runner_call")` | `ichor_brain.runner_client.HttpRunnerClient.run`         |
| Trace L2 chain  | `@observe(name="couche2_chain")`                 | `ichor_agents.fallback.FallbackChain.run`                          |
| Generation L2   | `@observe(as_type="generation", name="couche2_agent_task")` | `ichor_agents.claude_runner.call_agent_task`              |

This produces a clean parent-child hierarchy in the Langfuse UI:
```
session_card_4pass (4-pass orchestrator)
├── couche1_runner_call (Pass 1 régime)
├── couche1_runner_call (Pass 2 asset)
├── couche1_runner_call (Pass 3 stress)
└── couche1_runner_call (Pass 4 invalidation)
```
And independently, each Couche-2 agent run produces:
```
couche2_chain (FallbackChain.run)
└── couche2_agent_task (call_agent_task — Claude path)
```

### Fail-soft via package-local shim

Both `packages/ichor_brain` and `packages/agents` ship a
`observability.py` module with a try/except import:

```python
try:
    from langfuse import observe
except ImportError:
    def observe(*args, **kwargs):
        if len(args) == 1 and callable(args[0]) and not kwargs:
            return args[0]
        def _decorator(fn): return fn
        return _decorator
```

Three call patterns are transparently supported (matches SDK v4 API):
`@observe`, `@observe()`, `@observe(name="x", as_type="generation")`.

When `langfuse` is not installed (CI, unit tests, dev shells without
the optional dep), `observe` is a no-op — decorated functions stay
equivalent to their bare form. This is the same fail-soft pattern as
the `prometheus-fastapi-instrumentator` wrap landed in Phase A.4.a.

### Lifecycle in `apps/api/main.py`

`apps/api/src/ichor_api/observability.py` owns the `Langfuse` client
singleton. The FastAPI lifespan calls:
- `init_langfuse()` at startup — reads keys from settings, constructs
  the client, swallows any exception (boot must not fail on
  observability flakes).
- `flush_langfuse()` at shutdown, BEFORE the SQLAlchemy engine
  disposes — drains the worker thread queue so the last few traces
  finish serialising while the DB pool is still alive.

### Dependency placement

- `apps/api/pyproject.toml` — `langfuse>=4.0.0` is a **hard dep** of
  the API package. Production needs traces.
- `packages/ichor_brain/pyproject.toml` — `langfuse>=4.0.0` is in
  `[observability]` extra, **optional**. Tests run without it.
- `packages/agents/pyproject.toml` — same pattern. Optional.

Reasoning: only the API process actually emits traces. The two
packages just decorate functions; the decorator is a no-op when
the runtime env doesn't have the lib.

## Consequences

### Pros

- **Visibility on the entire 4-pass.** Every session card is now a
  named trace with input (data_pool, asset_data) and output
  (`OrchestratorResult.card`) captured by Langfuse v4 contextvar
  propagation.
- **Per-pass duration histograms** are implicit — Langfuse measures
  decorated function durations natively. Pass 1/2/3/4 latency drift
  is now a chart in the UI rather than a log-grep exercise.
- **LLM-call generation type** lets Langfuse correlate inputs/outputs
  with token usage (currently only `duration_ms` is recorded; the
  runner could populate `usage` once the Claude CLI exposes it).
- **Couche-2 fallback chain visibility** — when Cerebras or Groq
  fires (Claude path failed), the trace shows the failover sequence
  with `last_success` provider:model.

### Cons

- **Tokenizer cost on Hetzner** — inputs/outputs are serialized + sent
  to Langfuse. For a session card the data_pool can be 30-50 KB; that's
  ~150-200 KB per session card x 32 cards/day = ~6 MB/day of trace
  payload. Negligible vs ClickHouse capacity but worth flagging if we
  later add high-frequency traces (FX-tick collectors, etc.).
- **Hard dep on Langfuse v4 in `apps/api`.** If Langfuse breaks (server
  down, lib bug), the API still boots (init swallows exceptions) but
  the trace queue silently drops events. Mitigation: existing
  `prometheus-fastapi-instrumentator` keeps `/metrics` independent.
- **No upstream context propagation across cron CLIs yet.** Each
  `cli/run_session_cards_batch.py` invocation produces a fresh top-level
  trace per asset×session call — no "batch run" parent. Acceptable for
  v1; can add a manually-created span later via
  `langfuse.start_as_current_span("session_cards_batch")`.

### Neutral

- **No StreamingResponse traces tested.** The known SDK v4 issue
  (`https://github.com/langfuse/langfuse/issues/8216`) splits a stream
  into N traces. Ichor's `/v1/briefing-task` is request/response, not
  streamed — non-issue for now.

## Alternatives considered

### A — Pure OpenTelemetry instead of Langfuse decorator

Rejected. OTel is already wired (`opentelemetry-instrumentation-fastapi`
in `apps/api/pyproject.toml:20`) and gives us HTTP middleware traces,
but not LLM-specific concepts (`as_type="generation"`, prompt
versioning, score creation). Langfuse v4 sits *on top* of OTel for
its propagation; the decorator is the right abstraction for LLM
flows.

### B — Manually instantiate spans (`langfuse.span(...)` blocks)

Considered but verbose. Each pass would need a `with langfuse.span(...)`
block plus exception handling. The decorator captures inputs/outputs
automatically and is one line. Rejected as worse ergonomics.

### C — Class-level `@observe` on `Orchestrator` (instead of method)

Rejected: SDK v4 docs warn that decorating a class can break MRO and
miss async methods. Per-method is the documented pattern.

## Implementation

Code shipped on `claude/blissful-lewin-22e261` (commit landing with
this ADR):

- 3 new modules (~50 LOC total):
  - `packages/ichor_brain/src/ichor_brain/observability.py` — shim no-op.
  - `packages/agents/src/ichor_agents/observability.py` — shim no-op.
  - `apps/api/src/ichor_api/observability.py` — client lifecycle.
- 5 patches:
  - `packages/ichor_brain/src/ichor_brain/orchestrator.py:111` — `@observe(name="session_card_4pass")`.
  - `packages/ichor_brain/src/ichor_brain/runner_client.py:117` — `@observe(as_type="generation", ...)`.
  - `packages/agents/src/ichor_agents/fallback.py:60` — `@observe(name="couche2_chain")`.
  - `packages/agents/src/ichor_agents/claude_runner.py:138` — `@observe(as_type="generation", ...)`.
  - `apps/api/src/ichor_api/main.py:91` — lifespan `init_langfuse()` / `flush_langfuse()`.
- 3 dependency changes:
  - `apps/api/pyproject.toml` — `langfuse>=4.0.0` (hard dep).
  - `packages/ichor_brain/pyproject.toml` — `[observability]` optional extra.
  - `packages/agents/pyproject.toml` — same.

### Deployment

Hetzner: `ssh ichor-hetzner '/opt/ichor/api/.venv/bin/pip install langfuse>=4.0.0'`
then `sudo systemctl restart ichor-api.service`. Verify traces flow:
```bash
curl -X POST http://127.0.0.1:8000/v1/sessions/run-cards \
     -H 'Content-Type: application/json' \
     -d '{"session_type":"event_driven","assets":["EUR_USD"]}'
sleep 60
# Open Langfuse UI: https://langfuse.ichor.internal
# Filter on "session_card_4pass" — should see 1 trace with 4 child generations.
```

Not deployed in this commit — deferred to the next Hetzner sync window
(annonce préalable required: `pip install` is a réseau sortante action
per Eliot's standing guard-rails).

## Followups

- **RUNBOOK-016** — How to query traces by asset/session, how to debug
  missing-trace issues. Companion of this ADR.
- **Score creation** — once `last_success` provider tracking lands in
  the trace tags, we can call `langfuse.create_score()` from
  `services/critic_audit.py` to feed Critic verdicts back into the
  trace for offline analysis (cf ADR-022 Brier loop closure).
- **Couche-2 agent name in trace** — today every chain run is just
  `couche2_chain`; add the agent name (cb_nlp/news_nlp/macro/...) via
  `langfuse.update_current_observation(metadata={"agent": ...})` once
  the chain knows its identity (currently it doesn't; see
  `packages/agents/src/ichor_agents/agents/__init__.py` for the factory
  registry).

## Related

- ADR-009 — Voie D (Max 20x via local subprocess) — the runner client
  is the LLM gateway being traced.
- ADR-021 → ADR-023 — Couche-2 mapping (Sonnet → Haiku low). Traces will
  validate the latency claim post-deploy (Sonnet medium 60-130 s vs
  Haiku low <30 s).
- ADR-022 — Probability bias models reinstated (Critic gate). The trace
  hierarchy makes Critic feedback localizable to a specific pass.
- `docs/SPEC_V2_AUTOEVO.md:307` — defines the parent/child pattern this
  ADR implements: `langfuse.trace(name="session_card") → spans per pass`.
