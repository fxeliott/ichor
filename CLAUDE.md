# Ichor — Claude Code project memory

> Auto-injected at every session start. Keep terse and current.
> Last sync: 2026-05-11 deep night (post-W105 skeleton — autonomous session continuation : G1+G3+G4 closed (W104a/b/c) then W105 skeleton landed [scenarios.py Pydantic 7-bucket schema + cap_and_normalize proportional clipping + 35 tests + 3 ADR-081 CI guards + Scenario.mechanism BUY/SELL/TP/SL runtime validator]. 6 commits this session ca8ccb4 → 94667eb, 5 pushed to origin/main. Baseline = `94667eb`. Total Pass-6 contract surface now testable in isolation, blocks W105c LLM prompt + W105a migration 0039 + W105g reconciler in next sub-waves. W102 CF Access still pending Eliot 15 min dashboard).

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
│   │                         35 routers / 58 endpoints (+ /v1/tools W85),
│   │                         33 ORM models, 44 collectors, 66 services,
│   │                         42 CLI runners (alerts + brain passes + ML),
│   │                         data_pool = 43 sections (W79 cross-asset matrix v2)
│   ├── claude-runner/        FastAPI Win11 wrapper around `claude -p`
│   │                         /v1/briefing-task + /v1/agent-task
│   ├── ichor-mcp/            **W85** Win11 stdio MCP server (Capability 5
│   │                         STEP-3, ADR-077). Forwards mcp__ichor__query_db /
│   │                         mcp__ichor__calc to apps/api `/v1/tools/*`. NO
│   │                         DB credentials on Win11 by design.
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
  drainable. **W102 / RUNBOOK-018 authored 2026-05-11 ; awaiting
  Eliot 15 min CF dashboard action to unblock**. All code already
  wired (auth.py JWT verifier + HttpRunnerClient header injection +
  lifespan production guard).

## Latest migrations (head 0038)

- **head 0038** — `0038_tool_call_audit.py` (W80, Cap5 PRE-2,
  ADR-077 §"Audit row shape") — immutable trigger mirror of
  audit_log. Verified live 2026-05-09. Empty table by design until
  STEP-5 orchestrator agentic loop wires up.
- **0037** — `0037_myfxbook_outlooks.py` (W77, ADR-074) — retail
  FX positioning hypertable. LIVE 2026-05-09: 6 pair snapshots every
  4 h. AUDUSD 88 % short retail = extreme contrarian flag.
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

## Recent ADRs (2026-05-11 batch — ADR-082 / 083 / 084)

- [ADR-084](docs/decisions/ADR-084-searxng-self-hosted-web-research.md)
  **SearXNG self-host Hetzner ratified** for Couche-2 web research
  (vs Perplexity rejected — bundles metered LLM, violates Voie D
  spirit). Docker loopback :8081 + Redis 24h cache + Serper.dev free
  fallback. MCP tool `mcp__ichor__web_search` to be wired in W103,
  consumed by Couche-2 5 agents + Pass 6 scenario decomposer (W105).
  NOT exposed to 4-pass briefings (audit-trail integrity).
- [ADR-083](docs/decisions/ADR-083-ichor-v2-trader-grade-manifesto-and-gap-closure.md)
  **Ichor v2 trader-grade manifesto**. 7 decisions D1-D7. D1 = 6-asset
  universe (EURUSD, GBPUSD, USDCAD, XAUUSD, NAS100, SPX500 promoted).
  D2 = Pass 6 scenario_decompose 7 stratified (W105). D3 = `key_levels[]`
  non-technical surface — gamma flip / peg / TGA / Polymarket / VIX
  regime (W106). D4 = Living Analysis View frontend (W107). D5 =
  SearXNG (ratified separately ADR-084).
- [ADR-082](docs/decisions/ADR-082-w101-calibration-w102-cf-access-strategic-pivot.md)
  **Strategic pivot post-W100g audit**. W101 calibration scoreboard
  P0 SHIPPED 2026-05-11 (commits 38248f8 → b88307a). W102 CF Access
  service token P0 SECURITY (RUNBOOK-018 authored, Eliot 15 min
  dashboard pending). Vision reframe : "pre-trade context discretionary
  toolkit, calibrated against historical realized outcomes" (not
  "hedge fund collective").

