# Phase 0 — live log

> Started 2026-05-02. Target: 32 criteria green over 4 weeks (1 sem ≈ 7-10 days).
> Updated continuously by Claude Code as work progresses.

## Day-1 cumulative status (end of session, 2026-05-02 evening)

**26 commits** on `main`, **~250 files**, all pushed to `fxeliott/ichor` private repo.
CI green. Dependabot active. Auto-deploy.yml workflow ready.

### LIVE on Hetzner (verified end-to-end via HTTP)

| Service | State |
|---|---|
| Postgres 16 + TimescaleDB 2.26.4 + Apache AGE 1.5.0 | active, 5432 localhost-only |
| Redis 8.6.2 (AOF) | active, 6379 localhost-only |
| 5 ORM tables created via Alembic | briefings, alerts, predictions_audit (TS hypertable), bias_signals, alembic_version |
| AGE graph `ichor_graph` | created |
| ichor-api (uvicorn 2 workers) | systemd service active, /healthz=ok, db+redis connected |
| Sample data seeded | 8 bias_signals + 3 alerts + 1 briefing visible via API |
| wal-g 3.0.8 → R2 EU | 1 basebackup + WAL archive verified |
| 11 docker containers | Loki + Prometheus + Grafana + Langfuse stack + n8n stack — all UP |
| fail2ban + UFW + SSH hardening | active |

### LIVE on Win11

| Service | State |
|---|---|
| claude-runner Windows service | NSSM-managed, auto-restart, /healthz=ok, persona loaded, claude_cli_available=true |
| pnpm + Node 24 + Python 3.14 + age + sops | installed |
| Power plan never-sleep | configured |

### Awaits Eliot manual (~20 min total to fully unblock)

- ⏳ `claude auth logout && claude auth login` — unblocks 403 issue (ADR-010), enables real briefing tests
- ⏳ Cloudflare Tunnel setup (winget cloudflared + login + Access app + service token)
- ⏳ GitHub repo secret `HETZNER_SSH_PRIVATE_KEY` for deploy.yml workflow
- ⏳ (optional) Free API keys: Cerebras, Groq, Azure Speech F0, OANDA Practice, FRED

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

### Cleanup + Ansible foundation run (afternoon, 14:08-16:30 UTC)

- ✅ **Hetzner cleanup chirurgical** done (no snapshot — Eliot waived it
  saying "tu peux supprimer ce qu'il y a avant"). 1.6 Go freed (8.9 → 7.3),
  4 snaps removed (chromium ×2, cups, gnome+gtk+mesa), UFW reset to 22+80+443,
  orphan sudoers removed, cloud-init-hotplugd disabled. SSH still works.
