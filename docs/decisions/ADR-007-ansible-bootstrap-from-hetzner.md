# ADR-007: Run Ansible from Hetzner itself, not from local Win11

- **Status**: Accepted
- **Date**: 2026-05-02
- **Decider**: Eliot (autonomy delegation)

## Context

`infra/ansible/site.yml` provisions Hetzner. The classical pattern is to run
the Ansible **control node** locally (Win11) targeting the **managed node**
(Hetzner) via SSH.

Verified 2026-05-02:

- **Ansible control node does not run on native Windows.** The `ansible.cli`
  module imports `os.get_blocking()` and `grp` (POSIX-only). Both fail with
  `WinError 87` / `ModuleNotFoundError` on Win11 (with Python 3.14.4).
  Source: tested `ansible-core==2.20.5` and `ansible-lint==26.4.0`, same
  failure.
- **WSL2 is not installed** on Eliot's Win11. Installation requires admin +
  reboot + ~10 min setup of an Ubuntu image — out of scope for an autonomous
  Phase 0 session.
- **No local Docker** either (could use `quay.io/ansible/ansible:latest`).

## Decision

Bootstrap Ansible **on the Hetzner server itself** during Phase 0 cleanup

- first run. The Ansible control node and managed node are the same machine,
  running against `localhost` via the local connection plugin.

Workflow:

```bash
# After chirurgical cleanup, from local Win11:
ssh ichor-hetzner "apt-get install -y ansible-core"

# Sync playbook to server
rsync -avz --delete --exclude '.ansible_facts_cache' \
  D:/Ichor/infra/ansible/ ichor-hetzner:/root/ansible/

# Install required collections
ssh ichor-hetzner "cd /root/ansible && ansible-galaxy collection install \
  community.general community.docker community.postgresql ansible.posix"

# Run playbook against localhost from inside the server
ssh ichor-hetzner "cd /root/ansible && ansible-playbook \
  -i 'localhost,' -c local site.yml --check --diff"

# Once dry-run looks good:
ssh ichor-hetzner "cd /root/ansible && ansible-playbook \
  -i 'localhost,' -c local site.yml"
```

A helper script lives at `scripts/run-ansible-on-hetzner.sh`.

## Consequences

### Pros

- **Zero local install needed** — no WSL2 admin install, no Docker dep, no
  Linux VM. Everything runs on the target where it'll stay.
- **Ansible can be added to a cron** on Hetzner later for self-healing
  (`ansible-pull` pattern).
- **Inventory simplified** — `-i 'localhost,'` instead of dealing with SSH
  delegation across the network. No SSH-from-control-to-managed latency.
- **Apt is faster on the server** (datacenter network) than `become: true`
  - apt over SSH from Win11 residential.

### Cons

- **`rsync` step required** every time the playbook changes. Mitigation:
  the helper script wraps it.
- **Loses the convention** "your laptop is the source of truth, the server
  is a cattle". Mitigation: Git on the laptop is still the source of truth;
  rsync is just the deployment medium (analogous to a CI deploy step).
- **No `--check` against multiple hosts** in parallel (we have only one
  Hetzner box anyway, so moot).

## Alternatives considered

- **Install WSL2 + Ubuntu** — rejected for Phase 0 day 1 (admin + reboot +
  user-attended setup). Will revisit if Eliot wants a multi-host ops
  workflow later.
- **Run Ansible in Docker locally** — rejected: Docker not installed on
  Win11, and adding it just for this is overkill (also needs admin).
- **Add a small Linux jump-box** (free Oracle Cloud / fly.io machine) —
  rejected: extra dep, extra surface, not justified for one target host.
- **GitHub Actions runs Ansible against Hetzner** — rejected for Phase 0:
  needs SSH key in GHA secrets, network round-trips, and we're not yet at
  the CI/CD-driven-ops stage. Will revisit Phase 1+ once `ichor-prod`
  workspace API key + SOPS are in place.

## References

- Ansible support matrix: https://docs.ansible.com/ansible/latest/installation_guide/installation_distros.html#windows
- Test traceback (saved internally to PHASE_0_LOG.md day-1)
- `scripts/run-ansible-on-hetzner.sh` — implementation
