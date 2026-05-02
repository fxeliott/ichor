# RUNBOOK-002: SSH key compromise / forced rotation

- **Severity**: P1 (potential active intrusion)
- **Last reviewed**: 2026-05-02
- **Time to resolve (target)**: 10 min

## Trigger

- Suspect that one of the SSH keys (Eliot's local ED25519, vault RSA legacy)
  has leaked
- New unfamiliar entry in `/root/.ssh/authorized_keys`
- fail2ban shows successful auth from unexpected IP in `journalctl -u ssh`
- Lost the laptop holding `~/.ssh/id_ed25519_ichor_hetzner`

## Immediate actions (first 5 min)

1. **From Win11**, generate a NEW key (don't reuse the suspect one):
   ```powershell
   ssh-keygen -t ed25519 -C "ichor-hetzner-rotation-$(Get-Date -Format yyyy-MM-dd)" -f $env:USERPROFILE\.ssh\id_ed25519_ichor_hetzner_new -N ""
   icacls "$env:USERPROFILE\.ssh\id_ed25519_ichor_hetzner_new" /inheritance:r /grant:r "${env:USERNAME}:F"
   ```
2. **Get the public key**:
   ```powershell
   Get-Content "$env:USERPROFILE\.ssh\id_ed25519_ichor_hetzner_new.pub"
   ```

## Recovery (preferred path — old key still works)

3. SSH in with the OLD key (last time we use it):
   ```bash
   ssh -i ~/.ssh/id_ed25519_ichor_hetzner ichor-hetzner
   ```
4. Replace authorized_keys atomically:
   ```bash
   cat > /root/.ssh/authorized_keys.new <<'EOF'
   ssh-ed25519 AAAA<NEW_PUB_KEY> ichor-hetzner-rotation-...
   EOF
   chmod 600 /root/.ssh/authorized_keys.new
   mv /root/.ssh/authorized_keys.new /root/.ssh/authorized_keys
   ```
5. **From a NEW PowerShell**, test the new key works:
   ```bash
   ssh -i ~/.ssh/id_ed25519_ichor_hetzner_new root@178.104.39.201 echo NEW_KEY_OK
   ```
6. If ✓, replace the old key file:
   ```powershell
   Remove-Item "$env:USERPROFILE\.ssh\id_ed25519_ichor_hetzner"
   Move-Item "$env:USERPROFILE\.ssh\id_ed25519_ichor_hetzner_new" "$env:USERPROFILE\.ssh\id_ed25519_ichor_hetzner"
   Move-Item "$env:USERPROFILE\.ssh\id_ed25519_ichor_hetzner_new.pub" "$env:USERPROFILE\.ssh\id_ed25519_ichor_hetzner.pub"
   ```

## Recovery (lost-laptop path — old key gone)

3. Hetzner Console → server → **Console** (web KVM, password-based root)
4. Log in as root with the password set in Hetzner Robot/Cloud (in `yone-secrets-vault`)
5. Replace authorized_keys with the new pubkey only
6. Test new key from Win11

## After rotation

- Update USB vault `yone-secrets-vault` with the new private key (keep an
  emergency offline backup)
- Update GitHub Actions deploy secret if it stored the old key
- Tell `cloudflared` it's safe to keep running — tunnel auth is independent of SSH
- **Rotate the Hetzner Cloud password too** (was used in the lost-laptop fallback)
- File an incident report if compromise was confirmed (not just suspected)

## Post-incident

- Update this runbook if any step was missing
- If compromise confirmed: full audit of `/var/log/auth.log` + Postgres queries +
  fail2ban banlist for the period since last known-good rotation
- Consider enabling Hetzner Cloud Firewall in addition to UFW
