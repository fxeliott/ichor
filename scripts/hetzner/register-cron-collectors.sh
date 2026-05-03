#!/usr/bin/env bash
# Register the Ichor collector crons on Hetzner via systemd timers.
#
# Two collectors run on independent cadences:
#   - rss          every 15 min    (news headlines, lightweight)
#   - polymarket   every 5 min     (prediction-market price snapshots)
#
# Each timer triggers a oneshot service that runs the
# `ichor_api.cli.run_collectors --persist` CLI under the `ichor` user.
# Failures are non-fatal (collectors are best-effort sources of context).

set -euo pipefail

# Service template — collector type passed as systemd specifier %i
cat > /etc/systemd/system/ichor-collector@.service <<'EOF'
[Unit]
Description=Ichor collector runner (%i)
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_collectors %i --persist
TimeoutStartSec=120
StandardOutput=journal
StandardError=journal
# Don't break when a transient HTTP error happens on a single feed
SuccessExitStatus=0 1
EOF

declare -A SCHEDULES=(
  [rss]="*:0/15"          # every 15 min, on 0 / 15 / 30 / 45
  [polymarket]="*:0/5"    # every 5 min
)

for collector in "${!SCHEDULES[@]}"; do
  cat > /etc/systemd/system/ichor-collector-${collector}.timer <<EOF
[Unit]
Description=Ichor collector trigger (${collector})

[Timer]
OnCalendar=${SCHEDULES[$collector]}
Unit=ichor-collector@${collector}.service
RandomizedDelaySec=30
Persistent=true

[Install]
WantedBy=timers.target
EOF
done

systemctl daemon-reload

for collector in "${!SCHEDULES[@]}"; do
  systemctl enable --now ichor-collector-${collector}.timer
done

echo "=== Installed collector timers ==="
systemctl list-timers --no-pager | grep ichor-collector || true

echo ""
echo "Next runs:"
for collector in "${!SCHEDULES[@]}"; do
  systemctl list-timers ichor-collector-${collector}.timer --no-pager 2>&1 | tail -2 | head -1
done
