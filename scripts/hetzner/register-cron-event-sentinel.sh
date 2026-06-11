#!/usr/bin/env bash
# S03 Chantier D - Register the pre-announcement event sentinel.
#
# "Etre prevenu de TOUTES les annonces susceptibles d'influencer les
# trades" (spec S03 verbatim) was reactive-only as-built: streaming_refresh
# reacts AFTER a print lands. This timer scans economic_events every
# 10 min for high-impact events in the next 60 min (USD/EUR/GBP/CAD) and
# emits ECO_EVENT_IMMINENT (critical -> web-push) via the canonical
# pipeline. Event-cluster dedup makes re-runs idempotent; a quiet
# calendar emits nothing.
#
# Worst-case warning lead: 50-60 min before the print (10-min cadence on
# a 60-min horizon). ADR-017: descriptive calendar copy, never direction.
#
# Voie D : zero LLM call - pure SQL + datetime arithmetic.

set -euo pipefail

cat > /etc/systemd/system/ichor-event-sentinel.service <<'EOF'
[Unit]
Description=Ichor pre-announcement event sentinel (S03 Chantier D)
After=network-online.target postgresql.service
Wants=network-online.target
OnFailure=ichor-notify@%n.service

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_event_sentinel
TimeoutStartSec=120
StandardOutput=journal
StandardError=journal
# Exit 3 = DB connection failure (transient, retry next tick)
SuccessExitStatus=0 3
EOF

cat > /etc/systemd/system/ichor-event-sentinel.timer <<'EOF'
[Unit]
Description=Ichor event sentinel every 10 min (S03 Chantier D)

[Timer]
OnBootSec=4min
OnUnitActiveSec=10min
Unit=ichor-event-sentinel.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-event-sentinel.timer

echo "=== Installed event-sentinel timer (S03 Chantier D) ==="
systemctl list-timers ichor-event-sentinel.timer --no-pager
echo ""
echo "First manual run (dry-run — evaluates today's calendar, rolls back):"
sudo -u ichor /opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_event_sentinel --dry-run || echo "(exit $?)"
