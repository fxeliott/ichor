# `infra/secrets` — SOPS-encrypted secrets

All files in this directory (except this README and `.sops.yaml`) **must** be
SOPS-encrypted before commit. The `.gitignore` blocks `*.dec.*` and
`*.decrypted.*` to catch accidental decrypted leaks.

## Status (2026-05-02)

✅ Setup complete. Eliot's age public key:
`age1rgrexge5x3qvf8hns4dhrfhu92zsl9nyem5t6ge4nqn424lxefcsl08xaj`

- Private key in `%APPDATA%\sops\age\keys.txt` (ACL Full Control eliot only)
- Backup on USB vault `E:\age-key-ichor-2026-05-02.txt` (SHA256-verified)
- 8 `.env.example` templates committed showing the structure of expected
  secret files

## Daily workflow

### Add a new secret

```bash
# 1. Copy the matching template
cp infra/secrets/anthropic.env.example infra/secrets/anthropic.env

# 2. Fill the real values
$EDITOR infra/secrets/anthropic.env

# 3. Encrypt in place (the .sops.yaml regex picks it up automatically)
sops --encrypt --in-place infra/secrets/anthropic.env

# 4. Commit the encrypted file
git add infra/secrets/anthropic.env
git commit -m "chore(secrets): add anthropic prod credentials"
```

### Edit an encrypted secret

```bash
sops infra/secrets/anthropic.env  # opens decrypted in $EDITOR, re-encrypts on save
```

### Decrypt all secrets locally for dev (gitignored output)

```bash
./scripts/decrypt-secrets.sh
# Decrypted plaintext lives in infra/secrets/_decrypted/ (gitignored)
```

## Original setup (one-time, done 2026-05-02)

### 1. Install age + sops on Win11

```powershell
# age: download age-vX.Y.Z-windows-amd64.zip from
#   https://github.com/FiloSottile/age/releases
# Unzip, copy age.exe + age-keygen.exe to C:\Users\eliot\.local\bin\
# (already in PATH)

# sops: installed via pip in .venv-tooling (D:\Ichor\.venv-tooling)
# Or globally: choco install sops  (if Chocolatey installed)
```

### 2. Generate Eliot's age keypair

```powershell
mkdir -Force "$env:APPDATA\sops\age"
age-keygen -o "$env:APPDATA\sops\age\keys.txt"
icacls "$env:APPDATA\sops\age\keys.txt" /inheritance:r /grant:r "${env:USERNAME}:F"
```

The OUTPUT line `# public key: age1...` must be copied into `.sops.yaml`.

### 3. Backup the age private key OFF the machine — CRITICAL

The age private key is in `%APPDATA%\sops\age\keys.txt`. **If lost, all
encrypted secrets are unrecoverable.** Mirror it to:

- ✅ USB key (`E:\age-key-ichor-2026-05-02.txt`, done 2026-05-02)
- ⬜ 1Password / Bitwarden as a Secure Note (recommended additional copy)
- ⬜ Optionally: print on paper, store in a safe

## Secrets currently expected (Phase 0 → 1)

| File                    | Contents                                      | Source                     |
| ----------------------- | --------------------------------------------- | -------------------------- |
| `anthropic.env`         | `ANTHROPIC_API_KEY` (workspace `ichor-prod`)  | Anthropic Console          |
| `cloudflare.env`        | R2 access keys, API token, Tunnel credentials | Cloudflare Dashboard       |
| `oanda.env`             | OANDA practice account API key                | OANDA developer portal     |
| `fred.env`              | FRED API key                                  | research.stlouisfed.org    |
| `azure-tts.env`         | Azure Speech key + region                     | Azure portal               |
| `langfuse-postgres.env` | random 32-byte password                       | generate locally           |
| `n8n-postgres.env`      | random 32-byte password                       | generate locally           |
| `grafana-admin.env`     | random 32-byte password                       | generate locally           |
| `cerebras.env`          | Cerebras API key (free tier)                  | cloud.cerebras.ai          |
| `groq.env`              | Groq API key (free tier)                      | console.groq.com           |
| `github-pat.env`        | GitHub PAT for Actions runner / `gh`          | github.com/settings/tokens |

## Rotation cadence

- API keys (Anthropic, Cloudflare, etc.): every 90 days
- Local passwords (postgres, grafana): every 180 days
- Age keypair: every 2 years OR after any suspected compromise
