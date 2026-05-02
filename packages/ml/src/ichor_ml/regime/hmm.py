"""HMM 3-state regime detection.

State semantics (mapped from emission means after fit):
  0 = low-vol trending     (small daily moves, persistent direction)
  1 = high-vol trending    (large daily moves, persistent direction)
  2 = mean-reverting noise (whipsaw, no persistent direction)

Trained on log-returns + realized vol + ADX-like trend strength.
hmmlearn 0.3.3 is in limited maintenance (AUDIT_V3 §2). Stable for our use,
but monitor; switch to dynamax (JAX) if abandoned.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from hmmlearn.hmm import GaussianHMM


@dataclass
class HMMRegimeResult:
    states: np.ndarray  # shape (T,), int8 in {0, 1, 2}
    state_probs: np.ndarray  # shape (T, 3)
    log_likelihood: float
    converged: bool
    n_iter_actual: int


class HMMRegimeDetector:
    """Wraps hmmlearn.GaussianHMM with sane defaults for FX/equity returns."""

    def __init__(
        self,
        n_states: int = 3,
        n_iter: int = 200,
        random_state: int = 42,
    ) -> None:
        self._n_states = n_states
        self._model = GaussianHMM(
            n_components=n_states,
            covariance_type="full",
            n_iter=n_iter,
            random_state=random_state,
            tol=1e-3,
        )
        self._is_fit = False

    def fit(self, features: np.ndarray) -> None:
        """Fit on shape (T, F) feature matrix. Typically F=3:
        [log_return, realized_vol_5d, adx_14]."""
        if features.ndim != 2:
            raise ValueError(f"Expected 2D array, got shape {features.shape}")
        self._model.fit(features)
        self._is_fit = True

    def predict(self, features: np.ndarray) -> HMMRegimeResult:
        if not self._is_fit:
            raise RuntimeError("Call fit() before predict()")

        states = self._model.predict(features)
        state_probs = self._model.predict_proba(features)
        log_lik = self._model.score(features)

        # Reorder states by emission-mean magnitude so 0=lowest, 2=highest vol
        sort_order = np.argsort(self._model.means_[:, 0])
        state_remap = {old: new for new, old in enumerate(sort_order)}
        remapped_states = np.array([state_remap[s] for s in states], dtype=np.int8)
        remapped_probs = state_probs[:, sort_order]

        return HMMRegimeResult(
            states=remapped_states,
            state_probs=remapped_probs,
            log_likelihood=log_lik,
            converged=getattr(self._model.monitor_, "converged", True),
            n_iter_actual=getattr(self._model.monitor_, "iter", -1),
        )
