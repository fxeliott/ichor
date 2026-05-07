# ADR-030: `register-cron-*.sh` protection — post-2026-05-04 incident

- **Status**: Accepted (ratification of an in-place protection)
- **Date**: 2026-05-06
- **Deciders**: Eliot
- **Implements**: hook protection installed at project scope ;
  ADR-031 closed a related class of latent drift

## Context

On **2026-05-04**, a `register-cron-*.sh` edit on Hetzner overwrote
shared systemd unit templates and **took 5 ichor-* services down**
(documented in `CLAUDE.md` projet under "Things that are subtly
broken or deferred", specifically : *"the bug class that took down
5 services on 2026-05-04"*).

The exact root cause is not narrated in the dated SESSION_LOG of
that day (which focuses on the Phase 1 step shipping), but the
mechanism is well-understood :

- A `register-cron-*.sh` script writes both a `.service` unit and a
  `.timer` unit to `/etc/systemd/system/`.
- Several scripts share **template unit names** (`ichor-collector@.service`,
  `ichor-couche2@.service`, `ichor-briefing@.service`, `ichor-session-cards@.service`).
- Editing one register-cron script and re-running it with `sudo bash`
  overwrites the template — affecting every instance that depended
  on it (one collector becomes the wrong shape for all collectors).
- `daemon-reload` + `enable --now` on the new (broken) template
  silently degrades or kills sibling services until a manual revert.

## Decision

**Two layers of protection, both already installed at project scope :**

### Layer 1 — PreToolUse warn hook on Edit/Write/MultiEdit

Defined in `.claude/settings.json` :

```json
{
  "matcher": "Edit|Write|MultiEdit",
  "hooks": [{
    "type": "command",
    "command": "powershell.exe ... if ($path -match 'scripts[\\\\/]hetzner[\\\\/]register-cron') {
      Write-Host \"WARN: editing $path — this register script defines systemd unit
      templates shared by all timers. Re-running the script overwrites
      /etc/systemd/system/ichor-collector@.service which can break the existing
      fred/gdelt/polygon collectors. Verify the EnvironmentFile + ExecStart match
      the in-prod template before deploying.\"
    }"
  }]
}
```

This hook does **not block** the edit (`exit 0`) — it surfaces a
warn-level reminder to the operator (Claude or human) that they're
about to touch a high-blast-radius file.

### Layer 2 — Pattern conservation across all register-cron scripts

All `scripts/hetzner/register-cron-*.sh` files MUST follow the
canonical pattern verified against the in-prod template :

```bash
#!/usr/bin/env bash
set -euo pipefail

cat > /etc/systemd/system/ichor-<name>.service <<'EOF'
[Unit]
Description=...
After=network-online.target postgresql.service [chain]
Wants=network-online.target

[Service]
Type=oneshot
User=ichor
Group=ichor
WorkingDirectory=/opt/ichor/api
EnvironmentFile=/etc/ichor/api.env
ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_<name> --persist
TimeoutStartSec=<seconds>
StandardOutput=journal
StandardError=journal
SuccessExitStatus=0 1
EOF

cat > /etc/systemd/system/ichor-<name>.timer <<'EOF'
[Unit]
Description=...

[Timer]
OnCalendar=<schedule>
Unit=ichor-<name>.service
RandomizedDelaySec=120
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now ichor-<name>.timer
```

**Critical contract clauses** :
- `Type=oneshot` (not `simple` — these are tick-then-exit jobs)
- `EnvironmentFile=/etc/ichor/api.env` (absolute path)
- `User=ichor` (not root)
- `WorkingDirectory=/opt/ichor/api` (absolute path)
- `ExecStart` uses absolute Python path `/opt/ichor/api/.venv/bin/python`
- `RandomizedDelaySec=120` (avoids thundering-herd on 5+ overlapping crons)
- `Persistent=true` (survives reboot)

Each new register-cron-*.sh in Phase 0 (2026-05-06 :
`register-cron-rr25.sh`, `register-cron-liquidity-check.sh`,
`register-cron-cb-tone.sh`) was validated against this contract
before scp + execution on Hetzner.

## Consequences

### Pros

- **PreToolUse warn fires automatically** when an LLM (Claude Code)
  attempts to edit or create a register-cron-*.sh — no human reliance
  on memory.
- **Pattern is canonical and reviewable** : a new script can be
  diffed against `register-cron-vpin.sh` (the reference) before
  scp.
- **Layered defense** : even if the warn is ignored, the canonical
  pattern itself avoids the failure mode (no per-script env mutation,
  no hidden `Type=simple` swap, etc.).

### Cons

- **No CI lint** today — a register-cron-*.sh that violates the
  pattern (e.g. `Type=simple`, missing `EnvironmentFile`) would not
  be caught at PR time, only by manual review or by failing on
  Hetzner. Phase A.3 should add `shellcheck` + a structural lint to
  the CI workflow.
- **Hook is project-scoped** : if Eliot edits a register-cron-*.sh
  outside Claude Code (e.g. directly in VS Code without Claude in
  the loop), the hook does not fire.

### Neutral

- The hook also fires on legitimate edits (creating a new
  register-cron-*.sh as we did in Phase 0). This is by design —
  the warn is contextual reminder, not blocker.

## Alternatives considered

### A — Hard block via `exit 2` instead of warn

Rejected : would have prevented Phase 0 entirely (3 new scripts
created legitimately). The warn reminds, the operator decides.

### B — Move register-cron-*.sh under .git/hooks-equivalent CI gate

Rejected : the scripts are deployed to Hetzner via scp + sudo bash,
not through a CI pipeline. A CI gate would test syntax but not
catch the unit-template-overwrite mechanism, which only manifests
on prod when `daemon-reload` runs.

### C — Use systemd-template generators instead of file-overwrite

Considered ; tabled. Would require a refactor of all 28 existing
scripts. Phase A.7 / A.7+ if observability work uncovers more
incidents.

## Implementation

Already shipped :
- Hook : `.claude/settings.json` (project) — line ~30, matcher
  `Edit|Write|MultiEdit`, no-op exit 0 + visible warn.
- Canonical pattern : `scripts/hetzner/register-cron-vpin.sh`
  (reference), reproduced in 25+ siblings.
- Phase 0 new scripts validated against the pattern (verifier
  subagent confirmed conformity 2026-05-06 20:45 CEST).

## Followups

- **Phase A.3 / Wave 5 CI** : add `shellcheck` lint on
  `scripts/hetzner/register-cron-*.sh` + a structural test that
  asserts the `Type=oneshot` + `EnvironmentFile=/etc/ichor/api.env`
  + `User=ichor` clauses are present.
- **Phase A.7** : RUNBOOK-014 / 015 should include "if you suspect
  a register-cron drift, here is the diff vs canonical reference".

## Related

- ADR-024 — five-bug fix for session_card_audit (the same Hetzner
  cron family, different failure mode).
- ADR-031 — SessionType single source (closes a sibling drift class
  inside Python, not systemd).
