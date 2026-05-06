# Ichor

> Autonomous market intelligence platform — _Living Macro Entity_.
> Pre-trade macro/geopolitical/sentiment context for one trader (Eliot)
> who executes discretionary technical analysis on TradingView.

**Status** : 🟢 **Phase 2 LIVE in production**. 24 ADRs, 13 runbooks,
26 Alembic migrations (head `0027`), 49+ systemd timers autopilot 24/7,
the 4-pass + Pass 5 pipeline persists into `session_card_audit` on
every cron tick (8 assets × 4 windows/day = 32 cards/day).

## What is Ichor?

Ichor produces 32 **session cards per day** (8 actifs × 4 sessions :
06h00 pre-Londres, 12h00 pre-NY, 17h00 NY-mid, 22h00 NY-close, all
Europe/Paris) on 8 instruments — EUR/USD, XAU/USD, NAS100, USD/JPY,
SPX500, GBP/USD, AUD/USD, USD/CAD — using a 3-layer architecture:

1. **Qualitative analysis** — Claude (Opus 4.7 + Sonnet 4.6 + Haiku 4.5)
   via the **Max 20x subscription**, run locally on a Windows 11 host
   through Cloudflare Tunnel. Flat $200/mo, no API consumption
   ([ADR-009](docs/decisions/ADR-009-voie-d-no-api-consumption.md)).
   Couche-2 (5 always-on agents) routes via Claude Haiku 4.5 by
   default ([ADR-021](docs/decisions/ADR-021-couche2-via-claude-not-fallback.md) /
   [ADR-023](docs/decisions/ADR-023-couche2-haiku-not-sonnet-on-free-cf-tunnel.md)),
   with Cerebras + Groq free tiers wired as transparent fallback.
2. **Local ML (no LLM)** — LightGBM + hmmlearn + dtaidistance + river +
   FOMC-RoBERTa + FinBERT-tone running on Hetzner. 14 models registered
   in [`packages/ml/model_registry.yaml`](packages/ml/model_registry.yaml)
   with [model cards](packages/ml/model_cards/). 6 probability-only
   bias trainers reinstated via
   [ADR-022](docs/decisions/ADR-022-probability-bias-models-reinstated.md).

**Pipeline 4-pass + Pass 5 counterfactual** — every session card flows
through `regime → asset → stress → invalidation → critic` (with Pass 5
counterfactual on-demand from the UI). The data pool feeding the brain
is **~28 sections / ~95 sources / ~12-15 KB chars** per run, all
source-stamped (FRED series IDs, Polygon tickers, CFTC market codes,
Polymarket slugs, etc.) so the Critic Agent can verify and reject
unsourced claims.

**8 capabilities UNIQUE vs concurrents premium** (Bloomberg, Aladdin,
Permutable AI) :

1. CB intervention probability empirical (BoJ/SNB/PBoC sigmoid)
2. Polymarket↔Kalshi↔Manifold divergence detection
3. Time-machine replay slider over verdict history
4. Counterfactual Pass 5 ("what if event X hadn't happened?")
5. Brier-score calibration publique + reliability diagram
6. Régime-colored ambient UI (4-quadrant macro pulse)
7. Critic Agent gate with asset alias matching robust
8. Causal forward-propagation simulator (Bayes-lite shock)

See [`docs/decisions/ADR-017-reset-phase1-living-macro-entity.md`](docs/decisions/ADR-017-reset-phase1-living-macro-entity.md)
for the contractual vision, [`docs/VISION_2026.md`](docs/VISION_2026.md)
for the 17 deltas roadmap, and [`docs/SESSION_HANDOFF.md`](docs/SESSION_HANDOFF.md)
for the latest state. [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) is the
operator manual.

## Live state (post-2026-05-04 marathon)

| Service                                         | Where                 | State                     |
| ----------------------------------------------- | --------------------- | ------------------------- |
| `ichor-api` (uvicorn 2 workers)                 | Hetzner :8000 (lo)    | active                    |
| Postgres 16 + TimescaleDB 2.26 + Apache AGE 1.5 | Hetzner :5432 (lo)    | active                    |
| Redis 8 (AOF) — push subs + pubsub              | Hetzner :6379 (lo)    | active                    |
| `claude-runner` uvicorn user-mode               | Win11 :8766           | alive (proven via cron)   |
| Cloudflare Tunnel `claude-runner.fxmilyapp.com` | Win11 → CF edge       | 4 conns                   |
| **49+ systemd timers autopilot**                | Hetzner               | all enabled               |
| wal-g basebackup → R2 EU `ichor-walg-eu`        | Hetzner systemd timer | enabled                   |
| Loki + Prometheus + Grafana + Langfuse + n8n    | Hetzner Docker        | UP (11 ctrs)              |
| VAPID push notifications                        | Hetzner Redis subs    | live (`/v1/push/test` OK) |
| 9/10 collector tables peuplées                  | Hetzner Postgres      | LIVE                      |

