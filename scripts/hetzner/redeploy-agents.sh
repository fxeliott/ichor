#!/usr/bin/env bash
# redeploy-agents.sh — safe, idempotent, self-verifying ichor_agents
# package redeploy on Hetzner (mirrors redeploy-api.sh + redeploy-brain.sh
# patterns).
#
# WHY THIS EXISTS : pre-r172b there was NO vetted agents deploy script.
# `redeploy-brain.sh` only covers `ichor_brain` ; `redeploy-api.sh` only
# covers `ichor_api`. The `ichor_agents` package (`packages/agents/src/
# ichor_agents/`) is consumed by `apps/api` AND `cli/run_couche2_agent.py`
# via an editable install pointed at `/opt/ichor/packages-staging/agents/src`
# (verified by `_editable_impl_ichor_agents.pth` content). Until r172b,
# agents changes were deployed by hand (cf. r168 memory : "deploy
# ichor_brain via manual tar+scp+ssh since redeploy-brain.sh broken Win11
# rsync absent" — same pattern needed for ichor_agents).
#
# VERIFIED PATH (R59, do NOT guess) : the ichor_agents editable .pth at
# `/opt/ichor/api/.venv/lib/python3.12/site-packages/_editable_impl_ichor_agents.pth`
# contains exactly `/opt/ichor/packages-staging/agents/src`. Step 1
# HARD-CHECKS this and fails loud on drift.
#
# Strategy mirrors redeploy-api.sh r150 Pattern #14 SSH-retry resilience :
#   1. Hard-check the remote .pth + canonical package path exist.
#   2. Backup the remote package to a timestamped .bak (rollback < 30s).
#   3. tar+scp+ssh extract (decomposed pipe per Pattern #16 R-DEPLOY-6
#      Step-3, 3 short retryable calls).
#   4. Clear __pycache__ on Hetzner side (find -delete, no rm -rf).
#   5. systemctl restart ichor-api (so the api re-imports fresh agents).
#   6. Verify /healthz == 200.
#   7. On ANY verify failure : auto-restore the .bak + restart + abort.
#
# Usage :
#   ./scripts/hetzner/redeploy-agents.sh                 # deploy + verify
#   ./scripts/hetzner/redeploy-agents.sh rollback        # restore latest .bak
#   ./scripts/hetzner/redeploy-agents.sh --verify-only   # health probes only
#
# Idempotent. Pure bash (Voie D — no Python deps, ZERO Anthropic spend).

set -euo pipefail

SSH="ssh ichor-hetzner"
STABLE="/opt/ichor/packages-staging/agents/src/ichor_agents"
STAGING="/tmp/ichor_agents_redeploy_staging"
BAK_ROOT="/opt/ichor/packages-staging/agents/.redeploy-baks"
HEALTH="http://127.0.0.1:8000/healthz"
PTH_FILE="/opt/ichor/api/.venv/lib/python3.12/site-packages/_editable_impl_ichor_agents.pth"
EXPECTED_PTH_CONTENT="/opt/ichor/packages-staging/agents/src"
SVC="ichor-api"

