#!/usr/bin/env bash
# Register the FinBERT-tone news scorer cron on Hetzner.
#
# Wires news_items WHERE tone_label IS NULL
#   → packages.ml.nlp.finbert_tone.score_tones_batch
#   → UPDATE news_items SET tone_label + tone_score (signed confidence).
#
# Activates the upstream data flow for NEWS_NEGATIVE_BURST alert
# (Sprint 6) which scans tone_label='negative' AND tone_score < -0.5
# in 5-min windows.
#
# First run downloads the FinBERT model (~400 MB) — TimeoutStartSec=900
# accommodates the cold start. Subsequent runs use the cached pipeline.

set -euo pipefail

cat > /etc/systemd/system/ichor-news-tone.service <<'EOF'
[Unit]
Description=Ichor news tone scorer (FinBERT)
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_news_tone_scorer --persist
TimeoutStartSec=900
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-news-tone.timer <<'EOF'
[Unit]
Description=Ichor news tone scorer trigger (every 15 min)

[Timer]
OnCalendar=*:0/15
Unit=ichor-news-tone.service
RandomizedDelaySec=120
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-news-tone.timer

echo "=== Installed news tone timer ==="
systemctl list-timers ichor-news-tone.timer --no-pager
