#!/usr/bin/env bash
# Register the bid-ask spread monitor cron on Hetzner.
#
# Wires fx_ticks (live) → spread compute → BA_SPREAD_{asset}_*
# → LIQUIDITY_BIDASK_WIDEN alert (crisis_mode trigger).
#
# Cadence : every 10 min — bid-ask widening is the most actionable
# real-time liquidity stress signal, faster than VPIN.

set -euo pipefail

cat > /etc/systemd/system/ichor-bidask-spread.service <<'EOF'
[Unit]
Description=Ichor FX bid-ask spread z-score monitor
After=network-online.target postgresql.service ichor-fx-stream.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_bidask_spread_check --persist
TimeoutStartSec=180
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-bidask-spread.timer <<'EOF'
[Unit]
Description=Ichor bid-ask spread monitor (every 10 min)

[Timer]
OnCalendar=*:0/10
Unit=ichor-bidask-spread.service
RandomizedDelaySec=60
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-bidask-spread.timer

echo "=== Installed bid-ask spread timer ==="
systemctl list-timers ichor-bidask-spread.timer --no-pager
