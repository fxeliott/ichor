# Model card — `hmm-regime-3state-v0`

## Model details

- **ID**: `hmm-regime-3state-v0`
- **Family**: Hidden Markov Model (Gaussian emissions, 3 hidden states)
- **Library**: `hmmlearn`
- **Owner**: Ichor Macro/Vol agent
- **Status**: scaffolded — code lives at `packages/ml/src/ichor_ml/regime/hmm.py`
- **Last training date**: pending W2 (no real OHLCV yet)

## Intended use

Given a univariate or multivariate market series (default: log-returns +
realized vol + cross-asset correlation), label the current regime as one of:

| State | Label                | Behavioral meaning                               |
| ----- | -------------------- | ------------------------------------------------ |
| 0     | Low-vol trending     | Trust trend-following, momentum signals dominate |
| 1     | High-vol trending    | Trend persists but expect sharp pullbacks        |
| 2     | Mean-reverting noise | Fade extremes, distrust momentum                 |

Used as a **conditioning gate** in `bias_aggregator`: per-model weights are
downscaled when the model was trained on a different regime than the current.

### Out-of-scope

- Not a forecaster of _future_ regime — only labels the current observation.
- Not stable across very long horizons (re-fit on rolling 2y windows).

## Inputs / Outputs

- **Inputs**: shape `(T, F)`, F ∈ {1..6}. Default features: `log_returns`,
  `realized_vol_5m`, `vix_change_1d`.
- **Outputs**: per-row state assignment + state probabilities `(T, 3)`.

## Training data (planned)

- Period: 2018-01-01 → present.
- Source: OANDA M1 → resampled 1h.
- Sample size: ~70k hourly bars per asset.
- Known biases: COVID-19 March-2020 dominates state 1 emissions; consider
  exclusion or robust covariance.

## Evaluation (when trained)

- Cross-validated log-likelihood per state.
- Stability of state assignments across rolling re-fits (Hungarian-matched
  state IDs, % of bars where label flips < 5%).
- Downstream impact: Brier improvement on bias predictions when conditioned
  on regime vs unconditioned.

## Caveats & failure modes

- Initial state-ID is arbitrary across re-fits — use Hungarian assignment.
- 3-state too coarse for crisis differentiation — consider 4-state in Phase 2.
- Latency: < 50 ms per forward pass on 1k-row window; well under briefing budget.
- Degradation trigger: `RUNBOOK-007` (Brier degradation > 15% in 7d).

## Aggregator weight

Currently 0 (not yet integrated). Target weight 0.0 directly — used as a
**filter on other models' weights**, not as a probability contributor itself.
