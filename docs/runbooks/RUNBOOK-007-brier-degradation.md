# RUNBOOK-007: Brier score degradation > 15% in 7 days

- **Severity**: P2 (model accuracy regression; not blocking but trust-eroding)
- **Time to resolve (target)**: 1-2h investigation + days for re-calibration

## Trigger

- Alert `BIAS_BRIER_DEGRADATION` fires (auto, computed by aggregator)
- Manual review of `/performance` dashboard shows Brier worsening
- Specific model_family Brier slope upward over 90-day window

## Diagnosis

```sql
-- Brier score per model_family, last 7 days vs prior 14 days.
-- Note: ADR-017 renamed `predictions_audit` to `session_card_audit`
-- (one row per asset per session window) and `model_family` is now
-- `model_id`. Update this query if you upgrade the runbook.
WITH recent AS (
  SELECT model_id AS model_family, AVG(brier_contribution) AS brier_7d
  FROM session_card_audit
  WHERE realized_at > now() - interval '7 days'
    AND brier_contribution IS NOT NULL
  GROUP BY model_id
),
baseline AS (
  SELECT model_id AS model_family, AVG(brier_contribution) AS brier_baseline
  FROM session_card_audit
  WHERE realized_at BETWEEN now() - interval '21 days' AND now() - interval '7 days'
    AND brier_contribution IS NOT NULL
  GROUP BY model_id
)
SELECT r.model_family,
       r.brier_7d, b.brier_baseline,
       (r.brier_7d - b.brier_baseline) / b.brier_baseline * 100 AS pct_change
FROM recent r JOIN baseline b USING (model_family)
ORDER BY pct_change DESC;
```

Common causes (in order of likelihood):

1. **Regime shift**: HMM state changed — models trained in regime 0 perform
   poorly in regime 2. Check `bias_signals.weights_snapshot` evolution.
2. **Concept drift**: ADWIN already flagged it (RUNBOOK-XXX). Recalibrate.
3. **Feature data quality**: a collector started returning stale or wrong
   data. Cross-check with another source.
4. **Calibration table stale**: the isotonic calibration was fit on old data
   that no longer represents the current distribution.

## Recovery

### A. Recalibration (most common fix)

1. Trigger a fresh isotonic fit using last 90d of realized outcomes:
   ```bash
   ssh ichor-hetzner
   sudo -u ichor bash -c 'cd /opt/ichor/api/src && python -m ichor_api.cli.recalibrate_models'
   ```
2. Verify Brier improves on hold-out (last 7 days).
3. If yes: keep new calibration. If no: investigate other causes.

### B. Reduce weight of degraded model in aggregator

- If a single model is the outlier, drop its weight to 0 temporarily:
  ```python
  # In packages/ml/src/ichor_ml/bias_aggregator.py — config override
  BAD_FAMILIES = {"xgboost"}  # example
  weights = {f: w for f, w in brier_weights.items() if f not in BAD_FAMILIES}
  ```
- Document in `docs/incidents/YYYY-MM-DD-brier-degrade.md`
- Re-train + re-test the bad model offline

### C. Regime-aware retraining

- If the issue correlates with a regime change, partition the training data
  by HMM state and retrain per-regime ensembles (Phase 2+).

## Post-incident

- Update model card for the degraded model_family
- Schedule the re-evaluation in 7 days
- If recurring: consider model deprecation (remove from registry)
