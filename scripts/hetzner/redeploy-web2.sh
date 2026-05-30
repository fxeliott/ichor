#!/usr/bin/env bash
# redeploy-web2.sh — deploy the apps/web2 `/briefing` dashboard on Hetzner
# (ADR-099 Tier 0.1). Mirrors the proven `ichor-web` + `ichor-web-tunnel`
# pattern, additively: a SEPARATE service on a SEPARATE port + its own
# Cloudflare quick tunnel. The legacy `@ichor/web` deploy
# (`/opt/ichor/apps/web-deploy`, port 3030) is NEVER touched.
#
# Why a new script (not deploy-blue-green.sh): that script is for the
# Python ichor-api (nginx blue/green upstreams). There was NO web deploy
# script — the legacy web was deployed by hand on 2026-05-04 and frozen.
# This codifies the recipe in the house redeploy-brain.sh style:
# idempotent, self-verifying, loud-on-failure, pure-bash (Voie D — no
# Python deps, ZERO Anthropic API spend).
#
# Strategy:
#   1. rsync a curated monorepo subset (root manifests + apps/web2 +
#      packages/, excluding node_modules/.next/.git) to a staging dir,
#      then into /opt/ichor/apps/web2-deploy (chown ichor).
#   2. As user ichor: `pnpm install` (focused on @ichor/web2) + build.
#   3. Write systemd units ichor-web2.service (port 3031, ICHOR_API_URL
#      -> 127.0.0.1:8000 per api.ts:9) + ichor-web2-tunnel.service
#      (cloudflared quick tunnel -> :3031). daemon-reload.
#   4. enable --now both; wait; capture the *.trycloudflare.com URL.
#   5. Verify localhost:3031/briefing == 200 AND the public URL == 200.
#
# Usage (from repo root or worktree):
#   ./scripts/hetzner/redeploy-web2.sh              # full deploy + verify
#   ./scripts/hetzner/redeploy-web2.sh --skip-build # re-sync + restart only
#   ./scripts/hetzner/redeploy-web2.sh rollback     # stop+disable+rm units
#                                                   # (web2-deploy dir kept)
#
# Idempotent: safe to re-run. rsync copies only changes; unit writes are
# overwrites; enable/restart are idempotent.
#
# KNOWN CAVEAT (documented, intentional for Tier 0.1): a cloudflared
# *quick* tunnel mints a NEW random *.trycloudflare.com URL on every
# (re)start. This makes /briefing REACHABLE now (the Tier 0.1 goal:
# Eliot can SEE it) but the URL rotates on restart. A stable hostname is
# ADR-099 Tier 0.2 (CF Pages secret OR a named tunnel — Eliot-gated).

set -euo pipefail

SSH="ssh ichor-hetzner"
PORT=3031
DEPLOY_DIR=/opt/ichor/apps/web2-deploy
APP_DIR="${DEPLOY_DIR}/apps/web2"
STAGING=/tmp/ichor_web2_staging
SVC=ichor-web2
TUN=ichor-web2-tunnel

