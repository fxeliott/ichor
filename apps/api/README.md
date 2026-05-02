# `apps/api` — Ichor backend

FastAPI service running on Hetzner. Responsibilities:

- REST + WebSocket endpoints for the Next.js dashboard
- Briefing serving (read-only API over `briefings` Postgres table)
- Alert engine (33 alert types — see `docs/SPEC.md` §AlertCatalog)
- ML model serving (LightGBM + XGBoost + ensembled bias aggregator)
- Triggers Crisis Mode briefings (via Cloudflare Tunnel → claude-runner local)

## Quick start (after Phase 0 complete)

```bash
uv venv
uv pip install -e ".[dev]"
uvicorn ichor_api.main:app --reload --port 8000
```

## Layout

```
src/ichor_api/
├── main.py             FastAPI app factory
├── config.py           Pydantic settings (env-driven)
├── deps.py             DI: db, redis, http clients
├── routers/
│   ├── briefings.py
│   ├── alerts.py
│   ├── assets.py
│   └── ws.py
├── models/             SQLAlchemy ORM models
├── schemas/            Pydantic API schemas
├── services/           Business logic (briefing assembly, alert dispatch)
└── adapters/           External APIs (Anthropic, OANDA, FRED, Polymarket)
```

## Status

🚧 Phase 0 — skeleton only. Full implementation Phase 1.
