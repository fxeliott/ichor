# Ichor

> Autonomous market intelligence platform.
> Phase 0 — infrastructure setup (32 criteria over 4 weeks).

**Status** : 🟢 Phase 0 cron pipeline LIVE end-to-end (started 2026-05-02).

## What is Ichor?

Ichor produces 4 grouped multi-asset trading briefings per day (06h, 12h, 17h,
22h Europe/Paris) on 8 instruments — EUR/USD, XAU/USD, NAS100, USD/JPY,
SPX500, GBP/USD, AUD/USD, USD/CAD — using a 3-layer architecture:

1. **Qualitative analysis** — Claude (Opus 4.7 + Sonnet 4.6) via the **Max 20x
   subscription**, run locally on a Windows 11 host through Cloudflare Tunnel.
   Flat $200/mo, no API consumption ([ADR-009](docs/decisions/ADR-009-voie-d-no-api-consumption.md)).
2. **24/7 LLM automation** — Cerebras + Groq free tiers for continuous
   macro / sentiment / positioning agents on Hetzner.
3. **Local ML (no LLM)** — LightGBM + hmmlearn + dtaidistance + river +
   FOMC-RoBERTa + FinBERT-tone running on Hetzner. 14 models registered
   in [`packages/ml/model_registry.yaml`](packages/ml/model_registry.yaml)
   with [model cards](packages/ml/model_cards/).

See [`docs/ARCHITECTURE_FINALE.md`](docs/ARCHITECTURE_FINALE.md) for the full
design and [`docs/AUDIT_V3.md`](docs/AUDIT_V3.md) for the technical audit.

## Live state

| Service | Where | State |
|---|---|---|
| `ichor-api` (uvicorn 2 workers) | Hetzner :8000 (lo) | active |
| Postgres 16 + TimescaleDB 2.26 + Apache AGE 1.5 | Hetzner :5432 (lo) | active |
| Redis 8 (AOF) | Hetzner :6379 (lo) | active |
| `claude-runner` uvicorn user-mode | Win11 :8766 | alive (proven via cron) |
| Cloudflare Tunnel `claude-runner.fxmilyapp.com` | Win11 → CF edge | 4 conns |
| 5 systemd briefing timers (06h/12h/17h/22h + Sun 18h Paris) | Hetzner | enabled |
| wal-g basebackup → R2 EU `ichor-walg-eu` | Hetzner systemd timer | enabled |
| Loki + Prometheus + Grafana + Langfuse + n8n | Hetzner Docker | UP (11 ctrs) |

DR validated: see [`docs/dr-tests/2026-Q2-walg-drill.md`](docs/dr-tests/2026-Q2-walg-drill.md)
(restored a 34 MB basebackup from R2 in 5 s, structure verified).

## Repository layout

```
ichor/
├── apps/
│   ├── api/              FastAPI backend (Python 3.12) — runs on Hetzner
│   │   └── src/ichor_api/
│   │       ├── routers/     /v1/briefings, /v1/alerts, /v1/bias-signals, /v1/ws
│   │       ├── alerts/      33-alert engine + Crisis Mode composite
│   │       ├── collectors/  fred.py, rss.py, polymarket.py
│   │       └── cli/         run_briefing, seed_dev_data, run_collectors
│   ├── claude-runner/    Local Win11 FastAPI :8766, subprocesses `claude -p`
│   └── web/              Next.js 15 dashboard — Cloudflare Pages
│       └── app/             /, /briefings, /alerts, /assets, /assets/[code]
├── packages/
│   ├── agents/           Pydantic AI agents + Cerebras/Groq providers
│   ├── ml/               ML stack (HMM, ADWIN, HAR-RV, VPIN, DTW, FOMC-RoBERTa, FinBERT)
│   │   ├── model_registry.yaml   14 entries
│   │   └── model_cards/          12 Mitchell-2019 cards
│   ├── shared-types/     Pydantic models shared across services
│   └── ui/               13-component design system (BiasBar, AssetCard, ChartCard,
│                         DrillDownButton, Timeline, ConfidenceMeter, …)
├── infra/
│   ├── ansible/          Hetzner provisioning (12 roles, Postgres+TS+AGE,
│   │                     Redis, wal-g → R2, Docker, observability stack)
│   ├── cloudflare/       Cloudflare Tunnel + Pages config
│   └── secrets/          SOPS-encrypted .env files (.sops.yaml multi-recipient)
├── docs/
│   ├── ARCHITECTURE_FINALE.md   The accepted architecture
│   ├── AUDIT_V3.md              Final technical audit (78 verified sources)
│   ├── PHASE_0_LOG.md           Live log of Phase 0 status + deltas
│   ├── SESSION_HANDOFF.md       Single source of truth for /clear pickup
│   ├── decisions/               11 ADRs (Architecture Decision Records)
│   ├── runbooks/                10 on-call runbooks (DR, rotation, recovery)
│   ├── dr-tests/                Quarterly disaster-recovery drill records
│   └── legal/                   AMF + EU AI Act + Anthropic Usage Policy
├── scripts/                     Local dev + ops helpers
│   ├── windows/                 install + start + register-tasks for Win11
│   └── hetzner/                 register-cron-briefings + walg-restore-drill
├── phase0-artifacts/            Server audits + backups (kept for traceability)
└── .github/workflows/           CI (lint, test, audit, deploy)
```