log() { printf '[%s] %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*" >&2; }
fail() { log "FATAL: $1"; exit "${2:-1}"; }

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
[[ -d "${REPO_ROOT}/apps/web2" ]] || fail "apps/web2 not found at ${REPO_ROOT}" 3

cmd_rollback() {
  log "rollback: stopping + disabling ${SVC} and ${TUN} (web2-deploy dir kept)"
  ${SSH} "
    sudo systemctl disable --now ${SVC}.service ${TUN}.service 2>/dev/null || true
    sudo rm -f /etc/systemd/system/${SVC}.service /etc/systemd/system/${TUN}.service
    sudo systemctl daemon-reload
    echo 'rollback done — legacy ichor-web untouched:'
    systemctl is-active ichor-web ichor-web-tunnel 2>/dev/null || true
  "
  log "rollback complete (<30s, additive deploy fully reverted)"
}

cmd_deploy() {
  local skip_build="${1:-false}"

  if [[ "${skip_build}" != "true" ]]; then
    # r153 — Pattern #16 R-DEPLOY-6 Step-3 SSH-pipe decompose rule (codifies
    # the manual r142+r145+r152 workaround into the script itself). Same
    # failure-class as r150 pattern #14 (Step 4 SSH restart) but applied to
    # the long-lived `tar | ssh` pipe. Decompose into 3 short retryable calls.
    log "Step 1a: local-tar monorepo subset -> /tmp"
    local local_tarball
    local_tarball="/tmp/ichor_web2_redeploy_$$.tar.gz"
    tar czf "${local_tarball}" -C "${REPO_ROOT}" \
      --exclude=node_modules --exclude=.next --exclude=.git \
      --exclude=.turbo --exclude=out --exclude=.claude \
      --exclude='*.pyc' --exclude=__pycache__ \
      package.json pnpm-workspace.yaml pnpm-lock.yaml \
      tsconfig.base.json turbo.json apps/web2 packages \
      || fail "Step 1a local-tar failed" 8

    log "Step 1b: scp tarball -> remote /tmp"
    local scp_ok=0
    for attempt in 1 2 3; do
      if scp -o ConnectTimeout=15 "${local_tarball}" \
           ichor-hetzner:/tmp/ichor_web2_redeploy.tar.gz; then
        scp_ok=1
        log "Step 1b attempt ${attempt}: scp OK"
        break
      fi
      log "Step 1b attempt ${attempt}/3 failed, sleep 15s + retry"
      sleep 15
    done
    rm -f "${local_tarball}"
    if [[ ${scp_ok} -eq 0 ]]; then
      fail "Step 1b scp failed 3 attempts (lesson #24 cluster) — manual intervention required" 8
    fi

    log "Step 1c: ssh-extract + rsync + chown (short single call, retried)"
    local extract_ok=0
    for attempt in 1 2 3; do
      if ${SSH} -o ConnectTimeout=15 "
        set -e
        mkdir -p ${STAGING}
        tar xzf /tmp/ichor_web2_redeploy.tar.gz -C ${STAGING}
        sudo mkdir -p ${DEPLOY_DIR}
        sudo rsync -a --delete \
          --exclude node_modules --exclude .next \
          ${STAGING}/ ${DEPLOY_DIR}/
        sudo chown -R ichor:ichor ${DEPLOY_DIR}
        rm -f /tmp/ichor_web2_redeploy.tar.gz
      "; then
        extract_ok=1
        log "Step 1c attempt ${attempt}: extract+rsync OK"
        break
      fi
      log "Step 1c attempt ${attempt}/3 failed, sleep 15s + retry"
      sleep 15
    done
    if [[ ${extract_ok} -eq 0 ]]; then
      fail "Step 1c extract+rsync failed 3 attempts (lesson #24) — manual intervention required" 8
    fi

    log "Step 2: pnpm install (focused @ichor/web2) + build (user ichor)"
    ${SSH} "sudo -u ichor bash -lc '
      set -euo pipefail
      cd ${DEPLOY_DIR}
      pnpm install --filter @ichor/web2... --no-frozen-lockfile 2>&1 | tail -5
      pnpm --filter @ichor/web2 build 2>&1 | tail -15
      test -f ${APP_DIR}/node_modules/next/dist/bin/next \
        || { echo FATAL_NO_NEXT_BIN; exit 9; }
      test -d ${APP_DIR}/.next \
        || { echo FATAL_NO_DOT_NEXT; exit 9; }
    '" || fail "pnpm install/build failed on Hetzner" 4
  else
    log "--skip-build: skipping rsync + install + build"
  fi

  log "Step 3: write systemd units (additive — legacy ichor-web untouched)"
  ${SSH} "sudo tee /etc/systemd/system/${SVC}.service >/dev/null <<'UNIT'
[Unit]
Description=Ichor web2 /briefing dashboard (ADR-099 Tier 0.1)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ichor
Group=ichor
WorkingDirectory=${APP_DIR}
Environment=NODE_ENV=production
Environment=PORT=${PORT}
Environment=HOSTNAME=127.0.0.1
Environment=ICHOR_API_URL=http://127.0.0.1:8000
Environment=ICHOR_API_PROXY_TARGET=http://127.0.0.1:8000
ExecStart=/usr/bin/node ${APP_DIR}/node_modules/next/dist/bin/next start --port ${PORT} --hostname 127.0.0.1
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNIT
sudo tee /etc/systemd/system/${TUN}.service >/dev/null <<'UNIT'
[Unit]
Description=Ichor web2 Cloudflare quick tunnel (free *.trycloudflare.com URL)
After=${SVC}.service network-online.target
Wants=${SVC}.service network-online.target

[Service]
Type=simple
User=ichor
Group=ichor
ExecStart=/usr/local/bin/cloudflared tunnel --no-autoupdate --url http://127.0.0.1:${PORT}
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload"

  log "Step 4: (re)start ${SVC} to load the new build; keep ${TUN} URL stable"
  # ${SVC}: MUST restart, not 'enable --now' — the latter no-ops on an
  # already-active service and would keep serving the OLD .next build
  # (the re-deploy bug caught r75). ${TUN}: start only if inactive — a
  # quick tunnel mints a NEW *.trycloudflare.com URL on every restart,
  # so we never restart it on an app-only redeploy (URL stays stable
  # within the tunnel's lifetime; named tunnel = RUNBOOK-019 Tier 0.2).
  #
  # r151 — R-DEPLOY-6 Step-4 SSH-timeout decompose rule mirrored from
  # redeploy-api.sh (lesson #24 + doctrinal pattern #14, codified r150).
  # The single SSH-systemctl-restart call has been a stable failure
  # point on redeploy-api.sh (r147→r150 4 consecutive rounds) ;
  # redeploy-web2.sh shares the same SSH transport so the same
  # mitigation applies. 3-attempt retry + 15s sleep + ConnectTimeout=15
  # + fail-loud with lesson #24 ref. Stderr NOT swallowed per r150
  # code-reviewer SHOULD-FIX so legitimate non-timeout failures
  # (sudoers, unit-not-found, OOM) are visible to operator.
  local restart_ok=0
  for attempt in 1 2 3; do
    if ${SSH} -o ConnectTimeout=15 "
      sudo systemctl enable ${SVC}.service >/dev/null 2>&1 || true
      sudo systemctl restart ${SVC}.service
      sudo systemctl enable ${TUN}.service >/dev/null 2>&1 || true
      sudo systemctl is-active --quiet ${TUN}.service || sudo systemctl start ${TUN}.service
      for i in \$(seq 1 30); do
        code=\$(curl -fsS -o /dev/null -w '%{http_code}' http://127.0.0.1:${PORT}/briefing 2>/dev/null || echo 000)
        [ \"\$code\" = 200 ] && break
        sleep 2
      done
      echo \"local /briefing http=\$code\"
    "; then
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

  log "Step 5: capture public quick-tunnel URL + verify"
  local url
  url="$(${SSH} "
    for i in \$(seq 1 20); do
      u=\$(journalctl -u ${TUN} --no-pager 2>/dev/null | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1)
      [ -n \"\$u\" ] && { echo \"\$u\"; break; }
      sleep 2
    done
  ")"
  [[ -n "${url}" ]] || fail "could not capture quick-tunnel URL from journal" 5

  log "verifying public ${url}/briefing"
  local pub_local pub_pub
  pub_local="$(${SSH} "curl -fsS -o /dev/null -w '%{http_code}' http://127.0.0.1:${PORT}/briefing 2>/dev/null || echo 000")"
  pub_pub="$(${SSH} "curl -fsS -o /dev/null -w '%{http_code}' ${url}/briefing 2>/dev/null || echo 000")"
  log "RESULT: local=${pub_local} public=${pub_pub}"
  log "RESULT: PUBLIC /briefing URL = ${url}/briefing"
  [[ "${pub_local}" == "200" ]] || fail "local :${PORT}/briefing not 200 (got ${pub_local})" 6
  [[ "${pub_pub}" == "200" ]] || fail "public ${url}/briefing not 200 (got ${pub_pub})" 7
  log "DEPLOY OK — /briefing is reachable. Legacy ichor-web (3030) untouched."
}

case "${1:-deploy}" in
  deploy) cmd_deploy false ;;
  --skip-build) cmd_deploy true ;;
  rollback) cmd_rollback ;;
  *) fail "usage: $0 [deploy|--skip-build|rollback]" 2 ;;
esac