**Data live** (snapshot 2026-05-06) : polygon_intraday 28 643 bars,
fx_ticks 224 918 (FX quote-tick stream for VPIN), fred_observations
933, gpr_observations 15 096 historical, polymarket 711, gdelt_events
1 948, news_items 209, cb_speeches 133, kalshi 30, manifold 37,
session_card_audit live with the 4 daily windows. `cot_positions`
empty (weekly Saturday cron), `economic_events` and `post_mortems`
empty (former pending forex_factory cadence audit, latter weekly Sunday).

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
│   ├── web/              Next.js 15 dashboard — legacy Phase 1 (deprecated)
│   └── web2/             Next.js 15.5 + React 19 + Tailwind v4 — Phase 2 dashboard
│       └── app/             35 routes SSR + ISR (incl. /learn 16 chapters)
├── packages/
│   ├── agents/           Pydantic AI agents + Cerebras/Groq providers
│   ├── ml/               ML stack (HMM, ADWIN, HAR-RV, VPIN, DTW, FOMC-RoBERTa, FinBERT)
│   │   ├── model_registry.yaml   14 entries
│   │   └── model_cards/          12 Mitchell-2019 cards
│   └── ui/               15-component design system (BiasBar, AssetCard, ChartCard,
│                         DrillDownButton, Timeline, ConfidenceMeter, …) — used by
│                         apps/web (legacy). apps/web2 has its own component layer.
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

| Tool     | Version                                | Where                                 |
| -------- | -------------------------------------- | ------------------------------------- |
| Node     | 22.x LTS                               | local + Hetzner                       |
| pnpm     | 10.33.2                                | local + Hetzner                       |
| Python   | 3.12                                   | Hetzner (3.14 OK locally for tooling) |
| Postgres | 16 + TimescaleDB 2.26 + Apache AGE 1.5 | Hetzner                               |
| Redis    | 8.6 (AOF, allkeys-lru, maxmemory 2 GB) | Hetzner                               |
| Backup   | wal-g 3.0.8 → R2 EU                    | Hetzner                               |
| Tunnel   | cloudflared 2026.x                     | Win11 → CF edge                       |
| Secrets  | sops 3.12 + age 1.3                    | local + Hetzner                       |

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

| Item                            | Monthly                  |
| ------------------------------- | ------------------------ |
| Claude Max 20x                  | $200 (flat, ADR-009)     |
| Hetzner CX32                    | ~€20                     |
| Cloudflare R2 (8.9 GB used)     | $0 (free 10 GB)          |
| Cloudflare Tunnel + DNS + Pages | $0 (free)                |
| GitHub Actions (private repo)   | $0 (within 2 000 min/mo) |
| **Total**                       | **~$220 flat**           |

No usage-based API costs by design.

## Phase 2 — current status

[`docs/SESSION_LOG_2026-05-06.md`](docs/SESSION_LOG_2026-05-06.md)
captures the most recent state. Latest milestones :

- **24 ADRs** total (latest: ADR-024 session-cards 5-bug fix)
- **26 Alembic migrations** linear, head `0027`
- **49+ systemd timers** autopilot 24/7
- **5 Couche-2 agents** routing through Claude Haiku 4.5 (ADR-021/023)
- **6 probability-only bias trainers** reinstated (ADR-022)
- **8 unique capabilities** vs concurrents premium

The cron-fired session-card path is proven end-to-end. Auto-push iOS
notifications operational. Daily batches at 06:00 / 12:00 / 17:00 /
22:00 Paris generate 32 cards/day. Reconciler nightly chains into the
Living Entity loop : reconciler 02:00 → brier_optimizer 03:30 →
brier_drift 04:00 → concept_drift 04:30 → prediction_outlier 04:45 →
dtw_analogue 05:00, then weekly post_mortem Sun 19:00 →
counterfactual_batch Sun 20:00.

## Operational documents

- [24 ADRs](docs/decisions/) — every delta from the accepted architecture, with rationale
- [13 runbooks](docs/runbooks/) — on-call procedures (DR, rotation, recovery)
- [DR test records](docs/dr-tests/) — quarterly drill outcomes
- [Legal mapping](docs/legal/) — AMF DOC-2008-23, EU AI Act Article 50,
  Anthropic Usage Policy

## License

Currently `UNLICENSED` (all rights reserved). Final license to be decided
before any external publication.
