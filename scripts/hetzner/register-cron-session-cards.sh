#!/usr/bin/env bash
# Register the 4 Ichor session-cards batch crons on Hetzner via systemd timers.
#
# Source-of-truth recovery (r51) :
#   This script was MISSING from the repo despite the units being LIVE on
#   Hetzner since at least r13. Subagent F + M wave 2 audit identified
#   this as a drift hazard (`grep -rE register-cron-session-cards`
#   returned ZERO source files but 6+ docs/ADRs reference the units).
#   If Hetzner had been rebuilt from scratch, the session_cards timers
#   would have vanished silently. This commit codifies the actual prod
#   state. Schedules + ExecStart line copied verbatim from
#   `sudo cat /etc/systemd/system/ichor-session-cards-*.timer` and
#   `sudo cat /etc/systemd/system/ichor-session-cards@.service` on
#   ichor-hetzner 2026-05-15 17:35 CEST.
#
# Pipeline relationship :
#   ichor-briefing-${type}.timer fires at HH:00 -> ichor-briefing@${type}
#   .service runs the briefing (single Claude call, ~3 min). Then
#   ichor-session-cards-${type}.timer fires at HH:00 +1min (offset by
#   the briefing wall-time) -> ichor-session-cards@${type}.service runs
#   the 6-asset 4-pass batch (~25 min). Per CLAUDE.md briefings table
#   schema, briefing must complete BEFORE session_cards because the
#   batch reads briefing context from the briefings table.
#
# Schedule (Europe/Paris, +1min vs briefings to allow briefing completion) :
#   06:00  pre_londres   (6 actifs D1)
#   12:00  pre_ny        (6 actifs D1)
#   17:00  ny_mid        (6 actifs D1)
#   22:00  ny_close      (6 actifs D1)
#
# Per-card 4-pass + Pass 5 + Pass 6 + 30s inter-card sleep = ~25 min
# wall-time per batch. TimeoutStartSec=1800 (30min) covers worst-case.
# `SuccessExitStatus=0 1` whitelists rc=1 (run_session_cards_batch
# returns 1 if any per-card failure, treated as warning not systemd
# failure ; per-card failures are surfaced via batch.card_failed
# structlog + the new safety_reject path from r51 commit a0a0324).

set -euo pipefail

# Service template (single binary, session_type passed as arg)
#
# r51 hardening : OnFailure inline at template level. Same root cause
# as briefings + couche2 templates : install-onfailure-dropins.sh
# excludes `@.service` regex match (line 14-15), so concrete instances
# never gained the failure-notify drop-in.
cat > /etc/systemd/system/ichor-session-cards@.service <<'EOF'
[Unit]
Description=Ichor session-cards batch (%i)
After=network-online.target postgresql.service
Wants=network-online.target
OnFailure=ichor-notify@%n.service

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_session_cards_batch %i --live --enable-rag --enable-tools --inter-card-sleep 30
TimeoutStartSec=1800
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1

[Install]
WantedBy=multi-user.target
EOF

# Timers — one per session type. RandomizedDelaySec=120 to spread CPU
# bursts across the cluster (Hetzner shared with other services).
declare -A SCHEDULES=(
  [pre_londres]="*-*-* 06:00:00 Europe/Paris"
  [pre_ny]="*-*-* 12:00:00 Europe/Paris"
  [ny_mid]="*-*-* 17:00:00 Europe/Paris"
  [ny_close]="*-*-* 22:00:00 Europe/Paris"
)

declare -A DESCRIPTIONS=(
  [pre_londres]="Ichor session cards pre-Londres"
  [pre_ny]="Ichor session cards pre-NY"
  [ny_mid]="Ichor session cards NY mid-session"
  [ny_close]="Ichor session cards NY close"
)

for type in "${!SCHEDULES[@]}"; do
  cat > /etc/systemd/system/ichor-session-cards-"${type}".timer <<EOF
[Unit]
Description=${DESCRIPTIONS[$type]}

[Timer]
OnCalendar=${SCHEDULES[$type]}
Unit=ichor-session-cards@${type}.service
RandomizedDelaySec=120
Persistent=true

[Install]
WantedBy=timers.target
EOF
done

systemctl daemon-reload

# Enable + start (timers only — services trigger on schedule)
for type in "${!SCHEDULES[@]}"; do
  systemctl enable --now ichor-session-cards-"${type}".timer
done

echo "=== Installed session-cards timers ==="
systemctl list-timers --no-pager | grep ichor-session-cards

echo ""
echo "Next runs:"
for type in "${!SCHEDULES[@]}"; do
  systemctl list-timers ichor-session-cards-"${type}".timer --no-pager 2>&1 | tail -2 | head -1
done
