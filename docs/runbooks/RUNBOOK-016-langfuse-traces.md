# RUNBOOK-016: Langfuse traces — verify, debug, query

- **Severity**: P2 — observability is degraded, not the primary
  service. Trading bias output (`session_card_audit`) is the primary
  contract; this runbook is for the support layer that helps debug it.
- **Last reviewed**: 2026-05-07
- **Time to resolve (target)**: 10-30 min depending on path.

## When to use this runbook

- Verify that ADR-032 wiring is actually emitting traces post-deploy.
- Debug "I ran a 4-pass but nothing shows in Langfuse UI".
- Query traces by asset / session window for a Critic post-mortem.
- Confirm the SDK v4 worker thread isn't stalling.

## Trigger

Any of:
- A 4-pass run completed (row in `session_card_audit`) but no trace
  visible in https://langfuse.ichor.internal under
  `name="session_card_4pass"` after >2 minutes.
- The API logs show `api.langfuse_init_failed` or
  `api.langfuse_flush_failed`.
- The lifespan log on shutdown is missing `api.langfuse_flushed` —
  silent flush failure.
- Anyone says "wait, why don't I see Pass 3?"

## Diagnosis

### Path A — Is the lib installed?

```bash
ssh ichor-hetzner '/opt/ichor/api/.venv/bin/python -c \
    "import langfuse; print(langfuse.__version__)"'
# Expected: 4.x.x
```

If `ImportError`: the `pip install langfuse>=4.0.0` step on Hetzner
was skipped during deployment (cf ADR-032 §Deployment). Run it now,
then `sudo systemctl restart ichor-api.service`.

### Path B — Are the keys configured?

```bash
ssh ichor-hetzner 'grep -i langfuse /etc/ichor/api.env | sed "s/=.*/=***/"'
# Expected:
#   ICHOR_API_LANGFUSE_PUBLIC_KEY=***
#   ICHOR_API_LANGFUSE_SECRET_KEY=***
#   ICHOR_API_LANGFUSE_HOST=***
```

If keys are blank or absent: pull them from Langfuse UI →
Project Settings → API Keys. Update `/etc/ichor/api.env` (atomic swap
per RUNBOOK-015), restart the API service.

### Path C — Did init succeed?

```bash
ssh ichor-hetzner 'sudo journalctl -u ichor-api.service \
    --since "5 minutes ago" | grep langfuse'
# Look for:
#   api.langfuse_enabled host=http://127.0.0.1:3000   ← good
#   api.langfuse_disabled_no_keys                     ← keys absent (Path B)
#   api.langfuse_disabled_lib_missing                 ← lib absent (Path A)
#   api.langfuse_init_failed error=...                ← Langfuse server reachability
```

If `api.langfuse_init_failed`: check the Langfuse stack health.

```bash
ssh ichor-hetzner 'cd /opt/ichor/langfuse && docker compose ps'
# Expected: langfuse-web + postgres + clickhouse + redis + minio all UP.
```

If any container is unhealthy: see RUNBOOK-002 (Hetzner docker
recovery) and the langfuse-specific compose under
`infra/ansible/roles/langfuse/`.

### Path D — Trace was emitted but not visible

```bash
ssh ichor-hetzner 'docker logs --since 10m ichor-langfuse-web-1 2>&1 \
    | grep -iE "trace|error|drop"'
```

Look for "ingestion queue" warnings or 429s. If ClickHouse is the
bottleneck:
```bash
ssh ichor-hetzner 'docker exec ichor-langfuse-clickhouse-1 \
    clickhouse-client -q "SELECT count() FROM traces \
    WHERE timestamp > now() - INTERVAL 10 MINUTE"'
```

If count is 0 but app logs show `couche1_runner_call` or
`session_card_4pass`: the worker thread is queueing but ingestion is
failing. Restart langfuse-web container (`docker compose restart
langfuse-web`).

### Path E — Async context lost (orphan generations)

If you see `couche1_runner_call` traces in the UI but they aren't
nested under a `session_card_4pass` parent: the contextvar is being
lost across a thread/process boundary.

This is the well-known SDK pitfall (cf
https://github.com/langfuse/langfuse-python — "ThreadPoolExecutor"
section). Search the call site for any `concurrent.futures.run_in_executor`,
`ThreadPoolExecutor`, or `multiprocessing.Pool` between
`Orchestrator.run` and `HttpRunnerClient.run` — none should exist.
If introduced later, switch to `asyncio.gather()`.

## Recovery

### Quickest fix — fail-soft fallback (already in place)

Nothing to do. The `init_langfuse()` swallow path keeps the API up.
The `@observe` decorators are no-op when the SDK can't load. The
4-pass continues running — only observability is degraded. File a
post-mortem and resume normal traffic.

### Trace lib reinstall (Path A)

```bash
ssh ichor-hetzner '/opt/ichor/api/.venv/bin/pip install \
    --upgrade "langfuse>=4.0.0"'
ssh ichor-hetzner 'sudo systemctl restart ichor-api.service'
ssh ichor-hetzner 'sudo journalctl -u ichor-api.service \
    --since "30 seconds ago" | grep langfuse_enabled'
# Expected: api.langfuse_enabled
```

### Key swap (Path B)

Follow RUNBOOK-015 step 2 (atomic /etc/ichor/api.env swap) with the
3 langfuse vars. Verify by re-running the 4-pass and checking the UI.

### Langfuse stack rebuild (Path C/D — Langfuse server down)

```bash
ssh ichor-hetzner 'cd /opt/ichor/langfuse && \
    docker compose down && docker compose up -d'
sleep 30
curl -sf http://127.0.0.1:3000/api/public/health
# Expected: 200 OK
```

If unrecoverable from compose, restore from backup (RUNBOOK-001).
Trace data younger than the last backup is lost — accepted, as
traces are observability not source-of-truth.

## Useful queries (Langfuse UI)

Once traces are flowing, common analyses:

| Question | Filter |
|---|---|
| Which 4-pass took longest in the last 24h? | `name="session_card_4pass"` sorted by duration desc |
| Did any Pass 3 (stress) take >100s (CF edge cap)? | `name="couche1_runner_call"` + tag `pass=3` (todo: add tag) + duration ≥100s |
| Which Couche-2 agent fell back to Cerebras most? | `name="couche2_chain"` + metadata.last_success contains "cerebras" |
| Show all traces for a specific session card | search trace ID = `session_card_audit.id`, todo: persist trace id in DB column |

## Post-incident

- Log incident in `docs/SESSION_LOG_YYYY-MM-DD.md`.
- If a Path E orphan-trace bug shipped, file an ADR ratification of
  the fix.
- Update this RUNBOOK if a step was missing or wrong.

## Related

- ADR-032 — wiring decision (this runbook's source of truth).
- RUNBOOK-001 — Hetzner restore from backup.
- RUNBOOK-015 — Secrets rotation (Langfuse keys 90d cadence).
- ADR-022 — Critic gate; trace IDs will eventually feed Critic
  post-mortems.
- `docs/SPEC_V2_AUTOEVO.md:307` — original parent/child trace design
  (the wiring this runbook supports).
