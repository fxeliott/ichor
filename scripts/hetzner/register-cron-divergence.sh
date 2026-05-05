#!/usr/bin/env bash
# Register the Ichor cross-venue prediction-market divergence scanner.
#
# `run_divergence_scan --persist` matches Polymarket / Kalshi / Manifold
# markets via Jaccard token similarity (threshold 0.55), then alerts
# when yes-price gaps exceed 5% (info / warning / critical based on
# magnitude). Persists divergences as `alerts` rows with code
# PRED_MARKET_DIVERGENCE.
#
# Cadence : every 30 min — divergences are stable on the hours-scale.
# Off-hours it idles (no markets ↔ no work).

set -euo pipefail

cat > /etc/systemd/system/ichor-divergence-scan.service <<'EOF'
[Unit]
Description=Ichor cross-venue prediction-market divergence scan
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_divergence_scan --persist
TimeoutStartSec=300
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-divergence-scan.timer <<'EOF'
[Unit]
Description=Ichor divergence scanner — every 30 min

[Timer]
OnCalendar=*:0/30
Unit=ichor-divergence-scan.service
RandomizedDelaySec=120
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-divergence-scan.timer

echo "=== Installed divergence scan timer ==="
systemctl list-timers ichor-divergence-scan.timer --no-pager
