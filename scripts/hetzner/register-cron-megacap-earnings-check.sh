#!/usr/bin/env bash
# Register the MEGACAP_EARNINGS_T-1 cron on Hetzner (Phase D.5.f).
#
# Wires services/megacap_earnings_check.py (yfinance Mag-7 next-earnings
# fetch + T-1 proximity check) → MEGACAP_EARNINGS_T-1 alert
# (metric megacap_t_minus_days, days_to_event <= 1 = today or tomorrow).
# Source: yfinance:earnings_calendar.
#
# Cadence : daily 14:00 Paris.
#   14:00 Paris = 08:00 ET — post US pre-market window. Most Mag-7
#   companies announce earnings AFTER market close (16:00 ET / 22:00 Paris)
#   so a 14:00 daily run gives the trader a full session of advance
#   notice before the binary catalyst.
#
# Idempotent — re-running the script overwrites the unit files.

set -euo pipefail

cat > /etc/systemd/system/ichor-megacap-earnings-check.service <<'EOF'
[Unit]
Description=Ichor MEGACAP_EARNINGS_T-1 Mag-7 earnings proximity alert
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_megacap_earnings_check --persist
TimeoutStartSec=300
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-megacap-earnings-check.timer <<'EOF'
[Unit]
Description=Ichor MEGACAP_EARNINGS_T-1 trigger (daily 14:00 Paris, pre-NY-open)

[Timer]
OnCalendar=*-*-* 14:00:00 Europe/Paris
Unit=ichor-megacap-earnings-check.service
RandomizedDelaySec=180
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-megacap-earnings-check.timer

echo "=== Installed MEGACAP_EARNINGS_T-1 check timer ==="
systemctl list-timers --no-pager | grep ichor-megacap-earnings || true

echo ""
echo "Next runs:"
systemctl list-timers ichor-megacap-earnings-check.timer --no-pager 2>&1 | tail -2 | head -1
