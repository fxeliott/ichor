# WAL-G drill — 2026 Q2

- **Drill date**: 2026-05-03 14:40 Europe/Paris
- **Operator**: autonomous (Claude Code session, executed via `walg-restore-drill.sh`)
- **Method**: B (in-place dry-run on production server, no PGDATA touched)
- **Latest basebackup at drill start**: `base_000000010000000000000027_D_000000010000000000000006` (delta backup based off `base_000000010000000000000006`)

## Result

**PASSED** — full pipeline R2 → wal-g → restored PGDATA structure validated.

| Metric | Value |
|---|---|
| Restore duration (network + extract) | **5 s** |
| Restored size | 34 MB |
| PG version detected | 16 |
| Total RTO (drill scope) | < 10 s |

## Verifications

```
PG_VERSION=16   (expected 16)         OK
PGDATA structure: PG_VERSION + base + global + pg_wal + pg_xact + postgresql.auto.conf  OK
Backup extraction complete (delta walked back to base + replayed)               OK
Cleanup of /tmp/walg-drill-* successful                                         OK
```

## Notes

- The current backup chain is two-deep: a delta off the LSN-6 base, fetched via
  `wal-g backup-fetch LATEST`. wal-g handled the chain transparently.
- Total uncompressed PGDATA is 34 MB — minimal because Phase 0 has very little
  user data yet (3 briefings + 8 alerts + 384 bias_signals).
- This is the in-place dry-run (option B). Quarterly cadence going forward
  should still rotate to option A (throwaway VM) at least once a year to
  exercise the Postgres-start path end-to-end.

## Action items

- None — DR plan validated for the current data shape.
- Next drill scheduled: 2026-Q3 (sept 2026, first Sunday).

## Log

Saved to `/tmp/walg-drill-20260503-144031.log` on Hetzner. Contents inlined
above.
