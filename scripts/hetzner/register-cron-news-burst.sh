#!/usr/bin/env bash
# Register the news-negative-burst scanner cron on Hetzner.
#
# Wires news_items.tone_label/tone_score → NEWS_NEGATIVE_BURST alert.
# Cadence : every 5 min (matches the burst window so the rolling
# detector sees fresh data each tick).

set -euo pipefail

cat > /etc/systemd/system/ichor-news-burst.service <<'EOF'
[Unit]
Description=Ichor news-negative-burst scanner (5-min window)
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_news_burst_scan --persist
TimeoutStartSec=120
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-news-burst.timer <<'EOF'
[Unit]
Description=Ichor news-burst scanner (every 5 min)

[Timer]
OnCalendar=*:0/5
Unit=ichor-news-burst.service
RandomizedDelaySec=30
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-news-burst.timer

echo "=== Installed news-burst timer ==="
systemctl list-timers ichor-news-burst.timer --no-pager
