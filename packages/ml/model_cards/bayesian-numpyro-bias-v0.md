# Model card — `bayesian-numpyro-bias-eurusd-1h-v0`

## Model details

- **ID**: `bayesian-numpyro-bias-eurusd-1h-v0`
- **Family**: Bayesian logistic regression with hierarchical priors (NumPyro)
- **Owner**: Ichor bias agent
- **Status**: planned — Phase 1
- **Expected Brier**: 0.20 on hold-out

## Intended use

Provides per-prediction **credible intervals** that the frequentist models
can't natively produce. The 80% CI flows directly into `<BiasBar>` and
`<ConfidenceMeter>` UI components, and into the briefing prose ("60% long,
intervalle 50-72%").

Same inputs as the LightGBM card. Output is the posterior predictive
distribution, summarized as (median, p10, p90).

### Out-of-scope

- Slow training (~minutes for NUTS) — must be run nightly, not real-time.
- Single asset; hierarchy structure exists for future cross-asset pooling.

## Priors

- Coefficients: `Normal(0, 1)` after standardization.
- Intercept: `Normal(0, 5)` (weak prior).
- Group-level (regime): `Normal(0, 0.5)` half-Cauchy on scale.

## Caveats & failure modes

- Convergence failures should block deployment — check `r_hat < 1.05` for all
  parameters before promoting weights.
- Posterior may be over-confident if data is non-stationary; use rolling
  prior updating.
- Latency: < 50 ms per posterior predictive draw (vectorized over inputs).

## Aggregator weight

Initial weight: 0.15 — drives the CI band display in UI even when other
models drive the point estimate.
