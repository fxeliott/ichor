# ADR-104: Degraded-inputs persisted on the session card (ADR-099 §T3.2 end-user completion)

**Status**: **Accepted** (round-95, 2026-05-17) — thin child **implementing** the
end-user-visibility completion of [ADR-099](ADR-099-north-star-architecture-and-staged-roadmap.md)
§T3.2 ("Human-visible degraded-data alert — break the silent-skip chain"), under Eliot's
standing full-autonomy delegation ("autonomie totale ; décide et annonce, ne demande pas")
and the per-round default-Option contract (doctrine #10). Builds on the
**Accepted/immutable** [ADR-103](ADR-103-runtime-fred-liveness-degraded-data-explicit-surface.md)
runtime liveness surface — **ADR-103 is not amended**; this is the doctrinally-correct child
vehicle (ADR-101/102/103 precedent).

**Date**: 2026-05-17

**Supersedes**: none

**Extends**: [ADR-103](ADR-103-runtime-fred-liveness-degraded-data-explicit-surface.md) (the
r93 runtime `DataPool.degraded_inputs` foundation — this ADR carries that exact structure
through the **card persistence boundary** so the end user, not only the LLM and the operator,
sees it), [ADR-099](ADR-099-north-star-architecture-and-staged-roadmap.md) §T3.2 + §D-2
("every layer COVERED **or explicitly DEGRADED — never silently absent**" — r93 satisfied the
LLM-input + operator surface; this ADR is the end-user-surface satisfaction),
[ADR-009](ADR-009-voie-d-no-api-consumption.md) (Voie D — zero paid feeds, zero LLM call,
pure deterministic persistence), [ADR-017](ADR-017-reset-phase1-living-macro-entity.md)
(data-provenance vocabulary only — the projected field is structured provenance, never a
signal).

**Related**: r96 frontend follow-up — the dedicated `/briefing` degraded-data badge (pure
`apps/web2/lib/dataIntegrity.ts` SSOT + a thin client component mirroring the
`PocketSkillBadge` house style, placed adjacent to it in the per-asset page hierarchy),
consuming the field this ADR projects **from the existing `/v1/sessions/{asset}` fetch — no
new fetch, no `/v1/data-pool` sidecar**. Deliberately a separate round per the proven
r76→r77 / r80→r81 backend-then-frontend split and "1 incrément vérifié / n'accumule pas".

**Honest provenance note** (immutable-ADR discipline, doctrine #9): ADR-103 §Related/§Negative
anticipated this child as the "r94 follow-up". r94 was instead consumed by the ADR-092
`PIORECRUSDM`/`PCOPPUSDM` 60→120 d recalibration that ADR-103's _own first live signal_
surfaced (a true-positive mechanism find — see ADR-103 §Amendment(r94)). The end-user badge
is therefore r95 (this ADR, backend persist + projection) + r96 (frontend). ADR-103's "r94"
wording is left intact for archaeology — history is not rewritten, the evolution is recorded
here.

## Context

ADR-103 (r93) broke the silent-skip chain at **two** of three consumer surfaces: the LLM
input (primed `_section_data_integrity` top-of-pool + deterministic header) and the operator
(`GET /v1/data-pool/{asset}` `DataPoolOut.degraded_inputs`). The **third consumer — the end
user reading `/briefing` — still has zero visibility.** R59 inspection (round-95,
file:line-verified, not guessed):

- The `/briefing` per-asset page (`apps/web2/app/briefing/[asset]/page.tsx`) and cockpit
  (`app/briefing/page.tsx`) fetch the card via `apiGet<SessionCardList>(/v1/sessions/{asset}
?limit=1)` → `SessionCardListOut.items[0]` → `SessionCardOut.from_orm_row(SessionCardAudit)`
  (`routers/sessions.py:77,104`; `schemas.py:317,390`).
- `SessionCardOut` (`schemas.py:317-410`) has **no** `degraded_inputs`/integrity field and is
  `from_attributes`-bound (`schemas.py:387`) to `SessionCardAudit`
  (`models/session_card_audit.py:24-103`), which has **no** such column. This is the
  Pydantic-projection-gap class (doctrine #1, r66/r68) at the **persist** boundary.
- `degraded_inputs` is produced only by `build_data_pool` → `_section_data_integrity`
  (`data_pool.py:4516,438`) on the `DataPool` dataclass (`data_pool.py:230`), projected only
  onto the live-recompute operator/debug endpoint `/v1/data-pool/{asset}`
  (`routers/data_pool.py:48`), and is **dropped at card-persist**: `run_session_card.py:321`
  does `row = to_audit_row(card_with_levels)` where `to_audit_row(card: SessionCard)`
  (`ichor_brain/persistence.py:20-69`) maps the brain `SessionCard` → ORM row and never sees
  the `DataPool`. The only provenance persisted is the opaque 64-char `source_pool_hash`.

### Architecture decision (R59 + doctrine, not guess)

Two architectures were evaluated against the project's data-honesty doctrine ("marche
exactement", ADR-099 §D-2):

- **Live-fetch sidecar (no migration)** — the `/briefing` page additionally calls the
  existing `/v1/data-pool/{asset}`. **Rejected**: that endpoint is a heavy full-pool
  recompute _at page-load_; its `degraded_inputs` reflects the FRED state **now**, not at
  the persisted card's generation. A card generated hours ago on a dead China-M1 series
  would display "frais" if the live recompute differs — re-introducing the exact
  silent-skip dishonesty ADR-103 exists to kill, at the very surface meant to close it; and
  it mixes an operator/debug endpoint into the end-user serving path.
- **Persist-on-card (additive migration)** — **Chosen**: the badge reflects the data health
  of the card the user is _actually reading_, frozen at generation. Point-in-time honest —
  the only ADR-103-faithful design (mirrors why ADR-083 D3 froze `key_levels` at
  finalization rather than recomputing, ADR-093/0049 precedent).

## Decision (r95 scope = backend, end-to-end verifiable through `/v1/sessions/{asset}` JSON)

Purely additive, reversible. `to_audit_row` and every existing card column/path stay
**byte-identical** (anti-regression; r71/r91 extract-to-SSOT discipline):

1. **Extract `DegradedInputOut` to the `schemas.py` SSOT** (anti-accumulation doctrine #4 —
   the 6-field shape exists as the `DegradedInput` frozen dataclass `data_pool.py:256-269`
   and the `DegradedInputOut` Pydantic `routers/data_pool.py:25-36`; this round would be a
   3rd definition). Move the class **byte-identical** (same fields, same docstring) into
   `schemas.py`; `routers/data_pool.py` re-imports it (`from ..schemas import
DegradedInputOut`) so `DataPoolOut.degraded_inputs: list[DegradedInputOut]` is unchanged
   (identity-regression-pinned). `SessionCardOut` reuses the same class — producer↔both
   consumers share one shape by construction (the anti-projection-gap property itself).

2. **Migration 0050 — additive `degraded_inputs` JSONB on `session_card_audit`, NULLABLE,
   NO `server_default`.** This **deliberately diverges** from the 0049 `key_levels` /
   0039 `scenarios` `NOT NULL DEFAULT '[]'::jsonb` pattern, and that divergence is the core
   honesty decision of this ADR. Tri-state semantics:
   - **`NULL`** = "FRED-liveness was not tracked at this card's generation" — the honest
     state of **every** pre-0050 card (degradation tracking did not exist when it was
     generated). Backfilling them to `'[]'::jsonb` would falsely assert "all critical
     anchors were fresh" for cards that were never audited — the exact dishonesty ADR-103
     fights. NULL must mean _unknown_, not _clean_.
   - **`[]`** = "tracked at generation, all critical FRED anchors fresh".
   - **non-empty** = "generated on degraded inputs" (the per-series ADR-103 manifest).
     Reversible: `downgrade()` = `op.drop_column`. Adding a nullable column with no default
     and no backfill is a Postgres metadata-only operation (instant, no table rewrite, no
     long lock) even on the `session_card_audit` TimescaleDB hypertable.

3. **ORM**: `degraded_inputs: Mapped[Any | None] = mapped_column(JSONB)` on `SessionCardAudit`
   (nullable, no `server_default` — the documented divergence from `key_levels`/`scenarios`).

4. **Persist threading (surgical, `to_audit_row` untouched)**: in `run_session_card.py`,
   capture `degraded_inputs_payload` **symmetrically** in both data-pool branches (mirroring
   the existing `data_pool`/`asset_data` dual-branch assignment, since `pool` is bound only
   in the `if live:` branch): live → `[DegradedInputOut(...).model_dump(mode="json") for di
in pool.degraded_inputs]` (the SSOT model's `mode="json"` dump = guaranteed shape parity
   with the projection + `date`→ISO); dry-run → `None` (honest "not tracked"). After
   `row = to_audit_row(card_with_levels)`, set `row.degraded_inputs = degraded_inputs_payload`.
   `to_audit_row` (shared `ichor_brain.persistence`) is **not** modified — keeps the
   api←brain layering (the brain needn't know `DataPool`), keeps it byte-identical for all
   its other call sites and every other card column (zero regression surface).

5. **Project on `SessionCardOut`**: `degraded_inputs: list[DegradedInputOut] | None = None`
   (tri-state; auto-projected by the existing `model_validate(row)` in `from_orm_row`, like
   `key_levels`/`scenarios`). `None` for legacy/dry-run, `[]` tracked-fresh, list when
   degraded.

### Scope boundary (explicit, calibrated-honest — lesson #2 "shipped ≠ functional", doctrine #11)

r95 ships the **backend persistence + projection chain**, verifiable end-to-end on real prod
through `GET /v1/sessions/{asset}` JSON. The dedicated end-user `/briefing` badge component
(a `PocketSkillBadge`-style panel + a pure `lib/dataIntegrity.ts` SSOT, consuming the
now-projected field from the **existing** `/v1/sessions` fetch — no new fetch) is the
**announced r96 follow-up**. Bundling it here would be the migration-blast-radius +
accumulation Eliot forbids. ADR-099 §D-2 "never silently absent" reaches the **persisted
card / API surface** this round; the end-user-UI satisfaction is r96.

### Cross-endpoint contract — the r94-class consumption asymmetry, closed in-round (ichor-trader R28 YELLOW-1)

r95 makes `degraded_inputs` exist on **two** endpoints with **deliberately different
contracts** — and that asymmetry is a written invariant here, not a latent trap the r96
round must re-discover (the r94 lesson: widening a data-health surface creates a
consumption-point asymmetry that must be closed in the same round):

- **`GET /v1/data-pool/{asset}` → `DataPoolOut.degraded_inputs: list[DegradedInputOut]`** —
  ALWAYS present, **live recompute at request time**, never `null` (an operator/debug
  transparency tool; reflects FRED state _now_).
- **`GET /v1/sessions/{asset}` → `SessionCardOut.degraded_inputs: list[DegradedInputOut]
| None`** — **point-in-time**, frozen at the card's generation; **tri-state**: `null` =
  "FRED-liveness not tracked at this card's generation" (legacy/dry-run), `[]` = "tracked,
  all fresh", non-empty = "degraded".

These are **NOT the same contract**. The r96 end-user badge **MUST** read only the
card-bound `/v1/sessions` field (point-in-time honest — the data health of the card the
user is actually reading) and **MUST** render `null` as "intégrité des données : non
suivie" (data-health unknown) — **never** as "fraîche"/"all fresh". It must **not** fall
back to the live `/v1/data-pool` recompute for the badge (that would re-introduce the
exact temporal silent-skip dishonesty ADR-103 exists to kill, per §Context). This
paragraph is the binding r96 contract.

## Acceptance criteria

1. Migration 0050 `upgrade`/`downgrade` reversible; column is **nullable with no
   server_default** (asserted: a pre-existing card row reads `degraded_inputs IS NULL`,
   never `'[]'`).
2. `to_audit_row` byte-identical (regression: existing `ichor_brain` persistence + card
   tests pass unchanged).
3. `DegradedInputOut` re-export byte-identical — `routers.data_pool.DegradedInputOut is
schemas.DegradedInputOut` (identity test); `DataPoolOut` shape unchanged.
4. `SessionCardOut` tri-state projects: `None` (legacy/dry-run), `[]` (tracked, all fresh),
   list of the 6-field shape (degraded).
5. **Back-compat**: an existing (pre-0050) card via `GET /v1/sessions/{asset}` returns 200
   with `degraded_inputs: null` — no crash, no shape break (protects the r72–r84 panels
   that depend on `/v1/sessions`).
6. Empirical 3-witness (rule 18): ruff + pytest green incl. the byte-identity + tri-state
   tests; post-migration an existing prod card reads `null` (back-compat observed, not
   forecast); a freshly-generated `AUD_USD` card (the genuine China-M1 degradation, r94
   ground-truth) persists a non-NULL `degraded_inputs` carrying `MYAGM1CNM189N` and that
   value is observed in the live `/v1/sessions/AUD_USD` JSON.
7. Voie D (zero LLM call in the persist path) + ADR-017 (structured provenance, not a
   signal) held. `git revert` + alembic `downgrade` + `redeploy-api.sh rollback` fully
   reverse it; DB backed up before `alembic upgrade`.

## Reversibility

Additive nullable column (metadata-only on the hypertable) + `schemas.py` SSOT move +
one re-import line in `routers/data_pool.py` + one ORM line + one symmetric capture + one
assignment in `run_session_card.py` + one defaulted `SessionCardOut` field + tests + this
ADR. `downgrade()` drops the column; `git revert <commit>` reverses code; `redeploy-api.sh
rollback` reverses the deploy in <30 s; `alembic downgrade 0049` reverses the schema. DB
`pg_dump` of `session_card_audit` taken before `alembic upgrade` (KEYWORD MIGRATION
protocol).

## Consequences

### Positive

- **The end-user visibility loop of the r93→r94 data-honesty arc is closed,
  point-in-time-honest.** The badge (r96) will reflect the card's actual data health _at
  generation_, not a drifting recompute. ADR-099 §D-2 reaches the persisted card / API.
- **Anti-accumulation honored**: one `DegradedInputOut` SSOT, two consumers, identity-pinned.
- **Layering preserved**: the brain `to_audit_row` stays ignorant of `DataPool`
  (byte-identical); the api layer owns the cross-cut.
- **Tri-state honesty**: NULL≠[] is a deliberate, documented semantic — "unknown" is not
  "clean".

### Negative

- **Frontend badge deferred to r96** (honestly stated, not silently dropped) — r95
  human-visibility is the API JSON, not yet a rendered panel.
- **Every pre-0050 card is permanently `degraded_inputs: null`** ("not tracked at
  generation") — correct and honest, but the badge can only assert health for cards
  generated post-deploy. Backfill is impossible without re-deriving historical FRED state
  (out of scope, and arguably never honest to fabricate).
- AUD `source_pool_hash` already changes going forward (r94, unrelated to this ADR — noted
  to avoid mis-attribution).

### Neutral

- No Voie D / ADR-017 risk (deterministic persistence, structured provenance vocabulary);
  existing prod untouched (additive nullable); all existing Accepted ADRs remain valid;
  `docs/decisions/README.md` index back-fill (077→104) remains the separate flagged
  hygiene round (anti-noise, r89–r92 precedent — no lone row added here).

## Sources (round-95 R59 audit trail — file:line, tool-verified)

- `apps/web2/app/briefing/[asset]/page.tsx` (per-asset card fetch `/v1/sessions/{asset}`),
  `app/briefing/page.tsx` (cockpit), `apps/web2/lib/api.ts:171` (`SessionCard` TS — no
  degraded field).
- `routers/sessions.py:77,104` (`/v1/sessions/{asset}` → `SessionCardOut.from_orm_row`);
  `schemas.py:317-410` (`SessionCardOut`, no degraded field, `from_attributes`);
  `models/session_card_audit.py:24-103` (ORM, no degraded column).
- `services/data_pool.py:230` (`DataPool.degraded_inputs`), `:256-269` (`DegradedInput`
  frozen dataclass), `:438,4516` (`_section_data_integrity`); `routers/data_pool.py:25-36`
  (`DegradedInputOut` Pydantic, to be SSOT-extracted), `:48` (`DataPoolOut` projection).
- `cli/run_session_card.py:92` (`pool` bound, live-branch only), `:98` (`data_pool =
pool.markdown`, dual-branch assignment precedent), `:320-323` (`to_audit_row` + persist);
  `ichor_brain/persistence.py:20-69` (`to_audit_row`, to stay byte-identical).
- `migrations/versions/0049_session_card_key_levels.py` (additive-JSONB template; the
  NOT NULL DEFAULT pattern this ADR deliberately diverges from for honest tri-state).
- [ADR-103](ADR-103-runtime-fred-liveness-degraded-data-explicit-surface.md) §Related/§Scope
  boundary/§Negative (the anticipated child) + §Amendment(r94).

## Implementation (r96, 2026-05-17) — frontend badge shipped exactly as specified

The r96 follow-up named in §Related and bound by §Cross-endpoint was implemented as
specified (commit recorded in SESSION_LOG r96 / pickup §r96 — this ADR is committed within
that same commit, so its hash is not self-referenceable here; no fabricated hash). No new
ADR was authored: §Cross-endpoint **is** the r96 specification, and this dated note closes
the forward-reference per the immutable-ADR append discipline (doctrine #9 — history not
rewritten).

- **NEW pure SSOT `apps/web2/lib/dataIntegrity.ts`** (no `"use client"`, no React/JSX —
  RSC-safe, mirrors `lib/eventSurprise.ts`): `deriveDataIntegrity(degraded_inputs)` →
  discriminated `DataIntegritySummary` tri-state (`untracked` / `all_fresh` / `degraded`),
  all FR display strings precomputed in the pure module.
- **NEW thin client `apps/web2/components/briefing/DataIntegrityBadge.tsx`** mirroring the
  `EventSurpriseGauge` / `PocketSkillBadge` house style byte-faithfully; ADR-017 boundary
  footer on every state; renders nothing only when there is no card at all.
- **`apps/web2/lib/api.ts`**: new `DegradedInput` interface + `degraded_inputs:
DegradedInput[] | null` on `SessionCard` (mirrors the r95 backend wire shape exactly).
- **`apps/web2/app/briefing/[asset]/page.tsx`**: 1 component import + 1 SSOT import + the
  server-side `deriveDataIntegrity(card.degraded_inputs)` derive + the standalone
  `<DataIntegrityBadge>` placed between `<PocketSkillBadge>` and the "Niveaux clés" section
  (the epistemic-sibling placement specified in §Cross-endpoint / §Related).

§Cross-endpoint honored verbatim: consumes ONLY `SessionCard.degraded_inputs` (the
`/v1/sessions` card field), **no `/v1/data-pool` sidecar**, **no new fetch** (the card was
already fetched); `null` renders as "non suivie — absence d'information, à ne pas
interpréter comme un état sain", **never** as "fresh". Zero backend change, Voie D
(pure deterministic presentation, zero LLM), additive-only. See SESSION_LOG r96 for the
3-witness live verification on real prod data.
