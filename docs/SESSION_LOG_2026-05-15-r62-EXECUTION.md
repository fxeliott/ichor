# Round 62 — EXECUTION ship summary

> **Date** : 2026-05-15 21:10 CEST
> **Trigger** : Eliot "continue" → r62 default Option D from r61 ship summary (SessionCard.key_levels JSONB persistence)
> **Scope** : close ADR-083 D3 → D4 architectural bridge by snapshotting key_levels at orchestrator finalization
> **Branch** : `claude/friendly-fermi-2fff71` → 25 commits ahead `origin/main` (post-r62 commit)

---

## TL;DR

R62 closes the ADR-083 D3 → D4 architectural bridge by persisting the
KeyLevel snapshot into `session_card_audit` at 4-pass orchestrator
finalization. Single source of truth : both `/v1/key-levels` HTTP
endpoint AND `cli/run_session_card.py` persistence path call the same
`compose_key_levels_snapshot()` service — router and orchestrator can
never drift on which KeyLevels fire. **Local pytest 122/122 PASS + 6/6
brain persistence tests PASS** including 2 new r62 tests pinning the
key_levels mapper contract. Migration 0049 mirrors 0039 `scenarios`
pattern verbatim (NOT NULL DEFAULT `'[]'::jsonb`). Voie D respect ✓ ;
frontend gel rule 4 ✓ ; ZERO Anthropic API spend ✓.

---

## Sprint A — Audit (parallel research fork)

Spawned read-only audit fork to scope the change without polluting
main context. Fork returned a 7-section report with file_path:line_number
citations covering :

- SessionCardAudit ORM model (`apps/api/src/ichor_api/models/session_card_audit.py:24`) ;
  best precedent : `scenarios` at line 87 (W105a, migration 0039)
- 4-pass orchestrator finalization path : orchestrator stays DB-session-
  free at `packages/ichor_brain/src/ichor_brain/orchestrator.py:433-446`
  → `to_audit_row` mapper at `packages/ichor_brain/src/ichor_brain/persistence.py:20-65`
  → call site at `apps/api/src/ichor_api/cli/run_session_card.py:304-307`
- /v1/key-levels orchestration : INLINE in router (lines 95-131), 9-call
  sequence ripe for extraction
- /v1/today reads `SessionCardOut` from `apps/api/src/ichor_api/schemas.py:317`
- Existing test patterns : `test_persistence.py`, `test_key_levels_router.py`
- Recommendation : extract orchestration into shared service rather than
  duplicate

Followed the recommendation verbatim.

---

## Sprint B — Migration 0049 + ORM

`apps/api/migrations/versions/0049_session_card_key_levels.py` (NEW, 67 LOC) :

- `op.add_column("session_card_audit", sa.Column("key_levels", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")))`
- `downgrade()` drops the column
- Mirror of 0039 `scenarios` pattern verbatim — same JSONB shape semantics

`apps/api/src/ichor_api/models/session_card_audit.py` :

- Added `key_levels: Mapped[Any] = mapped_column(JSONB, nullable=False)`
- Mirrors `scenarios: Mapped[Any] = mapped_column(JSONB, nullable=False)` line 87

---

## Sprint C — Orchestration service + router refactor + brain wire

`apps/api/src/ichor_api/services/key_levels/orchestration.py` (NEW, ~110 LOC) :

- `compose_key_levels_snapshot(session) -> list[dict[str, Any]]`
- Async, returns plain dicts (JSONB-serializable)
- Composes the 9 KeyLevel computers in ADR-083 D3 phase order
- Empty list `[]` is the canonical "all NORMAL" state

`apps/api/src/ichor_api/routers/key_levels.py` (REFACTOR) :

- Replaces 47 LOC of inline orchestration with 3-line service call :
  `snapshot = await compose_key_levels_snapshot(session); items = [KeyLevelOut(**kl) for kl in snapshot]`
- Single source of truth maintained ; router is pure Pydantic-wrap layer

`packages/ichor_brain/src/ichor_brain/types.py` :

- Added `key_levels: list[dict[str, Any]] | None = None` field on
  `SessionCard` mirroring `scenarios` precedent (line 170+)

`packages/ichor_brain/src/ichor_brain/persistence.py` :

- `to_audit_row` now passes `key_levels=_dump_list(card.key_levels) or []`
- Same NOT NULL + `[]` default semantics as `scenarios` to avoid
  shadowing the server default with explicit NULL

`apps/api/src/ichor_api/cli/run_session_card.py` :

- After `orch.run()` and BEFORE `to_audit_row`, calls
  `compose_key_levels_snapshot(session)` (best-effort with try/except
  fallback to `[]` so KL snapshot failure NEVER fails the card persist)
- Attaches via `result.card.model_copy(update={"key_levels": snapshot})`
  (frozen Pydantic forbids in-place set)

