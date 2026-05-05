"""VPIN (Volume-Synchronized Probability of Informed Trading).

Reference: Easley D., López de Prado M., O'Hara M., 2012,
"Flow Toxicity and Liquidity in a High-Frequency World",
Review of Financial Studies 25(5):1457-1493.

Note the title: "Liquidity" (not "Volatility" — AUDIT_V3 §2 corrected this
common citation error).

We re-implement here because flowrisk (the only PyPI implementation) is
abandonware as of 2018.

Algorithm (trades — original equity-market formulation):
  1. Define a volume bucket size V (e.g., 1/50th of average daily volume)
  2. Aggregate trades into N consecutive buckets, each containing exactly V volume
  3. For each bucket, classify volume as buy (V_buy) or sell (V_sell) using
     bulk-volume classification (BVC) on tick-aggregated price changes
  4. VPIN = mean over the last n buckets of |V_buy - V_sell| / V

The classification uses the standardized price-change CDF: a strong upward
move within a bucket implies most of that bucket's volume was buy-initiated.

FX adaptation (quote-driven, no central trade tape):
  FX is OTC and has no consolidated trade-tape ; the equivalent of a
  trade tick is a quote-update tick (bid+ask refresh from the venue).
  Standard practice (NinjaTrader, MarketDelta, academic FX studies) is:
   - Use the mid-price (bid+ask)/2 as the price series.
   - Use tick-count as a synthetic volume — every quote update counts
     as 1 "unit of activity". Volume-bucketing then becomes
     tick-count-bucketing.
   - BVC on z-scored mid-price changes is unchanged.
  The `compute_vpin_from_fx_quotes` helper handles this conversion.

ADR-022 boundary : VPIN here is a microstructure feature emitted as a
PROBABILITY (toxicity 0..1) ; never a BUY/SELL signal. It feeds the brain
Pass 2 confluence engine, not an order generator.
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

    @property
    def latest(self) -> float | None:
        """Most recent non-NaN VPIN value, or None if the warmup is incomplete."""
        if self.vpin.empty:
            return None
        valid = self.vpin.dropna()
        if valid.empty:
            return None
        return float(valid.iloc[-1])

    @property
    def n_buckets(self) -> int:
        return len(self.vpin)


class VPINEstimator:
    """Bulk-Volume Classification (BVC) VPIN estimator.

    Args:
        bucket_volume: target volume per bucket (in same units as `volume`
            argument to compute()). Typical: 1/50th of average daily volume.
            For FX tick-count VPIN, this is a tick count (e.g., 200).
        window_n_buckets: rolling window for VPIN computation. Typical: 50.
        bvc_sigma_lookback: lookback in trade ticks for the std-dev estimate
            used in BVC. Typical: 1000 for equities, 200-500 for FX where
            tick frequency is higher and shorter windows track regime
            changes faster.
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
        if bvc_sigma_lookback < 30:
            raise ValueError("bvc_sigma_lookback must be >= 30")
        self._V = float(bucket_volume)
        self._n = window_n_buckets
        self._sigma_lb = bvc_sigma_lookback

    def compute(self, trades: pd.DataFrame) -> VPINResult:
        """Compute VPIN over the trade tape.

        Args:
            trades: DataFrame with columns ['timestamp', 'price', 'volume'].
                Sorted by timestamp ascending. `volume` may be synthetic
                (1 per row) when computing tick-count VPIN on FX quotes.

        Returns:
            VPINResult with VPIN series and bucket boundaries.

        Raises:
            ValueError: if columns missing, or fewer than
                `bvc_sigma_lookback + 100` rows are provided. The 100-row
                margin guards against an all-NaN VPIN series due to the
                `window_n_buckets` warmup landing past the data end.
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


# ─────────────────────── FX quote-tick adapter ───────────────────────


def quotes_to_synthetic_trades(quotes: pd.DataFrame) -> pd.DataFrame:
    """Convert FX quote stream rows to a synthetic trade frame.

    Each quote update becomes one row of the synthetic trade tape :
      - price = (bid + ask) / 2 (mid-price)
      - volume = 1 (tick-count proxy, since OTC FX has no real trade vol)
      - timestamp = quote update timestamp

    Args:
        quotes: DataFrame with at least columns ['timestamp', 'bid', 'ask'].
            Optional 'mid' column overrides the (bid+ask)/2 derivation.

    Returns:
        DataFrame ready for VPINEstimator.compute().

    Raises:
        ValueError: if required columns are missing or all rows have
            invalid bid/ask (≤ 0 or NaN).
    """
    if "timestamp" not in quotes.columns:
        raise ValueError("quotes must have a 'timestamp' column")
    if "mid" not in quotes.columns:
        if not {"bid", "ask"}.issubset(quotes.columns):
            raise ValueError("quotes must have either a 'mid' column or both 'bid' + 'ask' columns")
        mid = (quotes["bid"].astype(float) + quotes["ask"].astype(float)) / 2.0
    else:
        mid = quotes["mid"].astype(float)

    out = pd.DataFrame(
        {
            "timestamp": quotes["timestamp"].to_numpy(),
            "price": mid.to_numpy(),
            "volume": np.ones(len(quotes), dtype=np.float64),
        }
    )
    # Filter invalid mids (zero, negative, NaN) — we cannot take log() of them
    valid = out["price"].notna() & (out["price"] > 0)
    out = out[valid].reset_index(drop=True)
    if out.empty:
        raise ValueError("All quote rows had invalid mid-price (≤ 0 or NaN) ; cannot compute VPIN")
    return out


def compute_vpin_from_fx_quotes(
    quotes: pd.DataFrame,
    *,
    bucket_n_ticks: int = 200,
    window_n_buckets: int = 50,
    bvc_sigma_lookback: int = 500,
) -> VPINResult:
    """Compute VPIN on an FX quote stream using tick-count buckets.

    Defaults are calibrated for major-pair quote frequency (~ 1-5 quotes
    per second during liquid sessions) :
      - 200 ticks per bucket → ~ 30-60 s of liquidity per bucket
      - 50 buckets in the rolling VPIN window → ~ 25-50 min of context
      - 500-tick sigma lookback → ~ 2-8 min of vol normalization

    Args:
        quotes: DataFrame with ['timestamp', 'bid', 'ask'] (or 'mid').
        bucket_n_ticks: how many quote updates fill one bucket.
        window_n_buckets: rolling window for the VPIN average.
        bvc_sigma_lookback: trailing std lookback for BVC normalization.

    Returns:
        VPINResult with VPIN ∈ [0, 1] series + bucket time boundaries.

    Raises:
        ValueError: if `quotes` is too short (< sigma_lookback + 100 rows)
            or all quotes have invalid mid-price.
    """
    synth = quotes_to_synthetic_trades(quotes)
    estimator = VPINEstimator(
        bucket_volume=float(bucket_n_ticks),
        window_n_buckets=window_n_buckets,
        bvc_sigma_lookback=bvc_sigma_lookback,
    )
    return estimator.compute(synth)


__all__ = [
    "VPINEstimator",
    "VPINResult",
    "compute_vpin_from_fx_quotes",
    "quotes_to_synthetic_trades",
]
