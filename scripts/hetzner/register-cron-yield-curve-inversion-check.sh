#!/usr/bin/env bash
# Register the YIELD_CURVE_INVERSION_DEEP cron on Hetzner (Phase E innovation).
#
# Wires services/yield_curve_inversion_check.py (T10Y2Y level detector)
# → YIELD_CURVE_INVERSION_DEEP alert (metric t10y2y_spread_pct, fires when
# spread <= -0.50 pp = -50 bps). Source: FRED:T10Y2Y.
#
# Cadence : daily 22:50 Paris.
#   Last in nightly macro alert chain (TERM_PREMIUM 22:30 + MACRO_QUARTET 22:35
#   + DOLLAR_SMILE 22:40 + VIX_TERM 22:45 + YIELD_CURVE 22:50).

set -euo pipefail

cat > /etc/systemd/system/ichor-yield-curve-inversion-check.service <<'EOF'
[Unit]
Description=Ichor YIELD_CURVE_INVERSION_DEEP T10Y2Y recession leading indicator
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_yield_curve_inversion_check --persist
TimeoutStartSec=300
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-yield-curve-inversion-check.timer <<'EOF'
[Unit]
Description=Ichor YIELD_CURVE_INVERSION_DEEP trigger (daily 22:50 Paris)

[Timer]
OnCalendar=*-*-* 22:50:00 Europe/Paris
Unit=ichor-yield-curve-inversion-check.service
RandomizedDelaySec=180
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-yield-curve-inversion-check.timer

echo "=== Installed YIELD_CURVE_INVERSION_DEEP check timer ==="
systemctl list-timers --no-pager | grep ichor-yield-curve || true

echo ""
echo "Next runs:"
systemctl list-timers ichor-yield-curve-inversion-check.timer --no-pager 2>&1 | tail -2 | head -1
