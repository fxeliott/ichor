# Session 2026-06-14 — S06 Chantier C · C-2a votes seam (Opus 4.8)

> Continuation of the same session (owner re-fire "es-tu sûr à 100%, va 100x plus
> loin, ne t'arrête jamais, focus session 6"). Doctrine ">2x = construis, ne
> re-délibère pas" → instead of re-asserting C-1 done, shipped the next functional
> slice. Branch `feat/s06-chantier-c2-votes-param` = slice-0 (`DimensionVote`,
> PR #244) + C-1 (golden harness) merged + this C-2a. Model = Opus 4.8.

## What shipped (slice C-2a) — additive, flag-OFF byte-identical

The conviction fuser fused 3 layers (confluence / dollar / theme). C-2a adds the
**seam** for the ≥9 `DimensionVote` layers of Chantier C, WITHOUT wiring any real
layer yet (that is C-3) and WITHOUT touching the live prod path (the DB
`feature_flags` gate is C-2b — deliberately deferred, see below).

- `services/conviction_fusion.py` — `fuse_conviction` gains
  `votes: Sequence[DimensionVote] = ()`. When populated, each layer feeds the SAME
  agreement-factor math: `net_dimension_vote(votes) * direction_num` (directional,
  agreement-signed against the bucket edge) + `total_uncertainty_credit(votes)`
  (non-directional, like `theme`). A per-vote pass appends provenance to
  `agreeing` / `disagreeing` for transparency. **Direction stays bucket-derived
  (ADR-017)** — votes only move magnitude. Imports the stdlib-only
  `dimension_vote` contract (no cycle, Voie-D pure).
- `services/session_verdict_builder.py` — `_derive_direction_and_conviction` gains
  `votes: Sequence[DimensionVote] = ()`, forwarded verbatim to the fuser
  (`DimensionVote` imported under `TYPE_CHECKING`; no runtime cycle).
- `tests/test_conviction_fusion_votes.py` — 13 flag-ON tests (15 cases).

With `votes == ()` every added term is 0 and the loop is empty ⇒ **byte-identical**
to the legacy 3-layer path. Callers do not pass `votes` yet, so behaviour in prod
is unchanged once merged+deployed.

## Why this is safe (the C-1 harness pays off)

The C-1 golden harness (`assert_fuser_golden` over 179 cases) re-runs GREEN against
the new signature — it proves, byte-for-byte, that the flag-OFF path did not drift.
This is exactly what C-1 was built for.

## Verification (real runtime)

- `test_conviction_fusion_votes.py` → **15 passed**: aligned vote promotes (66.0),
  opposed demotes (54.0, direction unchanged), votes stack (72.0), **AGREEMENT_FLOOR
  (0.60) now reached** (the 3-layer fuser never could), cap-95 preserved under 10
  aligned votes, 20 opposed votes never flip direction (ADR-017), absent/stale/zero
  contribute 0, non-directional adds credit only, freshness scales, no trade tokens.
- Byte-identity: golden harness + pinned `test_conviction_fusion` (60/70/79/128/177)
  - seam + invariants → **90 passed**; golden harness alone (179 cases) **35 passed**.
- Full api suite → **3527 passed, 35 skipped** (3512 → +15, zero regression).
- `ruff check` / `ruff format` clean. `mypy` on the 2 prod files: 0 NEW errors
  (11 pre-existing `EconomicEvent`/`Select` errors in an unrelated function, proven
  identical with edits stashed). Diff = 2 prod files, +45 / -3 lines.
- **Fresh adversarial verifier**: 0 blockers / 0 majors / 0 minors. Confirmed by
  real execution: no double-counting (the provenance loop adds nothing to
  `net_vote`), correct sign on down-bias, direction never flips, bounds hold, no
  import cycle, Voie-D pure.

## Deferred ON PURPOSE (not done here)

- **C-2b** — the DB `feature_flags` gate in `build_session_verdict` (async prod
  path). It is INERT until real votes exist, so it belongs with C-3.
- **C-3** — map the S04 layers + new dimensions (rates, positioning, geopolitics —
  see the GPR doctrine in `[[ichor-chantier-c-slice1-blueprint]]`) onto
  `DimensionVote` and pass them through, behind the flag. Add the full-`card_verdict`
  guard (the harness covers fuser+seam only).

Owner gate: push / PR / merge / deploy is owner-only. C-2a is a LOCAL commit.

## NEXT

`go Chantier C C-2b/C-3` (fresh session): wire the `feature_flags` gate +
≥9 real dimensions, golden-diff each, one dimension at a time. Owner merges
slice-0 (#244) → C-1 → C-2a → C-2b/C-3 in order.
