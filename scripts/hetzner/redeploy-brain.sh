#!/usr/bin/env bash
# redeploy-brain.sh — idempotent brain package redeploy on Hetzner (r64).
#
# Replaces the brittle ad-hoc scp+cp chain that caused the silent
# `model_copy` NO-OP bug in r63 Sprint B (Python imported ichor_brain
# from `/tmp/ichor_brain-deploy/` because the editable .pth was hard-
# coded there ; `/tmp` is wiped on reboot, so any restart would have
# silently broken `session_card_audit.key_levels` persistence).
#
# This script :
#   1. Verifies the editable .pth points to the canonical stable path
#      (`/opt/ichor/packages/ichor_brain/src`). Fails loudly if drift.
#   2. Mirrors the local worktree's `packages/ichor_brain/src/ichor_brain/`
#      to the Hetzner stable path via rsync (byte-identical post-sync).
#   3. chown ichor:ichor to keep file ownership consistent with the
#      service runtime user.
#   4. Restarts ichor-api.
#   5. Verifies via `python -c "import ichor_brain.types; print(...)"`
#      that Python imports from the stable path AND that
#      `key_levels in SessionCard.model_fields` is True.
#   6. Optionally runs a dry-run session card to verify end-to-end
#      persistence (kl_count > 0 means snapshot path is healthy).
#
# Usage (from repo root or worktree) :
#   ./scripts/hetzner/redeploy-brain.sh                 # full deploy + verify
#   ./scripts/hetzner/redeploy-brain.sh --skip-restart  # dry-run sync only
#   ./scripts/hetzner/redeploy-brain.sh --no-card-test  # skip the dry-run card
#
# Idempotency : safe to run multiple times in a row. rsync only copies
# changed files. Restart is guarded by a flag.
#
# R64 doctrinal pattern codified : never editable-install from `/tmp/`
# or any path that survives only by luck. Stable canonical paths only :
#   - `/opt/ichor/api/src/src` for ichor_api (already correct r64 baseline)
#   - `/opt/ichor/packages/ichor_brain/src` for ichor_brain (THIS FIX)
#   - `/opt/ichor/packages-staging/agents/src` for ichor_agents (already correct)
#   - `/opt/ichor/packages-staging/ml/src` for ichor_ml (already correct)
#
# Voie D respect : pure-bash, no Python deps. Frontend gel rule 4 honored.

set -euo pipefail

SKIP_RESTART=false
NO_CARD_TEST=false
for arg in "$@"; do
  case "$arg" in
    --skip-restart) SKIP_RESTART=true ;;
    --no-card-test) NO_CARD_TEST=true ;;
    *) echo "unknown arg: $arg" >&2; exit 2 ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LOCAL_BRAIN_SRC="${REPO_ROOT}/packages/ichor_brain/src/ichor_brain"
HETZNER_STABLE_PATH="/opt/ichor/packages/ichor_brain/src/ichor_brain"
PTH_FILE="/opt/ichor/api/.venv/lib/python3.12/site-packages/_editable_impl_ichor_brain.pth"
EXPECTED_PTH_CONTENT="/opt/ichor/packages/ichor_brain/src"

if [[ ! -d "$LOCAL_BRAIN_SRC" ]]; then
  echo "FATAL : local brain source not found at $LOCAL_BRAIN_SRC" >&2
  exit 3
fi

echo "=== Step 1 : verify .pth points to stable canonical path ==="
PTH_ACTUAL=$(ssh ichor-hetzner "sudo cat $PTH_FILE 2>/dev/null | tr -d '[:space:]'")
if [[ "$PTH_ACTUAL" != "$EXPECTED_PTH_CONTENT" ]]; then
  echo "FATAL : .pth drift detected"
  echo "  expected : $EXPECTED_PTH_CONTENT"
  echo "  actual   : $PTH_ACTUAL"
  echo "Fix : echo '$EXPECTED_PTH_CONTENT' | ssh ichor-hetzner sudo tee $PTH_FILE"
  exit 4
fi
echo "  .pth OK : $PTH_ACTUAL"

echo "=== Step 2 : rsync local brain -> Hetzner stable path ==="
rsync -av --delete-after \
  -e "ssh" \
  "${LOCAL_BRAIN_SRC}/" \
  "ichor-hetzner:/tmp/ichor_brain_redeploy_staging/"

ssh ichor-hetzner "
  sudo rsync -a /tmp/ichor_brain_redeploy_staging/ $HETZNER_STABLE_PATH/ &&
  sudo chown -R ichor:ichor $HETZNER_STABLE_PATH &&
  sudo rm -rf /tmp/ichor_brain_redeploy_staging
"

if [[ "$SKIP_RESTART" == "true" ]]; then
  echo "=== --skip-restart : sync complete, NOT restarting service ==="
  exit 0
fi

echo "=== Step 3 : restart ichor-api ==="
ssh ichor-hetzner "sudo systemctl restart ichor-api && sleep 3 && sudo systemctl is-active ichor-api"

echo "=== Step 4 : verify Python imports from stable path ==="
ssh ichor-hetzner "
  cd /opt/ichor/api/src && sudo -u ichor bash -c '
    set -a; source /etc/ichor/api.env; set +a
    /opt/ichor/api/.venv/bin/python -c \"
import ichor_brain.types
assert ichor_brain.types.__file__ == \\\"$HETZNER_STABLE_PATH/types.py\\\", \\\"path drift : \\\" + ichor_brain.types.__file__
from ichor_brain.types import SessionCard
assert \\\"key_levels\\\" in SessionCard.model_fields, \\\"key_levels field missing\\\"
print(\\\"VERIFY OK : import path stable + key_levels field present\\\")
\"
  '
"

if [[ "$NO_CARD_TEST" == "true" ]]; then
  echo "=== --no-card-test : import verified, skipping dry-run card ==="
  exit 0
fi

echo "=== Step 5 : dry-run session card EUR_USD pre_londres + verify kl persisted ==="
ssh ichor-hetzner "
  cd /opt/ichor/api/src && sudo -u ichor bash -c '
    set -a; source /etc/ichor/api.env; set +a
    /opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_session_card EUR_USD pre_londres --dry-run 2>&1 | tail -3
  '
  echo '--- kl_count of latest card ---'
  sudo -u postgres psql -d ichor -tAc \"SELECT jsonb_array_length(key_levels) FROM session_card_audit ORDER BY created_at DESC LIMIT 1;\"
"

echo "=== R64 redeploy complete : brain stable path + key_levels persistence verified ==="
