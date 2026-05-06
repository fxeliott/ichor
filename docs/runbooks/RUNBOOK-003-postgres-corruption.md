# RUNBOOK-003: Postgres corruption / restore from wal-g R2 backup

- **Severity**: P0 (data layer down — all briefings + alerts blocked)
- **Last reviewed**: 2026-05-02
- **Time to resolve (target)**: 30-60 min depending on database size

## Trigger

- Postgres won't start: `journalctl -u postgresql --since "10 min"` shows
  `PANIC: database "ichor" cannot be opened`, or
  `FATAL: corrupted item pointer`, or
  `WARNING: page is not initialized`
- Disk inconsistency after sudden power loss / Hetzner host migration
- Filesystem errors in `dmesg`

## Immediate actions (first 5 min)

1. **Stop Postgres** to prevent further damage:
   ```bash
   ssh ichor-hetzner
   sudo systemctl stop postgresql
   ```
2. **Check Hetzner Cloud snapshot age**:
   - Hetzner Console → server → Snapshots
   - If a snapshot < 24h old exists: rollback is faster than wal-g restore
3. **Confirm wal-g R2 backups are intact**:
   ```bash
   sudo -u postgres bash -c 'set -a; source /etc/wal-g.env; set +a; wal-g backup-list'
   # Should list ≥ 1 backup, latest within last 24-48h
   ```

## Recovery — wal-g full restore (preferred for data-loss scenarios)

1. Move corrupted PGDATA aside:

   ```bash
   sudo mv /var/lib/postgresql/16/main /var/lib/postgresql/16/main.corrupted-$(date +%Y%m%d-%H%M)
   sudo -u postgres mkdir /var/lib/postgresql/16/main
   sudo chmod 700 /var/lib/postgresql/16/main
   ```

2. **Fetch latest basebackup from R2**:

   ```bash
   sudo -u postgres bash -c '
     set -a; source /etc/wal-g.env; set +a
     wal-g backup-fetch /var/lib/postgresql/16/main LATEST
   '
   ```

3. **Configure recovery target** — full point-in-time restore (latest WAL):

   ```bash
   cat > /var/lib/postgresql/16/main/recovery.signal <<EOF
   EOF
   # Add restore_command to postgresql.conf
   sudo -u postgres tee -a /etc/postgresql/16/main/conf.d/recovery.conf <<EOF
   restore_command = 'wal-g wal-fetch %f %p'
   recovery_target_timeline = 'latest'
   EOF
   ```

4. **Start Postgres** (will replay WAL from R2 until latest):

   ```bash
   sudo systemctl start postgresql
   ```

5. **Watch the recovery progress** (this is the tense moment):

   ```bash
   sudo tail -f /var/lib/postgresql/16/main/log/postgresql-*.log
   ```

   Look for:

   ```
   LOG:  starting archive recovery
   LOG:  restored log file "..." from archive
   ...
   LOG:  archive recovery complete
   LOG:  database system is ready to accept connections
   ```

6. **Verify integrity**:

   ```bash
   sudo -u postgres psql -d ichor <<SQL
   SELECT pg_is_in_recovery();   -- should be 'f'
   SELECT count(*) FROM briefings;
   SELECT max(triggered_at) FROM briefings;
   SELECT count(*) FROM alerts;
   SELECT count(*) FROM session_card_audit;  -- renamed from predictions_audit by ADR-017
   SQL
   ```

7. **Re-enable WAL archiving** (it was paused during recovery):
   ```bash
   sudo systemctl restart postgresql
   # Wait 60s, then verify
   sudo -u postgres bash -c 'set -a; source /etc/wal-g.env; set +a; wal-g wal-show'
   ```

## Recovery — Hetzner Cloud snapshot (faster but loses recent WAL)

1. Hetzner Console → server → Snapshots → Rebuild from snapshot
2. Wait ~5 min
3. After boot:
   ```bash
   sudo -u postgres psql -c "SELECT max(triggered_at) FROM briefings;"
   # Note the gap between this timestamp and "now" — that's the data loss
   ```
4. **No WAL replay needed** — snapshot is a consistent state.
5. Optional: replay the WAL between the snapshot timestamp and now via
   wal-g (advanced; usually not worth it for Phase 0).

## Post-incident

- Move `main.corrupted-*` to `/tmp` after a week (don't keep on production disk)
- File post-mortem if downtime > 30 min
- Run a **scheduled wal-g restore drill** quarterly:
  ```bash
  # On a separate test VM, fetch a backup and verify it boots
  # Document in docs/dr-tests/YYYY-Qn.md
  ```
- If corruption recurs: bad disk, request Hetzner hardware replacement
