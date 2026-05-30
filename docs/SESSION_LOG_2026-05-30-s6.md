# SESSION LOG — 2026-05-30 (SESSION 6) — content data-quality + London panel + weekend honesty

Branch `claude/ichor-s6-consensus` (branched fresh from `origin/main` `c528561`,
which holds the merged PR #159 / SESSION-4+5 work). **5 work commits `3528aa7 →
ca08f56`** (+ this session-log commit), all pushed — NOT yet a PR (Eliot merges).

Invariants held all session: **Voie D** (zero `import anthropic`), **ADR-017**
(no BUY/SELL — every new surface is descriptive + test-guarded), **ADR-023**
(Couche-2 stays Haiku), **Opus 4.8** on briefings. **ZERO Anthropic API spend.**

---

## Owner demands / directives (this session, verbatim intent)

- **Master vision re-sent** (`Prompt_Ichor.md`, archived `ichor_owner_vision_prompt.md`).
  CŒUR : pre-trade macro research for **5 assets** (EUR/USD, GBP/USD, XAU/USD,
  SPX500_USD, NAS100_USD). Eliot trades the **NY-open volume, 14h–16h Paris,
  cuts everything at 20h**. Ichor must deliver a **pre-session VERDICT** per
  asset = bias (haussier/baissier/neutre) + conviction % + nature
  (momentum vs structuré) + déclencheurs + invalidations + scénarios — calibrated
  for the NY session, as a **beginner-level COACH** on a **premium web page**.
  **NEVER BUY/SELL/TP/SL** (ADR-017 contractual) — Eliot does the technical
  analysis on TradingView; Ichor does everything else (fundamental, macro, géopo,
  news, DXY, Polymarket, volume, sentiment, corrélations, liquidité, calendrier,
  Londres→NY read, real-time reactivity).
- **Operating protocol ①–⑪** : full autonomy / non-stop / **real functional
  validation (verify rendered CONTENT, not just "code runs")** / world-class on
  each micro-action / unblock as expert / finalize everything / re-read + optimize /
  beginner bilan.
- **Ranked plan** (from the pickup prompt) : **#1** free analyst-consensus-range
  source → `economic_events.forecast_min/max` + fix the GDP "0.40284" anomaly
  (PLUS FORT LEVIER) · **#2** `<LondonSessionPanel>` frontend (§6.2 CAPITAL) ·
  **#3** §10 Couche-2 Opus decision · **#4** ADR-108 formal docs · **#5** ECB/BoE
  implied paths + weekend-card relevance + Phase-4.
- **Standing lesson (2026-05-29)** : a live data product is "done" only when the
  rendered CONTENT is fresh + coherent, not when tests are green.

## Open-check (session start) — VERIFIED, not assumed

The 2026-05-29 "pipeline broken" scare was **already RESOLVED that evening**
(Win11 runner binary repointed). At this session's open: runner `:8766` up
(`claude_cli_available:true`), Hetzner `NO_ICHOR_FAILED`, all 5 priority assets
had **fresh cards today**, verdicts coherent (low conviction = weekend).

---

## What shipped (5 commits — what / why / verification)

### 1. `3528aa7` fix(economic-events): normalize FRED actuals to FF unit convention — RANKÉ #1 core

- **Bug** : the FRED ALFRED reconciler stored `actual` in FRED-native units
  ("115" = 115K NFP, "6866" = 6.866M JOLTS, "0.40284" = non-annualized GDP %)
  while the ForexFactory collector stores `forecast`/`previous` as display
  strings with units ("65K", "6.86M", "2.0%"). → `actual` was **incomparable**
  to `forecast` for level series (only masked by the r146 100× `unit_scale_mismatch`
  band-aid) and **unreadable** on the briefing.
- **Fix** : `normalize_actual_value()` in
  `apps/api/src/ichor_api/services/economic_event_actuals_reconciler.py` converts
  each FRED actual to FF convention **before storage** — K/M for count series via
  a per-series `SERIES_DISPLAY_UNIT` map, 1-dp half-up "%" for pct-change/level
  series. **GDP `pch`→`pca`** (compounded annual rate) so its annualized SAAR
  basis matches FF's forecast (empirically verified GDPC1 2026-Q1 pch=0.40284 vs
  pca=1.62114). Classifier + its 100× guard untouched.
- **Verified** : 55+104 tests; deployed; **21 rows re-normalized LIVE** (NULL
  30-day window + re-reconcile, idempotent); `/v1/calendar/recent-actuals` →
  GDP 1.6%/cons 2.0% mag −20%, Core PCE 0.2%/0.3% mag −33%, `parse_failures:[]`;
  frontend RecentActualsPanel renders clean (playwright).
- **RANGE (`forecast_min/max`)** : web research (researcher subagent) confirmed
  **no free analyst-range source exists** (FXStreet paid, Investing point-only +
  ToS-hostile, TradingEconomics paid, SPF quarterly/5-var). Kept honestly
  **"unavailable"** (Voie D + zéro-fake) — did NOT fabricate a synthetic range.

### 2. `a3fee0c` feat(api): GET /v1/london-session/{asset} — RANKÉ #2 backend

- Exposed the §6.2 London-morning read (computed in `london_session.py`, only fed
  to the Pass-2 prompt before). NEW `load_london_session()` — a thin async DB
  loader shared by the data_pool renderer AND the endpoint (single
  `polygon_intraday` fetch, mirror of `previous_session_origin_zone`). Endpoint
  mirrors `/v1/origin-zone` (404 honest absence, `Cache-Control: private no-store`,
  frozen `extra=forbid` Pydantic, `practitioner_stamp`). Registered in
  `routers/__init__.py` + `main.py`.
- **Verified** : 14 tests (6 compute + 8 router/loader); deployed; live EUR_USD
  200 (Fri 1.16530→1.16427 baissière, range_ratio 1.68× active, 240 bars),
  GBP/XAU/SPX 200, **NAS100 404 honest** (thin equity-index London window).

### 3. `651c9e3` feat(web2): <LondonSessionPanel> — RANKÉ #2 frontend

- NEW `apps/web2/components/briefing/LondonSessionPanel.tsx` + `getLondonSession`
  - `LondonSessionData` in `lib/api.ts` + mounted on `/briefing/[asset]` as a
    "Séance de Londres" section (between Taux & Fed and Corrélations) + registered
    in `BriefingSectionNav`. SSR-prop thin-view (mirror StirPanel). Renders OHLC,
    net move + direction (bull/bear/muted), open→close range-track viz, activity
    tag (vs 5-day baseline), is_today freshness, coach text, ADR-017 footer. Honest
    empty state on 404.
- **Verified** : tsc 0, eslint 0, prettier; web2 build OK; deployed; playwright
  DOM + screenshot confirm the rendered panel (EUR baissière 1.7× active 240min).

### 4. `45c5a4b` fix(economic-events): correct Core PPI + Avg Hourly Earnings FRED series

- Audit of the FF→FRED title map (prompted by #1) found **2 more wrong-series
  bugs** producing materially wrong values : "Core PPI m/m" substring-matched
  "ppi m/m" → headline `PPIFID` (Core PPI showed the headline 1.4%) → fixed to
  **`PPIFES`** ("Final Demand less foods & energy", FRED-verified) ahead of the
  headline fragment + added headline PPI y/y. "Average Hourly Earnings" → `AHETPI`
  (production/nonsupervisory) but FF reports the **all-employees** series
  **`CES0500000003`** (0.16% vs AHETPI 0.34% on the same print) → fixed.
- **Verified** : 56 tests; deployed; re-reconciled live → Core PPI **1.0%** vs
  headline PPI **1.4%** (now distinct), AHE **0.2%**.

### 5. `ca08f56` fix(web2): suppress "temps réel" claim when markets are closed (weekend honesty)

- The `TodaySessionPulse` "Lecture en temps réel · recalibrée chaque session"
  subtitle was gated on card-freshness only → a FRESH weekend-cron card still
  claimed "temps réel" while the apex banner + NyWindowBadge said "Marchés fermés
  · week-end" (the 2026-05-29 "contradictions partout" class). NEW pure
  `freshnessSubtitleVariant(cardGeneratedAt, marketClosed)` in `lib/freshness.ts`
  (precedence absent → market_closed → stale → live); `FreshnessSubtitle` derives
  `marketClosed` from `getNyWindowStatus` (same source as the badge above it, so
  they never contradict): weekend closes all assets, a US holiday closes only
  equity (SPX/NAS) since FX/XAU keep trading.
- **Verified** : tsc 0, eslint 0, 14 vitest (5 new); deployed; **live Saturday** →
  subtitle = "Week-end · marchés fermés · dernière lecture il y a 2 h · recalibrée
  à la réouverture", "lecture en temps réel" absent.
- NOTE : the apex `<SessionStatus>` banner + `NyWindowBadge` ALREADY handled
  weekends well (backend `SessionStatusOut.state="weekend"`/`market_closed_fx`) —
  only the tagline contradicted; now coherent. (Verified-first → no over-build.)

---

## Decisions taken in autonomy (with rationale)

- **#3 Couche-2 STAYS Haiku** (ADR-023). Switching the 5 NLP agents to Opus runs
  them through the single Win11 runner subprocess = exactly the contention that
  caused the 2026-05-29 outage. Durability 24/7 > marginal quality on a secondary
  layer. Briefings (what Eliot reads) are already Opus 4.8.
- **#1 range = honest "unavailable"** (not a fabricated synthetic band) — aligned
  with the §8 zéro-fake stance. A clearly-labeled synthetic historical-dispersion
  band was offered as an option, not built.
- **Weekend cards not regenerated** — the panels read live (already correct); the
  Monday cron refreshes the frozen narratives.

## Dev-environment notes (this worktree — reversible, gitignored, NOT deployed)

- The worktree had no `.venv` / `node_modules` (gitignored). Created **3 directory
  junctions** → the main checkout (`apps/api/.venv`, `node_modules`,
  `apps/web2/node_modules`) so pre-commit hooks + tsc/eslint/vitest run here. The
  deploy rsync excludes `node_modules`, so the junctions don't affect prod.
- The main venv's editable `.pth` points to the **amazing-heyrovsky** worktree, so
  local pytest uses a `PYTHONPATH=<naughty>/apps/api/src;…packages/…` override
  (proven). Deploy scripts are path-relative (deploy the cwd worktree's source).

## Owner gotchas honored (pickup directives a–f)

- (a) did NOT `git checkout` in the live runner checkout (`D:\Ichor\apps\claude-runner`) ;
  (b) SSH to Hetzner with retries (lesson #24 instability) ; (c) the PR CI reds are
  PRE-EXISTING (orphan `packages/ui` lockfile + `apps/claude-runner` `effort="ultra"`
  test + Lighthouse/axe/CodeQL infra), NOT from this session ; (d) did NOT touch the
  EIA+FRED keys ("laisse tomber, on garde") ; (e) web2 redeploy kept the trycloudflare
  URL stable ; (f) wrote to `auto_session_resume.md`, NOT the over-cap `MEMORY.md`.

## Re-verification at session close (RE-checked, not asserted)

- **git** : the 5 work commits `3528aa7..ca08f56` + this session-log commit, all
  pushed to `origin/claude/ichor-s6-consensus`, working tree clean (only untracked
  screenshots).
- **tests** : FULL apps/api suite RE-RUN at close = **2982 passed / 34 skipped
  (DB-smoke, no local DB) / 0 failed** (12m02s) — no regression from the 5 changes
  (baseline 2952 → +30 new tests). FULL web2 vitest = **501 passed / 0 fail** (20
  files). (In-session spot-checks: backend touched-174, freshness-14.)
- **live** (Hetzner) : `/healthz`, `/v1/london-session/EUR_USD`, `/v1/stir`,
  public `/briefing` all **200**; `/v1/calendar/recent-actuals` shows the corrected
  values (GDP 1.6%, Core PPI 1.0%, AHE 0.2%); the weekend subtitle is live.

## Remaining / next (ranked)

- **#5** ECB/BoE implied rate paths (the #1 macro driver for EUR/USD + GBP/USD) —
  needs a free OIS source; verify feasibility first (likely the same "no free
  source" wall as the consensus range). · Phase-4 (real-time news push, London
  panel 60s polling like origin_zone). · weekend-card relevance deeper (should the
  cron generate ny_mid/ny_close cards on weekends at all — design question).
- **#4** ADR-108 formal docs : the 5 prior-session arch additions (coherence gate,
  STIR, FedWatch, reactivity, London read) + this session's (actuals-normalization,
  london-session-endpoint, FF→FRED mapping corrections, weekend-honesty gate).
- **Open the PR** to `main` for the session's commits (Eliot merges).

## Honest gaps / notes

- Only the **weekend** variant of the freshness-subtitle was verified LIVE (it's
  Saturday); the weekday live/stale variants are unit-tested + tsc only.
- EIA + FRED API keys are exposed in logs (pre-existing) → rotate (Eliot manual).
- "Core PPI y/y" / "PPI y/y" mappings were added but no such row was in the live
  30-day window to reconcile yet (ready for when FF publishes them).
