#!/usr/bin/env bash
# Ichor — run the Ansible playbook from the Hetzner server itself
# (because Ansible control node doesn't run on native Windows — see ADR-007)
#
# Usage:
#   scripts/run-ansible-on-hetzner.sh                # full run
#   scripts/run-ansible-on-hetzner.sh --check        # dry-run
#   scripts/run-ansible-on-hetzner.sh --tags postgres
#
# Forwards all flags to the remote ansible-playbook invocation.

set -euo pipefail

ICHOR_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SSH_HOST="ichor-hetzner"
REMOTE_DIR="/root/ansible"

ANSIBLE_FLAGS=("$@")
if [ ${#ANSIBLE_FLAGS[@]} -eq 0 ]; then
  ANSIBLE_FLAGS=(--diff)
fi

echo "=== Ichor Ansible bootstrap → $SSH_HOST ==="

# 1. Verify SSH works
ssh -o BatchMode=yes -o ConnectTimeout=10 "$SSH_HOST" "echo SSH_OK" >/dev/null

# 2. Ensure ansible-core installed on Hetzner (idempotent)
ssh "$SSH_HOST" 'bash -s' <<'BOOTSTRAP'
set -euo pipefail
if ! command -v ansible-playbook >/dev/null 2>&1; then
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ansible-core
fi
ansible --version | head -1
BOOTSTRAP

# 3. Sync playbook (exclude transient state)
echo "→ Syncing playbook to $SSH_HOST:$REMOTE_DIR ..."
rsync -avz --delete \
  --exclude '.ansible_facts_cache' \
  --exclude '*.retry' \
  --exclude '__pycache__' \
  "$ICHOR_ROOT/infra/ansible/" "$SSH_HOST:$REMOTE_DIR/"

# 4. Ensure required collections (idempotent; cached on server)
ssh "$SSH_HOST" "cd $REMOTE_DIR && ansible-galaxy collection install \
  community.general community.docker community.postgresql ansible.posix \
  --upgrade 2>&1 | tail -10"

# 5. Run playbook
echo "→ Running ansible-playbook ${ANSIBLE_FLAGS[*]} ..."
ssh -t "$SSH_HOST" "cd $REMOTE_DIR && ansible-playbook \
  -i 'localhost,' -c local site.yml ${ANSIBLE_FLAGS[*]}"

echo "=== Ansible run complete ==="
