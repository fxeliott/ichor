# VISION 2026 — Ichor pushed further

> **Date** : 2026-05-03 evening
> **Author** : Claude (autonomy-mode synthesis post-audit)
> **Status** : proposed addendum to [ADR-017](decisions/ADR-017-reset-phase1-living-macro-entity.md). Not contractual yet — Eliot validates by approving any sprint that draws from this file, or rejects by asking for amendments.
> **Why this exists** : ADR-017 froze a sound 12-capability architecture. The audit 2026-05-03 + 4 web searches surfaced 17 additional capabilities that institutional desks (Permutable AI, Aladdin AI agents, Bloomberg, hedge fund AI agents 2026) routinely ship and that Ichor must absorb to deliver the _"as if every top hedge fund and institution was rolled into one entity"_ mandate Eliot stated.

This file does NOT replace ADR-017. It lists the **17 deltas** Ichor needs on top of ADR-017's 12 capabilities, organized by the same 4-layer taxonomy (perception → analysis → memory → expression).

---

## 0. Calibration vs the field

| Capability                                | ADR-017 v1  | Permutable AI | Aladdin AI agents | Bloomberg  | Ichor v2 (this doc)              |
| ----------------------------------------- | ----------- | ------------- | ----------------- | ---------- | -------------------------------- |
| Real-time narrative clustering            | ❌          | ✅            | –                 | ✅ partial | ✅ (delta L)                     |
| Cross-asset regime detection              | partial     | –             | ✅                | –          | ✅ (delta E)                     |
| Public Brier-score calibration            | ✅          | –             | –                 | –          | ✅ kept + extended (delta H)     |
| Dealer gamma flip / 0DTE flow             | ❌          | –             | –                 | ✅         | ✅ (delta C)                     |
| Funding stress live (SOFR-IORB / FRA-OIS) | ❌          | –             | ✅                | ✅         | ✅ (delta B)                     |
| CB intervention probability               | ❌          | –             | –                 | –          | ✅ **unique to Ichor** (delta D) |
| Counterfactual reasoning                  | Phase 5     | –             | –                 | –          | ✅ **unique to Ichor** (delta J) |
| Polymarket↔Kalshi divergence detection    | ❌          | –             | –                 | –          | ✅ **unique to Ichor** (delta M) |
| Living UI (régime-colored ambient)        | ✅ skeleton | –             | ❌                | ❌         | ✅ extended (delta N-Q)          |
| Knowledge graph navigable                 | partial     | –             | –                 | –          | ✅ (delta K)                     |
| Time-machine replay                       | ❌          | –             | –                 | –          | ✅ **unique to Ichor** (delta P) |

**Strategic positioning** : Ichor's edge is not data breadth (Bloomberg wins) nor execution (Aladdin wins). It is the **synthesis quality + transparent calibration + living UI for one trader's pre-session ritual** — three axes nobody else combines.

---

## 1. PERCEPTION layer — 6 new collectors / data axes

### Delta A — Order-flow microstructure stack

**Status** : missing in ADR-017 collector list
**Why** : Eliot's strategy targets session momentum origins ("origine vendeuse passé qui a créé une poussée baissière"). Order flow proxies are the only way to know _where_ late longs/shorts got trapped (= where his retracement zones live).
**Deliverables** :

- `collectors/finra_ats.py` — FINRA ATS Weekly dark-pool prints (already on PHASE_1_LOG row 1.0.24, surface as priority)
- `collectors/finra_si.py` — FINRA Short Interest bi-monthly (row 1.0.23)
- `packages/ml/src/ichor_ml/microstructure/lee_ready.py` — Lee-Ready trade classification on intraday Polygon bars
- `packages/ml/src/ichor_ml/microstructure/kyle_lambda.py` — Kyle's lambda price-impact estimator
- `packages/ml/src/ichor_ml/microstructure/amihud.py` — Amihud illiquidity ratio rolling 30j
- existing `vpin.py` already in ml/ → wire into Pass 1 régime input

