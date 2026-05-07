# Ichor — Session Log 2026-05-07

> Ultrathink autonomous session. Started from `claude/blissful-lewin-22e261`
> with 47 pending files (29 M + 2 D + 16 ??), ended with **11 commits**
> structured across 3 phases + 1 fix. **Local only — no push, no SSH,
> no pnpm install** per Eliot's bypass-mode standing guard-rails.

## Headline numbers

- **80 files** changed, **+4588 / -143** lines.
- **11 commits** narratively organised, bisect-friendly.
- **6 new ADRs** ratified (026-032 less 029/030/031 already drafted but committed
  here; 026, 027, 028, 032 net new).
- **3 new RUNBOOKs** (014, 015, 016).
- **Build green** on `apps/web2` (41 routes, Next.js 15.5.15).
- **0 push** — diff awaits Eliot review.

## Scope by category

| Area         | Files | +LOC | -LOC | Notes                                                                                                                         |
| ------------ | ----: | ---: | ---: | ----------------------------------------------------------------------------------------------------------------------------- |
| `apps/api/`  |    12 |  316 |   35 | Event-loop x4 CLI fix + /metrics + Langfuse lifecycle + audit_log immuable                                                    |
| `apps/web2/` |    28 | 1288 |    5 | UX baseline (TopNav/cmdk/sonner/MobileGate) + Phase B (a11y/lighthouse/per-segment boundaries) + next.config security headers |
| `packages/`  |    15 |  282 |   66 | Couche-2 ADR-023 docstrings + VALID_SESSION_TYPES + Langfuse @observe shims + 5 patches                                       |
| `docs/`      |    12 | 2108 |    4 | 6 ADRs (026-032) + 3 RUNBOOKs (014-016) + ROADMAP REV5                                                                        |
| `scripts/`   |     6 |  281 |    0 | OnFailure systemd + register-cron-{rr25,liquidity,cb-tone} canonical pattern                                                  |
| `.github/`   |     4 |  202 |    6 | Wave 5 CI ramp + web2-a11y workflow + web2-lighthouse workflow                                                                |

## Commits chronological

| #   | Hash      | Subject                                                                                   | Phase       |
| --- | --------- | ----------------------------------------------------------------------------------------- | ----------- |
| 1   | `b5b6fd6` | chore(cleanup): event-loop fix x4 CLI + drop shared-types stub + ADR-023 + runbooks index | A.1         |
| 2   | `42c6823` | ci(wave5): coverage gate + shellcheck + structural lint hetzner scripts                   | A.3         |
| 3   | `39580a2` | feat(observability): Prometheus /metrics endpoint via fastapi-instrumentator              | A.4.a       |
| 4   | `d295577` | feat(systemd): OnFailure drop-ins on 28 services + ntfy notify-template                   | A.4.b       |
| 5   | `8eac82c` | docs(adr): 029 EU AI Act §50 + 030 ResolveCron protection + 031 SessionType single source | A.5         |
| 6   | `f4e3005` | feat(audit): immutable audit_log via BEFORE UPDATE/DELETE trigger + RUNBOOK-014/015       | A.7.partial |
| 7   | `4d5e76c` | feat(web2): UX baseline — TopNav + cmdk palette + sonner + MobileGate + NOW dyn           | A.9         |
| 8   | `7151d94` | docs(roadmap): REV5 — Phases 0+A.1+A.2+A.3+A.4.a/b+A.5+A.7.partial+A.9 shipped            | meta        |
| 9   | `719d511` | feat(observability): Langfuse @observe on 4-pass + Couche-2 (ADR-032)                     | A.4.c       |
| 10  | `b26419e` | feat(web2): Phase B frontend infra — WCAG 2.2 AA + Lighthouse CI + per-segment boundaries | B           |
| 11  | `44de15f` | fix(web2): exclude e2e/ from tsc + gitignore .serena/                                     | B (fix)     |

## Phase A.4.c Langfuse @observe — what was wired

3 layers of tracing per ADR-032:

```
session_card_4pass (Orchestrator.run)              ← parent trace
├── couche1_runner_call (HttpRunnerClient.run)      ← Pass 1 régime generation
├── couche1_runner_call (HttpRunnerClient.run)      ← Pass 2 asset
├── couche1_runner_call (HttpRunnerClient.run)      ← Pass 3 stress
└── couche1_runner_call (HttpRunnerClient.run)      ← Pass 4 invalidation

couche2_chain (FallbackChain.run)                   ← parent trace per agent run
└── couche2_agent_task (call_agent_task)            ← Claude path generation
```

