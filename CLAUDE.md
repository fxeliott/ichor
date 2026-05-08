# Ichor — Claude Code project memory

> Auto-injected at every session start. Keep terse and current.
> Last sync: 2026-05-09 (post-Wave 55 — production health restore: claude-runner Win11 restart + central_bank_speeches timer definitively killed + Couche-2 5 agents restored + 4 doc index drifts fixed
> via ADR-054 stdin pipe + Phase II Layer 1 quickwins).

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
│   │                         35 routers, 53 endpoints, 43 CLI runners,
│   │                         26 models, 37 collectors, 62 services
│   │                         (head migration: 0029_trader_notes)
│   ├── claude-runner/        FastAPI Win11 wrapper around `claude -p`
│   │                         /v1/briefing-task[/async] + /v1/agent-task
│   │                         stdin-pipe contract for prompt (ADR-054)
│   │                         async-polling for >100s tasks (ADR-053)
│   ├── web/                  legacy Phase 1 dashboard (read-only ref ; retired
│   │                         from pnpm-workspace 2026-05-06 ; 5 routes ported
│   │                         to web2 in commit `de80335`)
│   └── web2/                 Next.js 15.5 + React 19 + Tailwind v4 + motion 12
│                             42 routes SSR + ISR. `hooks/` dir absent
│                             (custom hooks live in `lib/use-*.ts`).
└── packages/
    ├── ichor_brain/          4-pass orchestrator (regime → asset → stress → invalidation)
    │                         + Pass 5 counterfactual. HttpRunnerClient async
    │                         polling default (ADR-053). Capability 5 scaffold
    │                         only (`tools_registry.py`, ADR-050).
    ├── agents/               5 Couche-2 agents (cb_nlp, news_nlp, sentiment,
    │                         positioning, macro). All on Claude Haiku low (ADR-023).
    │                         Wired to data_pool via `services/couche2_context`.
    ├── ml/                   HAR-RV, HMM, DTW, FinBERT-tone, multi-CB-RoBERTa
    │                         (FED/ECB/BOE/BOJ per ADR-040), ADWIN, Brier optimizer
    │                         V2 (env-gated), 6 bias trainers (ADR-022).
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
  user Startup folder. Rate limit raised 30→120 req/h (Wave 23) to
  fit a full 4-pass × 8-asset session-card sweep.
- **Cloudflare Tunnel** `claude-runner.fxmilyapp.com` → 127.0.0.1:8766
  (managed-config side, NOT in the local `~/.cloudflared/config.yml`).
  CF Access service token DEPLOYED on Hetzner side
  (`ICHOR_API_CF_ACCESS_CLIENT_ID=…`, expires 2027-05-06). Win11 runner
  itself still runs with `require_cf_access=false` (development mode)
  — the Hetzner→Cloudflare→Win11 path is auth-gated end-to-end via
  CF Access on the tunnel.

## Latest migrations (head 0033)

- **head 0033** — `0033_treasury_tic_holdings.py` (Wave 32) adds
  `treasury_tic_holdings` for monthly Major Foreign Holders. 38
  countries × 12 months persisted live 2026-05-08 with Dec 2025 Grand
  Total $9270.9B — China decline -20.5% / 3y is the canonical Stephen
  Jen "broken smile" foreign-repatriation signal.
- **0032** — `0032_cboe_vvix_observations.py` (Wave 29) — daily VVIX
  (vol of VIX) closes via Yahoo `^VVIX`. ~85 neutral / >100 elevated /
  >140 vol-surface blowup territory.
- **0031** — `0031_cftc_tff_observations.py` (Wave 25) — weekly CFTC
  TFF positioning, 4-class breakdown (Dealer / AssetMgr / LevFunds /
  Other / Nonrept). Smart-money divergence detection per asset.
- **0030** — `0030_cboe_skew_observations.py` (Wave 24) — daily CBOE
  SKEW Index. Tail-risk regime classifier (4-tier band).
