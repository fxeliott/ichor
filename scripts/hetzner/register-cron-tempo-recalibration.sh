#!/usr/bin/env bash
# Register the weekly per-asset tempo threshold recalibration cron on Hetzner.
#
# r126 ADR-099 §Impl(r126) — Mission centrale Axis-7 partial extension.
# Recomputes the per-asset daily-range percentile thresholds from a rolling
# 90-day window on `polygon_intraday` and INSERTs one row per asset into
# `tempo_thresholds` (migration 0051). Consumed by the frontend
# `<TodaySessionPulse>` panel in r127 via `/v1/tempo-thresholds` (backend
# ships first, wire splits to r127).
#
# Scheduled at weekly Sunday 04:00 Europe/Paris :
#   * Low Sunday-morning systemd contention — fits the quiet 00:00-06:00
#     Paris window before the regular weekday cron storm.
#   * Pure-data cron — NO LLM call surface. ADR-087 5-min spacing rule
#     applies to LLM-calling crons only.
#   * Weekly cadence matches the rate-of-change of a 90-day rolling
#     distribution — sliding the window by 7 of 90 days each fire is
#     enough to track regime shifts without thrashing the thresholds.
#
# Smoke verify after install :
#   systemctl list-timers ichor-tempo-recalibration.timer --no-pager
#   journalctl -u ichor-tempo-recalibration.service --since "1 week ago" \
#     --no-pager | tail -50
#   sudo -u ichor psql -d ichor -c \
#     "SELECT asset, breakout_bp, active_bp, trending_bp, range_bound_bp, \
#             sample_size, window_days, computed_at \
#      FROM tempo_thresholds \
#      ORDER BY computed_at DESC \
#      LIMIT 20;"
#
# Feature flag gating :
#   * `tempo_recalibration_collector_enabled` (fail-closed default)
#   * Set to true via UPDATE feature_flags at deploy time
#
# ADR-009 Voie D : zero `import anthropic` — pure SQL aggregation against
# polygon_intraday + stdlib percentile. No LLM surface.

set -euo pipefail

mkdir -p /etc/systemd/system/ichor-tempo-recalibration.service.d

cat > /etc/systemd/system/ichor-tempo-recalibration.service <<'EOF'
[Unit]
Description=Ichor tempo threshold recalibration (r126 ADR-099 Mission Axis-7)
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api/src
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_tempo_recalibration
TimeoutStartSec=300
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0
EOF

cat > /etc/systemd/system/ichor-tempo-recalibration.service.d/notify.conf <<'EOF'
[Unit]
OnFailure=ichor-notify@%n.service
EOF

cat > /etc/systemd/system/ichor-tempo-recalibration.timer <<'EOF'
[Unit]
Description=Ichor tempo threshold recalibration trigger (weekly Sun 04:00 Europe/Paris)

[Timer]
OnCalendar=Sun *-*-* 04:00:00 Europe/Paris
Unit=ichor-tempo-recalibration.service
RandomizedDelaySec=300
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-tempo-recalibration.timer

echo "=== Installed tempo threshold recalibration weekly timer ==="
systemctl list-timers ichor-tempo-recalibration.timer --no-pager
