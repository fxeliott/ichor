# SESSION LOG — 2026-06-13 · S06 Chantier B slice-1 : conviction calibration (ADR-117)

> Re-fire #6 of the S06 prompt on **Opus 4.8** ("fais tout, ne t'arrête jamais,
> décide seul, 100× plus loin"). Read honestly: the owner kept re-firing because
> I kept **stopping to ask** (`go deploy` / `go B`) — which violates his "ne
> t'arrête jamais sauf pour me solliciter". So this turn I **decided and built**,
> no menu: started Chantier B (the learning loop), which the Chantier A witness
> (ADR-116) had just proven necessary (conviction Brier 0.38 OOS).

## 1. Fresh-context audit of the existing learning machinery (workflow `wf_c0123b58-112`)

3 fresh subagents (mitigating my own deep-context rot) mapped what exists:

- ALL measurement plumbing exists: `brier.reliability_buckets`/`summarize`,
  `brier_feedback`, `post_mortem`, ADWIN drift, the Vovk aggregator.
- ONE outcome→live loop closes: `brier_optimizer` fits **confluence-factor**
  weights (projected SGD + 21-day holdout), live-read by `confluence_engine`.
- **THE GAP**: nothing recalibrates the **conviction itself** from realised
  outcomes. `brier.conviction_to_p_up` is a fixed affine rule; `conviction_fusion`
  "intentionally takes no learned weight"; the empirical reliability curve is
  computed but consumed only by a read-only diagnostic — never written back.
  That gap **is** the Brier-0.38 finding = the canonical Chantier B target.

## 2. slice-1 built (ADR-117, commit `a6c7198`, PR #243)

`services/conviction_calibration.py` — pure-core, I/O-free, NOT live-wired:

- `_pav` weighted pool-adjacent-violators isotonic fit.
- `fit_from_reliability` / `fit_from_pairs` fit `raw P_up → calibrated P_up` from
  the existing `brier.reliability_buckets` (reuses, reinvents nothing).
- `ConvictionCalibrator.apply` (interpolated map) + `calibrate_conviction`
  (shrinks over-confident conviction; ADR-017 never flips — wrong-side → 0;
  ADR-022 cap 95).
- `brier_improvement` (raw vs calibrated).
- 17 unit tests (PAV hand-computed, interpolation, shrink, isotonic in-sample
  optimality, no-flip, cap, identity); ruff + mypy clean.

## 3. ★ Read-only OOS witness — an HONEST NEGATIVE result

Fit on a temporal train split of real reconciled directional verdicts, measured
raw vs calibrated Brier on a disjoint OOS test split (read-only prod pull + local
run; no prod write):

|                        | raw Brier | calibrated | delta              |
| ---------------------- | --------- | ---------- | ------------------ |
| in-sample (24)         | 0.2764    | 0.2381     | −0.038 (better)    |
| **out-of-sample (11)** | 0.2593    | 0.3006     | **+0.041 (WORSE)** |

**On ~24 train samples the calibrator OVERFITS**: it improves in-sample (isotonic
guarantees this) but **degrades OOS**. Exactly the thin-data risk ADR-117 flagged.
The OOS witness therefore **validates the gating**: we do NOT wire it live,
because the OOS Brier does not improve. The approach is sound; it needs more
sessions (and likely shrinkage/regularisation) before it earns a live slot. A
negative result, reported faithfully — the anti-overfitting honesty the project
is built on.

## 4. State / next

- Chantier A: **done + witnessed** (PR #242, 11 commits, awaiting merge).
- Chantier B slice-1: **built + OOS-witnessed** (PR #243) → conclusion: do NOT
  wire live yet (overfits on N≈24). Next B slices: accumulate more reconciled
  sessions; add shrinkage/regularised calibration; re-run the OOS witness; only
  wire when OOS Brier genuinely improves. Then deploy+witness gate.
- Both PRs reversible, prod untouched (service `active`), zero spend.
