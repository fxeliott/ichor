#!/usr/bin/env bash
# Register the Polygon FX WebSocket subscriber as a long-running systemd
# service on Hetzner. Unlike the cron-style oneshot collectors, this one
# stays connected continuously to wss://socket.polygon.io/forex and
# streams quote ticks into fx_ticks.
#
# Pre-reqs (one-time) :
#   - migration 0020_fx_ticks applied (alembic upgrade head)
#   - websockets>=14.0 in apps/api venv
#   - ICHOR_API_POLYGON_API_KEY present in /etc/ichor/api.env
#
# To install :
#   sudo bash register-fx-stream.sh
#
# Validation :
#   journalctl -u ichor-fx-stream -f
#   psql -c "SELECT count(*) FROM fx_ticks WHERE ts > now() - interval '5 min'"

set -euo pipefail

cat > /etc/systemd/system/ichor-fx-stream.service <<'EOF'
[Unit]
Description=Ichor Polygon FX quote-stream subscriber (VPIN feed)
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=simple
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_fx_stream

# Resilience : restart on crash / network drop with bounded backoff so a
# transient outage does not flood Polygon's rate limiter.
Restart=always
RestartSec=10
StartLimitIntervalSec=600
StartLimitBurst=10

# Resource limits — the subscriber is light (one TCP connection, batched
# DB inserts) but bound the worst case.
MemoryHigh=256M
MemoryMax=512M
CPUQuota=50%

# Logs to journal (Promtail picks them up to Loki).
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-fx-stream.service

echo "=== ichor-fx-stream registered ==="
systemctl status ichor-fx-stream --no-pager | head -8
echo ""
echo "Recent logs (Ctrl-C to exit) :"
journalctl -u ichor-fx-stream -n 20 --no-pager
