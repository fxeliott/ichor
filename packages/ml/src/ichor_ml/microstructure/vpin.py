"""VPIN (Volume-Synchronized Probability of Informed Trading).

Reference: Easley D., López de Prado M., O'Hara M., 2012,
"Flow Toxicity and Liquidity in a High-Frequency World",
Review of Financial Studies 25(5):1457-1493.

Note the title: "Liquidity" (not "Volatility" — AUDIT_V3 §2 corrected this
common citation error).

We re-implement here because flowrisk (the only PyPI implementation) is
abandonware as of 2018.

Algorithm:
  1. Define a volume bucket size V (e.g., 1/50th of average daily volume)
  2. Aggregate trades into N consecutive buckets, each containing exactly V volume
  3. For each bucket, classify volume as buy (V_buy) or sell (V_sell) using
     bulk-volume classification (BVC) on tick-aggregated price changes
  4. VPIN = mean over the last n buckets of |V_buy - V_sell| / V

The classification uses the standardized price-change CDF: a strong upward
move within a bucket implies most of that bucket's volume was buy-initiated.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import norm


@dataclass
class VPINResult:
    vpin: pd.Series  # one value per volume bucket (after warmup)
    bucket_starts: pd.DatetimeIndex
    bucket_ends: pd.DatetimeIndex
    """For each bucket: timestamps of first and last trade."""


class VPINEstimator:
    """Bulk-Volume Classification (BVC) VPIN estimator.

    Args:
        bucket_volume: target volume per bucket (in same units as `volume`
            argument to compute()). Typical: 1/50th of average daily volume.
        window_n_buckets: rolling window for VPIN computation. Typical: 50.
        bvc_sigma_lookback: lookback in trade ticks for the std-dev estimate
            used in BVC. Typical: 1000.
    """

    def __init__(
        self,
        bucket_volume: float,
        window_n_buckets: int = 50,
        bvc_sigma_lookback: int = 1000,
    ) -> None:
        if bucket_volume <= 0:
            raise ValueError("bucket_volume must be positive")
        if window_n_buckets < 5:
            raise ValueError("window_n_buckets must be >= 5")
        self._V = float(bucket_volume)
        self._n = window_n_buckets
        self._sigma_lb = bvc_sigma_lookback

    def compute(self, trades: pd.DataFrame) -> VPINResult:
        """Compute VPIN over the trade tape.

        Args:
            trades: DataFrame with columns ['timestamp', 'price', 'volume'].
                Sorted by timestamp ascending.

        Returns:
            VPINResult with VPIN series and bucket boundaries.
        """
        required = {"timestamp", "price", "volume"}
        if not required.issubset(trades.columns):
            raise ValueError(f"trades must have columns {required}, got {set(trades.columns)}")

        df = trades.sort_values("timestamp").reset_index(drop=True)
        n_trades = len(df)
        if n_trades < self._sigma_lb + 100:
            raise ValueError(
                f"Need at least {self._sigma_lb + 100} trades to bootstrap VPIN, got {n_trades}"
            )

        # Compute log price changes
        log_p = np.log(df["price"].to_numpy())
        dp = np.diff(log_p)
        # Trailing std of dp for BVC standardization
        sigma = pd.Series(dp).rolling(self._sigma_lb, min_periods=self._sigma_lb).std()
        sigma = sigma.bfill().to_numpy()

        # BVC fraction per trade: P(buy) = CDF((p_t - p_{t-1}) / sigma_t)
        p_buy_per_trade = np.zeros(n_trades, dtype=np.float64)
        p_buy_per_trade[1:] = norm.cdf(dp / np.where(sigma > 0, sigma, 1e-12))
        p_buy_per_trade[0] = 0.5  # first trade ambiguous

        # Bucket trades by cumulative volume
        cum_vol = df["volume"].cumsum().to_numpy()
        bucket_id = (cum_vol / self._V).astype(np.int64)

        # Per-bucket sums
        df["_p_buy"] = p_buy_per_trade
        df["_bucket"] = bucket_id
        df["_v_buy"] = df["_p_buy"] * df["volume"]
        df["_v_sell"] = (1.0 - df["_p_buy"]) * df["volume"]

        agg = df.groupby("_bucket").agg(
            v_buy=("_v_buy", "sum"),
            v_sell=("_v_sell", "sum"),
            ts_start=("timestamp", "first"),
            ts_end=("timestamp", "last"),
            v_total=("volume", "sum"),
        )
        # Drop the partial last bucket (volume < V)
        agg = agg[agg["v_total"] >= self._V * 0.95]

        oi = (agg["v_buy"] - agg["v_sell"]).abs() / agg["v_total"]
        vpin = oi.rolling(self._n, min_periods=self._n).mean()

        return VPINResult(
            vpin=vpin,
            bucket_starts=pd.DatetimeIndex(agg["ts_start"]),
            bucket_ends=pd.DatetimeIndex(agg["ts_end"]),
        )
