# `phase0-artifacts/` — Phase 0 server-side artifacts

Files captured during Phase 0 setup for traceability and recovery.

## Files

| File | Committed? | Description |
|------|------------|-------------|
| `hetzner-audit-pre-wipe-2026-05-02.txt` | ✅ yes | Read-only audit of Hetzner server before any change. 551 lines covering OS, disks, firewall, services, packages, processes. Useful for later diff. |
| `pre-cleanup-backup-2026-05-02.tar.gz` | ❌ **NO** | 154 KB tarball containing `/etc/ssh/` (incl. **server host private keys**), `/etc/ufw`, `/etc/fail2ban`, `/etc/sudoers.d`, `/root/.ssh`, apt/snap manifests. Local-only — kept for Phase 0 rollback. **Never commit.** |
| `pre-cleanup-backup-2026-05-02.tar.gz.sha256` | ❌ no | Checksum of the tarball. Local-only. |

The tarball + checksum are excluded via `phase0-artifacts/.gitignore`.

## Restore from tarball

If a Phase 0 step breaks the server beyond easy fix and the Hetzner Cloud
snapshot is also unavailable:

```bash
# From local Win11 Git Bash (after re-establishing some kind of SSH access)
scp phase0-artifacts/pre-cleanup-backup-2026-05-02.tar.gz ichor-hetzner:/tmp/
ssh ichor-hetzner "cd / && tar -xzf /tmp/pre-cleanup-backup-2026-05-02.tar.gz \
  --strip-components=1 -C /etc"
```

The Hetzner Cloud snapshot is the **first-line recovery**. This tarball is
defense-in-depth in case the snapshot itself fails.
