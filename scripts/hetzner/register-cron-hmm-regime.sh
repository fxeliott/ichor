#!/usr/bin/env bash
# Register the HMM regime detection cron on Hetzner.
#
# Wires polygon_intraday_bars (1-min OHLCV)
#   → packages/ml/regime/hmm.HMMRegimeDetector (3-state Gaussian HMM)
#   → fred_observations.HMM_REGIME_{asset}
#   → REGIME_CHANGE_HMM alert when state transitions vs prior run
#
# Cadence : daily 23:45 Europe/Paris (15 min after HAR-RV at 23:30 ;
# both consume the day's bars but operate independently).

set -euo pipefail

cat > /etc/systemd/system/ichor-hmm-regime.service <<'EOF'
[Unit]
Description=Ichor HMM 3-state regime detection (per asset, daily)
After=network-online.target postgresql.service ichor-har-rv.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_hmm_regime --persist
TimeoutStartSec=600
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-hmm-regime.timer <<'EOF'
[Unit]
Description=Ichor HMM regime detection trigger (23:45 Paris)

[Timer]
OnCalendar=*-*-* 23:45:00 Europe/Paris
Unit=ichor-hmm-regime.service
RandomizedDelaySec=300
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-hmm-regime.timer

echo "=== Installed HMM regime timer ==="
systemctl list-timers ichor-hmm-regime.timer --no-pager
