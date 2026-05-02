# ADR-001: Lock stack versions verified 2026-05-02

- **Status**: Accepted
- **Date**: 2026-05-02
- **Decider**: Eliot (autonomy delegation)

## Context

Eliot's `CLAUDE.md` non-negotiable rule: never fabricate versions. Every
package version pinned in this repo must be verified against the live registry
or vendor docs **on the date of the commit**.

The Phase 0 init commit pins ~30 packages across Node + Python + apt + Docker.
Without lockdown, Dependabot or `npm install` could drift to incompatible
combos (e.g. Next 16 incompat with Serwist, vollib renamed from py_vollib,
pgbackrest archived).

## Decision

The following exact versions are pinned, verified against npm registry and
PyPI on 2026-05-02 (and cross-checked with `docs/AUDIT_V3.md` §2, §5, §6):

### JS/TS workspace

| Package | Pinned | Why |
|---------|--------|-----|
| `pnpm` | `10.33.2` | latest stable, via `packageManager` field |
| `turbo` | `2.9.7` | latest stable |
| `next` | `15.5.15` | **stay on 15.x** — Next 16 incompat Serwist Webpack (AUDIT_V3 §6) |
| `react` / `react-dom` | `19.0.0` | required by Next 15 |
| `typescript` | `5.9.3` | TS 6.0.3 too recent (released weeks ago, library compat unclear) |
| `tailwindcss` | `4.2.4` | latest stable, with `@tailwindcss/postcss` |
| `lightweight-charts` | `5.2.0` | `attributionLogo: true` is now the default (compliance simplified) |
| `motion` | `12.38.0` | renamed from `framer-motion` (AUDIT_V3 §2) |
| `orval` | `8.9.0` | **min 8.0.3** for CVE-2026-24132 RCE patch |
| `@playwright/test` | `1.59.1` | latest stable |
| `vitest` | `4.1.5` | latest stable |
| `eslint` | `10.3.0` | latest stable |
| `prettier` | `3.8.3` | latest stable |
| `@types/node` | `22.19.17` | matches Node 22 LTS |

### Python workspace

| Package | Pinned (`>=`) | Why |
|---------|--------------|-----|
| `python` | `3.12,<3.13` | LTS, ML libs broadest support |
| `claude-agent-sdk` | `>=0.1.71,<0.2` | latest 0.1.x (AUDIT_V3 §5) |
| `pydantic-ai` | `>=1.88,<2` | latest 1.x stable (AUDIT_V3 §5) |
| `pydantic` | `>=2.10` | latest 2.x |
| `fastapi` | `>=0.118.0` | latest stable |
| `uvicorn` | `>=0.34.0` | latest stable |
| `sqlalchemy` | `>=2.0.36` | 2.x async API |
| `redis[hiredis]` | `>=5.2.0` | latest |
| `vollib` | `>=1.0.7` | renamed from `py_vollib` (AUDIT_V3 §2) |
| `lightgbm` | `>=4.5.0` | latest stable |
| `xgboost` | `>=2.1.0` | latest stable |
| `hmmlearn` | `>=0.3.3` | last release Oct 2024 — limited maintenance, monitor (AUDIT_V3 §2) |
| `dtaidistance` | `>=2.4.0` | latest |
| `river` | `>=0.24.2` | latest |
| `arch` | `>=8.0.0` | Sheppard, latest |
| `numpyro` | `>=0.20.0` | latest |
| `mapie` | `>=1.3.0` | **BSD-3-Clause** (not MIT — AUDIT_V3 §2) |
| `transformers` | `>=4.46.0` | for FOMC-RoBERTa + FinBERT-tone |
| `mlflow` | `>=3.11.1` | latest |

### Server-side apt + Docker

| Component | Version | Source |
|-----------|---------|--------|
| Ubuntu | 24.04 LTS noble | Hetzner Cloud image |
| Postgres | 16 | PGDG apt repo |
| TimescaleDB | 2.17.x | TimescaleDB packagecloud apt |
| Apache AGE | 1.5.0 | built from source against PG16 (no apt) — see [ADR-005](ADR-005-apache-age-built-from-source.md) |
| Redis | 7 | redis.io packagecloud |
| wal-g | 3.0.8 | GitHub release (replaces archived pgbackrest — AUDIT_V3 §2) |
| Docker Engine | latest stable | docker.com apt |
| Node | 22 LTS | NodeSource apt — see [ADR-004](ADR-004-node-22-not-20.md) |
| Loki | 3.3.2 | docker image `grafana/loki:3.3.2` |
| Grafana | 11.4.0 | docker image |
| Prometheus | v3.1.0 | docker image |
| Langfuse | v3 | docker image `langfuse/langfuse:3` |
| Clickhouse | 24.12-alpine | docker image (Langfuse dependency) |
| n8n | 1.78.1 | docker image `docker.n8n.io/n8nio/n8n:1.78.1` |
| MinIO | RELEASE.2025-01-20T14-49-07Z | docker image (Langfuse dependency) |

## Consequences

- **Lockfiles must be committed** (pnpm-lock.yaml, uv.lock per package).
- **Dependabot weekly PRs** keep us informed of upgrades (`.github/dependabot.yml`).
- **Breaking upgrades** (Next 16, TS 6) require a new ADR before merge.
- Re-verification cadence: every 30 days OR before a release.

## Alternatives considered

- **Float on `latest`** — rejected: violates Eliot's no-fabrication rule and
  reproducibility (lockfile drift).
- **Pin to AUDIT_V3 versions verbatim** — rejected: AUDIT_V3 was written
  hours ago, but for fast-moving libs (motion 12.37 → 12.38 in 1 week) the
  registry is more authoritative.

## References

- [`docs/AUDIT_V3.md`](../AUDIT_V3.md) §2, §5, §6, §7
- [`cfdomainpricing.com`](https://cfdomainpricing.com/) (verified 2026-05-02)
- npm registry queries logged in PHASE_0_LOG.md day-1 entry
