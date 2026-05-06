# `apps/api` — Ichor backend

FastAPI service running on Hetzner. Responsibilities :

- 34 routers exposing 53 endpoints — REST + WebSocket for the Next.js
  dashboard
- 4-pass session-card pipeline (lazy-imports `packages/ichor_brain`)
  + Critic gate before persistence
- Alert engine — 33-alert catalog (`alerts/catalog.py`) + Crisis
  Mode composite (`alerts/crisis_mode.py`)
- 37 source-stamped collectors (FRED, Polygon, GDELT, Polymarket,
  Kalshi, Manifold, AAII, BIS speeches, etc.) with TimescaleDB
  hypertable persistence
- 24 CLI runners driven by 49+ systemd timers on Hetzner (Living
  Entity loop : reconciler → brier_optimizer → drift detection →
  outlier scan → DTW analogue → weekly post-mortem +
  counterfactual batch)
- Bridge to the local Win11 `claude-runner` via Cloudflare Tunnel
  (POST /v1/briefing-task for Couche-1, /v1/agent-task for Couche-2
  per ADR-021/023)

## Quick start (after Phase 0 complete)

```bash
uv venv
uv pip install -e ".[dev]"
uvicorn ichor_api.main:app --reload --port 8000
```

## Layout

```
src/ichor_api/
├── main.py             FastAPI app + lifespan + 34 router includes
├── config.py           Pydantic settings (env_prefix=ICHOR_API_)
├── db.py               Async engine + sessionmaker
├── alerts/             33-alert catalog + evaluator + Crisis Mode
├── routers/            34 routers (admin, alerts, briefings, sessions,
│                       calibration, correlations, divergence, polymarket,
│                       macro_pulse, today, ws, ...)
├── models/             24 SQLAlchemy hypertable-backed models
├── collectors/         37 source-stamped data collectors
├── services/           44 services (data_pool, alerts_runner,
│                       confluence_engine, ml_signals, post_mortem,
│                       liquidity_proxy, risk_reversal_check,
│                       cb_tone_check, ...)
├── cli/                24 cron runners (run_briefing,
│                       run_session_cards_batch, run_couche2_agent,
│                       run_brier_optimizer, run_dtw_analogue, ...)
└── briefing/           4-pass briefing assembly
migrations/             26 Alembic migrations linear chain (head 0027)
```

## Status (2026-05-06)

**LIVE in production** on Hetzner. ~771 tests pass locally (13
skipped for missing optional ML deps + DB-bound smoke). The
`ichor-api.service` systemd unit wraps `uvicorn` with 2 workers
on `127.0.0.1:8000`, fronted by Cloudflare Tunnel.
