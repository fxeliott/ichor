#!/usr/bin/env bash
# Register the MODEL_PREDICTION_OUTLIER detector cron on Hetzner.
#
# Wires bias_signals.probability per-(asset, horizon) z-score
#   → MODEL_PREDICTION_OUTLIER alert when |z| ≥ 3.0.
#
# Cadence : daily 04:45 Europe/Paris (after concept-drift at 04:30).
# The 3 ML self-monitors run consecutively :
#   04:00 brier-drift (level shifts)
#   04:30 concept-drift (distributional shifts via ADWIN+Page-Hinkley)
#   04:45 prediction-outlier (point outliers)

set -euo pipefail

cat > /etc/systemd/system/ichor-prediction-outlier.service <<'EOF'
[Unit]
Description=Ichor model prediction outlier detector (z-score on bias_signals)
After=network-online.target postgresql.service ichor-concept-drift.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_prediction_outlier --persist
TimeoutStartSec=300
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-prediction-outlier.timer <<'EOF'
[Unit]
Description=Ichor prediction-outlier trigger (daily 04:45 Paris)

[Timer]
OnCalendar=*-*-* 04:45:00 Europe/Paris
Unit=ichor-prediction-outlier.service
RandomizedDelaySec=300
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-prediction-outlier.timer

echo "=== Installed prediction-outlier timer ==="
systemctl list-timers ichor-prediction-outlier.timer --no-pager
