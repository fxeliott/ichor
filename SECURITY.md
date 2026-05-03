# Security policy

Ichor is a private, single-operator project (Eliot, France). It produces
financial research; the surface area is small but the data is sensitive
(market signals, alerts, persona prompts, R2 backups).

This file documents the **security model**, the **disclosure process**, and
the **known boundaries** of trust.

## Security model

### Threat actors considered in scope

- **Opportunistic scanners** (port-scanning, credential-stuffing, public
  endpoint enumeration). Fail2ban + UFW + SSH key-only auth handle this.
- **Compromised dependency** (npm/pypi supply-chain attack). Dependabot +
  pip-audit + npm audit, pinned versions, lockfile-frozen CI.
- **Stolen device** (laptop, phone). Disk encryption assumed at the OS
  level. Secrets are SOPS+age encrypted; the age private key sits on USB
  vault when not in use.
- **Cloud control-plane compromise** (Cloudflare account, Hetzner Cloud,
  GitHub). 2FA / YubiKey on each. Read-only CI tokens where possible.

### Threat actors NOT in scope

- **Targeted nation-state actors.** Out of scope at Phase 0; would require
  air-gapped key handling, hardware-attested compute, etc.
- **Insider threat.** Solo project — n/a.

### Trust boundaries

| Boundary | Trust direction | Mitigation |
|---|---|---|
| Internet → Cloudflare Tunnel → Win11 :8766 | untrusted → trusted | Cloudflare Access JWT verify (when enabled); rate limiter; UUID-secret-only fallback in Phase 0 |
| Hetzner :8000 (lo) → only local | trusted | Bind localhost-only; not exposed |
| GitHub Actions → Hetzner deploy | trusted (with HETZNER_SSH_PRIVATE_KEY secret) | Secret scoped to `deploy.yml`, only readable on `main` branch |
| LLM agents → output | untrusted | All outputs persisted with `briefing_markdown` source-of-truth; never auto-execute LLM output as code |

## Reporting a vulnerability

If you discover a vulnerability — or even a suspected one — please report it
**privately**, NOT through public issues.

- **Preferred** : email `eliottpena34690@gmail.com` with subject
  `[ICHOR-SECURITY] <short summary>`.
- Encrypt sensitive details with the public age key
  `age1rgrexge5x3qvf8hns4dhrfhu92zsl9nyem5t6ge4nqn424lxefcsl08xaj`
  (see [`infra/secrets/.sops.yaml`](infra/secrets/.sops.yaml) for current
  recipients).
- Expect acknowledgement within 72 h.
- Coordinated disclosure preferred. Public disclosure window : 90 days
  after fix is deployed (or earlier on mutual agreement).

## Secrets handling

| Type of secret | Where it lives | How it's used |
|---|---|---|
| Cloudflare API tokens, R2 keys, tunnel UUIDs | `infra/secrets/cloudflare.env` (SOPS+age) | Decrypted at runtime by Ansible / `ichor-decrypt-secrets` |
| Postgres `ichor` user password | `infra/secrets/postgres.env` (SOPS+age) | EnvironmentFile= for `ichor-api.service` |
| Grafana admin password | `infra/secrets/grafana.env` (SOPS+age) | Mounted as Docker secret |
| age private keys (Eliot + Hetzner) | `%APPDATA%\sops\age\keys.txt` (Win11 user dir) + USB vault | Local-only, never committed |
| Claude OAuth tokens (Max 20x) | `%USERPROFILE%\.claude\.credentials.json` (managed by `claude` CLI) | Read by user-mode `apps/claude-runner` only |
| GitHub Actions secrets (HETZNER_SSH_PRIVATE_KEY, etc.) | GitHub repo Settings → Secrets | Injected by workflow runner |

**Ground rules** :
- Never commit a `.env` file. The `.gitignore` blocks `.env*`,
  `*.pem`, `*.key`, `secrets/*.dec.*`.
- Never paste a secret into Claude Code chat (it gets stored in transcripts).
- Rotate any secret that touches a process that crashed or was terminated
  uncleanly (could have written to a swapfile).
- Multi-recipient SOPS files must include both Eliot's age key AND the
  Hetzner server age key for runtime decryption.

## Dependency hygiene

- **JS/TS** : pnpm lockfile-frozen CI install
  (`pnpm install --frozen-lockfile`). Dependabot weekly grouped updates
  (security-only get the merge-fast lane). `npm audit --audit-level=high`
  in `audit.yml` workflow.
- **Python** : per-package `uv sync` from `pyproject.toml` + lock.
  `pip-audit` in `audit.yml`.
- **Container images** : pinned by digest in
  `infra/ansible/roles/{observability,langfuse,n8n}/files/docker-compose.yml`.
  `trivy image` scan in `audit.yml`.
- **Filesystem** : `trivy fs` over the repo to catch committed secrets.

## Incident response

When a security incident is suspected :

1. **Stop the bleeding** :
   - If a credential is exposed : revoke at issuer (Cloudflare, Hetzner,
     GitHub) within 5 min.
   - If a process is exfiltrating : isolate the host
     (`ufw default deny outgoing` on the affected machine).
2. **Preserve evidence** : take a Hetzner snapshot before any cleanup so
   forensics can be done after.
3. **Pick the right runbook** :
   - Anthropic key compromise → [RUNBOOK-008](docs/runbooks/RUNBOOK-008-anthropic-key-revoked.md).
   - SSH key rotation → [RUNBOOK-002](docs/runbooks/RUNBOOK-002-ssh-key-rotation.md).
   - Postgres compromise / corruption → [RUNBOOK-003](docs/runbooks/RUNBOOK-003-postgres-corruption.md).
   - R2 bucket access lost → [RUNBOOK-004](docs/runbooks/RUNBOOK-004-r2-down.md).
   - Prompt injection in collector input → [RUNBOOK-006](docs/runbooks/RUNBOOK-006-prompt-injection.md).
4. **Document under** `docs/incidents/YYYY-MM-DD-<slug>.md`.

## Out-of-band disaster recovery

- **WAL-G basebackups → R2 EU** every Sunday 03h Paris.
- **Quarterly DR drill** : execute [RUNBOOK-010](docs/runbooks/RUNBOOK-010-walg-restore-drill.md).
  Last record : [`docs/dr-tests/2026-Q2-walg-drill.md`](docs/dr-tests/2026-Q2-walg-drill.md).
- **age private keys** backed up on USB vault (E:\), separate from laptop.
- **GitHub repo** is private; even a hostile reader of `main` learns the
  architecture but not the secrets (SOPS-encrypted).

## Acknowledged residual risks (Phase 0)

- **Cloudflare Access not yet enabled** on `claude-runner.fxmilyapp.com`.
  Tunnel currently relies on UUID-secret-only obscurity. Phase 1 fix : enable
  Access (free for ≤ 50 users) + service-token JWT verify.
- **No HSM for age keys.** Keys live as files. Acceptable for solo Phase 0;
  consider YubiKey-PIV for Phase 2+.
- **No SAST in CI.** Only dependency audit + secret scanning. Adding
  CodeQL or Semgrep is on the Phase 1 backlog.
- **No `predictions_audit` row-level access controls.** Single-tenant for
  now; if multi-tenant ever appears, RLS must be added.
