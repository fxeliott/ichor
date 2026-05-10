# ADR-072: Ansible `ichor_packages` role — declarative sync of internal Python packages

- **Status**: Accepted
- **Date**: 2026-05-09
- **Deciders**: Eliot
- **Related**: ADR-067 (Couche-2 async polling — surfaced this gap),
  W76 (this wave)

## Context

On 2026-05-08 (Wave 67) the Couche-2 async polling deploy revealed that
`/opt/ichor/packages-staging/agents/src/ichor_agents/observability.py`
was missing from the Hetzner host. Couche-2 systemd units crashed on
import time. A manual `scp` from the local monorepo restored the file.

The W67 ADR explicitly flagged this:

> `packages-staging/agents/observability.py` was missing on Hetzner:
> pre-existing deploy artifact missing. Copied from local to fix
> imports during W67 deploy. **Should be encoded into Ansible role.**

Root cause: the `ichor_api` role only synchronizes `apps/api/`. The
three internal Python packages — `packages/agents`, `packages/ichor_brain`,
`packages/ml` — were synced manually at provisioning time and never
re-synchronized on subsequent runs. Adding a new module (the
observability shim was added 2026-05-07 in ADR-032) silently failed
to propagate, manifesting only when a Couche-2 timer next ran.

This is exactly the class of bug Ansible declarative provisioning is
supposed to prevent. The fix is structural, not procedural.

## Decision

Create a new role `infra/ansible/roles/ichor_packages` that:

1. Ensures `/opt/ichor/packages-staging/` exists with `ichor` ownership.
2. `synchronize` each of the three packages (`packages/agents`,
   `packages/ichor_brain`, `packages/ml`) into
   `/opt/ichor/packages-staging/<name>/` with `delete=true` so the
   staging tree is in lockstep with the monorepo source-of-truth.
   Excludes `.venv`, `__pycache__`, `.pytest_cache`, `*.egg-info`,
   `node_modules`.
3. Busts `__pycache__` recursively across the staging tree to force a
   reload of any stale bytecode after the sync.
4. `uv pip install -e` each package into `/opt/ichor/api/.venv` so
   `import ichor_agents`, `import ichor_brain`, `import ichor_ml`
   resolve under the API + collector + Couche-2 services.
5. **W67 regression guard**: explicit `stat` + `fail` if
   `observability.py` is missing post-sync. Prevents silent
   regressions on the exact bug class that motivated this ADR.

Order in `site.yml`: `ichor_packages` runs **after** `ichor_api`
because it depends on the venv created in step 4 of the API role.
Both share the `[api, ichor_api]` tag set so partial deploys remain
ergonomic; new tags `[packages, ichor_packages]` allow a focused
sync run without touching the API service.

## Consequences

### Positive

- **Drift between monorepo and Hetzner is impossible** at the
  packages level. Re-running `site.yml` with `--tags packages`
  re-synchronizes all three packages atomically.
- **W67 regression cannot recur silently**: the role's last task is
  a stat + fail on the specific shim file. If the source file is
  ever deleted, the playbook fails loud at provisioning time, not
  at midnight when a Couche-2 timer next fires.
- **No more `scp + busy-the-pycache` shell sessions**: the sync is
  declarative. Eliot can re-run the role from any laptop with
  Ansible installed.
- **Editable installs**: `uv pip install -e` keeps the venv
  in editable mode, so a future re-sync (without re-running pip)
  picks up changes immediately.

### Negative

- **`synchronize` requires SSH passthrough on the controller** (which
  Eliot's `ichor-hetzner` alias already provides via `~/.ssh/config`).
  No new dependency.
- **Adds ~15 s to a full `site.yml` run** (3 rsyncs + 3 pip installs).
  Acceptable given the failure-class it eliminates.
- **Ownership and venv-bind to the `ichor` user**: assumes the
  `ichor_api` role created the user. The role explicitly depends on
  that ordering.

### Out of scope

- **Does not synchronize `apps/web2`** — frontend deploy is via
  Vercel CDN, not Hetzner.
- **Does not run pytest post-sync** — package-level tests run in
  CI; production-side runtime smoke is the systemd timers themselves
  - `/healthz`.

## Alternatives considered

- **Add the sync inline to the `ichor_api` role** — rejected:
  conceptually the packages are independent of the API service
  (they're consumed by collectors + Couche-2 timers too). A separate
  role keeps the responsibility split clean and the tags meaningful.
- **Bundle packages-as-wheels in the API role's `pip install`** —
  rejected: editable installs are already used for the API itself
  (`uv pip install -e /opt/ichor/api/src[dev]`). Wheel-building would
  diverge from the local-dev workflow and slow iteration.
- **Use a single `synchronize` of the entire `packages/` directory** —
  rejected: the loop-of-3 is more explicit and lets us add per-package
  excludes if any one of them grows unique build artifacts later.

## Verification plan

After committing, the next `site.yml --tags packages` run on Hetzner
must:

- Create `/opt/ichor/packages-staging/{agents,ichor_brain,ml}/` if
  missing.
- Sync each package's full source tree.
- Pass the regression guard (`observability.py` stat).
- Restart no services (the role does not own systemd units).

A subsequent fresh-deploy on a new Hetzner host (when we provision
the secondary) will validate the role end-to-end.

## References

- `infra/ansible/roles/ichor_packages/tasks/main.yml`
- `infra/ansible/site.yml` (role registered after `ichor_api`)
- ADR-067 (Couche-2 async migration — surfaced the missing shim)
- ADR-032 (Langfuse @observe wiring — introduced the shim)
- `packages/agents/src/ichor_agents/observability.py` (the regression
  guard target)
