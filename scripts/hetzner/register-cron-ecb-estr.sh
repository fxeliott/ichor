#!/usr/bin/env bash
# Register the daily €STR ingestion cron on Hetzner.
#
# ADR-090 P0 step-4 cron (round-34). Fetches the ECB Data Portal
# SDMX `EST/B.EU000A2X2A25.WT` series (free public source, daily
# refresh ~08:05 CEST after the trans-Euro short-term money market
# session) and upserts rows into `estr_observations` via INSERT ...
# ON CONFLICT DO NOTHING. Batched 5000 rows per call.
#
# Scheduled at daily 16:45 Europe/Paris :
#   * 15 min after the Bund 10Y cron (16:30) — both EUR signals
#     fresh same-day for `_section_eur_specific` Pass-2 render.
#   * 8+ hours after the ECB publication (~08:05 CEST) — safety
#     margin for any late updates.
#   * Pure-data cron — NO LLM call surface. ADR-087 5-min spacing
#     rule applies to LLM-calling crons only.
#
# Smoke verify after install :
#   systemctl list-timers ichor-ecb-estr.timer --no-pager
#   journalctl -u ichor-ecb-estr.service --since "1 day ago" --no-pager | tail -30
#   psql -d ichor -c "SELECT MAX(observation_date), COUNT(*) FROM estr_observations;"
#
# r33+r34 bug-class prevention :
#   * Collector uses COMMA delimiter (NOT semicolon like Bundesbank)
#   * Accept header `application/vnd.sdmx.data+csv;version=1.0.0`
#   * No `?format=` query param needed (ECB respects content negotiation)
#
# Feature flag gating :
#   * `ecb_estr_collector_enabled` (fail-closed default)
#   * Set to true via UPDATE feature_flags at deploy time
#
# ADR-009 Voie D : zero `import anthropic` — pure HTTPS GET against
# ECB Data Portal endpoint. No LLM surface.

set -euo pipefail

mkdir -p /etc/systemd/system/ichor-ecb-estr.service.d

cat > /etc/systemd/system/ichor-ecb-estr.service <<'EOF'
[Unit]
Description=Ichor ECB €STR daily ingestion (ADR-090 P0 step-4)
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api/src
EnvironmentFile=/etc/ichor/api.env
# --incremental : after first full backfill, only fetch new dates
# (saves bandwidth + faster cron). Default 30-day overlap window
# catches any back-revisions ECB publishes.
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_ecb_estr --incremental
TimeoutStartSec=300
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0
EOF

cat > /etc/systemd/system/ichor-ecb-estr.service.d/notify.conf <<'EOF'
[Unit]
OnFailure=ichor-notify@%n.service
EOF

cat > /etc/systemd/system/ichor-ecb-estr.timer <<'EOF'
[Unit]
Description=Ichor ECB €STR trigger (daily 16:45 Europe/Paris)

[Timer]
OnCalendar=*-*-* 16:45:00 Europe/Paris
Unit=ichor-ecb-estr.service
RandomizedDelaySec=300
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-ecb-estr.timer

echo "=== Installed €STR daily ingestion timer ==="
systemctl list-timers ichor-ecb-estr.timer --no-pager
