# RUNBOOK-004: Cloudflare R2 unreachable / wal-g push failures

- **Severity**: P1 (Postgres still serves; backups stop accumulating)
- **Time to resolve (target)**: 15 min

## Trigger

- `wal-g backup-list` returns connection error
- `journalctl -u walg-basebackup` shows repeated "failed to upload"
- Postgres `archive_status/*.ready` files accumulate (never become `.done`)
- Cloudflare status page shows R2 incident

## Diagnosis

```bash
ssh ichor-hetzner
# Test bucket reachability
sudo -u postgres bash -c 'set -a; source /etc/wal-g.env; set +a; wal-g st check write'
# Check R2 dashboard
# https://dash.cloudflare.com → R2 → ichor-walg-eu → Metrics
```

## Recovery

### A. Cloudflare-side incident

- Wait. WAL files queue locally in `pg_wal/` — Postgres tolerates this for
  hours (default `max_wal_size = 1GB`). Monitor disk space.
- If disk pressure: `df -h /var/lib/postgresql`. Above 80% → consider
  detaching unused snapshots or temporarily disabling archive.

### B. Token revoked / rotated

- Check `infra/secrets/cloudflare.env` is current: `sops --decrypt ... | grep R2_`.
- If keys changed: regenerate API token in Cloudflare R2 dashboard, update env,
  re-encrypt, re-deploy.

### C. Bucket deleted

- DON'T panic. **Recreate the bucket with the same name** in Cloudflare R2.
- wal-g will start writing again; existing backups in the deleted bucket
  are gone (Cloudflare R2 doesn't soft-delete by default).
- Trigger a fresh basebackup immediately:
  ```bash
  sudo systemctl start walg-basebackup.service
  ```

## Post-incident

- Update runbook with the resolution path used
- If incident recurs: enable R2 versioning OR add a secondary backup target
  (B2, S3) for defense in depth (Phase 2+)
