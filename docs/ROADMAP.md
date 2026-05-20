# Ichor — Forward-looking ROADMAP

> **Canonical, always-current**. The authoritative forward-looking plan : where Ichor is, where it's going, what's next, why. Refreshed each round at SESSION_LOG close. The dated archive docs (`ROADMAP_2026-05-06.md`, `ROADMAP_PHASE_F_12_MOTEURS.md`) remain as strategic-vision references but are NOT the current-state source.
>
> **Audience** : Eliot for the human roadmap view + Claude future sessions for explicit-plan-driven execution (replaces the implicit menu in paste-prompt).
>
> **Discipline** : every round closes with a 1-line §1 refresh ; deeper §3-§5 refresh only when a round actually changes the plan (e.g., r124 = this initial creation, r125+ = appended §3 promotion of the next default once executed).
>
> **Sync** : 2026-05-20 r126-close (HEAD bumps to +1 per this commit ; was `3d38cbc` at r125-close = 91 ahead origin/main `1909ca0` ; r126 commit will land 92 ahead, re-verified at push). Living-document discipline (per r124 lesson #21) — each round-close updates §1 sync + §3 promotion ; deeper §4-§6 refresh only when the plan shifts. **r126 alembic head bump 0050 → 0051 (`tempo_thresholds`) — the FIRST migration of the post-r110 stack ; backend deploy DEFERRED to r127 per split-atom doctrine.**

---

## §1 — Current state (r126-close, 2026-05-20)

### Shipped capabilities (the product TODAY)

- **5 priority assets** covered : EUR/USD, GBP/USD, XAU/USD, S&P 500 (SPX500), Nasdaq (NAS100) — per ADR-083 D1 6-card universe.
- **8 layers per asset** : fundamental, macro, géopolitique, corrélations, volume, sentiment, market actors, raisoned POV — EXCEPT analyse technique (Eliot on TradingView).
- **4-pass session-card pipeline** : regime → asset → stress → invalidation, persisted to `session_card_audit`. 4 windows/day × 8 assets = 32 cards/day target. Cap 95% conviction (ADR-017/022).
- **Pass-6 scenarios** : 7-bucket outcome probability distribution per card (ADR-085).
- **Frontend `/briefing/[asset]`** (Next.js 15.5 + React 19 + Tailwind v4 + motion 12, Fraunces serif + glassmorphism) : 14+ premium panels covering the 8 layers — BriefingHeader Sparklines + **TodaySessionPulse (r123)** + VerdictBanner + KeyLevelsPanel + NarrativeBlocks + ScenariosPanel + EconomicCalendarPanel + EventSurpriseGauge + GeopoliticsPanel + SentimentPanel + InstitutionalPositioningPanel + NewsPanel + VolumePanel + HourlyVolReport + CorrelationsStrip + PocketSkillBadge + DataIntegrityBadge + ADR-104 r96 degraded-data badge.
- **Phase D auto-improvement loops (W113-W118 + W116c + W117a)** — the LIVING ENTITY layer SHIPPED + AUTONOMOUSLY OPERATING : `auto_improvement_log` immutable trigger / ADWIN concept-drift / Vovk-Zhdanov aggregator (JMLR 2009) / Ahmadian Penalized Brier Score λ=2 / W116c LLM addendum generator (canonical Voie D entry, ADR-017 regex defense-in-depth) / DSPy 3.2 `ClaudeRunnerLM(BaseLM)` Voie D-wrapper. Observable via `/v1/phase-d/*` read-only endpoints. **Eliot's "Ichor doit s'améliorer en autonomie" is INFRASTRUCTURE-COMPLETE — the FRONTEND `/learn` consumer is gel'd per CLAUDE.md rule 4 (Eliot decision pending).**
- **Voie D** : ZERO Anthropic API spend ; all LLM calls go through local Win11 `claude-runner` subprocess (Max 20x flat). Held **38 rounds** as of r123.
- **Production deployment** : Hetzner SSH alias `ichor-hetzner`, 30+ ichor-\*.timer systemd units active, FastAPI + Alembic **0050 deployed** + **0051 landed code-only, deploy deferred to r127** + SQLAlchemy 2 async + TimescaleDB + Postgres-AGE. Cloudflare quick tunnel LIVE URL stable `https://latino-superintendent-restoration-dealtime.trycloudflare.com`. **2198+ pytest suite green (was 1900+) — 41 r126 tests added, 0 regression**.

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

## §3 — Immediate next (r127)

**r126 EXECUTED & SHIPPED (2026-05-20)** : per-asset tempo threshold AUTO-RECALIBRATION backend infrastructure — migration 0051 `tempo_thresholds` (historical-trace shape, 6 CHECK constraints, compound desc index) + ORM `TempoThreshold` + service `recalibrate_tempo_thresholds(...)` (Paris-day SQL aggregation + stdlib percentile + per-asset flush + all-or-nothing commit) + CLI `run_tempo_recalibration.py` (feature-flag-gated + --dry-run + --window-days + --assets) + Hetzner weekly Sunday 04:00 Paris cron + API `GET /v1/tempo-thresholds` + `GET /v1/tempo-thresholds/{asset}` (with `Cache-Control: public, max-age=300, stale-while-revalidate=900`) + 41 tests (35 base + 6 review-driven : MF-1 clamp regression + MF-2 overflow sanity + Y-2 SQL drift guard + Y-3 percentile drift guard + 2× cache-control header pin). Reviews 3 parallel : ichor-trader GREEN/MERGE 0 RED + code-reviewer MUST-FIX × 2 APPLIED + 5 YELLOW APPLIED + api-designer YELLOW-2 Cache-Control CONCORDANT-APPLIED + YELLOW-1 envelope FLAGGED-NOT-FIX with reason. pytest 2198 passed / 0 regression. Frontend wire SPLIT to r127 (doctrine-#2 strict scope — backend ships, cron runs, data accumulates, then r127 wires the consumer). The Mission centrale Axis-7 (auto-amélioration) is PARTIALLY EXTENDED — calibration is self-recalibrating, consumer view lands r127. See `docs/SESSION_LOG_2026-05-20-r126-EXECUTION.md` for atom detail + ADR-099 §Impl(r126) for the full reviews + verification record.

**r127 top-default candidate** : **frontend wire of `/v1/tempo-thresholds` into `<TodaySessionPulse>`** — add `apps/web2/lib/data/tempoThresholds.ts` fetcher + extend `derivePulse(bars, hv, ss, asset, thresholdsOverride?)` with optional override + wire `apps/web2/app/briefing/[asset]/page.tsx` Promise.all to await the fetcher + fallback to r125 hardcoded `TEMPO_THRESHOLDS_BY_ASSET` on API error. Includes the Hetzner DEPLOY of the r126 backend (alembic upgrade 0050 → 0051 + register-cron-tempo-recalibration.sh + feature flag flip). Effort M (~half-day) — frontend wire + deploy + Playwright DUAL witness. R59-AUDIT first to confirm honest scope before commit.

**r127 alternatives** (R59-pickable IF frontend-wire+deploy scope is too ambitious for one round) :

- **r126 backend deploy alone** — Hetzner alembic upgrade + cron registration + feature flag flip + smoke verify via `psql` + `journalctl`. XS effort (Eliot manual step, no code change). Lets the cron accumulate 1-2 weeks of data before the frontend wires.
- **Frontend wire WITHOUT deploy** — code-only landed artifact ; the r127 commit lands but the consumer remains on the r125 fallback until the backend deploys in r128. S effort.
- **Revalidate cleanup** (r122 carry) — simplify `/yield-curve` dual revalidate to just `force-dynamic`. XS effort (1-line removal + ADR note).
- **SSG-audit other pages** (r122 lesson #19 backlog) — systematic grep for `await apiGet` without `force-dynamic`.
- **Tempo cross-asset matrix on `/today`** (ROADMAP §4 r128+) — surface all 5 priority assets' tempo at once. M effort.

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
