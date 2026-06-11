#!/usr/bin/env bash
# S03 Chantier D - Register the proactive data-freshness monitor.
#
# Closes the Chantier D gate "a deliberately-killed COLLECTOR fires an
# alert < 15 min" (the RUNNER half shipped with ADR-110's
# ichor-runner-health-check). Every 5 min the CLI MAX()es each monitored
# collect table against services/collector_freshness.FRESHNESS_REGISTRY,
# emits COLLECTOR_STALE / COLLECTOR_ABSENT / RSS_FEED_SILENT alerts via
# the canonical pipeline (2h dedup per source), and exits 2 on the
# healthy->degraded TRANSITION (state file /var/lib/ichor, mirrors
# runner-health-check) -> systemd Result=failed -> OnFailure=ichor-notify@
# -> journald err + /var/log/ichor-failures.log + optional ntfy.
#
# Detection latency: <= 5 min timer + <= 15 min fast-tier max_age
# => killed fx/polygon/polymarket collector alerts within ~15 min while
# its market is open (ADR-105 gating kills weekend/reopen false alarms).
#
# Exit-code policing on collector units was deliberately REJECTED:
# collectors legitimately exit 1 on benign empty sources, so their
# SuccessExitStatus=0 1 stays. The DESTINATION TABLE freshness is the
# outcome that matters; this monitor measures that.
#
# Voie D : zero LLM call - pure SQL MAX() + catalog evaluation.

set -euo pipefail

install -d -m 0755 -o ichor -g ichor /var/lib/ichor

cat > /etc/systemd/system/ichor-data-freshness-check.service <<'EOF'
[Unit]
Description=Ichor proactive data-freshness monitor (S03 Chantier D)
After=network-online.target postgresql.service
Wants=network-online.target
OnFailure=ichor-notify@%n.service

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_data_freshness_check
TimeoutStartSec=180
StandardOutput=journal
StandardError=journal
# Exit 2 = critical degradation transition -> Result=failed -> notify.
# Exit 3 = DB connection failure (transient, retry next tick).
SuccessExitStatus=0 3
EOF

cat > /etc/systemd/system/ichor-data-freshness-check.timer <<'EOF'
[Unit]
Description=Ichor data-freshness monitor every 5 min (S03 Chantier D)

[Timer]
OnBootSec=3min
OnUnitActiveSec=5min
Unit=ichor-data-freshness-check.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-data-freshness-check.timer

echo "=== Installed data-freshness monitor timer (S03 Chantier D) ==="
systemctl list-timers ichor-data-freshness-check.timer --no-pager
echo ""
echo "First manual run (dry-run prints the full freshness table):"
sudo -u ichor /opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_data_freshness_check --dry-run || echo "(exit $?)"
