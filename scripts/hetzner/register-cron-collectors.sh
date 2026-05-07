#!/usr/bin/env bash
# Register the Ichor collector crons on Hetzner via systemd timers.
#
# Three collectors run on independent cadences:
#   - rss          every 15 min                  (news headlines, lightweight)
#   - polymarket   every 5 min                   (prediction-market snapshots)
#   - market_data  daily 23:10 Europe/Paris       (OHLCV bars, after NY close)
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
TimeoutStartSec=300
StandardOutput=journal
StandardError=journal
# Don't break when a transient HTTP error happens on a single feed
SuccessExitStatus=0 1
EOF

declare -A SCHEDULES=(
  [rss]="*:0/15"                                  # every 15 min
  [polymarket]="*:0/5"                            # every 5 min
  [market_data]="*-*-* 23:10:00 Europe/Paris"      # daily after NY close
  # Polygon Starter : 100 calls/min ceiling. 8 assets × 1 call = 8 calls/min,
  # 8% of quota. Each call fetches the day so far; persistence dedupes via
  # uq_polygon_asset_ts so the cost is paid in network bytes only.
  [polygon]="*:*:00"                               # every minute (1-min OHLCV)
)

# market_data fetch can take 1-2 min for 8 assets — give the service a longer
# timeout. Other collectors stay at the default 120 s.

for collector in "${!SCHEDULES[@]}"; do
  cat > /etc/systemd/system/ichor-collector-"${collector}".timer <<EOF
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
  systemctl enable --now ichor-collector-"${collector}".timer
done

echo "=== Installed collector timers ==="
systemctl list-timers --no-pager | grep ichor-collector || true

echo ""
echo "Next runs:"
for collector in "${!SCHEDULES[@]}"; do
  systemctl list-timers ichor-collector-"${collector}".timer --no-pager 2>&1 | tail -2 | head -1
done