## Earlier ADRs (2026-05-09 batch — 14 ADRs)

- [ADR-081](docs/decisions/ADR-081-doctrinal-invariant-ci-guards.md)
  Doctrinal invariant CI guards (W90) — single test module
  `test_invariants_ichor.py` mechanises ADR-017 (no BUY/SELL),
  ADR-009 (Voie D), ADR-023 (Couche-2 Haiku not Sonnet), ADR-029
  (audit_log immutable), ADR-077 (tool_call_audit immutable),
  ADR-079/080 (watermark single-source-of-truth). 7 tests in 2.6s
  using Python `tokenize`. Adds the canonical reference for
  invariant mechanisation policy ; future ADRs cite "CI-guarded
  by …" or "INFORMAL — CI guard pending W?".
- [ADR-080](docs/decisions/ADR-080-disclosure-surface-contract.md)
  Disclosure surface contract — `/legal/ai-disclosure`, `/methodology`,
  `/.well-known/ai-content` (W89). Closes silent 404 regression on
  ADR-079 watermark target URL + `AIDisclosureBanner` /methodology
  link. Triple-redundant disclosure surface : HTML pages (human),
  per-response headers (machine-runtime), well-known endpoint
  (machine-discovery). force-static rendering invariant prevents
  runtime-failure 404.
- [ADR-079](docs/decisions/ADR-079-eu-ai-act-50-2-watermark-middleware.md)
  EU AI Act §50.2 machine-readable watermark middleware (W88) —
  `AIWatermarkMiddleware` tags 5 LLM-derived route prefixes with
  `X-Ichor-AI-{Generated,Provider,Generated-At,Disclosure}` headers.
  Closes the §50.2 enforcement deadline 2026-08-02 (T-3 mois).
  Complementary to ADR-029's web2 disclosure surface (§50.5
  human-readable). 10 unit tests pass.
- [ADR-078](docs/decisions/ADR-078-cap5-query-db-excludes-trader-notes.md)
  Capability 5 `query_db` allowlist excludes `trader_notes` (W86) —
  permanent invariant : `trader_notes`, `audit_log`, `tool_call_audit`,
  `feature_flags` form the forbidden set never readable by the 4-pass
  orchestrator. AMF DOC-2008-23 criterion 3 (personnalisation) stays
  unchecked by construction. CI guard test pending (W87).
- [ADR-077](docs/decisions/ADR-077-capability-5-mcp-server-wire.md)
  Capability 5 STEP-3 MCP server (W85) — `apps/ichor-mcp` on Win11
  forwards `query_db` + `calc` to apps/api `/v1/tools/*` over HTTPS.
  Three-layer auth (X-Ichor-Tool-Token + CF Access PRE-1 + Postgres
  grants). HTTP wrapper chosen over direct DB to keep credentials
  off Win11 + centralise tool_call_audit immutability.
- [ADR-076](docs/decisions/ADR-076-frontend-mock-fallback-pattern.md)
  Frontend `MOCK_*` are graceful fallbacks behind `isLive()`, not
  hardcoded mocks — keep the pattern. CLAUDE.md tech-debt line
  corrected.
- [ADR-075](docs/decisions/ADR-075-cross-asset-matrix-v2.md) Cross-asset
  matrix v2 — 6-dim macro state (MCT + nowcast surprise + NFCI + SKEW
  - VIX + SBOI) with qualitative bands + per-asset directional bias
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
- ~~**`tool_call_audit` migration NOT yet shipped** — PRE-2 blocker~~
  ✅ shipped W80 (commit `274d8e3`, migration 0038, immutable trigger
  verified live).
