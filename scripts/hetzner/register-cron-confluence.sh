#!/usr/bin/env bash
# Register the Ichor confluence-snapshot cron on Hetzner via systemd timer.
#
# `snapshot_confluence` recomputes the per-asset confluence score
# (regime × bias × positioning × calendar) every 6h and persists to
# the `confluence_history` hypertable. Powers the dashboard "score
# heatmap" + the auto-tuning Brier feedback (Wave P3).
#
# Cf apps/api/src/ichor_api/cli/snapshot_confluence.py for the
# entrypoint; apps/api/src/ichor_api/services/confluence_engine.py
# for the scoring logic.
#
# This script is idempotent — re-running re-applies the unit files and
# bumps the timer to the latest schedule.

set -euo pipefail

cat > /etc/systemd/system/ichor-snapshot-confluence.service <<'EOF'
[Unit]
Description=Ichor confluence snapshot (8 assets)
After=network-online.target postgresql.service redis.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.snapshot_confluence
TimeoutStartSec=300
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-snapshot-confluence.timer <<'EOF'
[Unit]
Description=Ichor confluence snapshot — every 6h

[Timer]
OnCalendar=*-*-* 00,06,12,18:05:00 Europe/Paris
Unit=ichor-snapshot-confluence.service
RandomizedDelaySec=120
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-snapshot-confluence.timer

echo "=== Installed confluence timer ==="
systemctl list-timers ichor-snapshot-confluence.timer --no-pager
