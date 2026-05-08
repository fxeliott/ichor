#!/usr/bin/env bash
# Register the MACRO_QUINTET_STRESS cron on Hetzner.
#
# Phase E completeness — closes the followup in ADR-048 §Followups :
# upgrade MACRO_QUARTET_STRESS to MACRO_QUINTET_STRESS by adding
# TREASURY_VOL_SPIKE z-score as 5th dimension.
#
# Daily 22:37 Paris (after MACRO_QUARTET 22:35, before TREASURY_VOL 22:42).
#
# 5 dimensions: DXY (DTWEXBGS) + 10Y (DGS10 level) + VIX (VIXCLS) +
# HY OAS (BAMLH0A0HYM2) + Treasury vol (DGS10 30d realized vol annualized).
# Threshold: N>=4/5 |z|>2 alignment (stricter than quartet 3-of-4 to maintain
# specificity given 5 independent axes).
#
# ADR-051.

set -euo pipefail

cat > /etc/systemd/system/ichor-macro-quintet-check.service <<'EOF'
[Unit]
Description=Ichor MACRO_QUINTET_STRESS 5-dim composite stress alert
After=network-online.target postgresql.service ichor-collector@fred_extended.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_macro_quintet_check --persist
TimeoutStartSec=300
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-macro-quintet-check.timer <<'EOF'
[Unit]
Description=Ichor MACRO_QUINTET_STRESS check trigger (daily 22:37 Paris)

[Timer]
OnCalendar=*-*-* 22:37:00 Europe/Paris
Unit=ichor-macro-quintet-check.service
RandomizedDelaySec=120
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-macro-quintet-check.timer

echo "=== Installed MACRO_QUINTET_STRESS check timer ==="
systemctl list-timers ichor-macro-quintet-check.timer --no-pager
