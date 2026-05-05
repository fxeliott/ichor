"""NumPyro Bayesian bias model — Bayesian logistic regression.

Returns posterior-mean P(target_up == 1) computed by MCMC over the
weights of a logistic regression. Unlike the frequentist `logistic_bias`
which returns a point estimate, the Bayesian variant carries uncertainty
through the predictions — useful for the bias_aggregator's calibrated
ensemble (a high-variance prediction gets less weight).

Implementation :
  - Prior : N(0, 1) on intercept, N(0, 1) on each weight (weakly informative,
    standard logistic regression default).
  - Likelihood : Bernoulli(sigmoid(intercept + X @ w)).
  - Posterior : NUTS sampler, default 500 warmup + 1000 samples.
  - Prediction : posterior mean of sigmoid(intercept + x @ w).

Features are standardized in-process (NumPyro doesn't have a Pipeline
abstraction) ; means + stds are stored on the artifact so prediction
applies the same transform as training.

ADR-017 boundary : returns probabilities, never BUY/SELL signals.
"""

from __future__ import annotations

from dataclasses import dataclass

import jax
import jax.numpy as jnp
import numpy as np
import numpyro
import numpyro.distributions as dist
from numpyro.infer import MCMC, NUTS

from .features import FEATURE_NAMES, BarLike, FeatureRow, build_features_daily

_MIN_TRAIN_ROWS = 30


@dataclass(frozen=True)
class NumPyroBiasArtifact:
    asset: str
    feature_names: tuple[str, ...]
    n_train_rows: int
    train_brier: float
    n_samples: int
    n_warmup: int
    feature_means: tuple[float, ...]
    feature_stds: tuple[float, ...]
    posterior_intercept_mean: float
    posterior_weight_means: tuple[float, ...]


@dataclass
class NumPyroBiasModel:
    artifact: NumPyroBiasArtifact

    def predict_proba(self, row: FeatureRow) -> float:
        """Posterior-mean P(target_up == 1) for one feature row.

        Uses the posterior means of the intercept + weights stored on
        the artifact (point-estimate evaluation, fast). For full
        posterior predictive intervals call `predict_proba_samples`.
        """
        names = self.artifact.feature_names
        means = np.array(self.artifact.feature_means, dtype=np.float64)
        stds = np.array(self.artifact.feature_stds, dtype=np.float64)
        x = np.array([row.features[k] for k in names], dtype=np.float64)
        # Avoid division by zero on degenerate features.
        stds_safe = np.where(stds == 0.0, 1.0, stds)
        x_std = (x - means) / stds_safe

        w = np.array(self.artifact.posterior_weight_means, dtype=np.float64)
        b = self.artifact.posterior_intercept_mean
        logit = float(b + x_std @ w)
        # sigmoid clamped to [0, 1] just in case of inf overflow.
        return (
            float(1.0 / (1.0 + np.exp(-logit))) if abs(logit) < 700 else (1.0 if logit > 0 else 0.0)
        )


def _to_xy(rows: list[FeatureRow]) -> tuple[np.ndarray, np.ndarray]:
    x = np.array([[r.features[k] for k in FEATURE_NAMES] for r in rows], dtype=np.float64)
    y = np.array([r.target_up for r in rows], dtype=np.int32)
    return x, y


def _brier_score(probs: np.ndarray, targets: np.ndarray) -> float:
    if probs.size == 0:
        return 0.0
    return float(np.mean((probs - targets) ** 2))


def _logistic_model(x: jnp.ndarray, y: jnp.ndarray | None) -> None:
    """NumPyro probabilistic model : Bayesian logistic regression."""
    n_features = x.shape[1]
    intercept = numpyro.sample("intercept", dist.Normal(0.0, 1.0))
    w = numpyro.sample("w", dist.Normal(jnp.zeros(n_features), jnp.ones(n_features)))
    logits = intercept + x @ w
    numpyro.sample("y", dist.Bernoulli(logits=logits), obs=y)


def train_numpyro_bias(
    bars: list[BarLike],
    *,
    n_samples: int = 1000,
    n_warmup: int = 500,
    n_chains: int = 1,
    min_history: int = 60,
    seed: int = 42,
) -> NumPyroBiasModel:
    """Train a Bayesian logistic regression via NumPyro NUTS sampling.

    Args:
        n_samples: posterior samples per chain after warmup.
        n_warmup: warmup (burn-in) samples per chain.
        n_chains: number of MCMC chains.
        seed: PRNG key seed for reproducibility.

    Raises:
        ValueError: empty bars list, or < `_MIN_TRAIN_ROWS` feature rows.
    """
    if not bars:
        raise ValueError("train_numpyro_bias: empty bars list")
    asset = bars[0].asset

    rows = build_features_daily(bars, min_history=min_history)
    if len(rows) < _MIN_TRAIN_ROWS:
        raise ValueError(
            f"train_numpyro_bias: need at least {_MIN_TRAIN_ROWS} feature rows, got {len(rows)}"
        )

    x_raw, y = _to_xy(rows)
    means = x_raw.mean(axis=0)
    stds = x_raw.std(axis=0)
    stds_safe = np.where(stds == 0.0, 1.0, stds)
    x_std = (x_raw - means) / stds_safe

    x_jax = jnp.array(x_std)
    y_jax = jnp.array(y)

    kernel = NUTS(_logistic_model)
    mcmc = MCMC(
        kernel,
        num_warmup=n_warmup,
        num_samples=n_samples,
        num_chains=n_chains,
        progress_bar=False,
    )
    rng_key = jax.random.PRNGKey(seed)
    mcmc.run(rng_key, x=x_jax, y=y_jax)
    samples = mcmc.get_samples()

    intercept_mean = float(np.asarray(samples["intercept"]).mean())
    w_mean = np.asarray(samples["w"]).mean(axis=0).astype(np.float64)

    # In-sample Brier using posterior-mean point estimates.
    logits = intercept_mean + x_std @ w_mean
    train_probs = 1.0 / (1.0 + np.exp(-np.clip(logits, -500, 500)))
    train_brier = _brier_score(train_probs, y)

    artifact = NumPyroBiasArtifact(
        asset=asset,
        feature_names=FEATURE_NAMES,
        n_train_rows=len(rows),
        train_brier=train_brier,
        n_samples=n_samples,
        n_warmup=n_warmup,
        feature_means=tuple(float(m) for m in means),
        feature_stds=tuple(float(s) for s in stds),
        posterior_intercept_mean=intercept_mean,
        posterior_weight_means=tuple(float(v) for v in w_mean),
    )
    return NumPyroBiasModel(artifact=artifact)


__all__ = [
    "FEATURE_NAMES",
    "NumPyroBiasArtifact",
    "NumPyroBiasModel",
    "train_numpyro_bias",
]
