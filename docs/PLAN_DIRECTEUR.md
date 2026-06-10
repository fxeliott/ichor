# PLAN DIRECTEUR ICHOR — Master plan (9-session arc)

> **v4 — 2026-06-10 PM (Session 01/09 second adversarial re-run — prod verified, incident repaired).**
> Supersedes v3 (same day, PR #218/#219), v2 (2026-06-09, uncommitted) and the
> 2026-06-05 v1 (commit `94a64dc`; git keeps all). Canonical 9-session execution
> spine that Sessions 02→09 align to. Distinct from [`ROADMAP.md`](ROADMAP.md)
> (round-based running log). v3 re-verified v2 adversarially at source
> (15-agent `wf_17c396c2`: 30 claims → 26 CONFIRMED / 4 PARTIAL); **v4
> re-challenged v3 with a second independent 18-agent pass (`wf_dc5c71eb`,
> 06-10 PM)**: 25 claims re-refuted (18 CONFIRMED / 7 PARTIAL — corrections in
> §3/§7/§10), spec-fidelity audit of all 8 session files (§5ter-bis), **and the
> three prod-only zones §10 admitted it could not verify are now WITNESSED on
> the Hetzner host** (§10.1) — in doing so it caught and repaired a same-day
> P0 outage (runner down since 06:00, §10.2). **No production code was written
> in Session 01** (ops repair on the Win11 runner host + docs only). State of
> truth: `main = 9a92dea` (#219), alembic head `0055` (= prod, witnessed).

---

## 0 · The honest verdict (read this first)

1. **"We've done <1%" is factually false.** Verified at the source: Ichor is a
   **deployed, mature system** (`main 5699a90`, ~191 rounds, prod live). A
   rebuild would destroy real value. The job is **deepen + close the feedback
   loop + harden + prove the edge** — not restart. The "1%" line in the spec is
   rhetorical pressure; treating it literally would be the worst decision.
2. **Weighted maturity ≈ 56%** across the 8 build sessions (table §2). The
   forward flow (collect → analyse → synthesise → verdict → frontend) is
   **really wired end-to-end (~70%), not a façade** — verified maillon par
   maillon (§3).
3. **The "50/50 coin-flip" complaint is now ADDRESSED in code** (changed since
   v1): `fuse_conviction` IS wired into the apex verdict —
   `session_verdict_builder.py:180-182` calls it, `run_session_card.py:407`
   passes `enable_scenarios=live`. Evidence modulates conviction magnitude; the
   50/50 is killed in production. _Residual_: only **3 layers** vote on ~58
   dimensions, and the weights are fixed priors, not empirically calibrated.
4. **The NEW #1 gap is that the learning loop is still OPEN** — the heart of the
   vision ("a system that learns and self-improves") is **inert**. Ichor
   _measures_ its skill (Brier/Vovk/ADWIN persisted) but never _acts_ on it:
   `run_session_card.py` never calls `read_pocket`/`confluence_section`, and
   `test_architecture_invariants.py:133` (`test_learning_loop_still_open`)
   **explicitly locks** that state (`:144` asserts the wiring is absent). Ichor
   logs lessons; it does not yet apply them.
5. **Reliability improved since v1** (the 06-05 "pipeline lies intermittently"
   verdict is partly stale): Couche-2 self-heal shipped (PR #214/#216/#217),
   ECB/BLS/EIA + COT collectors repaired (PR #212/#213), prod witnessed healthy
   on 06-09. The residual reliability risks are now **perennity/architecture**
   risks (§6), not a daily-broken pipeline. **Caveat proven same-day (06-10):**
   the §6.4/§6.5 risk class fired again — a Win11 reboot (02:36) + npm CLI
   update left the standalone runner with a stale `claude` path → **0 cards,
   3/5 briefings and 5/5 Couche-2 failed all day, invisible to `healthz`**
   (`claude_runner_reachable=null`) and partly **masked by
   `SuccessExitStatus=0 1`** on the session-cards units. Repaired + witnessed
   the same evening (§10.2). Permanence engineering (Chantier D) must kill
   this exact class — it has now fired 3× (05-29, 06-02, 06-10).
6. **A live product's real health = content FRESHNESS + COHERENCE + a _proven_
   edge**, not green tests. Every "done" below is defined on that basis.

---

## 1 · Vision (reformulated, faithful)

Ichor = a single, massive, fully-interconnected system that **anticipates the
New York session** with its **own founded, motivated conviction — never a
50/50**. Asset universe (verified at source, **three** distinct layers): the
**verdict scope is 5 priority assets** — EUR/USD, GBP/USD, XAU/USD, SPX500,
NAS100 (`PriorityAsset` literal, `ichor_brain/session_verdict.py:87-93`),
matching the vision's "5 actifs"; the **autonomous card batch defaults to 6**
(`_DEFAULT_ASSETS` = the 5 + USD/CAD, ADR-083 D1 "the 6 assets Eliot actually
trades", `run_session_cards_batch.py:52-63`); the **data/collection layer
handles 8** (`_PHASE1_ASSETS`/`_VALID_ASSETS`: + USD/JPY, AUD/USD, USD/CAD).
It must:

- **Cover the whole field of trading** (macro, fundamental, monetary,
  geopolitics, flow, positioning, sentiment, intermarket, options structure,
  seasonality…), **in real time + via APIs**, continuously.
- **Reason with the best available Claude everywhere** — as-built: Opus 4.8
  (ADR-108); **owner decision 06-10: upgrade to Fable 5 at max effort** (§9) —
  understand the market like an embodied market-intelligence with decades of
  experience, and **self-improve** from past lessons (the differentiator —
  currently inert, see §0.4).
- **Explain everything as a beginner-level COACH** ("why / how / what to watch")
  inside an **ultra-premium web UI**.
- Stay aligned to the owner's method: NY momentum bull/bear/range, **position
  window 13h/14h–16h Paris, everything closed by 20h** (spec S06), and the
  **ADR-017 boundary** (bias + probability + pedagogy, never a BUY/SELL order —
  a boundary the S05 spec itself re-affirms: "PAS de TP, SL ou éléments du
  même type").

> **Canonical session numbering = the GUIDE / spec files** (`Ichor_Session_0N_*.md`):
> 01 Cadrage · 02 Architecture/socle · 03 Data temps-réel · 04 Analyse multidim ·
> 05 Méthodo technique · 06 Prédiction/verdict · 07 Apprentissage · 08 Frontend ·
> 09 Intégration/pérennité. The v1 of this file (06-05) used a _different_ internal
> numbering — that desync is corrected here; everywhere "Session N" now means the
> spec file N.

---

## 2 · State of the art — audited at source (per canonical session)

| Session | Layer                                            | Maturity | Honest one-liner (evidence)                                                                                                                                                                                                                                                                                                                                                                                            |
| ------- | ------------------------------------------------ | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **S02** | Socle (monorepo, Voie-D, persistence, real-time) | **72%**  | Solid & LIVE: Turborepo+pnpm+uv; Opus 4.8 via local subprocess, zero SDK (`subprocess_runner.py:64-142`); Postgres/Timescale head `0055`; watchdog (`runner-watchdog.ps1`). But effort capped at `high` (never `extra`/`xhigh`); learning seam exposed-not-exercised.                                                                                                                                                  |
| **S03** | Data collection & real-time                      | **70%**  | ~42–47 robust collectors + WebSocket FX + **102 ichor systemd timers** (recounted on host 06-10); newsletters layer exists as-built (11 verified RSS feeds, 06-06). The two cardinal capabilities (Opus-driven web research + `streaming_refresh`) **are ON in prod — witnessed in the DB 06-10** (§10.1); the one un-armed flag is `scenario_invalidation_monitor_enabled` (absent from the table = OFF fail-closed). |
| **S04** | Multidimensional analysis                        | **58%**  | ~58 `_section_*` dimensions really wired into the LLM pool (real academic microstructure); but only **3 layers vote** in the apex conviction and several dimensions are thin proxies. 9/9 wired, 0/9 "maxed" (`S04_FINALIZATION_PROGRAM.md:7-9`).                                                                                                                                                                      |
| **S05** | Technical methodology (Ichor reads TradingView)  | **18%**  | Honest data-derived proxy (candle classifier, SMC/ICT levels, origin-zone) but **none** of the 3 core deliverables (live chart reading, Pine indicators, the owner's TA method) — and the coded doctrine (**ADR-017**) _actively refuses_ this paradigm. See GAP-4: a **doctrine decision**, not a missing feature.                                                                                                    |
| **S06** | Verdict & real-time reactivity                   | **52%**  | Canonical verdict (direction + conviction% + nature, NY-calibrated) is LIVE and `fuse_conviction` is really wired (50/50 killed in prod). But technical analysis does **not** feed the verdict, and reactivity = 30 s polling + flag-gated cron, no SSE/WebSocket push.                                                                                                                                                |
| **S07** | Learning & self-improvement                      | **52%**  | Measurement is LIVE (Brier/Vovk/ADWIN/reconciliation crons) but the **act loop is OPEN**: `pocket_skill_reader` is dead code (0 callers from generation), W116c addendum flag-off. Ichor logs, doesn't act. **This is the #1 gap.**                                                                                                                                                                                    |
| **S08** | Premium frontend                                 | **68%**  | `apps/web2` (Next.js, OKLCH+aurora design, coach-FR `coachLabels`, ~21 honest-absence fetches) is real and high quality; but the public URL is a rotating quick-tunnel (breaks "works permanently") and demo data remains on `/today`. `apps/web` = legacy frozen.                                                                                                                                                     |
| **S09** | Integration, tests, durability                   | **62%**  | Multi-language CI + arch-invariant guards + auto-rollback deploy + runner watchdog are LIVE; but **no proactive monitoring** (no Prometheus alert rules), gates deliberately non-blocking (coverage ~49%, mypy/audit warn-only), no recurring real E2E multi-asset suite.                                                                                                                                              |

_(S01 Cadrage = this document.)_ **Weighted average ≈ 56%.** The gap to the
vision is **not absence of breadth** — it is **depth, feedback, and proven edge**.

> ⚠️ The maturity percentages are **editorial estimates** (lead judgment over the
> audit), not measured/sourced facts — no closed-form formula. Treat them as a
> relative ranking of where the work is, not as precise metrics. The _structural_
> claims (LIVE/PARTIAL/BROKEN/MISSING + file:line) are the verified facts.

---

## 3 · Interconnections — forward TRUE, feedback BROKEN

**Forward flow is real (~70%)**, verified link by link — not a façade:
`S03 (WebSocket FX + crons) → S04 data_pool → S05 confluence → frozen snapshots
(migration 0055) → S06 fuse_conviction → S08 SessionVerdictPanel (poll 30 s)`.
Direction stays bucket-derived (ADR-017); evidence modulates **magnitude** — the
50/50 is killed in live.

**The broken/partial links are the feedback loop and real-time edge:**

| Link                                                                 | State                             | Impact                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| -------------------------------------------------------------------- | --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Brier feedback → generation (down-weighting)                         | **BROKEN**                        | `brier_feedback.py` surfaces the diagnostic only ("Phase 2 will add automatic down-weighting"); sole consumer = read-only API router. Introspection shown, not auto-correction.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| Vovk weights `brier_aggregator_weights` → `confluence_engine`/Pass-3 | **BROKEN (dead code)**            | `pocket_skill_reader` has 0 callers from generation; `confluence_engine` never reads the weights. The nightly cron computes weights nobody consumes. Locked open by `test_architecture_invariants.py:133-144`. Same class (re-verified 06-10): `brier_optimizer` persists proposed weights with `adopted=False` and **no code ever promotes them** — only equal-weight baseline seeds get `is_active=TRUE` (`cli/run_brier_optimizer.py:109-131`).                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `streaming_refresh` reactive → verdict (inter-batch)                 | **LIVE (witnessed 06-10)**        | Flag `streaming_refresh_enabled` = ON in prod DB (enabled=t, 100%, §10.1); the watcher timer last ran exit 0 the same evening. _Still missing_: `scenario_invalidation_monitor_enabled` is **absent** from the prod table = OFF (fail-closed) — the auto-invalidation half of reactivity is the one un-armed flag (§4.6).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| Technical price-action → apex verdict                                | **MISSING as a voting dimension** | No technical input reaches the builder directly (negative search, `session_verdict_builder.py` — re-verified 06-10 ×2). Nuance (corrected v4): **three** indirect channels exist, not two — (a) confluence reads daily levels (PDH/PDL/pivots) + OFI (`confluence_engine.py:10-11,53`), (b) `tradeability` reads `is_range_bound` (`tradeability_evaluator.py:86,341`) — both magnitude-only, sign never (`conviction_fusion.py:21-23`); (c) the technical `_section_*` blocks (daily*levels, key_levels, microstructure, volume_rvol, hourly_vol, polygon_intraday) feed Pass-1's data pool whose chain builds the Pass-6 prompt, and **Pass-6 buckets set the apex SIGN** — so technicals \_can* influence direction via the LLM channel, just never via a deterministic vote. Still no technical _vote_ — blind spot vs S05/S06 vision. GAP-4 decided Option A (§9). |
| Ichor-beta meeting-hub lessons → learning                            | **MISSING**                       | Ad-hoc citations in 2 modules, no ingestion system.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |

**Closed feedback loops (corrected v4 — three, not one):**
(1) `scenario_calibration` (EWMA(0.94) σ on realised returns → Pass-6 prompt,
unflagged, live); (2) the **RAG analogue loop** — past cards (≥1-day embargo)
re-injected into Pass-1 via `--enable-rag` on the prod cron
(`register-cron-session-cards.sh:59`) — an output→input loop, not
outcome-calibrated; (3) `tempo_recalibration` — weekly percentile recompute →
`tempo_thresholds` consumed live by web2 (display-side only). What stays open
is the one that matters: **measured skill never re-injects into generation**
(Brier/Vovk weights → confluence). Closing that re-injection = the "100x"
lever (§4.1).

---

## 4 · Target architecture — principles for "100x further" (grounded in 2026 research + system reality)

Anchored on what exists, not generic. Research refs verified via the workflow's
focused 2026 sweep (StockBench, calibration-aware RL, narrative-bias studies).

1. **Close the learning loop FIRST** — the only "100x" lever that touches the
   differentiator. Wire `pocket_skill_reader.read_pocket` into `run_session_card`
   (pass `confluence_section`), make `confluence_engine` read
   `brier_aggregator_weights`, remove the `test_learning_loop_still_open` lock.
   The seam already exists (`orchestrator.py` accepts `confluence_section`) — this
   is **wiring, not construction**. Down-weight gradually + audit
   (`auto_improvement_log` already captures metric_before/after).
2. **Calibration as a first-class citizen** (calibration-aware RL research; Brier
   decomposition; isotonic/PAV reliability diagrams): **never trust the LLM's
   verbalised conviction** — RLHF systematically over-confident ("most sure when
   most wrong"). Report Brier decomposed into reliability/resolution/uncertainty,
   set decision/sizing thresholds on **measured accuracy per confidence bucket**,
   add post-hoc recalibration (temperature/isotonic) on the conviction output.
   Ichor already has `brier.py`/`penalized_brier.py`/`brier_multiclass.py` — the
   missing piece is the **calibrated re-injection**.
3. **Out-of-sample benchmark, non-negotiable** (StockBench: most LLM agents fail
   to beat buy-and-hold): impose buy-and-hold + a naïve baseline (momentum/ARIMA)
   as a **pass/fail gate**, evaluated strictly on periods _after_ the serving
   engine's training cutoff — **Fable 5 (January 2026), not Opus 4.8**, since
   the §9 engine upgrade lands before/with Chantier A. **Anti-leakage by design**: walk-forward only (never random
   CV on time series), latent-leakage test (recall-vs-forecast correlation),
   dynamic universe, costs/slippage included. Without this, the edge is a
   narrative.
4. **Make the ~58 dimensions vote, not 3**: extend `fuse_conviction` beyond
   confluence/dollar/theme. Multi-agent research (TradingAgents/FinCon) suggests
   **typed-I/O specialised roles** (fundamental/sentiment/technical analyst +
   adversarial Bull/Bear debate + a **distinct risk agent**) over one monolith
   reading `data_pool.py` (>6000 lines — high regression risk). This is a
   `data_pool` refactor into voting modules.
5. **Isolate factual from causal** (narrative-bias failure mode): treat every
   causal explanation from Opus as an **unverified hypothesis**; cross-reference
   each number against the data API; explicitly allow "ambiguous signal / I don't
   predict" (aligns with the existing `tradeability` flag). RAG with guardrails:
   never retrieve from retroactively-editable sources (current `embed_session_cards`
   is sound — time-stamped).
6. **Turn on real real-time**: `streaming_refresh_enabled` is **already ON in
   prod (witnessed 06-10, §10.1)**; the remaining seed is
   `scenario_invalidation_monitor_enabled` (absent from the prod table = OFF
   fail-closed — after the ≥3-session empirical validation the monitor
   requires), then move to SSE/WebSocket push. The 2026 event-driven
   reference (Kafka/Redpanda → Flink) is **likely over-engineering for 6 assets /
   a 3h NY window** — the existing 1–5 min cron + FX WebSocket is already good;
   prioritise **train/serve consistency** (feature store) to avoid "logic drift",
   the critical risk for a self-learning system.
7. **Proactive monitoring**: add Prometheus `rule_files`/`alerting` (collector
   stale, Brier drift, briefing lag, error rate) — turn passive `data_liveness`
   detection into autonomous poll-and-alert.
8. **Arbitrate S05** (GAP-4) — **✅ DECIDED 06-10, Option A reinforced (§9)**:
   Ichor reads the chart A→Z (amend the "Eliot does TA" doctrine, wire
   `tradingview-cdp`; no-BUY/SELL stays contractual). Chantier E remains gated
   only on the §9.2 materials and its place in the §5 order. _(The arbitration
   text below this plan kept for the record predates the decision.)_

---

## 5 · Roadmap — ordered chantiers, mapped to canonical sessions

> "Done" = **fresh + coherent content + a witnessed edge**, not just green tests.
> Order is dictated by (a) leverage on the vision, (b) hard dependencies,
> (c) the principle "prove the edge before enriching".

| #      | Chantier                                                            | Advances       | Depends on                          | Deliverable                                                                                                                                                                                                                                                                                                                                        |
| ------ | ------------------------------------------------------------------- | -------------- | ----------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **01** | **Cadrage + doctrine arbitrations** (this)                          | S01            | —                                   | This plan (v4); **GAP-4 + Couche-1 decided by the owner (§9)**; `README.md`/`ROADMAP.md` refreshed + SUPERSEDED banners (✅ 06-10 AM); **prod-zone verification closed + same-day P0 runner outage repaired & witnessed (✅ 06-10 PM, §10.1-10.2)**; lying docstrings (§7) = first task of the next code chantier (S01 writes no production code). |
| **A**  | **Benchmark & trading-grade validation**                            | S07/S09        | data S03✓, reconciliation S07✓      | Buy-and-hold + naïve baseline gate, **out-of-sample** (post-cutoff), walk-forward, costs included. _First — it conditions every later edge claim._                                                                                                                                                                                                 |
| **B**  | **Close the learning loop + calibration**                           | **S07** (+S06) | seams S02✓, measurement S07✓, **A** | Wire W115c (`read_pocket`→Pass-3), per-bucket recalibration. Ichor **actually learns**. The "100x" chantier.                                                                                                                                                                                                                                       |
| **C**  | **Make dimensions vote + risk agent**                               | S04/S06        | **B**, **A**                        | Refactor `data_pool` monolith into voting modules + adversarial Bull/Bear + distinct risk agent.                                                                                                                                                                                                                                                   |
| **D**  | **Real-time + proactive monitoring**                                | S03/S06/S09    | socle S02/S03✓                      | Seed streaming/invalidation flags (after empirical validation), SSE push, Prometheus alert rules, end-to-end freshness gate (GAP-8). _Parallelisable with C._                                                                                                                                                                                      |
| **E**  | **S05 technical methodology** _(GAP-4 DECIDED ✅ 06-10 — Option A)_ | **S05**/S06    | §9.2 materials (owner), **C**       | Chart validated by the owner: ADR amending the "Eliot does TA" doctrine, wire `tradingview-cdp`, Pine indicators, the owner's method → feed the verdict (no-BUY/SELL stays contractual).                                                                                                                                                           |
| **F**  | **Durability hardening + stable frontend**                          | **S09**/S08    | all above                           | Coverage→70%, mypy/audit blocking, recurring multi-asset E2E, **stable URL** (Cloudflare named tunnel — end the rotating quick-tunnel), remove `/today` demo data. Seals the system.                                                                                                                                                               |

**Why this order:** A-before-B/C is counter-intuitive but critical — 2026
research shows enriching a system _without_ an out-of-sample benchmark produces
narrative, not edge. B is the heart of the vision. E was gated on a human
decision — **decided 06-10 (Option A, §9)**; it now waits only on the §9.2
materials and on C. F plays the S09 sealing role.

**Transverse chantier (owner decision 06-10, §9): engine upgrade Opus 4.8 →
Fable 5 at max effort.** Config-level but witness-heavy: new ADR superseding
ADR-108, runner CLI ≥ 2.1.170 (✅ host already on 2.1.170, witnessed 06-10),
staged per-surface rollout (Pass-1..6, Couche-2, briefings) each with a live
card witness. **Concrete scope found by the v4 audit:** the runner's
`claude_default_model: Literal["opus","sonnet","haiku"]` does **not** accept
`fable` (`apps/claude-runner/.../config.py:30-34`) → small runner code change

- all call sites (`orchestrator.py`, `run_briefing.py`, Couche-2 agents) pass
  `model`/`effort` explicitly; the effort schema **already accepts
  `xhigh`/`max`** (`models.py:28,104`) — the `high` ceiling is caller
  convention, not enforced (§10.3). Execute as the opening task of the next
  code session — before/alongside Chantier A so the benchmark measures the
  final engine.

**Per-chantier pass/fail gates (added v4 — "done" must be falsifiable):**

- **A**: report beats buy-and-hold AND the naïve baseline out-of-sample
  (post-2026-01 walk-forward, costs included) — or honestly reports it does
  not. Gate = the report exists and is reproducible, not that Ichor wins.
- **B**: ≥1 measured-skill weight actually consumed by generation (invariant
  test flipped from `test_learning_loop_still_open` to its positive twin) +
  Brier reliability component improves or holds over a 20-session window.
- **C**: ≥9 dimension layers vote in `fuse_conviction` (vs 3 today) with
  per-layer provenance; data_pool monolith split without behaviour change
  (golden-card diff).
- **D**: a deliberately-killed runner/collector fires an alert < 15 min
  (proactive monitoring witnessed); `scenario_invalidation_monitor_enabled`
  seeded after its 3-session validation; the 06-10 outage class (§10.2) can
  no longer pass silent (`SuccessExitStatus` masking removed, healthz probes
  the runner).
- **E**: Ichor produces a chart read of one NY session that the owner
  validates against his own (the §9.2 transcripts are the rubric); no
  BUY/SELL token emitted (CI guard unchanged).
- **F**: stable URL survives a reboot; `/today` shows zero demo data; a
  vision-conformance audit (spec S09's "vision fondatrice intégralement
  respectée") is run and its gaps listed — the seal is vision-level, not just
  technical.

---

## 5bis · Backlog already-identified — folded in (so no chantier rediscovers it)

ADR-017-safe (descriptive; Ichor surfaces, Eliot trades):

- **AOI niveau-1/2** = `provenance` label `origin_entry`/`origin_exit` on
  `previous_session_origin_zone`.
- **failed_new_extreme** = derived field on the daily-candle classifier → feeds
  SessionVerdict `nature` (momentum-exhaustion tell).
- **5-announcement ranking** (rate decision > CPI > GDP > retail > employment) →
  weight Engine-8 baselines by theme-importance, not just bp.
- **EUR = read Germany then France** (never an "Europe" aggregate);
  **non-weighted currency-strength index** distinct from volume-weighted DXY;
  **geopolitics "no real catalyst"** nuance (fade low-grade rumour panic).
- **S08 pedagogy**: DXY inverse-mechanics coach copy; "structured market = no edge
  = OUT" tooltip reinforcing the existing `TradeabilityFlag`.
- **🚫 NON-GOAL — SUPERSEDED 06-10 by the GAP-4 decision (§9.1).** The v1-v3
  boundary "intrabar push/correction texture (H1/15-min) is Eliot's own lane,
  Ichor must NOT build it" is **retracted**: the owner decided Option A
  reinforced ("ichor lit et analyse complètement le chart de A à Z ultra ultra
  poussé") — chart reading at every granularity is now **in scope for Chantier
  E**. What survives, contractual and unchanged: **no BUY/SELL/TP/SL/entry
  orders ever** (ADR-017); Ichor reads, explains and feeds the verdict — the
  owner executes.

---

## 5ter · Spec sessions 02→09 — exact deliverables ↔ chantiers (full extraction 06-10)

> Source: complete extraction of the 8 spec files `Ichor_Session_0N_*.md`
> (workflow `wf_17c396c2`). "État" = §2 maturity; "Chantier" = which §5
> chantier carries the remaining work. This is the per-session roadmap the
> spec's Session 01 demands (order, dependencies, deliverables).

| Spec                          | Deliverable demanded by the spec (condensed, faithful)                                                                                                                                          | État                                                                                        | Chantier(s)                                         |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- | --------------------------------------------------- |
| **S02 Socle**                 | Orchestration backbone + LLM engine at full effort for every analysis + persistence + 24/7 real-time skeleton; "écosystème vivant, analyses jamais statiques"                                   | 72% LIVE                                                                                    | **D** (real-time), **F** (hardening)                |
| **S03 Data temps réel**       | Pipeline web research + APIs + newsletters + Polymarket + full eco calendar + holidays/week-end detection, continuous ingestion, automatic event captation                                      | 68% LIVE (flag ON-state not provable from repo)                                             | **D**                                               |
| **S04 Analyse multidim**      | Per-dimension modules (fonda, macro, géopo, world news, correlations/DXY, volume, sentiment, market actors, manipulation/liquidity + Ichor's own view) on live data, "aucune zone d'ombre"      | 58% — 9/9 wired, 0/9 maxed                                                                  | **C** (+ `S04_FINALIZATION_PROGRAM.md`)             |
| **S05 Méthodo technique**     | **Ichor does ALL the TA**: deep study of the 2 transcripts + Ichor-beta meeting hub, TradingView connection, live chart reading, own indicators, fusion with the multidim — never signals/TP/SL | 18% — data-derived proxies only; GAP-4 ✅ decided 06-10 (Option A), gated on §9.2 materials | **E**                                               |
| **S06 Prédiction/verdict**    | Verdict /100 (direction + conviction % + nature momentum/structuré), ranked scenarios, triggers/invalidations, London-morning read → NY calibration, daily reset, live re-analysis + alerts     | 52% — verdict+fusion LIVE; reactivity = poll/cron                                           | **C**, **D**                                        |
| **S07 Apprentissage**         | Structured memory + verdict↔reality feedback loop + lesson journal + **measurable daily improvement** + hub lessons ingestion                                                                   | 52% — measurement LIVE, **act-loop OPEN = #1 gap**                                          | **B** (after **A**)                                 |
| **S08 Frontend**              | Premium frontend (dark noir/bleu lumineux DA), visual comprehension-coach, responsive, auto-refreshed, zero bug                                                                                 | 68% — web2 real & premium; unstable URL, demo data                                          | **F** (continuous élévation)                        |
| **S09 Intégration/pérennité** | Everything interconnected as ONE system, tested in real conditions, 0 bug, durable + final beginner-level bilan                                                                                 | 62% — CI/guards LIVE; no proactive monitoring                                               | **A** (benchmark), **D** (monitoring), **F** (seal) |

> ⚠️ Three spec↔plan tensions are resolved deliberately here, not silently:
> (1) **S08 says "rebuild from zero"** — the 2026-06-03 grounded Playwright
> audit showed the premium OKLCH design system is already in place and a
> rebuild would be destructive; the chantier is **continuous élévation**, not
> rebuild. _(v4 honesty note: the spec phrase "conserver la même direction
> artistique" governs the daily Fable-5 rework sessions, it is not itself a
> licence to skip the rebuild — the no-rebuild call rests on the audit, and
> is re-submittable to the owner at any time.)_ (2) **S05's "Ichor fait toute
> l'AT"** contradicted the as-built doctrine — GAP-4, **decided Option A
> 06-10 (§9)**. (3) **S05 priority inversion**: the spec calls S05 "une
> priorité absolue, le cœur de l'edge", yet Chantier E runs after A/B/C —
> deliberate ("prove the edge before enriching" + §9.2 materials gate), now
> flagged explicitly rather than implied.

### 5ter-bis · Spec requirements the condensed rows under-carried (v4 fidelity audit, 8 fresh agents)

Load-bearing items the §5ter one-liners lost; each is now **owned by a
chantier** so no session rediscovers them. (LOW-severity wording nits omitted.)

- **S02** → the engine requirement "intégration Claude Fable 5, full
  performance, effort maximal **pour toutes les analyses ET recherches**" is
  carried by the **transverse Fable-5 chantier** (web-research passes
  included); the persistence layer is "persistance/**mémoire**" (the memory
  half anchors S07); "modulaire" and "points d'ancrage prêts" = Chantier C's
  refactor criteria.
- **S03** → the **newsletters interconnexion** (repeated 3× in the spec) is
  as-built (11 verified RSS feeds, 06-06) but thin: its expansion belongs to
  Chantier D. The daily output "**manipulation attendue AVANT le momentum
  NY**" (spec:196) = explicit deliverable of Chantier C (manipulation/liquidity
  dimension → verdict surface). Holiday/weekend **behavioural adaptation** is
  as-built (ADR-105 gates, both ON in prod, witnessed §10.1). "Être prévenu de
  toutes les annonces" = Chantier D alerting.
- **S04** → the "🎓 montée en compétence" block (spec:188-199) is **not**
  S05-only: web-research-driven mastery of fundamental/macro/announcement
  analysis + the transcripts' non-technical lessons feed **Chantier C** (and
  the Fable-5 web-research passes). "Analyse exhaustive, **vérifiée et
  croisée**" per asset = Chantier C done-criterion (cross-dimension
  consistency, §4.5). "Calibrées à la réalité actuelle du marché" =
  regime-awareness of dimension modules (distinct from §4.2 probability
  calibration) — Chantier C.
- **S05** → Chantier E done-criteria now include the spec's five assimilation
  dimensions ("ma logique, mes critères, mes déclencheurs, ma lecture du prix,
  tout mon raisonnement"), the **scam/marketing-vigilance filter** on encoded
  TA knowledge, hub assimilation on the S05 side (bilans/leçons/incohérences —
  beyond S07's ingestion), and indicators built **for Ichor's own reading**
  (aids, not end-user deliverables).
- **S06** → the spec's §10.4 "**calibrer la prise de risque (plus ou moins
  exposée)**" = daily exposure-guidance deliverable, owned by Chantier C's
  risk agent (ADR-017-safe: exposure stance, never sizing orders). Delivery is
  **bi-pre-session** (London AND NY) on the web app; the engine must also
  cover **pre-session/open capture**, not only the 13h-16h position window.
  Verdict granularity: **per-scenario conviction AND probability**. _(NB the
  "Paris" timezone in §1 is an inference — the spec never names a timezone —
  [TBD owner].)_
- **S07** → the spec demands learning **about the market itself** ("apprendre
  toujours plus en profondeur du marché — comment il bouge, pourquoi"), not
  only self-performance feedback: Chantier B's scope = skill re-injection +
  **market-behaviour lesson extraction** (lesson journal beyond Brier). The
  S05-technique re-injection target (spec:178) is explicitly **deferred to
  post-E**, not dropped.
- **S08** → two hard owner constraints now explicit: **never mention
  Claude/any model version on the page** (the `noModelNames` vitest guard
  partially enforces this — keep it green forever) and **no separate
  "methodology" blocks** — pedagogy must live in the content's structure and
  phrasing itself. The élévation chantier owns the spec's concrete visual
  deliverables (bespoke animated illustrations, embedded reference imagery,
  flawless charts, hover micro-interactions, zero overlap) and the **recurring
  frontend rework mechanism** (local Fable-5 sessions at max effort, same DA).
- **S09** → Chantier F's seal includes a **vision-conformance audit** (spec:
  "valide que la vision fondatrice est intégralement respectée") and the final
  bilan keeps its three spec components: where we are / what remains / **what
  the owner must say or do next**. The spec's absolute "0 bug, 100%" vs the
  pragmatic gates (coverage 70%, non-blocking→blocking) is a flagged tension:
  the absolute is the direction, the gates are the floor.

---

## 6 · Perennity risks (ranked — the durability of the whole system)

1. **P0 — Voie-D silent ban of the Max-20x account.** `ADR-009:79-80` states
   Anthropic **banned 3rd-party Max agents in April 2026**; the cron `claude -p`
   4×/day is a ToS grey zone (OAuth "intended for individual use"). A ban kills
   **100% of Claude compute with no notice**. **Doc/code divergence (precision
   v4)**: `ADR-009:61` documents a Cerebras → Groq → static-template chain, but
   in code (a) `fallback.py:4` wires it for the **Couche-2 agents only**, (b)
   the real order tries **Claude FIRST** (ADR-021, `fallback.py:87-105`), (c)
   **no template step exists at all** — exhaustion raises `AllProvidersFailed`
   (`fallback.py:160`), and (d) **prod has no Cerebras/Groq credentials**
   (witnessed 06-10: `agents.fallback.skip_no_creds` → `MissingCredentials`),
   so the effective chain everywhere is **Claude-only, fail-loud** — which now
   matches the owner's premium-only decision (§9.2) but means a ban stops
   Couche-2 too, not just Couche-1. Existential risk #1; mitigation (continuity
   plan, recovery runbook) still unwritten.
2. **Single Win11 host + serialised subprocess** (`max_concurrent_subprocess=1`):
   one Claude at a time for the whole system. No HA, no horizontal scale; home
   hardware/power/ISP failure = total outage. _Precision v4 (witnessed 06-10):_
   the semaphore is **per-instance**, and **two** runner instances listen
   today (NSSM remnant :8765 + standalone :8766; the tunnel routes :8766,
   proven empirically by the repair witness §10.2) — global serialisation is a
   convention, not a lock. Chantier D: retire the :8765 zombie, one canonical
   supervised instance.
3. **"Local-only" is a false friend**: Hetzner reaches the "local" runner via
   **Cloudflare Tunnel over the public internet**; 530/QUIC storms are a recurring
   outage source. Local compute yes, **local invocation path no**.
4. **Fragile CLI coupling**: everything depends on the undocumented
   `claude -p --output-format json` envelope and flags (`--effort`, alias `opus`).
   A CLI update can break generation silently — **already happened** (alias
   resolved to 4-7 instead of 4-8). Watchdog can signal, not repair.
5. **Win11 operational drift**: NSSM service degraded since 2026-05-02; prod
   runs a standalone uvicorn that dies on logout; bus-factor of one, manual
   recovery. **Fired again 06-10** (§10.2): reboot + npm CLI update → stale
   `claude` path frozen in the running process env → full LLM-layer outage for
   a day, masked by `SuccessExitStatus=0 1` and invisible to `healthz`
   (`claude_runner_reachable=null`). The launch-time path probe (06-02 fix) is
   **not reboot/update-race-proof**: Chantier D needs spawn-failure
   re-resolution (or a runner-side watchdog) + honest exit codes + healthz
   that actually probes the runner. _Good news witnessed the same day:_ the
   tunnel hostname is now behind **Cloudflare Access** (bare curl → 403;
   Hetzner passes via service token) — the W102 "no auth" exposure is closed.
6. **Monitoring debt** (no slow-drift detection): no alert fires until a unit
   crashes; combined with non-blocking gates → silent regressions possible.
   Direct debt against "nothing degrades over time". Addressed by Chantier D.
7. **Documentary-truth debt**: stale docstrings risk a maintainer "fixing" code
   toward the false doc (§7).

---

## 7 · Doc & docstring corrections (truth debt — verified at source)

**Stale docs (progress, not structure):**

- `README.md` **materially stale** (`:7-10,19,223`): announces Phase 2, Opus
  4.7+Haiku, head **0027**, "24 ADRs". Reality (verified): Opus 4.8, head **0055**
  (`migrations/versions/0055_*`), **95 ADRs** (head ADR-109), Couche-2 = Opus low
  (ADR-108). _(NB: the README's "8 assets" is **correct** for the data layer — do
  not "fix" it to 5; the 5 is the verdict scope, see §1.)_ **Refresh in Chantier 01.**
- `ROADMAP.md` §1 stale (frozen at `c877d04`/06-03 vs `5699a90`/06-09).
  **Refreshed 06-10 (this session).**
- **No SUPERSEDED banner** on docs a reader could mistake for current authority
  (verified 06-10): `ARCHITECTURE_FINALE.md`, `ICHOR_PLAN.md` (still claims "à
  relire en début de chaque nouvelle session", `:3`), root `SPEC.md` (`:5`
  "prêt pour implémentation", `:85+` still Opus 4.7), `docs/SPEC.md`,
  `SESSION_HANDOFF.md` (`:3` still "**AUTORITAIRE** — read this first").
  **Banners added 06-10 (this session).**
- `S04_FINALIZATION_PROGRAM.md:21-27` lists "DONE this session" (FX volume
  disclosure, commit `41e9976`) but that commit is **on branch
  `claude/s04-fx-volume-disclaimer`, not in main** (verified `git merge-base`
  06-10) — merge/deploy it or relabel the entry.
- `ARCHITECTURE_CIBLE.md` / `ARCHITECTURE_FINALE.md` / `SPEC.md` /
  `ICHOR_PLAN.md` / `ROADMAP_PHASE_F_12_MOTEURS.md` = archive (SUPERSEDED banners
  present). Do not edit.

**Lying docstrings (regression risk — verified false at source):**

- `conviction_fusion.py:32` says the verdict builder will delegate "in a **later
  (gated) integration step**" → **STALE**: the delegation is already done
  (`session_verdict_builder.py:180-182`), fusion is LIVE. _(The separate line
  `:54` "Vovk/Brier reader→conviction loop stays flag-gated OFF" is **accurate** —
  that's the learning loop of §0.4, genuinely off. Don't conflate the two.)_
- `session_verdict_builder.py:10` says `enable_scenarios=False` "dormant fallback"
  → **FALSE in prod**: `run_session_card.py:407` passes `enable_scenarios=live`.
  The False default only applies to dry-run/import.
- `ARCHITECTURE.md` says `_section_*` count 54 (`:24,55,80`) → real **58
  exactly** (re-counted twice, 06-10), and it misses **four** sections, not
  two: `_section_volume_rvol` (`data_pool.py:5025`), `_section_rate_positioning`
  (`:4502`), `_section_manipulation_liquidity`, `_section_today_schedule` —
  the as-built doc lags 06-05+. _(Correction v3: the "Pass-6 = sonnet/medium" line is **not** in
  `ARCHITECTURE.md`; it lives in the archived `ARCHITECTURE_CIBLE.md:45`. The
  live default is `opus/high`, `orchestrator.py:111-114`.)_
- `run_briefing.py:22-25` docstring **promises** a Couche-1 degraded fallback
  ("fallback to Cerebras+Groq … static template") → **FALSE in code**: on
  runner failure it sets `row.status="failed"` and returns 4, no LLM fallback
  (`run_briefing.py:536-545`). In-code twin of the §6.1 ADR-009 divergence.
- `providers.py:11` docstring promises a "static template (last resort)" step
  that is **implemented nowhere** (exhaustion raises `AllProvidersFailed`,
  `fallback.py:160`) — same family as the `run_briefing.py:22-25` lie; both
  reconcile to fail-loud truth per the §9.2 owner decision.
- The repo `CLAUDE.md` **body** is materially stale (the top sync-lines are
  current): "Latest migrations (head 0049)" (`:317`) vs real 0055; "Couche-2
  lives on Claude Haiku low (ADR-023)" (`:289`) vs ADR-108 Opus low; an
  "Opus 4.7 specifics" section (`:609`). A maintainer trusting the body over
  the sync-lines would regress — refresh in the next docs pass.
- Attribution nuance (not a bug): "cap-95" is canonical in code + ADR-081/085,
  but the `ADR-022` document itself never states "95" — don't cite ADR-022
  alone as the source of the cap. Same family: `_VALID_ASSETS` = 8 only in
  `routers/scenarios.py:38-47`; a second `_VALID_ASSETS`
  (`routers/tempo_thresholds.py:41-44`) = 6 — don't cite "the" `_VALID_ASSETS`
  without the file.

**Confirmed-still-accurate memory** (not stale):

- "Learning loop OPEN (pocket_skill_reader measures but not wired)" → **still true
  2026-06-09**, locked by `test_architecture_invariants.py:133-144`.
- "`apps/web` legacy frozen, `web2` = real deployed frontend" → confirmed.

**Numbering divergence:** the repo's `ARCHITECTURE.md` attributes "close the loop"
to "Session 05"; the spec places it in **S07**. Substance (wire pocket_skill →
Pass-3) is unchanged; this doc uses the **spec numbering** throughout.

---

## 8 · Invariants (never break — all sessions)

- **ADR-017** — never BUY/SELL (bias + probability only). CI-guarded.
- **Voie D (ADR-009/108)** — zero `import anthropic`; all LLM via local runner.
- **cap-95** conviction (ADR-022).
- **Couche-2 = Opus low** (ADR-108) — never hard-code `sonnet`.
- **Source-stamping** — every numeric claim traceable (Critic).
- Watermark single-source-of-truth; pure-data routes excluded (ADR-079/080).
- Feature flags fail-closed; audit logs immutable (ADR-029/077).
- **Liveness / "no blind spot"** — value | honest N/A | ABSENT/STALE+degraded;
  never a silent n/a.

---

## 9 · The decisions only the owner can make

> **⚖️ DECIDED 2026-06-10 (owner, in-session, verbatim recorded):**
>
> 1. **GAP-4 = Option A, reinforced** — "ichor lit et analyse complètement le
>    chart de A à Z ultra ultra poussé". Ichor does ALL the technical analysis.
>    Chantier E is **unblocked doctrinally**; it remains gated only on the
>    §9.2 materials (owner must supply) and on its place in the §5 order
>    (after C). First code step: ADR amending the "Eliot does TA" doctrine
>    (no-BUY/SELL/TP/SL stays contractual).
> 2. **Couche-1 = premium-only, NO degraded fallback** — "pas de fallback, on
>    priorise le maximum de qualité" — **and the LLM engine upgrades from
>    Opus 4.8 to Fable 5** ("full analyse avec fable 5 … puisque meilleur
>    modèle"), with maximum permanence engineering ("faire tout pour que tout
>    soit ultra permanent"). Consequences: (a) reconcile the lying fallback
>    docs (`run_briefing.py:22-25`, `ADR-009:61`) to fail-loud truth;
>    (b) new ADR superseding ADR-108: **full-Fable-5 everywhere, effort max**
>    via the local runner (CLI ≥ 2.1.170, model `claude-fable-5`/alias
>    `fable`) — staged rollout + live witness per surface (Pass-1..6,
>    Couche-2, briefings); (c) permanence hardening = collector-staleness
>    watchdog + runner auto-restart + alerting (folds into Chantier D).
>
> The arbitration analyses below are kept for the record.

**9.1 — GAP-4, S05 doctrine arbitration (blocks Chantier E and part of C/S06).**
The spec files are emphatic and repeat it three times (S04 "Analyse technique
DÉSORMAIS PRISE EN CHARGE PAR ICHOR", S05 "ICHOR FAIT TOUT … il n'y a plus de
découpage entre toi et moi sur la technique", S06 "ÉVOLUTION MAJEURE, À ACTER
ABSOLUMENT"): Ichor should _do all the technical analysis_ (read the live
TradingView chart, apply the owner's methodology, create indicators) and feed
it into the verdict. The as-built doctrine says the opposite (_Eliot does the
TA_: `data_pool.py:846-849`, `key_levels/__init__.py:6`, §5bis non-goal) and
earlier verbatim directives (Fathom 2026-05-25) match the as-built side.
Important nuance the spec itself settles: **the no-BUY/SELL/TP/SL boundary
survives either way** ("PAS de TP, SL ou éléments du même type", S05) — what
is being arbitrated is _who reads the chart_, not whether Ichor emits orders.

- **Option A — act the spec**: amend the "Eliot does TA" doctrine (ADR-017
  scope note, keep no-signals intact), wire `tradingview-cdp` (78 tools already
  available) + Pine indicators + the owner's method. Higher vision-fidelity;
  higher doctrine/risk surface. **Requires 9.2 materials.**
- **Option B — keep the as-built doctrine, downgrade S05**: Ichor stays a
  descriptive context engine; S05 = "technical _context_ (levels, zones),
  never the read". Lower risk; contradicts the current spec.

Until this is decided, **no S05 code is written**. Everything else proceeds in
full autonomy.

**9.2 — S05 mandatory materials (only the owner can provide).** The spec is
explicit: "Sans ces éléments, cette session ne peut pas être traitée
correctement" — (1) the **backtest transcript** (live trading shown), (2) the
**pedagogical transcript** (how the owner analyses on TradingView), (3) access
to the **Ichor-beta trading-meeting hub** (bilans, leçons, incohérences). None
are in the repo today.

**9.3 — Couche-1 fallback architecture** (carried from
`S04_FINALIZATION_PROGRAM.md` §Architecture; flagged repeatedly in memory as
"the one remaining decision"). Couche-1 generation has **zero LLM fallback**
(verified: `run_briefing.py:536-545` fails loud; `fallback.py:4` wraps
Couche-2 only) while `ADR-009:61` + `run_briefing.py:22-25` _document_ a
Cerebras→Groq→template chain. Options: **(A)** accept premium-only fail-loud
and reconcile the docs (consistent with Voie-D ToS posture); **(B)** add a
degraded Cerebras/Groq briefing path behind an explicit "degraded provenance"
watermark (HA, but rubs against the Max-20x single-user premise). This is a
risk-appetite call on existential risk #1 (§6.1).

---

## 10 · Verification record (honesty)

- Every load-bearing claim in §0/§3/§7 was **verified directly at source**
  (file:line) by the lead, not taken from sub-agent report alone.
- Asset universe (re-verified 06-10, **correcting v2**): **verdict scope = 5**
  (`PriorityAsset`, == the vision's "5 actifs"); **autonomous card batch = 6**
  (`_DEFAULT_ASSETS`, ADR-083 D1 — v2's note "there is no 6" was itself wrong);
  **data/collection layer = 8** (`_PHASE1_ASSETS`).
- v3 verification run (06-10 AM): 30 load-bearing claims re-checked at source
  by 15 fresh read-only agents (`wf_17c396c2`) → 26 CONFIRMED / 4 PARTIAL,
  folded in. v4 run (06-10 PM, `wf_dc5c71eb`, 18 fresh agents): 25 claims
  re-refuted → 18 CONFIRMED / 7 PARTIAL (zero REFUTED — v3's facts held),
  every PARTIAL folded into §3/§6/§7; + 8-file spec-fidelity audit (§5ter-bis)
  - the prod verification below.

### 10.1 · Prod-only zones — CLOSED (witnessed on the Hetzner host, 2026-06-10 ~19:30 CEST, read-only)

The three zones v3 admitted it could not verify from the repo:

1. **Feature flags (prod DB, table `feature_flags`)**: 12 flags, **all ON**
   (enabled=t, rollout 100) — incl. `streaming_refresh_enabled`,
   `brain_web_research_enabled`, `actuals_reconciler_enabled`,
   `phase_d_w115c_confluence_enabled`, both ADR-105 market-closed gates.
   **The single un-armed flag**: `scenario_invalidation_monitor_enabled` is
   **absent** from the table → OFF by fail-closed semantics
   (`feature_flags.py:137`). Code↔DB cross-check exhaustive: no other orphan
   on either side.
2. **Systemd liveness**: **102 ichor-\* timers** (not ~59), none
   never-scheduled, `NRestarts=0` on the critical collectors; cot / ecb_sdmx /
   bls / eia_petroleum / eia-crude-stocks / ai_gpr / fred / fred_extended /
   polymarket / streaming-refresh all exit 0 and on schedule. (LLM-dependent
   units were failed that day — see 10.2.)
3. **Polymarket & geopolitical series**: `polymarket_snapshots` fresh (424,782
   rows; last fetch ≈1 min before the check; 10,553 rows/24h; 30 open slugs —
   Iran/Israël, Fed June meeting ×5, BTC ladder…). `gdelt_events` fresh
   (1,501/24h, last article ~1h15 old). `gpr_observations` **stale upstream**
   (last observation 2026-06-01; the nightly collector runs clean and reports
   "persisted 0 new rows" — Caldara-Iacoviello publication lag, not a fault).
   Prod `alembic_version` = **0055** = local head.

### 10.2 · Same-day P0 caught & repaired (2026-06-10) — the re-challenge's reason to exist

- **Symptom**: 0 session cards generated all day (last cards 06-09 evening);
  briefings pre_londres/pre_ny/ny_mid failed exit 4; Couche-2 5/5 failed
  (`AllProvidersFailed: claude=ClaudeRunnerError, cerebras/groq=MissingCredentials`).
  **Two masking layers**: session-cards units showed `Result=success` despite
  `0 ok / 6 failed` (`SuccessExitStatus=0 1`), and API healthz reports
  `claude_runner_reachable=null` (never probes the runner).
- **Root cause**: Win11 host rebooted 02:36; the standalone runner relaunched
  03:46 **while the npm CLI update to 2.1.170 raced it** → the launch-time
  `claude.exe` probe resolved empty/stale → every spawn died
  `FileNotFoundError [WinError 2]`. Third occurrence of this class (05-29,
  06-02, 06-10).
- **Repair + witness (19:54–20:05 CEST)**: native `claude.exe` verified
  (2.1.170) → stale process killed, runner relaunched via the self-probing
  `.bat` → `ichor-couche2@cb_nlp` re-fired from Hetzner: **`couche2.run.ok
attempt=1 model=claude:opus`, async through the tunnel in 15.6 s, exit 0** — then
  macro/news_nlp/positioning/sentiment all `success`; zero Couche-2 units
  failed. The repair witness also **proves the tunnel routes to :8766**.
  Natural full witness = the 22:01 ny_close batch (6 cards).
- **Carry-over**: morning-window briefing units stay marked failed until
  their next scheduled runs (windows passed; regenerating them off-window
  would fabricate freshness). Chantier D owns killing this class (§6.5).

### 10.3 · v4 claim corrections folded (7 PARTIAL)

`fallback` chain truth → §6.1 · 58 sections exact / 4 missing in
ARCHITECTURE.md → §7 · second `_VALID_ASSETS`=6 → §7 · third (LLM-channel)
technical path to the apex sign → §3 · effort `high` = caller convention, not
an enforced cap; runner schema already accepts `xhigh`/`max`, but its model
Literal **lacks `fable`** → §5 transverse · per-instance semaphore + :8765
zombie → §6.2 · three closed loops, not one → §3.
