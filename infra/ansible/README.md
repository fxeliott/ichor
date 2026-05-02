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

From `D:\Ichor\infra\ansible\`:

```bash
# Sanity check (won't change anything)
ansible-playbook -i inventory/hetzner.yml site.yml --check --diff

# Run for real
ansible-playbook -i inventory/hetzner.yml site.yml

# Run a single role
ansible-playbook -i inventory/hetzner.yml site.yml --tags postgres

# Run on a single host
ansible-playbook -i inventory/hetzner.yml site.yml --limit ichor-prod-1
```

## Prerequisites

- Local: `ansible-core ≥2.18` + collections (`community.general`, `community.docker`,
  `community.postgresql`, `ansible.posix`)
- Target: Ubuntu 24.04 LTS, SSH key in `~/.ssh/id_ed25519_ichor_hetzner`
- Hetzner Cloud snapshot taken before first run (recovery 1-click)

## Install collections

```bash
ansible-galaxy collection install community.general community.docker community.postgresql ansible.posix
```

## Status (2026-05-02)

🚧 Roles written, **not yet executed** against Hetzner. Will run after the
chirurgical cleanup completes (`docs/PHASE_0_LOG.md`).
