#!/usr/bin/env bash
# Register the HY_IG_SPREAD_DIVERGENCE cron on Hetzner (Phase E completeness).
#
# Daily 22:48 Paris in the nightly macro chain :
#   22:35 macro-quartet
#   22:40 dollar-smile
#   22:42 treasury-vol
#   22:45 vix-term
#   22:48 hy-ig-spread     ← THIS
#   22:50 yield-curve-inversion
#   22:55 yield-curve-un-inversion
#
# Source : FRED:BAMLH0A0HYM2 (HY OAS) + FRED:BAMLC0A0CM (IG OAS) — both
# already in fred_extended.py EXTENDED_SERIES_TO_POLL.
#
# Detects credit-cycle inflection :
#   z > +2σ : expansion (HY widens > IG widens) = late-cycle credit stress
#   z < -2σ : compression (HY tightens > IG tightens) = early flight-to-quality
#
# Per ICAIF + Macrosynergy + InvestmentGrade Q1 2026 research, HY-IG
# differential front-runs HY OAS spikes by 2-4 weeks.
#
# ADR-049.

set -euo pipefail

cat > /etc/systemd/system/ichor-hy-ig-spread-check.service <<'EOF'
[Unit]
Description=Ichor HY_IG_SPREAD_DIVERGENCE credit-cycle alert
After=network-online.target postgresql.service ichor-collector@fred_extended.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_hy_ig_spread_check --persist
TimeoutStartSec=300
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-hy-ig-spread-check.timer <<'EOF'
[Unit]
Description=Ichor HY_IG_SPREAD_DIVERGENCE check trigger (daily 22:48 Paris)

[Timer]
OnCalendar=*-*-* 22:48:00 Europe/Paris
Unit=ichor-hy-ig-spread-check.service
RandomizedDelaySec=120
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-hy-ig-spread-check.timer

echo "=== Installed HY_IG_SPREAD_DIVERGENCE check timer ==="
systemctl list-timers ichor-hy-ig-spread-check.timer --no-pager
