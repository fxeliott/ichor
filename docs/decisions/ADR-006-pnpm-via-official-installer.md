# ADR-006: pnpm via official Win installer (Corepack fails)

- **Status**: Accepted
- **Date**: 2026-05-02
- **Decider**: Eliot (autonomy delegation)

## Context

Recommended pnpm install method since Node 22 is via **Corepack** (built into
Node, no global pollution): `corepack enable && corepack prepare pnpm@latest
--activate`.

On Eliot's Win11 (2026-05-02), Corepack failed:

```
Internal Error: EPERM: operation not permitted, open 'C:\Program Files\nodejs\pnpm'
```

Cause: Node was installed system-wide (`C:\Program Files\nodejs`), which
requires admin privileges to write into. Corepack tries to put shim
executables there. The Claude Code session does not run as admin (good!).

## Decision

Use the **official pnpm Windows installer** (per-user install):

```powershell
iwr https://get.pnpm.io/install.ps1 -useb | iex
```

Effects:

- Installs to `%USERPROFILE%\AppData\Local\pnpm\` (no admin needed)
- Adds `PNPM_HOME` and updates user `PATH` automatically
- Pinned in `package.json` `packageManager` field as `pnpm@10.33.2` so any
  contributor (or CI) using Corepack on Linux/macOS picks the same version

For **CI** (`.github/workflows/ci.yml`) and **Hetzner** (Ansible `node` role),
we keep Corepack — both run as root/admin, where Corepack works fine.

This is a Win11-local-only workaround. Documented so future contributors
on Windows aren't surprised.

## Consequences

- pnpm version on Eliot's Win11 may drift from `packageManager` if pnpm
  itself ships an update — `pnpm` shim auto-respects `packageManager` field
  in projects since v8, so this drift is invisible in practice.
- If Eliot ever runs a fresh Win11 install, `scripts/setup-local.sh` already
  detects missing `pnpm` and runs the same installer — idempotent.

## Alternatives considered

- **`npm install -g pnpm`** — rejected: same EPERM issue (also writes to
  `C:\Program Files\nodejs\node_modules`).
- **Run Claude Code session as admin** — rejected: violates Eliot's principle
  of least privilege; one-off install convenience doesn't justify perma-admin.
- **Reinstall Node via nvm-windows / fnm to user dir** — rejected:
  invasive change to Eliot's Node setup just to make Corepack work.
- **`npx pnpm@VERSION`** — rejected: pnpm is meant to be a persistent
  command, not invoked via npx.

## References

- [pnpm install docs](https://pnpm.io/installation#using-a-standalone-script)
- [Corepack docs](https://nodejs.org/api/corepack.html)
