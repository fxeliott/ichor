#!/usr/bin/env bash
# Register the Crisis Mode auto-trigger cron on Hetzner.
#
# Wires `alerts.crisis_mode.assess_crisis` (was test-only) into a
# 5-minute systemd timer. The runner :
#   - inserts CRISIS_MODE_ACTIVE when ≥2 crisis_mode alerts fire
#     within the trailing 60min window
#   - inserts CRISIS_MODE_RESOLVED when the count drops back below 2
#   - de-dups against the last state in the DB (no spam)
#
# Crisis triggers (catalog.py:CRISIS_TRIGGERS) :
#   HY_OAS_CRISIS, VIX_PANIC, GEX_FLIP, SOFR_SPIKE, FX_PEG_BREAK,
#   DEALER_GAMMA_FLIP, LIQUIDITY_BIDASK_WIDEN

set -euo pipefail

cat > /etc/systemd/system/ichor-crisis-check.service <<'EOF'
[Unit]
Description=Ichor Crisis Mode auto-trigger (composite check)
After=network-online.target postgresql.service
Wants=network-online.target
# S02 socle audit (2026-06-18) — the crisis DETECTOR going blind must not be
# silent. notify-failure fires on any non-whitelisted exit (real bug).
OnFailure=ichor-notify@%n.service

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_crisis_check --persist
TimeoutStartSec=120
StandardOutput=journal
StandardError=journal
# Exit 0 = ok ; 3 = transient DB/runtime failure (tolerated — the data-freshness
# monitor pages on sustained DB-down, so a single blip here stays quiet). Any
# OTHER non-zero (a real crisis-check bug) → Result=failed → OnFailure notify.
# The old `0 1` MASKED an uncaught exit-1 crash of the crisis detector (S02 fix).
SuccessExitStatus=0 3
EOF

cat > /etc/systemd/system/ichor-crisis-check.timer <<'EOF'
[Unit]
Description=Ichor crisis-check trigger (every 5 min)

[Timer]
OnCalendar=*:0/5
Unit=ichor-crisis-check.service
RandomizedDelaySec=30
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-crisis-check.timer

echo "=== Installed crisis-check timer ==="
systemctl list-timers ichor-crisis-check.timer --no-pager
