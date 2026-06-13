# Session 2026-06-13 — S06 Chantier-B slice-2+3: regularised conviction calibration (Opus 4.8)

> Re-fire S06 ("es-tu sûr d'avoir traité à 100%, focus session 6", Opus 4.8).
> Lesson applied (CLAUDE.md ">2x = build, don't re-deliberate"): no decision
> menu — picked the NEXT autonomously and shipped it.

## Cadrage (vérifié à la source, pas supposé)

- S06 verdict engine exists (~52%); Chantier A (benchmark gate) = PR #242 OPEN,
  Chantier B slice-1 (isotonic calibration, ADR-117) = PR #243 OPEN, both
  MERGEABLE, unmerged; main = d3d6dbe [tool-output gh].
- slice-1 witness (ADR-116): the raw isotonic recalibrator OVERFITS the thin
  history — in-sample Brier 0.276→0.238 but **OOS 0.259→0.301 (WORSE) on N≈24**.
  Gate correctly held (not wired). NEXT B = regularised calibration + re-witness.

## Décision (autonome) & livrable — Chantier B slice-2+3, ADR-118

The named NEXT B. Pure-core, locally verifiable, **still gated** (not wired).

**slice-2 — regularised isotonic.** `fit_regularized(buckets, k)` shrinks the
slice-1 isotonic map toward the identity by `λ = N/(N+k)` (empirical-Bayes /
James-Stein). Within the fitted range it equals exactly `(1−λ)·p + λ·isotonic(p)`
(interpolation commutes with the convex blend) → monotonicity + ADR-017/022
carry over. `select_regularization_oos` picks `k` (incl. "no calibration") by
Brier on a disjoint split.

**slice-3 — Platt scaling.** `fit_platt(pairs)` fits `1/(1+exp(a·p+b))` by
regularised MLE (Lin–Lin–Weng 2007 Newton + Armijo line search, overflow-safe,
pure stdlib). The literature's low-variance first choice for small N. Single-
class → `None`. `select_calibrator_oos` arbitrates identity vs regularised
isotonic vs Platt on the SAME held-out split, returns the winner or `identity`
(honest by construction — only proposes a calibration that generalises OOS).

Files: `services/conviction_calibration.py` (+~360 lines: shrinkage, Platt, two
OOS selectors, shared `_conviction_from_p_up`, `SupportsApply`),
`tests/test_conviction_calibration.py` (18→46), `docs/decisions/ADR-118-*.md`.

## Evidence-based (web, primary sources — cf. ADR-118)

Niculescu-Mizil & Caruana ICML 2005 (isotonic overfits <~1000 pts, Platt
dominates small N) · Platt 1999 + Lin–Lin–Weng 2007 (regularised targets, stable
Newton) · Kull et al. AISTATS 2017 (beta calibration) · Efron–Morris 1973
(shrinkage) · Filho et al. arXiv:2112.10327 (OOS selection).

> **Caught a sign error** in one researched pseudocode (gradient `p−t` + `-=` =
> ascent). Implemented the canonical Lin–Lin–Weng step (`g=∇NLL=Σ(t−p)·[f,1]`,
> `Δ=−H⁻¹g`) by re-derivation, not copy. The "remets en question chaque détail".

## Vérification (runtime réelle)

- `pytest tests/test_conviction_calibration.py` → **46 passed** ; ruff All checks
  passed ; mypy Success no issues [tool-output]. Voie-D (zero spend).
- **Adversarial fresh-context verification** (workflow wf_7e4a7957, 4 lenses):
  - Platt MLE math: **CLEAN** — gradient sign verified by from-scratch derivation
    - finite-difference (|Δ|≈9.6e-10); Newton step verified vs brute-force GD
      (nll Δ≤4.4e-16); Hessian PD; Armijo correct; no overflow/NaN/infinite-loop.
  - Shrinkage + monotonicity: **CLEAN** (within-range == true blend confirmed).
  - Invariants (ADR-017 no-flip / ADR-022 cap) + OOS no-leakage + gating (module
    never imported by live code, grep-confirmed) + ADR no-overclaim + Voie-D:
    **CLEAN**.
  - Test quality: nits-only → **2 minors fixed** (strict Brier-margin assertion
    on Platt; added a test pinning `best_label='platt'` as the cross-family OOS
    winner on a smooth-overconfidence regime where isotonic overfits OOS).
- Full api suite: **3400 passed, 34 skipped** (was 3372; +28 = the new tests) —
  zero regression [tool-output, exit 0].

## État & NEXT (gated — pourquoi ça re-fire en boucle)

S06 reste un chantier multi-sessions. Ce slice avance la QUALITÉ du learning loop
mais ne change PAS le verdict live (gated). Les vrais déblocages restent **owner**:

1. ⭐ **merge + deploy PR #242 (+#243, +ce slice)** = checkpoint prod (guard
   Hetzner, j'exécute sur "go" — auto-deploy.yml sur push main OU redeploy-api.sh).
2. **Re-witness OOS** de la calibration (régularisée + Platt) sur data-prod
   accumulée (multi-jours) → si un candidat bat le raw OOS de façon soutenue,
   wiring `calibrate_conviction` dans `_derive_direction_and_conviction` (deploy+witness).
3. Puis Chantier C (≥9 DimensionVotes + risk agent + Bull/Bear) — gated B,
   prérequis golden-card harness (cf. ichor_chantier_c_slice1_blueprint).
4. D-half parallélisable (SSE push, arming scenario_invalidation_monitor après
   validation 3 sessions).

Branche `feat/s06-chantier-b-conviction-calibration` (PR #243). ssh
ichor-hetzner=178.104.39.201, DB read-only `sudo -u postgres psql -d ichor`.
