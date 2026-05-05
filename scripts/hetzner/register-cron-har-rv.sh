#!/usr/bin/env bash
# Register the HAR-RV daily forecast cron on Hetzner.
#
# Wires polygon_intraday_bars (1-min OHLCV)
#   → packages/ml/vol/har_rv.HARRVModel
#   → fred_observations.HAR_RV_{asset}_H1
#   → HAR_RV_FORECAST_SPIKE alert when forecast change ≥ 30%
#
# Cadence : daily 23:30 Europe/Paris (after NY close so the day's
# 1-min bars are settled).

set -euo pipefail

cat > /etc/systemd/system/ichor-har-rv.service <<'EOF'
[Unit]
Description=Ichor HAR-RV daily forecast (Corsi 2009)
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_har_rv --persist
TimeoutStartSec=600
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-har-rv.timer <<'EOF'
[Unit]
Description=Ichor HAR-RV daily forecast trigger (23:30 Paris)

[Timer]
OnCalendar=*-*-* 23:30:00 Europe/Paris
Unit=ichor-har-rv.service
RandomizedDelaySec=300
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-har-rv.timer

echo "=== Installed HAR-RV timer ==="
systemctl list-timers ichor-har-rv.timer --no-pager
