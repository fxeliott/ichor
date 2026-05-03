# Model card — `xgboost-bias-eurusd-1h-v0`

## Model details

- **ID**: `xgboost-bias-eurusd-1h-v0`
- **Family**: XGBoost gradient-boosted decision trees
- **Owner**: Ichor bias agent
- **Status**: planned — Phase 0 W2 step 12
- **Expected Brier**: 0.20 on hold-out

## Intended use

Sibling of `lightgbm-bias-eurusd-1h-v0` with a different boosting
implementation. Kept in the ensemble for diversity (correlations between
LightGBM/XGBoost residuals are non-zero but typically < 0.7).

Same inputs / outputs / training pipeline as the LightGBM card —
see [lightgbm-bias-v0.md](lightgbm-bias-v0.md) for full details.

## Differences from LightGBM

- Uses `hist` tree method (matches LightGBM's leaf-wise growth approximation)
- Higher regularization defaults (`reg_lambda=1`, `reg_alpha=0.5`)
- Slightly slower training, comparable inference latency

## Caveats & failure modes

- Same as LightGBM: regime sensitivity, retrain weekly.
- If LightGBM and XGBoost predictions correlate > 0.95 over 30d, deprecate
  one to reduce ensemble redundancy.

## Aggregator weight

Initial weight after promotion to `live`: 0.15.
