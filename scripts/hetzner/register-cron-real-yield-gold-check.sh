#!/usr/bin/env bash
# Register the REAL_YIELD_GOLD_DIVERGENCE cron on Hetzner (Phase D.5.c).
#
# Wires services/real_yield_gold_check.py (rolling 60d correlation
# between XAU FRED:GOLDAMGBD228NLBM and DFII10 + z-score against
# trailing 250d distribution) → REAL_YIELD_GOLD_DIVERGENCE alert
# (metric real_yield_gold_div_z, |z| >= 2.0).
#
# Cadence : daily Mon-Fri 22:00 Paris (after NY close 22h).
#   FRED daily series settle by 22h Paris — running just after gives
#   the freshest rolling-corr.
#
# Idempotent — re-running overwrites the unit files but preserves
# the timer's existing schedule.

set -euo pipefail

cat > /etc/systemd/system/ichor-real-yield-gold-check.service <<'EOF'
[Unit]
Description=Ichor REAL_YIELD_GOLD_DIVERGENCE alert (XAU/DFII10 corr breakdown)
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_real_yield_gold_check --persist
TimeoutStartSec=300
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-real-yield-gold-check.timer <<'EOF'
[Unit]
Description=Ichor REAL_YIELD_GOLD_DIVERGENCE trigger (daily Mon-Fri after NY close)

[Timer]
OnCalendar=Mon..Fri *-*-* 22:00:00 Europe/Paris
Unit=ichor-real-yield-gold-check.service
RandomizedDelaySec=240
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-real-yield-gold-check.timer

echo "=== Installed REAL_YIELD_GOLD_DIVERGENCE check timer ==="
systemctl list-timers --no-pager | grep ichor-real-yield-gold || true

echo ""
echo "Next runs:"
systemctl list-timers ichor-real-yield-gold-check.timer --no-pager 2>&1 | tail -2 | head -1
