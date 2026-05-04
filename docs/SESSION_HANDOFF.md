# Session handoff — Ichor Phase 1 (Living Macro Entity)

> **AUTORITAIRE** — read this first when resuming work after `/clear`.
> Reset commit `[CHUNK 1]` 2026-05-03 — see ADR-017 for context.
> Pre-reset historical state in `SESSION_HANDOFF_pre-reset_2026-05-03.md`.

## TL;DR

**Ichor is being rebuilt as the Living Macro Entity** : an autonomous 24/7 agent
that continuously ingests 25+ macro/geo/sentiment/positioning sources, synthesizes
via Claude Max 20x at maximum power, and delivers per-asset per-session directional
verdicts with public calibration track-record — through a living UI Eliot opens
before each trading session.

**It is NOT** :
- A signal generator (Eliot trades discretionary on TradingView)
- A backtest framework or paper trading layer (those were a wrong-direction drift,
  archived 2026-05-03)
- A ML model that predicts price (Claude does the analysis, no ML model trained)
- A trader (Ichor never executes a single order)

## Vision contract

See **[ADR-017 — Reset Phase 1 : Living Macro Entity](decisions/ADR-017-reset-phase1-living-macro-entity.md)**
for the full contract — 12 capabilities across 4 layers (perception → analysis →
memory/calibration → expression).

## Asset universe (8 with session cards)

| # | Asset | Type |
|---|---|---|
| 1 | EUR/USD | FX major |
| 2 | GBP/USD | FX major |
| 3 | USD/JPY | FX major |
| 4 | AUD/USD | FX major |
| 5 | USD/CAD | FX major |
| 6 | XAU/USD | Gold |
| 7 | US30 | Dow Jones futures |
| 8 | US100 | NAS100 futures |

**Tracked for context only (no session card)** : SPX500, DXY, VIX, 10Y/2Y yields,
10Y TIPS real yields, WTI oil, BTC, EUR/GBP cross.

## Sessions

- **Pré-Londres** : generated ~07:30 Paris, valid 09:00-12:00 Paris
- **Pré-NY** : generated ~13:30 Paris, valid 14:30-22:00 Paris
- Plus event-driven re-generation on régime changes / NFP/CPI surprises / geo flash

## Cost ceiling

| Item | Monthly |
|---|---|
| Claude Max 20x | $200 (Voie D, fixed) |
| Polygon Starter intraday | $29 (validated by Eliot 2026-05-03) |
| Hetzner CX32 | ~€20 |
| Cloudflare R2 + Tunnel + Pages | $0 |
| GitHub Actions (private) | $0 |
| All other data (FRED, GDELT, Polymarket, COT, etc.) | $0 |
| **Total** | **~$249/mo flat** |

## What's running LIVE on Hetzner today

| Service | State | Notes |
|---|---|---|
| Postgres 16 + TimescaleDB 2.26 + Apache AGE 1.5 | active | scram-sha-256 + Docker bridge |
| Redis 8.6 (AOF) | active, localhost-only | |
| ichor-api uvicorn (systemd) | active | `/healthz/detailed` returns full state |
| 5 briefing systemd timers (06h/12h/17h/22h Paris + Sun 18h) | enabled | will be refactored toward session cards |
| 3 collector systemd timers (rss 15min, polymarket 5min, market_data daily) | enabled | will be extended to 17 more sources in CHUNK 2 |
| Loki + Prometheus + Grafana | UP | observability ready |
| wal-g basebackup → R2 EU | systemd timer 03h Paris | enabled |

## DB content (verified 2026-05-03)

| Table | Rows | Notes |
|---|---|---|
| `news_items` | 160+ | TimescaleDB hypertable, 24/7 ingestion |
| `polymarket_snapshots` | 7+ | TimescaleDB hypertable |
| `market_data` | 20 556 | 8 assets × 10y daily yfinance |
| `bias_signals` | 384 | seeded ; will be replaced by session cards |
| `alerts` | 8 | 33-alert engine + Crisis Mode triggers |
| `briefings` | 3 | will be refactored as session cards |
| `predictions_audit` | 2 036 | will be repurposed as `session_card_audit` for Brier tracking |

## What the reset removed (archived, not deleted)

All under `archive/2026-05-03-pre-reset/` :

