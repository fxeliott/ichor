# PLAN DIRECTEUR ICHOR — Master plan (9-session arc)

> **Created: 2026-06-05 (Session 01/09 — Cadrage & plan directeur).**
> Canonical 9-session execution arc. Distinct from [`ROADMAP.md`](ROADMAP.md)
> (round-based running log) — this file is the **strategic spine** that
> Sessions 02→09 align to. Built from an exhaustive read-only audit
> (6 parallel sub-agents + direct verification). No production code was
> written in Session 01.

---

## 0 · The honest verdict (read this first)

1. **Ichor is NOT "1% done". It is a mature, impressive system.** A rebuild
   would destroy value. The job is **deepen + harden + make-trustworthy**,
   not restart.
2. **Breadth of the "cover everything" vision is ~achieved**: coverage
   matrix = **9 dimensions COVERED / 5 PARTIAL / 0 MISSING** out of 14.
   The gap is **depth & fusion**, not absence.
3. **The "50/50 coin-flip" complaint is TRUE — root cause located in code**
   (not a guess): conviction is computed from Pass-6 bucket masses only,
   the rich evidence base is not mathematically fused into it, and the
   self-improvement loop that was meant to calibrate the dead-zone was
   never activated.
4. **The #1 lived problem is reliability**: the live pipeline is
   **intermittent** — last `ny_close` batch produced 0/6 cards, all 5
   Couche-2 agents are failing. A live product that shows stale/missing
   data as "real-time" is the worst failure mode (the 2026-05-29 lesson).
5. **A live product's real health = content FRESHNESS + COHERENCE**, not
   green tests. Every "done" below is defined on that basis.

---

## 1 · Vision (reformulated, faithful)

Ichor = a single, massive, fully-interconnected system that **anticipates
the New York session on 5 assets** (EUR/USD, GBP/USD, XAU/USD, SPX500,
NAS100 — the code currently handles 6, incl. USD_CAD) with its **own
founded, motivated conviction — never a 50/50**. It must:

- **Cover the whole field of trading** (macro, fundamental, monetary,
  geopolitics, flow, positioning, sentiment, intermarket, options
  structure, seasonality…), **in real time + via APIs**, continuously.
- **Reason with Opus 4.8 "extra" everywhere**, understand the market like
  an embodied market-intelligence with decades of experience, and
  **self-improve** from past lessons.