- **0029** — `0029_trader_notes.py` adds the `trader_notes` table
  for the `/journal` route (Phase B.5d). Annotations per card / per
  session / per asset (cap 10 000 chars). OUT of ADR-017 boundary
  surface (it's user notes, not bias output).
- **0028** — `0028_audit_log_immutable_trigger.py` makes
  `audit_log` append-only via a BEFORE UPDATE OR DELETE trigger.
  Sanctioned purge path = `SET LOCAL ichor.audit_purge_mode='on'`
  in the same transaction (used by `purge_older_than`). MiFID-grade
  audit trail (cf ADR-029, Phase A.7 hardening).
- **0027** — `0027_session_type_extend_ny.py` extends the
  `session_card_audit` CHECK constraint to include `ny_mid` and
  `ny_close` (cf. ADR-024).
- **0026** — `session_card_audit.drivers` JSONB for Brier V2
  per-factor SGD (cf. ADR-022). Column shipped, optimizer V2 SHIPPED
  2026-05-06 (cf. ADR-025). Activation gated on
  `ICHOR_API_BRIER_V2_ENABLED=true` env flag.

## Phase II Layer 1 progress (Wave 35)

**14 / 30 priority sources collected (47 %), 13 / 14 surfaced data_pool (93 %).**

Custom collectors live :
- `cboe_skew_observations` (Wave 24, Yahoo `^SKEW`, daily 23:30 Paris)
- `cftc_tff_observations` (Wave 25, Socrata `gpe5-46if`, weekly Sat 02:30)
- `cboe_vvix_observations` (Wave 29, Yahoo `^VVIX`, daily 23:35 Paris)
- `treasury_tic_holdings` (Wave 32, ticdata.treasury.gov `mfhhis01.txt`,
  daily 03:00 Paris with idempotent dedup)

FRED extended adds (Waves 23 / 24 / 28 / 34 / 40 / 42) ≈ 50 valid series :
- Fed H.4.1 detail : WSHOSHO + WSHOMCB + WRESBAL
- Atlanta nowcasts : GDPNOW + PCENOW
- CBOE vol surface : GVZCLS + OVXCLS + RVXCLS
- OECD CLI 7 regions : USA + G7 + JPN + DEU + GBR + CHN + EA19
- Labor + uncertainty + recession (W40) : ICSA + IC4WSA + USREC + USEPUINDXD
  + CIVPART + AHETPI + ATLSBUSRGEP
- FX rates (W42) : DEXJPUS + DEXUSEU + DEXCHUS + DEXCAUS + DEXSZUS +
  DEXUSAL + DEXUSNZ
- Fed monetary stance (W42) : FEDFUNDS + EFFR + DFEDTARU + DFEDTARL
- Inflation expectations (W42) : EXPINF1YR
- Financial conditions (W42) : NFCI + ANFCI + STLFSI4 + TEDRATE + AAA + BAA
- Macro composites (W42) : CFNAI + CFNAIDIFF + PSAVERT + UMCSENT + MCUMFN
- Yield curve detail (W42) : DGS1 + DGS3 + DGS7 + DGS20 + T10YFF
- Cleanup waves 37b/c : 7 ghost FRED series removed (silent 400-fails fixed)

data_pool sections live (37, was 29 pre-Wave 26) — new in Phase II :
`tail_risk` (SKEW + VVIX + GVZ + OVX + RVX), `tff_positioning`
(per-asset 4-class + Δw/w + smart-money divergence ⚠), `treasury_tic`
(top-10 holders + 3y trend, China -20.5 %), `oecd_cli` (7 regions +
China-vs-rest divergence flag), `labor_uncertainty` (jobless / EPU /
recession / wage-inflation, W41), `fed_financial` (Fed Funds target
band + EFFR position + NFCI/ANFCI/FSI4 + BAA-AAA spread + 1y inflation
expectations, W43). Polymarket section (W39) categorized in 6 buckets
(Monetary policy / Macro indicators / Geopolitics / US politics /
Crypto-macro / Other).

ADR-055 ratifies DOLLAR_SMILE_BREAK gate 4-of-4 → 5-of-5 with SKEW as
5th condition + graceful_none warm-up tolerance (preserves ADR-043
behavior <60 d, becomes strict-er after).

## Recent ADRs (2026-05-08 wave 20-35)

- [ADR-055](docs/decisions/ADR-055-dollar-smile-break-skew-extension.md)
  **DOLLAR_SMILE_BREAK extended with SKEW** — 5-of-5 gate + graceful-None
  warm-up. Strict-er than ADR-043 once SKEW history ≥ 60 d.
- [ADR-054](docs/decisions/ADR-054-claude-runner-stdin-pipe-windows-argv-limit.md)
  **claude-runner stdin pipe** — pipe `prompt` via stdin to bypass
  Windows `CreateProcessW` 32 768-char `lpCommandLine` limit. Pre-fix
  6 of 8 assets crashed `[WinError 206]` on data_pool > 17 KB ;
  post-fix all 8 persist DB live verified. (BLOCKER #2 closed.)
- [ADR-053](docs/decisions/ADR-053-claude-runner-async-polling-refactor.md)
  **claude-runner async + polling** — POST `/v1/briefing-task/async`
  → 202 + task_id ; GET poll every 5 s. Bypass Cloudflare 100 s edge
  timeout that silently broke 4 briefing types since 2026-05-06.
  (BLOCKER #1 closed wave 20.)
- [ADR-050](docs/decisions/ADR-050-capability-5-tools-runtime.md)
  **Capability 5 scaffold only** — 5 tools (web_search, web_fetch,
  query_db, calc, rag_historical) registered with JSON schemas in
  `tools_registry.py`. Handlers raise `NotImplementedError` ; runtime
  wiring deferred Phase D.0.
- [ADR-049](docs/decisions/ADR-049-hy-ig-spread-divergence-alert.md)
  HY-IG spread z-score 90d (credit cycle inflection). Catalog 51→52.
- [ADR-052](docs/decisions/ADR-052-term-premium-intraday-30d-alert.md)
  TERM_PREMIUM_INTRADAY_30D — completes term premium trinity (30d/90d/252d).
  Catalog 53→54 (current head).
- [ADR-025](docs/decisions/ADR-025-brier-optimizer-v2-projected-sgd.md)
  Brier optimizer V2 — projected SGD on the per-factor drivers matrix.
  New CLI `run_brier_optimizer_v2.py`, three helpers added to
  `services/brier_optimizer.py`, gated on `ICHOR_API_BRIER_V2_ENABLED`.
- [ADR-024](docs/decisions/ADR-024-session-cards-five-bug-fix.md)
  fixed 5 stacked bugs that had killed `session_card_audit` writes
  for 2 days. ny_mid + ny_close now valid sessions.
- [ADR-023](docs/decisions/ADR-023-couche2-haiku-not-sonnet-on-free-cf-tunnel.md)
  Couche-2 mapping changed Sonnet medium → Haiku low (CF Free
  tunnel 100 s edge cap).

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

## Things that are subtly broken or deferred (post Phase 0 + A.1)

- `apps/web` legacy retired from pnpm-workspace 2026-05-06 ; 5 routes
  portées vers web2 (commit `de80335`). 25 page.tsx restent on-disk
  comme référence read-only.
- `apps/web2` 1 boundary global pour loading.tsx/error.tsx/not-found.tsx ;
  per-segment manquant sur 41 routes (Phase B cible).
- CF Access service token pas wired sur claude-runner.fxmilyapp.com
  (Phase A.7).
- `crisis_mode_runner` mentionné dans `alerts_runner.py:20` mais
  **absent du repo** — Crisis Mode composite N≥2 non câblé (Phase A.2).
- Wave 5 CI : ruff blocking 4 packages ✓, mypy blocking apps/api seul,
  pytest auto-skip si pas de tests/, coverage gate absent (Phase A.3).
- Capability 5 ADR-017 absente : Claude tools en runtime
  (WebSearch/WebFetch/query_db/calc/rag_historical) pas câblés
  dans 4-pass — modèle reçoit text-only via data_pool précompilé
  (gap doctrinal, Phase D.0).

## Recently fixed (2026-05-06 evening, Phase 0 + A.1 + A.2 + A.3 + A.4.a/b + A.5 + A.7.partial)

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
