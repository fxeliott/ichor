#!/usr/bin/env bash
# redeploy-brain-tar.sh — Win11-compatible deploy script for the
# ichor_brain package, mirror of redeploy-agents.sh r172b infrastructure.
#
# WHY THIS EXISTS : `redeploy-brain.sh` (r64) uses local `rsync` which is
# ABSENT on Win11 Git-Bash (cf. r168 memory : "redeploy-brain.sh broken
# Win11 rsync absent"). The historical workaround was manual tar+scp+ssh.
# r172b codified this for `ichor_agents` ; r172c codifies the same for
# `ichor_brain`.
#
# This script mirrors `redeploy-agents.sh` decompose pattern (Pattern #16
# R-DEPLOY-6 Step-3 + Pattern #14 SSH-retry resilience) :
#   1. Hard-check .pth + remote canonical path
#   2. Backup remote package (rsync server-side, fine — only local rsync is missing)
#   3. local-tar → scp → ssh-extract (3 short retryable calls)
#   4. Clear *.pyc via find -delete (no destructive recursive patterns)
#   5. systemctl restart ichor-api (re-import fresh brain)
#   6. Verify /healthz == 200, auto-rollback on failure
#
# Usage (Win11 + Linux compatible) :
#   ./scripts/hetzner/redeploy-brain-tar.sh                 # deploy + verify
#   ./scripts/hetzner/redeploy-brain-tar.sh rollback        # restore latest .bak
#   ./scripts/hetzner/redeploy-brain-tar.sh --verify-only   # health probes only
#
# Idempotent. Pure bash. Voie D — no Python deps.

set -euo pipefail

SSH="ssh ichor-hetzner"
STABLE="/opt/ichor/packages/ichor_brain/src/ichor_brain"
STAGING="/tmp/ichor_brain_redeploy_staging"
BAK_ROOT="/opt/ichor/packages/ichor_brain/.redeploy-baks"
HEALTH="http://127.0.0.1:8000/healthz"
PTH_FILE="/opt/ichor/api/.venv/lib/python3.12/site-packages/_editable_impl_ichor_brain.pth"
EXPECTED_PTH_CONTENT="/opt/ichor/packages/ichor_brain/src"
SVC="ichor-api"