---

## Sprint D — SessionCardOut Pydantic surface

`apps/api/src/ichor_api/schemas.py` :

- Added `key_levels: list[dict[str, Any]] = []` field on `SessionCardOut`
- Default `[]` covers legacy rows ; never None on rows persisted post-r62
  because column is NOT NULL DEFAULT `'[]'::jsonb`
- `/v1/today` consumers (frontend D4 future) get the snapshot for free
  via `SessionCardOut.from_orm_row`

---

## Sprint E — Tests + Hetzner deploy (partial — SSH transient down)

**Local tests** :

- `packages/ichor_brain/tests/test_persistence.py` : 6/6 PASS including
  2 new r62 tests :
  - `test_to_audit_row_key_levels_default_empty_list` pins the
    None → `[]` mapper contract (avoids NULL shadowing server default)
  - `test_to_audit_row_key_levels_carries_snapshot` pins verbatim
    snapshot persistence + defensive copy
- `apps/api/tests/test_key_levels_orchestration.py` (NEW, ~110 LOC, 4 tests) +
  full key_levels suite (router + tga + walls + polymarket + peg_break +
  gamma_flip + vol_regime + invariants) : **122 passed, 6 skipped, 12
  warnings in 33s**. The 6 skips are DB-unavailable in test env (no
  local Postgres) — the same skips exist for r59 router tests, expected
  behaviour.

**Hetzner deploy partial** :

- Migration 0049 file scp'd + landed at
  `/opt/ichor/api/src/migrations/versions/0049_session_card_key_levels.py`
  (chown ichor:ichor)
- ORM update + new orchestration service + persistence + run_session_card
  - schemas updates **deferred to next session** : SSH connection
    timed out 3× consecutively after the first scp landed. Per R55
    doctrine ("production triage trumps") this is not a blocker — the
    alembic head on Hetzner stays at 0048 until next-round
    `alembic upgrade head` + service restart. No production regression
    because no code on Hetzner currently reads `session_card_audit.key_levels`.

**Worktree-venv junction repointed** : `.pth` files in
`apps/api/.venv/Lib/site-packages/_editable_impl_ichor_*.pth` were
hardcoded to `D:\Ichor\apps\api\src` (main repo) ; rewrote them to
worktree paths so the venv sees worktree edits. R30 worktree-venv
junction know-how applied.

---

## Files changed r62

| File                                                           | Change                           | Lines       |
| -------------------------------------------------------------- | -------------------------------- | ----------- |
| `apps/api/migrations/versions/0049_session_card_key_levels.py` | NEW                              | 67 LOC      |
| `apps/api/src/ichor_api/models/session_card_audit.py`          | +key_levels column               | +9 LOC      |
| `apps/api/src/ichor_api/services/key_levels/orchestration.py`  | NEW (extract)                    | ~110 LOC    |
| `apps/api/src/ichor_api/routers/key_levels.py`                 | REFACTOR (47→3 LOC inline)       | -44 LOC net |
| `apps/api/src/ichor_api/schemas.py`                            | +key_levels SessionCardOut field | +6 LOC      |
| `apps/api/src/ichor_api/cli/run_session_card.py`               | +snapshot capture + model_copy   | +18 LOC     |
| `packages/ichor_brain/src/ichor_brain/types.py`                | +key_levels SessionCard field    | +9 LOC      |
| `packages/ichor_brain/src/ichor_brain/persistence.py`          | +key_levels mapper               | +4 LOC      |
| `packages/ichor_brain/tests/test_persistence.py`               | +2 r62 tests                     | +44 LOC     |
| `apps/api/tests/test_key_levels_orchestration.py`              | NEW                              | ~110 LOC    |
| `CLAUDE.md`                                                    | head 0048 → 0049                 | +14 LOC     |
| `docs/SESSION_LOG_2026-05-15-r62-EXECUTION.md`                 | NEW                              | this file   |

---

## Self-checklist r62

| Item                                                            | Status                           |
| --------------------------------------------------------------- | -------------------------------- |
| Sprint A : audit fork dispatched + report consumed              | ✓                                |
| Sprint B : migration 0049 + ORM update                          | ✓                                |
| Sprint C : orchestration service + router refactor + brain wire | ✓                                |
| Sprint D : SessionCardOut Pydantic surface                      | ✓                                |
| Sprint E : local pytest 122/122 + brain 6/6 PASS                | ✓                                |
| Sprint E : Hetzner alembic upgrade + service restart            | ⏳ deferred (SSH transient down) |
| Sprint F : CLAUDE.md migration head bump                        | ✓                                |
| Sprint F : SESSION_LOG ship summary                             | ✓                                |
| Single source of truth : router + orchestrator share service    | ✓                                |
| Backward compat : NOT NULL DEFAULT `'[]'::jsonb`                | ✓                                |
| Frontend gel rule 4                                             | ✓ (zero web2 changes)            |
| ZERO Anthropic API spend                                        | ✓                                |
| Voie D respected (pure-Python compute, no LLM)                  | ✓                                |
| Anti-accumulation (extract not duplicate)                       | ✓                                |
| Pre-commit hooks pass                                           | ✓                                |

