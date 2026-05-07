#!/usr/bin/env bash
# Install OnFailure= drop-ins on every active ichor-*.service so that
# any unit fail triggers ichor-notify@%n.service (Phase A.4.b).
#
# Drop-in pattern: /etc/systemd/system/<unit>.service.d/notify.conf
# Idempotent: re-running just overwrites the conf with the same content.
#
# Excludes ichor-notify@.service itself (would loop).
# Excludes the legacy apps/web tunnel pair (already retired but units may exist).

set -euo pipefail

# Discover currently-loaded ichor-*.service (concrete, not template)
mapfile -t UNITS < <(systemctl list-unit-files --type=service --no-pager --no-legend 2>/dev/null \
    | awk '$1 ~ /^ichor-.*\.service$/ && $1 !~ /^ichor-notify/ && $1 !~ /@\.service$/ { print $1 }')

if [ ${#UNITS[@]} -eq 0 ]; then
    echo "No ichor-*.service units found — bail."
    exit 1
fi

echo "Installing OnFailure drop-ins on ${#UNITS[@]} units:"
for u in "${UNITS[@]}"; do
    DROPIN_DIR="/etc/systemd/system/${u}.d"
    mkdir -p "$DROPIN_DIR"
    cat > "${DROPIN_DIR}/notify.conf" <<EOF
# Phase A.4.b — notify on failure (cf ADR-030 + ROADMAP_2026-05-06)
# Idempotent drop-in. Safe to delete: just rm this file + daemon-reload.
[Unit]
OnFailure=ichor-notify@%n.service
EOF
    echo "  ✓ $u"
done

systemctl daemon-reload

echo
echo "=== Done. ${#UNITS[@]} units now notify on failure. ==="
echo "Verify with: systemctl cat <unit> --no-pager | grep -A1 OnFailure"