### Delta B — Funding/liquidity stack institutional

**Status** : partial (RRP/TGA/HY-IG via FRED) — missing the live banking stress signals
**Why** : USD direction reverses violently on funding squeezes. Without SOFR-IORB and FRA-OIS, Ichor will miss the 5% of days that move 50% of the year's PnL.
**Deliverables** :

- `collectors/sofr_live.py` — SOFR / IORB / RRP usage daily (NY Fed direct)
- `collectors/repo_dtcc.py` — DTCC repo data (general collateral rates)
- derived `fra_ois_spread`, `sofr_iorb_spread`, `cross_currency_basis_proxy` (synthetic from SOFR-OIS - €STR-OIS)
- `treasury_auction_tracker.py` — non-comp bid-to-cover, awarded vs WI-yield (auction tail = funding stress signal)

### Delta C — Options flow institutional (dealer positioning)

**Status** : partial (FlashAlpha GEX queued row 1.0.16) — missing 0DTE-specific
**Why** : 2026 markets are dominated by 0DTE flow on SPX/NDX. Without this, Pass 2 framework for SPX/NDX is structurally undercalibrated.
**Deliverables** :

- `collectors/flashalpha_gex.py` — implement row 1.0.16
- `packages/ml/src/ichor_ml/options/dealer_gamma.py` — call-wall / put-wall mapping (SpotGamma-style)
- `packages/ml/src/ichor_ml/options/risk_reversal.py` — 25-delta RR FX skew dynamics
- `collectors/cme_btc_futures.py` — BTC futures positioning as risk-on proxy

### Delta D — CB intervention probability (UNIQUE)

**Status** : missing entirely
**Why** : BoJ historically intervenes at 145+ USD/JPY ; SNB at 0.95 EUR/CHF ; ECB at 1.00 EUR/USD lower bound. These are tail events with regime-changing magnitude (200+ pips intraday). No vendor (Aladdin, Bloomberg, Permutable) prices intervention probability _quantitatively_ day-by-day. **This is Ichor's signature differentiator.**
**Deliverables** :

- `packages/ml/src/ichor_ml/cb_intervention/empirical_model.py` — historical intervention spots + magnitudes per CB
- `packages/ml/src/ichor_ml/cb_intervention/probability.py` — current probability given (level, vol, recent rhetoric, official threshold quotes)
- Pass 4 (invalidation) consumes this directly : "USD/JPY long invalidated above 145.50 — BoJ intervention probability 35%"

### Delta E — Surprise indices Citi-style

**Status** : missing
**Why** : Citi Eco Surprise Index is the gold-standard driver of FX risk-on/risk-off cycles. Building it from FRED + ECB + BLS + BoE is free.
**Deliverables** :

- `packages/ml/src/ichor_ml/surprise/eco_index.py` — z-score (actual - consensus) per release, weighted ema, per-region G10
- consumed by Pass 1 régime ("USD positive surprise momentum 7-day +1.2σ")

### Delta F — Asian-session liquidity (USD/JPY-critical)

**Status** : missing
**Why** : USD/JPY moves are routed through Tokyo fixing 9:55 JST + JGB futures + JPY NDF rolls. Without these, USD/JPY framework is a half-build.
**Deliverables** :

- `collectors/tokyo_fixing.py` — daily 9:55 JST tracking
- `collectors/jgb_futures.py` — JGB 10Y futures basis
- `collectors/jpy_ndf.py` — JPY NDF roll rates

---

## 2. ANALYSIS layer — 4 new capabilities (Claude at maximum power)

### Delta G — Per-asset framework completion (8/8)

**Status** : 1/8 (EUR/USD only, others fall to `_FRAMEWORK_DEFAULT`)
**Deliverables** : in `packages/ichor_brain/src/ichor_brain/passes/asset.py`, add explicit dicts :

