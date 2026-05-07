#!/usr/bin/env bash
# Register the multi-CB tone-shift cron on Hetzner.
#
# Phase 0 shipped FED only. Phase D.5.d (PR #32, ADR-040) extends to
# the 4 G7 pillar central banks : FED + ECB + BOE + BOJ. The CLI
# auto-iterates over CB_TO_METRIC keys when --cb is omitted, so this
# script no longer pins to a single CB.
#
# For each CB, the runner :
#   1. Reads recent CbSpeech rows (last 24h, case-insensitive query)
#   2. Scores each speech with FOMC-Roberta zero-shot transfer
#      (gtfintechlab) — the hawkish/dovish lexicon is shared across
#      G7 CBs per ICAIF 2024 benchmark
#   3. Persists net_hawkish into fred_observations.{CB}_TONE_NET
#   4. Computes 90d rolling z-score
#   5. Fires the per-CB alert (fomc_tone_z / ecb_tone_z / boe_tone_z /
#      boj_tone_z) when |z| >= 1.5
#
# Cadence : daily Mon-Fri 21:00 Paris.
#   - FOMC press conference window (14:30 EST = 20:30 CEST) ✓
#   - ECB press conference window (14:30 CET = 14:30 CEST) ✓ (already past)
#   - BoE MPC announcement window (12:00 GMT = 13:00 CEST) ✓ (already past)
#   - BoJ usually announces in Tokyo morning (03:00 JST = 19:00 CEST) ✓
#   The 21h slot covers all 4 same-day events. v2 could add a second
#   slot for off-cycle Asia speeches if BoJ tone shifts get missed.

set -euo pipefail

cat > /etc/systemd/system/ichor-cb-tone.service <<'EOF'
[Unit]
Description=Ichor multi-CB tone-shift alerts (FED + ECB + BOE + BOJ)
After=network-online.target postgresql.service ichor-collector-cb_speeches.service ichor-collector-central_bank_speeches.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_cb_tone_check --persist
TimeoutStartSec=900
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-cb-tone.timer <<'EOF'
[Unit]
Description=Ichor multi-CB tone check trigger (daily Mon-Fri 21:00 Paris)

[Timer]
OnCalendar=Mon..Fri *-*-* 21:00:00
Unit=ichor-cb-tone.service
RandomizedDelaySec=180
Persistent=true

[Install]
WantedBy=timers.target
EOF

# Disable the legacy FED-only timer (replaced by ichor-cb-tone.timer
# which auto-iterates over CB_TO_METRIC). Idempotent : if the legacy
# unit doesn't exist (fresh install), the disable is a no-op.
if systemctl list-unit-files | grep -q ichor-cb-tone-fed; then
    systemctl disable --now ichor-cb-tone-fed.timer 2>/dev/null || true
    rm -f /etc/systemd/system/ichor-cb-tone-fed.service /etc/systemd/system/ichor-cb-tone-fed.timer
fi

systemctl daemon-reload
systemctl enable --now ichor-cb-tone.timer

echo "=== Installed multi-CB tone check timer ==="
systemctl list-timers ichor-cb-tone.timer --no-pager
