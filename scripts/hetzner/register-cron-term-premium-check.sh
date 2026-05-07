#!/usr/bin/env bash
# Register the TERM_PREMIUM_REPRICING cron on Hetzner (Phase E.2).
#
# Wires services/term_premium_check.py (z-score of FRED THREEFYTP10
# Kim-Wright 10y term premium vs trailing 90d distribution) →
# TERM_PREMIUM_REPRICING alert (metric term_premium_z, |z| >= 2.0).
# Source: FRED:THREEFYTP10 (Kim-Wright model).
#
# Cadence : daily 22:30 Paris.
#   FRED extended collector polls THREEFYTP10 daily at 18:30 Paris (cf
#   register-cron-collectors-extended.sh [fred_extended] schedule). +4h
#   buffer accounts for FRED publication latency (KW model is updated
#   weekly but the FRED feed reflects the latest release within hours).
#
# Idempotent.

set -euo pipefail

cat > /etc/systemd/system/ichor-term-premium-check.service <<'EOF'
[Unit]
Description=Ichor TERM_PREMIUM_REPRICING 10y term premium z-score alert
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_term_premium_check --persist
TimeoutStartSec=300
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-term-premium-check.timer <<'EOF'
[Unit]
Description=Ichor TERM_PREMIUM_REPRICING trigger (daily 22:30 Paris)

[Timer]
OnCalendar=*-*-* 22:30:00 Europe/Paris
Unit=ichor-term-premium-check.service
RandomizedDelaySec=180
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-term-premium-check.timer

echo "=== Installed TERM_PREMIUM_REPRICING check timer ==="
systemctl list-timers --no-pager | grep ichor-term-premium || true

echo ""
echo "Next runs:"
systemctl list-timers ichor-term-premium-check.timer --no-pager 2>&1 | tail -2 | head -1
