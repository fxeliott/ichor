#!/usr/bin/env bash
# r165 Strand F - Register the Scenario Invalidation Monitor cron.
#
# ADR-106 Stride 1 closure : poll session_card_audit recent rows + evaluate
# populated invalidations via r164 monitor + emit canonical alerts via r165
# alerts pipeline. 6x/day Paris (00/04/08/12/16/20) per ADR-106 D3 refresh
# cycle rationale (pre-Tokyo / pre-London / pre-NY / mid-NY / end-NY / EOD).
#
# Gated by feature flag scenario_invalidation_monitor_enabled (default False).
# Activate post-deploy ONLY after Pass-6 populated path empirical validation
# >=3 production sessions per ADR-106 Carry-forward r166 :
#
#   UPDATE feature_flags SET enabled = true
#   WHERE key = 'scenario_invalidation_monitor_enabled' ;
#
# Voie D : zero LLM call, pure SQL + Python comparisons via r164 monitor.
# The cron stays within the Voie D ceiling at runtime.
#
# Doctrine #14 R-DEPLOY-6 hardening : ConnectTimeout=15 + retry-with-sleep
# present in redeploy-api.sh ensures this script's systemctl daemon-reload
# + enable invocations survive SSH-instability per lesson #24.
#
# Doctrine #11 calibrated honesty : if no card has populated invalidations
# yet (pre-Pass-6 activation), the monitor returns None per card -> cron
# logs "persisted=0 alerts" without fabricating noise.

set -euo pipefail

cat > /etc/systemd/system/ichor-scenario-invalidation-check.service <<'EOF'
[Unit]
Description=Ichor Scenario Invalidation Monitor cron (r165 Strand F)
OnFailure=ichor-notify@%n.service
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
# VALIDATION MODE (S03 2026-06-11): --dry-run evaluates the day's real
# cards with the flag OFF (read-only, rolled back, notify-gated) so the
# >=3-session arming evidence accumulates automatically in journalctl —
# without it the timer would exit-1 skip and the validation could never
# progress. ARMING STEP (owner, after >=3 clean sessions): set the
# feature flag to true AND remove --dry-run below, then re-register.
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_scenario_invalidation_check --dry-run
TimeoutStartSec=300
StandardOutput=journal
StandardError=journal
# Exit 1 = feature flag OFF without --dry-run (clean skip, not a failure)
# Exit 3 = DB connection failure (transient, retry next tick)
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-scenario-invalidation-check.timer <<'EOF'
[Unit]
Description=Ichor Scenario Invalidation Monitor - 6x/day (r165 Strand F)

[Timer]
# 6x/day Paris : 00, 04, 08, 12, 16, 20 per ADR-106 D3 cadence rationale
#   00h : EOD captures post-20h NY moves
#   04h : pre-Tokyo opening (Asian session pulse check)
#   08h : pre-London opening (EU-session repricing window)
#   12h : peri-briefing (right before pre-NY emission ~12h45)
#   16h : mid-NY session (trader's 14h-20h execution window)
#   20h : end-of-NY-session (final-hour captures before verdict expires_at)
OnCalendar=*-*-* 00,04,08,12,16,20:00:00 Europe/Paris
Unit=ichor-scenario-invalidation-check.service
RandomizedDelaySec=120
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-scenario-invalidation-check.timer

echo "=== Installed Scenario Invalidation Monitor timer (r165 Strand F) ==="
systemctl list-timers ichor-scenario-invalidation-check.timer --no-pager
echo ""
echo "Next steps after timer install :"
echo "  1. Verify feature flag is OFF initially :"
echo "     SELECT * FROM feature_flags WHERE key = 'scenario_invalidation_monitor_enabled' ;"
echo "  2. Smoke test the CLI in dry-run mode :"
echo "     /opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_scenario_invalidation_check --dry-run"
echo "  3. Activate AFTER Pass-6 empirical validation >=3 prod sessions :"
echo "     UPDATE feature_flags SET enabled = true"
echo "     WHERE key = 'scenario_invalidation_monitor_enabled' ;"
echo "  4. Monitor first fire via journalctl :"
echo "     journalctl -u ichor-scenario-invalidation-check.service -f"