- **Explain everything as a beginner-level COACH** ("why / how / what to
  watch") inside an **ultra-premium web UI**.
- Stay aligned to the owner's method: NY momentum bull/bear/range, working
  window **14h–20h Paris**, and the **ADR-017 boundary** (bias +
  probability + pedagogy, never a BUY/SELL order).

---

## 2 · State of the art — audited, atom-level

### 2.1 Backend / data / pipeline — **MATURE**

- **49 routers** · **104 services** · `data_pool.py` = **54 `_section_*`
  builders** (source-stamped) · **47 collectors** · **58 CLI runners** ·
  alembic head **`0054`** (`apps/api/migrations/versions/`). _(Counts
  verified directly 2026-06-05 — not sub-agent estimates.)_
- Orchestration = **systemd timers on Hetzner** (confirmed live).
- Exploratory/low-integration stubs: `meta_prompt_tuner.py`,
  `gepa_optimizer.py`, `couche2_context.py`.

### 2.2 The brain — **MATURE; conviction under-exploited**

- 6-pass pipeline: Régime → Asset → Stress → Invalidation (**Opus 4.8
  effort `high`**) + Pass-6 Scenarios 7 buckets (Sonnet 4.6). 5 Couche-2
  agents = **Opus 4.8 effort `low`** (ADR-108 supersedes ADR-023's model
  choice; the async-polling path ADR-067 removed the CF-timeout reason for
  Haiku).
- `FRENCH_COACH_DIRECTIVE` SSOT at `packages/ichor_brain/.../passes/base.py:37-64`
  enforces coach-FR tone on every pass. **Voie D intact** (zero Anthropic SDK).
- **Weakness**: the Critic only checks **source traceability**, not
  **factual accuracy** (phase-2 LLM critic unimplemented).
- **Pass-6 IS active in production** (verified): the cron
  `register-cron-session-cards.sh` passes `--live` →
  `run_session_card.py:278 enable_scenarios=live` (`:578 live = "--live" in args`).
  The orchestrator default `enable_scenarios=False` (`orchestrator.py:114`)
  applies only to dry-runs.

### 2.3 Frontend — **ALREADY PREMIUM (not a rebuild)**

- **46 routes** · OKLCH 3-layer design system + aurora cobalt + glass/glow
  (verified, not generic) · `/briefing/[asset]` deep-dive = 6 collapsible
  sections A–F + scroll-spy · verdict apex freshness-gated · coach-FR SSOT
  (`coachLabels.ts`, `sessionVerdict.ts`, `fredLabels.ts`).
- **Gap**: pedagogy is _implicit_ (integrated) rather than _explicit_ for a
  total beginner; `/learn` (**15 pages**) decoupled from briefing; narrative
  cohesion A→B→C to make explicit; mobile polish.

### 2.4 LIVE state right now — **⚠️ INTERMITTENT (most important fact)**

- Win11 runner :8766 **up** (`claude_cli_available:true`). Public API
  **200**. DB schema **0054**. Timers armed.
- 6 priority assets **fresh ~6h** (last good batch = `ny_mid`).
- **`ny_close` 22h = 0/6 cards** (empty runner responses); none since 06-03.
- **5 Couche-2 agents + 2 briefings FAILING** (`ClaudeRunnerError` / `501`
  / empty-JSON; fallback creds cerebras/groq missing).
- Root cause = **Win11 runner instability under load**. web2 served via a
  per-restart `*.trycloudflare.com` quick tunnel (**no stable URL** — the
  long-standing named-tunnel gap).

### 2.5 Coverage matrix (14 dimensions) — **9 / 5 / 0**

| Dimension                                          | Verdict | Evidence                                                                                                 |
| -------------------------------------------------- | ------- | -------------------------------------------------------------------------------------------------------- |
| Macroeconomics (growth/inflation/employment/cycle) | COVERED | `_section_macro_trinity`, `_section_nyfed_mct`, `_section_cleveland_fed_nowcast`, `regime_classifier.py` |
| Monetary policy / rate path / STIR / FedWatch      | COVERED | `services/stir.py`, `cme_zq_futures.py`, `_section_cb_speeches`                                          |
| Economic-data surprises (actuals vs consensus)     | COVERED | `_section_recent_actuals`, `economic_event_surprise.py`, `surprise_index.py`                             |
| Fiscal / liquidity (TGA, deficits, issuance)       | PARTIAL | `_section_fed_financial`, `liquidity_proxy.py`, `dts_treasury.py`; issuance/deficit thin                 |
| Geopolitics                                        | COVERED | `_section_geopolitics`, `ai_gpr.py`, `gdelt.py`                                                          |
| Interconnexions / cross-asset / dollar coherence   | COVERED | `_section_cross_asset_matrix`, `cross_asset_dollar_coherence.py`, DXY-9 (UUP proxy)                      |
| Positioning (CFTC, retail)                         | COVERED | `_section_cot`, `_section_tff_positioning`, `_section_myfxbook_outlook`                                  |
| Sentiment / news NLP / CB NLP                      | COVERED | `_section_news`, `_section_aaii`, Couche-2 cb_nlp/news_nlp/sentiment                                     |
| Options structure / dealer gamma / vol regime      | COVERED | `_section_tail_risk_skew`, `_section_vix_term`, `_section_key_levels` (gamma flip/walls)                 |
| Price-action / flow / microstructure (VPIN/OFI)    | PARTIAL | `microstructure.py` exists; theme `price_action_flow` driver baseline-only                               |
| Supply/demand (commodities, EIA)                   | PARTIAL | `eia_petroleum.py` (crude only); no metals/ags/inventory breadth                                         |
| Seasonality / time-of-day / session structure      | COVERED | `_section_previous_session_context`, `_section_london_session`, `_section_hourly_vol`                    |
| Theme classification (dominant driver)             | PARTIAL | `theme_classifier.py` 6/8 drivers; `fiscal_policy`/`price_action_flow` baseline                          |
| Prediction markets (Polymarket)                    | COVERED | `_section_prediction_markets`, `polymarket_impact.py`                                                    |

---

## 3 · The 3 gaps (vision ↔ reality) = the real work

### 🅰 RELIABILITY — _the pipeline lies intermittently_ (top priority)

Whole batches silently empty + Couche-2 down + stale-shown-as-fresh + no
stable URL. **Until fixed, every other improvement renders on quicksand.**

### 🅱 CONVICTION — _the "50/50", exact root cause_

- `session_verdict_builder.py:135` → `conviction = max(bullish_mass,
bearish_mass) × 100` (cap 95).
- `:61` `_DIRECTIONAL_DEAD_ZONE = 0.15` → spread < 15pp ⇒
  `("neutral", 0.0)` (`:131-132`).
- The 54 data sections, the **confluence_engine (10 factors)**, the theme
  classifier, the cross-asset dollar coherence **do NOT mathematically feed
  the conviction** — only the narrative/buckets, indirectly.
- The **Phase-D self-improvement loops (Vovk, Brier, ADWIN) are dormant**
  (flag off): they _log_ but never **feed back** weights — although
  `:58-60` states the dead-zone was _meant_ to be calibrated by that loop.

> **Image: a Ferrari engine (the evidence) bolted to a bicycle gearbox
> (conviction = one `max()` over 6 numbers).** Killing the 50/50 = **fuse
> the evidence into conviction** + calibrate the dead-zone + **close the
> learning loop** — all ADR-017-safe (bias + probability, never an order).

### 🅲 PEDAGOGY — _premium but implicit_

Make the beginner coach layer explicit (first-visit primer, inline glossary
"what is this %?", briefing→/learn deep-links, narrative cohesion, mobile).
**Note**: auto-rebuilding the frontend daily would be an anti-pattern
(drift, destroys the premium system). Correct design = **controlled
elevation** + optionally continuous regeneration of **content** (coach
narration), **never the structure**.

---

## 4 · Target architecture (the interconnected system)

```
   REAL-TIME COLLECTION (47 collectors + 5-min news feed) — Voie D, source-stamped
                                  │
        ┌─────────────────────────┴──────────────────────────┐
        │   DATA POOL (54 sections) — Ichor's world-memory     │
        └─────────────────────────┬──────────────────────────┘
                                  │
        ┌──────────── COUCHE-2 (5 agents Opus low) ────────────┐  enrichment
        └─────────────────────────┬──────────────────────────┘
                                  │
   ┌──────────── SYNTHESIS (the "interconnected" link) ─────────────┐
   │  theme_classifier 8/8 · confluence_engine 10 factors ·         │
   │  cross-asset coherence                                         │
   └─────────────────────────────┬─────────────────────────────────┘
                                  │  (← TODAY: feeds narrative, NOT conviction)
        ┌──────── BRAIN 4-pass + Pass-6 (Opus 4.8 high) ───────┐
        └─────────────────────────┬──────────────────────────┘
                                  │
        ┌──── VERDICT (founded, evidence-weighted conviction) ──┐  ← TARGET
        │  evidence fusion + calibrated dead-zone + grounding   │
        └─────────────────────────┬──────────────────────────┘
                                  │
   ┌── LEARNING LOOP (Phase-D ON): realized → Brier → weights → conviction ──┐  ← TARGET
   └──────────────────────────────────────────────────────────────────────────┘
                                  │
        ┌──── FRONTEND COACH (premium + explicit pedagogy) ────┐
        └───────────────────────────────────────────────────────┘
```

The two **← TARGET** arrows are what turns Ichor from "probability
generator" into "an intelligence that commits and learns".

---

## 5 · Roadmap — Sessions 02 → 09

> "Done" = **fresh + coherent content, witnessed live** (not just green tests).

| #      | Session                                     | Front | Depends on | Deliverable                                                                                                                                                                                                                                                                   |
| ------ | ------------------------------------------- | ----- | ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **02** | **Reliable live substrate**                 | 🅰    | —          | Win11 runner robust (root-cause empty/501 under load: concurrency/timeout/subprocess/port; serialize or queue; self-heal/auto-restart), Couche-2 green, `ny_close` produces cards, **stable named-tunnel URL** (guided CF action). Witness: 4×/day × 6 assets fresh for ≥48h. |
| **03** | **Honest freshness & coherence everywhere** | 🅰→🅲  | 02         | Freshness gate on **every** surface, 0 displayed↔real contradiction, coherence **residuals only** (the 15 frontend leaks are ALREADY done — PR #181/#182), never "real-time" over stale data.                                                                                 |
| **04** | **Conviction engine: fuse the evidence**    | 🅱    | 02         | Evidence-weighted conviction (confluence + theme + dollar coherence fused), calibrated dead-zone, **explicit grounding** ("conviction X% because …"). ADR-017 held.                                                                                                           |
| **05** | **Close the learning loop**                 | 🅱    | 04         | Phase-D ON: realized → Brier → factor weights → conviction. Ichor **actually learns** (not just logs).                                                                                                                                                                        |
| **06** | **Deepen coverage + 8/8 synthesis**         | 🅱    | 04         | `theme_classifier` **8/8 data-driven** (price_action_flow + fiscal_policy), supply/demand beyond crude, fiscal/issuance depth.                                                                                                                                                |
| **07** | **The "alive" strides (real-time)**         | 🅱    | 02         | 5-min per-asset news feed (ADR-106 Stride 2), cross-asset **cascading reactive** matrix (Stride 6), **conviction decay/half-life** (Stride 5).                                                                                                                                |
| **08** | **Pedagogy elevation (beginner coach)**     | 🅲     | 04, 06     | First-visit primer, inline glossary, briefing→/learn links, A→B→C narrative cohesion, mobile polish. A beginner grasps "why/what-to-watch" at a glance.                                                                                                                       |
| **09** | **Hardening & durability**                  | all   | 02-08      | Observability/alerting (failures surface, no silence), Critic phase-2 (factual accuracy), doctrine/ROADMAP refresh, performance, security. "0-bug, permanent" standard.                                                                                                       |

**Dependency logic**: can't be _honest about freshness_ (03) without
_reliable_ freshness (02); a _founded conviction_ (04) needs cards that
_exist_ (02); _learning_ (05) needs the _conviction engine_ (04); _pedagogy_
(08) explains the _improved_ conviction/theme (04/06).

---

## 5bis · Backlog already-identified — reconciled into the sessions

Prior sessions already located concrete pending work (memory:
`ichor_coherence_backlog_2026-06-03.md`, `ichor_transcripts_delta_2026-06-04.md`).
Folded in here so no session rediscovers it:

- **Session 03 scope correction** — the 15 frontend coherence leaks are
  **ALREADY closed** (PR #181 `coachLabels` SSOT + PR #182 `ea5fc0c` backend
  prose enum/`Pass N` scrub, witnessed prod). Session 03 = **freshness gates**
  - **residuals only**: shared `live`/`offline` pill → one SSOT component;
    minor EN mock chrome (`/sessions`, `/today` checklist, Polymarket FR theme
    map); backend `note` fields (yield-curve, `vix.interpretation`, StirPanel)
    routed through `fredLabels`/coach-FR.
- **Sessions 04 + 06 (conviction + coverage)** — transcript-delta intelligence
  features, all ADR-017-safe (descriptive, Ichor surfaces / Eliot trades):
  - **AOI niveau-1/2** = `provenance` label `origin_entry` / `origin_exit` on
    `previous_session_origin_zone` (niv-2 = institutional exit zone).
  - **failed_new_extreme** = derived field on the daily-candle classifier →
    feeds SessionVerdict `nature` (momentum-exhaustion tell).
  - **5-announcement ranking** (rate decision > CPI > GDP > retail >
    employment) → weight Engine-8 baselines by theme-importance, not just bp.
  - **EUR = read Germany then France** (never an "Europe" aggregate) in
    `_section_eur_specific`; **non-weighted currency-strength index** (distinct
    from volume-weighted DXY); **geopolitics "no real catalyst"** nuance (fade
    low-grade media-rumour panic vs a real event).
- **Session 08 (pedagogy)** — DXY inverse-mechanics coach copy; "structured
  market = no edge = OUT" tooltip reinforcing the existing `TradeabilityFlag`.
- **🚫 EXPLICIT NON-GOAL (boundary)** — intrabar push/correction texture
  asymmetry (H1 / 15-min reading) is **Eliot's own technical lane** (his 20%).
  Ichor must **NOT** build it — it would drift toward entry-timing and breach
  the ADR-017 spirit. Flag, never code.

---

## 6 · Invariants (never break, all sessions)

- **ADR-017** — never BUY/SELL (bias + probability only). CI-guarded.
- **Voie D (ADR-009/108)** — zero `import anthropic`; all LLM via Win11 runner.
- **cap-95** conviction (ADR-022).
- **Couche-2 = Opus low** (ADR-108) — never hard-code `sonnet`.
- **Source-stamping** — every numeric claim traceable (Critic).
- Watermark single-source-of-truth; pure-data routes excluded (ADR-079/080).
- Feature flags fail-closed; audit logs immutable (ADR-029/077).

---

## 7 · Notes & honesty

- **Audit corrected**: an audit pass claimed "Pass-6 off by default" — false
  for production (cron passes `--live` → Pass-6 active). Verified directly.
- **Not yet read in detail** (to investigate in Session 02+): `apps/claude-runner`
  internals (the runner-instability root cause), `confluence_engine.py`
  line-by-line, the full register-cron scripts, and the **rendered prod
  output via Playwright**. The runner empty-response cause is a hypothesis
  (concurrency/timeout/subprocess) to **diagnose empirically**, not guess.
- Asset universe: vision says 5; code handles 6 (+USD_CAD). Keep 6 unless
  the owner decides otherwise.
- **Counts corrected 2026-06-05** (direct verification, not sub-agent
  estimates): **49** routers / **104** services / **54** data_pool sections /
  **47** collectors / **58** CLI / **46** web2 routes / **15** `/learn` pages /
  migration head **0054**. Earlier sub-agent figures (50/105/58/49/60+/51/11)
  were rounded or off; this doc now carries the verified numbers.
