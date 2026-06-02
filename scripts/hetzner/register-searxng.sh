#!/usr/bin/env bash
# register-searxng.sh — deploy/refresh the self-hosted SearXNG metasearch used
# by apps/api web research (ADR-084, Prompt_Ichor §6). Loopback-only
# (127.0.0.1:8081), never public. Voie D: $0 marginal, no metered LLM.
#
# Idempotent: safe to re-run. Generates server.secret_key once (preserved on
# re-runs), syncs the compose + settings, brings the container up, verifies the
# JSON API. Win11 Git-Bash compatible (single-connection tar-pipe, no rsync).
#
# Usage:
#   ./scripts/hetzner/register-searxng.sh          # deploy + verify
#   ./scripts/hetzner/register-searxng.sh verify   # JSON probe only
#
# NB on Docker networking: the daemon default-address-pool (172.20.0.0/16) is
# fully consumed by the ichor-n8n network, so the compose pins an explicit
# subnet (172.21.0.0/24) to avoid "all predefined address pools fully
# subnetted" without a disruptive dockerd restart.
set -euo pipefail

SSH="ssh -o ConnectTimeout=25 ichor-hetzner"
REMOTE_DIR="/opt/ichor/searxng"
LOCAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../infra/ansible/roles/searxng/files" && pwd)"
PROBE_Q="EUR%20USD%20ECB%20today"

log() { printf '[%s] %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*" >&2; }
fail() { log "FATAL: $1"; exit "${2:-1}"; }

if [[ "${1:-}" == "verify" ]]; then
  log "verify-only: JSON probe"
  $SSH "curl -s 'http://127.0.0.1:8081/search?q=${PROBE_Q}&format=json' | python3 -c 'import sys,json;print(\"results:\",len(json.load(sys.stdin).get(\"results\",[])))'" \
    || fail "JSON probe failed"
  exit 0
fi

[[ -f "$LOCAL_DIR/docker-compose.yml" && -f "$LOCAL_DIR/settings.yml" ]] \
  || fail "missing compose/settings in $LOCAL_DIR"

log "Step 1: sync compose + settings (single-connection tar-pipe) + inject secret if absent"
tar czf - -C "$LOCAL_DIR" docker-compose.yml settings.yml | $SSH '
  set -e
  mkdir -p '"$REMOTE_DIR"'
  # Preserve an already-injected secret across re-runs.
  EXISTING=""
  if [ -f '"$REMOTE_DIR"'/settings.yml ]; then
    EXISTING=$(grep -oE "secret_key: \"[0-9a-f]{16,}\"" '"$REMOTE_DIR"'/settings.yml | head -1 | sed "s/secret_key: //; s/\"//g" || true)
  fi
  tar xzf - -C '"$REMOTE_DIR"'
  SECRET="$EXISTING"
  if [ -z "$SECRET" ] || [ "$SECRET" = "REPLACE_AT_DEPLOY" ]; then SECRET=$(openssl rand -hex 32); fi
  sed -i "s/REPLACE_AT_DEPLOY/$SECRET/" '"$REMOTE_DIR"'/settings.yml || true
  echo "secret_present=$( [ -n "$SECRET" ] && echo yes || echo no )"
' || fail "sync/secret step failed"

log "Step 2: docker compose up -d"
$SSH "cd $REMOTE_DIR && docker compose up -d" || fail "compose up failed"

log "Step 3: wait + verify JSON API"
$SSH "sleep 20 && curl -s 'http://127.0.0.1:8081/search?q=${PROBE_Q}&format=json' | python3 -c 'import sys,json; d=json.load(sys.stdin); n=len(d.get(\"results\",[])); print(\"results:\",n); exit(0 if n>0 else 1)'" \
  || fail "JSON API verify failed (0 results)"

log "DONE — SearXNG live on 127.0.0.1:8081, JSON API returning results."
