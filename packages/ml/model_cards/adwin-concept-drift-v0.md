# Model card — `adwin-concept-drift-v0`

## Model details

- **ID**: `adwin-concept-drift-v0`
- **Family**: ADaptive WINdowing (Bifet & Gavaldà 2007)
- **Library**: `river`
- **Owner**: Ichor model ops
- **Status**: scaffolded — `packages/ml/src/ichor_ml/regime/concept_drift.py`
- **Last calibration**: pending real Brier history (W2)

## Intended use

Online detector that monitors the **rolling Brier score** of every live
predictor and raises a `BIAS_BRIER_DEGRADATION` alert (and triggers
[RUNBOOK-007](../../docs/runbooks/RUNBOOK-007-brier-degradation.md)) when the
distribution shifts beyond ADWIN's confidence threshold.

### Out-of-scope

- Not a forecaster — only fires when something is already broken.
- Not used to auto-retrain (human-in-the-loop required, per persona).

## Inputs / Outputs

- **Input**: stream of per-prediction Brier contributions, one per
  `predictions_audit` row reconciled with realized outcomes.
- **Output**: boolean drift signal + cut point timestamp.

## Hyperparameters

- `delta = 0.002` (default, conservative — fewer false positives at the cost
  of slower detection).
- Window grows up to ~100 days of predictions before a cut is forced.

## Caveats & failure modes

- ADWIN can lag a true regime change by 7-14 days — pair with HMM regime
  flip for early warning.
- A single bad-data day can falsely trigger drift; verify the `predictions_audit`
  rows around the cut before retraining.
- Latency: O(log n) per update — negligible.

## Aggregator weight

Not used in aggregator — purely an observability signal.
