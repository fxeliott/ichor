# Model card — `dtw-analogues-v0`

## Model details

- **ID**: `dtw-analogues-v0`
- **Family**: Dynamic Time Warping nearest-neighbor on price-vol shape
- **Reference**: Sakoe-Chiba (1978), Berndt-Clifford (1994)
- **Library**: `dtaidistance`
- **Owner**: Ichor narrative agent
- **Status**: scaffolded — `packages/ml/src/ichor_ml/analogues/dtw.py`

## Intended use

Given a current 5-day window of normalized log-returns, find the K nearest
historical analogues from the last ~10 years. Used to anchor briefing
narrative ("this week's price action resembles the 2018-04-15 episode")
and to sample plausible 1-week paths conditional on the current shape.

### Out-of-scope

- Not a forecaster: analogues are illustrative, not predictive in
  isolation. Aggregator does not consume DTW probabilities directly.
- Not a robust similarity measure under regime change — pair with HMM filter.

## Inputs / Outputs

- **Input**: query window (T_q, F) and database of historical windows (N, T_d, F).
- **Output**: top-K matches with distance + return path forward + metadata (date,
  asset).

## Caveats & failure modes

- Sensitive to feature normalization — use z-scoring on rolling 30d window.
- Sakoe-Chiba band radius `r` controls warp tolerance; default `r = T/4`.
- Latency: O(N · T_q · T_d / r) — pre-compute database in cache.

## Aggregator weight

0 — used for narrative anchoring only.