---

## Master_Readiness post-r62

**Closed by r62** :

- ✅ ADR-083 D3 → D4 architectural bridge (KeyLevel snapshot persisted)
- ✅ Single source of truth for KeyLevel orchestration (router/persistence cannot drift)
- ✅ /v1/today + SessionCardOut surface key_levels for D4 frontend consumption
- ✅ Migration 0049 head ready for Hetzner deploy (file landed, alembic upgrade pending)

**Still open** :

- 1 silent-dead collector (`cot`)
- 11 Eliot-decision items (ADR-098 path A/B/C, W115c flag, ADR-021 amend, etc.)
- 3 Eliot-action-manuelle items (NEW r61 `ICHOR_CI_FRED_API_KEY` GH secret + r62 Hetzner deploy when SSH recovers)
- ADR-083 D4 frontend ungel (rule 4 décision Eliot critique)

**Confidence post-r62** : ~98% (stable + 1 D3→D4 bridge closed ; -1pp for SSH-deferred Hetzner empirical)

---

## Hetzner deploy resume (next round when SSH up)

```bash
# 1. scp the remaining files
scp apps/api/src/ichor_api/models/session_card_audit.py ichor-hetzner:/tmp/
scp apps/api/src/ichor_api/services/key_levels/orchestration.py ichor-hetzner:/tmp/
scp apps/api/src/ichor_api/routers/key_levels.py ichor-hetzner:/tmp/key_levels_router.py
scp apps/api/src/ichor_api/schemas.py ichor-hetzner:/tmp/
scp apps/api/src/ichor_api/cli/run_session_card.py ichor-hetzner:/tmp/

# 2. place + chown
ssh ichor-hetzner '
sudo cp /tmp/session_card_audit.py /opt/ichor/api/src/src/ichor_api/models/session_card_audit.py
sudo cp /tmp/orchestration.py /opt/ichor/api/src/src/ichor_api/services/key_levels/orchestration.py
sudo cp /tmp/key_levels_router.py /opt/ichor/api/src/src/ichor_api/routers/key_levels.py
sudo cp /tmp/schemas.py /opt/ichor/api/src/src/ichor_api/schemas.py
sudo cp /tmp/run_session_card.py /opt/ichor/api/src/src/ichor_api/cli/run_session_card.py
sudo chown -R ichor:ichor /opt/ichor/api/src/src/ichor_api/
'

# 3. alembic upgrade
ssh ichor-hetzner 'cd /opt/ichor/api/src && sudo -u ichor /opt/ichor/api/.venv/bin/alembic upgrade head'

# 4. service restart
ssh ichor-hetzner 'sudo systemctl restart ichor-api'

# 5. 4-witness empirical
ssh ichor-hetzner 'sudo -u postgres psql -d ichor -c "\d session_card_audit" | grep key_levels'
ssh ichor-hetzner 'curl -s -H "CF-Access-Client-Id: ..." -H "CF-Access-Client-Secret: ..." https://api.ichor.fxmilyapp.com/v1/key-levels | jq ".count"'
ssh ichor-hetzner 'sudo -u ichor /opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_session_card EUR_USD pre_londres --dry-run'
ssh ichor-hetzner 'sudo -u postgres psql -d ichor -c "SELECT id, asset, key_levels FROM session_card_audit ORDER BY created_at DESC LIMIT 1;"'
```

---

## Branch state

`claude/friendly-fermi-2fff71` → 25 commits ahead `origin/main`. **12 rounds delivered (r51-r62) en 1 session** :

- r51-r60 : per r60 ship summary
- r61 : ratify ADR-097/098 + ship FRED liveness CI workflow
- **r62 : SessionCard.key_levels JSONB persistence (ADR-083 D3 → D4 bridge)**

PR ready : https://github.com/fxeliott/ichor/pull/new/claude/friendly-fermi-2fff71

À ton "continue" suivant :

- **A** : Hetzner deploy resume r62 (5 scp + alembic upgrade + restart + 4-witness)
- **B** : `cot` collector last silent-dead (HIGH risk, dedicated ADR Socrata)
- **C** : Pivot Eliot decisions (ADR-098 path A/B/C, W115c flag, ADR-021 amend)
- **D** : ADR-083 D4 frontend ungel (rule 4 décision Eliot critique)

Default sans pivot : **Option A** (Hetzner deploy resume r62 — closes
the empirical 4-witness gap left by SSH transient timeout this round ;
prerequisite for D4 frontend consumption).
