# Model card — `lightgbm-bias-eurusd-1h-v0`

## Model details

- **ID**: `lightgbm-bias-eurusd-1h-v0`
- **Family**: LightGBM gradient-boosted decision trees
- **Owner**: Ichor bias agent
- **Status**: planned — Phase 0 W2 step 12
- **Expected Brier**: 0.20 on hold-out

## Intended use

Per-asset probability that a 1-hour-ahead bar will close higher than open
(`P(direction = long | features)`). Output is calibrated via isotonic
regression and consumed by `bias_aggregator` together with the other
predictor families.

### Out-of-scope

- Single asset (EUR/USD); per-asset variants planned post step 12.
- 1h horizon only; multi-horizon ensemble = Phase 1+.
- Not for execution sizing — directional probability only.

## Inputs / Outputs

- **Inputs (~30 features)**:
  - Returns: `r_5m`, `r_15m`, `r_1h`, `r_4h`, `r_1d`
  - Volatility: `RV_1h`, `RV_1d`, HAR-RV pred
  - Momentum: RSI(14), MACD, Stochastic
  - Microstructure: VPIN, order-flow imbalance
  - Calendar: hour-of-day, day-of-week, days-to-next-FOMC
  - Cross-asset: DXY change, VIX change, 10y yield change
- **Output**: probability ∈ [0, 1] + isotonic-calibrated.

## Training data (planned)

- Period: 2018-01-01 → train cutoff (rolling 24-month window).
- Source: OANDA M1 → 1h bars + FRED daily series.
- Sample: ~50k hourly bars per fold.
- Splits: walk-forward 3-month folds, no leakage.

## Evaluation (target)

- Brier ≤ 0.20 on hold-out (vs unconditional 0.25).
- Calibration: 95% of binned predictions within ±0.05 of empirical freq.
- Sharpe of long-when-prob-above-X strategy ≥ 0.8 (sanity, not goal).

## Caveats & failure modes

- Tree models drift fast under regime change — retrain weekly + monitor via
  `RUNBOOK-007`.
- Feature importance dominated by `r_1h` and HAR-RV pred in dev runs;
  watch for overfitting.
- Latency: < 5 ms per prediction batch.

## Aggregator weight

Initial weight after promotion to `live`: 0.15 (1 of ~6 directional models),
adjusted weekly based on rolling Brier per `bias_aggregator`.
