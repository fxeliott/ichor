# Session handoff — Ichor Phase 0 (2026-05-02 → 2026-05-03)

> Single document capturing the complete state at session end.
> Read this first when resuming work after `/clear` or new session.
> Authoritative timeline, current state, known issues, and next steps.

## TL;DR

**Phase 0 Voie D pipeline LIVE end-to-end.** A real briefing was generated
through the full chain (Hetzner → tunnel → Win11 → Claude Max 20x → Postgres).

```
36 commits on main, ~250 files, 11 ADRs, 9 runbooks, repo: github.com/fxeliott/ichor (private)
```

## Timeline of the session (2026-05-02 → 2026-05-03)

### Day 1 morning — read + plan + infra
1. Read ARCHITECTURE_FINALE + AUDIT_V3
2. Verified `ichor.app` taken → defer Phase 1 (ADR-002)
3. SSH access to Hetzner established (ED25519 + RSA legacy from vault)
4. Hetzner audit + backup tarball
5. Cleanup chirurgical (no full wipe — OS already 24.04, ADR-003)
6. Repo init Turborepo, 8 root config files, 12 packages structure
7. SOPS+age keypair generated, USB backup
8. Multi-recipient SOPS (Eliot's local key + Hetzner server key)

### Day 1 afternoon — Ansible + first services
9. Ansible foundation roles (base/security/docker/python/node/postgres/redis) GREEN
10. Apache AGE 1.5.0 built from source for PG16 (ADR-005)
11. wal-g 3.0.8 + R2 EU LIVE (basebackup + WAL archive verified)
12. 11 docker containers (Loki/Prom/Grafana + Langfuse stack + n8n) UP
13. Volume permission fixes for non-root container UIDs
14. claude-runner FastAPI implementation (subprocess + CF Access JWT + rate limiter)
15. Next.js 15 + first build green
16. SOPS + 9 .env templates + R2 credentials encrypted

### Day 2 — apps/api LIVE + tunnel + briefing test
17. apps/api real implementation (4 routers + WebSocket + briefing CLI)
18. Alembic migrations: 5 tables + TimescaleDB hypertable + AGE graph
19. Sample data seeded (8 bias_signals + 3 alerts + 1 briefing)
20. 33-alert engine (28 PLAN + 5 AUDIT_V2) + Crisis Mode composite
21. FRED collector (19 series)
22. Ichor-api uvicorn systemd service LIVE (verified /v1/briefings JSON)
23. ML scaffold expansion (concept drift, DTW, SABR stub, FOMC-RoBERTa)
24. 10 React+TS UI components (BiasBar, AssetCard, RegimeIndicator, DisclaimerBanner, ConfidenceMeter, SourceBadge, AlertChip, BriefingHeader, EmptyState, AudioPlayer)
25. /briefings/[id] dynamic page
26. 8 runbooks + 3 legal docs + 11 ADRs
27. GitHub Actions deploy workflow

### Day 2 — Cloudflare Tunnel saga (tricky)
28. Initial tunnel created with config_src=local — `<UUID>.cfargotunnel.com` only resolves to IPv6 ULA, not publicly routable
29. `cfut_` API token doesn't have scope to PUT /configurations (10405) — workaround via `cloudflared tunnel route dns` after Eliot did `cloudflared tunnel login`
30. Eliot migrated `fxmilyapp.com` from Hover DNS to Cloudflare (free plan)
31. CNAME `claude-runner.fxmilyapp.com` → tunnel UUID (proxied)
32. **Tunnel reachable from Hetzner** : HTTP 200, 330ms latency

### Day 2 — Auth pipeline workaround
33. claude -p returns 403 even after Eliot re-login: NSSM service runs as
    LocalSystem which can't access user-keychain OAuth credentials
34. Workaround: launch uvicorn AS USER on `:8766` (not the LocalSystem
    service on :8765 which stays idle)
35. Cloudflared ingress updated to point to :8766
36. **Real briefing generated end-to-end**: 461 tokens, 17s, $0 (Max 20x flat),
    French markdown respecting Ichor persona format

## Current LIVE state (verifiable RIGHT NOW)

### Hetzner (178.104.39.201)

| Service | Port | State | Auth |
|---|---|---|---|
| Postgres 16 + TimescaleDB 2.26.4 + Apache AGE 1.5.0 | 5432 (lo) | active | scram-sha-256 + Docker bridge |
| Redis 8.6.2 | 6379 (lo) | active, AOF | bind localhost |
| ichor-api uvicorn (systemd) | 8000 (lo) | active, /healthz=ok | none yet |
| Loki + Prometheus + Grafana (docker-compose) | 3001/9090/3100 | UP | grafana_admin in SOPS |
| Langfuse v3 + ClickHouse + MinIO | 3000 | UP | langfuse_*_password in SOPS |
| n8n 1.78.1 | 5678 | UP | n8n_postgres_password in SOPS |
| wal-g 3.0.8 → R2 ichor-walg-eu | systemd timer 03h Paris | enabled | R2 keys in SOPS |

### Win11 (Eliot's PC)

| Service | Port | State | How |
|---|---|---|---|
| **claude-runner uvicorn user-mode** | **8766** | **alive, claude_cli_available=true** | bash nohup |
| cloudflared tunnel | (outbound 443) | 4 connections MRS edge | bash nohup |
| OLD NSSM service IchorClaudeRunner | 8765 | running but idle (LocalSystem, can't access user OAuth) | NSSM |
| age 1.3.1 + sops 3.12.2 | — | installed | local bin |
| pnpm 10.33.2 + Node 24 + Python 3.14 | — | installed | local |
| age private key | — | `%APPDATA%\sops\age\keys.txt` + USB backup | — |

### Cloudflare

| Resource | Value |
|---|---|
| Account ID | `6bc2ed8d6d675701a9a54f4f3d9b2499` |
| Zone fxmilyapp.com | `f80b4469f67d1687211fd169a33258bf` (free plan, NS migrated from Hover) |
| Tunnel ID | `97aab1f6-bd98-4743-8f65-78761388fe77` |
| Tunnel name | `ichor-claude-runner` |
| Public hostname | `claude-runner.fxmilyapp.com` (proxied CNAME → cfargotunnel) |
| R2 bucket | `ichor-walg-eu` (EU jurisdiction) |
| API token (in SOPS) | `cfut_...` — has Tunnel:Edit + Access:Edit + Zone:Read but NOT DNS records:Edit |

### GitHub

- Repo `fxeliott/ichor` (private)
- 36 commits on `main`, CI green on latest
- Dependabot active (10 ecosystems)
- Auto-deploy.yml workflow ready (waits for `HETZNER_SSH_PRIVATE_KEY` secret)

## Pending blockers

### From Eliot (small, quick)

1. **Run `register-user-tasks.ps1`** (no admin) to make Win11 services persist across reboots
2. **GitHub repo secret `HETZNER_SSH_PRIVATE_KEY`** for deploy.yml auto-deploy
   (paste content of `~/.ssh/id_ed25519_ichor_hetzner` into Settings → Secrets → Actions → New)
3. (Optional) Free API keys: Cerebras + Groq + Azure Speech + OANDA + FRED

### Autonomy (no Eliot needed)

- Activate 5 Hetzner systemd timers for cron briefings (06h/12h/17h/22h Paris + Sun 18h)
- Trigger 1 manual briefing now to prove the timer-fired path works
- Phase 0 W2 collectors implementations (OANDA WS, RSS, Polymarket WS)
- Frontend pages /alerts + /assets/[code]
- 3 last UI components (ChartCard, DrillDownButton, +1)

## Known issues + workarounds discovered

| Issue | Workaround | Permanent fix |
|---|---|---|
| Win11 NSSM service runs as LocalSystem → can't read user OAuth tokens → claude -p 403 | Launch uvicorn as user on :8766 instead | Use `nssm set ObjectName .\eliot <password>` (need Eliot password) |
| `<UUID>.cfargotunnel.com` resolves to IPv6 ULA, unreachable | Use `cloudflared tunnel route dns` to bind hostname | none — by design |
| Cloudflare API token (cfut_) lacks DNS records:Edit scope | Use `cloudflared tunnel route dns` (CLI w/ cert.pem) for CNAME ops | Create new token with `Zone DNS: Edit` scope |
| PUT /configurations sometimes returns 10405 "Method not allowed" | Worked on retry — token may have transiently lacked perms during creation | always retry; verify scope via /user/tokens/verify |
| PowerShell can't parse em-dash `—` in scripts | Use ASCII dashes only in .ps1 files | save scripts as UTF-8 with BOM (Out-File -Encoding utf8BOM) |
| Eliot dismisses UAC prompts often | Avoid Start-Process -Verb RunAs, prefer scripts he runs once manually | n/a |
| `cloudflared service install <token>` ignores ~/.cloudflared/config.yml | Don't use service install with token, use scheduled task + nohup | n/a |
| TimescaleDB hypertable requires partitioning column in PK | Composite PK (id, generated_at) on predictions_audit | done in Alembic 0001 |
| pydantic-settings reads `.env` from CWD → permission error for service users | Drop env_file from SettingsConfigDict, use systemd EnvironmentFile only | done in apps/api/config.py |
| /etc/ichor mode 700 root-only blocks ichor user from reading files inside | chmod 750 + chown root:ichor | done |
| Apache AGE create_graph requires ag_catalog privileges (postgres only) | Grant USAGE/EXECUTE on ag_catalog to ichor + create graph as postgres | done in role + Ansible task |

## Critical commands ready to run

### Resume Win11 user-mode services after reboot

```powershell
powershell -ExecutionPolicy Bypass -File D:\Ichor\scripts\windows\start-claude-runner-user.ps1
powershell -ExecutionPolicy Bypass -File D:\Ichor\scripts\windows\start-cloudflared-user.ps1
```

### Run a manual briefing test from Hetzner

```bash
ssh ichor-hetzner 'curl -sS -X POST "https://claude-runner.fxmilyapp.com/v1/briefing-task" \
  -H "Content-Type: application/json" \
  -d "{\"briefing_type\":\"pre_londres\",\"assets\":[\"EUR_USD\"],\"context_markdown\":\"Briefing test\",\"model\":\"sonnet\",\"effort\":\"medium\"}" \
  --max-time 180' | python -m json.tool
```

### Trigger a real cron-style briefing via the run_briefing CLI

```bash
ssh ichor-hetzner 'cd /opt/ichor/api/src && \
  source /opt/ichor/api/.venv/bin/activate && \
  set -a && source /etc/ichor/api.env && set +a && \
  python -m ichor_api.cli.run_briefing pre_londres'
```

### Verify all services Hetzner-side

```bash
ssh ichor-hetzner '
systemctl is-active postgresql redis-server docker fail2ban ichor-api walg-basebackup.timer
docker ps --format "table {{.Names}}\t{{.Status}}" | head -15
sudo -u postgres psql -d ichor -c "SELECT count(*) FROM briefings; SELECT count(*) FROM bias_signals; SELECT count(*) FROM alerts;"
sudo -u postgres bash -c "set -a; source /etc/wal-g.env; set +a; wal-g backup-list"
'
```

## Cost summary (real, verified)

| Item | Cost | Status |
|---|---|---|
| Claude Max 20x | $200/mo flat | active (Eliot) |
| Hetzner CX32 | ~€20/mo flat | active |
| Cloudflare R2 (8.9 GB used) | $0/mo (free 10 GB) | active |
| Cloudflare Tunnel + DNS + Pages | $0/mo (free) | active |
| GitHub Actions (private repo) | $0/mo (within 2000 min/mo free) | active |
| **Total monthly** | **~$220** | flat, no surprise |

## Files of authority

- `docs/PHASE_0_LOG.md` — live status of 32 Phase 0 criteria
- `docs/decisions/` — 11 ADRs documenting every delta vs plan
- `docs/runbooks/` — 9 operational runbooks
- `docs/legal/` — AI disclosure + AMF mapping
- `infra/secrets/.sops.yaml` — multi-recipient encryption config
- `infra/ansible/site.yml` — playbook orchestrating 12 roles

## After /clear: how to resume

Paste in new session :

```
Reprends Ichor. Lis docs/SESSION_HANDOFF.md (autoritaire), docs/PHASE_0_LOG.md
(checklist 32 critères), git log --oneline | head -10. Vérifie services live
(curl http://127.0.0.1:8766/healthz, ssh ichor-hetzner systemctl is-active ichor-api).
Continue selon priorité Phase 0. Rappel: Voie D actée (ADR-009), pas d'API
consommation, Max 20x flat seul.
```

The 3 memories in `~/.claude/projects/D--Ichor/memory/` will auto-load critical
context (URLs, UUIDs, constraints, pickup template).