- Capability 5 wiring (ADR-071 6-step sequence) progress :
  PRE-1 CF Access service token = ⏳ pending Eliot manual ;
  PRE-2 tool_call_audit migration = ✅ W80 ;
  STEP-1 sqlglot whitelist = ✅ W83 ;
  STEP-2 calc dispatcher = ✅ W84 ;
  STEP-3 MCP server = ✅ W85 (ADR-077) ;
  STEP-4 RunnerCall.tools plumbing = ✅ W86 (`bf780f7`, ADR-078) ;
  STEP-5 orchestrator tool wiring = ✅ **W87 (this commit)** —
  `ToolConfig` dataclass in `runner_client.py` + `tool_config`
  argument on `Orchestrator` ; helper `_tool_fields_for(pass_kind)`
  emits `mcp_config / allowed_tools / max_turns` to RunnerCall when
  the pass is in `enabled_for_passes` (default `{"regime","asset"}`,
  Pass-3 stress and Pass-4 invalidation excluded — they operate on
  prior-pass narrative not raw market data) ; CI guard test
  `test_tool_query_db_allowlist_guard.py` enforces ADR-078 forbidden
  set ; 5 orchestrator tool-wiring tests + 4 allowlist guard tests
  green locally ;
  STEP-6 integration test = ⏳ final (depends PRE-1 in prod).
  Server tools (`web_search`/`web_fetch`) **excluded** — billed by
  Anthropic since 2026-04, violate Voie D.
- **WGC quarterly XLSX collector DROPPED 2026-05-11** (W101 strategic
  review). Rationale : (a) the dataset is quarterly with 3-month lag
  — does NOT fit Ichor's 4-pass intraday-to-weekly cadence ;
  (b) gold-related signals (FRED prices + CFTC TFF positioning +
  SKEW vol + DXY anti-correlation + real yields) already cover the
  actionable portion of the macro story for XAU/USD ; (c) Eliot's
  honest assessment "déjà mort" plus the friction of licensing
  request makes this cost > benefit. If future need arises for
  physical-gold-flows context, alternatives evaluated : IMF SDDS
  central-bank gold holdings (monthly, public SDMX API, free), CMX
  Stocks of Gold (daily inventory, free), SPDR Gold Shares (GLD)
  trust daily holdings PDF (free). All listed in W101 strategic
  audit but deferred too.
- Frontend `MOCK_*` audit (W78) revealed they are graceful fallbacks
  behind `isLive()`, not tech-debt. ADR-076 codifies; future revisit
  via reusable `<EmptyStateWithRetry>` component (W80 candidate).
- `replay/[asset]/page.tsx` derives `thesis_excerpt` via
  `deriveExcerpt` proxy because `SessionCardOut` lacks a `thesis`
  field (W81 candidate, 1h estimate).
- Polymarket `WHALES` constant in `polymarket/page.tsx` — no backend
  trade-tape collector yet (W82 candidate, separate ADR needed).

## Recently fixed (2026-05-11 — W100c+d+e+f : auto-fix avalanche + CF API token rotation)

- **W100c** ✅ — `.github/dependabot.yml` Docker section : 3 ecosystems
  changed from `docker` (parses Dockerfiles / k8s YAML) to
  `docker-compose` (parses `image:` tags from compose files), because
  the Ansible role dirs only contain `docker-compose.yml`. GA since
  Feb 2025 per github.blog/changelog/2025-02-25. Verified empirically
  post-W100b : Dependabot run failures with "No Dockerfiles nor
  Kubernetes YAML found" disappeared.
