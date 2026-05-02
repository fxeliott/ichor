"""Bias Aggregator — Brier-weighted ensemble of N model predictions.

Per AUDIT_V3 + ARCHITECTURE_FINALE: the production roster is 6 models
(LightGBM, XGBoost, Random Forest, Logistic, Bayesian NumPyro, MLP PyTorch)
plus the deterministic regime/vol/microstructure/NLP signals.

Phase 0 scaffolding: this module accepts an arbitrary list of Predictions and
combines them via Brier-weighted averaging. Per-model Brier scores come from
a 90-day rolling calibration table (to be wired Phase 0 W2 step 17).

Algorithm:
  1. Filter Predictions to a single (asset, horizon) cohort.
  2. For each model_family present, fetch its current Brier weight w_f.
     w_f = 1 / (Brier_f + epsilon) so lower Brier => higher weight.
  3. Compute calibrated probability: p = sum(w_f * p_f) / sum(w_f)
  4. Discretize direction by p > 0.5 threshold (asymmetric in Phase 1+).
  5. Bootstrap 1000 resamples for the credible interval.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .types import AssetCode, BiasSignal, Direction, Prediction


@dataclass
class AggregatorConfig:
    """Knobs for the aggregator. Tuned per asset eventually."""

    epsilon: float = 1e-3  # avoids div-by-zero on perfect-Brier models
    bootstrap_samples: int = 1000
    decision_threshold: float = 0.55  # p > 0.55 = long, p < 0.45 = short, else neutral
    min_models_required: int = 2  # don't issue a signal if only 1 model contributes


class BiasAggregator:
    def __init__(
        self,
        config: AggregatorConfig | None = None,
        rng_seed: int = 7,
    ) -> None:
        self._cfg = config or AggregatorConfig()
        self._rng = np.random.default_rng(rng_seed)

    def aggregate(
        self,
        predictions: list[Prediction],
        *,
        asset: AssetCode,
        horizon_hours: int,
        brier_weights: dict[str, float],
    ) -> BiasSignal | None:
        """Combine predictions for one (asset, horizon) into a single BiasSignal.

        Args:
            predictions: candidates. Filtered to matching asset + horizon.
            asset: target asset.
            horizon_hours: forecast horizon to align across models.
            brier_weights: {model_family: brier_score}. Lower is better.
                Use the 90-day rolling table (Phase 0 W2 step 17).

        Returns:
            BiasSignal if >= min_models_required matched, else None.
        """
        cohort = [
            p for p in predictions
            if p.asset == asset
            and p.horizon_hours == horizon_hours
            and p.calibrated_probability is not None
        ]
        if len(cohort) < self._cfg.min_models_required:
            return None

        # Build aligned p_f and w_f arrays
        probs: list[float] = []
        weights: list[float] = []
        weight_snapshot: dict[str, float] = {}
        contributing: list = []

        for p in cohort:
            family = p.model_family
            brier = brier_weights.get(family)
            if brier is None or brier < 0:
                continue
            w = 1.0 / (brier + self._cfg.epsilon)

            # Use probability of LONG direction consistently
            p_long = (
                p.calibrated_probability if p.direction == "long"
                else 1.0 - p.calibrated_probability
            )
            probs.append(float(p_long))
            weights.append(w)
            weight_snapshot[family] = w
            contributing.append(p.prediction_id)

        if len(probs) < self._cfg.min_models_required:
            return None

        probs_arr = np.array(probs, dtype=np.float64)
        weights_arr = np.array(weights, dtype=np.float64)

        ensemble_p = float(np.average(probs_arr, weights=weights_arr))

        # Bootstrap CI by resampling the contributing models
        n = len(probs_arr)
        idx = self._rng.integers(0, n, size=(self._cfg.bootstrap_samples, n))
        boot = (probs_arr[idx] * weights_arr[idx]).sum(axis=1) / weights_arr[idx].sum(axis=1)
        ci_low, ci_high = np.percentile(boot, [10, 90])

        if ensemble_p >= self._cfg.decision_threshold:
            direction: Direction = "long"
            prob = ensemble_p
        elif ensemble_p <= (1.0 - self._cfg.decision_threshold):
            direction = "short"
            prob = 1.0 - ensemble_p
        else:
            direction = "neutral"
            prob = max(ensemble_p, 1.0 - ensemble_p)

        # Normalize the weight snapshot to sum=1 for readability
        total_w = sum(weight_snapshot.values())
        weights_norm = {k: v / total_w for k, v in weight_snapshot.items()}

        return BiasSignal(
            asset=asset,
            horizon_hours=horizon_hours,
            direction=direction,
            probability=prob,
            credible_interval_low=float(min(ci_low, ci_high)),
            credible_interval_high=float(max(ci_low, ci_high)),
            contributing_predictions=contributing,
            weights_snapshot=weights_norm,
            notes=f"Aggregated {len(probs)} model predictions",
        )
