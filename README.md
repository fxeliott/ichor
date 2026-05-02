# Ichor

> Autonomous market intelligence platform.
> Phase 0 — infrastructure setup (4 weeks, 32 criteria).

**Status** : 🚧 Phase 0 in progress (started 2026-05-02).

## What is Ichor?

Ichor produces 4 grouped multi-asset trading briefings per day on 8 instruments
(EURUSD, XAUUSD, NAS100, USDJPY, SPX500, GBPUSD, AUDUSD, USDCAD) using a
3-layer architecture:

1. **Qualitative analysis** — Claude (Opus 4.7 + Sonnet 4.6) via Max 20x
   subscription, run locally on a Windows 11 host through Cloudflare Tunnel.
2. **24/7 LLM automation** — Cerebras and Groq free tiers for continuous
   macro/sentiment/positioning agents on Hetzner.
3. **Local ML (no LLM)** — LightGBM + hmmlearn + dtaidistance + river +
   FOMC-RoBERTa + FinBERT-tone running on Hetzner.

See [`docs/ARCHITECTURE_FINALE.md`](docs/ARCHITECTURE_FINALE.md) for the full
design and [`docs/AUDIT_V3.md`](docs/AUDIT_V3.md) for the technical audit.

## Repository layout

```
ichor/
├── apps/
│   ├── api/              FastAPI backend (Python 3.12) — runs on Hetzner
│   ├── claude-runner/    Local Win11 FastAPI :8765, subprocesses `claude -p`
│   └── web/              Next.js 15 dashboard — Cloudflare Pages
├── packages/
│   ├── agents/           Claude Agent SDK + Pydantic AI agent definitions
│   ├── ml/               ML stack (LightGBM, hmmlearn, dtaidistance, river…)
│   ├── shared-types/     Pydantic models shared across services
│   └── ui/               shadcn/ui design system
├── infra/
│   ├── ansible/          Hetzner provisioning (Postgres+TimescaleDB, Redis,
│   │                     Apache AGE, wal-g, Langfuse, n8n, observability)
│   ├── cloudflare/       Cloudflare Tunnel + Pages config
│   └── secrets/          SOPS-encrypted environment files (.sops.yaml)
├── docs/
│   ├── ARCHITECTURE_FINALE.md   The accepted architecture
│   ├── AUDIT_V3.md              Final technical audit (78 verified sources)
│   ├── PHASE_0_LOG.md           Live log of Phase 0 decisions and deltas
│   ├── decisions/               ADRs (Architecture Decision Records)
│   ├── runbooks/                On-call runbooks (DR, rotation, recovery)
│   └── legal/                   AMF, EU AI Act, Anthropic compliance
├── scripts/                     Local dev and ops helpers
├── phase0-artifacts/            Server audits + backups (kept for traceability)
└── .github/workflows/           CI (lint, test, audit, deploy)
```

## Toolchain

| Tool | Version | Where |
|------|---------|-------|
| Node | 22.x LTS | local + Hetzner |
| pnpm | 10.x | local + Hetzner |
| Python | 3.12 | Hetzner (3.14 OK locally for tooling) |
| Postgres | 16 + TimescaleDB + Apache AGE | Hetzner |
| Redis | 7 (AOF) | Hetzner |
| Backup | wal-g 3.0.8 → R2 | Hetzner |

## Phase 0 — current step

See [`docs/PHASE_0_LOG.md`](docs/PHASE_0_LOG.md) for the live status of the
32 Phase 0 criteria.

## License

Currently `UNLICENSED` (all rights reserved). Final license to be decided
before any external publication.
