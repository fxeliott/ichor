#!/usr/bin/env bash
# Register the GEOPOL_FLASH cron on Hetzner (Phase D.5.b.1).
#
# Wires services/geopol_flash_check.py (z-score of AI-GPR daily index
# vs trailing 30d distribution) → GEOPOL_FLASH alert (metric ai_gpr_z,
# |z| >= 2.0). Source: ai_gpr:caldara_iacoviello.
#
# Cadence : daily 23:30 Paris.
#   23:00 Paris = AI-GPR collector run (cf register-cron-collectors-extended.sh
#   bucket [ai_gpr]). +30 min buffer for the parser to land the day's
#   value into gpr_observations.
#
# Idempotent — re-running the script overwrites the unit files but
# keeps the timer's existing schedule (systemd merges).

set -euo pipefail

cat > /etc/systemd/system/ichor-geopol-flash-check.service <<'EOF'
[Unit]
Description=Ichor GEOPOL_FLASH AI-GPR geopolitical risk burst alert
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_geopol_flash_check --persist
TimeoutStartSec=300
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-geopol-flash-check.timer <<'EOF'
[Unit]
Description=Ichor GEOPOL_FLASH trigger (daily 23h30 after AI-GPR collector)

[Timer]
OnCalendar=*-*-* 23:30:00 Europe/Paris
Unit=ichor-geopol-flash-check.service
RandomizedDelaySec=180
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-geopol-flash-check.timer

echo "=== Installed GEOPOL_FLASH check timer ==="
systemctl list-timers --no-pager | grep ichor-geopol-flash || true

echo ""
echo "Next runs:"
systemctl list-timers ichor-geopol-flash-check.timer --no-pager 2>&1 | tail -2 | head -1
