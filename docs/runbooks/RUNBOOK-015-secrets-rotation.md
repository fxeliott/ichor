# RUNBOOK-015: Secrets rotation procedure

- **Severity**: P1 (planned) / P0 (compromise) — depends on cause.
- **Last reviewed**: 2026-05-06
- **Time to resolve (target)**: 1-2h for a planned rotation ; 30-60 min for a compromise response (revoke first, rotate later).

## Trigger

### Planned cadence (preventive)
- Every **90 days** for app-level secrets (FRED API key, Polygon
  API key, etc.) — calendar entry in Eliot's task list.
- Every **60 days** for SSH keys (root + ichor user on Hetzner).
- Every **12 months** for the age master key (sops-encrypted
  secrets in `infra/secrets/*.age`).

### Compromise (reactive)
- A secret leaks publicly (committed to git, posted in screenshot, etc.).
- Eliot's laptop is lost / stolen.
- An external service flags an API key as compromised.
- Anthropic emails about banned account / API key revocation.

## Scope of secrets

`docs/SPEC_V2_HARDENING.md:84-90` defines the cadence ; this RUNBOOK
makes the procedure concrete.

| Secret | Storage | Cadence | Reset cost |
|---|---|---|---|
| FRED API key | `/etc/ichor/api.env` (Hetzner) | 90 d | 5 min |
| Polygon API key | `/etc/ichor/api.env` | 90 d | 5 min |
| Cloudflare API token | sops `infra/secrets/cf-api.age` | 90 d | 10 min |
| CF Access service token | `infra/secrets/cf-access.age` | 90 d | 15 min (when wired Phase A.7) |
| age master key | `~/.config/sops/age/keys.txt` (Eliot's machines) | 12 mo | 30 min |
| Hetzner SSH ED25519 (root) | `~/.ssh/id_ed25519_ichor` | 60 d | 15 min — see RUNBOOK-002 |
| Postgres `ichor` role pwd | `/etc/ichor/api.env` (DB_URL) | 90 d | 20 min |
| Redis pwd | `/etc/ichor/api.env` (REDIS_URL) | 90 d | 10 min |
| wal-g R2 creds | sops `infra/secrets/wal-g-r2.age` | 90 d | 15 min |
| VAPID keys (web push) | `apps/web2/.env.production` | 12 mo | depends on subscriber count (each device must re-subscribe) |
| Langfuse public + secret key | `/etc/ichor/api.env` | 90 d | 5 min |
| ntfy topic (when wired) | `/etc/ichor/ntfy.env` | 6 mo | 1 min |

## Diagnosis (compromise case)

```powershell
# Have the secret been committed?
git log --all --full-history --source -p -- '**/.env*' '**/secrets/**' 2>&1 | grep -i "<keyword>"
git log --all -S "<the_actual_value>" 2>&1
```

If a secret is in git history :
- **DO NOT** simply remove it from the latest commit.
- Treat the value as **fully compromised** — assume scrapers found it within 24h.
- Rotate immediately, then optionally rewrite history (`git filter-repo`
  / BFG) on a coordinated branch — but this is hard with a public mirror.

## Recovery — Generic rotation procedure

### Step 1 — Generate the new secret

Examples per secret type :

```bash
# FRED / Polygon / Anthropic — go to provider dashboard and revoke + recreate
# Cloudflare API token — https://dash.cloudflare.com/profile/api-tokens
# SSH keypair
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_ichor_v2 -C "eliot+ichor@$(date +%Y-%m)"
# Postgres role
NEW_PWD=$(openssl rand -base64 32 | tr -d '/+=' | head -c 28)
# age master key
age-keygen -o ~/.config/sops/age/keys-v2.txt
# VAPID
npx web-push generate-vapid-keys
# ntfy topic
NEW_TOPIC="ichor-alerts-$(openssl rand -hex 6)"
```

### Step 2 — Deploy the new secret atomically

For `/etc/ichor/api.env` style secrets :

```bash
ssh ichor-hetzner
sudo cp /etc/ichor/api.env /etc/ichor/api.env.bak-$(date +%Y%m%d-%H%M%S)
sudo nano /etc/ichor/api.env  # replace OLD_KEY=... with NEW_KEY=...
sudo systemctl restart ichor-api.service
sudo systemctl status ichor-api.service --no-pager | head -10
curl -s http://127.0.0.1:8000/healthz
```

For sops-encrypted secrets :

```bash
cd infra/secrets
sops cf-api.age  # opens $EDITOR with decrypted yaml — edit and save
git add cf-api.age
git commit -m "chore(secrets): rotate cf-api token (90d cadence)"
# Re-deploy via Ansible playbook that consumes infra/secrets/*.age
ansible-playbook -i infra/ansible/inventory.yml infra/ansible/site.yml --tags secrets
```

For SSH keys, see RUNBOOK-002 — the canonical procedure with atomic
`authorized_keys` swap and KVM fallback.

For the age master key (rare — annual) :
- Generate the new keypair (`age-keygen`).
- Re-encrypt every `infra/secrets/*.age` file with the new public key
  (sops `--add-age <new_pub_key>` then `--rm-age <old_pub_key>`).
- Distribute the new private key to authorized machines (Eliot's
  laptop + Hetzner deploy node).
- Commit the re-encrypted `*.age` files.
- Destroy the old private key (`shred ~/.config/sops/age/keys.txt.old`).

### Step 3 — Verify the new secret is the only one accepted

```bash
# Provider-side : confirm the OLD key is REVOKED in the dashboard.
# Most providers show a "last used" timestamp ; force-revoke + watch for
# 401s in app logs.

# App-side
ssh ichor-hetzner
sudo journalctl -u ichor-api.service -p err --since "5 minutes ago"
# Expected : no "401 Unauthorized" entries from external APIs.
```

### Step 4 — Update the rotation log

Append to `docs/dr-tests/secrets-rotation-log.md` :

```markdown
| Date       | Secret                | Cause       | Operator | Verified |
| ---------- | --------------------- | ----------- | -------- | -------- |
| 2026-05-06 | FRED API key (90d)    | scheduled   | Eliot    | ✓        |
```

This log is the audit trail (Article 16 MiFID-grade if Ichor research
is ever sold — cf ADR-029).

## Compromise-specific add-ons

If the rotation is reactive (a leak happened) :

1. **Revoke first, rotate after**. Most providers' "revoke" button is
   immediate ; stop the bleeding before regenerating.
2. **Audit the blast radius** : grep all access logs for the
   compromised key in the last 30 days. Look for unexpected source IPs.
3. **File a security incident** in `docs/incidents/` with timeline,
   blast radius, and lessons.
4. **Post-mortem** if any user-facing impact ; otherwise an internal
   note suffices.

## Post-incident

- Log incident in `docs/incidents/secrets-YYYY-MM-DD.md`.
- Update calendar reminder for the next rotation cadence.
- If the cause was a process gap (e.g. secret committed via `.env`
  file not in `.gitignore`), patch the gap (add to `.gitignore`,
  add a pre-commit hook, etc.).

## Related

- RUNBOOK-002 — SSH key rotation (concrete steps for SSH specifically).
- RUNBOOK-008 — Anthropic key revoked (a special case).
- ADR-009 — Voie D no Anthropic SDK (so Anthropic creds rotation is
  via the `claude` CLI login, not an env var).
- `docs/SPEC_V2_HARDENING.md` — overall security policy (cadences).
- `infra/secrets/README.md` — sops + age workflow (the "how" of
  encrypting / decrypting `*.age` files).
