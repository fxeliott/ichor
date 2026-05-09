# Ichor — Claude Code project memory

> Auto-injected at every session start. Keep terse and current.
> Last sync: 2026-05-09 15:30 CEST (post-Phase II 11-commit batch W70-W79).

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
│   │                         34 routers, 53 endpoints, 26 CLI runners,
│   │                         28 models, 41 collectors, 49 services
│   │                         data_pool = 43 sections (W79 cross-asset matrix v2)
│   ├── claude-runner/        FastAPI Win11 wrapper around `claude -p`
│   │                         /v1/briefing-task + /v1/agent-task
│   ├── web/                  legacy Phase 1 dashboard (read-only ref ; retired
│   │                         from pnpm-workspace 2026-05-06 ; 5 routes ported
│   │                         to web2 in commit `de80335`)
│   └── web2/                 Next.js 15.5 + React 19 + Tailwind v4 + motion 12
│                             41 routes SSR + ISR. Hooks dir empty (TODO).
└── packages/
    ├── ichor_brain/          4-pass orchestrator (regime → asset → stress → invalidation)
    │                         + Pass 5 counterfactual. HttpRunnerClient with retry.
    ├── agents/               5 Couche-2 agents (cb_nlp, news_nlp, sentiment,
    │                         positioning, macro). All on Claude Haiku low (ADR-023).
    ├── ml/                   HAR-RV, HMM, DTW, FinBERT-tone, FOMC-Roberta,
    │                         ADWIN, Brier optimizer, 7 bias trainers (ADR-022)
    └── ui/                   shadcn-style 15 components, used by apps/web only
