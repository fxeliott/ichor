#!/usr/bin/env bash
# notify-failure.sh — invoked by `ichor-notify@%i.service` when any
# ichor-*.service fires `OnFailure=ichor-notify@%n.service` (cf ADR-030 / A.4.b).
#
# Argument: $1 = full unit name that failed (e.g. ichor-rr25-check.service)
#
# Output paths:
#   1. journalctl   — priority=err, tagged "ichor-failure"
#   2. /var/log/ichor-failures.log — append-only record (tail-friendly)
#   3. ntfy webhook (optional) — if /etc/ichor/ntfy.env exists with NTFY_TOPIC,
#      posts a JSON message. Failure is silent (notification is a nice-to-have).

set -euo pipefail

UNIT="${1:-unknown.service}"
TS="$(date -Is)"
LOG_FILE="/var/log/ichor-failures.log"
NTFY_ENV="/etc/ichor/ntfy.env"

# Last 30 lines of the failed unit's journal — concise, fits in a notification
LAST_LINES=$(journalctl -u "$UNIT" -n 30 --no-pager 2>/dev/null | tail -10 || echo "(no journal lines available)")

# 1) journal at err priority — visible in `journalctl -p err`
logger -p user.err -t ichor-failure "unit=$UNIT failed at $TS"

# 2) append-only log
{
    echo "===== $TS — UNIT FAIL: $UNIT ====="
    echo "$LAST_LINES"
    echo
} >> "$LOG_FILE" 2>/dev/null || true

# 3) optional ntfy webhook
if [ -f "$NTFY_ENV" ]; then
    # shellcheck disable=SC1090
    . "$NTFY_ENV"
    if [ -n "${NTFY_TOPIC:-}" ]; then
        BODY=$(printf '{"topic":"%s","title":"Ichor unit fail","message":"%s\\n%s","priority":4,"tags":["warning","robot"]}' \
            "$NTFY_TOPIC" "$UNIT" "$(echo "$LAST_LINES" | tr '\n' ' ' | head -c 400 | sed 's/"/\\"/g')")
        curl -sS -m 5 -X POST -H "Content-Type: application/json" -d "$BODY" \
            "${NTFY_URL:-https://ntfy.sh}" > /dev/null 2>&1 || true
    fi
fi

exit 0
