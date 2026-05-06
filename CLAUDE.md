# Ichor — Claude Code project memory

> Auto-injected at every session start. Keep terse and current.
> Last sync: 2026-05-06.

## What this repo is

**Ichor — Living Macro Entity (Phase 2)**, a pre-trade FX/macro
research system. Outputs probability-calibrated bias cards per
asset, never trade signals (cf. [ADR-017](docs/decisions/ADR-017-reset-phase1-living-macro-entity.md)
boundary, contractual).

Stack : Turborepo + pnpm 10 monorepo. Python 3.12 strict for the
backend, Node 22 LTS for the frontend.

## Topology

```
D:\Ichor
├── apps/
│   ├── api/                  FastAPI + Alembic + SQLAlchemy 2 async
│   │                         34 routers, 53 endpoints, 24 CLI runners,
│   │                         24 models, 37 collectors, 44 services
│   ├── claude-runner/        FastAPI Win11 wrapper around `claude -p`
│   │                         /v1/briefing-task + /v1/agent-task
│   ├── web/                  legacy Phase 1 dashboard (deprecated, coexist)
│   └── web2/                 Next.js 15.5 + React 19 + Tailwind v4 + motion 12
│                             35 routes SSR + ISR. Hooks dir empty (TODO).
└── packages/
    ├── ichor_brain/          4-pass orchestrator (regime → asset → stress → invalidation)
    │                         + Pass 5 counterfactual. HttpRunnerClient with retry.
    ├── agents/               5 Couche-2 agents (cb_nlp, news_nlp, sentiment,
    │                         positioning, macro). All on Claude Haiku low (ADR-023).
    ├── ml/                   HAR-RV, HMM, DTW, FinBERT-tone, FOMC-Roberta,
    │                         ADWIN, Brier optimizer, 7 bias trainers (ADR-022)
    ├── ui/                   shadcn-style 15 components, used by apps/web only
    └── shared-types/         STUB — empty package, never imported
```

## Critical invariants (DO NOT BREAK)

- **No BUY/SELL signals anywhere.** ADR-017 contractual. The pipeline
  emits probabilities (`P(target_up=1) ∈ [0,1]`) and bias direction
  (`long|short|neutral`), never an order. Grep `BUY|SELL` returns
  only docstrings of boundary, persona Claude, or `/learn` pages.
- **Voie D : no Anthropic SDK consumption.** Production routes via
  the local Win11 `claude-runner` subprocess (Max 20x flat). Never
  add `anthropic` python SDK — use `pydantic-ai-slim[openai]` only.
- **Couche-2 lives on Claude Haiku low.** Sonnet medium hits the
  Cloudflare Free 100 s edge timeout (ADR-023). To revisit if we
  upgrade CF plan.
- **Session-cards 4-pass per asset, persisted to `session_card_audit`.**
  4 windows/day × 8 assets = 32 cards/day target. Cap 95 % conviction.

## Production deployment

- **Hetzner** SSH alias `ichor-hetzner` (~/.ssh/config). All API,
  Postgres-with-Timescale-AGE, Redis 8, n8n, Langfuse, observability.
  43+ ichor-*.timer units active. systemd `After=` chains the Living
  Entity loop : reconciler → brier_optimizer → brier_drift →
  concept_drift → prediction_outlier → dtw_analogue (nightly), then
  post_mortem → counterfactual_batch (weekly Sun).
- **Win11 local** runs the `IchorClaudeRunner` (NSSM service). At
  the time of writing, the NSSM service is in `Paused` state because
  `ICHOR_RUNNER_ENVIRONMENT=development` was lost from its env list ;
  a standalone uvicorn on port 8766 is the active runner, kept alive
  via `scripts/windows/start-claude-runner-standalone.bat` in the
  user Startup folder.
- **Cloudflare Tunnel** `claude-runner.fxmilyapp.com` → 127.0.0.1:8766
  (managed-config side, NOT in the local `~/.cloudflared/config.yml`).
  **Currently no auth** — `require_cf_access=false`. Public endpoint
  drainable. Sprint dedicated to wire CF Access service token pending.

## Latest migrations

- **head 0027** — `0027_session_type_extend_ny.py` extends the
  `session_card_audit` CHECK constraint to include `ny_mid` and
  `ny_close` (cf. ADR-024).
- **0026** — `session_card_audit.drivers` JSONB for Brier V2
  per-factor SGD (cf. ADR-022). Column shipped, optimizer V2 still
  TODO.

## Recent ADRs (2026-05-06)

