#!/usr/bin/env bash
# Register the 5 Ichor briefing crons on Hetzner via systemd timers.
#
# Briefing schedule (Europe/Paris, per ARCHITECTURE_FINALE.md):
#   06:00  pre_londres   (5 actifs core P1)
#   12:00  pre_ny        (8 actifs P1+P2)
#   17:00  ny_mid        (8 actifs P1+P2)
#   22:00  ny_close      (8 actifs P1+P2)
#   Sun 18:00  weekly    (8 actifs, weekly review)
#
# Each timer triggers a oneshot service that:
#   1. Decrypts cloudflare.env (R2 + CF Access tokens) via SOPS
#   2. Assembles context.md (queries Postgres for ML signals + recent news)
#   3. POSTs context to <TUNNEL-UUID>.cfargotunnel.com/v1/briefing-task
#      with CF-Access-Client-Id + CF-Access-Client-Secret headers
#   4. Inserts the resulting markdown into briefings table
#
# This script INSTALLS the systemd units. The actual briefing-runner binary
# (apps/api/src/ichor_api/cli/run_briefing.py) will land in Phase 0 W2.

set -euo pipefail

# Service template (single binary, briefing_type passed as arg)
#
# r51 hardening (subagent F + M wave 2 finding) : OnFailure inline at
# template level. The post-hoc install-onfailure-dropins.sh excludes
# `^ichor-.*\.service$` matches against `@.service` templates by regex
# (line 14-15), so concrete instances `ichor-briefing@pre_ny.service`
# never gained the failure-notify drop-in. As a result, briefing
# 530-storm failures during 2026-05-13 -> 2026-05-15 blackout went
# silently to journalctl with no notify. Inline OnFailure here so
# the template propagates the directive to every instance unit.
cat > /etc/systemd/system/ichor-briefing@.service <<'EOF'
[Unit]
Description=Ichor briefing runner (%i)
After=network-online.target postgresql.service
Wants=network-online.target
OnFailure=ichor-notify@%n.service

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/dev/shm/ichor-secrets.env
ExecStartPre=/usr/local/bin/ichor-decrypt-secrets
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_briefing %i
ExecStartPost=/usr/bin/shred -u /dev/shm/ichor-secrets.env
StandardOutput=journal
StandardError=journal
EOF

# Timers — one per briefing type
declare -A SCHEDULES=(
  [pre_londres]="*-*-* 06:00:00 Europe/Paris"
  [pre_ny]="*-*-* 12:00:00 Europe/Paris"
  [ny_mid]="*-*-* 17:00:00 Europe/Paris"
  [ny_close]="*-*-* 22:00:00 Europe/Paris"
  [weekly]="Sun *-*-* 18:00:00 Europe/Paris"
)

for type in "${!SCHEDULES[@]}"; do
  cat > /etc/systemd/system/ichor-briefing-"${type}".timer <<EOF
[Unit]
Description=Ichor briefing trigger (${type})

[Timer]
OnCalendar=${SCHEDULES[$type]}
Unit=ichor-briefing@${type}.service
RandomizedDelaySec=120
Persistent=true

[Install]
WantedBy=timers.target
EOF
done

systemctl daemon-reload

# Enable + start (timers only — services trigger on schedule)
for type in "${!SCHEDULES[@]}"; do
  systemctl enable --now ichor-briefing-"${type}".timer
done

echo "=== Installed timers ==="
systemctl list-timers --no-pager | grep ichor-briefing

echo ""
echo "Next runs:"
for type in "${!SCHEDULES[@]}"; do
  systemctl list-timers ichor-briefing-"${type}".timer --no-pager 2>&1 | tail -2 | head -1
done