- **W100d** ✅ — pnpm-lock.yaml sync after first auto-merged
  Dependabot PR (#82, zustand 5.0.12 → 5.0.13, commit de2bdc2).
  Dependabot updated apps/web2/package.json but pnpm monorepo root
  lockfile didn't always sync. CI Node lint failed with
  `ERR_PNPM_OUTDATED_LOCKFILE`. Fix : `pnpm install --lockfile-only`
  on local. Followup tracking : the npm ecosystem in pnpm monorepos
  can mis-sync the root lockfile on per-directory Dependabot updates.
  Options for permanent fix tracked as W101 candidate.
- **W100e** ✅ — HTML guide `docs/guide-actions-eliot.html` §8 fully
  rewritten with real dashboard CF data (3 screenshots Eliot
  2026-05-11) + anti-hallucination correction. W100 had affirmed
  "Eliot Free pur, Budget Alerts inaccessibles" — WRONG. Real state
  is R2 Paid active (Pay-as-you-go) which DOES unlock Budget Alerts.
  Eliot already configured 3 alerts ($1/$5/$10). Cost Apr 17 → May
  11 = $0.00 across 25 days, R2 at 0.7% of free tier (143× margin).
  New §8.1bis section : abonnements ne protègent pas des coûts
  surprises (Pro/Workers Paid/Business breakdown). Stats grid + top
  callout bumped to W100e / 2026-05-11.
- **W100f** ✅ — **CF API token rotation** (`infra/secrets/cloudflare.env`
  SOPS-encrypted). Old token = REVOKED (confirmed via
  `curl /user/tokens/verify` → HTTP 401 "Invalid API Token"). New
  token created with minimum scope `Account.Cloudflare Pages:Edit`
  (audit confirmed this is the ONLY usage in the repo, via
  `wrangler-action@v3` in `auto-deploy.yml`). New token validated
  active (HTTP 200, ID `806ea32ba599dda8d73a49bd03942c11`). Diff
  sanity : exactly 3 changed line pairs (token blob +
  sops_lastmodified + sops_mac). 14 CI check-runs success.
  **Critical decision** : `CLOUDFLARE_API_TOKEN` GitHub Secret NOT
  added — would activate Pages deploy which publishes apps/web2 at
  `ichor-web2.pages.dev` (public URL by default), violating Eliot's
  "ultra sécurisé du publique le plus caché" directive. To activate
  Pages deploy in the future (W101 followup) : (a) create CF Pages
  project + CF Access service token gate on `*.pages.dev`,
  (b) `gh secret set CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID`,
  (c) verify first deploy lands behind CF Access (403 without
  headers, 200 with).
- **W100f known gap** — `HETZNER_HOST` GitHub Secret is ABSENT (only
  `HETZNER_SSH_PRIVATE_KEY` exists). Conséquence : the
  `auto-deploy.yml` Hetzner job conclusion=success is a no-op
  (guard skip all rsync + restart steps when HETZNER_HOST is empty).
  This is pre-existing (NOT a W100f regression — same state
  pre-W100). Implication : Python apps/api changes are NOT
  auto-deployed to Hetzner ; manual SSH + git pull + service
  restart required. For Hetzner side, this rotation requires a
  manual sync (next time someone deploys to Hetzner, they pick up
  the rotated SOPS file via git pull). Audit confirms NO Hetzner
  script consumes `CLOUDFLARE_API_TOKEN` directly (it's only used
  by `wrangler-action` in GitHub Actions for Pages), so no
  operational impact. Adding `HETZNER_HOST` is a W101 candidate if
  Eliot wants CI-driven Hetzner deploys.

## Recently fixed (2026-05-11 — W100 + W100b)

- **W100** ✅ — **Cap5 STEP-6 e2e SHIPPED — ADR-071 sequence is now 6/6**.
  `apps/ichor-mcp/tests/test_capability5_e2e.py` (8 tests, < 1s/run).
  Uses `mcp.shared.memory.create_connected_server_and_client_session`
  (MCP Python SDK 1.27, official 2026 pattern) to wire an in-memory
  ClientSession to the real `ichor_mcp.server` Server. httpx mocked
  via respx so the full chain is exercised : MCP client → `_call_tool`
  / `_list_tools` handlers → `ToolApiClient.calc()`/`.query_db()` →
  POST `/v1/tools/{calc,query_db}` → response wrap as TextContent.
  Cross-platform (no subprocess, no socket, no port collision). The
  8 tests pin : (1) canonical 2-tool round-trip + audit fields +
  9-op enum, (2) calc happy path full chain + header round-trip,
  (3) query_db happy path, (4) query_db validation rejection →
  audit-first TextContent (no exception), (5) calc bad-input →
  same audit-first wrap, (6) SDK upstream schema enforcement on
  unknown operation (drift guard on inputSchema), (7) network
  failure → 599 TextContent, (8) unknown tool name → handler's
  `name not in tool_index` guard returns TextContent JSON.
  Also W100 : Dependabot auto-merge workflow
  `.github/workflows/dependabot-auto-merge.yml` (patch+minor only,
  major manual, github-actions ecosystem always skipped). Cooldown
  block on every `.github/dependabot.yml` updates entry — npm/pip
  default 7d / patch 3d / minor 7d / major 14d ; github-actions
  flat 14d ; docker 7d. Mitigates Axios (mar 2026) + Shai-Hulud
  (sep 2025) supply-chain attack classes (95% yanked < 48h).
  HTML guide `docs/guide-actions-eliot.html` corrected three
  hallucinations from W97-W99 (CF Free Budget Alerts not available,
  CF Free R2 notifications not available, Anthropic console URL
  migration to `platform.claude.com`).
- **W100b** ✅ — Five post-merge findings from independent re-audit
  (verifier + code-reviewer + researcher subagents) closed in a
  single follow-up commit. (a) `.github/dependabot.yml` was being
  rejected by Dependabot's parser because the github-actions
  ecosystem doesn't support `semver-{major,minor,patch}-days`
  sub-keys ; check-run on 8605fa4 was failure. Fixed by keeping
  only `default-days: 14` for that block. (b) CLAUDE.md was bumped
  to W100 (this paragraph). (c) `test_capability5_e2e.py` got an
  `autouse` fixture that resets `ichor_mcp.config._settings` between
  tests (prevents singleton leak under parallel runs). (d) The
  `test_e2e_unknown_tool_returns_error_not_crash` test was
  tightened from a vague `try/except Exception` to a strict
  contract pin (no exception + CallToolResult shape + JSON payload
  with "unknown tool" + both real tool names). (e) Independent
  HEAD-check confirmed `platform.claude.com/settings/{keys,limits}`
  - `/usage` all return 200 + `console.anthropic.com/settings/keys`
    redirects to `platform.claude.com/settings/keys` (migration is
    real, URLs in the guide are valid).

## Recently fixed (2026-05-10 — invariant CI extension + pre-commit)

- **W91** ✅ — Doctrinal invariant CI guards extension + pre-commit
  hook (extends ADR-081). 2 new tests bring the tracked set from 7
  to 9 : `test_conviction_pct_capped_at_95` (ADR-017/022 cap-95
  source-inspection regex on `packages/ichor_brain/types.py`) and
  `test_pure_data_routes_excluded_from_watermark` (ADR-079/080
  NEGATIVE guard — `/v1/tools`, `/v1/market`, `/v1/fred`, `/v1/calendar`,
  `/v1/sources`, `/v1/correlations`, `/v1/macro-pulse`, `/healthz`,
  `/livez`, `/readyz`, `/metrics`, `/.well-known` MUST NOT leak
  into the watermark set). Pre-commit hook `ichor-invariants` added
  to `.pre-commit-config.yaml` so violations are caught locally
  before push (CI runs the same test as backstop). 9 tests in 2.4s.

## Recently fixed (2026-05-09 deep night — doctrinal invariant CI guards)

- **W90** ✅ — Doctrinal invariant CI guards (ADR-081). Mechanises
  5 of the most consequential Ichor invariants — never trade signals
  (ADR-017), Voie D (ADR-009), Couche-2 Haiku low (ADR-023), audit
  immutability (ADR-029 + ADR-077), watermark single-source-of-truth
  (ADR-079 + ADR-080). New module `apps/api/tests/test_invariants_ichor.py`
  (~250 LOC, 7 tests, runs in 2.6s). Uses Python `tokenize` to
  distinguish code tokens from STRING/COMMENT tokens — catches
  identifier-shaped uses of `BUY`/`SELL` while allowing them in
  docstrings/prompts. Catches `import anthropic`. Catches Couche-2
  drift back to Sonnet. Catches accidental migration trigger
  weakening. Catches W88/W89 single-source-of-truth drift between
  middleware DEFAULT_WATERMARKED_PREFIXES and Settings field. Now
  every CI run + every developer pre-commit (W91 follow-up) gate
  the doctrinal surface mechanically.

## Recently fixed (2026-05-09 deep night — disclosure surface contract)

- **W89** ✅ — Disclosure surface contract codified (ADR-080). Closes
  silent 404 compliance regression : ADR-079 watermark pointed to
  `https://app-ichor.pages.dev/legal/ai-disclosure` and
  `AIDisclosureBanner` linked to `/methodology`, but neither page
  existed. Created `apps/web2/app/legal/ai-disclosure/page.tsx`
  (full EU AI Act §50 + AMF DOC-2008-23 5-criteria + Anthropic AUP
  narrative, FR native, WCAG 2.2 AA, force-static) and
  `apps/web2/app/methodology/page.tsx` (4-pass + Pass 5 + Couche-2
  Haiku low + data-pool 43 sections + Brier calibration narrative,
  force-static). Added `apps/api` endpoint `/.well-known/ai-content`
  (EU CoP draft Dec-2025 hint, JSON schema v1, 5-min public cache).
  7 unit tests pass (`test_well_known_ai_content.py`). Single source
  of truth : `Settings.ai_*` fields drive both the W88 middleware
  AND the W89 well-known JSON, so config drift is impossible.
  Disclosure surface now triple-redundant : human (HTML pages),
  machine (per-response headers W88), discovery (well-known endpoint).

## Recently fixed (2026-05-09 deep night — EU AI Act §50.2 watermark)

- **W88** ✅ — EU AI Act Article 50(2) machine-readable watermark
  middleware. New `apps/api/src/ichor_api/middleware/ai_watermark.py`
  (`AIWatermarkMiddleware`, ~110 LOC, Starlette `BaseHTTPMiddleware`).
  Mounted in `main.py` between `RateLimitMiddleware` (inside) and
  `CSPSecurityHeadersMiddleware` (outside). Tags 5 LLM-derived route
  prefixes (`/v1/briefings`, `/v1/sessions`, `/v1/post-mortems`,
  `/v1/today`, `/v1/scenarios`) with 4 headers : `X-Ichor-AI-Generated`,
  `X-Ichor-AI-Provider`, `X-Ichor-AI-Generated-At` (RFC3339 UTC),
  `X-Ichor-AI-Disclosure`. Pure-data routes (`/v1/market`, `/v1/fred`,
  `/v1/correlations`, etc.) deliberately excluded. Path-prefix tuple
  match is allocation-free hot path. 3 new Settings fields :
  `ai_watermarked_route_prefixes`, `ai_provider_tag`,
  `ai_disclosure_url`. 10 unit tests pass (`tests/test_ai_watermark_middleware.py`).
  ADR-079 ratified — closes EU AI Act §50.2 enforcement deadline
  (2026-08-02 ferme, T-3 mois) on the API surface, complementary to
  ADR-029's web2 disclosure surface.

## Recently fixed (2026-05-10 — W99 Cap5 STEP-1/2 hardening from code-review)

- **W99** ✅ — 4 CRITICAL issues from code-reviewer subagent on the
  W83/W84/W87 batch. (1) `tool_query_db` function-call DoS bypass —
  `pg_sleep`, `pg_advisory_lock`, `lo_import`, `dblink`,
  `copy_from_program`, `pg_read_file` etc. were NOT rejected even
  though the table allowlist enforced. New `_FORBIDDEN_FUNCTIONS`
  frozenset + AST walk via `sqlglot.exp.Anonymous` /
  `sqlglot.exp.Func` subclass check (Defense 4). (2) `tool_query_db`
  `SELECT … FOR UPDATE / FOR SHARE` lifted row-locks — caught
  explicit `node.args["locks"]` non-empty (Defense 5). (3) CTE
  alias shadowing pinned by explicit regression test
  (`WITH alerts AS (SELECT * FROM trader_notes) SELECT * FROM alerts`
  rejected because the inner walk hits `trader_notes` first). (4)
  `tool_calc._no_nan` now rejects `bool` (Python `isinstance(True, int)
is True` surprise) + `inf` explicitly (was raising opaque
  `AttributeError` 500 from `statistics.fmean`). `_op_correlation`
  pre-checks `pstdev() == 0` to translate `StatisticsError` on
  constant series to a clean `ToolCalcError` 400.
  `runner_client.ToolConfig` docstring corrected — `mcp_config: dict`
  makes `hash(cfg)` raise `TypeError`, not hashable in practice ;
  new test `test_tool_config_is_not_hashable_due_to_dict_field` is
  the canary if a future ADR converts `mcp_config` to a hashable
  wrapper. SHOULD-FIX issues #5-#11 deferred. Coverage : apps/api
  1218 pass, ichor_brain 80 pass, claude-runner 22 pass — no
  regression. 18 new W99 regression tests (13 in
  `test_tool_query_db_w99_hardening.py` + 4 in `test_tool_calc.py` +
  1 in `test_orchestrator_tool_wiring.py`).

## Recently fixed (2026-05-09 late evening — Cap5 STEP-5 + ADR-078 guard)

- **W87** ✅ — Capability 5 STEP-5 orchestrator tool wiring +
  ADR-078 CI guard test. New `ToolConfig` dataclass in
  `packages/ichor_brain/runner_client.py` (mcp_config / allowed_tools
  tuple / max_turns / enabled_for_passes frozenset). `Orchestrator`
  accepts optional `tool_config` ; helper `_tool_fields_for(pass_kind)`
  emits the 3 fields to RunnerCall for each enabled pass. Default
  enables tools on Pass-1 (regime) + Pass-2 (asset) only — Pass-3
  stress and Pass-4 invalidation operate on prior-pass narrative,
  no marginal lift from tool access. Backward-compat preserved
  (`tool_config=None` is a strict zero-diff). New tests :
  `apps/api/tests/test_tool_query_db_allowlist_guard.py` (4 tests
  enforcing ADR-078 forbidden set ∩ ALLOWED_TABLES = ∅) +
  `packages/ichor_brain/tests/test_orchestrator_tool_wiring.py`
  (5 tests : pre-W87 zero-diff baseline / default Pass-1+2 wiring /
  custom enabled_for_passes filter / empty set disables everywhere /
  ToolConfig hashable). 84 pass ichor_brain + 73 pass apps/api tool
  suite.
- **W87 housekeeping** — Cleanup orphan worktrees `inspiring-
tereshkova-1de00b` (byte-identical to main pre-W85) and
  `zealous-banzai-efc1c7` (W85 source, mergé bf780f7's parent).
  Local branches deleted.

## Recently fixed (2026-05-09 late evening — Cap5 STEP-4 + housekeeping)

- **W86** ✅ — Capability 5 STEP-4 RunnerCall.tools plumbing.
  `packages/ichor_brain/runner_client.py` `RunnerCall` dataclass
  gains 3 fields (`mcp_config: dict | None`, `allowed_tools:
tuple[str, ...] | None`, `max_turns: int = 0`) ; payload submit
  in `_run_async_polling` + `_run_legacy_sync` forwards them
  conditionally to claude-runner ; `apps/claude-runner/models.py`
  `BriefingTaskRequest` + `AgentTaskRequest` mirror the same fields
  with Pydantic caps (max_turns 0..20, allowed_tools max 16,
  mcp_config max 8 top-level keys) ; `subprocess_runner.run_claude`
  writes mcp_config to a tempfile (Windows `delete=False` for the
  spawned subprocess lock), adds `--mcp-config <path>
--strict-mcp-config --allowedTools <csv> --max-turns N` to the
  CLI argv when set, cleans up in `finally`. 4 sites of `await
run_claude(...)` in main.py threaded (sync briefing + async
  briefing + sync agent + async agent). All pre-W86 callers stay
  byte-compatible (None defaults). ADR-078 bonus.
  Architecture validated by web research : claude CLI handles the
  agentic tool_use→tool_result loop entirely in-process when
  `--mcp-config` is provided ; orchestrator stays single round-trip.
- **W86 housekeeping** — Hooks user-scope `%USERPROFILE%` →
  `C:/Users/eliot` fix in `~/.claude/settings.json` (CC 2.1.128
  Rust spawn no longer expands the cmd.exe variable, so all 11
  hooks were silently exiting 127). audit.log + secret_scanner +
  pre_tool_destructive restored.

## Recently fixed (2026-05-09 evening — Capability 5 STEP-3 wave)

- **W85** ✅ — Capability 5 STEP-3 MCP server. New `apps/ichor-mcp`
  (Win11 stdio, lowlevel SDK, lifespan-managed httpx) +
  `apps/api/.../routers/tools.py` (POST `/v1/tools/{query_db,calc}`,
  audit-first dedicated session). Three-layer auth :
  `X-Ichor-Tool-Token` (production lifespan refuses empty) +
  CF Access PRE-1 (header pass-through, optional today) + Postgres
  grants. CI matrix updated (`apps/ichor-mcp` added to `.github/
workflows/{ci,audit}.yml`). 12 unit tests apps/api +
  12 unit tests apps/ichor-mcp green locally. ADR-077.

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
- **W78** ✅ — Frontend MOCK\_\* audit reframe (graceful fallbacks
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
