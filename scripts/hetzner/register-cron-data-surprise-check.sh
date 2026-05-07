#!/usr/bin/env bash
# Register the DATA_SURPRISE_Z cron on Hetzner (Phase D.5.a).
#
# Wires services/surprise_index.py (US Eco Surprise proxy on
# PAYEMS/UNRATE/CPIAUCSL/PCEPI/INDPRO/GDPC1) →
# services/data_surprise_check.py → DATA_SURPRISE_Z alert
# (metric data_surprise_z, |z| >= 2 per series).
#
# Cadence : daily Mon-Fri 14:35 Paris.
#   14:30 Paris = 08:30 ET — most US headline data releases (NFP, CPI,
#   Core PCE, Retail Sales, ISM Mfg/Services, GDP advance). +5 min
#   buffer for the FRED collector to pick up the new vintage.
#
# Idempotent — re-running the script overwrites the unit files but
# keeps the timer's existing schedule (systemd merges).

set -euo pipefail

cat > /etc/systemd/system/ichor-data-surprise-check.service <<'EOF'
[Unit]
Description=Ichor DATA_SURPRISE_Z macro-release surprise alert
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_data_surprise_check --persist
TimeoutStartSec=300
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-data-surprise-check.timer <<'EOF'
[Unit]
Description=Ichor DATA_SURPRISE_Z trigger (daily Mon-Fri after 14h30 US release window)

[Timer]
OnCalendar=Mon..Fri *-*-* 14:35:00 Europe/Paris
Unit=ichor-data-surprise-check.service
RandomizedDelaySec=180
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-data-surprise-check.timer

echo "=== Installed DATA_SURPRISE_Z check timer ==="
systemctl list-timers --no-pager | grep ichor-data-surprise || true

echo ""
echo "Next runs:"
systemctl list-timers ichor-data-surprise-check.timer --no-pager 2>&1 | tail -2 | head -1
