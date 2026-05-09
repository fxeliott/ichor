#!/bin/bash
# activate_myfxbook.sh — interactive activation helper for the Couche-2
# MyFXBook Community Outlook collector (Wave 77, ADR-074).
#
# Reads email + password interactively (never on command-line argv to
# keep them out of `ps` / shell history), writes them to
# /etc/ichor/api.env (mode 0640, owner ichor:ichor), restarts ichor-api,
# triggers the collector once, verifies a row was persisted.
#
# Usage:
#   sudo /opt/ichor/scripts/hetzner/activate_myfxbook.sh
#
# Pre-requisites :
#   1. Free signup at https://www.myfxbook.com (already done if you
#      created an account via Google OAuth).
#   2. Set a LOCAL password at https://www.myfxbook.com/settings
#      (Google OAuth alone does NOT give you an API password — the
#      v1 API requires email + password classic credentials).
#
# Exit codes:
#   0 = activated + verified row persisted
#   1 = invalid input (empty email/password, etc.)
#   2 = env.write failed
#   3 = systemctl restart failed
#   4 = collector run did not produce any row (likely wrong creds —
#       check https://www.myfxbook.com/settings password is set)

set -euo pipefail

ENV_FILE=/etc/ichor/api.env
ENV_BACKUP="/etc/ichor/api.env.bak.$(date +%s)"
SERVICE=ichor-collector@myfxbook_outlook.service

echo "=== MyFXBook collector activation (W77 / ADR-074) ==="
echo

# ── Pre-checks ───────────────────────────────────────────────────
if [[ "$(id -u)" -ne 0 ]]; then
  echo "ERROR: this script must run as root (use sudo)." >&2
  exit 1
fi
if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE not found. Is ichor_api role provisioned?" >&2
  exit 1
fi

# ── Read credentials interactively ──────────────────────────────
read -r -p "MyFXBook email: " EMAIL
if [[ -z "$EMAIL" ]]; then
  echo "ERROR: empty email." >&2
  exit 1
fi
read -r -s -p "MyFXBook password (will not echo): " PASSWORD
echo
if [[ -z "$PASSWORD" ]]; then
  echo "ERROR: empty password." >&2
  exit 1
fi

# Strict trim of trailing whitespace / newlines
EMAIL="${EMAIL%[$'\r\n\t ']*}"
PASSWORD="${PASSWORD%[$'\r\n\t ']*}"

# ── Backup the env file ─────────────────────────────────────────
cp -p "$ENV_FILE" "$ENV_BACKUP"
echo "Backup: $ENV_BACKUP"

# ── Update env file idempotently ─────────────────────────────────
# Strategy: remove any existing ICHOR_API_MYFXBOOK_* lines, then append.
# Use a tmpfile + atomic mv to avoid partial writes.
TMP="$(mktemp -p /etc/ichor/ .api.env.tmp.XXXX)"
chmod 0640 "$TMP"
chown ichor:ichor "$TMP"

grep -v '^ICHOR_API_MYFXBOOK_EMAIL=' "$ENV_FILE" \
  | grep -v '^ICHOR_API_MYFXBOOK_PASSWORD=' \
  > "$TMP" || true

# Append the new creds. Quote the password to allow special chars
# (escape any embedded double quotes for shell safety).
ESC_PWD="${PASSWORD//\"/\\\"}"
{
  echo "ICHOR_API_MYFXBOOK_EMAIL=$EMAIL"
  echo "ICHOR_API_MYFXBOOK_PASSWORD=\"$ESC_PWD\""
} >> "$TMP"

mv "$TMP" "$ENV_FILE"
chown ichor:ichor "$ENV_FILE"
chmod 0640 "$ENV_FILE"
echo "Updated $ENV_FILE (2 vars set)"

# ── Restart ichor-api so any cached env reloads ─────────────────
if ! systemctl restart ichor-api 2>&1; then
  echo "ERROR: failed to restart ichor-api. Check journalctl -u ichor-api" >&2
  echo "Restoring backup..." >&2
  cp -p "$ENV_BACKUP" "$ENV_FILE"
  exit 3
fi
sleep 4
if ! systemctl is-active --quiet ichor-api; then
  echo "ERROR: ichor-api failed to come back up after restart." >&2
  exit 3
fi
echo "ichor-api restarted OK"

# ── Trigger one collector run ───────────────────────────────────
echo "Triggering $SERVICE ..."
systemctl start "$SERVICE"
sleep 6
journalctl -u "$SERVICE" --since "30 sec ago" --no-pager 2>&1 \
  | tail -15

# ── Verify a row was persisted ─────────────────────────────────
echo
echo "=== Verification ==="
ROW_COUNT=$(sudo -u postgres psql ichor -tAc \
  "SELECT COUNT(*) FROM myfxbook_outlooks WHERE fetched_at >= now() - interval '5 minutes';" \
  2>/dev/null || echo 0)
ROW_COUNT="${ROW_COUNT// /}"

if [[ "$ROW_COUNT" -gt 0 ]]; then
  echo "✅ ${ROW_COUNT} myfxbook_outlooks rows persisted in the last 5 min."
  echo "Latest snapshot:"
  sudo -u postgres psql ichor -c \
    "SELECT pair, ROUND(long_pct::numeric, 1) AS long_pct, ROUND(short_pct::numeric, 1) AS short_pct, fetched_at FROM myfxbook_outlooks ORDER BY fetched_at DESC LIMIT 6;"
  echo
  echo "✅ MyFXBook collector ACTIVATED. Timer will fire every 4h."
  exit 0
else
  echo "❌ No rows persisted. Likely causes:"
  echo "   1. Password not set on MyFXBook account"
  echo "      → https://www.myfxbook.com/settings"
  echo "   2. Wrong email or password (check journalctl above for 'login_failed' or 'login_rejected')"
  echo
  echo "The env vars are still in place. Re-run this script after fixing creds."
  exit 4
fi
