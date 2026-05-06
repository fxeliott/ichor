# Model card — `logistic-bias-eurusd-1h-v0`

## Model details

- **ID**: `logistic-bias-eurusd-1h-v0`
- **Family**: L2-regularized logistic regression (`scikit-learn`)
- **Owner**: Ichor bias agent
- **Status**: planned — Phase 0 W2 step 12
- **Expected Brier**: 0.22 on hold-out

## Intended use

Linear baseline: any non-linear model added to the ensemble must beat this
in cross-val Brier _plus_ improve ensemble Brier marginally — otherwise we
keep the simpler model.

Same inputs / outputs as the LightGBM card. Features standardized
(mean-0, var-1 per training fold) before fit.

## Differences from tree models

- Inherently calibrated (no need for isotonic post-hoc, but we run it
  anyway for consistency).
- Coefficients are interpretable — useful for sanity-checking new feature
  additions.

## Caveats & failure modes

- Misses non-linearities (regime interactions). Expect lower Brier than
  boosters but more robust under distribution shift.
- Latency: < 1 ms.

## Aggregator weight

Initial weight: 0.10 — kept as a regularizer + interpretability anchor.
