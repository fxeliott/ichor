# Round 63 — EXECUTION ship summary

> **Date** : 2026-05-15 21:25 CEST
> **Trigger** : Eliot "continue" → r63 default Option A from r62 (Hetzner deploy resume) + Option E pivot (CI invariant guards)
> **Scope** : (1) Hetzner deploy r62 + 4-witness empirical (closes R59 doctrine gap from r62) ; (2) ship r62 invariant CI guards (ADR-081 extension)
> **Branch** : `claude/friendly-fermi-2fff71` → 26 commits ahead `origin/main` (post-r63 commit)

---

## TL;DR

R63 closes the empirical 4-witness gap left by r62's SSH timeout. Hetzner
alembic head bumped 0048 → 0049 ; ichor-api restarted with new ORM ; first
post-r62 dry-run card persisted with **kl_count=11** (full TGA + 2
gamma_flip + 2 gex_call_wall + SKEW + HY OAS + 3 polymarket content).
Bonus : found + fixed a brain-venv install path drift (`/tmp/ichor_brain-deploy`
not `/opt/ichor/packages/`) that initially caused silent persistence of
empty key_levels — root-caused via 12 sequential empirical witnesses.
Plus shipped 5 mechanical CI invariant guards (ADR-081 extension)
codifying the r62 architectural contract so single-source-of-truth
drift fails the build instead of silently corrupting persistence.

---

## Sprint A — SSH connectivity + Hetzner deploy

SSH was flapping (down → 1 successful echo → down again 3× consecutive)
but eventually held a stable session long enough to :

1. `scp` 7 files to `/tmp/` :
   - `session_card_audit.py` (ORM)
   - `orchestration.py` (NEW service)
   - `key_levels.py` (refactored router)
   - `schemas.py` (SessionCardOut + key_levels field)
   - `run_session_card.py` (CLI snapshot capture)
   - `types.py` (brain SessionCard + key_levels field)
   - `persistence.py` (brain to_audit_row mapper)

2. `sudo cp` to `/opt/ichor/api/src/src/ichor_api/...` paths + chown
   ichor:ichor

