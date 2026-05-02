# `infra/secrets` — SOPS-encrypted secrets

All files in this directory (except this README and `.sops.yaml`) **must** be
SOPS-encrypted before commit. The `.gitignore` blocks `*.dec.*` and
`*.decrypted.*` to catch accidental decrypted leaks.

## Setup (one-time, Phase 0 Week 1 step 7)

### 1. Install age + sops on Win11

```powershell
# Via Scoop (recommended) or manual download from GitHub releases
scoop install age sops
# OR download:
#   https://github.com/FiloSottile/age/releases
#   https://github.com/getsops/sops/releases
```

### 2. Generate Eliot's age keypair

```powershell
mkdir -Force "$env:APPDATA\sops\age"
age-keygen -o "$env:APPDATA\sops\age\keys.txt"
# The OUTPUT line `# public key: age1...` must be copied into .sops.yaml
# (replace the placeholder).
```

### 3. Update `.sops.yaml`

Replace `age1placeholderpublickey...` in `creation_rules` with your real
public key, then commit.

### 4. Encrypt your first secret

```bash
# Create plaintext temporarily, then encrypt in place
cat > infra/secrets/anthropic.env <<EOF
ANTHROPIC_API_KEY=sk-ant-...
EOF

sops --encrypt --in-place infra/secrets/anthropic.env
```

### 5. Backup the age private key OFF the machine

The age private key is in `%APPDATA%\sops\age\keys.txt`. **If lost, all
encrypted secrets are unrecoverable.** Mirror it to:

- USB key (yone-secrets-vault) — already done if Phase 0 step 7 follows the runbook
- 1Password / Bitwarden as a Secure Note
- Optionally: print on paper and store in a safe

## Secrets currently expected (Phase 0 → 1)

| File | Contents | Source |
|------|----------|--------|
| `anthropic.env` | `ANTHROPIC_API_KEY` (workspace `ichor-prod`) | Anthropic Console |
| `cloudflare.env` | R2 access keys, API token, Tunnel credentials | Cloudflare Dashboard |
| `oanda.env` | OANDA practice account API key | OANDA developer portal |
| `fred.env` | FRED API key | research.stlouisfed.org |
| `azure-tts.env` | Azure Speech key + region | Azure portal |
| `langfuse-postgres.env` | random 32-byte password | generate locally |
| `n8n-postgres.env` | random 32-byte password | generate locally |
| `grafana-admin.env` | random 32-byte password | generate locally |
| `cerebras.env` | Cerebras API key (free tier) | cloud.cerebras.ai |
| `groq.env` | Groq API key (free tier) | console.groq.com |
| `github-pat.env` | GitHub PAT for Actions runner / `gh` | github.com/settings/tokens |

## Rotation cadence

- API keys (Anthropic, Cloudflare, etc.): every 90 days
- Local passwords (postgres, grafana): every 180 days
- Age keypair: every 2 years OR after any suspected compromise
