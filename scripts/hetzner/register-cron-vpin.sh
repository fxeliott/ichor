#!/usr/bin/env bash
# Register the VPIN compute cron on Hetzner.
#
# Wires fx_ticks (live, from ichor-fx-stream) → packages/ml/microstructure/vpin
# → fred_observations.VPIN_FX_{asset} + VPIN_TOXICITY_HIGH alert.
#
# Cadence : every 30 min — VPIN over a 4h trailing window. Faster
# cycles wouldn't add value (one bucket = ~30-60 s of liquidity).

set -euo pipefail

cat > /etc/systemd/system/ichor-vpin-compute.service <<'EOF'
[Unit]
Description=Ichor FX VPIN flow-toxicity compute
After=network-online.target postgresql.service ichor-fx-stream.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_vpin_compute --persist
TimeoutStartSec=300
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-vpin-compute.timer <<'EOF'
[Unit]
Description=Ichor VPIN compute trigger (every 30 min)

[Timer]
OnCalendar=*:0/30
Unit=ichor-vpin-compute.service
RandomizedDelaySec=120
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-vpin-compute.timer

echo "=== Installed VPIN compute timer ==="
systemctl list-timers ichor-vpin-compute.timer --no-pager
