#!/usr/bin/env bash
# Register the weekly Pass 5 counterfactual batch cron on Hetzner.
#
# Wires the existing POST /v1/sessions/{id}/counterfactual endpoint
# into a weekly batch run that probes one card per Phase 1 asset
# (8 calls/week max, Claude Haiku effort=low so each ~$0.005).
#
# Schedule : Sun 20:00 Europe/Paris — 1h after post-mortem at 19:00.
# The post-mortem reports robustness deltas from the previous week's
# batch ; this cron seeds the next week's robustness signal.

set -euo pipefail

cat > /etc/systemd/system/ichor-counterfactual-batch.service <<'EOF'
[Unit]
Description=Ichor weekly Pass 5 counterfactual batch (8 cards/week)
After=network-online.target postgresql.service ichor-api.service ichor-post-mortem.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_counterfactual_batch --persist
TimeoutStartSec=900
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-counterfactual-batch.timer <<'EOF'
[Unit]
Description=Ichor counterfactual batch trigger (Sun 20:00 Paris)

[Timer]
OnCalendar=Sun *-*-* 20:00:00 Europe/Paris
Unit=ichor-counterfactual-batch.service
RandomizedDelaySec=300
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-counterfactual-batch.timer

echo "=== Installed counterfactual-batch timer ==="
systemctl list-timers ichor-counterfactual-batch.timer --no-pager
