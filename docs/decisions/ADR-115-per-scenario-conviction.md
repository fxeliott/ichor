# ADR-115 — Per-scenario conviction (S06 verdict granularity)

- **Status:** Accepted — 2026-06-13
- **Deciders:** owner (delegated "fais tout, décide seul"), engine
- **Related:** ADR-085 (Pass-6 scenario_decompose) · ADR-022 (cap-95) ·
  ADR-017 (no BUY/SELL) · ADR-106 (SessionVerdict) · PLAN_DIRECTEUR §5ter-bis ·
  Session 06 spec ("chacun assorti de sa conviction ET de sa probabilité")

## Context

Session 06 spec requires, verbatim, that the verdict expose scenarios « chacun
assorti de **sa conviction** ET **de sa probabilité**, pour chaque détail », and
PLAN_DIRECTEUR §5ter-bis lists "Verdict granularity : **per-scenario conviction
AND probability**".

Today the `Scenario` model (`packages/ichor_brain/scenarios.py`) carries **only
`p`** (probability the bucket realizes). There is no per-scenario conviction —
only a single aggregate `SessionVerdict.conviction_pct`. This is a genuine,
literal S06 gap (verified : `scenarios.py:263` has `p`, no conviction field).

`p` and conviction are **distinct**: `p` is _how likely_ a bucket is; conviction
is _how confident Ichor is in that probability estimate_ (evidence strength). A
bucket can have low `p` yet high conviction ("confident it will NOT fire").

## Decision

Add an **optional, backward-compatible** `conviction_pct: float | None` field to
`Scenario`, on the ADR-022 0..95 scale, default `None`. Expose a pure read
helper `ScenarioDecomposition.per_scenario_conviction()`.

This follows the **exact precedent of the r161 Strand-A `invalidations` field**:
additive, default-empty/None, backward-compatible — pre-ADR-115 Pass-6 JSONB rows
deserialise cleanly (`None`), and the existing verdict derivation (which reads
`p` only) is **byte-unchanged** (golden-card diff preserved). A future Pass-6
prompt update will populate the field; downstream consumers no-op on `None`.

**Slice scope (this ADR):** the schema field + validator + read helper + tests +
zero-regression proof. NOT in scope (deferred): the Pass-6 LLM prompt update that
populates the field, and any change to the verdict's aggregate-conviction
formula to weight by per-scenario conviction (that would be a behaviour change
requiring its own deploy+witness).

**Doctrine alignment:**

- ADR-022 : `conviction_pct` capped at `CAP_95 * 100 = 95.0` (mirror of
  `SessionVerdict.conviction_pct`).
- ADR-017 : a number, never an order — no prose, no token risk.
- Doctrine #2 strict scope : additive field, no new pass, no migration
  (scenarios are JSONB in `session_card_audit`).

## Consequences

- **+** Closes the literal S06 "per-scenario conviction AND probability" gap at
  the schema level; the frontend/consumers can surface per-bucket conviction.
- **+** Zero behaviour change to the witnessed verdict derivation (proved by
  running the existing scenarios + invariants + verdict-builder suites green).
- **+** Backward-compatible: old emissions deserialise to `None`.
- **−** The field is `None` in production until the Pass-6 prompt is updated to
  emit it (a follow-up slice, owner-sequenced) — surfaced honestly, not faked.
- **Risk:** an invariant test enumerating `Scenario`'s field set must be updated
  to include the new optional field (intentional contract change, documented
  here). The new API output gains `conviction_pct: null` per scenario (additive,
  structurally ignored by the frontend unless it strict-parses — verified low
  risk; the per-asset surface does not strict-reject extra fields).

## Gate (falsifiable)

- `Scenario` accepts/defaults/caps `conviction_pct`; `per_scenario_conviction()`
  returns the per-bucket map; pre-ADR-115 dicts (no field) deserialise to `None`.
- Existing scenarios + invariants + verdict-builder test suites stay green
  (golden-card diff = behaviour unchanged). ruff + mypy clean.
