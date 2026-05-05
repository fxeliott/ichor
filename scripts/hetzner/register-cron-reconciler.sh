#!/usr/bin/env bash
# Register the Ichor session-card outcome reconciler on Hetzner.
#
# `reconcile_outcomes` walks back over yesterday's session cards,
# fetches realized prices, scores each prediction with Brier loss,
# and writes the results to `session_card_audits` so the calibration
# UI + the Brier→weights auto-tuner can consume them.
#
# Runs nightly at 02:00 Europe/Paris (after Asian close), with a
# RandomizedDelaySec=600 to spread load when multiple jobs collide.

set -euo pipefail

cat > /etc/systemd/system/ichor-reconciler.service <<'EOF'
[Unit]
Description=Ichor session-card outcome reconciler (Brier scoring)
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.reconcile_outcomes
TimeoutStartSec=600
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-reconciler.timer <<'EOF'
[Unit]
Description=Ichor reconciler nightly (Brier back-fill)

[Timer]
OnCalendar=*-*-* 02:00:00 Europe/Paris
Unit=ichor-reconciler.service
RandomizedDelaySec=600
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-reconciler.timer

echo "=== Installed reconciler timer ==="
systemctl list-timers ichor-reconciler.timer --no-pager
