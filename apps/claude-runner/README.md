# `apps/claude-runner` — Local Win11 Claude Code subprocess wrapper

Runs on Eliot's Windows 11 desktop, never on Hetzner.

Exposes a FastAPI accessible via Cloudflare Tunnel
(`claude-runner.fxmilyapp.com` → `127.0.0.1:8766`). Cloudflare
Access service-token gating is configured but currently disabled
(`require_cf_access=false`) — re-enabling is a deferred sprint
(see `CLAUDE.md` root §Production deployment).

Two endpoints expose the runner :

- `POST /v1/briefing-task` — Couche-1 briefings + session-cards
  (Opus 4.7 / Sonnet 4.6 high effort)
- `POST /v1/agent-task` — Couche-2 single-shot agents (Haiku 4.5
  low effort per ADR-023). Body : `{system, prompt, model, effort}`.

Both endpoints share one `max_concurrent_subprocess` semaphore + a
30-req/h `HourlyRateLimiter` for Max 20x quota self-protection.
Callers (Hetzner cron) carry retry-on-503/429 logic
(`HttpRunnerClient` in `packages/ichor_brain` and `call_agent_task`
in `packages/agents`).

## Why a local subprocess wrapper?

Anthropic Max 20x ($200/mo flat) is meant for individual developer use of
Claude Code. To run automation jobs that consume Max 20x quota without using a
paid API key, we invoke `claude -p --output-format json` as a subprocess from
Eliot's locally-authenticated Claude Code installation.

Hetzner's cron triggers a webhook to this local FastAPI 4× per day at 06h/12h/
17h/22h Paris (briefing windows). Latency budget: 3-6 min per briefing.

## Risks accepted (documented in `docs/ARCHITECTURE_FINALE.md`)

- Anthropic may detect automation patterns and ban the Max 20x account.
  → Fallback chain: Cerebras free → Groq free → static template.
- Local PC sleep / Windows update / power outage.
  → Power Plan never sleep + gpedit Windows Update window 04-05h Paris.

## Status (2026-05-06)

**LIVE in production**. Currently running as a standalone uvicorn
process (PID owned by user) instead of the NSSM `IchorClaudeRunner`
service (which is in `Paused` because `ICHOR_RUNNER_ENVIRONMENT=development`
was lost from its env list — admin elevation needed to restore).
A user-level launcher
`scripts/windows/start-claude-runner-standalone.bat` is installed in
the Startup folder so the runner survives reboot.

17 tests pass (`tests/`) covering models, rate limiter, and the
end-to-end agent-task endpoint with mocked subprocess.