log() { printf '[%s] %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*" >&2; }
fail() { log "FATAL: $1"; exit "${2:-1}"; }

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LOCAL_PKG="${REPO_ROOT}/packages/ichor_brain/src/ichor_brain"
[[ -d "${LOCAL_PKG}" ]] || fail "local package not found: ${LOCAL_PKG}" 3

probe() {
  ${SSH} "curl -fsS -o /dev/null -w '%{http_code}' '$1' 2>/dev/null || echo 000" 2>/dev/null || echo 000
}

cmd_verify_only() {
  local h
  h="$(probe "${HEALTH}")"
  log "healthz=${h}"
  [[ "${h}" == 200 ]] || fail "healthz not 200 (${h})" 6
  log "verify-only OK"
}

cmd_rollback() {
  log "rollback: restoring most recent .bak"
  ${SSH} "
    set -e
    LATEST=\$(ls -1dt ${BAK_ROOT}/ichor_brain.* 2>/dev/null | head -1)
    [ -n \"\$LATEST\" ] || { echo 'no .bak found'; exit 4; }
    echo \"restoring \$LATEST -> ${STABLE}\"
    sudo rsync -a --delete \"\$LATEST/\" ${STABLE}/
    sudo chown -R ichor:ichor ${STABLE}
    sudo find ${STABLE} -name '*.pyc' -delete
    sudo systemctl restart ${SVC}
  "
  sleep 4
  cmd_verify_only
  log "rollback complete"
}

cmd_deploy() {
  log "Step 1: hard-check verified .pth + remote path"
  local pth_actual
  pth_actual="$(${SSH} "sudo cat ${PTH_FILE} 2>/dev/null | tr -d '[:space:]'")"
  if [[ "${pth_actual}" != "${EXPECTED_PTH_CONTENT}" ]]; then
    fail ".pth drift detected: expected '${EXPECTED_PTH_CONTENT}', got '${pth_actual}'" 5
  fi
  ${SSH} "test -d ${STABLE}" || fail "remote package path ${STABLE} missing — refusing" 5

  log "Step 2: backup remote package -> ${BAK_ROOT}"
  local stamp
  stamp="$(date -u +%Y%m%d-%H%M%S)"
  ${SSH} "
    sudo mkdir -p ${BAK_ROOT}
    sudo rsync -a --delete ${STABLE}/ ${BAK_ROOT}/ichor_brain.${stamp}/
    ls -1dt ${BAK_ROOT}/ichor_brain.* | tail -n +6 | xargs -r sudo rm -rf
  "

  log "Step 3a: local-tar package -> /tmp"
  local local_tarball
  local_tarball="/tmp/ichor_brain_redeploy_$$.tar.gz"
  tar czf "${local_tarball}" -C "${REPO_ROOT}/packages/ichor_brain/src" \
    --exclude='__pycache__' --exclude='*.pyc' --exclude='.pytest_cache' \
    ichor_brain \
    || fail "Step 3a local-tar failed" 8

  log "Step 3b: scp tarball -> remote /tmp"
  local scp_ok=0
  for attempt in 1 2 3; do
    if scp -o ConnectTimeout=15 "${local_tarball}" \
         ichor-hetzner:/tmp/ichor_brain_redeploy.tar.gz; then
      scp_ok=1
      log "Step 3b attempt ${attempt}: scp OK"
      break
    fi
    log "Step 3b attempt ${attempt}/3 failed, sleep 15s + retry"
    sleep 15
  done
  rm -f "${local_tarball}"
  if [[ ${scp_ok} -eq 0 ]]; then
    fail "Step 3b scp failed 3 attempts (lesson #24)" 8
  fi

  log "Step 3c: ssh-extract + rsync + chown + clear *.pyc"
  local extract_ok=0
  for attempt in 1 2 3; do
    if ${SSH} -o ConnectTimeout=15 "
      set -e
      sudo mkdir -p ${STAGING}
      sudo tar xzf /tmp/ichor_brain_redeploy.tar.gz -C ${STAGING}
      sudo rsync -a --delete ${STAGING}/ichor_brain/ ${STABLE}/
      sudo chown -R ichor:ichor ${STABLE}
      sudo find ${STABLE} -name '*.pyc' -delete
      sudo rm -rf ${STAGING}
      sudo rm -f /tmp/ichor_brain_redeploy.tar.gz
    "; then
      extract_ok=1
      log "Step 3c attempt ${attempt}: extract+rsync OK"
      break
    fi
    log "Step 3c attempt ${attempt}/3 failed, sleep 15s + retry"
    sleep 15
  done
  if [[ ${extract_ok} -eq 0 ]]; then
    fail "Step 3c extract+rsync failed 3 attempts (lesson #24)" 8
  fi

  log "Step 4: restart ${SVC}"
  local restart_ok=0
  for attempt in 1 2 3; do
    if ${SSH} -o ConnectTimeout=15 "sudo systemctl restart ${SVC}"; then
      restart_ok=1
      log "Step 4 attempt ${attempt}: SSH restart OK"
      break
    fi
    log "Step 4 attempt ${attempt}/3 failed, sleep 15s + retry"
    sleep 15
  done
  if [[ ${restart_ok} -eq 0 ]]; then
    fail "Step 4 SSH restart failed 3 attempts (lesson #24)" 9
  fi

  log "Step 5: verify /healthz"
  local h="000"
  local ssh_recovery_count=0
  local poll_idx
  for poll_idx in $(seq 1 30); do
    h="$(probe "${HEALTH}")"
    [[ "${h}" == 200 ]] && break
    if [[ "${h}" == 000 && ${ssh_recovery_count} -lt 3 ]]; then
      log "Step 5 healthz probe ${poll_idx}/30 returned 000 — Pattern #14 retry sleep 15s (recovery ${ssh_recovery_count}/3)"
      ssh_recovery_count=$((ssh_recovery_count + 1))
      sleep 15
    else
      sleep 2
    fi
  done

  log "RESULT: healthz=${h}"
  if [[ "${h}" != 200 ]]; then
    log "verify FAILED — auto-rolling back to backup ichor_brain.${stamp}"
    ${SSH} "
      sudo rsync -a --delete ${BAK_ROOT}/ichor_brain.${stamp}/ ${STABLE}/ &&
      sudo chown -R ichor:ichor ${STABLE} &&
      sudo find ${STABLE} -name '*.pyc' -delete &&
      sudo systemctl restart ${SVC}
    "
    sleep 4
    fail "deploy verify failed (healthz=${h}) — ROLLED BACK to ichor_brain.${stamp}" 8
  fi
  log "DEPLOY OK — ichor_brain synced + ${SVC} restarted, /healthz 200. Backup: ichor_brain.${stamp}"
}

case "${1:-deploy}" in
  deploy) cmd_deploy ;;
  rollback) cmd_rollback ;;
  --verify-only) cmd_verify_only ;;
  *) fail "usage: $0 [deploy|rollback|--verify-only]" 2 ;;
esac