log() { printf '[%s] %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*" >&2; }
fail() { log "FATAL: $1"; exit "${2:-1}"; }

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LOCAL_PKG="${REPO_ROOT}/packages/agents/src/ichor_agents"
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
    LATEST=\$(ls -1dt ${BAK_ROOT}/ichor_agents.* 2>/dev/null | head -1)
    [ -n \"\$LATEST\" ] || { echo 'no .bak found'; exit 4; }
    echo \"restoring \$LATEST -> ${STABLE}\"
    sudo rsync -a --delete \"\$LATEST/\" ${STABLE}/
    sudo chown -R ichor:ichor ${STABLE}
    sudo find ${STABLE} -name __pycache__ -type d -prune -exec find {} -type f -delete +
    sudo systemctl restart ${SVC}
  "
  sleep 4
  cmd_verify_only
  log "rollback complete"
}

cmd_deploy() {
  log "Step 1: hard-check verified .pth + remote path (anti silent-noop)"
  local pth_actual
  pth_actual="$(${SSH} "sudo cat ${PTH_FILE} 2>/dev/null | tr -d '[:space:]'")"
  if [[ "${pth_actual}" != "${EXPECTED_PTH_CONTENT}" ]]; then
    fail ".pth drift detected: expected '${EXPECTED_PTH_CONTENT}', got '${pth_actual}'" 5
  fi
  ${SSH} "test -d ${STABLE} && test -f ${STABLE}/agents/news_nlp.py" \
    || fail "remote package path ${STABLE} missing/!news_nlp.py — refusing" 5

  log "Step 2: backup remote package -> ${BAK_ROOT}"
  local stamp
  stamp="$(date -u +%Y%m%d-%H%M%S)"
  ${SSH} "
    sudo mkdir -p ${BAK_ROOT}
    sudo rsync -a --delete ${STABLE}/ ${BAK_ROOT}/ichor_agents.${stamp}/
    # keep only 5 most recent baks
    ls -1dt ${BAK_ROOT}/ichor_agents.* | tail -n +6 | xargs -r sudo rm -rf
  "

  log "Step 3a: local-tar package -> /tmp/ichor_agents_redeploy.tar.gz"
  local local_tarball
  local_tarball="/tmp/ichor_agents_redeploy_$$.tar.gz"
  tar czf "${local_tarball}" -C "${REPO_ROOT}/packages/agents/src" \
    --exclude='__pycache__' --exclude='*.pyc' --exclude='.pytest_cache' --exclude='.bak-r169' \
    ichor_agents \
    || fail "Step 3a local-tar failed" 8

  log "Step 3b: scp tarball -> remote /tmp"
  local scp_ok=0
  for attempt in 1 2 3; do
    if scp -o ConnectTimeout=15 "${local_tarball}" \
         ichor-hetzner:/tmp/ichor_agents_redeploy.tar.gz; then
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

  log "Step 3c: ssh-extract + rsync + chown + clear __pycache__"
  local extract_ok=0
  for attempt in 1 2 3; do
    if ${SSH} -o ConnectTimeout=15 "
      set -e
      sudo mkdir -p ${STAGING}
      sudo tar xzf /tmp/ichor_agents_redeploy.tar.gz -C ${STAGING}
      sudo rsync -a --delete ${STAGING}/ichor_agents/ ${STABLE}/
      sudo chown -R ichor:ichor ${STABLE}
      sudo find ${STABLE} -name '*.pyc' -delete
      sudo rm -rf ${STAGING}
      sudo rm -f /tmp/ichor_agents_redeploy.tar.gz
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

  log "Step 4: restart ${SVC} (re-import fresh agents)"
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
      log "Step 5 healthz probe ${poll_idx}/30 returned 000 (SSH-timeout) — Pattern #14 retry sleep 15s (recovery ${ssh_recovery_count}/3)"
      ssh_recovery_count=$((ssh_recovery_count + 1))
      sleep 15
    else
      sleep 2
    fi
  done

  log "RESULT: healthz=${h}"
  if [[ "${h}" != 200 ]]; then
    log "verify FAILED — auto-rolling back to backup ichor_agents.${stamp}"
    ${SSH} "
      sudo rsync -a --delete ${BAK_ROOT}/ichor_agents.${stamp}/ ${STABLE}/ &&
      sudo chown -R ichor:ichor ${STABLE} &&
      sudo find ${STABLE} -name __pycache__ -type d -prune -exec find {} -type f -delete + &&
      sudo systemctl restart ${SVC}
    "
    sleep 4
    fail "deploy verify failed (healthz=${h}) — ROLLED BACK to ichor_agents.${stamp}" 8
  fi
  log "DEPLOY OK — ichor_agents synced + ${SVC} restarted, /healthz 200. Backup: ichor_agents.${stamp}"
}

case "${1:-deploy}" in
  deploy) cmd_deploy ;;
  rollback) cmd_rollback ;;
  --verify-only) cmd_verify_only ;;
  *) fail "usage: $0 [deploy|rollback|--verify-only]" 2 ;;
esac
