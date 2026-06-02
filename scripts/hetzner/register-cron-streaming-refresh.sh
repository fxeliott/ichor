#!/usr/bin/env bash
# Phase 7 (ADR-109) — Register the Streaming-cadence verdict-refresh cron.
#
# Between the 4x/day batch emissions, detect a NEW strong event since each
# asset's last card (fresh economic actual / central-bank speech / strong-
# tone news, reusing _assemble_live_triggers) and regenerate ONLY that
# asset's card (4-pass + Pass-6 Opus via run_session_card._run) + push, so
# the NY-session verdict never goes stale to a market-mover between batches.
#
# ADDITIVE : never touches ichor-session-cards@.service (the 4x/day batch).
#
# Gated by feature flag streaming_refresh_enabled (default False / absent =
# fail-closed). Activate post-deploy AFTER the witness :
#
#   UPDATE feature_flags SET enabled = true
#   WHERE key = 'streaming_refresh_enabled' ;
#
# Voie D : the regen routes through the Win11 runner over the Cloudflare
# Tunnel; detection + push are pure DB reads / web-push. ZERO Anthropic
# spend. Most ticks find no new event and exit having done nothing (zero
# marginal Opus). Bounding is stateless : per-asset 45-min cooldown +
# per-fire cap (default 3) -> deterministic <= ~8 regens/hour ceiling.
#
# Doctrine #14 R-DEPLOY-6 : ConnectTimeout=15 + retry-with-sleep in
# redeploy-api.sh covers this script's systemctl invocations per lesson #24.

set -euo pipefail

cat > /etc/systemd/system/ichor-streaming-refresh.service <<'EOF'
[Unit]
Description=Ichor Streaming-cadence verdict refresh (Phase 7, ADR-109)
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_streaming_refresh
# Up to max-per-fire (3) sequential 4-pass+Pass-6 Opus regens; each ~80-240s.
# 600s < the 12-min timer interval so a runaway card is killed before the
# next tick (systemd also serialises oneshot starts -> no concurrent runs).
TimeoutStartSec=600
StandardOutput=journal
StandardError=journal
# Exit 1 = feature flag OFF (clean skip, not a failure)
# Exit 3 = DB/runtime failure (transient, retry next tick)
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-streaming-refresh.timer <<'EOF'
[Unit]
Description=Ichor Streaming-cadence verdict refresh - every 12min (Phase 7, ADR-109)

[Timer]
# Every 12 minutes (minute 0,12,24,36,48 of every hour), Europe/Paris.
# Light watcher : detection is 4 cheap SQL reads per asset; a regen only
# fires on a genuinely NEW strong event past the per-asset cooldown.
OnCalendar=*-*-* *:0/12:00 Europe/Paris
Unit=ichor-streaming-refresh.service
RandomizedDelaySec=30
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-streaming-refresh.timer

echo "=== Installed Streaming-cadence verdict refresh timer (Phase 7, ADR-109) ==="
systemctl list-timers ichor-streaming-refresh.timer --no-pager
echo ""
echo "Next steps after timer install :"
echo "  1. Verify the feature flag is OFF initially (fail-closed) :"
echo "     SELECT * FROM feature_flags WHERE key = 'streaming_refresh_enabled' ;"
echo "  2. Smoke test the CLI in dry-run mode (read-only, no regen/push) :"
echo "     /opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_streaming_refresh --dry-run"
echo "  3. Activate AFTER the witness :"
echo "     UPDATE feature_flags SET enabled = true"
echo "     WHERE key = 'streaming_refresh_enabled' ;"
echo "  4. Monitor fires via journalctl :"
echo "     journalctl -u ichor-streaming-refresh.service -f"
