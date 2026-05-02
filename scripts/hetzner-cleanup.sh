#!/usr/bin/env bash
# Ichor — Hetzner chirurgical cleanup (per ADR-003)
# Run AFTER:
#   1. backup tarball downloaded locally (DONE 2026-05-02 — 154 KB SHA256 verified)
#   2. Hetzner Cloud snapshot taken via console.hetzner.cloud
#
# This script SSHes into Hetzner and:
#   - Purges desktop/GUI packages (apt + snap)
#   - Resets UFW to baseline (22 limit + 80 + 443 only)
#   - Removes orphan sudoers (www-data-nginx-reload)
#   - Disables failed cloud-init-hotplugd service
#   - Verifies SSH still works after changes
#
# Idempotent: safe to re-run.

set -euo pipefail

SSH_HOST="${SSH_HOST:-ichor-hetzner}"

echo "=== Ichor Hetzner cleanup ==="
echo "Target: $SSH_HOST"
echo

# Pre-flight: SSH connectivity + verify snapshot exists is up to user
ssh -o BatchMode=yes -o ConnectTimeout=10 "$SSH_HOST" "echo SSH_PRECHECK_OK" >/dev/null

read -r -p "Hetzner Cloud snapshot is taken? [yes/NO] " confirm
if [[ "$confirm" != "yes" ]]; then
  echo "Aborted. Take the snapshot first via console.hetzner.cloud."
  exit 1
fi

ssh "$SSH_HOST" 'bash -s' <<'CLEANUP'
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

echo "--- BEFORE: disk usage + package count ---"
df -h / | tail -1
echo "apt installed: $(dpkg --get-selections | grep -v deinstall | wc -l)"
echo "snap installed: $(snap list 2>/dev/null | tail -n +2 | wc -l)"
echo

# 1. Purge GUI / desktop apt packages
echo "--- step 1/5: apt purge GUI ---"
apt-get purge -y --auto-remove \
  chromium-browser \
  chromium-codecs-ffmpeg-extra 2>/dev/null || true

# 2. Remove desktop/GUI snaps
echo "--- step 2/5: snap remove desktop ---"
for snap_name in chromium gnome-46-2404 gtk-common-themes mesa-2404 cups; do
  if snap list "$snap_name" >/dev/null 2>&1; then
    echo "removing snap: $snap_name"
    snap remove --purge "$snap_name" || true
  fi
done

# Cleanup snap cache
rm -rf /var/lib/snapd/cache/* 2>/dev/null || true

# 3. apt autoremove + clean
echo "--- step 3/5: apt autoremove + clean ---"
apt-get autoremove -y --purge
apt-get clean

# 4. Reset UFW to clean baseline
echo "--- step 4/5: UFW reset ---"
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw default deny routed
ufw limit 22/tcp comment 'SSH (rate-limited)'
ufw allow 80/tcp comment 'HTTP (Lets Encrypt challenges)'
ufw allow 443/tcp comment 'HTTPS public'
ufw --force enable
echo
ufw status verbose

# 5. Cleanup orphan sudoers + failed services
echo "--- step 5/5: orphans ---"
if [ -f /etc/sudoers.d/www-data-nginx-reload ]; then
  rm -f /etc/sudoers.d/www-data-nginx-reload
  echo "removed orphan: /etc/sudoers.d/www-data-nginx-reload"
fi

systemctl disable --now cloud-init-hotplugd.service 2>/dev/null || true
systemctl reset-failed

echo
echo "--- AFTER: disk usage + package count ---"
df -h / | tail -1
echo "apt installed: $(dpkg --get-selections | grep -v deinstall | wc -l)"
echo "snap installed: $(snap list 2>/dev/null | tail -n +2 | wc -l)"
echo "fail2ban: $(systemctl is-active fail2ban)"
echo "ssh: $(systemctl is-active ssh)"
echo "ufw: $(systemctl is-active ufw)"
CLEANUP

echo
echo "--- post-cleanup: re-test SSH from local ---"
ssh -o BatchMode=yes -o ConnectTimeout=10 "$SSH_HOST" "echo SSH_POSTCHECK_OK; uname -r; uptime"

echo
echo "=== Cleanup complete ==="
echo "Next: scripts/run-ansible-on-hetzner.sh --check --diff"
