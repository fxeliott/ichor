#!/usr/bin/env bash
# Register the US Treasury Auction cron on Hetzner.
#
# Wires fiscaldata.treasury.gov "Treasury Securities Auctions Data"
#   → fred_observations.TREASURY_AUC_*
#   → TREASURY_AUCTION_TAIL alert when high-vs-median ≥ 2 bps.
#
# Cadence : every 6h (auctions settle on schedule, not continuously ;
# 6h cycle catches the post-auction publication window).

set -euo pipefail

cat > /etc/systemd/system/ichor-treasury-auction.service <<'EOF'
[Unit]
Description=Ichor US Treasury auction results poller
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_collectors treasury_auction --persist
TimeoutStartSec=180
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-treasury-auction.timer <<'EOF'
[Unit]
Description=Ichor Treasury auction trigger (every 6h)

[Timer]
OnCalendar=*-*-* 00,06,12,18:30:00 Europe/Paris
Unit=ichor-treasury-auction.service
RandomizedDelaySec=300
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-treasury-auction.timer

echo "=== Installed Treasury auction timer ==="
systemctl list-timers ichor-treasury-auction.timer --no-pager