**Fail-soft**: when `langfuse>=4.0.0` is absent (CI, tests),
package-local shim modules (`ichor_brain.observability`,
`ichor_agents.observability`) provide a no-op decorator. When present
(Hetzner prod after deployment), real spans fire to the self-hosted
Langfuse v3 stack.

**Lifecycle**: `apps/api/observability.py` owns `Langfuse` singleton;
FastAPI lifespan calls `init_langfuse()` at startup, `flush_langfuse()`
at shutdown BEFORE engine.dispose() (worker thread is daemonic).

**Tests**: 5 unit tests each in `packages/{ichor_brain,agents}/tests/test_observability.py`.

## Phase B Frontend infra — what was wired

### Surface security (`apps/web2/next.config.ts`)

- async `headers()` with HSTS 1y+subdomains, X-Frame-Options DENY,
  X-Content-Type-Options nosniff, strict Referrer-Policy, denied
  Permissions-Policy.
- Basic CSP (script-src 'unsafe-inline' interim — strict-dynamic +
  nonces in Phase B.5).
- `experimental.ppr` commented (Next 15.5 stable rejects with
  CanaryOnlyError per [vercel/next.js#71587](https://github.com/vercel/next.js/issues/71587);
  path = Next 16 cacheComponents migration).

### WCAG 2.2 AA (ADR-026/027)

- `apps/web2/e2e/fixtures/a11y.ts` — shared `makeAxeBuilder` fixture
  tagged `["wcag2a","wcag2aa","wcag21a","wcag21aa","wcag22aa"]`.
- `apps/web2/e2e/a11y.spec.ts` — 5 pivot routes × axe scan, 0 violations
  contract.
- `.github/workflows/web2-a11y.yml` — runs on every PR.

### Performance budget (ADR-026)

- `apps/web2/lighthouserc.json` — perf ≥0.9 / a11y ≥0.95 / LCP ≤2500ms
  / TBT ≤200ms (INP proxy) / CLS ≤0.1 / interactive ≤3500ms.
- `.github/workflows/web2-lighthouse.yml`.

### Per-segment boundaries (ADR-026)

- 5 pivot routes × {loading.tsx, error.tsx} = 10 new files:
  /today, /sessions/[asset], /replay/[asset], /scenarios/[asset], /admin.

## Eliot-blocking items (cannot proceed without input)

### 1. `git push origin claude/blissful-lewin-22e261` — diff review

11 commits against main (44ec15a → 44de15f). To push:

```bash
git diff 44ec15a..HEAD          # full diff — 4731 line review
git log --stat 44ec15a..HEAD    # per-file change counts
git push origin claude/blissful-lewin-22e261
gh pr create --base main --head claude/blissful-lewin-22e261 \
    --title "Phases A.1+A.3+A.4.a/b/c+A.5+A.7.partial+A.9+B shipped" \
    --body "..."
```

Per Eliot's standing rule: I must show the full diff and get an
explicit "yes push" before doing it.

### 2. `pnpm install` — réseau sortante for Phase B devDeps

Phase B added 4 devDependencies (`@axe-core/playwright`, `axe-core`,
`@lhci/cli`, `lighthouse`). The lockfile is NOT regenerated. CI
workflows `web2-a11y.yml` and `web2-lighthouse.yml` will fail at
`pnpm install --frozen-lockfile` until this runs.

Command (annonce préalable per guard-rails):

```bash
cd D:\Ichor\.claude\worktrees\blissful-lewin-22e261
pnpm install
```

This pulls ~25 MB of new packages from npm registry. Local-only —
no remote write — but is réseau sortante.

### 3. SSH Hetzner — Langfuse v4 install

Phase A.4.c lands the wiring; Hetzner needs the lib:

```bash
ssh ichor-hetzner '/opt/ichor/api/.venv/bin/pip install "langfuse>=4.0.0"'
ssh ichor-hetzner 'sudo systemctl restart ichor-api.service'
ssh ichor-hetzner 'sudo journalctl -u ichor-api.service \
    --since "30 seconds ago" | grep langfuse_enabled'
# Expected: api.langfuse_enabled host=http://127.0.0.1:3000
```

Two réseau-sortante hops (pip install + systemctl restart). Per ADR-032

- RUNBOOK-016 deployment note.

### 4. Worktree rationalisation

Currently 3 worktrees co-exist:

- `D:\Ichor` (main, 44ec15a)
- `D:\Ichor\.claude\worktrees\blissful-lewin-22e261` (this work, +11 commits)
- `D:\Ichor\.claude\worktrees\trusting-faraday-6ba8fc` (clean, my CWD)

After push + merge, prune blissful-lewin + trusting-faraday:

```bash
git worktree remove D:\Ichor\.claude\worktrees\blissful-lewin-22e261
git worktree remove D:\Ichor\.claude\worktrees\trusting-faraday-6ba8fc
```

## Next session priority menu (ranked)

| #   | Phase                                                                                 | Estimated | Risk   | Blocker                                            |
| --- | ------------------------------------------------------------------------------------- | --------- | ------ | -------------------------------------------------- |
| 1   | **B.5 partial — Counterfactual UI scaffold**                                          | 3-4 h     | low    | none — code-only                                   |
| 2   | **B.5 partial — SessionTabs câblées (4 dead buttons in `/sessions/[asset]:404-428`)** | 1 h       | low    | none                                               |
| 3   | **B.5 partial — pin/favorite asset (localStorage)**                                   | 1 h       | low    | none                                               |
| 4   | **C QW — globals.css OKLCH migration**                                                | 2-3 h     | low    | none                                               |
| 5   | **D.0 — Capability 5 (Claude tools runtime)**                                         | 6-8 h     | medium | needs runner /v1/structured-prompt endpoint design |
| 6   | **D.1 — Brier V2 adoption-promotion job**                                             | 3-4 h     | medium | needs holdout ≥30 sessions                         |
| 7   | **D.5.a — DATA_SURPRISE_Z (NFP/CPI/Core PCE/ISM)**                                    | 4-6 h     | medium | needs ForexFactory consensus collector             |
| 8   | **E — Conformal prediction wrapper Brier V2**                                         | 4-5 h     | high   | depends on D.1                                     |
| 9   | **F.1 — Routines POC**                                                                | 2 h       | low    | needs Eliot Routines eligibility check             |

## Verification done this session

- `next build` on `apps/web2` — **green** (41 routes static + dynamic).
- `python -m py_compile` on all Python modules touched — **green** (10 files).
- 5 unit tests for the @observe shim each in brain + agents (offline,
  no langfuse needed) — created, will run on CI.
- No SSH, no pip install, no pnpm install, no git push — all 0.
- All commits passed pre-commit hooks (ruff format, prettier write).

## Verification deferred

- Langfuse trace flow end-to-end — needs Hetzner deploy (Eliot blocker #3).
- Lighthouse CI numbers — needs lockfile regeneration (Eliot blocker #2).
- `pnpm test:e2e a11y.spec.ts` locally — same.
- Browser preview snapshot of /today loading skeleton — skipped this
  session, build green is the structural proof.

## Known issues / debt

- `apps/web2/package.json` lists 4 new devDeps that don't exist in
  `pnpm-lock.yaml` yet. Lockfile-only mismatch; harmless until CI runs.
- `experimental.ppr` is commented out — re-add post-Next-16 migration.
- `audit.log` (~/.claude) figé depuis 2026-05-01 — Phase A.1 hook diag
  not yet done. Not a code issue, env-side.
- The 3-worktree topology (main + blissful + trusting-faraday) is
  redundant once push + merge land.

## What was NOT touched (intentional, per scope)

- Couche-2 agent docstrings cite ADR-021 in some lingering places —
  will be caught by ADR-023 mention in commit b5b6fd6 ; full grep
  cleanup deferred.
- `lightweight-charts 5.2.0` dead dep removal — already done in main.
- ADR-032 followups (per-batch parent trace, score creation, agent
  name in trace metadata) — explicitly deferred in the ADR.
- Phase D / E / F — out of scope for this session's diff.

## Doctrinal anchors maintained

- ADR-017 boundary — **no BUY/SELL** anywhere in the new code (verified
  by greps in commit messages where applicable).
- ADR-009 Voie D — **no anthropic SDK** added; Langfuse v4 has no
  Anthropic dep transitively (verified via the optional pydantic-ai-slim
  - httpx baseline).
- ADR-029 EU AI Act §50 — surface unchanged, banner + footer stay live;
  Phase B's CSP doesn't mask them (no `frame-ancestors`/`object-src`
  rule that conflicts).
- Conviction cap 95% — untouched (no model/prompt change in this scope).
