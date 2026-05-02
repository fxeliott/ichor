# RUNBOOK-001: Hetzner host down (no SSH, no HTTPS)

- **Severity**: P0 (service down — no briefings, no dashboard)
- **Last reviewed**: 2026-05-02
- **Time to resolve (target)**: 15 min via snapshot rollback / 60 min via fresh rebuild

## Trigger

- `ssh ichor-hetzner` returns "Connection timed out" or "Connection refused"
- Cloudflare Pages dashboard shows API errors (api.ichor → 502)
- Grafana alert `ichor.hetzner.unreachable` fires (ICMP+TCP probes from a 2nd Cloudflare worker)

## Immediate actions (first 5 min)

1. **Confirm scope** — is it just SSH, or full host?
   ```bash
   curl -sIo /dev/null -w "%{http_code}\n" https://178.104.39.201:443 --max-time 5
   ping -c 3 178.104.39.201
   ```
2. **Check Hetzner Cloud status** — https://status.hetzner.com
   If a region-wide outage at NBG1 is declared → wait, no action needed (Hetzner SLA is 99.9% monthly).
3. **Check Hetzner Console** — https://console.hetzner.cloud
   → server card status. If "Off" or "Migrating" → click Power On / wait.

## Diagnosis

### A. Server marked "Off" in Hetzner Cloud

- Most likely cause: someone (Eliot via console, or auto-shutdown after max-budget)
  pressed Power Off.
- **Fix**: click "Power On" in console. Boot takes ~60s.

### B. Server marked "Running" but no SSH

- DNS issue (ours doesn't matter — IP-based) or SSH daemon down.
- Try **Hetzner Console → server → Console** (web KVM). If you can log in, run:
  ```bash
  systemctl status ssh
  systemctl restart ssh
  journalctl -u ssh --since "10 minutes ago" | tail -30
  ufw status
  ```
- If UFW is blocking 22 (e.g., we accidentally pushed a bad rule):
  ```bash
  ufw allow 22/tcp
  ufw reload
  ```

### C. Disk full / I/O hung

- Web console may also hang. Try `df -h` and `iostat`.
- If `/var/log` is the culprit (often is): `journalctl --vacuum-size=500M`

### D. Hardware failure / disk corruption

- Hetzner ticket required. Submit via console → Support → Create Ticket.
- **Restore from snapshot** while ticket pends (see below).

## Recovery — restore from snapshot

If we have a recent snapshot in Hetzner Cloud:

1. Hetzner Console → server → **Snapshots** tab → identify latest known-good
2. Click **Rebuild** → choose snapshot
3. Wait ~5 min for rebuild
4. SSH in:
   ```bash
   ssh ichor-hetzner uptime
   systemctl status postgresql redis-server docker fail2ban
   docker ps
   ```
5. **Verify wal-g** can still see R2:
   ```bash
   sudo -u postgres bash -c 'set -a; source /etc/wal-g.env; set +a; wal-g backup-list'
   ```
   Should list backups (empty list = R2 unreachable, separate runbook).

## Recovery — fresh rebuild (snapshot too old or corrupted)

1. Hetzner Console → server → **Rebuild** → Ubuntu 24.04
2. Re-add SSH key during rebuild (Cloud SSH Keys → ED25519 `ichor-ed25519-eliot-win11-2026-05-02`)
3. Wait ~5 min for boot
4. Bootstrap Ansible from local Win11:
   ```bash
   bash scripts/run-ansible-on-hetzner.sh
   ```
5. **Restore Postgres from R2** (wal-g):
   ```bash
   ssh ichor-hetzner
   sudo systemctl stop postgresql
   sudo -u postgres bash -c 'set -a; source /etc/wal-g.env; set +a; wal-g backup-fetch /var/lib/postgresql/16/main LATEST'
   sudo -u postgres touch /var/lib/postgresql/16/main/recovery.signal
   sudo systemctl start postgresql
   # Verify recovery completed
   sudo -u postgres psql -c "SELECT pg_is_in_recovery();"
   ```

## Post-incident

- **Update incident log** in `docs/incidents/YYYY-MM-DD-hetzner-down.md`
- **File post-mortem** if downtime > 15 min (template in `docs/incidents/POSTMORTEM_TEMPLATE.md`)
- **Update this runbook** if a step was missing, wrong, or surprising
- If snapshot was used: **schedule a fresh snapshot the next quiet hour**
- If full rebuild was needed: **verify that walg basebackup completed within 24h** to catch up the WAL chain
