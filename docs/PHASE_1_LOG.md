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

| # | Item | Status | Notes |
|---|------|--------|-------|
| 1.0.1 | ADR-017 written + accepted | 🟢 | The contract for Phase 1 |
| 1.0.2 | Wrong-scope packages archived | 🟢 | git mv to `archive/2026-05-03-pre-reset/` (backtest/risk/trading/ml-training + 2 web pages + obsolete migration/router/model + 3 deprecated ADRs + 1 deprecated runbook) |
| 1.0.3 | SESSION_HANDOFF refondu | 🟢 | Old version moved to `SESSION_HANDOFF_pre-reset_2026-05-03.md` |
| 1.0.4 | PHASE_1_LOG initialized | 🟢 | This file |
| 1.0.5 | API references cleaned (main.py + routers/__init__.py + models/__init__.py) | 🟢 | Backtest router/model removed from imports |

### CHUNK 2 — 17 new collectors

| # | Source | Status | Notes |
|---|--------|--------|-------|
| 1.0.6 | FRED extended (real yields, RRP, TGA, breakevens, MOVE, more series) | ⬜ | builds on existing `collectors/fred.py` |
| 1.0.7 | GDELT 2.0 Doc API (translingual news + GKG themes) | ⬜ | Replaces NewsAPI ($449/mo) with $0 free tier |
| 1.0.8 | AI-GPR Index daily (LLM-scored geopolitical risk) | ⬜ | matteoiacoviello.com, CSV cron |
| 1.0.9 | CFTC COT positioning | ⬜ | Python `cftc-cot` lib, weekly Friday |
| 1.0.10 | Treasury Fiscal Data DTS daily (TGA) | ⬜ | More granular than FRED weekly |
| 1.0.11 | BLS v2 (NFP, CPI core, employment) | ⬜ | 500 queries/day cap |
| 1.0.12 | ECB SDMX (rates, balance sheet, credit) | ⬜ | SDMX 2.1 |
| 1.0.13 | EIA (oil, gas, energy) | ⬜ | Free key |
| 1.0.14 | BoE IADB (UK rates) | ⬜ | CSV endpoint, no auth |
| 1.0.15 | BIS speeches aggregator | ⬜ | RSS feed |
| 1.0.16 | FlashAlpha free GEX (gamma exposure) | ⬜ | 5 req/day, same numerics as paid SpotGamma |
| 1.0.17 | Polygon Starter intraday (8 assets) | ⬜ | $29/mo, validated by Eliot |
| 1.0.18 | Kalshi public REST | ⬜ | Prediction market US |
| 1.0.19 | Manifold REST | ⬜ | 500 req/min/IP free |
| 1.0.20 | VIX/VVIX live (FRED + CBOE delayed) | ⬜ | Real-time intraday needs paid CBOE feed |
| 1.0.21 | AAII sentiment weekly | ⬜ | Free spreadsheet |
| 1.0.22 | Reddit WSB praw | ⬜ | Free for low volume |
| 1.0.23 | FINRA Short Interest API | ⬜ | Bi-monthly |
| 1.0.24 | FINRA ATS Weekly (dark pools) | ⬜ | 2-week lag |

### CHUNK 3 — Migration TimescaleDB

Status: 🟢 9/14 tables shipped — 8 in migration `0005_phase1_collector_tables.py`
(`fred_observations`, `gdelt_events`, `gpr_observations`, `cot_positions`,
`cb_speeches`, `kalshi_markets`, `manifold_markets`, `session_card_audit`)
applied at alembic `0005`, plus `polygon_intraday` shipped in migration `0006`
applied at alembic `0006` (Hetzner currently at `0006 (head)`).
Remaining tables (treasury_dts, bls, ecb, eia, gex, finra_short_interest,
finra_ats_weekly) deferred to later migrations once their collectors land.

| # | Table | Status |
|---|-------|--------|
| 1.0.25 | `fred_observations` (time-series, hypertable, 90d chunks) | 🟢 |
| 1.0.26 | `gdelt_events` (hypertable, 7d chunks) | 🟢 |
| 1.0.27 | `gpr_observations` (daily, 180d chunks) | 🟢 |
| 1.0.28 | `cot_positions` (weekly, hypertable, 180d chunks) | 🟢 |
| 1.0.29 | `treasury_dts_daily` (daily TGA balance) | ⬜ |
| 1.0.30 | `bls_observations` (monthly) | ⬜ |
| 1.0.31 | `ecb_series` (varying frequency) | ⬜ |
| 1.0.32 | `eia_series` (varying frequency) | ⬜ |
| 1.0.33 | `gex_snapshots` (daily) | ⬜ |
| 1.0.34 | `polygon_intraday` (1-min OHLCV, hypertable, 7d chunks) — shipped in migration `0006` | 🟢 |
| 1.0.35 | `kalshi_markets` + `manifold_markets` snapshots (30d chunks) | 🟢 |
| 1.0.35b | `cb_speeches` (90d chunks) | 🟢 |
| 1.0.36 | `finra_short_interest` + `finra_ats_weekly` | ⬜ |
| 1.0.37 | `session_card_audit` (replace `predictions_audit`, 30d chunks) | 🟢 |

