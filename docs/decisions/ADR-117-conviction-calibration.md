# ADR-117 — Conviction calibration from realised outcomes (Chantier B, slice-1)

- **Status:** Accepted (slice-1 pure-core, NOT live-wired) — 2026-06-13
- **Deciders:** owner (delegated "fais tout, décide seul"), engine
- **Supersedes:** none
- **Related:** ADR-116 (benchmark witness) · ADR-114 · ADR-022 (cap-95) ·
  ADR-017 · ADR-009 (Voie D) · `services/brier.py` · `conviction_fusion.py` ·
  PLAN_DIRECTEUR §5 Chantier B (learning loop)

## Context

Chantier A is done and **witnessed** (ADR-116): on ~1 month of real data the
verdict's conviction is **poorly calibrated** — OOS Brier **0.38**, worse than
the 0.25 no-skill reference; the hit-rate IC95 spans 50%. A "long 90 %" does not
close up 90 % of the time.

A fresh-context audit of the existing machinery found: all the **measurement**
plumbing exists (`brier.reliability_buckets`/`summarize`, `brier_feedback`,
`post_mortem`, the Vovk aggregator) and ONE outcome→live loop closes
(`brier_optimizer` fits _confluence-factor_ weights, live-read by
`confluence_engine`). **But nothing recalibrates the CONVICTION itself from
realised outcomes**: `brier.conviction_to_p_up` is a fixed affine rule,
`conviction_fusion` "intentionally takes no learned weight", and the empirical
reliability curve is computed but consumed only by a read-only diagnostic — never
written back. That gap is exactly the Brier-0.38 finding. It is the canonical
Chantier B (learning loop) target.

## Decision

Introduce `services/conviction_calibration.py` — a **pure-core, I/O-free**
conviction reliability recalibrator (the first learning-loop slice):

- `fit_from_reliability` / `fit_from_pairs` fit a **monotonic isotonic
  (pool-adjacent-violators)** map `raw P_up → calibrated P_up` from the EXISTING
  reliability buckets (`brier.reliability_buckets`) — reusing the canonical
  primitives, reinventing nothing.
- `ConvictionCalibrator.apply` interpolates the map; `calibrate_conviction`
  shrinks/grows a `(bias, conviction)` toward the realised frequency.
- `brier_improvement` reports `(raw, calibrated)` mean Brier.

**Slice scope (this ADR):** pure compute + read-only fit/apply + a read-only
witness only. **NO live wiring** — the verdict still emits its raw conviction.
Wiring `calibrate_conviction` into `_derive_direction_and_conviction` is a
behaviour change deferred to a later GATED step that must first witness, OUT-OF-
SAMPLE, that the calibrated Brier actually beats the raw Brier on enough sessions.
Mirrors the S04 `conviction_fusion` discipline (pure core first, gated
integration later).

**Doctrine alignment:**

- **ADR-009 (Voie D):** zero LLM / IO / spend — pure arithmetic.
- **ADR-017:** direction stays bucket-derived; calibration shrinks/grows the
  conviction MAGNITUDE only. If the calibration lands on the wrong side of 0.5
  for the bias, conviction → 0 — it never flips a direction nor emits an order.
- **ADR-022:** calibrated conviction clamped 0..95.

## Consequences

- **+** The learning loop's first, falsifiable slice exists: conviction can be
  corrected by its own track-record, attacking the Brier-0.38 finding with data
  and primitives that already exist, zero new infra.
- **+** Pure-core → fully unit-tested (PAV, interpolation, shrink, isotonic
  in-sample optimality, ADR-017 no-flip, ADR-022 cap). Zero risk to the live
  verdict (not wired).
- **−** No live effect yet; the headline "does it help OUT-OF-SAMPLE" number
  needs a train/test witness on real data (this session: read-only) and, before
  any live wiring, a deploy+witness gate.
- **Risk:** thin history (~65 in-sample / 32 OOS sessions) → the fit is noisy.
  In-sample Brier is TYPICALLY but **not guaranteed** improved: the PAV fits
  bucket means, while per-sample Brier is scored through a clamping/interpolating
  map, so an in-sample forecast below the first knot can be hurt (verifier-
  confirmed). Therefore ONLY the OOS witness is meaningful, reporting N honestly
  (a small-sample delta is suggestive, not conclusive — same discipline as
  ADR-116's IC95 guard).

## Gate (pass/fail, falsifiable)

slice-1 code: the calibrator fits a monotonic map, shrinks over-confident
conviction, never flips direction, caps at 95, is identity on thin data; ruff +
mypy + tests green. (Met by this slice.)

slice-1 witness (read-only, this session): fit on a train split of real
reconciled verdicts, measure raw vs calibrated Brier on a disjoint OOS test
split — report the delta and N honestly.

live wiring (future, GATED): inject `calibrate_conviction` into the verdict only
after an OOS witness shows a real, sustained Brier improvement; deploy + witness.
