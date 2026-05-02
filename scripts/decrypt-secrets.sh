#!/usr/bin/env bash
# Ichor — decrypt all SOPS-encrypted secrets to a local cache for dev.
# Usage: ./scripts/decrypt-secrets.sh
# Output: infra/secrets/_decrypted/*  (gitignored — see .gitignore)

set -euo pipefail

ICHOR_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SECRETS_DIR="$ICHOR_ROOT/infra/secrets"
OUT_DIR="$SECRETS_DIR/_decrypted"

if ! command -v sops >/dev/null 2>&1; then
  echo "ERROR: sops not installed. See infra/secrets/README.md for setup."
  exit 1
fi
if ! command -v age >/dev/null 2>&1; then
  echo "ERROR: age not installed. See infra/secrets/README.md for setup."
  exit 1
fi

# age key location (default per SOPS convention)
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
  AGE_KEY="$APPDATA/sops/age/keys.txt"
else
  AGE_KEY="$HOME/.config/sops/age/keys.txt"
fi
if [ ! -f "$AGE_KEY" ]; then
  echo "ERROR: age private key not found at $AGE_KEY"
  echo "       See infra/secrets/README.md step 2 to generate one."
  exit 1
fi
export SOPS_AGE_KEY_FILE="$AGE_KEY"

mkdir -p "$OUT_DIR"

shopt -s nullglob
for enc_file in "$SECRETS_DIR"/*.{env,yml,yaml,json}; do
  [ -e "$enc_file" ] || continue
  base="$(basename "$enc_file")"
  out="$OUT_DIR/$base"
  echo "Decrypting $base..."
  sops --decrypt "$enc_file" > "$out"
  chmod 600 "$out"
done

echo "Decrypted to: $OUT_DIR"
echo "(this directory is gitignored)"
