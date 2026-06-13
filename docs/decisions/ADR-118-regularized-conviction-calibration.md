# ADR-118 — Regularised conviction calibration for small samples (Chantier B, slice-2 + slice-3)

- **Status:** Accepted (pure-core, NOT live-wired) — 2026-06-13
- **Deciders:** owner (delegated "fais tout, décide seul"), engine (Opus 4.8)
- **Supersedes:** none
- **Extends:** ADR-117 (slice-1 isotonic calibration)
- **Related:** ADR-116 (benchmark witness) · ADR-022 (cap-95) · ADR-017
  (no-flip) · ADR-009 (Voie D) · `services/brier.py` · `conviction_fusion.py` ·
  PLAN_DIRECTEUR §5 Chantier B (learning loop)

## Context

ADR-117 shipped slice-1: a monotonic isotonic (pool-adjacent-violators)
recalibrator of the verdict conviction. Its **read-only OOS witness** (ADR-116
methodology, ~24–32 reconciled sessions) found the honest, expected failure of a
non-parametric fit on a thin sample:

- in-sample Brier improved 0.276 → 0.238,
- **out-of-sample Brier got WORSE: 0.259 → 0.301** (N≈24).

This is textbook isotonic overfitting on a small calibration set. The slice-1
gate was therefore correctly held: the calibrator is **not wired live**. The
named NEXT (auto_session_resume) was _"+ data + regularised calibration +
re-witness OOS before wiring"_. This ADR delivers the **regularised calibration**
half — pure-core, locally verifiable, still gated.

### Evidence (web-verified, primary sources)

- Isotonic regression has degrees of freedom bounded by N, not a fixed parameter
  count, so on a few dozen points it interpolates noise. Below ~1000 calibration
  points it overfits and **Platt scaling dominates** — _"isotonic regression …
  has more degrees of freedom than Platt Scaling, so it is easier for it to
  overfit when the calibration set is small."_ [Niculescu-Mizil & Caruana, ICML
  2005, https://www.cs.cornell.edu/~alexn/papers/calibration.icml05.crc.rev3.pdf]
  Confirmed by the reference survey [Filho et al., arXiv:2112.10327].
- **Platt scaling** (2 parameters) is the consensus low-variance choice for
  small N, with **regularised targets** `t+ = (N_pos+1)/(N_pos+2)`,
  `t- = 1/(N_neg+2)` that keep the log-loss finite on a confident sample
  [Platt 1999; numerically-stable Newton: Lin, Lin & Weng, *Machine Learning*
  2007, https://link.springer.com/content/pdf/10.1007/s10994-007-5018-6.pdf].
- **Shrinkage toward a prior** `θ̂ = N/(N+k)·fit + k/(N+k)·prior` is the
  empirical-Bayes / James-Stein estimator [Efron & Morris 1973]. Applied to a
  calibration map it is a defensible **engineering heuristic** but is _not_
  formalised as a proven-optimal calibration recipe in the literature — recorded
  honestly as such.
- Calibration method/hyperparameter selection must be **out-of-sample**, never
  in-sample [Filho et al., arXiv:2112.10327].

> A sign error was found in one researched pseudocode (gradient `p−t` with a
> `-=` update = ascent). The implementation follows the canonical Lin–Lin–Weng
> (2007) Newton step (`g = ∇NLL = Σ(t−p)·[f,1]`, `Δ = −H⁻¹g`, Armijo line
> search) — verified by re-derivation, not copied.

## Decision

Extend `services/conviction_calibration.py` (pure-core, I/O-free, Voie-D) with
two low-variance calibration candidates and an honest out-of-sample arbiter.

**slice-2 — regularised isotonic (shrinkage toward identity).**
`fit_regularized(buckets, k)` shrinks the slice-1 isotonic map toward the
identity by `λ = N/(N+k)` (N = realised observations across populated bins).
Small N → λ→0 → identity (no correction, no overfit); large N → λ→1 → full fit.
The blend is applied to the knot ordinates: within the fitted range it equals
**exactly** `(1−λ)·p + λ·isotonic(p)` (linear interpolation commutes with the
convex blend), so monotonicity and every ADR-017/022 invariant carry over
unchanged. `k=0` recovers slice-1 isotonic. `select_regularization_oos` picks
`k` (including "no calibration") by Brier on a disjoint test split.

**slice-3 — Platt scaling (the literature's small-N first choice).**
`fit_platt(pairs)` fits `P_up → 1/(1+exp(a·P_up+b))` by regularised MLE
(Lin–Lin–Weng 2007 Newton + line search, overflow-safe, pure stdlib). Single-
class samples return `None` (a 2-param sigmoid is unidentifiable). `PlattCalibrator`
shares the ADR-017/022 conviction rule via `_conviction_from_p_up`.

**Cross-family OOS arbiter.** `select_calibrator_oos(train, test)` scores
identity, regularised isotonic over candidate `k`, and Platt on the **same
disjoint test split** and returns the winner — or `identity` when nothing beats
"do not calibrate". This makes the learning loop **honest by construction**: it
only proposes a calibration that demonstrably generalises out-of-sample.

**Scope (this ADR): pure compute + read-only selection only. NO live wiring.**
The verdict still emits its raw conviction. Wiring the selected calibrator into
`_derive_direction_and_conviction` stays a later GATED step that must first
witness, OUT-OF-SAMPLE on enough real sessions (and after merge+deploy), that the
calibrated Brier beats the raw Brier. Same discipline as ADR-117.

## Consequences

- **+** The learning loop now carries **low-variance candidates** (Platt, shrunk
  isotonic) that the literature predicts will generalise better than the slice-1
  isotonic on the thin history actually available — the direct, evidence-grounded
  response to the overfit finding.
- **+** The OOS arbiter can **decline to calibrate**, so the loop never makes the
  conviction worse than raw on held-out data. Honest by construction.
- **+** Pure-core, fully unit-tested (45 tests on the module), zero new infra,
  zero risk to the live verdict (not wired). Voie-D (zero LLM/IO/spend).
- **−** No live effect yet; still needs a real OOS witness (data-prod + multi-day
  accumulation) and a deploy gate before any wiring.
- **Risk:** with N≈24–32 even Platt/shrunk-isotonic may not show a stable OOS
  gain — the arbiter must then honestly return `identity`. Selection on a single
  small split is itself noisy; leave-one-out / k-fold is the future hardening
  [Filho et al., arXiv:2112.10327].

## Gate (pass/fail, falsifiable)

- slice-2/3 code: regularised isotonic shrinks toward identity by `N/(N+k)` and
  preserves monotonicity + ADR-017/022; Platt fits a stable 2-param sigmoid with
  regularised targets and returns `None` on a single-class sample; the OOS
  arbiter always includes identity and only reports `improved` when a method
  strictly beats it; ruff + mypy + 45 tests green. **(Met by this slice.)**
- live wiring (future, GATED): inject the OOS-selected calibrator into the
  verdict only after a real OOS witness shows a sustained Brier improvement on
  enough reconciled sessions; deploy + witness.
