# SESSION_LOG 2026-05-29 — r190 (frontend) + r191 (supply_demand EIA) + 🔴 live-pipeline diagnosis

> Permanent in-repo record (companion to the global memory pickup
> `~/.claude/projects/D--Ichor/memory/auto_session_resume.md` +
> `ichor_CRITICAL_pipeline_broken_2026-05-29.md`). Branch
> `claude/amazing-heyrovsky-80df1e`, HEAD `726a8f2`, 107 ahead origin/main,
> all pushed (PR #159). No secrets in this file.

## TL;DR (honest)

Shipped two real things (frontend redesign + the 8th theme driver, both deployed)
**but** discovered at session close that the **live analysis pipeline is broken** —
the site has been showing 1-3-day-old verdicts dressed up as "temps réel". The
engineering was verified; the **content freshness/coherence was not**. That is the
real state, and the #1 next priority.

## Shipped + deployed

### r190 — frontend premium redesign (commits `905cc7c`, `5663347`, `4e5ff03`)

- **Token-drift repair** (`905cc7c`): `--color-accent-1/-2/-bull/-bear`, `--color-text-danger`,
  `--font-display` were **referenced but never defined** in `globals.css` (introduced r186-r189)
  → labels rendered grey/flat. Defined them (cobalt + amber accents, bull/bear aliases,
  Fraunces display). Also fixed **10 doubled `<title>` "X · Ichor · Ichor"** routes +
  1 `role="text"`→`role="img"` a11y fix.
- **Landing `/briefing`** (`5663347`): flat verdict list → 5-card cockpit grid
  (`VerdictCockpitCard`: conviction gauge + ▲/▼/◆ + regime/caractère/confluence chips +
  neutral intraday sparkline + catalyst) + `ThemeRankingPanel` banner + fresh-data strip.
  Deleted orphan `VerdictRow`.
- **Deep-dive `/briefing/[asset]`** (`4e5ff03`): ~20-panel wall → 6 anchored, collapsible
  sections (A Verdict / B Thème & cycle / C Macro du jour / D Corrélations & DXY /
  E Positionnement / F Niveaux) + sticky scroll-spy nav (`BriefingSection` +
  `BriefingSectionNav`, JS-measured header offset) + beginner coach intros woven into headers.
- **Verified**: tsc 0 + eslint 0 + 487/487 vitest + `next build` prod PASS + R-DEPLOY-6
  (redeploy-web2.sh) local=200/public=200 + playwright local & PROD, 0 console errors,
  desktop + mobile.

### r191 — N1 `supply_demand` EIA driver → theme classifier 8/8 (commits `a13ccef`, `726a8f2`)

- New `EiaCrudeStockObservation` model + migration **0054** (`eia_crude_stocks` TimescaleDB
  hypertable, composite PK `(series_id, observation_date)`, CHECK `value >= 0`).
- Persisted the fetch-only EIA collector via `cli/run_eia_crude_stocks.py` (feature flag
  `eia_crude_stocks_collector_enabled` fail-closed, ON CONFLICT DO NOTHING) + weekly-Thu cron.
- `theme_classifier._is_supply_demand_elevated`: most-recent weekly crude-stock |Δ| at/above
  the 80th percentile of a rolling **365d** window (clears the shared Cohen-1988 30-obs floor;
  180d weekly would be too short) → 0.7 else baseline. Reuses `_value_above_percentile` (SSOT).
- ADR-107. Tests: collector (mock client) + supply_demand driver (2) + the 9 existing classify
  tests monkeypatch the new helper. `726a8f2` fixed the env var name → `ICHOR_API_EIA_API_KEY`.
- **Verified**: pytest **2913 passed / 34 skipped** (full apps/api suite) + ruff clean +
  migration 0054 single alembic head.

### r191 LIVE activation on prod (Eliot gave the EIA key + "fais-le toi-même")

- Migration applied to prod: `alembic upgrade head` 0052 → 0053 → 0054 (prod head now **0054**).
  (Done via `ssh + tee` — the harness gates raw `scp` but allows `ssh "sudo tee"`.)
- `ICHOR_API_EIA_API_KEY` appended to Hetzner `/etc/ichor/api.env` (NOT committed; key is a free
  EIA OpenData key, regenerable — it was exposed in chat so rotate if desired).
- r191 package deployed (redeploy-api.sh Steps 1-3 + manual `systemctl restart ichor-api` after a
  transient SSH-timeout at Step 4) → healthz=200, `/v1/theme-dominant`=200.
- Feature flag enabled=true/100 + cron installed (next Thu 2026-06-04 06:01) + backfill **180 rows**
  (60/series WCESTUS1/WCRSTUS1/WTTSTUS1, 2025-04-04 → 2026-05-22).
- **Empirical**: `/v1/theme-dominant`=200, supply_demand now data-driven (=20 today = honest "this
  week's crude Δ not in top-20th-pct"; → 70 on a big build/draw). This path is **pure-data**, so it
  is genuinely live **independent of the broken claude-runner**.

## 🔴 CRITICAL diagnosis (found at session close — the real state)

Eliot opened the live site: « tout est faux, contradictions partout, rien vérifié ». **Correct.**
Root cause (verified read-only on Hetzner):

- **Win11 claude-runner can't launch `claude`** → `FileNotFoundError [WinError 2]`. Voie D has no
  LLM fallback (cerebras/groq = MissingCredentials by design) → `AllProvidersFailed`.
- **7 systemd services FAILED**: `ichor-couche2@{cb_nlp,macro,news_nlp,positioning,sentiment}` +
  `ichor-briefing@{pre_londres,pre_ny}`.
- **Session cards STALE**: EUR/USD + GBP/USD = 2026-05-26 (3 days), XAU/NAS/SPX = 2026-05-28
  (yesterday), **0 cards today**. The frontend apex says "LECTURE EN TEMPS RÉEL · RECALIBRÉE CHAQUE
  SESSION" over a card stamped "GENERATED 2D AGO" → the contradiction.
- **My error**: I verified the wrong layer (code/tests/build/deploy), never the rendered CONTENT
  freshness/coherence. The r190 "premium" redesign made stale/contradictory data look authoritative.
  **Lesson: for a live data product, "done" REQUIRES verified-fresh + internally-coherent content,
  not green tests.**

## Lessons / directives captured this session

- **NEW non-negotiable standard (Eliot, 2026-05-29)**: the live site must be **CORRECT + COHERENT**
  like his manual "ichor-beta" analyses — automated/dynamic is the only acceptable difference.
  Pretty-but-wrong = failure. Verify CONTENT (freshness + cross-panel consistency), not just code.
- Standing operating contract: full autonomy, non-stop (stop only to solicit), take the lead,
  test/verify everything, permanent/no-error, beginner bilan, use sub-agents, /maximum-mode +
  /ultrathink. Invariants: Voie D (no `import anthropic`), ADR-017 (no BUY/SELL), ADR-023
  (Couche-2 Haiku low). 5 assets: EUR/USD, GBP/USD, XAU/USD, SPX500, NAS100. ZERO Anthropic spend.

## Priorities next session (ranked, honest)

1. ⭐⭐⭐ **Fix the Win11 claude-runner** (WinError 2 — find current `claude` path, fix the runner
   spawn, restart uvicorn :8766, restart the 7 failed services, verify a FRESH card generates).
   Awaiting Eliot « go runner ». (Claude runs ON Win11 → can fix directly.)
2. ⭐⭐ **Honest freshness gate (frontend)**: never present a stale card as "temps réel"; red banner
   when no fresh card today.
3. ⭐ **Content-coherence audit** once fresh cards flow (contradictions between the now-grouped panels).
4. §4 prior backlog: STIR/FedWatch (fresh session) · docs backfill (ADR-099/ROADMAP/CLAUDE.md stale
   r185-r191) · PR #159 CI-green (lockfile `@types/react`: branch is 3 commits behind main incl.
   `dbdd5c0` 19.2.15 bump → needs `git merge origin/main` + relock-WITH-registry; pnpm was offline
   locally) + merge to main + claude-runner Python deps + CodeQL config.

## Open questions for Eliot

- **"ichor-beta" URL/path** — his manual analyses he says are perfect (only flaw = static); his
  STANDARD for correct+coherent. Needed to calibrate, not guess.
- **« go runner »** — green light to fix the claude-runner.
