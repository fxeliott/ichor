#!/usr/bin/env bash
# Register the `ichor-notify@.service` systemd template (Phase A.4.b
# observability). Triggered by any ichor-*.service via OnFailure=,
# logs the failure to journal + /var/log/ichor-failures.log + (opt) ntfy.
#
# Idempotent : safe to re-run.

set -euo pipefail

# Ensure log file exists with proper permissions
touch /var/log/ichor-failures.log
chmod 0644 /var/log/ichor-failures.log
chown root:root /var/log/ichor-failures.log

# Ensure the worker script is in place at the canonical location
install -m 0755 -o root -g root \
    /opt/ichor/scripts/hetzner/notify-failure.sh \
    /opt/ichor/scripts/notify-failure.sh

cat > "/etc/systemd/system/ichor-notify@.service" <<'EOF'
[Unit]
Description=Ichor failure notifier (logs + optional ntfy push)
Documentation=ADR-030 + Phase A.4.b ROADMAP

[Service]
Type=oneshot
User=root
ExecStart=/opt/ichor/scripts/notify-failure.sh %i
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0
EOF

systemctl daemon-reload

echo "=== Installed ichor-notify@ template + worker script ==="
systemctl cat "ichor-notify@" --no-pager 2>&1 | head -20
echo
echo "Next: add 'OnFailure=ichor-notify@%n.service' as a drop-in on each ichor-*.service."
echo "Drop-ins land under /etc/systemd/system/<unit>.service.d/notify.conf"
