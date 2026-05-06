# Session log — 2026-05-06 Couche-2 → Claude end-to-end activation

## Context

Continuation of the 2026-05-05 marathon. Audit revealed
`n_couche2_outputs_7d = 0` in `/v1/admin/pipeline-health` despite 5
ichor-couche2-* timers being active on Hetzner. Mission for this
session : root-cause + close the loop end-to-end so Couche-2 actually
emits structured Pydantic outputs into `couche2_outputs`.

Eliot delegated full autonomy and explicitly chose ADR-021 strict
(Claude primary) over the pragmatic shortcut (just add Cerebras/Groq
API keys).

## Root causes uncovered (2 distinct bugs in series)

### Bug 1 — Ghost-env systemd unit
`scripts/hetzner/register-cron-couche2.sh` was the only one of 38
ichor-* unit files that referenced `/dev/shm/ichor-secrets.env` and
`/usr/local/bin/ichor-decrypt-secrets` — a tmpfs-encrypted secrets
design that was never deployed. All 5 Couche-2 services failed at
ExecStartPre with "No such file or directory" before Python even ran.

**Fix** : aligned the unit on the same `/etc/ichor/api.env` pattern
the other 38 services use ; redeployed via SSH. Services now reach
Python.

### Bug 2 — ADR-021 was a paper ADR
[ADR-021](decisions/ADR-021-couche2-via-claude-not-fallback.md) stated
Claude is primary for Couche-2, but the implementation in
`packages/agents/src/ichor_agents/agents/*.py` only ever constructed
`FallbackChain(providers=(CEREBRAS, GROQ))`. Claude was never even in
the dispatch list. With the tmpfs guard fixed, the runs now produced
**`AllProvidersFailed: cerebras=MissingCredentials, groq=MissingCredentials`**
because no API keys were ever provisioned for the fallbacks either.

**Fix** : implemented the missing pieces below.

## What shipped this session

### `apps/claude-runner` — new endpoint
- `POST /v1/agent-task` — generic Claude single-shot for Couche-2.
  Body : `{system, prompt, model, effort}`. Reuses the same rate
  limiter and subprocess semaphore as `/v1/briefing-task` so all
  traffic shares one Max 20x quota envelope.
  ([main.py:255-355](../apps/claude-runner/src/ichor_claude_runner/main.py:255),
   [models.py:62-110](../apps/claude-runner/src/ichor_claude_runner/models.py:62))

### `packages/agents` — Claude adapter + chain rewiring
- New module `claude_runner.py` :
  `ClaudeRunnerConfig` + `call_agent_task` adapter, with
  - JSON-fence stripping
  - JSON-Schema injection into the prompt (fixes the original
    `theme=alien_invasion` validation failure where Claude invented
    enum values)
  - 3-step exponential backoff retry on 503 / 429 (5 / 15 / 45 s)
    so single-slot semaphore collisions don't bubble up as
    AllProvidersFailed during burst traffic.
- `fallback.py` extended with a `claude` slot tried before the
  `providers` list, and a `last_success` field for accurate
  provider:model provenance reporting.
- All 5 chain factories (`make_macro_chain`, `make_cb_nlp_chain`,
  `make_news_nlp_chain`, `make_sentiment_chain`,
  `make_positioning_chain`) wire `ClaudeRunnerConfig.from_env()` as
  primary.

### `apps/api/src/ichor_api/cli/run_couche2_agent.py`
- `model_used` now reads `chain.last_success` instead of hard-coding
  `providers[0]`. Pre-2026-05-06 this lied whenever Claude (now
  primary) was used.

### Tests
- `packages/agents/tests/test_claude_runner.py` — 15 new tests
  (config, schema-hint, retry-on-503, fallback wiring).
- `apps/claude-runner/tests/test_agent_task_endpoint.py` — 4 new tests
  (success / subprocess error / timeout / pydantic validation).
- All suites pass : 82 agents + 17 runner = 99 fast, deterministic
  tests.

### `docs/decisions/ADR-023`
[ADR-023](decisions/ADR-023-couche2-haiku-not-sonnet-on-free-cf-tunnel.md)
documents the Sonnet → Haiku downgrade for Couche-2. Empirical
finding : Free-tier Cloudflare Tunnel imposes 100 s edge timeout ;
Sonnet medium often runs 60-120 s on a 5 KB prompt and hits HTTP 524.
Haiku low runs 18-45 s, well under the cap. ADR-023 supersedes the
default-mapping table of ADR-021.

