# Phase 0 — live log

> Started 2026-05-02. Target: 32 criteria green over 4 weeks (1 sem ≈ 7-10 days).
> Updated continuously by Claude Code as work progresses.

## Day-1 status (2026-05-02)

### Done

- ✅ Read & internalized `ARCHITECTURE_FINALE.md` + `AUDIT_V3.md` §2/5/6/7
- ✅ Verified Cloudflare Registrar `.app` price (US$14.20/yr, [cfdomainpricing.com](https://cfdomainpricing.com/) 2026-05-02)
- ✅ Verified `ichor.app` is **taken** (resolves to `185.158.133.1`, Lovable.dev project "ichor-vitality-nexus")
- ✅ Decision: **defer domain purchase to Phase 1+** → operate on `*.pages.dev` + `<TUNNEL-UUID>.cfargotunnel.com` (see [ADR-002](decisions/ADR-002-domain-deferred.md))
- ✅ SSH access to Hetzner established (`ichor-hetzner` alias, ED25519 key in `~/.ssh/id_ed25519_ichor_hetzner`)
- ✅ Legacy RSA key from yone-secrets-vault USB also imported as fallback (`hetzner-dieu` alias)
- ✅ Hetzner full audit done — saved to [`phase0-artifacts/hetzner-audit-pre-wipe-2026-05-02.txt`](../phase0-artifacts/hetzner-audit-pre-wipe-2026-05-02.txt) (551 lines)
- ✅ Backup tarball of `/etc` + UFW + fail2ban + SSH + sudoers + apt manifests — [`phase0-artifacts/pre-cleanup-backup-2026-05-02.tar.gz`](../phase0-artifacts/pre-cleanup-backup-2026-05-02.tar.gz) (154 KB, SHA256 verified)
- ✅ Decision: **cleanup chirurgical** (purge GUI + reset UFW) instead of full wipe (see [ADR-003](decisions/ADR-003-cleanup-vs-wipe.md))
- ✅ Repo monorepo Turborepo initialized (this commit) — apps/, packages/, infra/ansible/, docs/, .github/, scripts/
- ✅ Stack versions verified via context7 + npm registry — see [ADR-001](decisions/ADR-001-stack-versions-2026-05-02.md)
- ✅ pnpm 10.33.2 installed locally (official installer, per-user) — see [ADR-006](decisions/ADR-006-pnpm-via-official-installer.md)

### Awaiting

- ⏳ Eliot to take Hetzner Cloud snapshot via console (recovery 1-click before destructive cleanup)

### Next (after snapshot)

- 🔜 Run cleanup chirurgical SSH session: purge GUI packages (chromium, gnome, gtk, mesa, cups), reset UFW, remove orphan sudoers, disable failed cloud-init-hotplugd
- 🔜 Bootstrap `ansible-core` on Hetzner via `scripts/run-ansible-on-hetzner.sh` (see [ADR-007](decisions/ADR-007-ansible-bootstrap-from-hetzner.md))
- 🔜 Run `ansible-playbook --check --diff` (sanity check — no changes)
- 🔜 Run `ansible-playbook` for real (Postgres 16 + TimescaleDB + Apache AGE + Redis + wal-g + Docker + Loki/Grafana/Prometheus + Langfuse + n8n + cloudflared)

### Found during the day (deferred decisions)

- ❗ **Ansible doesn't run on native Windows** (`os.get_blocking()` + `grp` POSIX-only).
  Tested `ansible-core==2.20.5` with Python 3.14.4 → `WinError 87`.
  Decision: bootstrap on Hetzner itself ([ADR-007](decisions/ADR-007-ansible-bootstrap-from-hetzner.md)).
  WSL2 not installed, install requires admin + reboot — out of scope for autonomous session.
- ✅ All YAML files (24 Ansible + 3 GHA workflows) validated via pure Python `yaml.safe_load_all`.
- ✅ All JSON config files (7) validated.
- ✅ SSH connectivity to Hetzner re-verified at 13:35 UTC.

## Phase 0 — 32 criteria checklist

> Status legend: ⬜ not started · 🟡 in progress · 🟢 done · ⏸ deferred (with link)

### Semaine 1 — Infrastructure base

| # | Item | Status | Notes |
|---|------|--------|-------|
| 1 | Achat domaine `ichor.app` Cloudflare Registrar | ⏸ | Deferred Phase 1+ — see [ADR-002](decisions/ADR-002-domain-deferred.md) |
| 2 | Backup Hetzner pre-wipe (Langfuse + n8n + /etc + clés) | 🟢 | Reduced scope (no Langfuse/n8n on server) — see [ADR-003](decisions/ADR-003-cleanup-vs-wipe.md) |
| 3 | Wipe + réinstall Ubuntu 24.04 LTS | 🟡 | Replaced by cleanup chirurgical (OS already 24.04.4 LTS) — pending snapshot |
| 4 | Ansible playbook (Postgres 16 + TimescaleDB + Redis + Python 3.12 + uv + Node 22 + pnpm + Docker + Loki + Grafana + Prometheus + Langfuse + n8n) | 🟡 | Playbook **written**, not yet run |
| 5 | Init repo `ichor/` GitHub privé Turborepo | 🟡 | Local git init done, GitHub push pending Eliot OK |
| 6 | CI GitHub Actions stub vert + Dependabot + pip-audit + npm audit | 🟡 | Workflows written, not yet pushed |
| 7 | SOPS+age secrets management | 🟡 | `.sops.yaml` placeholder written, age key generation pending |
| 8 | Cloudflare Access zero-trust sur `*.ichor.app` + YubiKey MFA Cloudflare/Hetzner/GitHub/Anthropic | ⏸ | CF Access deferred (needs custom domain). YubiKey MFA in progress separately. |

### Semaine 2 — Couche 3 ML + Couche 2 LLM automation

| # | Item | Status | Notes |
|---|------|--------|-------|
| 9 | Cron systemd archiver HY/IG OAS J0 critique (FRED 3 ans rolling) | ⬜ | |
| 10 | wal-g WAL streaming Postgres → R2 EU bucket + 1er test restauration | ⬜ | wal-g role written, R2 bucket creation manual |
| 11 | Redis Streams setup + producers asyncio | ⬜ | |
| 12 | ML stack install (hmmlearn + dtaidistance + river + NumPyro + arch + ...) | ⬜ | `pyproject.toml` for `packages/ml` written |
| 13 | NLP self-host : FOMC-RoBERTa + FinBERT-tone HuggingFace download | ⬜ | |
| 14 | Cerebras free + Groq free wrappers Pydantic AI multi-provider | ⬜ | |
| 15 | Alerts engine 33 types + Crisis Mode triggers composite | ⬜ | |
| 16 | Tableau model_registry.yaml + 1 model card par modèle | ⬜ | |
| 17 | Table SQL `predictions_audit` complète | ⬜ | |

### Semaine 3 — Couche 1 Claude Code + tunnel

| # | Item | Status | Notes |
|---|------|--------|-------|
| 18 | Installation `cloudflared` Windows service ordi local Eliot | ⬜ | |
| 19 | Setup Cloudflare Tunnel sortant `claude-runner.ichor.internal` + service-token Hetzner | ⬜ | (tunnel UUID-based, no custom domain needed) |
| 20 | FastAPI local Win11 `:8765/briefing-task` + subprocess `claude -p` headless | ⬜ | `apps/claude-runner` skeleton written |
| 21 | Power Plan never sleep + gpedit Windows Update + WoL | ⬜ | |
| 22 | Test cron Task Scheduler 24h sur 4 timestamps Paris | ⬜ | |
| 23 | Test consommation Max 20x : 1 semaine de runs réels via `/usage-stats` | ⬜ | |
| 24 | Décision Voie D vs C selon résultats | ⬜ | |

### Semaine 4 — Frontend + storytelling + audio

| # | Item | Status | Notes |
|---|------|--------|-------|
| 25 | Next.js 15 minimal Cloudflare Pages deploy `app.ichor.app` | 🟡 | `apps/web` skeleton written. Deploy to `app-ichor.pages.dev` (no custom domain Phase 0) |
| 26 | Service worker PWA + VAPID push test (iOS Eliot + Android) | ⬜ | |
| 27 | 12 composants design system canon | ⬜ | `packages/ui` skeleton written, components TBD |
| 28 | Logo + palette + 3 mockups asset cards via skill `canvas-design` | ⬜ | |
| 29 | Setup Azure Speech key + voix `fr-FR-DeniseNeural` test 10 phrases finance | ⬜ | |
| 30 | Lexique phonétique custom v0 (`packages/agents/voice/lexicon_fr.json`) | ⬜ | |
| 31 | Persona Ichor v1 prompt finalisé `packages/agents/personas/ichor.md` | ⬜ | |
| 32 | Disclaimer modal AMF + AI disclosure obligatoire | ⬜ | |

## Deltas vs `ARCHITECTURE_FINALE.md` plan

These deltas are decisions made during execution, all documented as ADRs:

| Delta | Why | ADR |
|-------|-----|-----|
| Domain `ichor.app` → deferred + sub-domain Cloudflare gratuit | `ichor.app` taken by Lovable.dev project | [ADR-002](decisions/ADR-002-domain-deferred.md) |
| Wipe Ubuntu 24.04 → cleanup chirurgical | OS already 24.04.4 LTS, services to backup absent | [ADR-003](decisions/ADR-003-cleanup-vs-wipe.md) |
| Node 20 → Node 22 LTS | Node 20 LTS ended Apr 2026 | [ADR-004](decisions/ADR-004-node-22-not-20.md) |
| Hetzner backup minimal (no Langfuse/n8n data) | Services never deployed on this server | (covered in ADR-003) |
| pnpm via official installer (not corepack) | Corepack fails on Windows w/o admin | [ADR-006](decisions/ADR-006-pnpm-via-official-installer.md) |
| Ansible runs on Hetzner itself, not from Win11 | Ansible control node POSIX-only, WSL2 not installed | [ADR-007](decisions/ADR-007-ansible-bootstrap-from-hetzner.md) |
| Apache AGE built from source (not apt) | No apt package exists for PG16 | [ADR-005](decisions/ADR-005-apache-age-built-from-source.md) |

## Open questions for Eliot

- LICENSE choice: currently `UNLICENSED`. If/when published — MIT, Apache-2.0, AGPLv3, or proprietary?
- GitHub repo name: `ichor`? `ichor-platform`? Public or private (private recommended Phase 0)?
- Domain final choice: revisit at Phase 1 start (ichor.fyi $15.18, getichor.com $10.46, or custom?)
- Anthropic Workspace `ichor-prod` API key: when do we provision it (currently no API key, only Max 20x via local Claude Code)?
- R2 bucket `ichor-walg-eu`: who creates it and when (manually before wal-g first basebackup, or part of automation)?
