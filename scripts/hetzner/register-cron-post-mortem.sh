#!/usr/bin/env bash
# Register the weekly post-mortem cron on Hetzner.
#
# Wires services/post_mortem.py into systemd. Runs Sun 19:00 Paris,
# right after the weekly briefing at 18:00, so the post-mortem
# captures the freshest week's data + narrative.
#
# Output : both a row in `post_mortems` (Postgres) and a markdown
# file at /var/lib/ichor/post-mortems/{iso_year}-W{iso_week}.md.

set -euo pipefail

mkdir -p /var/lib/ichor/post-mortems
chown ichor:ichor /var/lib/ichor /var/lib/ichor/post-mortems
chmod 0755 /var/lib/ichor /var/lib/ichor/post-mortems

cat > /etc/systemd/system/ichor-post-mortem.service <<'EOF'
[Unit]
Description=Ichor weekly post-mortem (8-section AUTOEVO report)
After=network-online.target postgresql.service ichor-briefing@weekly.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_post_mortem --persist
TimeoutStartSec=600
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-post-mortem.timer <<'EOF'
[Unit]
Description=Ichor weekly post-mortem trigger (Sun 19:00 Paris)

[Timer]
OnCalendar=Sun *-*-* 19:00:00 Europe/Paris
Unit=ichor-post-mortem.service
RandomizedDelaySec=300
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-post-mortem.timer

echo "=== Installed post-mortem timer ==="
systemctl list-timers ichor-post-mortem.timer --no-pager
