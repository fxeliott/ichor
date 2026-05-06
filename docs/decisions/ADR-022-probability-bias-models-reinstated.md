# ADR-022 — Probability-only bias models reinstated under Critic gate

- **Date** : 2026-05-05
- **Status** : Accepted (supersedes ADR-017 §"What's ARCHIVED" item `packages/ml/src/ichor_ml/training/`)
- **Decider** : Eliot (2026-05-05 reset-audit)

## Context

ADR-017 (2026-05-03) archived `packages/ml/src/ichor_ml/training/` along with the
`backtest/`, `risk/`, and `trading/` packages, motivated by the drift towards a
"signal-generating" system that Eliot does not want.

Between 2026-05-03 and 2026-05-05, the training modules were rebuilt under a
deliberately different contract :

- 6 trainers : `lightgbm_bias`, `xgboost_bias`, `random_forest_bias`,
  `logistic_bias`, `mlp_bias`, `numpyro_bias`.
- All return `P(target_up == 1) ∈ [0, 1]` — **probabilities, never BUY/SELL
  signals**, never position sizing, never P&L.
- Aggregated by `bias_aggregator` (Brier-optimal weights) and consumed by
  `services/ml_signals.py` as **one input among many** in the Critic
  confluence engine.
- `model_registry.yaml` pins versions ; `train_brier` is captured on every
  artifact for sanity-check vs in-sample overfit.
- 29/29 tests green locally (matrix : 5 trainers × 4 contract tests + 1 export
  check + 9 features tests).

This is **not** the same scope as the archived training. The archived
`lightgbm_bias` predicted **price-level returns** to drive a backtest framework.
The reinstated trainers predict **direction probability** to feed the Critic
gate before Claude publishes a session card.

## Decision

The 6 probability-only bias trainers stay. ADR-017's archival paragraph (lines
70-71 : _"`packages/ml/src/ichor_ml/training/` — wrong scope (Claude does
analysis, not ML models)"_) is amended to read :

> `packages/ml/src/ichor_ml/training/` (the **price-prediction**
> `lightgbm_bias` and helpers) — wrong scope. The Phase-2 reinstated
> trainers under the same path produce **probabilities only** and feed the
> Critic gate ; they comply with ADR-017's "Claude synthesizes, not a
> model guesses" principle because they are **inputs to Claude's
> reasoning, not outputs replacing it**. See ADR-022 for the contract.

## Contract for the reinstated trainers (binding)

1. **Probability output only.** No `direction: "BUY" | "SELL"`, no scaling
   factor, no position size. The signature is `predict_proba(row) -> float in
[0, 1]`.
2. **No P&L, no order generation.** No call to any broker API, no paper
   trading wrapper. Any code introducing those is a violation of this ADR.
3. **Inputs to Claude only.** Probabilities flow to
   `services/ml_signals.py` → `data_pool.py` → context builder → Claude
   passes 1-4. Claude's narrative remains the user-facing artifact.
4. **Critic gate authoritative.** Even if all 6 trainers agree on
   high-conviction direction, the Critic Agent
   (`packages/agents/critic/cross_asset.py`) can block, amend, or approve.
   Models do not bypass the Critic.
5. **Calibration tracked.** Each trainer's `train_brier` lands on the
   artifact. Production should add weekly held-out Brier per asset (Phase 2.3
   item — already wired via `routers/calibration.py`).
6. **No retrain on non-Hetzner.** Production retrain happens on Hetzner via
   a separate cron unit ; Win11 dev machines may run trainers for tests but
   never publish artifacts to the registry.

## What this ADR does NOT change

- ADR-017's archival of `packages/backtest/`, `packages/risk/`,
  `packages/trading/` stands. **No backtest framework, no risk engine, no
  paper trading wrapper.**
- ADR-017's 12-capability architecture, 8-asset universe, Voie D constraint,
  legal floor (AMF DOC-2008-23, EU AI Act Art. 50, no order execution).
- Disclaimer banner non-dismissible on every screen.

## Consequences

- `services/ml_signals.py` keeps its current 9-signal contract (HMM regime,
  HAR-RV, VPIN, ADWIN drift, FOMC-RoBERTa, FinBERT tone, SABR-SVI, plus the
  6-trainer aggregator). 3/9 signals (VPIN, SABR-SVI, FOMC-RoBERTa) remain
  placeholders ; ADR-022 does not mandate completion timeline.
- `archive/2026-05-03-pre-reset/ml-training/` (the **old** lightgbm_bias that
  predicted price) stays archived as historical reference.
- Future ADRs may further constrain or extend the trainer contract ; they
  must explicitly cite ADR-022 to maintain audit trail.

## References

- ADR-017 — Reset Phase 1 (the contract being amended) : `docs/decisions/ADR-017-reset-phase1-living-macro-entity.md`
- Reinstated trainers : `packages/ml/src/ichor_ml/training/{features,lightgbm_bias,xgboost_bias,random_forest_bias,logistic_bias,mlp_bias,numpyro_bias}.py`
- Aggregator : `packages/ml/src/ichor_ml/bias_aggregator.py`
- Critic gate : `packages/agents/critic/cross_asset.py`
- Pre-reset reference (price-predicting trainer) : `archive/2026-05-03-pre-reset/ml-training/lightgbm_bias.py`
- Boundary doc cited in every trainer module : _"ADR-017 boundary : returns probabilities, never BUY/SELL signals."_
