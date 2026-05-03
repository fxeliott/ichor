# Ichor model cards

Each model used in production has a card here. Format follows Mitchell et al.
2019 ("Model Cards for Model Reporting", FAccT) adapted for our needs.

## Required sections

1. **Model details** — ID, family, version, owner, last training date.
2. **Intended use** — primary use case + secondary uses + out-of-scope.
3. **Inputs / Outputs** — exact features, output type, calibration target.
4. **Training data** — period, source, sample size, known biases.
5. **Evaluation** — Brier on hold-out, calibration plot reference,
   confusion matrix where applicable.
6. **Caveats & failure modes** — regime sensitivity, latency budget,
   degradation triggers (linked to runbook).
7. **Aggregator weight** — current weight in `bias_aggregator` + last
   adjustment rationale.

## Lifecycle

- `planned` — card describes the design, no code yet.
- `scaffolded` — card exists, code lazy-loads, weights downloaded on first call.
- `trained` — fitted on real Ichor data, has cross-val Brier on hold-out.
- `live` — integrated into `bias_aggregator`, current weight > 0.
- `deprecated` — kept for reproducibility, weight = 0, do not call.

When promoting status, update both this card AND
`packages/ml/model_registry.yaml`.
