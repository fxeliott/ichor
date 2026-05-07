#!/usr/bin/env bash
# Register the TARIFF_SHOCK cron on Hetzner (Phase D.5.b.2).
#
# Wires services/tariff_shock_check.py (GDELT-filtered tariff narrative
# burst + tone gate) → TARIFF_SHOCK alert (metric tariff_count_z,
# count_z >= 2.0 AND avg_tone <= -1.5). Source: gdelt:tariff_filter.
#
# Cadence : Mon..Fri 11:30 / 15:30 / 18:30 / 22:30 Paris
#   - 11:30 : mid-Londres pre-NY (catches overnight tariff news)
#   - 15:30 : 1h post-NY-open (Trump tweets, USTR press releases)
#   - 18:30 : US PM session (mid-NY, post lunch)
#   - 22:30 : post NY close (consolidation + late news)
#
# GDELT collector itself runs every 30 min — these slots query the
# accumulated 24h flow, not real-time.
#
# Idempotent — re-running the script overwrites the unit files.

set -euo pipefail

cat > /etc/systemd/system/ichor-tariff-shock-check.service <<'EOF'
[Unit]
Description=Ichor TARIFF_SHOCK GDELT tariff narrative burst alert
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_tariff_shock_check --persist
TimeoutStartSec=300
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-tariff-shock-check.timer <<'EOF'
[Unit]
Description=Ichor TARIFF_SHOCK trigger (4x business days, NY/London sessions)

[Timer]
OnCalendar=Mon..Fri *-*-* 11,15,18,22:30:00 Europe/Paris
Unit=ichor-tariff-shock-check.service
RandomizedDelaySec=180
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-tariff-shock-check.timer

echo "=== Installed TARIFF_SHOCK check timer ==="
systemctl list-timers --no-pager | grep ichor-tariff-shock || true

echo ""
echo "Next runs:"
systemctl list-timers ichor-tariff-shock-check.timer --no-pager 2>&1 | tail -5
