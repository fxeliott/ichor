#!/usr/bin/env bash
# Register the daily Bund 10Y ingestion cron on Hetzner.
#
# ADR-090 P0 step-1 cron (round-33). Fetches the Bundesbank SDMX
# `BBSIS/D.I.ZAR.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A` series
# (free public source, daily refresh ~16:00 CEST after the German
# bond market close) and upserts rows into `bund_10y_observations`
# via INSERT ... ON CONFLICT DO NOTHING. Batched 5000 rows per call
# (asyncpg 32767 param limit / 5 cols = 6553 max).
#
# Scheduled at daily 16:30 Europe/Paris :
#   * 30 min after Bundesbank refresh — safety margin for late updates.
#   * 30 min BEFORE the proposed €STR cron at 16:45 (W117c roadmap).
#   * Pure-data cron — NO LLM call surface. ADR-087 5-min spacing
#     rule applies to LLM-calling crons only ; daily 16:30 is fine.
#
# Smoke verify after install :
#   systemctl list-timers ichor-bundesbank-bund.timer --no-pager
#   journalctl -u ichor-bundesbank-bund.service --since "1 day ago" --no-pager | tail -30
#   psql -d ichor -c "SELECT MAX(observation_date), COUNT(*) FROM bund_10y_observations;"
#
# Round-32c bug fixes embedded in the collector :
#   * URL has NO `?format=csvdata` (Bundesbank rejects with HTTP 406)
#   * CSV parser uses `delimiter=';'` (SDMX-CSV 1.0.0 spec)
#
# Feature flag gating :
#   * `bundesbank_bund_collector_enabled` (fail-closed default).
#   * Set to true via UPDATE feature_flags at deploy time.
#
# ADR-009 Voie D : zero `import anthropic` — pure HTTPS GET against
# Bundesbank SDMX endpoint. No LLM surface.

set -euo pipefail

mkdir -p /etc/systemd/system/ichor-bundesbank-bund.service.d

cat > /etc/systemd/system/ichor-bundesbank-bund.service <<'EOF'
[Unit]
Description=Ichor Bundesbank Bund 10Y daily ingestion (ADR-090 P0 step-1)
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api/src
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_bundesbank_bund
TimeoutStartSec=300
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0
EOF

cat > /etc/systemd/system/ichor-bundesbank-bund.service.d/notify.conf <<'EOF'
[Unit]
OnFailure=ichor-notify@%n.service
EOF

cat > /etc/systemd/system/ichor-bundesbank-bund.timer <<'EOF'
[Unit]
Description=Ichor Bundesbank Bund 10Y trigger (daily 16:30 Europe/Paris)

[Timer]
OnCalendar=*-*-* 16:30:00 Europe/Paris
Unit=ichor-bundesbank-bund.service
RandomizedDelaySec=300
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-bundesbank-bund.timer

echo "=== Installed Bund 10Y daily ingestion timer ==="
systemctl list-timers ichor-bundesbank-bund.timer --no-pager
