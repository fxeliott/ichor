# ADR-031: SessionType single source via `get_args`

- **Status**: Accepted
- **Date**: 2026-05-06
- **Deciders**: Eliot
- **Supersedes**: closes the ADR-024 §"future drift is possible" debt

## Context

ADR-024 fixed five stacked bugs that had killed `session_card_audit`
writes for 2 days (2026-05-04 → 2026-05-06). One of those bugs was a
**hardcoded duplicate of the valid session set** :

```python
# apps/api/src/ichor_api/cli/run_session_card.py (pre-ADR-031)
_VALID_SESSIONS = {"pre_londres", "pre_ny", "ny_mid", "ny_close", "event_driven"}

# apps/api/src/ichor_api/cli/run_session_cards_batch.py (pre-ADR-031)
_VALID_SESSIONS = {"pre_londres", "pre_ny", "ny_mid", "ny_close", "event_driven"}
```

Two copies of the same set existed in two CLI runners. They drifted
on 2026-05-04 14:23 when `ny_mid` and `ny_close` were added to the
batch wrapper but **not** to the single-card runner — every batch tick
silently rejected those session windows with `unknown session_type`
before even hitting the runner.

ADR-024 §close reaffirmed the bug class but explicitly deferred the
single-source-of-truth fix : _"the two CLI runners still carry their
own `_VALID_SESSIONS` set. A future drift is possible. Pin
`_VALID_SESSIONS` to a single source of truth across both CLI
entrypoints"_.

This ADR closes that debt.

## Decision

**Derive the runtime-validated session set from the `SessionType`
Literal via `typing.get_args`**, exposed as a single module-level
constant in `ichor_brain.types` :

```python
# packages/ichor_brain/src/ichor_brain/types.py
from typing import Literal, get_args

SessionType = Literal["pre_londres", "pre_ny", "ny_mid", "ny_close", "event_driven"]

VALID_SESSION_TYPES: frozenset[str] = frozenset(get_args(SessionType))
"""Single source of truth for runtime validation across CLI runners."""
```

Both CLI runners now import this constant :

```python
# apps/api/src/ichor_api/cli/run_session_card.py
from ichor_brain.types import VALID_SESSION_TYPES as _VALID_SESSIONS

# apps/api/src/ichor_api/cli/run_session_cards_batch.py
from ichor_brain.types import VALID_SESSION_TYPES as _VALID_SESSIONS
```

Adding or removing a window in the `SessionType` Literal automatically
updates the runtime check. **Drift is structurally impossible.**

## Consequences

### Pros

- **Drift impossible by construction**. The bug class that took
  `session_card_audit` down for 2 days is closed at the type level —
  not just at the test level.
- **No new abstraction**. `get_args` is a stdlib function, the
  constant is a `frozenset`, and there is exactly one source. No
  helper module, no factory, no class.
- **`__all__` updated** in `ichor_brain.types` so the constant is
  part of the documented public API.

### Cons

- **Cross-package import** : `apps/api` now imports from
  `packages/ichor_brain` for this constant. This is consistent with
  the existing pattern (already 2 cross-imports in the API package
  for `HttpRunnerClient` and `Orchestrator`), so no architectural
  precedent change.
- **Marginal startup cost** : `frozenset(get_args(SessionType))` runs
  once at module import time. Negligible (5 strings, ~1 µs).

### Neutral

- Type-checkers see the new constant as `frozenset[str]`, not as a
  union of literals. If we ever want literal-narrowing on session
  membership checks, we'd need a TypeGuard. Not currently needed.

## Alternatives considered

### A — Helper module `cli/_session_types.py`

Putting the constant in a helper module of the API package would
avoid the cross-package import but introduces a new abstraction layer
for one constant. Rejected : the source of truth IS the Literal in
`ichor_brain.types` ; everything else is a derivation.

### B — Test-only assertion

Add a CI test that `_VALID_SESSIONS_CARD == _VALID_SESSIONS_BATCH ==
set(get_args(SessionType))`. Rejected : this is exactly what ADR-024
called out as insufficient — drift is detected at CI time, not made
impossible. The current fix is structural ; this would have been a
behavioural backstop.

### C — Pydantic Settings

Promote the set to a Pydantic Settings field. Rejected : settings
are runtime-overridable, but a session set is a code-level invariant.
Wrong abstraction.

## Implementation

Single commit, 3 files modified :

- `packages/ichor_brain/src/ichor_brain/types.py:26-33` (`VALID_SESSION_TYPES` + `__all__` update)
- `apps/api/src/ichor_api/cli/run_session_card.py:34` (import replace hardcoded set)
- `apps/api/src/ichor_api/cli/run_session_cards_batch.py:54` (idem)

Verified at 2026-05-06 20:50 CEST :

```bash
python -c "from ichor_api.cli.run_session_card import _VALID_SESSIONS; print(sorted(_VALID_SESSIONS))"
# ['event_driven', 'ny_close', 'ny_mid', 'pre_londres', 'pre_ny']
```

No import cycle. No regression on `session_card_audit` writes
(prod still green at 03:15 CEST baseline + Phase 0 alerts active).

## Related

- ADR-024 — five-bug fix (introduced this debt as a known followup).
- Migration 0027 — extended the `session_card_audit` CHECK constraint
  to match the Literal (separate fix, complementary).
