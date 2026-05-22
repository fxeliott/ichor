# SESSION_LOG 2026-05-17 — r95 EXECUTION (ADR-104 — degraded_inputs persisted on the session card)

**Round type:** Tier-3 autonomy-hardening continuation — the r94
SESSION_LOG / pickup v26 binding default ("Tier 3 continues, R59 first,
pick highest value/effort"). Chosen item: the **end-user `/briefing`
degraded-data visibility** (ADR-099 §T3.2 completion). A backend
persist+projection round (ADR-before-code), explicitly **NOT** the
frontend badge (that is r96 — proven backend-then-frontend split).

**Branch:** `claude/friendly-fermi-2fff71` (worktree
`D:\Ichor\.claude\worktrees\friendly-fermi-2fff71`). **ZERO Anthropic
API** (the Witness-C card-gen ran through claude-runner = Voie D). ADR-017
held (the projected field is structured FRED-staleness provenance, never a
signal — empirically the AUD card carried a normal bias/conviction with
the manifest alongside). `to_audit_row` byte-identical; the only
behavioural delta is a new nullable column + its projection.

## Resume verification (R59 — prompt is a failsafe, live wins)

Spawned in the STALE `gifted-bell-c1b656` worktree; real work in
`friendly-fermi-2fff71`. Verified by tool: HEAD `17e3780` (r94), 59 ahead,
clean, pushed, PR #138 OPEN/MERGEABLE. The standing-brief re-issuance =
"continue" (doctrine #10) → executed the announced Tier-3 default;
re-evaluated value/effort across the 3 options — (c) the end-user
degraded badge is highest value / lowest blast-radius and the explicit
next step ADR-103 itself named; (a) holiday-gate = the 2026-05-04
5-services-killed class (deferred, dedicated cautious round); (b) GBP
Driver-3 = structural R53 chicken-egg (`IR3TIB01GBM156N` unpolled →
prod-DB liveness unverifiable this round). No pivot.

## The decision — persist-on-card, not live-sidecar (R59 + doctrine, not guess)

2 parallel R59 sub-agents (backend chain + frontend chain, file:line) +
precise confirm-reads mapped the exact gap (the Pydantic-projection-gap
class, doctrine #1, at the **persist** boundary): `/briefing` reads
`/v1/sessions/{asset}`→`SessionCardOut`←`SessionCardAudit`, which had no
degraded column; `degraded_inputs` lived only on the live-recompute
operator endpoint `/v1/data-pool/{asset}` and was dropped at
`run_session_card.py:321` (`to_audit_row` maps the brain `SessionCard`,
never the `DataPool`).

Two architectures evaluated against the data-honesty doctrine:
**live-sidecar (no migration)** = REJECTED — a badge reflecting a fresh
recompute at page-load rather than the persisted card's data-health at
generation is dishonest by construction (re-introduces the exact
silent-skip ADR-103 kills, at the surface meant to close it).
**persist-on-card (additive migration)** = CHOSEN — point-in-time honest,
the only ADR-103-faithful design.

## What shipped (backend chain, end-to-end verifiable through /v1/sessions JSON)

- **NEW `docs/decisions/ADR-104-…md`** — thin child implementing ADR-099
  §T3.2 end-user completion on immutable ADR-103 (not amended; honest
  provenance note: ADR-103 said "r94", r94 was consumed by the ADR-092
  recalibration its own surface surfaced → badge is r95+r96). Includes
  the ichor-trader-YELLOW-1 **§Cross-endpoint contract** binding r96.
- **`schemas.py`** — `DegradedInputOut` Pydantic **moved byte-identical**
  from `routers/data_pool.py` (anti-accumulation SSOT doctrine #4; the
  3rd-use trigger) + new `degraded_inputs: list[DegradedInputOut] | None
= None` tri-state field on `SessionCardOut` (auto-projected by
  `from_orm_row`'s `model_validate`).
- **`routers/data_pool.py`** — local class deleted, `from ..schemas
import DegradedInputOut` re-export (identity-pinned → `DataPoolOut`
  byte-identical); unused `date`/`Literal` imports removed.
- **`migrations/versions/0050_session_card_degraded_inputs.py`** — NEW.
  Additive `degraded_inputs` JSONB **NULLABLE, NO server_default** —
  deliberate tri-state honesty divergence from 0049 `key_levels` /
  0039 `scenarios` (`NULL`="liveness not tracked at generation" — honest
  unknown, never a backfilled "[]" falsely asserting "all fresh").
- **`models/session_card_audit.py`** — matching nullable ORM column
  (documented divergence).
- **`cli/run_session_card.py`** — `degraded_inputs_payload` captured
  **symmetrically** (live: serialize `pool.degraded_inputs` via the SSOT
  `DegradedInputOut(...).model_dump(mode="json")`; dry-run: `None`),
  `row.degraded_inputs` set **after** `to_audit_row` →
  `ichor_brain.persistence.to_audit_row` **byte-identical** (api↔DataPool
  cross-cut kept in the api layer, not the brain).
- **Tests**: NEW `test_session_card_degraded_inputs_column.py`
  (present/nullable/**no-server-default**/JSONB) ; tri-state projection
  appended to `test_session_card_extractors.py` (legacy-`None`
  back-compat, `[]`-tracked-fresh, degraded typed round-trip with
  ISO→`date`) ; SSOT-identity + producer→wire parity appended to
  `test_data_pool_data_integrity.py`.

## ichor-trader proactive review (R28 — every RED/YELLOW pre-merge)

Dispatched BEFORE deploy on the full diff. **0 RED, 1 YELLOW-1, 7 GREEN.**
GREEN: ADR-017 (provenance only, no signal path), Voie D (zero LLM in
persist), SSOT byte-identity (`RouterDIO is SchemaDIO`, `DataPoolOut`
unchanged), `to_audit_row` byte-identity/layering, `source_pool_hash`/
Critic (additive, not folded into the hash), over-claim honesty (scope
boundary scrupulously stated), test coverage.
**YELLOW-1 (the r94-class consumption asymmetry) — APPLIED pre-merge,
doc-only:** `/v1/data-pool.degraded_inputs` (always-present live
recompute) vs `/v1/sessions.degraded_inputs` (tri-state, point-in-time,
`null`=not-tracked) are deliberately NOT the same contract. Added
**ADR-104 §Cross-endpoint contract** making it a binding r96 invariant
(r96 MUST read only the card field, MUST render `null` as
"data-health unknown" never "fresh", MUST NOT fall back to `/v1/data-pool`).
No code change → build gate unaffected.

## Verification (3-witness, "marche exactement pas juste fonctionne")

1. **Witness A — static/test gate:** ruff check + `ruff format --check`
   clean (8 files) ; doctrine-#4 venv worktree-resolved
   (`ichor_api`/`ichor_brain` → worktree) ; **77 targeted pytest pass**
   (71 apps/api incl. tri-state + SSOT-identity + producer→wire parity +
   the existing extractor back-compat regression + drivers/data_pool/
   data_integrity ADR-103 regression ; **6 `ichor_brain` test_persistence
   = the `to_audit_row` byte-identity proof**, unmodified → all pass
   unchanged). Offline `alembic upgrade 0049:0050 --sql` audited: exactly
   `ALTER TABLE session_card_audit ADD COLUMN degraded_inputs JSONB;`
   (pure additive, transactional DDL, provably non-destructive).
2. **Deploy (KEYWORD MIGRATION, expand-pattern: schema before code):**
   `pg_dump -Fc` table backup (`/tmp/sca_pre0050_20260517-144319.dump`),
   `alembic upgrade` `0049`→**`0050 (head)`**, column live
   `degraded_inputs | jsonb` nullable/no-default. `redeploy-api.sh`
   Steps 1-3 OK, Step-4 hit the known sshd-throttle → ONE consolidated
   throttle-aware recovery SSH (r76/r90/r94 pattern; prod NOT regressed —
   un-restarted = old code, safe with the additive nullable column).
   Restart → `healthz=200 sample=200`, no rollback.
3. **Witness B — back-compat (NEW code):** `/v1/sessions/NAS100_USD` →
   `has_field=True value=None`. New code projects the field; the legacy
   row (pre-0050) honestly `null` — no crash, no shape break (r72-r84
   `/v1/sessions` consumers protected). Already observed `null` with OLD
   code immediately post-migration too (expand-pattern safety proven both
   sides).
4. **Witness C — end-to-end on real prod:** single `AUD_USD pre_ny
   --live` card-gen (User=ichor, api.env-sourced, mirroring the systemd
   unit — R59, not guessed) ran via claude-runner (~344 s, critic
   approved, **zero Anthropic API** = Voie D). Fresh card
   `2026-05-17 16:45:32`, `n_degraded=1`, and the **definitive API
   witness** `/v1/sessions/AUD_USD` → `degraded_inputs =
['MYAGM1CNM189N:stale']` — the genuine dead China-M1 manifest
   (r93/r94 ground-truth) captured from the DataPool → SSOT-serialized →
   persisted → projected through `SessionCardOut`, exactly as designed.
   Tri-state proven live: legacy=`null`, degraded=`[China-M1:stale]`.

**Honest note (calibrated, lesson #11 — do not oversell):** the in-SSH
`psql` `first_series` column rendered blank because of an over-clever
`chr()`-built JSON key-path in my verification script (a quoting
work-around). That is a **verification-script display artifact, NOT a
data defect** — `n_degraded=1`, `degraded_not_null=t`, and the
authoritative API witness (`['MYAGM1CNM189N:stale']`) definitively prove
the persisted data is correct.

## Flagged residuals (NOT fixed — scope discipline)

- **r96 = the frontend `/briefing` degraded-data badge** — the binding
  contract is now written in ADR-104 §Cross-endpoint (consume only the
  card `/v1/sessions` field; `null`→"intégrité non suivie"; pure
  `lib/dataIntegrity.ts` SSOT + thin client component, `PocketSkillBadge`
  house style, placement `[asset]/page.tsx:224↔226`; no new fetch).
- **Every pre-0050 card is permanently `degraded_inputs: null`**
  ("not tracked at generation" — correct & honest; the badge can only
  assert health for post-deploy cards). Backfill impossible without
  re-deriving historical FRED state (never honest to fabricate).
- `0050` is now on Hetzner; **alembic head = 0050** (was 0049 r93/r94).
- Carried forward (r91/r92/r93/r94): vitest/vite peer-skew repo-wide
  realign (verdict + fred-liveness + data_integrity tests in CI) ;
  README/ADR `## Index` back-fill 077→104 (stale since ADR-076,
  anti-noise — no lone row added here, consistent r89-r94) ; GBP
  Driver-3 (`IR3TIB01GBM156N`) ; cron 365d/yr holiday-gate (HIGH
  blast-radius) ; Pass-6 occasional ADR-017-token retry ; Dependabot 3
  main vulns (r49 baseline) ; KeyLevelsPanel $5 polymarket joke market.

## Process lessons (durable)

- **Point-in-time honesty is the deciding doctrine, not effort.** The
  no-migration sidecar was cheaper but temporally dishonest; the
  data-honesty doctrine (the whole r93→r94 arc) made the
  higher-effort persist-on-card the only correct design. "marche
  exactement" decides architecture, not the path of least resistance.
- **Expand-pattern, empirically proven:** an additive **nullable, no
  default** column applied BEFORE the code that maps it = old running
  code is unaffected (SQLAlchemy only SELECTs mapped columns); the
  offline `--sql` audit + the metadata-only nature make it provably
  non-destructive. Migration-before-code is the safe ordering when
  `redeploy-api.sh` does not carry migrations (R59: it syncs only the
  `ichor_api` package — discovered, not guessed).
- **ichor-trader catches the r94-class consumption asymmetry even at
  0 RED.** Two endpoints exposing a same-named field with different
  null-semantics is a latent trap; closing it as a written ADR contract
  in the same round (not leaving it for r96 to re-discover) is the
  doctrine-complete move.
- **A verification-script display artifact is not a data defect** —
  separate the witness instrument from the result; the API witness was
  the ground truth (R59 applied to my own tooling).

## Next

**Default sans pivot:** ADR-099 **Tier 3 autonomy hardening continues** —
R59 first, pick highest value/effort: **r96 the frontend `/briefing`
degraded-data badge** (the natural continuation — ADR-104 §Cross-endpoint
is its binding contract; pure `lib/dataIntegrity.ts` SSOT + thin client
component, `redeploy-web2.sh`) ; or cron 365d/yr holiday-gate (HIGH
blast-radius — register-cron/systemd 2026-05-04 class, PRUDENCE + R59 +
infra-auditor) ; or GBP Driver-3 (`IR3TIB01GBM156N` ingestion + R53
prod-DB liveness first). Then the r91/r92 doc/infra-hygiene flags →
Tier 4 premium UI. The next `continue` executes this default unless
Eliot pivots.

**Session depth:** this is round 1 of a fresh post-/clear session (r95
only) — NOT deep ; no /clear/handoff needed. pickup v26 + this
SESSION_LOG are the current resume anchor (current through r95).
