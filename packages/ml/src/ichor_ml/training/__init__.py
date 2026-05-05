"""ML training pipeline — feature engineering + bias-direction classifiers.

Bias model lineup (all share the same interface : `train_X(bars, ...)`
returns a wrapper with `.artifact` + `.predict_proba(feature_row)`) :

  - LightGBM   (lightgbm_bias.py)   — gradient-boosted trees, fastest fit
  - XGBoost    (xgboost_bias.py)    — gradient-boosted trees, alt impl
  - RandomForest (random_forest_bias.py) — bagged trees, robust baseline
  - Logistic   (logistic_bias.py)   — linear baseline, calibrated probas
  - MLP        (mlp_bias.py)        — small neural network, captures
                                       non-linear feature interactions
  - NumPyro    (numpyro_bias.py)    — Bayesian logistic regression with
                                       posterior uncertainty

The `bias_aggregator` module ensembles them with Brier-optimal weights ;
each individual learner ships an in-sample `train_brier` for sanity checks.

ADR-017 : all six return PROBABILITIES, never BUY/SELL signals.
"""

from .features import BarLike, FeatureRow, build_features_daily
from .lightgbm_bias import (
    LightGBMBiasArtifact,
    LightGBMBiasModel,
    train_lightgbm_bias,
)
from .logistic_bias import (
    LogisticBiasArtifact,
    LogisticBiasModel,
    train_logistic_bias,
)
from .mlp_bias import MLPBiasArtifact, MLPBiasModel, train_mlp_bias
from .numpyro_bias import (
    NumPyroBiasArtifact,
    NumPyroBiasModel,
    train_numpyro_bias,
)
from .random_forest_bias import (
    RandomForestBiasArtifact,
    RandomForestBiasModel,
    train_random_forest_bias,
)
from .xgboost_bias import (
    XGBoostBiasArtifact,
    XGBoostBiasModel,
    train_xgboost_bias,
)

__all__ = [
    "BarLike",
    "FeatureRow",
    "LightGBMBiasArtifact",
    "LightGBMBiasModel",
    "LogisticBiasArtifact",
    "LogisticBiasModel",
    "MLPBiasArtifact",
    "MLPBiasModel",
    "NumPyroBiasArtifact",
    "NumPyroBiasModel",
    "RandomForestBiasArtifact",
    "RandomForestBiasModel",
    "XGBoostBiasArtifact",
    "XGBoostBiasModel",
    "build_features_daily",
    "train_lightgbm_bias",
    "train_logistic_bias",
    "train_mlp_bias",
    "train_numpyro_bias",
    "train_random_forest_bias",
    "train_xgboost_bias",
]