## End-to-end validation on prod (Hetzner ↔ tunnel ↔ runner ↔ Claude)

Manual triggers of all 5 Couche-2 services :

| Agent       | model_used    | payload chars | Status |
| ----------- | ------------- | ------------- | ------ |
| macro       | claude:haiku  | 1444          | OK     |
| cb_nlp      | claude:haiku  | 3537          | OK     |
| news_nlp    | claude:haiku  | 1804          | OK     |
| sentiment   | claude:haiku  | 308           | OK     |
| positioning | claude:haiku  | 1148          | OK     |

`couche2_outputs` is now alive. The 24/7 Couche-2 timers (registered
2026-05-05, schedule in `register-cron-couche2.sh`) will pick up the
correct flow on their next firing without further intervention.

## Operational drift in the runner host (Win11) — followed up

- `IchorClaudeRunner` NSSM service is in `Paused` state because
  `ICHOR_RUNNER_ENVIRONMENT=development` was lost from the NSSM
  AppEnvironmentExtra list. The runner's startup guard refuses to
  boot in `production` mode with `require_cf_access=false`. Fixing
  NSSM env requires admin elevation.
- **Workaround installed** : a standalone uvicorn (PID 7104) is
  running on port 8766 with the right env vars, and a launcher
  `scripts/windows/start-claude-runner-standalone.bat` is now in
  the user Startup folder so the runner survives reboot. The NSSM
  service can stay Paused for now.
- The Cloudflare Tunnel ingress points to port 8766 (managed
  remotely on the Cloudflare side, not the local `config.yml`).
  Verified by inspecting the cloudflared log : `Updated to new
  configuration ... service: http://localhost:8766`.

## Security note flagged for a future sprint

Per local stderr archeology, the runner has been serving
`/v1/briefing-task` (and now `/v1/agent-task`) without CF Access
JWT verification since 2026-05-02. The tunnel domain
`claude-runner.fxmilyapp.com` is therefore a public endpoint that
can be discovered + drained. To harden : provision a Cloudflare
Access service token, set `ICHOR_RUNNER_REQUIRE_CF_ACCESS=true` +
team-domain + aud-tag, populate `ICHOR_API_CF_ACCESS_CLIENT_ID/
CLIENT_SECRET` in `/etc/ichor/api.env` on Hetzner. Estimated work :
~30-45 min once the dashboard creds are in hand.

## Untouched / explicit non-goals this session

- The 4 alerts that ADR-021's mapping listed as fallback-target
  (RISK_REVERSAL_25D, LIQUIDITY_TIGHTENING, FED_FUNDS_REPRICE,
  ECB_DEPO_REPRICE) remain DORMANT — they're blocked upstream by
  missing data feeds (FX options chains, Fed/ECB futures).
- `packages/shared-types` is still a STUB.
- `pipeline-health.n_couche2_outputs_7d` will start incrementing
  from this session on (root cause was the `0` count).

## Files added / modified

- new : `packages/agents/src/ichor_agents/claude_runner.py`
- new : `packages/agents/tests/test_claude_runner.py`
- new : `apps/claude-runner/tests/test_agent_task_endpoint.py`
- new : `docs/decisions/ADR-023-couche2-haiku-not-sonnet-on-free-cf-tunnel.md`
- new : `scripts/windows/start-claude-runner-standalone.bat`
  (also installed in `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`)
- new : `scripts/windows/restart-claude-runner-elevated.ps1`
  (provided as the admin-elevation path for whenever NSSM gets fixed)
- new : `apps/claude-runner/.env` (development override for local
  dev; **NOT** the deployed config)
- modif : `packages/agents/src/ichor_agents/fallback.py`
- modif : `packages/agents/src/ichor_agents/agents/{macro,cb_nlp,news_nlp,sentiment,positioning}.py`
- modif : `apps/claude-runner/src/ichor_claude_runner/main.py`
- modif : `apps/claude-runner/src/ichor_claude_runner/models.py`
- modif : `apps/claude-runner/tests/test_models.py`
- modif : `apps/api/src/ichor_api/cli/run_couche2_agent.py`
- modif : `scripts/hetzner/register-cron-couche2.sh`
