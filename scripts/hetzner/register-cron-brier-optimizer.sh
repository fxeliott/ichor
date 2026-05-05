#!/usr/bin/env bash
# Register the nightly Brier→weights optimizer on Hetzner.
#
# Closes the Living Entity loop step 3 :
#  1. reconciler (02:00 Paris) computes brier_contribution per session card
#  2. **optimizer (03:30 Paris)** reads those Brier scores, seeds baseline
#     weights into confluence_weights_history when missing, persists a
#     diagnostic row to brier_optimizer_runs
#  3. confluence_engine.assess_confluence reads latest_active_weights at
#     runtime
#
# Runs after the reconciler so it sees fresh brier_contribution values.

set -euo pipefail

cat > /etc/systemd/system/ichor-brier-optimizer.service <<'EOF'
[Unit]
Description=Ichor Brier→weights optimizer (nightly)
After=network-online.target postgresql.service ichor-reconciler.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_brier_optimizer --persist
TimeoutStartSec=600
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-brier-optimizer.timer <<'EOF'
[Unit]
Description=Ichor Brier optimizer trigger (nightly 03:30 Paris)

[Timer]
OnCalendar=*-*-* 03:30:00 Europe/Paris
Unit=ichor-brier-optimizer.service
RandomizedDelaySec=300
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-brier-optimizer.timer

echo "=== Installed Brier optimizer timer ==="
systemctl list-timers ichor-brier-optimizer.timer --no-pager