- ✅ **Ansible bootstrap on Hetzner** : ansible-core 2.20.5 in /opt/ansible-venv
  (apt's 2.16.3 too old for current community.* collections). Galaxy collections
  installed: ansible.posix 2.1.0, community.postgresql 4.2.0, community.docker 5.2.0,
  community.general 12.6.0.
- ✅ **Foundation roles GREEN** (run for real, not --check):
  - `base`: timezone Europe/Paris, locale fr, kernel sysctl tuned (vm.swappiness=10,
    vm.overcommit_memory=1, net.core.somaxconn=65535, fs.file-max=2097152),
    unattended-upgrades configured (security only, no auto-reboot), apt safe upgrade
    (41 packages including kernel 6.8.0-101 → 6.8.0-111).
  - `security`: SSH hardening drop-in /etc/ssh/sshd_config.d/00-ichor-hardening.conf,
    UFW propre (22 limit + 80 + 443), fail2ban jail.local for sshd.
  - `docker`: Docker Engine + Compose plugin via official repo, daemon.json with
    log rotation 100 MB × 5 + custom address pool 172.20.0.0/16.
  - `python`: Ubuntu 24.04 default Python 3.12 + python3-dev/venv/pip + uv 0.11.8.
  - `node`: Node.js 22 LTS via NodeSource (legacy nodesource.sources cleaned up
    pre-install) + pnpm via Corepack.
  - `postgres`: Postgres 16 + TimescaleDB 2.26.4 + python3-psycopg2 + custom
    postgresql-ichor.conf (4 GB shared_buffers, 12 GB effective_cache_size, 200
    max_connections) + restrictive pg_hba.conf (deny all except local + Docker
    bridges 172.17/172.20). **Apache AGE 1.5.0 BUILT FROM SOURCE** against PG16
    (no apt package). Both extensions enabled in `postgres` database.
  - `redis`: Redis 8.6.2 with AOF (appendfsync everysec, maxmemory 2GB,
    allkeys-lru). NB: apt serves 8.x not 7.x — see [ADR-008](decisions/ADR-008-redis-8-not-7.md).
- ✅ **Verified live**: `psql SELECT version()` OK, `LOAD 'age'; create_graph('test_g')` OK,
  `redis-cli PING` → PONG, listening ports localhost-only for DBs (5432, 6379).

### Bugs found + fixed during Ansible run (committed)

| Symptom | Root cause | Fix |
|---------|-----------|-----|
| `community.general.yaml` callback removed | Plugin moved to ansible-core 2.13+ | `stdout_callback = ansible.builtin.default` + `[callback_default] result_format = yaml` |
| UFW `No closing quotation` on port 80 | Shell quoting broken by `'` in "Let's Encrypt" | Changed comment to "Lets Encrypt" |
| `swapon: Device or resource busy` | Idempotence check matched wrong stderr substring | Use `swapon --show` to detect already-active before invoking |
| `Failed to update apt cache` (deadsnakes PPA) | Ubuntu 24.04 ships Python 3.12 natively | Removed deadsnakes; just install python3-dev/venv/pip |
| `Conflicting Signed-By` (NodeSource) | Pre-existing nodesource.sources DEB822 file | Pre-cleanup: remove legacy `/usr/share/keyrings/nodesource.gpg` + `nodesource.sources` |
| `psycopg2 not found` (postgresql_ext) | Module dependency missing | Added `python3-psycopg2` to postgres apt list |
| `server closed connection` (CREATE EXTENSION timescaledb) | shared_preload_libraries pending restart | `meta: flush_handlers` before extension enabling |
| `db is deprecated` warning | community.postgresql 4.x renamed | Use `login_db` instead of `db` |

## Phase 0 — 32 criteria checklist

> Status legend: ⬜ not started · 🟡 in progress · 🟢 done · ⏸ deferred (with link)

### Semaine 1 — Infrastructure base

| # | Item | Status | Notes |
|---|------|--------|-------|
| 1 | Achat domaine `ichor.app` Cloudflare Registrar | ⏸ | Deferred Phase 1+ — see [ADR-002](decisions/ADR-002-domain-deferred.md) |
| 2 | Backup Hetzner pre-wipe (Langfuse + n8n + /etc + clés) | 🟢 | Reduced scope (no Langfuse/n8n on server) — see [ADR-003](decisions/ADR-003-cleanup-vs-wipe.md) |
| 3 | Wipe + réinstall Ubuntu 24.04 LTS | 🟢 | Replaced by cleanup chirurgical (OS already 24.04.4 LTS), executed without snapshot per Eliot — see [ADR-003](decisions/ADR-003-cleanup-vs-wipe.md) |
| 4 | Ansible playbook (Postgres 16 + TimescaleDB + Redis + Python 3.12 + uv + Node 22 + pnpm + Docker + Loki + Grafana + Prometheus + Langfuse + n8n) | 🟢 | **ALL 11 ROLES GREEN** — base+security+docker+python+node+postgres+redis+walg+observability+langfuse+n8n+cloudflared. 11 containers UP (verified HTTP 200 langfuse/n8n/grafana/prometheus, Loki ready). Multi-recipient SOPS (Eliot + Hetzner age keys), secrets role decrypts at runtime with `no_log`. |
| 5 | Init repo `ichor/` GitHub privé Turborepo | 🟢 | `fxeliott/ichor` private, 17 commits pushed, default branch `main` |
| 6 | CI GitHub Actions stub vert + Dependabot + pip-audit + npm audit | 🟢 | CI green on commit 33b6033+; Dependabot weekly grouped updates active |
| 7 | SOPS+age secrets management | 🟢 | age 1.3.1 + sops live; keypair generated (`age1rgrexge5x3qvf8hns4dhrfhu92zsl9nyem5t6ge4nqn424lxefcsl08xaj`); private key backed up to USB E:\; `.sops.yaml` updated; round-trip OK; 8 `.env.example` templates committed |
| 8 | Cloudflare Access zero-trust sur `*.ichor.app` + YubiKey MFA Cloudflare/Hetzner/GitHub/Anthropic | ⏸ | CF Access deferred (needs custom domain). YubiKey MFA in progress separately. |

### Semaine 2 — Couche 3 ML + Couche 2 LLM automation

| # | Item | Status | Notes |
|---|------|--------|-------|
| 9 | Cron systemd archiver HY/IG OAS J0 critique (FRED 3 ans rolling) | 🟡 | FRED collector live in `apps/api/src/ichor_api/collectors/fred.py` (19 series wired incl. BAMLH0A0HYM2 + BAMLC0A0CMTRIV). Systemd timer pending Eliot's FRED key |
| 10 | wal-g WAL streaming Postgres → R2 EU bucket + 1er test restauration | 🟢 | wal-g 3.0.8 LIVE: basebackup `base_000000010000000000000006` written to R2 `ichor-walg-eu/postgres/basebackups_005/`, 3 WAL files archived to `wal_005/`. systemd timer `walg-basebackup.timer` enabled (next: Sun 03:08 Paris). archive_mode=on + archive_command=`/usr/local/bin/wal-g-archive %p` flipped on. `set -a` fix in wrapper for env propagation. **Restore test pending Phase 0 W2.** |
| 11 | Redis Streams setup + producers asyncio | 🟡 | Redis Pub/Sub channels wired in `apps/api/src/ichor_api/routers/ws.py` (briefings:new, alerts:new, bias:updated). Production via cli/run_briefing.py publishes on success |
| 12 | ML stack install (hmmlearn + dtaidistance + river + NumPyro + arch + ...) | 🟡 | Scaffolds written: `packages/ml/src/ichor_ml/{regime/hmm.py,vol/har_rv.py,microstructure/vpin.py,bias_aggregator.py}`. Real training pending data collectors (step 11) |
| 13 | NLP self-host : FOMC-RoBERTa + FinBERT-tone HuggingFace download | 🟡 | FinBERT-tone wrapper live in `packages/ml/src/ichor_ml/nlp/finbert_tone.py` (lazy load + lru_cache + batch + aggregate_tone). FOMC-RoBERTa pending |
| 14 | Cerebras free + Groq free wrappers Pydantic AI multi-provider | 🟡 | Code committed: `packages/agents/src/ichor_agents/{providers.py,fallback.py}`. Awaits Cerebras + Groq free-tier API keys from Eliot |
| 15 | Alerts engine 33 types + Crisis Mode triggers composite | 🟢 | Catalog (`alerts/catalog.py`) 28 PLAN + 5 AUDIT_V2 = 33 alerts; 7 crisis_mode triggers. `evaluator.py` evaluate_metric() walks catalog with above/below/cross_up/cross_down. `crisis_mode.py` assess_crisis() composite with min_concurrent + lookback. `assert_catalog_complete()` startup guard |
| 16 | Tableau model_registry.yaml + 1 model card par modèle | 🟡 | `packages/ml/model_registry.yaml` committed with 5 scaffolded + 6 planned entries |
| 17 | Table SQL `predictions_audit` complète | 🟢 | **LIVE on Hetzner Postgres** — alembic 0001 migration applied; predictions_audit converted to TimescaleDB hypertable (chunks 7d, partitioned by generated_at, composite PK id+generated_at). Plus 3 sister tables (briefings, alerts, bias_signals) |

### Semaine 3 — Couche 1 Claude Code + tunnel

| # | Item | Status | Notes |
|---|------|--------|-------|
| 18 | Installation `cloudflared` Windows service ordi local Eliot | 🟡 | Runbook + config template ready: `infra/cloudflare/README.md` + `tunnel-config.yml`. Awaits Eliot to run `cloudflared tunnel login` (browser oauth, 5 min) |
| 19 | Setup Cloudflare Tunnel sortant `claude-runner.ichor.internal` + service-token Hetzner | 🟡 | Step-by-step Eliot runbook in `infra/cloudflare/README.md`. Expected UUID-based URL: `<UUID>.cfargotunnel.com` |
| 20 | FastAPI local Win11 `:8765/briefing-task` + subprocess `claude -p` headless | 🟢 | **Real implementation done** in `apps/claude-runner/`: FastAPI app + CF Access JWT verify + asyncio subprocess wrapper + sliding-hour rate limiter + persona Ichor v1. Tests for rate limiter + Pydantic models. Service installer at `scripts/windows/install-claude-runner-service.ps1` (NSSM-based, auto-restart) |
| 21 | Power Plan never sleep + gpedit Windows Update + WoL | 🟡 | `scripts/windows/setup-power-plan.ps1` ready (run as admin). gpedit Windows Update active hours documented |
| 22 | Test cron Task Scheduler 24h sur 4 timestamps Paris | 🟡 | `scripts/hetzner/register-cron-briefings.sh` registers 5 systemd timers (06h/12h/17h/22h Paris + Sun 18h weekly). Service shreds /dev/shm secrets after each run |
| 23 | Test consommation Max 20x : 1 semaine de runs réels via `/usage-stats` | ⬜ | Pending real briefings (after step 18-22 deployment) |
| 24 | Décision Voie D vs C selon résultats | 🟢 | **Voie D acted irrevocably 2026-05-02** — see [ADR-009](decisions/ADR-009-voie-d-no-api-consumption.md). No Anthropic API key. Production runs Max 20x via local subprocess. |

### Semaine 4 — Frontend + storytelling + audio

| # | Item | Status | Notes |
|---|------|--------|-------|
| 25 | Next.js 15 minimal Cloudflare Pages deploy `app.ichor.app` | 🟡 | `apps/web` skeleton written. Deploy to `app-ichor.pages.dev` (no custom domain Phase 0) |
| 26 | Service worker PWA + VAPID push test (iOS Eliot + Android) | ⬜ | |
| 27 | 12 composants design system canon | 🟡 | **9/12 live** in `packages/ui/src/components/`: BiasBar, AssetCard, RegimeIndicator, DisclaimerBanner, ConfidenceMeter, SourceBadge, AlertChip, BriefingHeader, EmptyState, AudioPlayer. Remaining 3 (ChartCard, DrillDownButton, plus 1 TBD) Phase 0 W4 last push |
| 28 | Logo + palette + 3 mockups asset cards via skill `canvas-design` | ⬜ | |
| 29 | Setup Azure Speech key + voix `fr-FR-DeniseNeural` test 10 phrases finance | 🟡 | Wrapper code done: `packages/agents/src/ichor_agents/voice/tts.py` (Azure REST + SSML pauses + Piper fallback). Awaits Eliot's `AZURE_SPEECH_KEY` (free F0 tier) |
| 30 | Lexique phonétique custom v0 (`packages/agents/voice/lexicon_fr.json`) | 🟢 | 130+ entries committed: pairs, indices, central banks, macro, vol/positioning, energy, idioms |
| 31 | Persona Ichor v1 prompt finalisé `packages/agents/personas/ichor.md` | 🟢 | Committed in `apps/claude-runner/src/ichor_claude_runner/personas/ichor.md` — sober FR voice, probabilistic, AMF + EU AI Act Article 50 footer baked in |
| 32 | Disclaimer modal AMF + AI disclosure obligatoire | 🟢 | `<DisclaimerBanner>` component live (compact + full forms, non-dismissible per legal). `docs/legal/ai-disclosure.md` canonical FR wording + EU AI Act Article 50 mapping. `docs/legal/amf-mapping.md` DOC-2008-23 classification + 5 design constraints to stay in general-research scope |

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
| Redis 8.x accepted (not 7) | apt repo serves 8 now, license + API OK | [ADR-008](decisions/ADR-008-redis-8-not-7.md) |
| Voie D irrevocably acted (no API consumption) | Eliot's flat-cost preference | [ADR-009](decisions/ADR-009-voie-d-no-api-consumption.md) |

## Open questions for Eliot

- LICENSE choice: currently `UNLICENSED`. If/when published — MIT, Apache-2.0, AGPLv3, or proprietary?
- Domain final choice: revisit at Phase 1 start (ichor.fyi $15.18, getichor.com $10.46, or custom?)
- ~~Anthropic Workspace `ichor-prod` API key~~ — **resolved**: Voie D, no API key (ADR-009)
- ~~R2 bucket~~ — **resolved**: created + creds encrypted (commit 7a0eb3b)
- ~~GitHub repo~~ — **resolved**: `fxeliott/ichor` private, 12 commits pushed, CI green
