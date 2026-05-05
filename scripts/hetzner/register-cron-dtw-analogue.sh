#!/usr/bin/env bash
# Register the DTW analogue match cron on Hetzner.
#
# Wires fred_observations.VIXCLS (last 28d) → DTWAnalogueMatcher
# (8 archetypes via services/analogue_library) → ANALOGUE_MATCH_HIGH
# alert when min DTW distance ≤ 0.15.
#
# Cadence : daily 05:00 Europe/Paris — fifth and last leg of the
# ML self-monitor + analogue triad :
#   04:00 brier-drift   (Brier level shift)
#   04:30 concept-drift (ADWIN distributional shift)
#   04:45 prediction-outlier (z-score on bias_signals)
#   05:00 dtw-analogue  (regime archetype match)

set -euo pipefail

cat > /etc/systemd/system/ichor-dtw-analogue.service <<'EOF'
[Unit]
Description=Ichor DTW analogue matcher (VIX vs 8 historical archetypes)
After=network-online.target postgresql.service ichor-prediction-outlier.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_dtw_analogue --persist
TimeoutStartSec=300
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-dtw-analogue.timer <<'EOF'
[Unit]
Description=Ichor DTW analogue trigger (daily 05:00 Paris)

[Timer]
OnCalendar=*-*-* 05:00:00 Europe/Paris
Unit=ichor-dtw-analogue.service
RandomizedDelaySec=300
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-dtw-analogue.timer

echo "=== Installed DTW analogue timer ==="
systemctl list-timers ichor-dtw-analogue.timer --no-pager