- `_FRAMEWORK_XAU` : TIPS real yields (FRED `DFII10`) + DXY + WGC quarterly CB buying + ETF flows + gold-silver ratio
- `_FRAMEWORK_USDJPY` : US-JP 10Y diff + BoJ YCC stance + JPY safe-haven flag + Tokyo fixing direction
- `_FRAMEWORK_NAS100` : mega-cap 7 earnings momentum + AI capex narrative (BERTopic) + GEX 0DTE + US10Y inverse
- `_FRAMEWORK_US30` : cyclicals + ISM manufacturing + oil + Fed
- `_FRAMEWORK_GBPUSD` : BoE NLP + UK CPI/wages + gilt 10Y
- `_FRAMEWORK_AUDUSD` : China data + iron ore + RBA + AUD COT
- `_FRAMEWORK_USDCAD` : oil WTI + BoC + Canadian CPI + rig count

### Delta H — Brier reconciler + calibration cron

**Status** : schema columns exist (`realized_*`, `brier_contribution` in `session_card_audit`), zero reconciler writes them
**Why** : without back-feedback, Ichor cannot self-improve nor publish honest calibration. ADR-017 capability #8 mandates this. Currently stub.
**Deliverables** :

- `apps/api/src/ichor_api/cli/reconcile_outcomes.py` CLI : nightly cron at 23:00 Paris
- For each closed `session_card_audit` row : fetch realized OHLC from `polygon_intraday`, compute realized direction + magnitude, write `realized_*` columns + `brier_contribution`
- `/v1/calibration` route : Brier 30/90/365 by asset × session × régime
- `/calibration` Next.js page : reliability diagram (10 bins) + sharpness histogram

### Delta I — Counterfactual reasoning agent (UNIQUE)

**Status** : Phase 5 in old plan — promote to Phase 1.2
**Why** : "If Powell hadn't said X, EUR/USD would be at Y" — this is exactly the kind of insight that makes Eliot's intuitive analysis _learn_. No competitor ships this.
**Deliverables** :

- `packages/agents/src/ichor_agents/counterfactual/` package
- Pass 5 (optional, on-demand from UI button) : Claude is given the actual session card + asked "what if event_X had not occurred — re-run Pass 2 with event_X scrubbed from context"
- UI : `<CounterfactualToggle>` per drill-down

### Delta J — Macro narrative tracker live (BERTopic)

**Status** : mentioned in ICHOR_PLAN, never coded
**Why** : "narrative-driven" is what Permutable AI sells for $$. We can build it on top of GDELT + Reddit WSB + RSS already collected.
**Deliverables** :

- `packages/ml/src/ichor_ml/nlp/bertopic_runner.py` — daily BERTopic clustering on news_items + reddit_wsb (24h / 48h / 7d windows)
- `packages/ml/src/ichor_ml/nlp/narrative_halflife.py` — track topic prevalence decay
- `narratives_daily` hypertable with topic_id, label, prevalence, drift_speed
- Pass 1 régime input : top 5 narratives + their delta vs J-1

---

## 3. MEMORY/CALIBRATION layer — 3 new capabilities

### Delta K — Knowledge graph navigable (Apache AGE frontend)

**Status** : Apache AGE installed, populator exists in `apps/api/src/ichor_api/graph/`, **frontend missing**
**Why** : "as if all institutions were rolled into one" requires showing the **causal map** Ichor uses internally.
**Deliverables** :

- `/knowledge-graph` Next.js page with `react-force-graph` (already a known good React lib)
- Click an entity (Powell, Fed, FOMC, USD, DXY, XAU) → drill-down with all sessions where this entity appeared as primary mechanism
- Pre-coded causal edges : Powell→Fed→USD→DXY→XAU ; OPEC→WTI→CAD/NOK ; ECB→EUR→DAX ; BoJ→JPY→NIKKEI

### Delta L — Causal Bayesian Network on top of KG

**Status** : Phase 4 in old plan — promote to Phase 2
**Why** : Force-directed graph is pretty but static. CBN on top makes propagation **probabilistic** : "Powell hawkish (P=0.7) → Fed hike next meeting (P=0.55|hawkish) → USD strength 7d (P=0.65|hike)".
**Deliverables** :