- `packages/backtest/` — wrong scope (we don't backtest)
- `packages/risk/` — wrong scope (no order generation)
- `packages/trading/` — wrong scope (TradingView is the broker UI)
- `packages/ml/training/` — wrong scope (Claude does analysis)
- `apps/web/app/portfolio/` — wrong scope
- `apps/web/app/backtests/` — wrong scope
- `apps/api/migrations/versions/0004_backtest_runs.py` — wrong table
- `apps/api/src/ichor_api/models/backtest_run.py` — wrong model
- `apps/api/src/ichor_api/routers/backtests.py` — wrong router
- `decisions/ADR-014-backtest-framework-design.md` — superseded
- `decisions/ADR-015-risk-engine-kill-switch.md` — superseded
- `decisions/ADR-016-paper-only-default.md` — superseded
- `runbooks/RUNBOOK-012-kill-switch-trip.md` — superseded

## What's KEPT and load-bearing

- `apps/api/` skeleton (FastAPI + Alembic + ORM + 6 routers)
- `apps/claude-runner/` Voie D wrapper Win11
- `apps/web/` Next.js 15 + Tailwind 4 + design tokens + 7 working routes
- `packages/ui/` 13-component design system
- `packages/agents/critic/` Critic Agent skeleton (will be extended)
- `apps/api/src/ichor_api/graph/` AGE knowledge graph populator
- 17 ADRs (16 historic + ADR-017 reset)
- 11 runbooks (RUNBOOK-001 to RUNBOOK-011)
- 4 research reports : `docs/research/{macro-tools-landscape,data-sources,macro-frameworks,claude-orchestration-patterns}-2026.md`
- DR drill record : `docs/dr-tests/2026-Q2-walg-drill.md`
- SOPS+age + secrets infrastructure
- DisclaimerBanner + AMF + EU AI Act compliance

## Phase 1 Step 1 — DONE (CHUNK 1 → 7)

7 reset chunks shipped 2026-05-03 (commits `b884943` → `5c95982`) :
ADR-017 reset, 6 collectors, migration 0005, 4-pass brain skeleton,
SessionCard UI, Polygon collector + timer, cross-asset Critic.

## Phase 1 Step 2 — DONE (2026-05-04 marathon, 31 commits)

Full VISION_2026 roadmap shipped end-to-end. **17/17 deltas in production**.

### What's LIVE on origin/main (head `d386e30`)

**Brain pipeline** :
- 4-pass orchestrator (regime → asset → stress → invalidation + Critic)
- Pass 5 counterfactual (on-demand via UI button)
- 8 frameworks asset-spécifiques (XAU + USDJPY + NAS100 + US30 + GBPUSD
  + AUDUSD + USDCAD + EURUSD)
- Critic Agent gate with asset alias matching robust
- Brier reconciler nightly 23:15 Paris

**Data pool** (14 sections per session run, ~9000 chars / 65 sources cited) :
macro_trinity, dollar_smile, rate_diff, polygon_intraday, microstructure,
asian_session (JPY-relevant only), cot, prediction_markets, funding_stress,
surprise_index (z-score proxy), narrative, geopolitics, cb_speeches, news,
+ cb_intervention conditional (USD/JPY, EUR/CHF, USD/CNH).

**Collectors câblés** (15 total, 9/10 tables peuplées) :
fred, fred_extended, polygon, polygon_news, market_data, rss, polymarket,
kalshi (discovery), manifold (discovery), cb_speeches, gdelt, ai_gpr (xls
parser via xlrd), cot (Friday-only, expected empty Mon-Thu), flashalpha
(scaffold awaiting key).

**Services backend** (10) :
brier, data_pool, funding_stress, cb_intervention, microstructure,
asian_session, narrative_tracker, surprise_index, causal_propagation, push.

**Endpoints API** (29 routes + 1 WS) :
sessions, calibration, market[/intraday], narratives, graph, geopolitics,
data-pool (debug), counterfactual, push, admin, news, alerts, briefings,
predictions, bias-signals, ws.

**Web pages** (13) :
/, /sessions, /sessions/[asset], /replay/[asset], /narratives,
/knowledge-graph, /geopolitics, /calibration, /admin, /briefings, /assets,
/alerts, /news.

**UI components** (9 nouveaux) :
RegimeQuadrantWidget, CrossAssetHeatmap, ReliabilityDiagram, LiveChartCard,
TimeMachineReplay, KnowledgeGraphViz, GeopoliticsGlobe, CounterfactualButton,
ShockSimulator + Cmd+K palette + EventTicker + PushToggle.

**Capacités UNIQUES vs concurrents** (8) :
1. CB intervention probability empirical (BoJ/SNB/PBoC sigmoid)
2. Polymarket↔Kalshi↔Manifold divergence detection
3. Time-machine replay slider verdicts
4. Counterfactual Pass 5 (brain + UI)
5. Brier-score calibration publique + reliability diagram
6. Régime-colored ambient UI (4 quadrants pulse)
7. Critic Agent alias matching robust
8. Causal shock simulator (Bayes-lite forward propagation + UI panel)

### State Hetzner production (2026-05-04 12:43 UTC)

Tables peuplées :
  polygon_intraday    4771   (cron 1-min)
  gpr_observations   15096   (full history loaded via xlrd)
  gdelt_events         534   (cron 2h post-backoff fix)
  polymarket           263   (cron 5-min)
  news_items           176   (cron 15-min)
  cb_speeches          126   (cron 6h)
  manifold_markets      37   (discovery)
  fred_observations     37   (cron 4h)
  kalshi_markets        30   (discovery)
  cot_positions          0   (Friday-only — expected)
  session_card_audit    17   (13 approved = 76% rate)

Cards approved breakdown :
  EUR_USD: 9 (5 approved, 1 amendments, 3 blocked)
  USD_JPY: 3 (3 approved)
  XAU_USD: 2 (2 approved)
  NAS100_USD: 1 (1 approved)
  USD_CAD: 1 (1 approved)
  GBP_USD: 1 (1 approved)

17 systemd timers actifs sur Hetzner (autopilot 24/7) :
  polygon (1-min), rss (15-min), polymarket (5-min), fred (4h),
  gdelt (2h), cb_speeches (6h), market_data (daily), cot (Friday),
  reconciler (nightly 23:15 Paris), session-cards × 4 (06/12/17/22 Paris),
  briefings × 5 (06/12/17/22 + Sun 18:00 weekly).

VAPID + push notifications opérationnels (clés persistées dans api.env).

### What still requires Eliot action (all marginal)

1. **FlashAlpha free key** (5 min) — registration on flashalphalive.com,
   set `ICHOR_API_FLASHALPHA_API_KEY` in `/etc/ichor/api.env`. Unlocks
   SPX + NDX dealer GEX collector (scaffold ready, skip path tested).
2. **Domain decision** (ADR-002 / ADR-011) — keep `claude-runner.fxmilyapp.com`
   tunnel hostname or migrate to `ichor.fyi` $15/yr. Current setup works.
3. **GitHub HETZNER_SSH_PRIVATE_KEY secret** — for auto-deploy.yml
   (currently deploys are manual via tar+ssh streaming).

## Critical rules (non-negotiable)

- **Voie D** (ADR-009) : never any Anthropic API key, only Max 20x via local subprocess
- **AMF DOC-2008-23** : briefings remain general research, never personalized advice
- **EU AI Act Article 50** : AI-generated content disclosed everywhere (DisclaimerBanner)
- **Anthropic Usage Policy** : every output is "research material to inform a human decision"
- **Ichor never executes any order**, ever. Eliot trades on TradingView.
- **Track-record + calibration must be public** on every session card (Brier 30/90j)

## How to resume after /clear

Paste in new session :

```
Reprends Ichor. Lis docs/SESSION_HANDOFF.md (autoritaire), docs/decisions/ADR-017
(la nouvelle vision Living Macro Entity), git log --oneline | head -10. Continue
au CHUNK courant marqué dans SESSION_HANDOFF. Voie D maintenue, AMF + EU AI Act
non-négociables.
```

## Key files of authority

- `README.md` — project overview (to be updated post-CHUNK 7)
- `CONTRIBUTING.md` — branching, commits, model + collector workflows
- `SECURITY.md` — threat model, secrets, incident response
- **`docs/decisions/ADR-017-reset-phase1-living-macro-entity.md`** — the contract
- `docs/PHASE_1_LOG.md` — live status of Phase 1 (this file's companion)
- `docs/PHASE_0_LOG.md` — historic Phase 0 retrospective
- `docs/research/` — 4 ground-truth research reports
- `docs/runbooks/` — 11 operational runbooks
- `infra/secrets/.sops.yaml` + `.gitignore` — secret management
- `infra/ansible/site.yml` — playbook orchestrating 12 roles

## Status tracker

Phase 1 — CHUNK 1 (Reset propre) : **DONE** at commit `[reset]` 2026-05-03 evening.
Next : CHUNK 2 (17 new collectors).
