# Model card — `random-forest-bias-eurusd-1h-v0`

## Model details

- **ID**: `random-forest-bias-eurusd-1h-v0`
- **Family**: Random Forest classifier (`scikit-learn`)
- **Owner**: Ichor bias agent
- **Status**: planned — Phase 0 W2 step 12
- **Expected Brier**: 0.21 on hold-out

## Intended use

Bagging-based directional probability predictor. Lower variance than the
boosting siblings, useful as a diversity contributor in the ensemble.

Same inputs / outputs / training pipeline as the LightGBM card —
see [lightgbm-bias-v0.md](lightgbm-bias-v0.md).

## Differences from boosting

- Trees are independent — no sequential error correction.
- Robust to noisy features; doesn't need as much regularization tuning.
- Slightly worse calibration out of the box — isotonic critical here.

## Caveats & failure modes

- Memory-heavy at predict time with `n_estimators=500` — keep < 200 in prod.
- Latency: 5-15 ms per batch (slower than gradient boosting).

## Aggregator weight

Initial weight: 0.10 (lower than boosting given marginally worse Brier).
