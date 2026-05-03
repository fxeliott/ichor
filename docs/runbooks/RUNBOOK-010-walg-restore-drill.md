# RUNBOOK-010: WAL-G restore drill (quarterly DR exercise)

- **Severity**: P3 (planned exercise — not a production incident)
- **Cadence**: Quarterly (Mar / Jun / Sep / Dec, 1st Sunday)
- **Time required**: 30-45 min
- **Last reviewed**: 2026-05-03

## Goal

Prove end-to-end that a wal-g basebackup + WAL chain stored in R2 EU can be
restored on a clean Postgres instance. Validates:

1. R2 credentials are still valid + bucket is reachable.
2. The latest basebackup is consistent (`wal-g backup-fetch` succeeds).
3. WAL replay reaches the latest archived position without errors.
4. Application data tables (briefings, alerts, predictions_audit, bias_signals)
   are present and readable.
5. RTO is within target (< 60 min for Phase 0).

A failed drill = silent failure of our DR plan. Better to find out now than
during a real incident.

## Pre-flight

```bash
# Confirm a recent backup exists
ssh ichor-hetzner '
  sudo -u postgres bash -c "set -a; source /etc/wal-g.env; set +a; wal-g backup-list"
'
# Should show LATEST < 8 days old
```

If no recent backup, first run a manual basebackup, then drill:

```bash
ssh ichor-hetzner '
  sudo systemctl start walg-basebackup.service
  journalctl -u walg-basebackup.service -f
'
```

## Drill — option A: spin up a throwaway Hetzner VM (preferred, isolated)

1. **Create a CX22 VM** (€4/mo prorated to drill duration) in Hetzner Console:
   - Image: Ubuntu 24.04 LTS
   - Region: eu-west (matches R2 EU)
   - SSH key: same as production
   - Name: `ichor-drill-$(date +%Y%m%d)`

2. **Bootstrap minimal Postgres + wal-g**:

   ```bash
   ssh root@<NEW_IP>
   apt update && apt install -y postgresql-16 postgresql-server-dev-16
   curl -fsSL https://github.com/wal-g/wal-g/releases/download/v3.0.8/wal-g-pg-24.04-amd64.tar.gz \
     | tar -xz -C /usr/local/bin/
   chmod +x /usr/local/bin/wal-g-pg-ubuntu-24.04-amd64
   ln -sf /usr/local/bin/wal-g-pg-ubuntu-24.04-amd64 /usr/local/bin/wal-g
   ```

3. **Copy `/etc/wal-g.env` from production** (sops-decrypted):

   ```bash
   # On laptop:
   sops -d infra/secrets/walg.env | ssh root@<NEW_IP> "cat > /etc/wal-g.env && chmod 600 /etc/wal-g.env"
   ```

4. **Stop fresh Postgres + wipe its empty PGDATA**:

   ```bash
   ssh root@<NEW_IP> '
     systemctl stop postgresql
     rm -rf /var/lib/postgresql/16/main/*
     chown postgres:postgres /var/lib/postgresql/16/main
     chmod 700 /var/lib/postgresql/16/main
   '
   ```

5. **Restore basebackup + recovery config**:

   ```bash
   ssh root@<NEW_IP> '
     sudo -u postgres bash -c "
       set -a; source /etc/wal-g.env; set +a
       wal-g backup-fetch /var/lib/postgresql/16/main LATEST
     "
     touch /var/lib/postgresql/16/main/recovery.signal
     chown postgres:postgres /var/lib/postgresql/16/main/recovery.signal

     cat >> /etc/postgresql/16/main/postgresql.conf <<EOF
   restore_command = '"'"'wal-g wal-fetch %f %p'"'"'
   recovery_target_timeline = '"'"'latest'"'"'
   EOF
   '
   ```

6. **Start Postgres + watch recovery**:

   ```bash
   ssh root@<NEW_IP> 'systemctl start postgresql && tail -f /var/log/postgresql/postgresql-16-main.log'
   ```

   Wait for:

   ```
   LOG:  archive recovery complete
   LOG:  database system is ready to accept connections
   ```

7. **Validate data tables**:

   ```bash
   ssh root@<NEW_IP> '
     sudo -u postgres psql -d ichor <<SQL
   SELECT pg_is_in_recovery();
   SELECT count(*) AS briefings_count, max(triggered_at) AS last_briefing FROM briefings;
   SELECT count(*) AS alerts_count FROM alerts;
   SELECT count(*) AS bias_count FROM bias_signals;
   SELECT count(*) AS predictions_count FROM predictions_audit;
   SQL
   '
   ```

   **Acceptance**: all counts > 0 (or matching production within the WAL
   archive lag), `pg_is_in_recovery() = f`.

8. **Destroy the drill VM** in Hetzner Console (saves €).

## Drill — option B: in-place dry-run (cheaper, less isolated)

Useful only if budget forbids the throwaway VM. Risk: if you typo a path, you
overwrite production. **Always pair with a Hetzner snapshot beforehand.**

1. Take Hetzner snapshot: Console → ichor-prod → Snapshots → Take snapshot
2. On production:

   ```bash
   sudo -u postgres bash -c '
     set -a; source /etc/wal-g.env; set +a
     mkdir -p /tmp/walg-drill && cd /tmp/walg-drill
     wal-g backup-fetch ./pgdata LATEST
     ls -la ./pgdata
   '
   ```

3. Verify the directory structure (`base/`, `pg_wal/`, `PG_VERSION`).
4. Delete `/tmp/walg-drill` immediately after.
5. Document: total bytes restored, time elapsed.

## Recording

Save results in `docs/dr-tests/YYYY-Qn-walg-drill.md` with:

```markdown
# WAL-G drill — YYYY-Qn

- Drill date: YYYY-MM-DD
- Operator: Eliot
- Method: A (throwaway VM) | B (in-place dry-run)
- Latest basebackup age at drill start: Xh
- Restore duration: X min Y s
- WAL replay duration: X min Y s
- Total RTO: X min
- Verifications passed: yes/no (paste SQL output)
- Issues encountered: …
- Action items: …
```

## Failure modes + recovery

| Symptom | Likely cause | Action |
|---|---|---|
| `wal-g backup-fetch` 403 | R2 keys revoked | Rotate via SOPS, re-encrypt, redeploy |
| `wal-g backup-fetch` 404 LATEST | No backup exists | Trigger `walg-basebackup.service`, retry |
| WAL replay stuck on missing WAL | Gap in archive | Find last good WAL, restore to that point with `recovery_target_lsn` |
| Postgres won't start after fetch | Permissions | `chown -R postgres:postgres /var/lib/postgresql/16/main && chmod 700 .` |
| Data tables empty | Restored older basebackup before tables existed | Pick newer basebackup with `wal-g backup-fetch ... <BACKUP_NAME>` |

## Cost

- Option A (throwaway CX22 VM): ~€0.10 per drill (15-min prorated)
- Option B (in-place): €0
- R2 egress: ~7 GB Phase 0 = $0 (under 10 GB free tier monthly)