```

> `packages/shared-types` was removed in Phase A.1.3 cleanup (was a stub
> never imported, cf ADR-031). CI matrices in `.github/workflows/{ci,audit}.yml`
> updated accordingly.

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
  43+ ichor-\*.timer units active. systemd `After=` chains the Living
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

## Latest migrations (head 0037)

- **head 0037** — `0037_myfxbook_outlooks.py` (W77, ADR-074) — retail
  FX positioning hypertable. LIVE 2026-05-09: 6 pair snapshots every
  4 h.
- **0036** — `0036_nfib_sbet_observations.py` (W74, ADR-073) — NFIB
  SBET monthly. LIVE: March 2026 SBOI=95.8 / Uncertainty=92.
- **0035** — `0035_cleveland_fed_nowcasts.py` (W72, ADR-070) — daily
  4×3 inflation nowcast (CPI/Core CPI/PCE/Core PCE × MoM/QoQ/YoY).
- **0034** — `0034_nyfed_mct_observations.py` (W71, ADR-069) — NY Fed
  Multivariate Core Trend monthly (replaces UIGFULL). 795 rows
  backfilled 1960-01 → 2026-03.
- **0028 → 0033** — Phase II Layer 1 collectors: audit_log immutable
  trigger (0028, ADR-029), trader_notes (0029), CBOE SKEW (0030),
  CFTC TFF (0031), CBOE VVIX (0032), Treasury TIC (0033).

## Recent ADRs (2026-05-09 batch — 9 ADRs)

- [ADR-076](docs/decisions/ADR-076-frontend-mock-fallback-pattern.md)
  Frontend `MOCK_*` are graceful fallbacks behind `isLive()`, not
  hardcoded mocks — keep the pattern. CLAUDE.md tech-debt line
  corrected.
- [ADR-075](docs/decisions/ADR-075-cross-asset-matrix-v2.md) Cross-asset
  matrix v2 — 6-dim macro state (MCT + nowcast surprise + NFCI + SKEW
  + VIX + SBOI) with qualitative bands + per-asset directional bias
  tags for the 8 Ichor pairs.
- [ADR-074](docs/decisions/ADR-074-myfxbook-replaces-oanda-orderbook.md)
  MyFXBook Community Outlook replaces OANDA orderbook (Sept 2024 EOL,
  $1850/mo Data Service violates Voie D). LIVE 2026-05-09.
- [ADR-073](docs/decisions/ADR-073-nfib-sbet-pdf-collector.md) NFIB SBET
  PDF collector — hub-scrape + pdfplumber + regime classifier.
- [ADR-072](docs/decisions/ADR-072-ansible-ichor-packages-role.md)
  Ansible `ichor_packages` role — declarative packages-staging sync +
  W67 regression guard.
- [ADR-071](docs/decisions/ADR-071-capability-5-deferral-client-tools-only.md)
  Capability 5 — wire ONLY client tools (query_db/calc/rag_historical),
  never server tools (web_search/web_fetch — billed separately,
  violate Voie D). PRE-1 CF Access + PRE-2 tool_call_audit migration.
- [ADR-070](docs/decisions/ADR-070-cleveland-fed-nowcast-collector.md)
  Cleveland Fed Inflation Nowcast (4×3 daily surface).
- [ADR-069](docs/decisions/ADR-069-nyfed-mct-collector-replaces-uig.md)
  NY Fed MCT collector replaces discontinued FRED UIGFULL.
- [ADR-068](docs/decisions/ADR-068-cb-nlp-prompt-redesign-content-refusal.md)
  cb_nlp prompt redesign — research framing, drop "buy/sell" ban,
  descriptive `rate_path_skew`. Fixed Claude content refusal.
- [ADR-067](docs/decisions/ADR-067-couche2-async-polling-migration.md)
  Couche-2 async polling — CF 100 s structural fix on agent-task path.
  Pipeline 3/3 CF-immune.

## Conventions and protocols

- All commits / PRs / docstrings in **English**. Conversation in
  **French**.
- **Conventional Commits**, short subject. Body explains _why_ not
  _what_.
- Tests required for non-trivial code changes. Pytest for Python,
  Vitest + Playwright for web2.
- ADR for any architectural decision (one decision = one file in
  `docs/decisions/`, immutable once Accepted ; supersede via new ADR).
- RUNBOOK for any recovery procedure (`docs/runbooks/`).
- SESSION_LOG for per-day work summary (`docs/SESSION_LOG_YYYY-MM-DD.md`).

## Working in this repo (Claude Code 2026 stack)

### 4-layer Claude Code architecture for Ichor

| Layer                             | Where                                                                    | Status                                                                                                                                                    |
| --------------------------------- | ------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **CLAUDE.md** (advisory)          | This file + per-package `CLAUDE.md` if needed                            | Active                                                                                                                                                    |
| **Skills** (reusable recipes)     | `.claude/skills/` (project) and `~/.claude/skills/` (global)             | 4 project skills : `frontend-design` (legacy), `ichor-dashboard-component`, `ichor-alembic-migration`, `ichor-ssh-deploy`                                 |
| **Hooks** (deterministic gates)   | `.claude/settings.json` (project) and `~/.claude/settings.json` (global) | PreToolUse blocks `.git`/`infra/secrets`/`.env`, warns on `register-cron-*.sh` edits ; PostToolUse auto-formats `.py` (ruff) and `.tsx`/`.ts` (prettier). |
| **Subagents** (parallel/isolated) | `.claude/agents/` (project) and `~/.claude/agents/` (global)             | Project : `ichor-navigator`, `ichor-trader`, `ichor-data-pool-validator`. Global : 16 generalists (researcher, verifier, code-reviewer, etc.).            |

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

| Alert                | Status                             | Notes                                                                                                                                                                                                  |
| -------------------- | ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| RISK_REVERSAL_25D    | **WIRED**                          | `services/risk_reversal_check.py` + `cli/run_rr25_check.py` deployed. 3 tickers persisted (SPY/QQQ/GLD → SPX500/NAS100/XAU). Cron registration pending.                                                |
| LIQUIDITY_TIGHTENING | **WIRED**                          | `services/liquidity_proxy.py` + `cli/run_liquidity_check.py` deployed. Will activate after dts_treasury collector accumulates first DTS_TGA_CLOSE (next 04:00 Paris cron).                             |
| FOMC_TONE_SHIFT      | **CODE READY, ACTIVATION PENDING** | `services/cb_tone_check.py` + `cli/run_cb_tone_check.py` shipped. To activate: `pip install transformers torch --index-url https://download.pytorch.org/whl/cpu` in `/opt/ichor/api/.venv` on Hetzner. |
| ECB_TONE_SHIFT       | **CODE READY, ACTIVATION PENDING** | Same path as FOMC_TONE_SHIFT (transfer-learning FOMC-Roberta on ECB speeches). Same activation step.                                                                                                   |
| FED_FUNDS_REPRICE    | DORMANT                            | moyen (no FRED feed for ZQ futures, approx via DFF+OIS)                                                                                                                                                |
| ECB_DEPO_REPRICE     | DORMANT                            | difficile (no free Eurex €STR feed)                                                                                                                                                                    |

