"""HAR-RV (Heterogeneous AutoRegressive Realized Volatility) model.

Reference: Corsi F., 2009, "A Simple Approximate Long-Memory Model of
Realized Volatility", Journal of Financial Econometrics 7(2):174-196.

Uses arch (Sheppard) for the underlying RV computation. Wrapper here exposes
a simple .fit / .predict interface.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class HARRVPrediction:
    next_day_rv: float
    next_week_rv: float
    next_month_rv: float
    """Forecast RV (realized vol) at h=1, h=5, h=22 trading days ahead."""
    confidence_band_low: tuple[float, float, float]
    confidence_band_high: tuple[float, float, float]
    """80% CI on each horizon."""


class HARRVModel:
    """Daily HAR-RV regression: RV_t = β0 + β_d·RV_{t-1} + β_w·avg(RV_{t-5:t-1}) + β_m·avg(RV_{t-22:t-1}) + ε.

    To use:
        model = HARRVModel()
        model.fit(daily_rv_series)
        forecast = model.predict()
    """

    def __init__(self) -> None:
        self._betas: np.ndarray | None = None
        self._sigma: float | None = None
        self._last_features: np.ndarray | None = None

    def fit(self, daily_rv: pd.Series) -> None:
        """Fit OLS on the HAR-RV regression.

        Args:
            daily_rv: pandas Series of daily realized volatility, indexed by
                date (chronological). Length must be >= 30.
        """
        if len(daily_rv) < 30:
            raise ValueError(f"Need at least 30 obs to fit HAR-RV, got {len(daily_rv)}")

        rv = daily_rv.to_numpy(dtype=np.float64)
        # Build feature matrix: daily, weekly avg, monthly avg
        T = len(rv)
        X = np.zeros((T - 22, 4), dtype=np.float64)
        y = rv[22:]
        for t in range(22, T):
            X[t - 22, 0] = 1.0  # intercept
            X[t - 22, 1] = rv[t - 1]
            X[t - 22, 2] = rv[t - 5: t].mean()
            X[t - 22, 3] = rv[t - 22: t].mean()

        # OLS via lstsq
        self._betas, residuals, rank, _ = np.linalg.lstsq(X, y, rcond=None)
        if rank < 4:
            raise RuntimeError(f"HAR-RV regression rank-deficient (rank={rank})")
        residual_var = (residuals[0] / (len(y) - 4)) if residuals.size else np.var(y - X @ self._betas)
        self._sigma = float(np.sqrt(residual_var))

        # Snapshot last 22 RVs for prediction
        self._last_features = rv[-22:]

    def predict(self) -> HARRVPrediction:
        if self._betas is None or self._last_features is None:
            raise RuntimeError("Call fit() before predict()")

        rv = self._last_features.copy()
        b0, bd, bw, bm = self._betas
        sigma = self._sigma

        # h=1
        h1 = b0 + bd * rv[-1] + bw * rv[-5:].mean() + bm * rv[-22:].mean()

        # h=5: roll forward
        rv_ext = np.concatenate([rv, [h1]])
        h5_path = [h1]
        for _ in range(4):
            tail = rv_ext[-22:]
            next_v = b0 + bd * tail[-1] + bw * tail[-5:].mean() + bm * tail.mean()
            h5_path.append(next_v)
            rv_ext = np.concatenate([rv_ext, [next_v]])
        h5 = float(np.mean(h5_path))

        # h=22: same approach
        h22_path = h5_path.copy()
        for _ in range(17):
            tail = rv_ext[-22:]
            next_v = b0 + bd * tail[-1] + bw * tail[-5:].mean() + bm * tail.mean()
            h22_path.append(next_v)
            rv_ext = np.concatenate([rv_ext, [next_v]])
        h22 = float(np.mean(h22_path))

        # Naive Gaussian CI; replace with bootstrap in Phase 1
        z80 = 1.282
        return HARRVPrediction(
            next_day_rv=float(h1),
            next_week_rv=h5,
            next_month_rv=h22,
            confidence_band_low=(
                float(h1 - z80 * sigma),
                float(h5 - z80 * sigma),
                float(h22 - z80 * sigma),
            ),
            confidence_band_high=(
                float(h1 + z80 * sigma),
                float(h5 + z80 * sigma),
                float(h22 + z80 * sigma),
            ),
        )
