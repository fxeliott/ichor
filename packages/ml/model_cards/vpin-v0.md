# Model card — `vpin-eurusd-v0`

## Model details

- **ID**: `vpin-eurusd-v0`
- **Family**: Volume-Synchronized Probability of Informed Trading
- **Reference**: Easley-López de Prado-O'Hara (2012), RFS 25(5):1457-1493
- **Owner**: Ichor microstructure agent
- **Status**: scaffolded — `packages/ml/src/ichor_ml/microstructure/vpin.py`

## Intended use

Per-bucket order-flow imbalance metric used as a leading indicator of
liquidity-driven price moves. Fires `PLAN_VPIN_SPIKE` when 1-hour rolling
VPIN exceeds the 95th percentile of its 30-day distribution.

Also surfaces as a contextual signal in briefings when above 80th percentile,
phrased as "tension microstructure élevée — liquidité asymmetric".

### Out-of-scope

- Single-asset only; spillover modeling is Phase 2.
- Misspecified for very low-volume periods (off-hours overnight FX).

## Inputs / Outputs

- **Input**: tick or M1 trade tape (price + signed volume).
- **Output**: scalar VPIN ∈ [0, 1] per bucket (default bucket = 50 buckets/day).

## Caveats & failure modes

- VPIN's predictive power is debated (Andersen-Bondarenko 2014 critique);
  treat as a _risk gauge_, not a return predictor.
- Bucket size ≠ time — long quiet periods inflate VPIN spuriously.
- Latency: O(N) per bucket — < 5 ms.

## Aggregator weight

Not directional; used as feature + alert trigger.
