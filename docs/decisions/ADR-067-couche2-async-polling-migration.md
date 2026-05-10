# ADR-067: Couche-2 → async polling pattern (CF Tunnel 100s structural fix)

- **Status**: Accepted
- **Date**: 2026-05-09
- **Deciders**: Eliot
- **Supersedes**: extends ADR-053 (briefing-task/async W20) to agent-task path
- **Related**: ADR-021 (Claude primary brain), ADR-023 (Couche-2 → Haiku low),
  ADR-053 (briefing async), ADR-054 (claude-runner stdin pipe)

## Context

Wave 67 audit found 5 Couche-2 systemd units (`ichor-couche2@{cb_nlp,
news_nlp, sentiment, positioning, macro}.service`) in `failed` state on
2026-05-08 evening with `runner returned HTTP 502/524` errors:

```
agents.claude_runner.try       effort=low model=haiku prompt_len=5025 system_len=742
agents.fallback.claude_failed  error='runner returned HTTP 524: <Cloudflare timeout HTML>'
                               error_type=ClaudeRunnerError
agents.fallback.skip_no_creds  model=llama-3.3-70b provider=cerebras
agents.fallback.skip_no_creds  model=llama-3.3-70b-versatile provider=groq
couche2.run.failed             error="AllProvidersFailed('claude=ClaudeRunnerError,
                                cerebras=MissingCredentials, groq=MissingCredentials')"
```

### Root cause identical to ADR-053 wave 20

Cloudflare Tunnel free plan enforces a **100-second edge timeout** on
streaming-disabled HTTP responses. The legacy synchronous
`/v1/agent-task` endpoint (apps/claude-runner/main.py:304) runs
`claude -p` subprocess inline. Haiku low takes 30-130s typical depending
on prompt size, with cb_nlp (5 KB) and news_nlp (12 KB) routinely
exceeding 100s.

Subprocess completes successfully on Win11 origin, but Cloudflare drops
the request with HTTP 524 mid-flight. The Couche-2 chain falls through
to Cerebras/Groq fallback which immediately fails on
`MissingCredentials`, propagating `AllProvidersFailed` and putting the
systemd unit into `failed` state.

This silently broke 3/5 Couche-2 agents on every cron run. The
`couche2_outputs` table received error rows instead of structured
agent outputs.

### Why ADR-053 didn't cover this

ADR-053 fixed `briefing-task/async` for the 4-pass orchestrator
(`HttpRunnerClient` in `packages/ichor_brain/`). Couche-2 uses a
separate adapter at `packages/agents/claude_runner.py:141`
(`call_agent_task`) calling `/v1/agent-task` (sync) — a parallel code
path that was missed.

## Decision

Mirror ADR-053 exactly on the agent-task path:

### Server side (apps/claude-runner/main.py)

Add 2 endpoints + 1 background runner:

- `POST /v1/agent-task/async` → 202 Accepted + `task_id` (sub-second).
  Validates rate-limit, registers task in shared `_async_tasks` store,
  spawns `asyncio.create_task(_run_agent_background(...))`, returns
  immediately.

- `GET /v1/agent-task/async/{task_id}` → status (each call <100ms,
  well under 100s edge cap). Returns `pending` → `running` → `done`
  (with `result: AgentTaskResponse`) | `error`.

- `_run_agent_background(task_id, req, settings)` mirrors
  `_run_briefing_background` but persists `req.system` as
  `--append-system-prompt` persona. Same `_subprocess_semaphore`,
  `_async_tasks` store, GC, rate-limiter as briefings (single envelope).

### Client side (packages/agents/claude_runner.py + fallback.py)

- New: `call_agent_task_async(cfg, system, prompt, output_type, ...)`.
  Submit + poll loop (5s cadence, 600s budget). Same return contract
  (raw text or validated Pydantic instance).

- `FallbackChain.use_async_endpoint: bool = True` (default). Routes
  Couche-2 calls through async path. Set `False` for tests / legacy.

### Pydantic AsyncTaskStatus.result Union (W67b)

Original `result: BriefingTaskResponse | None` rejected the
`AgentTaskResponse` payload at serialization, returning HTTP 500 on
GET poll. Fixed: `result: BriefingTaskResponse | AgentTaskResponse | None`.

## Consequences

### Positive

