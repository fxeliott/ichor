#!/usr/bin/env bash
# redeploy-api.sh — safe, idempotent, self-verifying ichor_api redeploy
# on Hetzner (ADR-099 Tier 1.2a infrastructure).
#
# WHY THIS EXISTS : the backend is scp-deployed (`/opt/ichor` is not a
# git repo). Until now there was NO vetted API deploy script — ad-hoc
# scp+cp chains are the documented r63 "silent NO-OP" bug class (Python
# kept importing from a stale path). This codifies the deploy in the
# proven redeploy-brain.sh house pattern.
#
# VERIFIED PATH (R59, do NOT guess) : the ichor_api editable .pth points
# at `/opt/ichor/api/src/src` so the package lives at
# `/opt/ichor/api/src/src/ichor_api` (the double `src/src` is real). The
# obvious-looking `/opt/ichor/api/src/ichor_api` does NOT exist —
# deploying there would be a silent no-op. Step 1 HARD-CHECKS the path
# and fails loud on drift.
#
# Strategy :
#   1. Hard-check the remote package path exists (anti silent-noop).
#   2. Backup the remote package to a timestamped .bak (rollback < 30s).
#   3. tar-over-ssh the local package -> staging -> rsync into the
#      verified stable path (chown ichor). rsync is absent from Win11
#      Git-Bash; it runs server-side only (present there).
#   4. systemctl restart ichor-api ; wait /healthz == 200.
#   5. Verify a sample endpoint (the r76 /v1/geopolitics/briefing).
#   6. On ANY verify failure : auto-restore the .bak + restart + abort.
#
# Usage :
#   ./scripts/hetzner/redeploy-api.sh                 # deploy + verify
#   ./scripts/hetzner/redeploy-api.sh rollback        # restore latest .bak
#   ./scripts/hetzner/redeploy-api.sh --verify-only   # health probes only
#
# Idempotent. Pure bash (Voie D — no Python deps, ZERO Anthropic spend).

set -euo pipefail

SSH="ssh ichor-hetzner"
STABLE="/opt/ichor/api/src/src/ichor_api"
STAGING="/tmp/ichor_api_redeploy_staging"
BAK_ROOT="/opt/ichor/api/.redeploy-baks"
HEALTH="http://127.0.0.1:8000/healthz"
SAMPLE="http://127.0.0.1:8000/v1/geopolitics/briefing?hours=48&top=3"
SVC="ichor-api"

log() { printf '[%s] %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*" >&2; }
fail() { log "FATAL: $1"; exit "${2:-1}"; }

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LOCAL_PKG="${REPO_ROOT}/apps/api/src/ichor_api"
[[ -d "${LOCAL_PKG}" ]] || fail "local package not found: ${LOCAL_PKG}" 3

probe() { ${SSH} "curl -fsS -o /dev/null -w '%{http_code}' '$1' 2>/dev/null || echo 000"; }

cmd_verify_only() {
  local h s
  h="$(probe "${HEALTH}")"
  s="$(probe "${SAMPLE}")"
  log "healthz=${h} sample=${s}"
  [[ "${h}" == 200 ]] || fail "healthz not 200 (${h})" 6
  [[ "${s}" == 200 ]] || fail "sample endpoint not 200 (${s})" 7
  log "verify-only OK"
}

cmd_rollback() {
  log "rollback: restoring most recent .bak"
  ${SSH} "
    set -e
    LATEST=\$(ls -1dt ${BAK_ROOT}/ichor_api.* 2>/dev/null | head -1)
    [ -n \"\$LATEST\" ] || { echo 'no .bak found'; exit 4; }
    echo \"restoring \$LATEST -> ${STABLE}\"
    sudo rsync -a --delete \"\$LATEST/\" ${STABLE}/
    sudo chown -R ichor:ichor ${STABLE}
    sudo systemctl restart ${SVC}
  "
  sleep 4
  cmd_verify_only
  log "rollback complete"
}

cmd_deploy() {
  log "Step 1: hard-check verified remote path (anti silent-noop)"
  ${SSH} "test -d ${STABLE} && test -f ${STABLE}/main.py" \
    || fail "remote package path ${STABLE} missing/!main.py — path drift, refusing" 5

  log "Step 2: backup remote package -> ${BAK_ROOT}"
  local stamp
  stamp="$(date -u +%Y%m%d-%H%M%S)"
  ${SSH} "
    sudo mkdir -p ${BAK_ROOT}
    sudo rsync -a --delete ${STABLE}/ ${BAK_ROOT}/ichor_api.${stamp}/
    # keep only the 5 most recent baks
    ls -1dt ${BAK_ROOT}/ichor_api.* | tail -n +6 | xargs -r sudo rm -rf
  "

  log "Step 3: tar-over-ssh local package -> staging -> ${STABLE}"
  ${SSH} "rm -rf ${STAGING} && mkdir -p ${STAGING}"
  tar czf - -C "${REPO_ROOT}/apps/api/src" \
    --exclude='__pycache__' --exclude='*.pyc' --exclude='.pytest_cache' \
    ichor_api \
    | ${SSH} "tar xzf - -C ${STAGING}"
  ${SSH} "
    sudo rsync -a --delete ${STAGING}/ichor_api/ ${STABLE}/ &&
    sudo chown -R ichor:ichor ${STABLE} &&
    sudo rm -rf ${STAGING}
  "

  log "Step 4: restart ${SVC}; wait /healthz"
  ${SSH} "sudo systemctl restart ${SVC}"
  local h="000"
  for _ in $(seq 1 30); do
    h="$(probe "${HEALTH}")"
    [[ "${h}" == 200 ]] && break
    sleep 2
  done

  log "Step 5: verify health + sample endpoint"
  local s
  s="$(probe "${SAMPLE}")"
  log "RESULT: healthz=${h} sample(/v1/geopolitics/briefing)=${s}"
  if [[ "${h}" != 200 || "${s}" != 200 ]]; then
    log "verify FAILED — auto-rolling back to backup ichor_api.${stamp}"
    ${SSH} "
      sudo rsync -a --delete ${BAK_ROOT}/ichor_api.${stamp}/ ${STABLE}/ &&
      sudo chown -R ichor:ichor ${STABLE} &&
      sudo systemctl restart ${SVC}
    "
    sleep 4
    fail "deploy verify failed (healthz=${h} sample=${s}) — ROLLED BACK to ichor_api.${stamp}" 8
  fi
  log "DEPLOY OK — ichor_api synced + restarted, /healthz + sample 200. Backup: ichor_api.${stamp}"
}

case "${1:-deploy}" in
  deploy) cmd_deploy ;;
  rollback) cmd_rollback ;;
  --verify-only) cmd_verify_only ;;
  *) fail "usage: $0 [deploy|rollback|--verify-only]" 2 ;;
esac
