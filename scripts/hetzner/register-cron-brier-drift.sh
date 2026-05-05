#!/usr/bin/env bash
# Register the Brier-degradation monitor cron on Hetzner.
#
# Wires session_card_audit.brier_contribution → 7d-vs-prior-7d delta
# → BIAS_BRIER_DEGRADATION alert. Sister job to brier_optimizer ;
# both consume the same column.
#
# Cadence : daily 04:00 Europe/Paris (after brier_optimizer at 03:30
# so the latest weights have been committed).

set -euo pipefail

cat > /etc/systemd/system/ichor-brier-drift.service <<'EOF'
[Unit]
Description=Ichor Brier-degradation monitor (per asset×model, weekly delta)
After=network-online.target postgresql.service ichor-brier-optimizer.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_brier_drift_check --persist
TimeoutStartSec=300
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-brier-drift.timer <<'EOF'
[Unit]
Description=Ichor Brier-drift trigger (daily 04:00 Paris)

[Timer]
OnCalendar=*-*-* 04:00:00 Europe/Paris
Unit=ichor-brier-drift.service
RandomizedDelaySec=300
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-brier-drift.timer

echo "=== Installed Brier-drift timer ==="
systemctl list-timers ichor-brier-drift.timer --no-pager
