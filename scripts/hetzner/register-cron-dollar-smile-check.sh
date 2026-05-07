#!/usr/bin/env bash
# Register the DOLLAR_SMILE_BREAK cron on Hetzner (Phase E.3).
#
# Wires services/dollar_smile_check.py (4-condition AND gate detecting
# Stephen Jen "broken smile" / US-driven instability regime) →
# DOLLAR_SMILE_BREAK alert (metric dollar_smile_conditions_met,
# fires when all 4 conditions met). Source: FRED:THREEFYTP10+DTWEXBGS+
# VIXCLS+BAMLH0A0HYM2.
#
# Cadence : daily 22:40 Paris.
#   Post NY close + 5 min after MACRO_QUARTET_STRESS (22:35) so they
#   share the same FRED data freshness window. Both depend on the FRED
#   extended collector at 18:30 Paris.
#
# Idempotent.

set -euo pipefail

cat > /etc/systemd/system/ichor-dollar-smile-check.service <<'EOF'
[Unit]
Description=Ichor DOLLAR_SMILE_BREAK US-driven instability detector
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_dollar_smile_check --persist
TimeoutStartSec=300
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-dollar-smile-check.timer <<'EOF'
[Unit]
Description=Ichor DOLLAR_SMILE_BREAK trigger (daily 22:40 Paris)

[Timer]
OnCalendar=*-*-* 22:40:00 Europe/Paris
Unit=ichor-dollar-smile-check.service
RandomizedDelaySec=180
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-dollar-smile-check.timer

echo "=== Installed DOLLAR_SMILE_BREAK check timer ==="
systemctl list-timers --no-pager | grep ichor-dollar-smile || true

echo ""
echo "Next runs:"
systemctl list-timers ichor-dollar-smile-check.timer --no-pager 2>&1 | tail -2 | head -1
