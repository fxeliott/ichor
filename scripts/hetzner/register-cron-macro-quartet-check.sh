#!/usr/bin/env bash
# Register the MACRO_QUARTET_STRESS cron on Hetzner (Phase E.4).
#
# Wires services/macro_quartet_check.py (composite 4-dim z-score on
# DXY + 10Y + VIX + HY OAS) → MACRO_QUARTET_STRESS alert
# (metric quartet_stress_count, fires when count >= 3 of 4 dims |z|>2).
# Source: FRED:DTWEXBGS+DGS10+VIXCLS+BAMLH0A0HYM2.
#
# Cadence : daily 22:35 Paris.
#   Post NY close + 5 min after TERM_PREMIUM_REPRICING (22:30) so they
#   share the same FRED data freshness window. Both depend on the FRED
#   extended collector run at 18:30 Paris.
#
# Idempotent.

set -euo pipefail

cat > /etc/systemd/system/ichor-macro-quartet-check.service <<'EOF'
[Unit]
Description=Ichor MACRO_QUARTET_STRESS 4-dim composite stress alert
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_macro_quartet_check --persist
TimeoutStartSec=300
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-macro-quartet-check.timer <<'EOF'
[Unit]
Description=Ichor MACRO_QUARTET_STRESS trigger (daily 22:35 Paris)

[Timer]
OnCalendar=*-*-* 22:35:00 Europe/Paris
Unit=ichor-macro-quartet-check.service
RandomizedDelaySec=180
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-macro-quartet-check.timer

echo "=== Installed MACRO_QUARTET_STRESS check timer ==="
systemctl list-timers --no-pager | grep ichor-macro-quartet || true

echo ""
echo "Next runs:"
systemctl list-timers ichor-macro-quartet-check.timer --no-pager 2>&1 | tail -2 | head -1