3. `alembic upgrade head` (had to source `/etc/ichor/api.env` first —
   the bare `alembic upgrade head` failed with `NoSuchModuleError:
sqlalchemy.dialects:driver` because the placeholder URL in
   alembic.ini wasn't overridden by `ICHOR_API_DATABASE_URL` env var) :
   `INFO Running upgrade 0048 -> 0049, session_card_key_levels — ADR-083
D3 KeyLevel snapshot persistence (r62)`

4. `systemctl restart ichor-api` → status `active`

---

## Sprint B — Brain venv install path drift fix (root cause analysis)

After Sprint A, W6 empirical showed the just-persisted EUR_USD card had
**kl_count=0** despite `/v1/key-levels` returning 11 items. Direct test
(W8) confirmed `compose_key_levels_snapshot()` returned 11 items. The
silent zero was a real bug.

Root cause traced through 4 hypotheses :

1. ❌ Code wasn't deployed → `grep` showed correct content in deployed
   `run_session_card.py` and `persistence.py`
2. ❌ Snapshot returned [] silently in CLI session → W8 direct test
   confirmed snapshot=11 in identical session pattern
3. ❌ try/except fallback fired → no `key_levels_snapshot.fallback`
   warning in structlog output
4. ✅ **`SessionCard.key_levels` field MISSING from deployed Python's
   imported `ichor_brain.types`** — `model_copy(update={"key_levels":
...})` silently dropped the unknown key (Pydantic `extra="forbid"`
   only triggers at validation, not copy)

Fix : `python -c "import ichor_brain.types; print(ichor_brain.types.__file__)"`
revealed the venv was importing from `/tmp/ichor_brain-deploy/packages/
ichor_brain/src/ichor_brain/types.py` — a stale install path NOT
`/opt/ichor/packages/`. Deployed `types.py` + `persistence.py` to
`/tmp/ichor_brain-deploy/...` + chown + restart. Verified post-fix :
`key_levels in SessionCard.model_fields = True`.

**R63 doctrinal pattern NEW** : Hetzner editable-install paths can
diverge from `/opt/ichor/packages/` ; always verify with `python -c
"import X; print(X.__file__)"` before declaring a deploy successful.

---

## Sprint C — 4-witness empirical (12 sequential checkpoints)

| #   | Check                                                        | Result                                                             |
| --- | ------------------------------------------------------------ | ------------------------------------------------------------------ |
| W1  | `psql \d session_card_audit` (key_levels row)                | `key_levels jsonb not null default '[]'::jsonb` ✓                  |
| W2  | `curl /v1/key-levels` then `jq .count`                       | 11 ✓                                                               |
| W3  | `SELECT COUNT(*) FROM session_card_audit`                    | 176 (pre-r62 baseline)                                             |
| W4  | `SELECT key_levels FROM ... LIMIT 1` (pre-r62 row)           | `[]` (server default backfill ✓)                                   |
| W5  | dry-run EUR_USD pre_londres                                  | persisted (id=c3d5cb92...) but kl_count=0 ✗                        |
| W6  | `SELECT jsonb_array_length(key_levels) ... LIMIT 3`          | 0/0/0 across 3 latest cards ✗                                      |
| W7  | grep CLI log for fallback warning                            | (no output, snapshot didn't error)                                 |
| W8  | direct `compose_key_levels_snapshot(s)` from CLI session     | 11 items ✓                                                         |
| W9  | `key_levels in SessionCard.model_fields` post brain fix      | True ✓                                                             |
| W10 | dry-run NAS100_USD post brain fix                            | persisted (id=ae2f4537...) ✓                                       |
| W11 | `SELECT jsonb_array_length(key_levels) ... LIMIT 3` post-fix | 11 / 0 / 0 ✓                                                       |
| W12 | sample latest card key_levels content                        | full TGA + 2 gamma_flip + 2 walls + SKEW + HY OAS + 3 polymarket ✓ |

**ADR-083 D3 → D4 architectural bridge LIVE on Hetzner production.**

---

## Sprint D — r62 invariant CI guards (ADR-081 extension)

`apps/api/tests/test_invariants_r62_key_levels_persistence.py` (NEW, ~145
LOC, 5 tests, runs in 2.5s) :

1. **`test_key_levels_router_uses_orchestration_service_only`** — parses
   `routers/key_levels.py` source, asserts the only key*levels-related
   import is `compose_key_levels_snapshot`, AND tokenize-aware scan
   confirms NO direct `compute*\*\_levels()` calls in router body.
   **Catches the r62 single-source-of-truth drift class** : a future
   contributor adding a new KeyLevel computer X must update the
   orchestration service, not just wire it inline in the router.

2. **`test_compose_key_levels_snapshot_is_async_function`** — pins the
   async contract via `inspect.iscoroutinefunction`. Sync drift would
   corrupt both router and CLI persistence paths.

3. **`test_session_card_audit_has_key_levels_column`** — pins the ORM
   column at runtime : exists + JSONB type + nullable=False. Catches
   accidental migration revert.

4. **`test_session_card_pydantic_has_key_levels_field`** — pins the
   brain `SessionCard.model_fields["key_levels"]` exists. Catches the
   exact bug class hit in Sprint B (silent model_copy NO-OP).

5. **`test_to_audit_row_maps_none_key_levels_to_empty_list`** — source-
   inspection of `persistence.py`, asserts the canonical
   `key_levels=_dump_list(card.key_levels) or []` mapper line is
   present (catches accidental removal of the `or []` fallback that
   would INSERT NULL violating the NOT NULL constraint).

5/5 tests pass locally + auto-run by pre-commit ADR-081 hook.

---

## Files changed r63

| File                                                           | Change                             | Lines     |
| -------------------------------------------------------------- | ---------------------------------- | --------- |
| `apps/api/tests/test_invariants_r62_key_levels_persistence.py` | NEW                                | ~145 LOC  |
| `CLAUDE.md`                                                    | head 0049 LIVE empirical 4-witness | +14 LOC   |
| `docs/SESSION_LOG_2026-05-15-r63-EXECUTION.md`                 | NEW                                | this file |

Hetzner deploy : 7 files placed + chown + alembic upgrade + 2 service
restarts + 1 brain-venv-path fix. No new git changes for the deploy
itself (already committed in r62).

---

## Self-checklist r63

| Item                                                                                  | Status                           |
| ------------------------------------------------------------------------------------- | -------------------------------- |
| Sprint A : SSH + scp + alembic upgrade                                                | ✓                                |
| Sprint B : brain venv path drift root-caused + fixed                                  | ✓                                |
| Sprint C : 12-witness empirical sequence                                              | ✓                                |
| Sprint D : 5 r62 invariant CI guards shipped                                          | ✓                                |
| Sprint E : CLAUDE.md + SESSION_LOG                                                    | ✓                                |
| ADR-083 D3 → D4 bridge LIVE prod                                                      | ✓                                |
| Pre-commit hooks pass                                                                 | ✓                                |
| Frontend gel rule 4                                                                   | ✓                                |
| ZERO Anthropic API spend                                                              | ✓                                |
| Voie D respected                                                                      | ✓                                |
| R59 doctrine ("marche exactement, pas juste fonctionne")                              | ✓ closed via 12-witness sequence |
| R63 NEW doctrine codified : verify Python import path before declaring deploy success | ✓                                |

---

## Master_Readiness post-r63

**Closed by r63** :

- ✅ ADR-083 D3 → D4 architectural bridge LIVE on Hetzner (was code-shipped r62, now empirically validated)
- ✅ R59 doctrine 4-witness gap from r62 closed (kl_count=11 in latest persisted card)
- ✅ Brain venv install path drift discovered + fixed (`/tmp/ichor_brain-deploy` was stale)
- ✅ R62 architectural contract codified mechanically (5 new ADR-081 invariant guards)

**Still open** :

- 1 silent-dead collector (`cot`)
- 11 Eliot-decision items (ADR-098 path A/B/C, W115c flag, ADR-021 amend, etc.)
- 1 Eliot-action-manuelle item (`ICHOR_CI_FRED_API_KEY` GH secret r61)
- ADR-083 D4 frontend ungel (rule 4 décision Eliot critique)
- Brain venv install path consolidation (`/tmp/ichor_brain-deploy` is brittle ; should symlink to /opt/ichor/packages or be re-installed editable to a stable path) — R64 candidate

**Confidence post-r63** : ~99% (stable + 1 D3→D4 bridge LIVE empirically + 1 brittle path identified for next session)

---

## Branch state

`claude/friendly-fermi-2fff71` → 26 commits ahead `origin/main`. **13 rounds delivered (r51-r63) en 1 session** :

- r51-r60 : per r60 ship summary
- r61 : ratify ADR-097/098 + ship FRED liveness CI workflow
- r62 : SessionCard.key_levels JSONB persistence (ADR-083 D3 → D4 bridge)
- **r63 : Hetzner deploy r62 + 4-witness empirical + 5 CI invariant guards**

PR ready : https://github.com/fxeliott/ichor/pull/new/claude/friendly-fermi-2fff71

À ton "continue" suivant :

- **A** : `cot` collector last silent-dead (HIGH risk, dedicated ADR Socrata)
- **B** : Brain venv install path consolidation (`/tmp/ichor_brain-deploy` → `/opt/ichor/packages` symlink + idempotent deploy script)
- **C** : Pivot Eliot decisions (ADR-098 path A/B/C, W115c flag, ADR-021 amend)
- **D** : ADR-083 D4 frontend ungel (rule 4 décision Eliot critique)
- **E** : Anti-skill structural fix EUR_USD/usd_complacency (n=13 stat-sig anti-skill — Vovk weight 0.300 vs equal_weight 0.350)

Default sans pivot : **Option B** (brain venv path consolidation —
closes the brittle deploy path discovered r63 Sprint B ; prerequisite
for safer future r62-class deploys).
