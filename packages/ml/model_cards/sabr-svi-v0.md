# Model card — `sabr-svi-eurusd-v0`

## Model details

- **ID**: `sabr-svi-eurusd-v0`
- **Family**: SABR (stochastic alpha-beta-rho) + SVI parametric vol surface fit
- **Reference**: Hagan-Kumar-Lesniewski-Woodward (2002) + Gatheral-Jacquier (2014)
- **Owner**: Ichor Vol agent
- **Status**: scaffolded — `packages/ml/src/ichor_ml/vol/sabr_svi.py`
- **Last calibration**: pending vol surface ingest (Phase 1+)

## Intended use

Fit a SABR parameterization to a snapshot of EUR/USD ATM + RR + BFLY at
1W/1M/3M/6M/1Y tenors, derive smile + skew metrics:

- Risk-reversal sign (skew): positive = call-skew (bullish tail demand).
- Butterfly: convexity = tail-fear premium.
- Term-structure slope: contango vs backwardation.

Output drives `PLAN_RISK_REVERSAL_FLIP` alert and is summarized in briefings
when material.

### Out-of-scope

- Phase 0: not yet wired — vol surface data needs Bloomberg/Reuters or
  EOD Historical Data subscription. Planned Phase 1+.

## Inputs / Outputs

- **Input**: vector of (tenor, ATM_vol, RR_25d, BFLY_25d) tuples per snapshot.
- **Output**: SABR params `(α, β, ρ, ν)` + derived skew/curvature/term-structure
  metrics + fitting RMSE.

## Caveats & failure modes

- SABR can hit the well-known "negative density" issue at low strikes — use
  shifted-SABR or SVI fallback when β ≈ 0.
- Calibration is daily (or per-tick if streaming) — cache results.

## Aggregator weight

Not directional; used as feature for downstream models.
