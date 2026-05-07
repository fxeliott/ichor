#!/usr/bin/env bash
# Register the FOMC_TONE_SHIFT cron on Hetzner (Phase 0 = FED only).
#
# Reads recent CbSpeech rows for FED, scores each with FOMC-Roberta
# (transformers + torch CPU just installed), persists net_hawkish into
# fred_observations.FED_TONE_NET, computes rolling z-score, fires
# FOMC_TONE_SHIFT when |z| ≥ 1.5.
#
# ECB_TONE_SHIFT is intentionally DEFERRED (--cb FED only) until ECB-specific
# calibration is done — the FOMC-Roberta model interprets "patient" hawkish
# whereas ECB uses it dovishly (cf. ICAIF 2024 + FinBERT-FOMC paper).
# A separate register-cron-cb-tone-ecb.sh will land in Phase D.
#
# Cadence : daily 21:00 Paris — covers the FOMC press-conference window
# (typically 14:30 EST = 20:30 CEST). Mon-Fri only (FED quiet on weekends).

set -euo pipefail

cat > /etc/systemd/system/ichor-cb-tone-fed.service <<'EOF'
[Unit]
Description=Ichor FOMC_TONE_SHIFT central-bank tone alert (FED only)
After=network-online.target postgresql.service ichor-collector-cb_speeches.service ichor-collector-central_bank_speeches.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_cb_tone_check --persist --cb FED
TimeoutStartSec=600
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-cb-tone-fed.timer <<'EOF'
[Unit]
Description=Ichor FED tone check trigger (daily Mon-Fri 21:00)

[Timer]
OnCalendar=Mon..Fri *-*-* 21:00:00
Unit=ichor-cb-tone-fed.service
RandomizedDelaySec=180
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-cb-tone-fed.timer

echo "=== Installed FED tone check timer ==="
systemctl list-timers ichor-cb-tone-fed.timer --no-pager