- `packages/ml/src/ichor_ml/causal/bn.py` (pgmpy or pyAgrum) on top of AGE relations
- Pass 2 framework can query the CBN for "given current state, P(USD strength | this Powell speech)"

### Delta M — Polymarket↔Kalshi↔Manifold divergence detector (UNIQUE)

**Status** : 3 sources collected, zero divergence logic
**Why** : 2-5% gaps = information asymmetry signal (cf. _Maduro Trade_ $400k arb, Feb 2026). Polymarket = decentralized "insider" pricing. Kalshi = retail-heavy regulated pricing. Manifold = community wisdom-of-crowds. **The gap between them is itself a tradeable feature.** Nobody surfaces this systematically.
**Deliverables** :

- `packages/agents/src/ichor_agents/predictions/divergence.py` — daily cron computing event-by-event gap (matched on similar question phrasing via embeddings)
- Alert type 28 : "Polymarket vs Kalshi divergence > 5pp on Fed-cut May meeting (Poly 62%, Kalshi 47%)"
- `/predictions` page : table of all matched events × 3 venues with gap, history, half-life, last-5-shifts

---

## 4. EXPRESSION layer — 4 new UI capabilities (the "ultra-design vivant")

### Delta N — Régime-colored ambient global accent (ADR-017 cap. #11 fully delivered)

**Status** : skeleton in `<RegimeIndicator>`, no global accent
**Deliverables** :

- Zustand store `useRegimeStore` (currently 0 zustand usage in code despite installed)
- Tailwind data-attribute `data-regime={haven_bid|funding_stress|goldilocks|usd_complacency}` on `<html>`
- CSS custom properties switch primary/accent colors live
- Smooth `motion` transition 800ms when régime flips

### Delta O — Living dashboard mosaic

**Status** : missing
**Inspiration** : Bloomberg Terminal multi-monitor, Fortress Next.js template, Vault Robinhood-style
**Deliverables** :

- `/` redesign : 3 columns desktop / 2 tablet / 1 mobile
  - Left rail : 8-asset cross-asset heatmap (biais × magnitude × confidence) + 4-quadrant régime widget
  - Center : current session card focus (auto-rotates per the active session window) + scenarios bars + invalidation conditions
  - Right rail : live event ticker (Bloomberg-tape) + Polymarket pulse + alert feed
- `motion` for entry/exit + count-up animations
- `lightweight-charts` for the price overlay (with attribution)

### Delta P — Time-machine slider (UNIQUE)

**Status** : missing
**Why** : Eliot wants to _understand_ why the system says what it says. Replay = ultimate trust-building.
**Deliverables** :

- `/replay/[asset]` page : slider over the last 30/90 days, plays back biais/régime/scenarios as the data arrived
- Pause + step-forward + step-backward + 2x speed
- "Current verdict at T" + "data points that arrived since T"

### Delta Q — Globe géopolitique 3D

**Status** : missing
**Why** : GDELT + AI-GPR + ACLED data are 2D-listed today. Globe makes geographic context immediate (oil shipping lanes, conflict zones near refineries, etc.).
**Deliverables** :

- `react-globe.gl` (or `@react-three/fiber` + custom) on `/geopolitics` page
- Hot zones : GDELT critical clusters, GPR spikes, OFAC sanctions, NOAA hurricanes
- Click country → drill-down (recent events × asset proximity)

---

## 5. Full sprint topology (proposed atomic order)

> **Each sprint = one git commit minimum. Tests must stay green. No push to origin without Eliot OK.**

