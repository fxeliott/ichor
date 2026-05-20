# Ichor — Forward-looking ROADMAP

> **Canonical, always-current**. The authoritative forward-looking plan : where Ichor is, where it's going, what's next, why. Refreshed each round at SESSION_LOG close. The dated archive docs (`ROADMAP_2026-05-06.md`, `ROADMAP_PHASE_F_12_MOTEURS.md`) remain as strategic-vision references but are NOT the current-state source.
>
> **Audience** : Eliot for the human roadmap view + Claude future sessions for explicit-plan-driven execution (replaces the implicit menu in paste-prompt).
>
> **Discipline** : every round closes with a 1-line §1 refresh ; deeper §3-§5 refresh only when a round actually changes the plan (e.g., r124 = this initial creation, r125+ = appended §3 promotion of the next default once executed).
>
> **Sync** : 2026-05-20 r130-close (HEAD bumps to +1 per this commit ; was `adfb37e` at r129-close = 95 ahead origin/main `1909ca0` ; r130 commit will land 96 ahead, re-verified at push). Living-document discipline (per r124 lesson #21) — each round-close updates §1 sync + §3 promotion ; deeper §4-§6 refresh only when the plan shifts. **🎯 r130 PIVOT post Eliot prompt-cadre re-engagement : after 4 rounds on axis-7 (r126→r129 = MATURE), r130 re-prioritizes onto axis-4 (anticipation par profondeur) with `<PolymarketImpactPanel>` shipped on `/briefing/[asset]`. The Polymarket backend service `polymarket_impact.py` LIVE since r74 (8 themes clusterisés feeding LLM data-pool) is now SURFACED directly to Eliot's eye via per-asset directional tone label + diverging bar (NO numeric overclaim per trader MUST-FIX-1) + provenance staleness banner mirroring r129 doctrine #11. Mission axis 8 (manipulation watch) gets infrastructure precondition ; Δ-YES wire deferred r131+. Lesson #27 codified : 4-rounds-on-single-axis triggers FULL-matrix re-evaluation.**

---

## §1 — Current state (r131-close, 2026-05-20)

### Shipped capabilities (the product TODAY)

- **5 priority assets** covered : EUR/USD, GBP/USD, XAU/USD, S&P 500 (SPX500), Nasdaq (NAS100) — per ADR-083 D1 6-card universe.
- **8 layers per asset** : fundamental, macro, géopolitique, corrélations, volume, sentiment, market actors, raisoned POV — EXCEPT analyse technique (Eliot on TradingView).
- **4-pass session-card pipeline** : regime → asset → stress → invalidation, persisted to `session_card_audit`. 4 windows/day × 8 assets = 32 cards/day target. Cap 95% conviction (ADR-017/022).
- **Pass-6 scenarios** : 7-bucket outcome probability distribution per card (ADR-085).
- **Frontend `/briefing/[asset]`** (Next.js 15.5 + React 19 + Tailwind v4 + motion 12, Fraunces serif + glassmorphism) : 14+ premium panels covering the 8 layers — BriefingHeader Sparklines + **TodaySessionPulse (r123)** + VerdictBanner + KeyLevelsPanel + NarrativeBlocks + ScenariosPanel + EconomicCalendarPanel + EventSurpriseGauge + GeopoliticsPanel + SentimentPanel + InstitutionalPositioningPanel + NewsPanel + VolumePanel + HourlyVolReport + CorrelationsStrip + PocketSkillBadge + DataIntegrityBadge + ADR-104 r96 degraded-data badge.
- **Phase D auto-improvement loops (W113-W118 + W116c + W117a)** — the LIVING ENTITY layer SHIPPED + AUTONOMOUSLY OPERATING : `auto_improvement_log` immutable trigger / ADWIN concept-drift / Vovk-Zhdanov aggregator (JMLR 2009) / Ahmadian Penalized Brier Score λ=2 / W116c LLM addendum generator (canonical Voie D entry, ADR-017 regex defense-in-depth) / DSPy 3.2 `ClaudeRunnerLM(BaseLM)` Voie D-wrapper. Observable via `/v1/phase-d/*` read-only endpoints. **Eliot's "Ichor doit s'améliorer en autonomie" is INFRASTRUCTURE-COMPLETE — the FRONTEND `/learn` consumer is gel'd per CLAUDE.md rule 4 (Eliot decision pending).**
- **Voie D** : ZERO Anthropic API spend ; all LLM calls go through local Win11 `claude-runner` subprocess (Max 20x flat). Held **38 rounds** as of r123.
- **Production deployment** : Hetzner SSH alias `ichor-hetzner`, **31+ ichor-\*.timer systemd units active** (r128 added `ichor-tempo-recalibration.timer`), FastAPI + **Alembic 0051 LIVE** + SQLAlchemy 2 async + TimescaleDB + Postgres-AGE. Cloudflare quick tunnel LIVE URL stable `https://latino-superintendent-restoration-dealtime.trycloudflare.com`. **2198+ pytest apps/api suite green ; web2 vitest 8 files / 181 tests pass (was 177 r127 + 4 r129 new, 0 regression)**. **`tempo_thresholds` table LIVE with 5 rows** (EUR/GBP/XAU/SPX/NAS, computed 2026-05-20 16:05 UTC, 90d window) ; **`/v1/tempo-thresholds` endpoint LIVE with `Cache-Control: public, max-age=300, stale-while-revalidate=900`** ; **r129 staleness banner LIVE in `<TodaySessionPulse>` panel footer** ("Calibration des seuils · aujourd'hui · n=16 · fenêtre 90 j").

### Doctrine ledger (the operational invariants — pointers, not duplications)

- **ADR-017** : no BUY/SELL/orders/personalized sizing. CI-guarded by ADR-081 `test_invariants_ichor.py`. Vaut frontend (doctrine #11).
- **Voie D** : zero Anthropic API SDK consumption. ADR-009.
- **ADR-023** : Couche-2 LLM agents on Claude Haiku low (Sonnet medium hits Cloudflare 100s edge timeout).
- **ADR-099 §D-4 boundary of autonomy** : Claude = local/reversible/additive ; Eliot = irreversible/shared-state/secrets.
- **doctrine-#9 coord-math ledger** (always-current at r123) : `{VolumePanel r105 · ScenariosPanel r108 · confluence-history r109 · I3 r111 · HeatmapBars r116 · CurveChart r118}` — UNCHANGED by r119-r123 (r120 EXTRACT-to-shared + r121 additive-prop + r122 render-mode + r123 NEW additive consumer are all doctrine-#8 "more coverage", NOT coord-math changes).
- **r122 lesson #19** : `next build` flag `○ Static` vs `ƒ Dynamic` IS the load-bearing signal for SSG bake-in defects.
- **r123 lesson #20** : when Eliot refreshes the prompt-cadre with a new PRODUCT-LEVEL principle, R59-AUDIT current state vs the new principle via focused sub-agent BEFORE picking the next code increment.

---

## §2 — Mission centrale d'Ichor (the long-game vision)

**Source : Eliot's 2026-05-20-morning + 2026-05-20-afternoon prompt-cadre refreshes.**

Ichor's mission is to produce **continuous, ultra-deep, real-time-reactive macro/FX analyses calibrated specifically for taking position-trades in the NY 13h-16h Paris window**. The system must approach "anticipation lucide" via **maximum-depth multi-dimensional cross-analysis** — not prediction, but a probability-weighted forward read so deep + so well-grounded that it approaches what's likely to happen.

### Mission centrale axes

1. **Daily-reset semantic** : reset complet quotidien on every briefing render. No carry-over from yesterday's analysis. Each day = a new equation. (r123 closed Axis-1 here — `<TodaySessionPulse>` filters by Paris-date boundary on the latest bar.)
2. **London-en-cours live calibration** : the briefing must surface what London is doing RIGHT NOW (mouvements, niveaux, réactions, comportement réel). (r123 closed this — `london_range_bp` + tempo cross-reference visible LIVE.)
3. **NY 13h-16h window specificity** : analyses calibrated for the morning NY session (07:00-10:00 ET). The user takes positions in this window. (r123 placement = BriefingHeader → TodaySessionPulse → VerdictBanner mirrors the temporal reading flow ; the NY pre-session briefing window already fires at cron 13:00 Paris.)
4. **Anticipation lucide par profondeur** : push every dimension to maximum depth so cross-analysis approaches probable outcomes. (r123 partial — tempo cross-references 30-day p75 baseline ; deeper synthesis = future Polymarket × DXY × macro aggregate panel.)
5. **Réactivité temps réel** : when events tombent/sortent/sont publiés, Ichor must react IMMEDIATELY, alert, analyze, update. (PARTIAL today — `<EventSurpriseGauge>` r89 + `<EconomicCalendarPanel>` show upcoming events but don't AUTO-update on event-fire ; the 4-pass cron-fires at fixed windows.)
6. **Conviction level mesuré + justifié** : a clear, mesured, justified degree of certainty per card. (PARTIAL — `card.conviction_pct ∈ [0, 95]` exists ; per-axis confidence decomposition is the deeper ambition.)
7. **Apprentissage et auto-amélioration en autonomie** : Ichor must understand itself, see its errors, learn lessons, get better each day. (INFRASTRUCTURE COMPLETE via Phase D loops W113-W118 ; FRONTEND `/learn` consumer GEL'D per rule 4, Eliot decision pending to ungel.)
8. **Pre-momentum manipulation watch** : Ichor must say whether manipulation is expected BEFORE the NY momentum. (FUTURE — would be a synthesis between GEX dealer flows + Polymarket positioning + retail extreme tilts ; not directly surfaced today.)

### Anti-features (definitive boundaries — pointers to ROADMAP_2026-05-06.md)

ZERO of these are ever shipped in Ichor :

- Pas de BUY/SELL signals (ADR-017 immutable)
- Pas de TP/SL/zone d'entrée (Eliot fait sur TradingView)
- Pas de Order block / SMC overlay
- Pas de pédagogie / glossaire séparé / mode débutant-expert (clarté = par STRUCTURE de l'information, pas par encart méthodologie)
- Pas de coaching trader (track trades / pattern erreurs / discipline / mood / drawdown manager / performance attribution personnelle)
- Pas d'auto-trading bot / copy trading / EA
- Pas d'anonymous community signals

See `docs/ROADMAP_2026-05-06.md` for the original 4-layer architecture (DATA FOUNDATION / ANALYTICS / DELIVERY UX / LIVING ENTITY) + the verbatim anti-features rationale. See `docs/ROADMAP_PHASE_F_12_MOTEURS.md` for the 12-engine academic-framework blueprint.

---

## §3 — Immediate next (r132)

**r131 EXECUTED & SHIPPED (2026-05-20)** : Polymarket Δ-YES velocity primitive on `<PolymarketImpactPanel>` — closes r130 trader MUST-FIX-2 deferred Δ-YES wire. NEW backend SQL helper (tight 22-26h window post-trader MUST-FIX-1) + MarketHit/Pydantic/TS schema extension with `yes_24h_ago` + `yes_velocity_pp` + `yes_24h_ago_at` (trader MUST-FIX-2 dual-stamp) + frontend badge with tone escalation (subtle / rapid / **major** — renamed from "manipulation possible" per trader CRITICAL-1 + ui-designer + a11y CONCORDANT, causal-claim ADR-017 leakage avoided). 3 parallel reviewers (trader + ui-designer + a11y) — 3 CONCORDANT MUST-FIX + 2 STRONG single-reviewer trader R28 MUST-FIX ALL applied same-commit. Build gate : pytest 20/20 + tsc 0 + eslint 0 + vitest 9f/199 + next build OK. Deploy LIVE backend (scp + restart, /healthz=200, endpoint schema verified) + frontend (redeploy-web2.sh, local=200 public=200). Playwright DUAL witness GREEN : XAU velocity badge "+0,0 pp / 24 h" LIVE on China-Taiwan top market (subtle tone, no label, exactly designed) + Oil/OPEC silent (no 24h history, honest absence) + EUR empty-second-branch with role=status. **Lesson #28 codified** : causal labels ("manipulation", "anomalie", "signal") are opt-IN per round with explicit evidence-stacking, NOT opt-OUT defaults. **Mission axis-8 +1 LEVEL PARTIAL** : velocity primitive ships ; full closure (volume-anomaly + cross-venue Kalshi divergence + order-book depth) deferred r132+. See `docs/SESSION_LOG_2026-05-20-r131-EXECUTION.md` + ADR-099 §Impl(r131).

**r132 binding default candidates** (R59-AUDIT first to pick) :

1. **Axis-8 closure completion** — cross-venue Kalshi divergence wire OR volume-anomaly z-score (closes axis 8 fully ; r131 only velocity primitive). Effort M-L.
2. **NY 13-16h window UI marker** (deferred r130/r131) — explicit "T-{N}h pré-NY" badge on `<TodaySessionPulse>`. Effort S. CLOSES axis 3.
3. **Conviction decomposition per-axe** (deferred r130/r131) — `conviction_pct` decomposed into (macro + flux + positioning + sentiment) sub-scores. Effort M-L. CLOSES axis 6.
4. **Threshold drift detector cron** (deferred r129+r130+r131) — axis-7 ALERT-stage. Effort M.
5. **Polymarket threshold recalibration cron** — mirror tempo r126 pattern : weekly cron empirically calibrates 5pp/10pp thresholds from per-market-class distribution. Effort M.
6. **AUD_USD revival** — alternative China money supply LIVE series since MYAGM1CNM189N dead. Effort M-L.

## §3 — Previous immediate next (r131, EXECUTED above)

**r130 EXECUTED & SHIPPED (2026-05-20)** : `<PolymarketImpactPanel>` on `/briefing/[asset]` — closes prompt-cadre clause _"Intégration des données Polymarket, exploitées pleinement"_. NEW lib/polymarketImpact.ts + NEW PolymarketImpactPanel.tsx + page.tsx wire + 12 vitest tests. Reviews 4 parallel : 3 CONCORDANT MUST-FIX (aria-labelledby id collision + generated_at provenance + role="img" over-announce) + 2 STRONG single-reviewer MUST-FIX (trader numeric overclaim → drop visible scalar ; code-reviewer NF_SIGNED near-zero contradiction → POLYMARKET_NEUTRAL_THRESHOLD = 0.005). Build gate : tsc 0 / eslint 0 / vitest 9f/194 pass / next build OK. Deploy LIVE on CF tunnel. Playwright DUAL witness GREEN : EUR_USD empty-second-branch ("Polymarket inactif" — honest, FX rarely Polymarket-priced) ; XAU_USD 2 themes populated (China-Taiwan + Oil/OPEC, both "baissier pour XAU/USD"). **Lesson #27 codified** : 4 rounds on single axis (axis-7 r126→r129) triggers FULL-matrix re-evaluation, user-facing high-leverage axes take priority over infrastructure-completion. axis 4 anticipation par profondeur +1 LEVEL ; axis 8 manipulation watch partial INFRA (Δ-YES wire deferred r131). See `docs/SESSION_LOG_2026-05-20-r130-EXECUTION.md` + ADR-099 §Impl(r130).

**r131 binding default candidates** (R59-AUDIT first to pick) :

1. **Polymarket Δ-YES wire + manipulation watch completion** — adds velocity field to `polymarket_impact.py` service + surfaces ΔYES on the r130 panel. Effort M. CLOSES axis 8 fully (currently r130 only partial infra).
2. **NY 13-16h window UI marker** — explicit "T-2h pré-NY" badge on `<TodaySessionPulse>` + briefing context. Effort S. CLOSES axis 3.
3. **Conviction decomposition per-axis** — `conviction_pct` decomposed into (macro + flux + positioning + sentiment) sub-scores with visible breakdown. Effort M-L. CLOSES axis 6.
4. **Threshold drift detector cron** (deferred from r129) — axis-7 ALERT-stage. Effort M.
5. **AUD_USD revival** — alternative China money supply LIVE series. Effort M-L.

## §3 — Previous immediate next (r130, EXECUTED above)

**r129 EXECUTED & SHIPPED (2026-05-20)** : ADR-104 data-honesty staleness banner on `<TodaySessionPulse>` panel footer — closes r127 trader NIT + adds the 5th stage (SEE) to the Mission centrale Axis-7 auto-improvement loop. ~120 LOC + 5 new vitest cases. `getTempoThresholds()` envelope reshape `{thresholds, metadata}` + `derivePulse(..., thresholdsMetadata?)` 6th param + `tempo_metadata: TempoMetadata | null` on `SessionPulse` + `formatCalibrationAge` helper + banner in panel footer. Reviews 4 parallel : trader GREEN/MERGE + ui-designer NEEDS-FIX→MERGE post-apply (size + placement + prose-mono) + a11y 0 MUST-FIX→MERGE (drop aria-label + size) + code-reviewer 0 MUST-FIX (drop aria-label + extract const). Concordance applied : size text-[10px]→text-[11px], aria-label dropped (override-on-`<p>`-ignored per ARIA 1.2), placement Tempo-tile→panel-footer (provenance-with-provenance STRONG single-reviewer). 2 lessons codified : #25 (UI taxonomy is single-discipline domain — STRONG single-reviewer placement applies even without concordance) ; #26 (post-resume git-state R59 = capture deployed reality, no re-deploy). Build gate : tsc 0 / eslint 0 / vitest 8f/181 pass / next build OK. Deploy LIVE on CF tunnel. Playwright TRIPLE witness GREEN (EUR + GBP + XAU banner LIVE). See `docs/SESSION_LOG_2026-05-20-r129-EXECUTION.md` + ADR-099 §Impl(r129).

**Mission centrale Axis-7 = FULLY OBSERVABLE** : measure → store → consume → **SEE** → recalibrate. The 5-stage chain is LIVE on the user surface.

**r130 binding default candidates** (R59-AUDIT first to pick) :

1. **Threshold drift detector cron** — weekly cron comparing this-week thresholds against last-week's, structlog alert + `auto_improvement_log` row on >N% drift. New cron + ALTER `auto_improvement_log.loop_kind` CHECK constraint to add `tempo_drift`. Effort M. Closes the Axis-7 loop with the **alert** stage (currently silent if cron stops firing).
2. **Stale-amber + degraded-sample tone escalation** on r129 banner — `days >= 7` → `--color-warn` amber tint ; `sample_size < window_days * 0.5` → tone shift. Closes the r129 ui-designer deferred missing-states. Effort S.
3. **Tempo cross-asset matrix on `/today`** — surface all 5 priority assets' current tempo + thresholds at once. Effort M.
4. **AUD_USD revival** — alternative China money supply LIVE series since MYAGM1CNM189N still dead per FRED. Effort M-L.
5. **Polymarket × DXY synthesis panel** — Mission Axis-4 deepening from r123 audit. Effort M.

## §3 — Previous immediate next (r129, EXECUTED above)

**r128 EXECUTED & SHIPPED (2026-05-20)** : Hetzner production deploy of the r126+r127 stack + Playwright DUAL witness GREEN. **Mission centrale Axis-7 FULLY ACTIVATED on prod** — auto-recalibration cron LIVE (next Sun 2026-05-24 04:01 CEST), `tempo_thresholds` table has 5 rows after manual first-run (EUR/GBP/XAU/SPX/NAS, 90d window, n=8-16), `/v1/tempo-thresholds` LIVE with Cache-Control header, frontend wire LIVE on CF tunnel showing API-fed labels. Empirical drift from r125 60d to r128 90d : EUR/GBP/XAU +0-22bp on higher percentiles (regime shift across the 30 extra days), SPX/NAS ~0 (stable). **Transparent-on-stable-calibration EMPIRICALLY confirmed** : EUR 54bp + XAU 221bp both render "tendance" label LIVE — same as r125 hardcoded would produce (within-bracket dispersion), proving the wire works invisibly correctly. **Lesson #24 codified** : SSH-unstable mid-tar → pivot to file-by-file scp with `ServerAliveInterval=5`. The r126+r127+r128 3-round arc is the **first end-to-end auto-improvement loop VISIBLE on the user surface** : measure → store → consume → recalibrate. See `docs/SESSION_LOG_2026-05-20-r128-EXECUTION.md` + ADR-099 §Impl(r128).

**r129 binding default candidates** (R59-AUDIT first to pick) :

1. **ADR-104 data-honesty staleness banner** on `<TodaySessionPulse>` — re-plumb `getTempoThresholds()` to preserve `computed_at`/`sample_size`/`window_days` (currently dropped in flatten per r127 trader NIT) + add `<small>` line on the Pulse panel : "recalibré il y a N jours, n=K, 90j window". Effort S-M. Closes the r127 banner-hook NIT.
2. **Tempo drift detector** — weekly cron comparing this-week thresholds to last-week, structlog alert on >N% drift. Effort M (new cron + auto_improvement_log loop_kind extension).
3. **Tempo cross-asset matrix on `/today`** — surface all 5 priority assets' tempo + thresholds at once. Effort M (new component + route addition).
4. **AUD_USD revival** — alternative China money supply LIVE series since MYAGM1CNM189N is dead (FRED). Effort M-L (researcher + collector + integration).
5. **Polymarket × DXY synthesis panel** — Mission Axis-4 gap from r123 audit. Effort M.

**r127 EXECUTED & SHIPPED (2026-05-20)** : frontend WIRE of `/v1/tempo-thresholds` API → `<TodaySessionPulse>` (Mission centrale Axis-7 consumer-view completion). +254 / -9 LOC across 4 files. NEW exported `TempoThresholds` interface from `sessionPulse.ts` + new `derivePulse(..., asset, thresholdsOverride?)` 5th param + `tempoLabelByAsset` 3-layer lookup chain (override → r125 hardcoded → DEFAULT). NEW exported `TempoThresholdsForAsset` interface from `lib/api.ts` + `getTempoThresholds()` fetcher (300s ISR matches backend Cache-Control max-age 300, transform list→map, null on error/empty, console.info distinguishes cold-state from API-down). Briefing page Promise.all 14 → 15 items + `tempoThresholdsLive ?? undefined` passed to derivePulse. +6 vitest tests (omission-byte-identical / override-applied / empty-fallback / partial-fallback / XAU transparency / drift-guard with `import.meta.url`-resolved paths post MF-1). Reviews 2 parallel (frontend WIRE classe-trigger, NO ui-designer / a11y) : trader GREEN/MERGE 0 RED + 2 single-reviewer YELLOW dissolved + 2 NIT applied ; code-reviewer MF-1 + Y-1 + Y-3 + N-1 APPLIED same-commit + Y-2/Y-5 single-reviewer flag-not-fix + Y-4 calibrated via doctrine #11 ("API-fed ≤5min CDN lag" replaces "LIVE"). Build gate : tsc 0 / eslint 0 / vitest 8f/177 pass / next build OK. **Hetzner deploy DEFERRED to r128 per ADR-099 §D-4 boundary** (production rsync + alembic upgrade + cron register + feature flag flip + Playwright witness = Eliot territory). The wire is dormant-but-safe : on production the `/v1/tempo-thresholds` API returns 404 → fetcher returns null → derivePulse falls back to r125 hardcoded `TEMPO_THRESHOLDS_BY_ASSET` via the 3-layer chain. Lesson #23 codified : Hetzner deploy chain crosses §D-4 even when SSH is authorized (the rsync source + deploy-blue-green trigger live outside `/opt/ichor/`). See `docs/SESSION_LOG_2026-05-20-r127-EXECUTION.md` for atom detail + ADR-099 §Impl(r127).

**r126 EXECUTED & SHIPPED (2026-05-20)** : per-asset tempo threshold AUTO-RECALIBRATION backend infrastructure — migration 0051 `tempo_thresholds` (historical-trace shape, 6 CHECK constraints, compound desc index) + ORM `TempoThreshold` + service `recalibrate_tempo_thresholds(...)` (Paris-day SQL aggregation + stdlib percentile + per-asset flush + all-or-nothing commit) + CLI `run_tempo_recalibration.py` (feature-flag-gated + --dry-run + --window-days + --assets) + Hetzner weekly Sunday 04:00 Paris cron + API `GET /v1/tempo-thresholds` + `GET /v1/tempo-thresholds/{asset}` (with `Cache-Control: public, max-age=300, stale-while-revalidate=900`) + 41 tests (35 base + 6 review-driven : MF-1 clamp regression + MF-2 overflow sanity + Y-2 SQL drift guard + Y-3 percentile drift guard + 2× cache-control header pin). Reviews 3 parallel : ichor-trader GREEN/MERGE 0 RED + code-reviewer MUST-FIX × 2 APPLIED + 5 YELLOW APPLIED + api-designer YELLOW-2 Cache-Control CONCORDANT-APPLIED + YELLOW-1 envelope FLAGGED-NOT-FIX with reason. pytest 2198 passed / 0 regression. Frontend wire SPLIT to r127 (doctrine-#2 strict scope — backend ships, cron runs, data accumulates, then r127 wires the consumer). The Mission centrale Axis-7 (auto-amélioration) is PARTIALLY EXTENDED — calibration is self-recalibrating, consumer view lands r127. See `docs/SESSION_LOG_2026-05-20-r126-EXECUTION.md` for atom detail + ADR-099 §Impl(r126) for the full reviews + verification record.

**r128 top-default candidate** : **Hetzner production deploy of the r126+r127 stack + Playwright DUAL witness**. Steps : (1) GitHub PR merge `claude/friendly-fermi-2fff71` (93 ahead) → `main` ; (2) Hetzner rsync sync of 8 r126 backend files + 4 r127 wire files ; (3) `alembic upgrade head` (0050 → 0051) ; (4) smoke verify `\d tempo_thresholds` ; (5) `register-cron-tempo-recalibration.sh` ; (6) feature flag flip `tempo_recalibration_collector_enabled = true` ; (7) manual first run + verify rows in `tempo_thresholds` ; (8) reload `ichor-api.service` ; (9) `redeploy-web2.sh` ; (10) Playwright DUAL witness EUR + XAU on the CF tunnel verifying network log shows `/v1/tempo-thresholds` 200. Effort M (~half-day). **CROSSES ADR-099 §D-4 BOUNDARY** : requires Eliot-manual step (PR merge) before the autonomous SSH chain. Lesson #23 (r127) codified : Hetzner deploy chain is §D-4 even when SSH is authorized (rsync source lives outside `/opt/ichor/`).

**r128 alternatives** (R59-pickable IF the full deploy chain is too ambitious for one round) :

- **r126 backend deploy alone** — steps 1-7 only (Hetzner alembic + cron + feature flag + first-run verify). XS effort. r129 = frontend deploy + witness.
- **Frontend deploy alone** — land the wire on production FIRST while the cron is still disabled ; the wire stays dormant-but-safe (fallback to r125 hardcoded). XS effort.
- **Revalidate cleanup** (r122 carry) — simplify `/yield-curve` dual revalidate to just `force-dynamic`. XS effort (1-line removal + ADR note).
- **SSG-audit other pages** (r122 lesson #19 backlog) — systematic grep for `await apiGet` without `force-dynamic`.
- **Tempo cross-asset matrix on `/today`** (ROADMAP §4 r129+) — surface all 5 priority assets' tempo at once. M effort.

---

## §4 — Near-term plan (r125-r130 candidates, R59-prioritized)

| #                    | Increment                                                                                                                                                                                                                                                                                                                                                                                            | Effort                               | Mission-centrale axis                         | Status                                   |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------ | --------------------------------------------- | ---------------------------------------- |
| **r125 top-default** | **Per-asset tempo recalibration** (r123 explicit backlog) — offline R53 via Hetzner `psql` to derive per-asset thresholds across the **5 frontend-shipped priority assets** (EUR/USD, GBP/USD, XAU/USD, SPX500, NAS100 ; extends to USDCAD if/when the ADR-083 D1 6th `/briefing/[asset]` route ships), codify `TEMPO_THRESHOLDS_BY_ASSET` const in `lib/sessionPulse.ts`, update tests + docstring. | S (~2-3 hrs)                         | Axis-4 (anticipation lucide depth)            | R59-ready, single round                  |
| r125 alt             | **Revalidate cleanup** (r122 carry) — `/yield-curve/page.tsx` has dual revalidate on a `force-dynamic` page ; simplify to just `force-dynamic`.                                                                                                                                                                                                                                                      | XS (1-line removal + ADR note)       | infra hygiene                                 | R59-ready                                |
| r125 alt             | **SSG-audit other pages** (r122 lesson #19 backlog) — systematic grep for `await apiGet` without `force-dynamic`.                                                                                                                                                                                                                                                                                    | S (grep + 1-2 fix per page if found) | infra hygiene                                 | R59-ready                                |
| r126+                | **Polymarket × DXY synthesis panel** (Axis-4 minor gap from r123 audit) — dedicated themed panel surfacing Polymarket-themed positioning vs DXY divergence.                                                                                                                                                                                                                                          | M (~half-day + reviews)              | Axis-4 (anticipation depth)                   | R59-needed                               |
| r127+                | **Tempo cross-asset matrix on `/today`** — the 5 frontend-shipped priority assets' tempo at once (extends to 6 if USDCAD D1 route ships), separate route addition.                                                                                                                                                                                                                                   | M                                    | Axis-1 + Axis-3 (London-en-cours x NY-window) | R59-needed                               |
| r128+                | **Real-time event reactivity** (Mission centrale Axis-5) — when calendar event fires, briefing page auto-refreshes that section + surfaces the surprise vs consensus. Today : 30s ISR on EconomicCalendarPanel ; would extend to per-event-fire push or aggressive revalidation.                                                                                                                     | M-L                                  | Axis-5                                        | R59-needed (architectural design)        |
| r129+                | **Conviction-level per-axis decomposition** (Mission centrale Axis-6) — surface WHICH axis drives the bias_direction (macro vs sentiment vs positioning vs ...). Today : single conviction_pct.                                                                                                                                                                                                      | L                                    | Axis-6                                        | R59-needed                               |
| r130+                | **Pre-momentum manipulation watch** (Mission centrale Axis-8) — synthesis between GEX dealer flows + Polymarket positioning + retail extreme tilts. Today : KeyLevels has gamma_flip + polymarket_decision separately, NO synthesis.                                                                                                                                                                 | L                                    | Axis-8                                        | R59-needed (deep cross-data integration) |

---

## §5 — Medium-term ambitions (r131-r150)

- **`/learn` ungel decision** (Eliot manual) : the Phase D auto-improvement loops are SHIPPED + AUTONOMOUSLY OPERATING (W113-W118 + Vovk aggregator + Ahmadian PBS + W116c LLM addendum generator + W117a DSPy foundation). The `/v1/phase-d/*` read-only endpoints exist. The frontend `/learn` route consumer is GEL'D per CLAUDE.md rule 4 awaiting Eliot's go-signal. Surface design : (a) `/learn` landing : the Phase D loop diagram + recent skill evolution per pocket ; (b) `/learn/brier-explained` : how Brier scoring works + the Vovk pocket weights ; (c) `/learn/recent-improvements` : the `auto_improvement_log` table surfaced as a timeline ; (d) `/learn/pocket-weights` : the live `brier_aggregator_weights` per pocket. **CRITICAL** : the AUTO-LEARN INFRASTRUCTURE EXISTS — this is the missing CONSUMER VIEW.
- **Typography-reconcile** (r121 ui Important-1 DEFERRED) : `<HourlyVolReport>` glass chrome `<header border-b>` + `<h3 font-serif text-lg>` adoption (ui-designer Important from r121 review). Eliot-preference-dependent (sub-component-identity micro-labels VS full-sibling-identity titled-band). DEFER until Eliot signals preference.
- **T4.2 muted-text recalibration** (a11y hygiene from r121 baseline) — repo-wide token bump. Per r121 a11y review : `text-muted` currently 5.19:1 on glass effective bg, AA-pass for 10px+ small text. Recalibrate to AAA target if Eliot prioritizes a11y depth.
- **Tempo persistence into `session_card_audit`** (Mission centrale Axis-7 — backtest validation) : store `tempo_label` + `tempo_ratio` per card so post-mortem can validate "did breakout-labeled days actually break out". Separate ADR scope.
- **Backend cross-asset matrix v3** — extend ADR-075 6-dim macro state with the r123 tempo dimension across all 5 assets.
- **Pass-2 LLM narrative depth** — extend the per-asset specific section frameworks (currently EUR r32+r34 / XAU r41 / NAS r42 / SPX r43 / JPY r45 / AUD r46) with the r123-style live-calibration dimension.
- **Pass-6 conditional scenarios** — extend the 7-bucket outcome distribution with "conditional on event X firing" sub-distributions (Mission centrale Axis-5 prep).

---

## §6 — Long-term vision (r150+)

- **Full auto-learn loop closure on the frontend** : Eliot can audit Ichor's skill evolution live ; the `/learn` view becomes the visible auto-improvement proof.
- **NY-window depth** : every briefing card calibrated specifically for the 13h-16h Paris position-trade window with explicit pre-momentum / post-event-surprise / manipulation-watch synthesis.
- **Real-time event reactor** : when a Tier-1 calendar event fires (FOMC, NFP, CPI, ECB), the briefing auto-refreshes within 30s with the surprise-vs-consensus + the LLM Pass-2 re-narrate on the fresh data.
- **Per-pocket calibration trajectory** : Eliot sees on `/learn` how Ichor's calibration per (asset, regime, session_type) has evolved over 90 days — empirical skill receipt.

---

## §7 — Permanent doctrines (immutable pointers)

For full text, see :

- `D:\Ichor\.claude\worktrees\friendly-fermi-2fff71\CLAUDE.md` (project memory, sync line)
- `docs/decisions/ADR-017-reset-phase1-living-macro-entity.md` (no BUY/SELL boundary)
- `docs/decisions/ADR-081-doctrinal-invariant-ci-guards.md` (CI guards)
- `docs/decisions/ADR-099-north-star-architecture-and-staged-roadmap.md` (Tier 0-4 north-star + §Impl history)
- `docs/decisions/ADR-104-degraded-inputs-tri-state-data-honesty.md` (data-honesty)
- `docs/decisions/ADR-099` §D-4 boundary of autonomy (Claude local/reversible/additive vs Eliot irreversible/shared/secrets)
- `C:\Users\eliot\.claude\projects\D--Ichor\memory\ichor_r51-r71_doctrinal_patterns.md` (operational doctrines)

Cross-round lessons (#1 forecast≠proof, #2 SHIPPED≠FUNCTIONAL, #3 R59 RESHAPE design, #4 anti-accumulation extract-to-SSOT, #5 RSC-leak discipline, #6 commit single-step prettier 2e-passe, #7 SSH throttle ONE-connection, #8 coverage vs de-accumulation vs extract-to-shared vs additive-prop vs render-mode vs additive-consumer, #9 ADR immuable §Impl APPEND, #10 default-per-round=binding contract, #11 calibrated-honesty, #12 "tu es sûr"=concordance audit, #13 1st signal frais=ground-truth, #14 gate sur shape committée, #15 reconcile snippet-reviewer vs convention, #16 FAIL-OPEN component / FAIL-LOUD SSOT, #17 sous-agents protocole pas FOMO, #18 witness prod-code via api.env+cwd, **#19 `next build` flag for SSG bake-in (r122)**, **#20 POINT FONDAMENTAL refresh → R59-AUDIT first (r123)**).

---

## §8 — R59-DISPROVED paths (honest record of what was discarded + why)

- **r110 R59** : `pathFromHistory` mis-flagged as a coord-scaling consumer-migration — disproved (it's a sign-flip in viewBox units, NOT a scaling site).
- **r113 R59** : "regime-timeline panel" R59-DISPROVED — needs a NEW backend regime-TIME-series projection first (the #1 Pydantic-projection-gap class, backend-first NOT a frontend-only Tier-4 item).
- **r117 R59** : (D) yield-curve CurveChart "needs a NEW log-x primitive" — disproved by r118 (decomposes into a caller `Math.log` domain-transform ∘ existing `linScale`, NO new primitive).
- **r118 R59** : prompt's "truncated y-baseline" framing — disproved (a line chart legitimately uses a zoomed domain, preserved exactly).
- **r120 R59** : prompt's "web2-SSR-seed condition gates any new SSR-fetch surface" — disproved by live code (the `FALLBACK` is `/yield-curve`-route-LOCAL, NOT a universal gate).
- **r121 R59** : (a) prompt's "the standalone would visibly CHANGE" framing — REFINED to "additive prop preserves byte-identical default" ; (b) a11y "glass may drop contrast below threshold" — FALSIFIED by computed math, glass is contrast-POSITIVE Δ +0.25 to +0.81.
- **r122 R59** : sub-agent's "ISR cache TTL is the bug" hypothesis — FALSIFIED by deployed witness, actual mechanism is Next.js SSG bake-in at build time, actual fix is `force-dynamic`.
- **r123 R59** : prompt's "today's tape on briefing requires a new backend" — disproved by R59 audit (Axis-5 data plumbing GREEN — reuses `/v1/market/intraday/{asset}` + `/v1/hourly-volatility/{asset}` + `/v1/calendar/session-status` already in the Promise.all).

---

## §9 — Operational discipline (the always-honored process)

Per CLAUDE.md project memory + `ichor_r51-r71_doctrinal_patterns.md` :

1. R59 inspection-first (verify shapes/math against the LIVE before deriving from them).
2. ADR-before-code (§Impl daté inline APPEND, doctrine #9 — no new ADR per round unless genuinely-new architectural decision).
3. Build gate (tsc + eslint + vitest + next build) BEFORE deploy.
4. Reviews 1-pass (classe-trigger : NEW component visible → ichor-trader R28 + ui-designer + accessibility-reviewer ; pure config → trader-alone). Apply CHAQUE RED/YELLOW concordant 2+ ; flag-not-fix-with-reason single-reviewer items NOT re-scoped.
5. Deploy via `redeploy-web2.sh` (frontend) or `redeploy-api.sh` (backend) — ONE consolidated SSH chain, throttle-aware.
6. Playwright witness on the public CF tunnel for any frontend change ; SSH `curl 127.0.0.1` for backend ; honest scope on pre-existing defects (causation≠proof, r106-a).
7. SESSION_LOG_YYYY-MM-DD-rNN-EXECUTION.md per round + commit single-step (doctrine #6, prettier 2e-passe idempotent) + push + memory updates (pickup v26 line-2 + MEMORY.md header sync + paste-prompt vNN+1).
8. Reconcile ADR Reviews/Verification to MEASURED in the merge commit (0 PENDING, the ichor-trader NO-MERGE-gate).

---

## §10 — Living-document discipline

This ROADMAP.md is **canonical, always-current**. Each round close updates §1 (sync line) + §3 (immediate next promotion) at minimum. Deeper §4-§5 refresh only when the plan genuinely shifts (new prompt-cadre principle, ADR strategic pivot, R59 reveals an unanticipated gap).

The dated archives `ROADMAP_2026-05-06.md` (strategic 4-layer vision) + `ROADMAP_PHASE_F_12_MOTEURS.md` (12-engine academic blueprint) remain as reference but are NOT updated — this canonical doc supersedes them for forward-looking decisions.

ADR-099 §Impl entries remain the immutable retrospective record of each round. SESSION_LOGs remain the per-round execution detail. paste-prompt + pickup + MEMORY.md cover the cross-session resume mechanics. ROADMAP.md is the NEW forward-looking layer, complementary, NOT a duplicate.
