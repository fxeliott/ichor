#!/usr/bin/env bash
# Ichor — local development setup script (Win11 Git Bash / Linux)
# Idempotent — safe to re-run.

set -euo pipefail

ICHOR_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ICHOR_ROOT"

echo "=== Ichor local dev setup ==="
echo "Repo root: $ICHOR_ROOT"
echo

# --- Check Node ---
if ! command -v node >/dev/null 2>&1; then
  echo "ERROR: Node not installed. Install Node 22 LTS from https://nodejs.org/"
  exit 1
fi
NODE_MAJOR=$(node --version | sed 's/v\([0-9]*\).*/\1/')
if [ "$NODE_MAJOR" -lt 22 ]; then
  echo "WARNING: Node $NODE_MAJOR detected, Ichor pins Node 22+. Consider upgrading."
fi
echo "✓ Node $(node --version)"

# --- Check pnpm ---
if ! command -v pnpm >/dev/null 2>&1; then
  echo "Installing pnpm via official installer..."
  if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
    powershell -Command "iwr https://get.pnpm.io/install.ps1 -useb | iex"
    export PATH="$HOME/AppData/Local/pnpm:$PATH"
  else
    curl -fsSL https://get.pnpm.io/install.sh | sh -
    export PATH="$HOME/.local/share/pnpm:$PATH"
  fi
fi
echo "✓ pnpm $(pnpm --version)"

# --- pnpm install ---
echo "Installing JS/TS workspace dependencies..."
pnpm install

# --- Optional: ansible-core in a tooling venv ---
if command -v python >/dev/null 2>&1; then
  PYTHON_VER=$(python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
  echo "✓ Python $PYTHON_VER"
  if [ ! -d ".venv-tooling" ]; then
    echo "Creating .venv-tooling for Ansible + dev scripts..."
    python -m venv .venv-tooling
  fi
  # shellcheck source=/dev/null
  if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
    source .venv-tooling/Scripts/activate
  else
    source .venv-tooling/bin/activate
  fi
  pip install --quiet --upgrade pip
  pip install --quiet ansible-core==2.18.1 ansible-lint==25.1.2
  ansible-galaxy collection install --quiet community.general community.docker community.postgresql ansible.posix
  deactivate
  echo "✓ ansible-core in .venv-tooling/"
fi

# --- SSH config sanity ---
if ! grep -q "ichor-hetzner" "$HOME/.ssh/config" 2>/dev/null; then
  echo "WARNING: SSH alias 'ichor-hetzner' not found in ~/.ssh/config"
  echo "         Run Phase 0 Week 1 step 2a to set up SSH access first."
fi

echo
echo "=== Setup complete ==="
echo
echo "Next steps:"
echo "  1. Activate ansible venv: source .venv-tooling/Scripts/activate (Win) or bin/activate (Linux)"
echo "  2. Test ansible: ansible -i infra/ansible/inventory/hetzner.yml ichor-prod -m ping"
echo "  3. Sanity-check playbook: ansible-playbook -i infra/ansible/inventory/hetzner.yml infra/ansible/site.yml --check --diff"
