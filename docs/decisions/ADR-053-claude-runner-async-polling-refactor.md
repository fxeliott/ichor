# ADR-053: claude-runner async + polling pattern (Cloudflare 524 fix)

- **Status**: Accepted
- **Date**: 2026-05-08
- **Deciders**: Eliot
- **Implements**: Phase I.1 — claude-runner Cloudflare Tunnel timeout fix

## Context

Wave 20 audit (2026-05-08) identified that **4 briefing systemd services
on Hetzner have FAILED systematically since 2026-05-06** :

```
ichor-briefing@pre_londres.service     FAILED
ichor-briefing@pre_ny.service          FAILED
ichor-briefing@ny_mid.service          FAILED
ichor-briefing@ny_close.service        FAILED
```

Logs show `cli.claude_runner_call_failed error="Server error '524 <none>'
for url 'https://claude-runner.fxmilyapp.com/v1/briefing-task'"` repeatedly
across 3 days.

### Root cause

**Cloudflare Tunnel free plan enforces a 100-second edge timeout** on
streaming-disabled HTTP responses. The synchronous `/v1/briefing-task`
endpoint runs the `claude -p` subprocess inline, which takes 60-180s
typical and routinely exceeds 100s on large `data_pool` prompts (the
4-pass orchestrator concatenates assets × FRED windows × news → ~150KB
context).

When the subprocess takes >100s, Cloudflare drops the request with HTTP
524 even though the Win11 origin server is still processing. The
subprocess completes successfully but the result is lost.

This silently broke the entire 4-pass session-card generation pipeline.
Catalog growth of 21 alerts (waves 5-19) shipped to a system whose CORE
was offline.

## Decision

Implement **async + polling pattern** :

1. **`POST /v1/briefing-task/async`** → 202 Accepted + `task_id` (fast,
   sub-second). The endpoint validates rate-limit, registers the task in
   `_async_tasks` store, spawns `asyncio.create_task()` for the subprocess,
   returns immediately.

2. **`GET /v1/briefing-task/async/{task_id}`** → status (each call <1s,
   well under 100s edge cap). Returns `pending` → `running` → `done`
   (with `result` field) | `error` (with `error` field).

3. **`HttpRunnerClient._run_async_polling()`** : submits, then polls every
   5s for up to 600s total. Each poll completes in <1s so Cloudflare
   timeout no longer applies to subprocess wall-time.

### Concurrency / rate-limit guards preserved

- `_subprocess_semaphore` (max_concurrent_subprocess=1) acquired BY the
  background task before launching subprocess. Submissions are immediate
  but execution is still serialized.
- `_rate_limiter` (hourly Max 20x quota self-protection) acquired ON
  submission. Rejected with 429 if exceeded.

### Memory store

`_async_tasks: dict[str, dict]` — in-memory only.
- TTL : 30 min (results purged after that)
- MAX : 100 tasks (oldest evicted on overflow)
- Restart loses pending tasks (acceptable : polling client times out at
  600s and Hetzner cron retries hourly).

### Back-compat

The legacy `POST /v1/briefing-task` endpoint is preserved unchanged. New
field `use_async_endpoint=True` (default) on `HttpRunnerClient` selects
the async path; `=False` falls back to legacy sync (still works for short
prompts that fit under 100s).

Existing tests `test_runner_client_retry.py` updated to pass
`use_async_endpoint=False` to cover the legacy path explicitly. New tests
for async polling path can land in `test_runner_client_async.py` (TODO
next session).

### Why not Option B (per-pass chunking) ?

Per-pass chunking would split the 4-pass orchestrator into 4 separate
HTTP calls (one per pass). Pros : each call independently <100s. Cons :
- Requires significant refactoring of orchestrator to be HTTP-aware
- 4× the network overhead
- 4× the auth verification (CF Access roundtrips)
- Loses the single-shot context efficiency of one claude CLI invocation

Async + polling preserves the single-shot subprocess model AND bypasses
the timeout issue. Cleaner.

### Why not Option C (streaming responses) ?

Cloudflare Tunnel free plan supports streaming, but the `claude -p`
subprocess outputs the entire response at end (not streamed). Implementing
streaming would require a fork of `claude` CLI behavior or wrapping
stdout incrementally, both fragile. Async polling is more robust.

## Consequences

### Pros
- Briefings of any duration (60s to 600s) succeed reliably
- Concurrency / rate-limit guards preserved
- Back-compat preserved (legacy endpoint + use_async_endpoint=False)
- 0 ADR-017 boundary impact (no Buy/Sell, no functional change)
- 0 Voie D impact (no SDK consumption, claude CLI subprocess unchanged)
- Failure modes graceful : 404 if task expired, 429 if rate-limited,
  503 if concurrency busy, error status if subprocess crashes

### Cons
- Polling adds ~5s latency on average (acceptable : briefings run hours
  ahead of session, not real-time)
- In-memory store loses tasks on Win11 restart (mitigation : 30min TTL +
  client retries on timeout)
- Two new endpoints to monitor (added to `/v1/usage` for visibility)

### Neutral
- The async pattern adds ~50 LOC to claude-runner. Maintenance overhead
  small.

## Alternatives rejected

- **A — Per-pass chunking** : refactor 4-pass orchestrator. Higher cost.
- **B — Streaming responses** : claude CLI doesn't stream. Fragile.
- **C — Cloudflare Tunnel paid plan** : Voie D violation (paid services).
- **D — Bypass Cloudflare via Tailscale** : alternative tunnel,
  introduces network complexity and Auth break.
- **E — Skip Cloudflare entirely (direct to Win11)** : exposes Win11
  to public internet, security risk, NSSM/CF Access integration breaks.

## Implementation

Shipped in PR #58 (Wave 20 follow-up). Files :
- `apps/claude-runner/src/ichor_claude_runner/main.py` (NEW endpoints +
  `_async_tasks` store + `AsyncTaskAccepted` / `AsyncTaskStatus` models +
  `_run_briefing_background` worker + `_async_task_gc` cleanup)
- `packages/ichor_brain/src/ichor_brain/runner_client.py` (NEW
  `_run_async_polling()` method + `use_async_endpoint` flag)
- `packages/ichor_brain/tests/test_runner_client_retry.py` (existing
  tests updated to pass `use_async_endpoint=False`)
- `docs/decisions/ADR-053-claude-runner-async-polling-refactor.md` (this)

**Deploy required** :
- Win11 : restart claude-runner standalone (kill PID, re-run
  `start-claude-runner-standalone.bat`)
- Hetzner : pull updated `runner_client.py` + redeploy `ichor-api.service`

## Verification post-deploy

After Win11 restart + Hetzner pull, manual `systemctl start
ichor-briefing@pre_londres.service` should succeed and produce a
session_card_audit row. The 4 briefing timers should resume normal
operation at their scheduled cron times.

## Related

- ADR-009 — Voie D (preserved, no paid services)
- ADR-017 — Boundary (preserved, no Buy/Sell)
- ADR-024 — 5-bug session-cards fix (Cloudflare timeout was the 6th
  bug, undetected until wave 20)
- CLAUDE.md projet "Things subtly broken or deferred" updated
- ROADMAP REV19 (strategic pivot — this is Phase I.1 first concrete fix)
