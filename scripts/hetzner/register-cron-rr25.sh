#!/usr/bin/env bash
# Register the RISK_REVERSAL_25D cron on Hetzner.
#
# Wires yfinance options chain (SPY/QQQ/GLD) → packages/api/services/risk_reversal_check
# → fred_observations.RR25_<asset> + RISK_REVERSAL_25D alert (metric rr25_z, |z|≥2).
#
# Cadence : twice-daily Mon-Fri at 14:05 + 21:30 Paris.
#   14:05 = right before NY equity open, captures pre-market skew shift
#   21:30 = right after NY close, captures end-of-day positioning

set -euo pipefail

cat > /etc/systemd/system/ichor-rr25-check.service <<'EOF'
[Unit]
Description=Ichor RISK_REVERSAL_25D options-skew alert
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_rr25_check --persist
TimeoutStartSec=300
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-rr25-check.timer <<'EOF'
[Unit]
Description=Ichor RR25 check trigger (twice-daily Mon-Fri)

[Timer]
OnCalendar=Mon..Fri *-*-* 14:05:00
OnCalendar=Mon..Fri *-*-* 21:30:00
Unit=ichor-rr25-check.service
RandomizedDelaySec=120
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-rr25-check.timer

echo "=== Installed RR25 check timer ==="
systemctl list-timers ichor-rr25-check.timer --no-pager