| Sprint   | Title                                                                                                                                            | Deltas covered                     | Effort               | Blockers                                                         |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------- | -------------------- | ---------------------------------------------------------------- |
| **A** ✅ | Sprint A — Audit + XAU fix + docs                                                                                                                | –                                  | done in this session | none                                                             |
| **B**    | UI vivante v1 — wire 4 deps + heatmap + régime quadrant + ChartCard live                                                                         | N partial, O partial               | 1 session            | none                                                             |
| **C**    | Brier reconciler + `/calibration` page                                                                                                           | H                                  | 1 session            | needs ≥1 closed session card with realized OHLC                  |
| **D**    | 7 asset frameworks (XAU + USD/JPY + NAS100 + US30 + GBPUSD + AUDUSD + USDCAD)                                                                    | G                                  | 2 sessions           | none                                                             |
| **E**    | Pré-NY cron + register on Hetzner + first end-to-end --live EUR/USD                                                                              | –                                  | 1 session            | needs Polygon key + ADR-010 relogin + ADR-011 CF Tunnel exposure |
| **F**    | Polymarket↔Kalshi↔Manifold divergence detector + `/predictions` page                                                                             | M                                  | 1 session            | none                                                             |
| **G**    | 11 missing collectors (priority : eco calendar, BLS, ECB SDMX, EIA, BoE, Treasury DTS, FlashAlpha GEX, VIX live, AAII, Reddit WSB, FINRA SI/ATS) | A partial, B partial, C partial, E | 3-4 sessions         | none                                                             |
| **H**    | Funding stress + CB intervention probability                                                                                                     | B, D                               | 2 sessions           | none                                                             |
| **I**    | Macro narrative tracker BERTopic live                                                                                                            | J                                  | 1 session            | needs ≥30 days of news_items                                     |
| **J**    | Knowledge graph frontend `/knowledge-graph` (force-graph) + CBN                                                                                  | K, L                               | 2 sessions           | AGE populator already exists                                     |
| **K**    | Counterfactual reasoning Pass 5 on-demand                                                                                                        | I                                  | 1 session            | none                                                             |
| **L**    | Time-machine replay `/replay/[asset]`                                                                                                            | P                                  | 1 session            | needs ≥7 days of session_card_audit history                      |
| **M**    | Globe géopolitique 3D `/geopolitics`                                                                                                             | Q                                  | 1 session            | none                                                             |
| **N**    | Voice briefing player + Azure FR TTS                                                                                                             | – (ADR-017 cap. #11 audio)         | 1 session            | needs Azure Speech key                                           |
| **O**    | Mobile PWA companion                                                                                                                             | ADR-017 cap. #12                   | 1 session            | needs VAPID setup                                                |
| **P**    | 24/7 event-driven persistent agent (vs cron)                                                                                                     | ADR-017 cap. final                 | 2 sessions           | requires Phase 1-3 stable                                        |

**Total** : ~20 sessions of focused work to ship Ichor v2 full vision. Sprint B-D is the critical path for "system that delivers value before each session" (= Eliot's MVP-2). Sprints G-I are the "feels omniscient" upgrade. Sprints J-P are the "feels alive" upgrade.

---

## 6. What this file does NOT change

- ADR-017 is the contract. This file proposes additions, not amendments.
- Voie D (ADR-009) stays. No Anthropic API consumption ever.
- Cost ceiling **updated to $269/mo** (Massive Currencies $49/mo — the
  correct plan ; ADR-017's original $29 was a mistake, the Stocks
  Starter doesn't cover forex). $20 over the original ceiling, but
  the Currencies key also unlocks 5 bonus endpoints free :
  - News API (`/v2/reference/news`) — ticker-linked news, integrated
    in `collectors/polygon_news.py` 2026-05-03
  - Market Status (`/v1/marketstatus/now`) — live FX/crypto/exchanges
  - Crypto snapshot (`/v2/snapshot/.../crypto/...`) — BTC proxy for
    risk-on regime input (delta C extension)
  - Currencies snapshot global — 1-call multi-pair refresh
  - Reference Tickers — full FX catalog for narrative tracker
- AMF DOC-2008-23 + EU AI Act Article 50 + Anthropic Usage Policy : all maintained.
- Ichor never executes orders. Eliot trades on TradingView.

---

## 7. Open questions (decisions taken in autonomy until Eliot says otherwise)

| #   | Question                                                                                                    | Default decision (autonomy)                                                      |
| --- | ----------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| 1   | Polygon Starter $29 (ADR-017) or Massive Currencies $49 (memory) ?                                          | Stick with ADR-017 = $29 Starter. Re-evaluate when Eliot subscribes.             |
| 2   | Push origin/main 5 commits ahead ?                                                                          | NOT without explicit "go push" — CLAUDE.md non-negotiable                        |
| 3   | ML regime detection upgrade : standard HMM (hmmlearn) or non-homogeneous Bayesian HMM (cf. 2026 preprint) ? | Stay hmmlearn Phase 1, upgrade to dynamax JAX Phase 2-3 if needed                |
| 4   | Charts library : keep `lightweight-charts` (already installed) or add `tremor` (Vercel-backed) ?            | Keep `lightweight-charts`, add `tremor` only if a specific component needs it    |
| 5   | Globe library : `react-globe.gl` or custom `@react-three/fiber` ?                                           | `react-globe.gl` (faster ship, good enough)                                      |
| 6   | KG frontend lib : `react-force-graph` or `sigma.js` ?                                                       | `react-force-graph` (already mentioned in ICHOR_PLAN)                            |
| 7   | UI template inspiration : Fortress paid $69 or Tremor free ?                                                | Tremor free + custom (closer to ADR-017 design tokens already in `packages/ui/`) |

---

## 8. Hallucination guard

Every numeric assertion in a session card MUST :

1. Have an attached source URL + timestamp pulled at fetch time.
2. Be cross-corroborated by ≥2 independent sources when published as a "fact" (vs an estimation).
3. Show a staleness flag if `now() - source_timestamp > threshold`.
4. Be auditable from the UI : click a number → source provenance modal.

This is the institutional-grade anti-hallucination floor that distinguishes Ichor from "ChatGPT trader" toys.

---

## 9. Closing — calibration of Ichor's identity

Ichor v2 = **(Permutable AI narrative engine) ∪ (Aladdin agentic stress-tests) ∪ (Bloomberg multi-monitor depth) ∪ (Polymarket prediction-market truth-engine)**, but :

- single-trader-focused (not institutional sales-driven)
- transparent calibration (Brier publicly tracked, not hidden behind PM)
- macro/geo/sentiment only (no AT — Eliot owns the chart)
- Voie D economic model (no per-token costs)
- French-language briefings
- non-prescriptive (never tells Eliot to BUY/SELL — only "current macro context, here's the risk and conviction")

That's a niche of one. Which is exactly the point — this isn't built to compete in B2B, it's built to give _one_ discretionary trader the institutional macro tailwind he is currently missing.

---

_Document maintained by Claude. Update on every sprint that delivers a delta. Eliot can amend at will — this is a proposal, not a contract._

Sources cited :

- [Permutable AI macro intelligence](https://permutable.ai/macro-trends-market-sentiment-top-vendors/)
- [AI Agents in Hedge Funds 2026 — Digiqt](https://digiqt.com/blog/ai-agents-in-hedge-funds/)
- [Polymarket vs Kalshi divergence — FinancialContent](https://markets.financialcontent.com/stocks/article/predictstreet-2026-2-5-the-great-prediction-war-polymarket-vs-kalshi)
- [HMM regime detection 2026 preprint — Preprints.org](https://www.preprints.org/manuscript/202603.0831)
- [Multimodal probabilistic forecasting with calibrated uncertainty — ScienceDirect 2026](https://www.sciencedirect.com/science/article/pii/S2666827026000058)
- [Brier score in probabilistic forecasting — Emergent Mind](https://www.emergentmind.com/topics/brier-score)
- [SMC pre-session bias framework — ACY](https://acy.com/en/market-news/education/market-education-london-session-high-low-day-smart-money-j-o-20250811-120907/)
- [Fortress Next.js trading dashboard template — DashboardPack](https://dashboardpack.com/templates/next-js/)