- [ADR-024](docs/decisions/ADR-024-session-cards-five-bug-fix.md)
  fixed 5 stacked bugs that had killed `session_card_audit` writes
  for 2 days. ny_mid + ny_close now valid sessions.
- [ADR-023](docs/decisions/ADR-023-couche2-haiku-not-sonnet-on-free-cf-tunnel.md)
  Couche-2 mapping changed Sonnet medium → Haiku low (CF Free
  tunnel 100 s edge cap).

## Conventions and protocols

- All commits / PRs / docstrings in **English**. Conversation in
  **French**.
- **Conventional Commits**, short subject. Body explains *why* not
  *what*.
- Tests required for non-trivial code changes. Pytest for Python,
  Vitest + Playwright for web2.
- ADR for any architectural decision (one decision = one file in
  `docs/decisions/`, immutable once Accepted ; supersede via new ADR).
- RUNBOOK for any recovery procedure (`docs/runbooks/`).
- SESSION_LOG for per-day work summary (`docs/SESSION_LOG_YYYY-MM-DD.md`).

## Working in this repo (Claude Code 2026 stack)

### 4-layer Claude Code architecture for Ichor

| Layer | Where | Status |
|---|---|---|
| **CLAUDE.md** (advisory) | This file + per-package `CLAUDE.md` if needed | Active |
| **Skills** (reusable recipes) | `.claude/skills/` (project) and `~/.claude/skills/` (global) | 4 project skills : `frontend-design` (legacy), `ichor-dashboard-component`, `ichor-alembic-migration`, `ichor-ssh-deploy` |
| **Hooks** (deterministic gates) | `.claude/settings.json` (project) and `~/.claude/settings.json` (global) | PreToolUse blocks `.git`/`infra/secrets`/`.env`, warns on `register-cron-*.sh` edits ; PostToolUse auto-formats `.py` (ruff) and `.tsx`/`.ts` (prettier). |
| **Subagents** (parallel/isolated) | `.claude/agents/` (project) and `~/.claude/agents/` (global) | Project : `ichor-navigator`, `ichor-trader`, `ichor-data-pool-validator`. Global : 16 generalists (researcher, verifier, code-reviewer, etc.). |

### Subagents : when to invoke

- `ichor-navigator` (project) — first hop on "where is X" / "how do I add a Y" questions. Read-only.
- `ichor-trader` (project) — proactively before merging anything that touches the alert catalog, the 4-pass pipeline, the data-pool sources, or any new `cli/run_*_check.py`. Defends the 9 trading invariants (ADR-017 boundary, macro trinity, dollar smile, VPIN BVC, dealer GEX sign, FX peg conventions, Tetlock invalidation, conviction cap, source-stamping).
- `ichor-data-pool-validator` (project) — right after a new collector lands, after wiring an alert metric, before deploying a register-cron script.
- `researcher` (global) — >3-file exploration without polluting main context. **No Bash** — use `general-purpose` for SSH/Hetzner audits.
- `verifier` (global) — after non-trivial work to reality-check claims against actual code/tests.
- `monorepo-coordinator` (global) — knows pnpm/Turbo workspaces. Use for cross-package change ordering.
- `code-reviewer` (global) — read-only review of a diff or a stretch of code post-implementation.
- `debugger` (global) — for non-trivial bugs. Reproduces first, writes a failing test, then fixes.

### Hooks already installed (deterministic, can't be skipped)

- **SessionStart** : prints alembic head + git branch (so a fresh session knows the schema state).
- **PreToolUse Edit/Write** :
  - blocks `.git/`, `infra/secrets/`, `.env` paths (exit 2).
  - warns on `scripts/hetzner/register-cron-*.sh` edits (the bug class that took down 5 services on 2026-05-04).
- **PostToolUse Edit/Write** :
  - auto-`ruff format` for `.py` files (using `apps/api/.venv/Scripts/ruff.exe`).
  - auto-`prettier --write` for `.tsx`/`.ts` files (using `apps/web2/node_modules/.bin/prettier`).
- (Inherited from global ~/.claude/) `long_prompt_detector.ps1` injects `/restate` recommendation on >200-word user prompts ; PreCompact backs up the transcript ; audit log on Edit/Write/Stop/PermissionDenied.

### MCP servers (active on this machine)

- `context7` — version-specific docs for any library cited in CLAUDE.md/global. Prevents stale-API hallucination on Pydantic AI / FastAPI / Tailwind v4 / motion / lightweight-charts.
- `serena` — semantic code search. Persists context across `/clear` operations.
- `sequential-thinking` — structured reasoning for complex decisions. Token-intensive — use sparingly.
- `Claude_Preview` — start the web2 dev server, screenshot, eval, inspect, snapshot. The verification loop for any frontend change.
- `computer-use` — desktop automation when no MCP exists for the target app. Tier-aware (browsers = read, terminals = click, others = full).

