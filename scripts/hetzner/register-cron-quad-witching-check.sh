#!/usr/bin/env bash
# Register the QUAD_WITCHING + OPEX_GAMMA_PEAK cron on Hetzner (Phase D.5.e).
#
# Wires services/quad_witching_check.py (3rd Friday calendar math) →
# QUAD_WITCHING + OPEX_GAMMA_PEAK alerts.
#
# Cadence : daily 22:00 Paris.
#   Pure date-math check, no API call ; runs in < 1 second. Daily 22h
#   slot keeps the alert fresh as the calendar advances toward each
#   third Friday — fires T-5 through T-0 for QUAD, T-2 through T-0 for
#   monthly OPEX.

set -euo pipefail

cat > /etc/systemd/system/ichor-quad-witching-check.service <<'EOF'
[Unit]
Description=Ichor QUAD_WITCHING + OPEX_GAMMA_PEAK proximity alerts
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_quad_witching_check --persist
TimeoutStartSec=120
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-quad-witching-check.timer <<'EOF'
[Unit]
Description=Ichor QUAD_WITCHING + OPEX_GAMMA_PEAK trigger (daily 22h Paris)

[Timer]
OnCalendar=*-*-* 22:00:00 Europe/Paris
Unit=ichor-quad-witching-check.service
RandomizedDelaySec=120
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-quad-witching-check.timer

echo "=== Installed QUAD_WITCHING + OPEX_GAMMA_PEAK check timer ==="
systemctl list-timers --no-pager | grep ichor-quad-witching || true

echo ""
echo "Next runs:"
systemctl list-timers ichor-quad-witching-check.timer --no-pager 2>&1 | tail -2 | head -1