## Toolchain

| Tool | Version | Where |
|------|---------|-------|
| Node | 22.x LTS | local + Hetzner |
| pnpm | 10.33.2 | local + Hetzner |
| Python | 3.12 | Hetzner (3.14 OK locally for tooling) |
| Postgres | 16 + TimescaleDB 2.26 + Apache AGE 1.5 | Hetzner |
| Redis | 8.6 (AOF, allkeys-lru, maxmemory 2 GB) | Hetzner |
| Backup | wal-g 3.0.8 → R2 EU | Hetzner |
| Tunnel | cloudflared 2026.x | Win11 → CF edge |
| Secrets | sops 3.12 + age 1.3 | local + Hetzner |

## Quickstart (development)

### Prerequisites

- pnpm + Node 22 (`corepack enable` or [official installer](https://pnpm.io/installation))
- Python 3.12 (`pyenv` or system) with `uv` for the Python workspaces
- SSH access to Hetzner (key in `~/.ssh/id_ed25519_ichor_hetzner`)
- age key for SOPS in `%APPDATA%\sops\age\keys.txt` (Win) or `~/.config/sops/age/keys.txt` (POSIX)

### Frontend dev

```bash
pnpm install
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 pnpm --filter @ichor/web dev
# → http://localhost:3000
```

The dev server reads from the Hetzner API by default if `NEXT_PUBLIC_API_URL`
points to the production host (`http://178.104.39.201:8000` only reachable
from your SSH tunnel; production-style access is via Cloudflare Pages).

### Run the API locally

```bash
cd apps/api
uv venv && uv pip install -e ".[dev]"
# Provide DB + Redis (use docker compose or your local install)
uv run alembic upgrade head
uv run uvicorn ichor_api.main:app --port 8000
```

### Trigger a briefing manually (against live Hetzner pipeline)

```bash
ssh ichor-hetzner '
  cd /opt/ichor/api/src && \
  source /opt/ichor/api/.venv/bin/activate && \
  set -a && source /etc/ichor/api.env && set +a && \
  python -m ichor_api.cli.run_briefing pre_londres
'
```

### Smoke-test collectors

```bash
ssh ichor-hetzner '
  cd /opt/ichor/api/src && source /opt/ichor/api/.venv/bin/activate && \
  set -a && source /etc/ichor/api.env && set +a && \
  python -m ichor_api.cli.run_collectors all
'
```

### Run the WAL-G restore drill (quarterly)

```bash
ssh ichor-hetzner 'sudo bash /usr/local/bin/walg-restore-drill.sh'
# Last drill: 2026-05-03 → PASSED, 5 s, 34 MB restored. See docs/dr-tests/.
```

## Costs (current, verified)

| Item | Monthly |
|---|---|
| Claude Max 20x | $200 (flat, ADR-009) |
| Hetzner CX32 | ~€20 |
| Cloudflare R2 (8.9 GB used) | $0 (free 10 GB) |
| Cloudflare Tunnel + DNS + Pages | $0 (free) |
| GitHub Actions (private repo) | $0 (within 2 000 min/mo) |
| **Total** | **~$220 flat** |

No usage-based API costs by design.

## Phase 0 — current status

See [`docs/PHASE_0_LOG.md`](docs/PHASE_0_LOG.md) for the live status of the
32 Phase 0 criteria. The cron-fired briefing path is proven end-to-end
(Hetzner → Cloudflare Tunnel → Win11 → Claude Max 20x → Postgres) — see
[`docs/SESSION_HANDOFF.md`](docs/SESSION_HANDOFF.md).

## Operational documents

- [11 ADRs](docs/decisions/) — every delta from the accepted architecture, with rationale
- [10 runbooks](docs/runbooks/) — on-call procedures (DR, rotation, recovery)
- [DR test records](docs/dr-tests/) — quarterly drill outcomes
- [Legal mapping](docs/legal/) — AMF DOC-2008-23, EU AI Act Article 50,
  Anthropic Usage Policy

## License

Currently `UNLICENSED` (all rights reserved). Final license to be decided
before any external publication.