## Things that are subtly broken or deferred (post 2026-05-09 batch)

- `apps/web` legacy retired 2026-05-06. 25 page.tsx on-disk as
  read-only ref.
- `apps/web2` per-segment loading.tsx/error.tsx/not-found.tsx still
  pending (Phase B target).
- **CF Access service token NOT wired** sur
  `claude-runner.fxmilyapp.com` — **PRE-1 blocker for Capability 5
  Phase D.0** wiring (cf ADR-071).
- **`tool_call_audit` migration NOT yet shipped** — PRE-2 blocker for
  Capability 5 Phase D.0. ADR-029 MiFID compliance requires the
  immutable trigger pattern (mirror of `audit_log` 0028).
- Capability 5 = scaffolded only (registry + 22 tests, ADR-050) but
  wiring deferred per ADR-071 with the 6-step sequence (PRE-1, PRE-2,
  STEP-1..STEP-5, STEP-6 integration test). Server tools
  (`web_search`/`web_fetch`) **excluded** from scope — they're
  metered by Anthropic since 2026-04 and violate Voie D.
- WGC quarterly XLSX collector deferred — license requires explicit
  WGC consent for systematic extraction; private-research framing OK
  but not yet validated. (W75 candidate, `gold-demand-by-country` hub
  scrape strategy researched + documented.)
- Frontend `MOCK_*` audit (W78) revealed they are graceful fallbacks
  behind `isLive()`, not tech-debt. ADR-076 codifies; future revisit
  via reusable `<EmptyStateWithRetry>` component (W80 candidate).
- `replay/[asset]/page.tsx` derives `thesis_excerpt` via
  `deriveExcerpt` proxy because `SessionCardOut` lacks a `thesis`
  field (W81 candidate, 1h estimate).
- Polymarket `WHALES` constant in `polymarket/page.tsx` — no backend
  trade-tape collector yet (W82 candidate, separate ADR needed).

## Recently fixed (2026-05-09 — 11 commits Phase II batch)

- **W70** ✅ — cb_nlp Claude content refusal fix (research-framing
  rewrite of system prompt). ADR-068 / commit 2343158.
- **W71** ✅ — NY Fed MCT collector replaces discontinued FRED UIGFULL.
  795 monthly observations 1960-01 → 2026-03. ADR-069 / commit
  8091b42.
- **W72** ✅ — Cleveland Fed Inflation Nowcast (3 webcharts JSON
  endpoints, 4 measures × 3 horizons). ADR-070 / commit 10e1ff5.
- **W73** ✅ — Capability 5 deferral codified with 6-step sequence
  (PRE-1 CF Access + PRE-2 tool_call_audit migration + STEP-1..6).
  ADR-071 / commit e2cbb98.
- **W74** ✅ — NFIB SBET PDF collector (hub-scrape + pdfplumber +
  regime classifier). March 2026 SBOI=95.8 / Uncertainty=92.
  ADR-073 / commit a31818a.
- **W76** ✅ — Ansible `ichor_packages` role declarative sync of
  packages-staging + W67 regression guard. ADR-072 / commit b99e172.
