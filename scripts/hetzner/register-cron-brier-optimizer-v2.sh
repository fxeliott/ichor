#!/usr/bin/env bash
# Register the V2 Brier optimizer cron on Hetzner.
#
# V2 (per ADR-025) runs projected-SGD on the per-factor drivers matrix
# from `session_card_audit.drivers` (JSONB col 0026). Activation is gated
# on `ICHOR_API_BRIER_V2_ENABLED=true` in /etc/ichor/api.env — when unset
# the CLI logs a single line and exits 0, so deploying this timer is safe
# even before V2 is ready to run.
#
# Schedule : 03:45 Paris, i.e. 15 minutes AFTER the V1 diagnostic run
# (V1 = 03:30 Paris, see register-cron-brier-optimizer.sh). V2 uses
# After=ichor-brier-optimizer.service in the unit chain so it only fires
# after V1 has had a chance to write its diagnostic row, even if both
# units race for the same minute on a busy night.
#
# This script is idempotent — re-running it overwrites the units cleanly.

set -euo pipefail

cat > /etc/systemd/system/ichor-brier-optimizer-v2.service <<'EOF'
[Unit]
Description=Ichor Brier→weights optimizer V2 (projected SGD on drivers JSONB)
After=network-online.target postgresql.service ichor-brier-optimizer.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_brier_optimizer_v2 --persist
TimeoutStartSec=900
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-brier-optimizer-v2.timer <<'EOF'
[Unit]
Description=Ichor Brier optimizer V2 trigger (nightly 03:45 Paris)

[Timer]
OnCalendar=*-*-* 03:45:00 Europe/Paris
Unit=ichor-brier-optimizer-v2.service
RandomizedDelaySec=300
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-brier-optimizer-v2.timer

echo "=== Installed Brier optimizer V2 timer ==="
systemctl list-timers ichor-brier-optimizer-v2.timer --no-pager
echo
echo "Reminder : V2 only runs when ICHOR_API_BRIER_V2_ENABLED=true is"
echo "set in /etc/ichor/api.env. Otherwise it logs and exits 0."
