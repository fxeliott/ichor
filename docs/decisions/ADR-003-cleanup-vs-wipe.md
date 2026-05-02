# ADR-003: Hetzner — chirurgical cleanup instead of full wipe

- **Status**: Accepted
- **Date**: 2026-05-02
- **Decider**: Eliot (validated 2026-05-02)

## Context

`docs/ARCHITECTURE_FINALE.md` Phase 0 Week 1 steps 2-3:
> 2. Backup Hetzner pre-wipe (Langfuse + n8n + /etc + clés)
> 3. Wipe + réinstall Ubuntu 24.04 LTS

Audit of Hetzner server `178.104.39.201` performed 2026-05-02 (full output:
[`phase0-artifacts/hetzner-audit-pre-wipe-2026-05-02.txt`](../../phase0-artifacts/hetzner-audit-pre-wipe-2026-05-02.txt)) revealed:

- **OS already on target version**: Ubuntu 24.04.4 LTS noble, kernel 6.8.0-101
- **Server quasi-empty**: `/dev/sda1` 8.9 GB used / 301 GB total (3% usage)
  - `/opt`, `/srv`, `/home` all empty
  - `/root` only has `.bashrc`, `.profile`, `.ssh`, `.cache`, `.bash_history` (1 byte)
- **Langfuse and n8n absent** (no Docker installed, no Postgres running).
  UFW rules referencing them (ports 5678, 3000, 18789, 8001, 8005, 16080) are
  orphans from a previous deployment that was uninstalled but not cleaned.
- **Existing useful state worth keeping**:
  - SSH config already hardened (`PermitRootLogin prohibit-password`,
    `PasswordAuthentication no`, `MaxAuthTries 3`)
  - fail2ban active (103 hours of IP banlist learned over 53 days uptime)
  - `cloudflared` already installed via apt (will be reused Phase 0 Week 3)
- **GUI bloat to remove**: `chromium-browser`, snap `chromium` (×2 versions),
  `gnome-46-2404`, `gtk-common-themes`, `mesa-2404`, snap `cups` (×2 versions)
  — useless on a headless server, total ~2 GB

## Decision

Replace step 3 ("wipe + réinstall") with **chirurgical cleanup** while
keeping the existing OS install:

1. **Hetzner Cloud snapshot** before any change (recovery 1-click, ~€0.09/mo
   for 8.9 GB during Phase 0)
2. **Backup tarball** of `/etc/{ufw,fail2ban,ssh,sudoers.d,cloud}` +
   `/root/.ssh` + apt manifests + UFW rules + systemd state to local
   `phase0-artifacts/` (done 2026-05-02, 154 KB, SHA256 verified)
3. **Purge GUI packages** (apt + snap): chromium-browser, snap chromium ×2,
   gnome-46-2404, gtk-common-themes, mesa-2404, snap cups ×2
4. **Reset UFW** to clean baseline: only 22/tcp (SSH limit), 80/tcp (LE
   challenges), 443/tcp (HTTPS public). All app services exposed via
   Cloudflare Tunnel only.
5. **Remove orphan sudoers** `/etc/sudoers.d/www-data-nginx-reload`
   (references nginx that no longer exists)
6. **Disable failed service** `cloud-init-hotplugd.service` (cosmetic only)
7. **Then run Ansible** `infra/ansible/site.yml` to bring the server to
   Phase 0 baseline

## Consequences

### Saved

- **30-60 min downtime** vs full wipe + Ansible
- **fail2ban learned banlist** preserved (53 days of attacker IPs)
- **SSH hardened state** preserved (Ansible's `security` role re-validates
  but doesn't break working config)
- **APT cache** (~233 MB) preserved → faster `apt install` during Ansible
- Existing `cloudflared` apt install preserved (saves a step in Week 3)

### Lost (acceptable)

- Some packages accumulated over time may persist in `apt-mark showmanual`
  even after our explicit purge list; we'll catch them in Week 2 via
  `apt list --installed` diff.
- `cloud-init` initial profile is preserved (could differ from a fresh
  Hetzner reinstall) — but harmless for our use case.

## Rollback

If anything breaks during cleanup or first Ansible run:

1. Hetzner Cloud Console → server → Snapshots → `ichor-pre-cleanup-2026-05-02`
   → "Restore" → confirm. Server reverts in ~5 min.
2. SSH still works via either ED25519 key (local) or RSA legacy (vault USB).

## Alternatives considered

- **Full wipe via Hetzner Rebuild → Ubuntu 24.04** (plan original) — rejected:
  ~30-60 min extra downtime for no concrete benefit since OS is already on
  target version and the server has no app data to lose.
- **Item-by-item validation before each purge** (Eliot offered this as a
  third option) — rejected: cleanup scope is small and fully documented; the
  snapshot covers rollback risk.

## References

- [`phase0-artifacts/hetzner-audit-pre-wipe-2026-05-02.txt`](../../phase0-artifacts/hetzner-audit-pre-wipe-2026-05-02.txt)
- [`phase0-artifacts/pre-cleanup-backup-2026-05-02.tar.gz`](../../phase0-artifacts/pre-cleanup-backup-2026-05-02.tar.gz) (SHA256 verified)
- `docs/ARCHITECTURE_FINALE.md` Phase 0 Week 1 step 3
