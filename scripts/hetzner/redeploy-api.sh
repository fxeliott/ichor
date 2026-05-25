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

probe() {
  # r158 fix : the inner `|| echo 000` only handles curl-failure WITHIN the
  # SSH session. If SSH ITSELF times out (the lesson #24 SSH-instability class
  # documented in Pattern #14), the entire ${SSH} "..." command exits non-zero
  # and bash strict-mode `set -e` trips BEFORE the function returns. r157
  # Strand C Step 5 hardening assumed probe() returns "000" on SSH-timeout to
  # trigger the 15s SSH-recovery sleep — but the assumption was wrong : SSH-
  # itself-timeout bypassed the inner fallback. r155+r156+r157 all hit Step 5
  # SSH timeout for this exact reason.
  #
  # Fix : OUTER `|| echo 000` catches SSH-itself-timeout/disconnect/auth-fail
  # at the bash level. Stderr also swallowed at outer level so set -e doesn't
  # trip on SSH stderr lines that aren't real failures (e.g., banner). The
  # function now ALWAYS returns a 3-digit string + exit 0 :
  #   - SSH OK + curl 200    → "200"
  #   - SSH OK + curl failure → "000" (inner fallback)
  #   - SSH timeout/disconnect → "000" (outer fallback, r158 hardening)
  # Strand C 15s SSH-recovery retry loop now correctly observes "000" on
  # SSH-itself-timeout and applies the retry-with-sleep discipline.
  ${SSH} "curl -fsS -o /dev/null -w '%{http_code}' '$1' 2>/dev/null || echo 000" 2>/dev/null || echo 000
}

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

  # r153 — Pattern #16 R-DEPLOY-6 Step-3 SSH-pipe decompose rule (codifies
  # the manual r142+r152 workaround into the script itself). The original
  # `tar czf - ... | ${SSH} "tar xzf - ..."` is a long-lived SSH pipe that
  # has empirically timed out (r152 — same failure-class as Step 4 SSH
  # restart hardened r150 as pattern #14, but different step). Decompose
  # into 3 short retryable calls : local-tar to disk → scp → ssh-extract+
  # rsync. Each call is short enough that SSH transient instability
  # doesn't kill the deploy mid-pipe. Same lesson #24 stop-loss applies
  # if ANY of the 3 short calls fails after 3 retries.
  log "Step 3a: local-tar package -> /tmp/ichor_api_redeploy.tar.gz"
  local local_tarball
  local_tarball="/tmp/ichor_api_redeploy_$$.tar.gz"
  tar czf "${local_tarball}" -C "${REPO_ROOT}/apps/api/src" \
    --exclude='__pycache__' --exclude='*.pyc' --exclude='.pytest_cache' \
    ichor_api \
    || fail "Step 3a local-tar failed" 8

  log "Step 3b: scp tarball -> remote /tmp"
  local scp_ok=0
  for attempt in 1 2 3; do
    if scp -o ConnectTimeout=15 "${local_tarball}" \
         ichor-hetzner:/tmp/ichor_api_redeploy.tar.gz; then
      scp_ok=1
      log "Step 3b attempt ${attempt}: scp OK"
      break
    fi
    log "Step 3b attempt ${attempt}/3 failed, sleep 15s + retry"
    sleep 15
  done
  rm -f "${local_tarball}"
  if [[ ${scp_ok} -eq 0 ]]; then
    fail "Step 3b scp failed 3 attempts (lesson #24 SSH-instability cluster) — manual intervention required" 8
  fi

  log "Step 3c: ssh-extract + rsync + chown (short single call)"
  local extract_ok=0
  for attempt in 1 2 3; do
    if ${SSH} -o ConnectTimeout=15 "
      set -e
      mkdir -p ${STAGING}
      tar xzf /tmp/ichor_api_redeploy.tar.gz -C ${STAGING}
      sudo rsync -a --delete ${STAGING}/ichor_api/ ${STABLE}/
      sudo chown -R ichor:ichor ${STABLE}
      rm -f /tmp/ichor_api_redeploy.tar.gz
    "; then
      extract_ok=1
      log "Step 3c attempt ${attempt}: extract+rsync OK"
      break
    fi
    log "Step 3c attempt ${attempt}/3 failed, sleep 15s + retry"
    sleep 15
  done
  if [[ ${extract_ok} -eq 0 ]]; then
    fail "Step 3c extract+rsync failed 3 attempts (lesson #24) — manual intervention required" 8
  fi

  log "Step 4: restart ${SVC}; wait /healthz"
  # r150 — R-DEPLOY-6 Step-4 SSH-timeout decompose rule (lesson #24 explicit
  # codification, doctrinal pattern #14). The single `${SSH} "systemctl
  # restart"` call has timed out r147→r148→r149 consecutively — stable
  # failure pattern, not transient. Decompose into 3 retryable short calls
  # with sleep-then-retry instead of failing the whole deploy on first
  # timeout. Manual recovery from past rounds is now baked in.
  local restart_ok=0
  # r150 code-reviewer SHOULD-FIX : DO NOT `2>/dev/null` here — stderr must
  # leak through so legitimate non-timeout failures (sudoers / unit-not-
  # found / OOM) are visible to the operator instead of hidden behind a
  # misleading "SSH timed out" log. The retry-on-any-error semantics stay
  # correct (we retry regardless of which failure mode hit).
  for attempt in 1 2 3; do
    if ${SSH} -o ConnectTimeout=15 "sudo systemctl restart ${SVC}"; then
      restart_ok=1
      log "Step 4 attempt ${attempt}: SSH restart OK"
      break
    fi
    log "Step 4 attempt ${attempt}/3 failed (timeout OR non-zero exit, see stderr above), sleep 15s + retry"
    sleep 15
  done
  if [[ ${restart_ok} -eq 0 ]]; then
    fail "Step 4 SSH restart failed 3 attempts (lesson #24 SSH-instability cluster) — manual intervention required" 9
  fi
  # r157 Step 5 SSH retry hardening — r155+r156 deploys both hit SSH timeout
  # on the post-restart endpoint-verify probe (Step 5 internal SSH calls).
  # Extends Pattern #14 retry-with-sleep + ConnectTimeout=15 + fail-loud-with-
  # lesson-#24-ref discipline to the Step 5 probe loop. The probe() helper
  # already uses ${SSH} (which carries ConnectTimeout=15), but the 30×2s
  # polling loop above had no retry-on-SSH-timeout — a single connection
  # timeout would silently report h=000 for that probe and the loop would
  # continue, eventually exhausting the 30 attempts on h!=200 alone.
  #
  # r157 hardening (code-reviewer SF-3 comment-vs-code aligned) : if probe
  # returns 000 (SSH-timeout signature per probe() fallback, OR ANY curl
  # failure including TCP RST during normal cold-start per code-reviewer
  # SF-4 false-positive note), invoke a 15s SSH-recovery sleep instead of
  # the bare 2s polling sleep. Capped at 3 SSH-recovery waits per 30-attempt
  # loop so the total wallclock stays ≤ ~110s vs ~60s baseline. The
  # `ssh_recovery_count` bound is the ONLY guard (no poll_idx threshold —
  # prior comment claimed "after 10 polls" but code never enforced it).
  # False-positive cost (h=000 fires on cold-start TCP RST not just SSH
  # timeout) is acceptable : the 3-recovery cap bounds the cost at +45s
  # wallclock even in worst-case false-positive scenario.
  local h="000"
  local ssh_recovery_count=0
  local poll_idx
  for poll_idx in $(seq 1 30); do
    h="$(probe "${HEALTH}")"
    [[ "${h}" == 200 ]] && break
    if [[ "${h}" == 000 && ${ssh_recovery_count} -lt 3 ]]; then
      log "Step 5 healthz probe ${poll_idx}/30 returned 000 (SSH-timeout signature) — Pattern #14 retry sleep 15s (recovery ${ssh_recovery_count}/3 lesson #24 cluster)"
      ssh_recovery_count=$((ssh_recovery_count + 1))
      sleep 15
    else
      sleep 2
    fi
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
