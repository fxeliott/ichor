# Model card — `har-rv-eurusd-v0`

## Model details

- **ID**: `har-rv-eurusd-v0`
- **Family**: Heterogeneous Autoregressive model of Realized Volatility
- **Reference**: Corsi (2009), JFE 7(2):174-196
- **Owner**: Ichor Vol agent
- **Status**: scaffolded — `packages/ml/src/ichor_ml/vol/har_rv.py`
- **Last training date**: pending W2

## Intended use

1d-ahead forecast of realized variance using a parsimonious linear
combination of past realized variance at three horizons (1d, 5d, 22d):

`RV_{t+1} = β₀ + β_d · RV_t + β_w · RV_t^(5d) + β_m · RV_t^(22d) + ε`

Used in two places:

1. **Vol-aware position sizing** in briefings (probabilistic statements
   conditioned on next-day realized vol).
2. **PLAN_VOL_REGIME_BREAK alert**: triggers when `RV_{t+1}^pred >
2 × MA_30(RV)`.

### Out-of-scope

- Single-asset only (no cross-asset spillover).
- Misses jumps; combine with bipower-variation or HAR-RV-J for jump-aware
  variant.

## Inputs / Outputs

- **Input**: 1-min log-returns over the last 30 days (8 640 bars per
  trading day approx).
- **Output**: scalar `RV_{t+1}^pred` (annualized vol equivalent published
  for traders).

## Training data (planned)

- Period: 2018-01-01 → present (~7 years of OANDA M1 EUR/USD).
- Sample size: ~1.8M minute bars.
- Train/val split: rolling-window 24-month / 6-month with re-fit weekly.

## Evaluation (when trained)

- Out-of-sample R² target ≥ 0.55 (Corsi 2009 reports 0.6+).
- MSE on log(RV) — comparable to Forsberg-Ghysels (2007) GMM.
- QLIKE loss vs naive RV-AR(1) baseline.

## Caveats & failure modes

- Sensitive to outliers — winsorize extreme returns at 99.5%.
- Underestimates vol during regime shifts (combine with HMM state 1 flag).
- Latency: < 10 ms.

## Aggregator weight

Not in `bias_aggregator` directly (vol forecast, not directional bias).
Consumed as a feature by directional models.
