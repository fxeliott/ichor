#!/usr/bin/env bash
# Register the LIQUIDITY_TIGHTENING cron on Hetzner.
#
# Reads RRPONTSYD + DTS_TGA_CLOSE → liquidity_proxy 5-day delta in $bn
# → check_metric("liq_proxy_d", ...) → LIQUIDITY_TIGHTENING alert when ≤ -200.
#
# Cadence : daily Mon-Fri at 04:30 Paris — 30 min after the dts_treasury
# collector finishes (it runs at 04:00). This ensures the latest TGA close
# is already persisted before the proxy is computed.

set -euo pipefail

cat > /etc/systemd/system/ichor-liquidity-check.service <<'EOF'
[Unit]
Description=Ichor LIQUIDITY_TIGHTENING proxy delta alert
After=network-online.target postgresql.service ichor-collector-dts_treasury.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_liquidity_check --persist
TimeoutStartSec=180
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-liquidity-check.timer <<'EOF'
[Unit]
Description=Ichor liquidity proxy check trigger (daily Mon-Fri 04:30)

[Timer]
OnCalendar=Mon..Fri *-*-* 04:30:00
Unit=ichor-liquidity-check.service
RandomizedDelaySec=120
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-liquidity-check.timer

echo "=== Installed liquidity check timer ==="
systemctl list-timers ichor-liquidity-check.timer --no-pager
