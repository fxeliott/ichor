#!/usr/bin/env bash
# Register the weekly EIA crude-stocks ingestion cron on Hetzner.
#
# ADR-107 cron (r190). Fetches weekly US petroleum-stock series from
# EIA OpenData v2 `petroleum/stoc/wstk` (WCESTUS1 / WCRSTUS1 / WTTSTUS1)
# and upserts rows into `eia_crude_stocks` via INSERT ... ON CONFLICT
# DO NOTHING on (series_id, observation_date). Feeds the theme_classifier
# `supply_demand` driver (Eliot Fathom transcript étape 1, the 8th driver).
#
# Scheduled weekly Thursday 06:00 Europe/Paris :
#   * The EIA Weekly Petroleum Status Report releases Wed 10:30 ET
#     (~16:30 Paris winter / 15:30 summer). Thursday 06:00 Paris is a
#     generous safety margin after publication.
#   * Pure-data cron — NO LLM call surface (ADR-009 Voie D ; the ADR-087
#     5-min LLM-cron spacing rule does not apply).
#
# Smoke verify after install :
#   systemctl list-timers ichor-eia-crude-stocks.timer --no-pager
#   journalctl -u ichor-eia-crude-stocks.service --since "1 day ago" --no-pager | tail -30
#   psql -d ichor -c "SELECT series_id, MAX(observation_date), COUNT(*) FROM eia_crude_stocks GROUP BY series_id;"
#
# Prerequisites (Eliot-gated, one-time) :
#   1. EIA_API_KEY in /etc/ichor/api.env  (EIA has NO anonymous tier ;
#      free registration at https://www.eia.gov/opendata/register.php).
#   2. Feature flag : UPDATE feature_flags SET enabled = true,
#      rollout_pct = 100 WHERE flag_name = 'eia_crude_stocks_collector_enabled';
#      (fail-closed default — the CLI is a no-op until flipped.)
#
# Backfill (one-shot, after the flag + key are set) :
#   /opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_eia_crude_stocks --last-n-obs 120

set -euo pipefail

mkdir -p /etc/systemd/system/ichor-eia-crude-stocks.service.d

cat > /etc/systemd/system/ichor-eia-crude-stocks.service <<'EOF'
[Unit]
Description=Ichor EIA weekly crude-stocks ingestion (ADR-107 supply_demand)
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api/src
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_eia_crude_stocks
TimeoutStartSec=300
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0
EOF

cat > /etc/systemd/system/ichor-eia-crude-stocks.service.d/notify.conf <<'EOF'
[Unit]
OnFailure=ichor-notify@%n.service
EOF

cat > /etc/systemd/system/ichor-eia-crude-stocks.timer <<'EOF'
[Unit]
Description=Ichor EIA crude-stocks trigger (weekly Thu 06:00 Europe/Paris)

[Timer]
OnCalendar=Thu *-*-* 06:00:00 Europe/Paris
Unit=ichor-eia-crude-stocks.service
RandomizedDelaySec=600
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-eia-crude-stocks.timer

echo "=== Installed EIA crude-stocks weekly ingestion timer ==="
systemctl list-timers ichor-eia-crude-stocks.timer --no-pager
