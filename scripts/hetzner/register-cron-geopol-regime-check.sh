#!/usr/bin/env bash
# Register the GEOPOL_REGIME_STRUCTURAL cron on Hetzner (Phase D.5.b
# structural companion).
#
# Wires services/geopol_regime_check.py (z-score AI-GPR vs trailing 252d
# / 1 trading year window) → GEOPOL_REGIME_STRUCTURAL alert
# (metric ai_gpr_z_252d, |z| >= 2.0, severity info).
#
# Cadence : weekly Sunday 22h Paris.
#   Slow-build signal evaluated on a year-trailing window doesn't need
#   daily evaluation. Sunday post-NY-close keeps the alert fresh for
#   Monday pre-Londres briefings.
#
# Idempotent — re-running the script overwrites the unit files.

set -euo pipefail

cat > /etc/systemd/system/ichor-geopol-regime-check.service <<'EOF'
[Unit]
Description=Ichor GEOPOL_REGIME_STRUCTURAL 252d structural geopol regime alert
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_geopol_regime_check --persist
TimeoutStartSec=300
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-geopol-regime-check.timer <<'EOF'
[Unit]
Description=Ichor GEOPOL_REGIME_STRUCTURAL trigger (weekly Sun 22h Paris)

[Timer]
OnCalendar=Sun *-*-* 22:00:00 Europe/Paris
Unit=ichor-geopol-regime-check.service
RandomizedDelaySec=300
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-geopol-regime-check.timer

echo "=== Installed GEOPOL_REGIME_STRUCTURAL check timer ==="
systemctl list-timers --no-pager | grep ichor-geopol-regime || true

echo ""
echo "Next runs:"
systemctl list-timers ichor-geopol-regime-check.timer --no-pager 2>&1 | tail -2 | head -1
