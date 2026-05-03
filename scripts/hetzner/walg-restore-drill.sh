#!/usr/bin/env bash
# WAL-G restore drill — option B (in-place dry-run, see RUNBOOK-010).
#
# Fetches the LATEST basebackup into a tmp directory and validates its
# structure. Does NOT touch production PGDATA. Safe to run on the live
# server.
#
# Usage:
#   sudo bash scripts/hetzner/walg-restore-drill.sh
#
# Exit codes:
#   0 — drill passed
#   1 — pre-flight failure (missing wal-g, env, etc.)
#   2 — restore failed (network, perms, R2 down)
#   3 — restored data structure invalid

set -euo pipefail

DRILL_DIR="${DRILL_DIR:-/tmp/walg-drill-$(date +%Y%m%d-%H%M%S)}"
ENV_FILE="${ENV_FILE:-/etc/wal-g.env}"
LOG_FILE="${LOG_FILE:-/tmp/walg-drill-$(date +%Y%m%d-%H%M%S).log}"

log() { printf '[%s] %s\n' "$(date -Iseconds)" "$*" | tee -a "$LOG_FILE"; }
fail() { log "FAIL: $*"; exit "${2:-1}"; }

# ──────────────────── pre-flight ────────────────────

log "WAL-G restore drill starting (DRILL_DIR=$DRILL_DIR)"

command -v wal-g >/dev/null || fail "wal-g not in PATH" 1
[[ -f "$ENV_FILE" ]] || fail "env file $ENV_FILE missing" 1
id postgres >/dev/null || fail "postgres user missing" 1

mkdir -p "$DRILL_DIR/pgdata"
chown postgres:postgres "$DRILL_DIR/pgdata"
chmod 700 "$DRILL_DIR/pgdata"

# ──────────────────── list backups ────────────────────

log "Listing backups available in R2..."
sudo -u postgres bash -c "set -a; source $ENV_FILE; set +a; wal-g backup-list" \
  | tee -a "$LOG_FILE" \
  || fail "backup-list failed (R2 unreachable or auth error)" 2

# ──────────────────── fetch ────────────────────

START_TS=$(date +%s)
log "Fetching LATEST basebackup into $DRILL_DIR/pgdata..."
sudo -u postgres bash -c "
  set -a; source $ENV_FILE; set +a
  wal-g backup-fetch '$DRILL_DIR/pgdata' LATEST
" 2>&1 | tee -a "$LOG_FILE" \
  || fail "backup-fetch failed" 2
END_TS=$(date +%s)
RESTORE_S=$((END_TS - START_TS))

log "Restore completed in ${RESTORE_S}s"

# ──────────────────── validate structure ────────────────────

REQUIRED=(
  "PG_VERSION"
  "base"
  "global"
  "pg_wal"
  "pg_xact"
  "postgresql.auto.conf"
)

for path in "${REQUIRED[@]}"; do
  if [[ ! -e "$DRILL_DIR/pgdata/$path" ]]; then
    fail "restored PGDATA missing required entry: $path" 3
  fi
done

PG_VER=$(cat "$DRILL_DIR/pgdata/PG_VERSION")
log "PG_VERSION=$PG_VER (expected 16)"
[[ "$PG_VER" == "16" ]] || fail "unexpected Postgres version: $PG_VER" 3

# ──────────────────── size report ────────────────────

SIZE_BYTES=$(du -sb "$DRILL_DIR/pgdata" | awk '{print $1}')
SIZE_MB=$((SIZE_BYTES / 1024 / 1024))
log "Restored size: ${SIZE_MB} MB"

# ──────────────────── cleanup ────────────────────

if [[ "${KEEP_DRILL:-0}" != "1" ]]; then
  log "Cleaning up $DRILL_DIR (set KEEP_DRILL=1 to retain)"
  rm -rf "$DRILL_DIR"
else
  log "Keeping $DRILL_DIR for inspection"
fi

# ──────────────────── summary ────────────────────

cat <<SUMMARY | tee -a "$LOG_FILE"

=========================================================
WAL-G drill PASSED
=========================================================
Restore duration : ${RESTORE_S}s
Restored size    : ${SIZE_MB} MB
PG version       : $PG_VER
Log              : $LOG_FILE

Next: file a quarterly DR record under docs/dr-tests/.
SUMMARY
