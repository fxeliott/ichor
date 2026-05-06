#!/usr/bin/env bash
# Blue-green deploy script for ichor-api on Hetzner.
#
# Cf docs/SPEC_V2_HARDENING.md §3 + research notes 2026-05-04.
#
# Strategy:
#   1. Identify the currently-active slot from `/etc/nginx/conf.d/ichor-upstream.conf`
#      (symlink → upstream-blue.conf | upstream-green.conf).
#   2. The "other" slot is the target. Start the target slot's systemd
#      instance (e.g. `ichor-api@green.service`).
#   3. Wait for /readyz on the target's port (60s timeout).
#   4. Flip the symlink to point at the target's upstream config and
#      `nginx -s reload`.
#   5. Sleep 30s to let in-flight requests drain on the old slot.
#   6. Stop the old slot's systemd instance.
#
# Rollback: `deploy-blue-green.sh rollback` flips the symlink back without
# touching either systemd instance.

set -euo pipefail

NGINX_UPSTREAM_LINK="/etc/nginx/conf.d/ichor-upstream.conf"
UPSTREAM_BLUE="/etc/nginx/conf.d/upstream-blue.conf"
UPSTREAM_GREEN="/etc/nginx/conf.d/upstream-green.conf"
PORT_BLUE=8001
PORT_GREEN=8002
DRAIN_SECONDS="${DRAIN_SECONDS:-30}"
READYZ_TIMEOUT_SECONDS="${READYZ_TIMEOUT_SECONDS:-60}"

log() { printf '[%s] %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*" >&2; }
fail() { log "FATAL: $1"; exit "${2:-1}"; }

current_slot() {
  # Resolve the symlink to determine the active slot.
  local target
  target="$(readlink -f "${NGINX_UPSTREAM_LINK}" 2>/dev/null || echo "")"
  case "${target}" in
    *upstream-blue.conf) echo "blue" ;;
    *upstream-green.conf) echo "green" ;;
    *) echo "" ;;
  esac
}

other_slot() {
  case "$1" in
    blue) echo "green" ;;
    green) echo "blue" ;;
    *) echo "blue" ;;  # default if no current
  esac
}

slot_port() {
  case "$1" in
    blue) echo "${PORT_BLUE}" ;;
    green) echo "${PORT_GREEN}" ;;
    *) fail "unknown slot: $1" 2 ;;
  esac
}

slot_upstream() {
  case "$1" in
    blue) echo "${UPSTREAM_BLUE}" ;;
    green) echo "${UPSTREAM_GREEN}" ;;
    *) fail "unknown slot: $1" 2 ;;
  esac
}

wait_for_readyz() {
  local port="$1"
  local end=$(( $(date +%s) + READYZ_TIMEOUT_SECONDS ))
  while [ "$(date +%s)" -lt "${end}" ]; do
    if curl -fsS "http://127.0.0.1:${port}/readyz" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}

cmd_deploy() {
  local cur tgt tgt_port tgt_upstream
  cur="$(current_slot)"
  tgt="$(other_slot "${cur:-green}")"
  tgt_port="$(slot_port "${tgt}")"
  tgt_upstream="$(slot_upstream "${tgt}")"

  log "current=${cur:-none} target=${tgt} (port=${tgt_port})"

  log "starting ichor-api@${tgt}.service"
  systemctl start "ichor-api@${tgt}.service"

  log "waiting for /readyz on :${tgt_port}"
  if ! wait_for_readyz "${tgt_port}"; then
    fail "target slot ${tgt} did not become ready in ${READYZ_TIMEOUT_SECONDS}s"
  fi
  log "target ready"

  log "flipping nginx upstream symlink to ${tgt_upstream}"
  ln -sfn "${tgt_upstream}" "${NGINX_UPSTREAM_LINK}"
  nginx -t || fail "nginx config invalid after symlink flip" 3
  nginx -s reload
  log "nginx reloaded"

  log "draining old slot ${cur:-none} for ${DRAIN_SECONDS}s"
  sleep "${DRAIN_SECONDS}"

  if [ -n "${cur}" ]; then
    log "stopping ichor-api@${cur}.service"
    systemctl stop "ichor-api@${cur}.service" || log "warning: stop failed (non-fatal)"
  fi

  log "deploy complete: active=${tgt}"
}

cmd_rollback() {
  local cur tgt tgt_upstream
  cur="$(current_slot)"
  if [ -z "${cur}" ]; then
    fail "no current slot — nothing to rollback" 4
  fi
  tgt="$(other_slot "${cur}")"
  tgt_upstream="$(slot_upstream "${tgt}")"
  log "rolling back from ${cur} → ${tgt}"

  # Ensure target service is up before flipping.
  if ! systemctl is-active --quiet "ichor-api@${tgt}.service"; then
    log "starting ichor-api@${tgt}.service"
    systemctl start "ichor-api@${tgt}.service"
    if ! wait_for_readyz "$(slot_port "${tgt}")"; then
      fail "rollback target ${tgt} not ready" 5
    fi
  fi

  ln -sfn "${tgt_upstream}" "${NGINX_UPSTREAM_LINK}"
  nginx -t || fail "nginx config invalid after rollback" 6
  nginx -s reload
  log "rollback complete: active=${tgt}"
}

cmd_status() {
  echo "active_slot=$(current_slot)"
  systemctl is-active "ichor-api@blue.service" >/dev/null 2>&1 && echo "blue=active" || echo "blue=inactive"
  systemctl is-active "ichor-api@green.service" >/dev/null 2>&1 && echo "green=active" || echo "green=inactive"
}

case "${1:-deploy}" in
  deploy) cmd_deploy ;;
  rollback) cmd_rollback ;;
  status) cmd_status ;;
  *) fail "usage: $0 [deploy|rollback|status]" 2 ;;
esac
