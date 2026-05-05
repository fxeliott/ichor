#!/usr/bin/env bash
# Register the Reddit subreddit poller cron on Hetzner.
#
# Wires reddit.fetch_subreddit (public JSON, no OAuth) on 4 watched
# subreddits (wallstreetbets/forex/stockmarket/Gold) into news_items
# (source_kind=social). Feeds the Couche-2 sentiment agent.
#
# Cadence : every 30 min — Reddit "hot" tab refreshes meaningfully
# on hourly+ scale, polling more often = duplicate posts.

set -euo pipefail

cat > /etc/systemd/system/ichor-reddit.service <<'EOF'
[Unit]
Description=Ichor Reddit watchlist poller (4 subreddits)
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_collectors reddit --persist
TimeoutStartSec=180
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-reddit.timer <<'EOF'
[Unit]
Description=Ichor Reddit watchlist trigger (every 30 min)

[Timer]
OnCalendar=*:0/30
Unit=ichor-reddit.service
RandomizedDelaySec=120
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-reddit.timer

echo "=== Installed Reddit timer ==="
systemctl list-timers ichor-reddit.timer --no-pager
