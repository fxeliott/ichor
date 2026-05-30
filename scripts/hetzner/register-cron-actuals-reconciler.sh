#!/usr/bin/env bash
# r144 — Register the FRED ALFRED economic_events.actual reconciler.
#
# Backfills `economic_events.actual` for US events 4×/day via FRED
# ALFRED first-vintage values. Idempotent — re-runs skip events that
# already have `actual` populated (preserves first-vintage even if
# FRED issues T+24h revisions).
#
# Cadence : 01:15 / 07:15 / 13:15 / 19:15 Paris — offset 15 min from
# the existing FF collector fires (03/09/15/21h) so FF has already
# upserted the event row before the reconciler queries it.
#
# Gated by feature flag `actuals_reconciler_enabled` (default False).
# To activate post-deploy :
#   UPDATE feature_flags SET enabled = true WHERE key = 'actuals_reconciler_enabled';
# (or seed if absent via the W116 / W117a pattern).
#
# Honest scope (lesson #37) :
#   - US-only (currency = 'USD').
#   - 12 viable FRED series cover ~70-80% of tier-1 USD events.
#   - ISM Manufacturing PMI / ISM Services PMI / ADP Employment Change
#     are licensing-blocked / discontinued on FRED → `actual` stays
#     NULL for those events (reconciler silently skips unmapped titles).
#   - EU/UK/JP/AU/CA `actual` providers deferred r145+.
#
# Voie D : ALFRED API uses the same `fred_api_key` (env
# ICHOR_API_FRED_API_KEY) as existing FRED collectors ; no paid API.

set -euo pipefail

cat > /etc/systemd/system/ichor-actuals-reconciler.service <<'EOF'
[Unit]
Description=Ichor FRED ALFRED economic_events.actual reconciler (r144)
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_economic_event_actuals_reconcile
TimeoutStartSec=300
StandardOutput=journal
StandardError=journal
# Exit 1 = feature flag OFF (clean skip, not a failure)
# Exit 2 = ICHOR_API_FRED_API_KEY empty (clean skip, not a failure)
SuccessExitStatus=0 1 2
EOF

cat > /etc/systemd/system/ichor-actuals-reconciler.timer <<'EOF'
[Unit]
Description=Ichor FRED ALFRED actuals reconciler — 4x/day (r144)

[Timer]
# Offset 15 min from FF collector fires (03/09/15/21h Paris) so FF has
# upserted the event row before reconciler queries it.
OnCalendar=*-*-* 01,07,13,19:15:00 Europe/Paris
Unit=ichor-actuals-reconciler.service
RandomizedDelaySec=120
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-actuals-reconciler.timer

echo "=== Installed FRED ALFRED actuals reconciler timer (r144) ==="
systemctl list-timers ichor-actuals-reconciler.timer --no-pager
