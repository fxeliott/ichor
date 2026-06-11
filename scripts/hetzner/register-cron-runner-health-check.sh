#!/usr/bin/env bash
# Register the Ichor runner-health proactive monitor on Hetzner (ADR-110,
# Chantier D gate: "a deliberately-killed runner fires an alert < 15 min").
#
# Why this exists (2026-06-10 P0, third firing of the class):
#   The Win11 claude-runner died at 03:46 and stayed dead ALL DAY with
#   zero alert — session-cards rc=1 was masked by `SuccessExitStatus=0 1`
#   and the API /healthz never probed the runner. This timer closes the
#   detection half: every 5 min it reads the API /healthz (which now
#   carries a cached `claude_runner_reachable` probe, ADR-110) and fires
#   ichor-notify@ on the up→down TRANSITION (re-notify hourly while the
#   outage lasts — transition-based to avoid 12 notifications/hour spam).
#
# Detection latency: ≤ 5 min timer cadence + ≤ 60 s probe cache = ≤ 6 min,
# well under the 15-min Chantier D gate.

set -euo pipefail

install -d -m 0755 /var/lib/ichor

# ── Check script ──────────────────────────────────────────────────────
cat > /usr/local/bin/ichor-runner-health-check.sh <<'EOF'
#!/usr/bin/env bash
# Probe the API /healthz for claude_runner_reachable. Exit 1 (→ systemd
# Result=failed → OnFailure=ichor-notify@) ONLY on the up→down transition
# or hourly re-notify while down. Steady states exit 0.
set -u

HEALTH_URL="http://127.0.0.1:8000/healthz"
STATE_FILE="/var/lib/ichor/runner-health.state"
RENOTIFY_SEC=3600

body="$(curl -fsS --max-time 10 "${HEALTH_URL}" 2>/dev/null || true)"
now="$(date +%s)"
prev="$(cat "${STATE_FILE}" 2>/dev/null || echo "up")"

if printf '%s' "${body}" | grep -q '"claude_runner_reachable":true'; then
  if [[ "${prev}" != "up" ]]; then
    echo "runner-health: RECOVERED (was: ${prev})"
  fi
  echo "up" > "${STATE_FILE}"
  exit 0
fi

# Runner not reachable (false / null / API itself down — all alert-worthy:
# null here means the prod API lost its runner config, which is its own bug).
if [[ "${prev}" == "up" ]]; then
  echo "down:${now}" > "${STATE_FILE}"
  echo "runner-health: TRANSITION up→down — claude-runner unreachable (body: ${body:0:200})" >&2
  exit 1
fi

last_notify="${prev#down:}"
if [[ "${last_notify}" =~ ^[0-9]+$ ]] && (( now - last_notify >= RENOTIFY_SEC )); then
  echo "down:${now}" > "${STATE_FILE}"
  echo "runner-health: STILL DOWN since $(date -d "@${last_notify}" 2>/dev/null || echo "${last_notify}") — hourly re-notify" >&2
  exit 1
fi

echo "runner-health: still down, already notified (next re-notify in $(( RENOTIFY_SEC - (now - last_notify) ))s)"
exit 0
EOF
chmod 0755 /usr/local/bin/ichor-runner-health-check.sh

# ── Service + timer ───────────────────────────────────────────────────
cat > /etc/systemd/system/ichor-runner-health-check.service <<'EOF'
[Unit]
Description=Ichor runner-health proactive monitor (ADR-110 Chantier D)
After=network-online.target
Wants=network-online.target
OnFailure=ichor-notify@%n.service

[Service]
Type=oneshot
User=ichor
Group=ichor
ExecStart=/usr/local/bin/ichor-runner-health-check.sh
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/ichor-runner-health-check.timer <<'EOF'
[Unit]
Description=Ichor runner-health monitor every 5 min (ADR-110)

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
Unit=ichor-runner-health-check.service

[Install]
WantedBy=timers.target
EOF

chown ichor:ichor /var/lib/ichor 2>/dev/null || true

systemctl daemon-reload
systemctl enable --now ichor-runner-health-check.timer

echo "=== Installed runner-health-check timer ==="
systemctl list-timers --no-pager | grep ichor-runner-health-check || true
echo ""
echo "First manual run (should print state + exit 0/1):"
sudo -u ichor /usr/local/bin/ichor-runner-health-check.sh || echo "(exit $? — notify path will fire when armed)"
