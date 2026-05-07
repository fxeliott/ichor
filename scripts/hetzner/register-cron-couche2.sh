#!/usr/bin/env bash
# Register the 4 Couche-2 agent crons on Hetzner via systemd timers.
#
# Cadence (cf SPEC.md §3.2):
#   CB-NLP       toutes les 4h (00:15, 04:15, 08:15, 12:15, 16:15, 20:15 Paris)
#   News-NLP     toutes les 4h (offset +30min : 00:45, 04:45, ...)
#   Sentiment    toutes les 6h (02:30, 08:30, 14:30, 20:30 Paris)
#   Positioning  toutes les 6h (offset +60min : 03:30, 09:30, ...)
#
# Each timer triggers a oneshot service that runs
# `python -m ichor_api.cli.run_couche2_agent <kind>` and persists
# the structured output (or error row) to couche2_outputs.
#
# Env loads /etc/ichor/api.env — same pattern as every other ichor-*
# service. The earlier draft referenced a tmpfs-encrypted secrets file
# that was never deployed, which silently broke all 5 services and left
# couche2_outputs empty (cf root-cause investigation 2026-05-06).
#
# Cf docs/decisions/ADR-021-couche2-via-claude-not-fallback.md for the
# routing decision (Claude primary, Cerebras/Groq fallback).

set -euo pipefail

# Service template (systemd unit instance — %i = agent kind)
cat > /etc/systemd/system/ichor-couche2@.service <<'EOF'
[Unit]
Description=Ichor Couche-2 agent runner (%i)
After=network-online.target postgresql.service redis.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api/src
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_couche2_agent %i
TimeoutStartSec=600
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Timers — one per agent kind, OnCalendar staggered to avoid CPU bursts.
declare -A SCHEDULES=(
  [cb_nlp]="*-*-* 00/4:15:00 Europe/Paris"
  [news_nlp]="*-*-* 00/4:45:00 Europe/Paris"
  [sentiment]="*-*-* 02/6:30:00 Europe/Paris"
  [positioning]="*-*-* 03/6:30:00 Europe/Paris"
  # Macro — every 4h, offset +75min from cb_nlp so they don't collide.
  # Migration 0021 extends couche2_outputs CHECK to allow this kind.
  [macro]="*-*-* 01/4:30:00 Europe/Paris"
)

for kind in "${!SCHEDULES[@]}"; do
  cat > /etc/systemd/system/ichor-couche2-"${kind}".timer <<EOF
[Unit]
Description=Ichor Couche-2 trigger (${kind})

[Timer]
OnCalendar=${SCHEDULES[$kind]}
Unit=ichor-couche2@${kind}.service
RandomizedDelaySec=180
Persistent=true

[Install]
WantedBy=timers.target
EOF
done

systemctl daemon-reload

# Enable + start
for kind in "${!SCHEDULES[@]}"; do
  systemctl enable --now ichor-couche2-"${kind}".timer
done

echo "=== Installed timers ==="
systemctl list-timers --no-pager | grep ichor-couche2

echo ""
echo "Next runs:"
for kind in "${!SCHEDULES[@]}"; do
  systemctl list-timers ichor-couche2-"${kind}".timer --no-pager 2>&1 | tail -2 | head -1
done
