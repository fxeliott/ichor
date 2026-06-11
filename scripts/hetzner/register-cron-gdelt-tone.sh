#!/usr/bin/env bash
# ADR-112 - Register the local GDELT tone scorer (FinBERT, English titles).
#
# WHY: the GDELT DOC 2.0 ArtList feed carries NO per-article tone; the
# collector's parser default left 100% of gdelt_events.tone at 0.0
# (witnessed 2026-06-11: 13,607/13,607 over the full retention), which
# silently killed every tone consumer: the geopolitics most-negative
# ranking (suspended by the PR #230 column-vitality guard), the
# TARIFF_SHOCK alert (avg_tone <= -1.5 could never fire), and the
# /v1/geopolitics/heatmap mean_tone (flat 0.0 on the consumed endpoint).
#
# Every 15 min this CLI scores unscored (tone=0.0) English rows of the
# last 6h through the LOCAL FinBERT-tone pipeline (same model already
# serving run_news_tone_scorer on this host - HF cache warm) and writes
# (p_pos - p_neg) * 10 onto the GDELT-like -10..+10 scale.
#
# Voie D: zero LLM call, zero external API - local CPU inference only.
#
# First-run backfill (48h window) is executed at the end of this script
# so the 24h consumers revive immediately.

set -euo pipefail

cat > /etc/systemd/system/ichor-gdelt-tone-scorer.service <<'EOF'
[Unit]
Description=Ichor local GDELT tone scorer (FinBERT, ADR-112)
After=network-online.target postgresql.service
Wants=network-online.target
OnFailure=ichor-notify@%n.service

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_gdelt_tone_scorer --persist
# First FinBERT load can pull the HF cache; scoring ~2500 titles on CPU
# stays well under this wall.
TimeoutStartSec=600
StandardOutput=journal
StandardError=journal
# Exit 1 = ML unavailable / batch failure -> Result=failed -> notify.
SuccessExitStatus=0
EOF

cat > /etc/systemd/system/ichor-gdelt-tone-scorer.timer <<'EOF'
[Unit]
Description=Ichor GDELT tone scorer every 15 min (ADR-112)

[Timer]
OnBootSec=4min
OnUnitActiveSec=15min
Unit=ichor-gdelt-tone-scorer.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload

# Backfill BEFORE arming the timer (reviewer PR #232 MINOR-3): enabling a
# monotonic timer whose OnBootSec already elapsed fires the service
# immediately — running the 48h backfill first avoids two concurrent
# FinBERT processes chewing the same rows at install time.
echo "First-run 48h backfill (revives the 24h consumers immediately):"
sudo -u ichor bash -c 'set -a; source /etc/ichor/api.env; set +a; \
  /opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_gdelt_tone_scorer \
  --persist --max-age-hours 48 --max-rows 2500' || echo "(backfill exit $?)"

systemctl enable --now ichor-gdelt-tone-scorer.timer

echo "=== Installed GDELT tone scorer timer (ADR-112) ==="
systemctl list-timers ichor-gdelt-tone-scorer.timer --no-pager
