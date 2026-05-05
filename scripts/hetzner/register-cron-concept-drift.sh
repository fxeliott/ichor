#!/usr/bin/env bash
# Register the ADWIN concept-drift detector cron on Hetzner.
#
# Wires session_card_audit.brier_contribution stream
#   → packages/ml/regime/concept_drift.DriftMonitor (ADWIN + Page-Hinkley)
#   → CONCEPT_DRIFT_DETECTED alert when drift detected in last 10 obs.
#
# Cadence : daily 04:30 Europe/Paris (after brier-drift at 04:00).
# brier-drift catches level shifts ; ADWIN catches distributional
# changes — complementary detectors on the same input.

set -euo pipefail

cat > /etc/systemd/system/ichor-concept-drift.service <<'EOF'
[Unit]
Description=Ichor concept-drift detector (ADWIN on Brier stream)
After=network-online.target postgresql.service ichor-brier-drift.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_concept_drift --persist
TimeoutStartSec=600
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-concept-drift.timer <<'EOF'
[Unit]
Description=Ichor concept-drift trigger (daily 04:30 Paris)

[Timer]
OnCalendar=*-*-* 04:30:00 Europe/Paris
Unit=ichor-concept-drift.service
RandomizedDelaySec=300
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-concept-drift.timer

echo "=== Installed concept-drift timer ==="
systemctl list-timers ichor-concept-drift.timer --no-pager
