#!/usr/bin/env bash
# Register the VIX_TERM_INVERSION cron on Hetzner (Phase E innovation).
#
# Wires services/vix_term_check.py (VIXCLS / VXVCLS ratio detector) →
# VIX_TERM_INVERSION alert (metric vix_term_ratio, fires when ratio > 1.0
# = backwardation = near-term stress). Source: FRED:VIXCLS+VXVCLS.
#
# Cadence : daily 22:45 Paris.
#   Post NY close + 5 min after DOLLAR_SMILE_BREAK (22:40), part of the
#   nightly macro alert chain (TERM_PREMIUM 22:30 + MACRO_QUARTET 22:35
#   + DOLLAR_SMILE 22:40 + VIX_TERM 22:45).
#
# Idempotent.

set -euo pipefail

cat > /etc/systemd/system/ichor-vix-term-check.service <<'EOF'
[Unit]
Description=Ichor VIX_TERM_INVERSION term-structure backwardation detector
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_vix_term_check --persist
TimeoutStartSec=300
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-vix-term-check.timer <<'EOF'
[Unit]
Description=Ichor VIX_TERM_INVERSION trigger (daily 22:45 Paris)

[Timer]
OnCalendar=*-*-* 22:45:00 Europe/Paris
Unit=ichor-vix-term-check.service
RandomizedDelaySec=180
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-vix-term-check.timer

echo "=== Installed VIX_TERM_INVERSION check timer ==="
systemctl list-timers --no-pager | grep ichor-vix-term || true

echo ""
echo "Next runs:"
systemctl list-timers ichor-vix-term-check.timer --no-pager 2>&1 | tail -2 | head -1