- **W77** ✅ — MyFXBook Community Outlook collector dormant deploy +
  helper script + RUNBOOK-017. Replaces OANDA orderbook (Sept 2024
  EOL). ADR-074 / commits 4d2a30a + 33dd25e.
- **W77b** ✅ — MyFXBook session_id raw URL concat fix (httpx
  `params=` was double-encoding the URL-encoded session token).
  Now LIVE with 6 pair snapshots / 4 h. AUDUSD 88 % short retail
  (extreme contrarian flag). Commit c841c58.
- **W78** ✅ — Frontend MOCK_* audit reframe (graceful fallbacks
  pattern, not tech-debt). ADR-076 / commit 9adb168.
- **W79** ✅ — Cross-asset matrix v2 — 6-dim macro state surface +
  per-asset directional bias tags. Pure-leverage section
  (`_section_cross_asset_matrix` in data_pool). ADR-075 / commit
  00309a8.

## Earlier waves (2026-05-06 / Phase 0 + A.1 + A.2 + A.3 + A.4.a/b + A.5 + A.7.partial)

- Phase 0 ✅ — 3 alertes activées Hetzner : RR25 (Mon..Fri 14:05+21:30),
  LIQUIDITY (Mon..Fri 04:30 after dts_treasury), FOMC_TONE_SHIFT
  (Mon..Fri 21:00). transformers 5.8.0 + torch 2.11.0+cpu installés.
  ECB_TONE_SHIFT differé Phase D (calibration ECB requise).
- A.1.1 ✅ — `audit.log` global hook migré : convention 2026 stdin JSON
  via scripts dédiés `~/.claude/hooks/post_tool_audit.ps1` etc.
- A.1.2 ✅ — `RuntimeError: Event loop is closed` corrigé dans 3 CLI
  runners (rr25/liquidity/cb_tone) + déployé Hetzner + 3 runs propres
  vérifiés post-fix.
- A.1.3 ✅ — `_VALID_SESSIONS` single-source via `get_args(SessionType)`
  exposé en `VALID_SESSION_TYPES` dans `ichor_brain.types` (ADR-031) ;
  index `docs/runbooks/README.md` 3 liens cassés corrigés ; Couche-2
  docstrings ADR-021 → ADR-023 ; `packages/shared-types` supprimé du
  repo + matrice CI.
- A.2 ✅ — crisis_mode_runner re-cadré (déjà câblé sous nom différent
  `cli/run_crisis_check.py` + `alerts/crisis_mode.py` + timer actif),
  Event loop fix appliqué + commentaire `alerts_runner.py` corrigé.
- A.3 ✅ — Wave 5 CI durci : coverage gate apps/api 60% + nouveau job
  `shell-lint` shellcheck + structural lint sur `register-cron-*.sh`
  (clauses canoniques ADR-030 vérifiées).
- A.4.a ✅ — `/metrics` FastAPI endpoint LIVE (Prometheus
  `prometheus-fastapi-instrumentator 7.1.0`) ; toute la stack
  Prometheus était silencieusement aveugle, maintenant fonctionnelle.
- A.4.b ✅ — `OnFailure=ichor-notify@%n.service` drop-ins systemd
  installés sur 28 services ichor-\* ; template `[email protected]` +
  worker `/opt/ichor/scripts/notify-failure.sh` + log
  `/var/log/ichor-failures.log` + (optionnel) ntfy webhook.
  Chaîne testée end-to-end (`ichor-test-fail.service` → log écrit).
- A.5 ✅ — 3 ADRs ratifiés : 029 (EU AI Act §50 + AMF DOC-2008-23),
  030 (ResolveCron protection post-2026-05-04), 031 (SessionType
  single source via get_args).
- A.7.partial ✅ — RUNBOOK-014 (claude-runner Win11 down) + RUNBOOK-015
  (secrets rotation 90d/60d/12mo) + `audit_log` immuable Postgres
  trigger (migration 0028) testé end-to-end.