### CHUNK 4 — Pipeline Claude 4-pass skeleton

Status: 🟢 skeleton shipped in `packages/ichor_brain/`. Orchestrator
serializes the 4 passes through a `RunnerClient` interface
(`HttpRunnerClient` for prod via Cloudflare Tunnel, `InMemoryRunnerClient`
for tests). Critic Agent is wired through an injectable `critic_fn` so
the package stays installable without `ichor_agents`. Tests : 30/30 on
Hetzner with the real Critic, 29/30 standalone.

| # | Item | Status |
|---|------|--------|
| 1.0.38 | New package `packages/ichor_brain/` | 🟢 |
| 1.0.39 | Pass 1 — Régime global (`passes/regime.py`) | 🟢 |
| 1.0.40 | Pass 2 — Asset specialization, EUR/USD framework (`passes/asset.py`) | 🟢 |
| 1.0.41 | Pass 3 — Bull case stress-test (`passes/stress.py`) | 🟢 |
| 1.0.42 | Pass 4 — Invalidation conditions (`passes/invalidation.py`) | 🟢 |
| 1.0.43 | Cache prompt setup — TTL constants + per-pass cache_key | 🟢 |
| 1.0.44 | Critic Agent gate integration via injectable `critic_fn` | 🟢 |
| 1.0.45 | Output → `session_card_audit` (mapper `persistence.to_audit_row`) | 🟢 |
| 1.0.46 | Tests : 30/30 (orch + per-pass + cache + persistence + critic-integration) | 🟢 |

### CHUNK 5 — Carte de session UI

| # | Item | Status |
|---|------|--------|
| 1.0.47 | `/sessions` page (8 cards grid) | 🟢 |
| 1.0.48 | `/sessions/[asset]` detail page (drill-down) | 🟢 |
| 1.0.49 | `<SessionCard>` component (`packages/ui/src/components/SessionCard.tsx`) | 🟢 |
| 1.0.50 | Sources cliquables + cas comparables | 🟡 sources rendered inline; cas comparables pending CHUNK 7 |
| 1.0.51 | WebSocket live updates | ⬜ deferred to CHUNK 7 (server revalidate=30s for now) |

### CHUNK 6 — Polygon Starter integration (8 assets intraday)

| # | Item | Status |
|---|------|--------|
| 1.0.52 | Polygon REST client (`collectors/polygon.py`, 8 assets via C:/X:/I: tickers) | 🟢 |
| 1.0.53 | 1-min bars persistence (`polygon_intraday` hypertable, migration 0006, ORM model + persist_polygon_bars) | 🟢 |
| 1.0.54 | Cron systemd 1-min ingestion (`*:*:00`, 8 calls/min = 8 % of Polygon Starter quota) | 🟢 |
| 1.0.34 | `polygon_intraday` hypertable shipped in migration 0006 | 🟢 |

### CHUNK 7 — Critic Agent + tests + final commit

| # | Item | Status |
|---|------|--------|
| 1.0.55 | Critic Agent extended : `cross_asset.review_cards` (DXY-leg disagreement, XAU+DXY double-long, SPX long inside funding_stress) | 🟢 |
| 1.0.56 | Full pipeline test EUR/USD pré-Londres : `python -m ichor_api.cli.run_session_card EUR_USD pre_londres --dry-run` writes `session_card_audit` row, `/v1/sessions` returns it | 🟢 |
| 1.0.57 | Verifier subagent on the chunk | 🟡 manual end-to-end smoke replaces verifier for this skeleton |
| 1.0.58 | Final commit + push | 🟢 (commit pending below) |

## Phase 1.1+ — see ADR-017 for the full roadmap

Phase 1.1 (Coverage) — 8 assets × 2 sessions
Phase 1.2 (Méta-cognition) — auto-improvement + RAG + audio TTS
Phase 1.3 (Living entity) — 24/7 event-driven agent + voice + ambient widget
