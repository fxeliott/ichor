#!/usr/bin/env bash
# Register the TREASURY_VOL_SPIKE cron on Hetzner (Phase E innovation, MOVE proxy).
#
# Wires services/treasury_vol_check.py (DGS10 30d realized vol z-score)
# → TREASURY_VOL_SPIKE alert. Closes ADR-042 followup.
# Source: FRED:DGS10. Daily 23:00 Paris.

set -euo pipefail

cat > /etc/systemd/system/ichor-treasury-vol-check.service <<'EOF'
[Unit]
Description=Ichor TREASURY_VOL_SPIKE realized vol MOVE proxy alert
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_treasury_vol_check --persist
TimeoutStartSec=300
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-treasury-vol-check.timer <<'EOF'
[Unit]
Description=Ichor TREASURY_VOL_SPIKE trigger (daily 23:00 Paris)

[Timer]
OnCalendar=*-*-* 23:00:00 Europe/Paris
Unit=ichor-treasury-vol-check.service
RandomizedDelaySec=180
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-treasury-vol-check.timer

echo "=== Installed TREASURY_VOL_SPIKE timer ==="
systemctl list-timers --no-pager | grep ichor-treasury-vol || true
