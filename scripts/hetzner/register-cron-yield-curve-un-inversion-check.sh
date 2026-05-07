#!/usr/bin/env bash
# Register the YIELD_CURVE_UN_INVERSION_EVENT cron on Hetzner (Phase E innov).
#
# Wires services/yield_curve_un_inversion_check.py (cross_up event detection
# + deep inversion confirmation) → YIELD_CURVE_UN_INVERSION_EVENT alert
# (metric yield_curve_un_inversion_conditions, fires when 2/2 conditions met).
# Source: FRED:T10Y2Y. Sister to YIELD_CURVE_INVERSION_DEEP (ADR-046).
#
# Cadence : daily 22:55 Paris (last in nightly chain).

set -euo pipefail

cat > /etc/systemd/system/ichor-yield-curve-un-inversion-check.service <<'EOF'
[Unit]
Description=Ichor YIELD_CURVE_UN_INVERSION_EVENT recession imminent trigger
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_yield_curve_un_inversion_check --persist
TimeoutStartSec=300
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-yield-curve-un-inversion-check.timer <<'EOF'
[Unit]
Description=Ichor YIELD_CURVE_UN_INVERSION_EVENT trigger (daily 22:55 Paris)

[Timer]
OnCalendar=*-*-* 22:55:00 Europe/Paris
Unit=ichor-yield-curve-un-inversion-check.service
RandomizedDelaySec=180
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-yield-curve-un-inversion-check.timer

echo "=== Installed YIELD_CURVE_UN_INVERSION_EVENT timer ==="
systemctl list-timers --no-pager | grep ichor-yield-curve-un-inversion || true
echo ""
echo "Next runs:"
systemctl list-timers ichor-yield-curve-un-inversion-check.timer --no-pager 2>&1 | tail -2 | head -1
