#!/usr/bin/env bash
# Register the TERM_PREMIUM_INTRADAY_30D cron on Hetzner.
#
# Phase E completeness — completes the 30d/90d/252d trinity for fiscal
# stress detection (sister to TERM_PREMIUM_REPRICING 90d ADR-041 and
# TERM_PREMIUM_STRUCTURAL_252D ADR-045).
#
# Daily 22:25 Paris (5 min before TERM_PREMIUM_REPRICING 22:30, lets the
# trader see acute reading first then tactical).
#
# Source : FRED:THREEFYTP10 (Kim-Wright 10y term premium, same as sisters).
# Threshold : |z| >= 2.0 vs trailing 30d distribution.
# Régimes : expansion (z>+2) | contraction (z<-2).
#
# ADR-052.

set -euo pipefail

cat > /etc/systemd/system/ichor-term-premium-intraday-check.service <<'EOF'
[Unit]
Description=Ichor TERM_PREMIUM_INTRADAY_30D acute fiscal stress alert
After=network-online.target postgresql.service ichor-collector@fred_extended.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_term_premium_intraday_check --persist
TimeoutStartSec=300
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-term-premium-intraday-check.timer <<'EOF'
[Unit]
Description=Ichor TERM_PREMIUM_INTRADAY_30D check trigger (daily 22:25 Paris)

[Timer]
OnCalendar=*-*-* 22:25:00 Europe/Paris
Unit=ichor-term-premium-intraday-check.service
RandomizedDelaySec=120
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-term-premium-intraday-check.timer

echo "=== Installed TERM_PREMIUM_INTRADAY_30D check timer ==="
systemctl list-timers ichor-term-premium-intraday-check.timer --no-pager