**Keep the MCP set light.** Adding a 6th MCP can eat 40 % of the context window at boot. Only add if a workflow truly needs it.

### Slash commands / skills

- `/restate` — when the user prompt > 200 words or contains ambiguity markers (FR : "tu vois", "ce genre", "ou bien", "etc"). Produces a 4-block brief.
- `/spec` — for new feature interviews. Asks `AskUserQuestion`, writes `SPEC.md`, recommends `/clear`.
- `/check` — repo state snapshot.
- `/verify-no-hallucinate` — post-task reality check on any claim made.
- `/orchestrate` — multi-agent coordination for big tasks.
- `/ultrathink-this` (or `ultrathink` keyword anywhere in a prompt) — deeper reasoning on the current turn without changing session effort.

### Opus 4.7 specifics (the model running by default)

- **Adaptive thinking** is the only thinking mode (extended thinking with fixed budget was removed). The model decides per-step.
- **xhigh effort** is default in Claude Code v2.1.117+. `/effort max` raises further but only for the current session.
- **1M context** auto-enabled on Max plan. `CLAUDE_CODE_DISABLE_1M_CONTEXT=1` to opt out.
- **Tokenizer is +35 % vs Opus 4.6** — files consume more context. Compact at ~60 % usage rather than waiting for autocompact.
- **task_budget** advisory cap distinct from `max_tokens` — use it for self-moderation on long agentic tasks.
- **Lost-in-the-middle** still bites at 1M tokens. Front-load and end-load critical context.

### Optimization knobs already set globally

- `CLAUDE_CODE_USE_POWERSHELL_TOOL=1` — PowerShell available alongside Bash.
- `DISABLE_TELEMETRY=1`.
- `ENABLE_PROMPT_CACHING_1H=1` — bigger cache window.
- `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` — allows agent-team peer-to-peer coordination (separate from subagents).
- `BASH_DEFAULT_TIMEOUT_MS=180000`, `BASH_MAX_TIMEOUT_MS=600000`.

## Known dormant alerts (status 2026-05-06 evening)

| Alert | Status | Notes |
|---|---|---|
| RISK_REVERSAL_25D | **WIRED** | `services/risk_reversal_check.py` + `cli/run_rr25_check.py` deployed. 3 tickers persisted (SPY/QQQ/GLD → SPX500/NAS100/XAU). Cron registration pending. |
| LIQUIDITY_TIGHTENING | **WIRED** | `services/liquidity_proxy.py` + `cli/run_liquidity_check.py` deployed. Will activate after dts_treasury collector accumulates first DTS_TGA_CLOSE (next 04:00 Paris cron). |
| FOMC_TONE_SHIFT | **CODE READY, ACTIVATION PENDING** | `services/cb_tone_check.py` + `cli/run_cb_tone_check.py` shipped. To activate: `pip install transformers torch --index-url https://download.pytorch.org/whl/cpu` in `/opt/ichor/api/.venv` on Hetzner. |
| ECB_TONE_SHIFT | **CODE READY, ACTIVATION PENDING** | Same path as FOMC_TONE_SHIFT (transfer-learning FOMC-Roberta on ECB speeches). Same activation step. |
| FED_FUNDS_REPRICE | DORMANT | moyen (no FRED feed for ZQ futures, approx via DFF+OIS) |
| ECB_DEPO_REPRICE | DORMANT | difficile (no free Eurex €STR feed) |

## Things that are subtly broken or deferred

- `apps/web` legacy active with 5 routes never ported to web2
  (`/assets/[code]`, `/briefings/[id]`, `/confluence`, `/sessions`
  index, `/hourly-volatility/[asset]`).
- `apps/web2` 0 `loading.tsx`/`error.tsx`/`not-found.tsx` on 35 routes,
  CF Access not wired client-side.
- `lightweight-charts 5.2.0` listed as web2 dep, **0 imports**.
- Couche-2 docstrings still cite ADR-021 Sonnet (mapping
  superseded by ADR-023).
- `packages/agents/README.md` says "Cerebras primary, Sonnet
  fallback" — outdated (cf. ADR-021/023).
- `packages/shared-types` is a stub (no `src/`).
- Wave 5 CI (mypy + pytest blocking + coverage gate) deferred since
  2026-05-05.
- All package READMEs say "Phase 0 skeleton only" while LIVE in prod.
- `audit.log` (~/.claude) figé depuis 2026-05-01 — hook PostToolUse
  à diagnostiquer.
