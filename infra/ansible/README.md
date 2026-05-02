# `infra/ansible` — Ichor Hetzner provisioning

Idempotent Ansible playbook that takes a fresh Ubuntu 24.04 LTS Hetzner Cloud
server and brings it to Phase 0 baseline (steps 4 in `docs/ARCHITECTURE_FINALE.md`):

- Postgres 16 + TimescaleDB + Apache AGE
- Redis 7 (AOF, appendfsync everysec)
- wal-g 3.0.8 → Cloudflare R2 EU
- Python 3.12 + uv
- Node 22 + pnpm via Corepack
- Docker Engine + Compose plugin
- Loki + Grafana + Prometheus (docker-compose)
- Langfuse v3 (docker-compose, Postgres+Clickhouse+Redis+MinIO)
- n8n 1.78 (docker-compose)
- cloudflared (tunnel scaffold, configuration deferred to Week 3)

## Usage

**Important** : Ansible's control node does not run on native Windows
(see [`docs/decisions/ADR-007`](../../docs/decisions/ADR-007-ansible-bootstrap-from-hetzner.md)).
We bootstrap Ansible **on the Hetzner server itself**.

From local Win11 Git Bash:

```bash
# Dry-run (no changes)
scripts/run-ansible-on-hetzner.sh --check --diff

# Single role
scripts/run-ansible-on-hetzner.sh --tags postgres --diff

# Full run
scripts/run-ansible-on-hetzner.sh

# Specific extra-vars
scripts/run-ansible-on-hetzner.sh -e ufw_force_reset=true
```

The script:

1. Verifies SSH connectivity to `ichor-hetzner` alias
2. Installs `ansible-core` on the server if missing (idempotent)
3. `rsync`'s `infra/ansible/` to `/root/ansible` on the server
4. Installs required Galaxy collections (cached after first run)
5. Runs `ansible-playbook -i 'localhost,' -c local site.yml ...`

## Prerequisites

- Local: SSH alias `ichor-hetzner` working (see Phase 0 Week 1 step 2a setup)
- Local: `rsync` (Git Bash on Win11 ships with it)
- Target: Ubuntu 24.04 LTS — Ansible auto-installed on first run
- Target: **Hetzner Cloud snapshot taken before first run** (recovery 1-click)

## Required Galaxy collections (installed by the script)

- `community.general` — `community.general.timezone`, `community.general.locale_gen`,
  `community.general.ufw`
- `community.docker` — `community.docker.docker_compose_v2`
- `community.postgresql` — `community.postgresql.postgresql_ext`
- `ansible.posix` — `ansible.posix.sysctl`

## Why not WSL2?

Could work, but requires admin install + reboot on Eliot's Win11. Bootstrap-on-server is
zero-install and identical idempotency. See ADR-007.

## Status (2026-05-02)

🚧 Roles written, **not yet executed** against Hetzner. Will run after the
chirurgical cleanup completes (`docs/PHASE_0_LOG.md`).