- **Structural CF 524 immunity**: each HTTP call (submit + each poll)
  completes in <1s. Subprocess wall-time is no longer bounded by
  Cloudflare's edge timeout.
- **Live verification 2026-05-09 11:08 CEST**: cb_nlp completed in
  **111s** wall-time via async (`elapsed_sec=111.0 poll_count=22 status=done`)
  — would have 524'd on legacy sync path.
- **All 5 Couche-2 agents migrated** : same `FallbackChain.run()`
  call path, async pattern transparent to callers.
- **Rate-limit + concurrency guards preserved**: shared
  `_subprocess_semaphore` (max_concurrent=1) + shared `_rate_limiter`
  (Hourly Max 20x quota) still enforced. Submissions can be queued;
  execution is serialized.
- **Back-compat**: `use_async_endpoint=False` flag preserves legacy
  sync path for tests.

### Negative

- **5 Couche-2 timers fired in parallel now serialize**: with
  `max_concurrent_subprocess=1`, batch of 5 agents takes
  ~5×60-110s = 5-9 minutes total. Was already serialized via
  503 retry with backoff on legacy path. Net wall-time unchanged.
- **In-memory `_async_tasks` store**: result expires after 30 min
  TTL. If agent run takes >30 min the result is GC'd before client
  polls — but Haiku low is bounded at 130s typical, no real risk.
- **Restart of claude-runner loses pending tasks**: poll returns 404
  after restart. Acceptable: Couche-2 cron retries on next interval.

### Independent issues caught during W67 verification

These are unrelated to the async migration but worth noting:

- **cb_nlp prompt produces Claude content refusals** (~"I cannot
  complete this..."): output validation fails as JSON. Not infra,
  prompt redesign needed — out of scope for ADR-067, deferred.
- **`packages-staging/agents/observability.py` was missing on Hetzner**:
  pre-existing deploy artifact missing. Copied from local to fix
  imports during W67 deploy. Should be encoded into Ansible role.

## Implementation

### Files modified

- `apps/claude-runner/src/ichor_claude_runner/main.py`
  - lines 597-768: 3 new symbols (`_run_agent_background`,
    `agent_task_async`, `agent_task_async_status`)
  - line 91-93: `AsyncTaskStatus.result` Union type
- `packages/agents/src/ichor_agents/claude_runner.py`
  - lines 258+: `call_agent_task_async(...)` new function
- `packages/agents/src/ichor_agents/fallback.py`
  - new flag `use_async_endpoint: bool = True`
  - branching in `run()` between sync and async paths

### Deploy steps executed (autonomous from W66 audit findings)

1. SCP main.py to Win11 → restart claude-runner standalone uvicorn (port 8766)
2. SCP claude_runner.py + fallback.py + observability.py to
   `/opt/ichor/packages-staging/agents/src/ichor_agents/` on Hetzner
3. Bust `__pycache__` recursively
4. Trigger 5 Couche-2 systemd units sequentially → verify async path
   in journals (`agents.claude_runner.async.try / .completed`)

### Verification (live 2026-05-09)

| Agent       | Status                      | Wall-time | Notes                                           |
| ----------- | --------------------------- | --------- | ----------------------------------------------- |
| cb_nlp      | ⚠ infra OK, content refusal | 111s      | Async path works; Claude content issue separate |
| news_nlp    | ✅ OK via=async             | 62s       | Post W64 Pydantic ge=0 fix                      |
| sentiment   | ✅ OK via=async             | 17s       |                                                 |
| positioning | ✅ OK via=async             | 24s       |                                                 |
| macro       | ✅ OK via=async             | 64s       |                                                 |

= 4/5 producing valid structured output; 5/5 use async path
(structural fix complete).

## Linked

- **ADR-053** — briefing-task/async (BLOCKER #1 wave 20)
- **ADR-054** — stdin pipe Win argv 32K (BLOCKER #2 wave 23)
- **ADR-021** — Claude primary brain
- **ADR-023** — Couche-2 → Haiku low

ADR-067 closes the Couche-2 leg of the structural CF Tunnel timeout
work that ADR-053 started for briefings + session-cards. Pipeline now
**3/3 paths immune to CF 100s edge cap**: briefing-task/async (W20),
session-cards (uses briefing path), agent-task/async (W67).
