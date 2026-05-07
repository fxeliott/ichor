#!/usr/bin/env bash
# Register the TERM_PREMIUM_STRUCTURAL_252D cron on Hetzner (Phase E.2 sister).
#
# Wires services/term_premium_structural_check.py (z-score 252d trailing
# year on FRED:THREEFYTP10) → TERM_PREMIUM_STRUCTURAL_252D alert
# (metric term_premium_z_252d, |z| >= 2.0, severity info).
#
# Cadence : weekly Sunday 22:15 Paris (slow-build, daily overkill on 252d).
# Sister to ichor-geopol-regime-check.timer (also weekly Sun 22:00).
#
# Idempotent.

set -euo pipefail

cat > /etc/systemd/system/ichor-term-premium-structural-check.service <<'EOF'
[Unit]
Description=Ichor TERM_PREMIUM_STRUCTURAL_252D structural fiscal regime alert
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_term_premium_structural_check --persist
TimeoutStartSec=300
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-term-premium-structural-check.timer <<'EOF'
[Unit]
Description=Ichor TERM_PREMIUM_STRUCTURAL_252D trigger (weekly Sun 22:15 Paris)

[Timer]
OnCalendar=Sun *-*-* 22:15:00 Europe/Paris
Unit=ichor-term-premium-structural-check.service
RandomizedDelaySec=300
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-term-premium-structural-check.timer

echo "=== Installed TERM_PREMIUM_STRUCTURAL_252D check timer ==="
systemctl list-timers --no-pager | grep ichor-term-premium-structural || true

echo ""
echo "Next runs:"
systemctl list-timers ichor-term-premium-structural-check.timer --no-pager 2>&1 | tail -2 | head -1
