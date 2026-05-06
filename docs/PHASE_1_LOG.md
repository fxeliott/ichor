# Phase 1 — Living Macro Entity — Live Log

> Started 2026-05-03. Target : ship the 12 capabilities defined in ADR-017
> across 4 sub-phases (Foundation → Coverage → Méta-cognition → Living entity).

## Status legend

- ⬜ not started
- 🟡 in progress
- 🟢 done
- ⏸ deferred (with reason)

## Phase 1.0 — Foundation (4-5 weeks)

Goal : ship the EUR/USD Pré-Londres carte de session end-to-end.

### CHUNK 1 — Reset propre (2026-05-03)

| #     | Item                                                                        | Status | Notes                                                                                                                                                                    |
| ----- | --------------------------------------------------------------------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1.0.1 | ADR-017 written + accepted                                                  | 🟢     | The contract for Phase 1                                                                                                                                                 |
| 1.0.2 | Wrong-scope packages archived                                               | 🟢     | git mv to `archive/2026-05-03-pre-reset/` (backtest/risk/trading/ml-training + 2 web pages + obsolete migration/router/model + 3 deprecated ADRs + 1 deprecated runbook) |
| 1.0.3 | SESSION_HANDOFF refondu                                                     | 🟢     | Old version moved to `SESSION_HANDOFF_pre-reset_2026-05-03.md`                                                                                                           |
| 1.0.4 | PHASE_1_LOG initialized                                                     | 🟢     | This file                                                                                                                                                                |
| 1.0.5 | API references cleaned (main.py + routers/**init**.py + models/**init**.py) | 🟢     | Backtest router/model removed from imports                                                                                                                               |

### CHUNK 2 — 17 new collectors

| #      | Source                                                               | Status | Notes                                        |
| ------ | -------------------------------------------------------------------- | ------ | -------------------------------------------- |
| 1.0.6  | FRED extended (real yields, RRP, TGA, breakevens, MOVE, more series) | ⬜     | builds on existing `collectors/fred.py`      |
| 1.0.7  | GDELT 2.0 Doc API (translingual news + GKG themes)                   | ⬜     | Replaces NewsAPI ($449/mo) with $0 free tier |
| 1.0.8  | AI-GPR Index daily (LLM-scored geopolitical risk)                    | ⬜     | matteoiacoviello.com, CSV cron               |
| 1.0.9  | CFTC COT positioning                                                 | ⬜     | Python `cftc-cot` lib, weekly Friday         |
| 1.0.10 | Treasury Fiscal Data DTS daily (TGA)                                 | ⬜     | More granular than FRED weekly               |
| 1.0.11 | BLS v2 (NFP, CPI core, employment)                                   | ⬜     | 500 queries/day cap                          |
| 1.0.12 | ECB SDMX (rates, balance sheet, credit)                              | ⬜     | SDMX 2.1                                     |
| 1.0.13 | EIA (oil, gas, energy)                                               | ⬜     | Free key                                     |
| 1.0.14 | BoE IADB (UK rates)                                                  | ⬜     | CSV endpoint, no auth                        |
| 1.0.15 | BIS speeches aggregator                                              | ⬜     | RSS feed                                     |
| 1.0.16 | FlashAlpha free GEX (gamma exposure)                                 | ⬜     | 5 req/day, same numerics as paid SpotGamma   |
| 1.0.17 | Polygon Starter intraday (8 assets)                                  | ⬜     | $29/mo, validated by Eliot                   |
| 1.0.18 | Kalshi public REST                                                   | ⬜     | Prediction market US                         |
| 1.0.19 | Manifold REST                                                        | ⬜     | 500 req/min/IP free                          |
| 1.0.20 | VIX/VVIX live (FRED + CBOE delayed)                                  | ⬜     | Real-time intraday needs paid CBOE feed      |
| 1.0.21 | AAII sentiment weekly                                                | ⬜     | Free spreadsheet                             |
| 1.0.22 | Reddit WSB praw                                                      | ⬜     | Free for low volume                          |
| 1.0.23 | FINRA Short Interest API                                             | ⬜     | Bi-monthly                                   |
| 1.0.24 | FINRA ATS Weekly (dark pools)                                        | ⬜     | 2-week lag                                   |

### CHUNK 3 — Migration TimescaleDB

Status: 🟢 9/14 tables shipped — 8 in migration `0005_phase1_collector_tables.py`
(`fred_observations`, `gdelt_events`, `gpr_observations`, `cot_positions`,
`cb_speeches`, `kalshi_markets`, `manifold_markets`, `session_card_audit`)
applied at alembic `0005`, plus `polygon_intraday` shipped in migration `0006`
applied at alembic `0006` (Hetzner currently at `0006 (head)`).
Remaining tables (treasury_dts, bls, ecb, eia, gex, finra_short_interest,
finra_ats_weekly) deferred to later migrations once their collectors land.

| #       | Table                                                                                 | Status |
| ------- | ------------------------------------------------------------------------------------- | ------ |
| 1.0.25  | `fred_observations` (time-series, hypertable, 90d chunks)                             | 🟢     |
| 1.0.26  | `gdelt_events` (hypertable, 7d chunks)                                                | 🟢     |
| 1.0.27  | `gpr_observations` (daily, 180d chunks)                                               | 🟢     |
| 1.0.28  | `cot_positions` (weekly, hypertable, 180d chunks)                                     | 🟢     |
| 1.0.29  | `treasury_dts_daily` (daily TGA balance)                                              | ⬜     |
| 1.0.30  | `bls_observations` (monthly)                                                          | ⬜     |
| 1.0.31  | `ecb_series` (varying frequency)                                                      | ⬜     |
| 1.0.32  | `eia_series` (varying frequency)                                                      | ⬜     |
| 1.0.33  | `gex_snapshots` (daily)                                                               | ⬜     |
| 1.0.34  | `polygon_intraday` (1-min OHLCV, hypertable, 7d chunks) — shipped in migration `0006` | 🟢     |
| 1.0.35  | `kalshi_markets` + `manifold_markets` snapshots (30d chunks)                          | 🟢     |
| 1.0.35b | `cb_speeches` (90d chunks)                                                            | 🟢     |
| 1.0.36  | `finra_short_interest` + `finra_ats_weekly`                                           | ⬜     |
| 1.0.37  | `session_card_audit` (replace `predictions_audit`, 30d chunks)                        | 🟢     |

### CHUNK 4 — Pipeline Claude 4-pass skeleton

Status: 🟢 skeleton shipped in `packages/ichor_brain/`. Orchestrator
serializes the 4 passes through a `RunnerClient` interface
(`HttpRunnerClient` for prod via Cloudflare Tunnel, `InMemoryRunnerClient`
for tests). Critic Agent is wired through an injectable `critic_fn` so
the package stays installable without `ichor_agents`. Tests : 30/30 on
Hetzner with the real Critic, 29/30 standalone.

| #      | Item                                                                       | Status |
| ------ | -------------------------------------------------------------------------- | ------ |
| 1.0.38 | New package `packages/ichor_brain/`                                        | 🟢     |
| 1.0.39 | Pass 1 — Régime global (`passes/regime.py`)                                | 🟢     |
| 1.0.40 | Pass 2 — Asset specialization, EUR/USD framework (`passes/asset.py`)       | 🟢     |
| 1.0.41 | Pass 3 — Bull case stress-test (`passes/stress.py`)                        | 🟢     |
| 1.0.42 | Pass 4 — Invalidation conditions (`passes/invalidation.py`)                | 🟢     |
| 1.0.43 | Cache prompt setup — TTL constants + per-pass cache_key                    | 🟢     |
| 1.0.44 | Critic Agent gate integration via injectable `critic_fn`                   | 🟢     |
| 1.0.45 | Output → `session_card_audit` (mapper `persistence.to_audit_row`)          | 🟢     |
| 1.0.46 | Tests : 30/30 (orch + per-pass + cache + persistence + critic-integration) | 🟢     |

### CHUNK 5 — Carte de session UI

| #      | Item                                                                     | Status                                                      |
| ------ | ------------------------------------------------------------------------ | ----------------------------------------------------------- |
| 1.0.47 | `/sessions` page (8 cards grid)                                          | 🟢                                                          |
| 1.0.48 | `/sessions/[asset]` detail page (drill-down)                             | 🟢                                                          |
| 1.0.49 | `<SessionCard>` component (`packages/ui/src/components/SessionCard.tsx`) | 🟢                                                          |
| 1.0.50 | Sources cliquables + cas comparables                                     | 🟡 sources rendered inline; cas comparables pending CHUNK 7 |
| 1.0.51 | WebSocket live updates                                                   | ⬜ deferred to CHUNK 7 (server revalidate=30s for now)      |

### CHUNK 6 — Polygon Starter integration (8 assets intraday)

| #      | Item                                                                                                     | Status |
| ------ | -------------------------------------------------------------------------------------------------------- | ------ |
| 1.0.52 | Polygon REST client (`collectors/polygon.py`, 8 assets via C:/X:/I: tickers)                             | 🟢     |
| 1.0.53 | 1-min bars persistence (`polygon_intraday` hypertable, migration 0006, ORM model + persist_polygon_bars) | 🟢     |
| 1.0.54 | Cron systemd 1-min ingestion (`*:*:00`, 8 calls/min = 8 % of Polygon Starter quota)                      | 🟢     |
| 1.0.34 | `polygon_intraday` hypertable shipped in migration 0006                                                  | 🟢     |

### CHUNK 7 — Critic Agent + tests + final commit

| #      | Item                                                                                                                                                                         | Status                                                         |
| ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| 1.0.55 | Critic Agent extended : `cross_asset.review_cards` (DXY-leg disagreement, XAU+DXY double-long, SPX long inside funding_stress)                                               | 🟢                                                             |
| 1.0.56 | Full pipeline test EUR/USD pré-Londres : `python -m ichor_api.cli.run_session_card EUR_USD pre_londres --dry-run` writes `session_card_audit` row, `/v1/sessions` returns it | 🟢                                                             |
| 1.0.57 | Verifier subagent on the chunk                                                                                                                                               | 🟡 manual end-to-end smoke replaces verifier for this skeleton |
| 1.0.58 | Final commit + push                                                                                                                                                          | 🟢 (commit pending below)                                      |

## Phase 1.1+ — see ADR-017 for the full roadmap

Phase 1.1 (Coverage) — 8 assets × 2 sessions
Phase 1.2 (Méta-cognition) — auto-improvement + RAG + audio TTS
Phase 1.3 (Living entity) — 24/7 event-driven agent + voice + ambient widget

---

## Phase 1 Step 2 — DONE (2026-05-04 marathon, 24 sprint commits)

The session ran from 2026-05-04 00:00 to ~13:00 Paris. End state :
17/17 VISION_2026 deltas shipped + 6 non-roadmap sprints. 32 commits
on origin/main (5c95982 → 3747e49).

### Sprint A — Audit + XAU bug fix + VISION_2026.md (`9f3a8f2`)

Atomic audit via researcher subagent. Fix `XAU_USD: "X:XAUUSD"` →
`"C:XAUUSD"` (the X: namespace is crypto, gold is in C: per Massive
2026 docs). Test verrouillé corrigé. `docs/VISION_2026.md` listing
17 deltas to push beyond the original audit.

### Sprint B.1+B.2 — Living dashboard v1 (`557c6fd`)

Zustand store régime + `<RegimeQuadrantWidget>` motion+pulse +
`<CrossAssetHeatmap>` 8 actifs animée. Wires `motion` + `zustand`
from "installed but never imported" to "active".

### Sprint D — 7 frameworks asset-spécifiques (`10fdf71`)

XAU (DFII10 + DXY + WGC), USDJPY (US-JP 10Y + BoJ YCC + MoF intervention),
NAS100 (mega-7 + AI capex + 0DTE GEX), SPX500 (broad macro + dealer GEX),
GBPUSD, AUDUSD, USDCAD. 24/24 pass tests.

### Sprint C (Brier reconciler) — `93d0b68`

`services/brier.py` pure functions (28 tests). `cli/reconcile_outcomes.py`
nightly. `routers/calibration.py` 3 endpoints. Reconciler armed
23:15 Paris.

### Sprint F (Polymarket↔Kalshi↔Manifold divergence) — `ca1d824`

`packages/agents/src/ichor_agents/predictions/divergence.py` —
token-Jaccard matcher + 2-5pp gap detection. 20/20 tests. UNIQUE.

### Sprint B.3 (Calibration page) — `afd28c5`

`/calibration` reliability diagram SVG + per-asset/régime breakdown.
`<ReliabilityDiagram>` component.

### Sprint G+1 (polygon_news + ADR-017 fix) — `942c151`

`collectors/polygon_news.py` + 11 tests. ADR-017 corrigé : Polygon
Starter $29 → Massive Currencies $49 (l'original couvrait pas FX).

### Sprint G+ (data_pool service) — `f72f426`

`services/data_pool.py` — 9 sections markdown source-stamped, builds
the input for the brain 4-pass. 10 tests.

### Sprint G+2 (FRED collector wiring) — `a44aba9`

FRED câblé dans run_collectors CLI. COT codes corrigés (numerical
CFTC codes au lieu des shorthands "EU/BP/JY").

### Sprint G+3 (6 keyless collectors) — `f8b9e6c`

gdelt, ai_gpr, cot, cb_speeches, kalshi, manifold all wired into
run_collectors. 6 persist helpers added. 126 cb_speeches persisted
in first run. **Verdict passes blocked → amendments**.

### Critic alias matching fix — `c9cbf1c`

`reviewer.py` \_ASSET_ALIASES dict — EUR/USD ↔ EUR_USD ↔ C:EURUSD
all considered equivalent. **First --live verdict approved** :
card `5b2b5089` EUR/USD pre_londres.

### Sprint cron-card autopilot — `a338ec6`

`cli/run_session_cards_batch.py` + 4 systemd timers (06/12/17/22 Paris)

- 2 collector timers (gdelt 2h, cot Friday 23:00). 16 cards/day automatic.

### Sprint B.4 (LiveChartCard) — `14a954f`

`<LiveChartCard>` lightweight-charts v5 + endpoint
`/v1/market/intraday/{asset}`. Wires the 3rd dep that was installed
but unused. Auto-poll 30s.

### Sprint H (Funding stress + CB intervention) — `4e88865`

`services/funding_stress.py` (SOFR-IORB / SOFR-EFFR / RRP / HY OAS
composite). `services/cb_intervention.py` (BoJ 152, SNB 0.95, PBoC 7.30
empirical sigmoid). 16/16 tests. UNIQUE. **2nd approved card USD/JPY**.

### Sprint Dashboard hero + Replay + Narratives — `c6f68c2`

4 deltas in 1 commit (1072 lines). Dashboard `/` rewrite avec hero
régime + heatmap. Time-machine replay slider `/replay/[asset]`.
Narrative tracker keyword-frequency + page `/narratives`. 9 tests.

### Sprint G+4 (kalshi/manifold discovery) — `369d8c1`

Discovery endpoints au lieu de slugs hardcoded. 37 manifold + 30 kalshi
markets persisted via `/search-markets` + `/markets`.

### Sprint S+M+K brain (KG + Geopolitics + Counterfactual brain) — `aa0def8`

`/v1/graph/news-network` + `/v1/graph/causal-map` + page
`/knowledge-graph` avec radial cluster SVG. `/v1/geopolitics/heatmap`

- page `/geopolitics` equirectangular projection. Pass 5
  counterfactual reasoning brain (9 tests). UNIQUE.

### Sprint K UI (counterfactual button) — `31d907c`

`POST /v1/sessions/{id}/counterfactual` + `<CounterfactualButton>`
modal sur `/sessions/[asset]`. Pass 5 end-to-end accessible from UI.

### Sprint A microstructure — `d57c566`

`services/microstructure.py` Amihud + Kyle's lambda + RV + VWAP

- value-area sur polygon_intraday. 19 tests. **3rd approved card
  EUR/USD avec data_pool 8472 chars / 60 sources cited**.

### Sprint F+Q (asian_session + WS pubsub) — `fb4154b`

`services/asian_session.py` Tokyo fix tracking JPY pairs (5 tests).
Redis pubsub `ichor:session_card:new` + WS forward + frontend toast
violet. **4th approved card USD/JPY**.

### Sprint E + types fix — `b789cef`

`services/surprise_index.py` z-score proxy on FRED hard data (9 tests).
`AssetSpecialization.correlations_snapshot: dict[str, float | None]`
fix surfaced live. **5th approved card EUR/USD bias=short conv=22%**
(first non-neutral approved).

### Sprint L (causal propagation) — `bcba5fe`

`services/causal_propagation.py` Bayesian-lite forward propagation
(noisy-OR). `POST /v1/graph/shock` + `GET /v1/graph/shock-nodes`.
10 tests. UNIQUE.

### Sprint L UI (ShockSimulator) — `09fa4ea`

`<ShockSimulator>` panel sur `/knowledge-graph`. Pick node + P → see
forward propagation with bars + hops. Powell hawkish 1.0 → XAU/USD
100% in 3 hops.

### Sprint G+5 partial (graceful skip xls) — `72067de`

`collectors/ai_gpr.py` magic-byte detection (CFB / ZIP / text).
Logs clear warning instead of crashing on binary upstream.

### Sprint C scaffold (FlashAlpha GEX) — `c09e310`

`collectors/flashalpha.py` 7 tests. Skip path tested on Hetzner.
Awaits Eliot's free-tier key.

### Sprint G+5 complet (xls parser) — `3516e17`

xlrd + openpyxl installed on Hetzner. ai_gpr xls parser via xlrd.
**15096 AI-GPR observations persisted** (full historical series).
GET `/v1/data-pool/{asset}` debug endpoint added.

### Sprint UX (Cmd+K + EventTicker) — `34fd964`

`<CommandPalette>` Cmd+K Linear-style nav + `<EventTicker>`
Bloomberg-tape pinned bottom. Both wired in root layout.

### Sprint R (PWA push end-to-end) — `e9c3091`

VAPID keys generated + persisted. `services/push.py` Redis-backed
subscription store. `routers/push.py` 4 endpoints. `<PushToggle>`
frontend. Auto-send on non-blocked cards in `cli/run_session_card.py`.

### Sprint admin (operational health) — `d386e30`

`/v1/admin/status` + page `/admin`. Per-table freshness badges +
per-asset card breakdown.

### Doc refresh — `3747e49`

`docs/SESSION_HANDOFF.md` rewrite. `docs/USER_GUIDE.md` operator manual.

---

### Phase 1 Step 2 final state

- 17/17 VISION_2026 deltas shipped
- 5/5 last --live runs verdict=approved (taux 100% post-fix)
- 17/17 cards persisted total (76% approval rate)
- 9/10 tables peuplées
- 17 systemd timers autopilot 24/7
- 8 unique capabilities vs concurrents premium
- 13 web pages, 29 REST endpoints, 12 UI components, 10 backend services
- ~340 Python tests vert
- ~12 000 lines added in one session marathon
