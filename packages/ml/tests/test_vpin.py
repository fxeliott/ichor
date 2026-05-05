"""Tests for VPIN — equity trade variant + FX quote-tick variant."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Allow direct import without depending on pip-install of the package.
SRC = Path(__file__).parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


pytest.importorskip("scipy", reason="scipy required for VPIN BVC")

from ichor_ml.microstructure.vpin import (  # noqa: E402
    VPINEstimator,
    VPINResult,
    compute_vpin_from_fx_quotes,
    quotes_to_synthetic_trades,
)

# ───────────────────────── Synthetic generators ─────────────────────────


def _trades_brownian(
    n: int = 1500, seed: int = 42, drift: float = 0.0, vol: float = 1e-4
) -> pd.DataFrame:
    """Geometric Brownian price walk + uniform unit volume."""
    rng = np.random.default_rng(seed)
    log_returns = rng.normal(loc=drift, scale=vol, size=n)
    prices = np.exp(np.cumsum(log_returns)) * 1.10
    ts = pd.date_range("2026-05-01", periods=n, freq="100ms")
    return pd.DataFrame({"timestamp": ts, "price": prices, "volume": 1.0})


def _quotes_from_trades(trades: pd.DataFrame, *, spread_bp: float = 0.5) -> pd.DataFrame:
    """Build a quote frame around the trade-tape mid-prices.

    bid = mid * (1 - spread_bp / 2 / 10_000)
    ask = mid * (1 + spread_bp / 2 / 10_000)
    """
    half = spread_bp / 2.0 / 10_000.0
    return pd.DataFrame(
        {
            "timestamp": trades["timestamp"].to_numpy(),
            "bid": trades["price"].to_numpy() * (1 - half),
            "ask": trades["price"].to_numpy() * (1 + half),
        }
    )


# ───────────────────────── VPINEstimator core ─────────────────────────


def test_vpin_estimator_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError, match="bucket_volume"):
        VPINEstimator(bucket_volume=0)
    with pytest.raises(ValueError, match="bucket_volume"):
        VPINEstimator(bucket_volume=-1)
    with pytest.raises(ValueError, match="window_n_buckets"):
        VPINEstimator(bucket_volume=100, window_n_buckets=4)
    with pytest.raises(ValueError, match="bvc_sigma_lookback"):
        VPINEstimator(bucket_volume=100, bvc_sigma_lookback=10)


def test_vpin_estimator_rejects_missing_columns() -> None:
    est = VPINEstimator(bucket_volume=20, bvc_sigma_lookback=100)
    bad = pd.DataFrame({"timestamp": [1, 2, 3], "price": [1.0, 1.0, 1.0]})
    with pytest.raises(ValueError, match="must have columns"):
        est.compute(bad)


def test_vpin_estimator_rejects_too_short_series() -> None:
    est = VPINEstimator(bucket_volume=20, bvc_sigma_lookback=100)
    short = _trades_brownian(n=150)
    with pytest.raises(ValueError, match="bootstrap VPIN"):
        est.compute(short)


def test_vpin_estimator_returns_values_in_unit_interval() -> None:
    est = VPINEstimator(bucket_volume=20, window_n_buckets=10, bvc_sigma_lookback=200)
    trades = _trades_brownian(n=2000)
    result = est.compute(trades)
    assert isinstance(result, VPINResult)
    valid = result.vpin.dropna()
    assert (valid >= 0).all() and (valid <= 1).all()
    assert result.n_buckets > 0


def test_vpin_drift_with_trending_price_should_be_higher_than_noise() -> None:
    """A trending price → BVC tags most of each bucket as buys → high |Vb-Vs|/V → high VPIN."""
    est = VPINEstimator(bucket_volume=20, window_n_buckets=10, bvc_sigma_lookback=200)
    noise = est.compute(_trades_brownian(n=2000, seed=1, drift=0.0, vol=1e-4))
    trend = est.compute(_trades_brownian(n=2000, seed=2, drift=5e-5, vol=1e-4))
    assert noise.latest is not None
    assert trend.latest is not None
    # Trending market should have higher toxicity than no-drift Brownian
    assert trend.latest > noise.latest


def test_vpin_result_latest_handles_warmup_nans() -> None:
    est = VPINEstimator(bucket_volume=20, window_n_buckets=50, bvc_sigma_lookback=200)
    # Just enough rows to bucket but not to fill the rolling window of 50
    trades = _trades_brownian(n=400)
    result = est.compute(trades)
    # We should still get a VPINResult ; .latest may be None if window not filled
    assert isinstance(result, VPINResult)
    # Sanity : no negative bucket counts
    assert result.n_buckets >= 0


# ───────────────────────── FX quote-tick adapter ─────────────────────────


def test_quotes_to_synthetic_trades_uses_mid_price() -> None:
    quotes = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-05-01", periods=4, freq="1s"),
            "bid": [1.0995, 1.1000, 1.1005, 1.1010],
            "ask": [1.1005, 1.1010, 1.1015, 1.1020],
        }
    )
    out = quotes_to_synthetic_trades(quotes)
    np.testing.assert_allclose(out["price"].to_numpy(), [1.1000, 1.1005, 1.1010, 1.1015])
    assert (out["volume"] == 1.0).all()


def test_quotes_to_synthetic_trades_accepts_mid_column_directly() -> None:
    quotes = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-05-01", periods=3, freq="1s"),
            "mid": [1.1000, 1.1010, 1.1020],
        }
    )
    out = quotes_to_synthetic_trades(quotes)
    np.testing.assert_allclose(out["price"].to_numpy(), [1.1000, 1.1010, 1.1020])


def test_quotes_to_synthetic_trades_drops_invalid_mids() -> None:
    quotes = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-05-01", periods=4, freq="1s"),
            "bid": [1.10, 0.0, np.nan, 1.10],
            "ask": [1.11, 0.0, np.nan, 1.11],
        }
    )
    out = quotes_to_synthetic_trades(quotes)
    assert len(out) == 2  # rows 1 and 2 dropped


def test_quotes_to_synthetic_trades_rejects_missing_columns() -> None:
    bad = pd.DataFrame({"timestamp": [1, 2], "bid": [1.10, 1.10]})
    with pytest.raises(ValueError, match=r"mid|bid"):
        quotes_to_synthetic_trades(bad)


def test_quotes_to_synthetic_trades_rejects_all_invalid_mids() -> None:
    quotes = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-05-01", periods=3, freq="1s"),
            "bid": [0.0, 0.0, 0.0],
            "ask": [0.0, 0.0, 0.0],
        }
    )
    with pytest.raises(ValueError, match="invalid mid-price"):
        quotes_to_synthetic_trades(quotes)


def test_compute_vpin_from_fx_quotes_end_to_end() -> None:
    """Full integration : synthetic FX quotes → VPIN result with bounded values."""
    base = _trades_brownian(n=1500, seed=7, vol=2e-5)
    quotes = _quotes_from_trades(base, spread_bp=0.5)
    result = compute_vpin_from_fx_quotes(
        quotes,
        bucket_n_ticks=20,
        window_n_buckets=10,
        bvc_sigma_lookback=200,
    )
    valid = result.vpin.dropna()
    assert len(valid) > 0
    assert (valid >= 0).all() and (valid <= 1).all()
    assert result.latest is not None and 0.0 <= result.latest <= 1.0


def test_compute_vpin_from_fx_quotes_trend_higher_than_noise() -> None:
    """Same trend-vs-noise property as on equity trades."""
    noise_q = _quotes_from_trades(_trades_brownian(n=2000, seed=11, drift=0.0))
    trend_q = _quotes_from_trades(_trades_brownian(n=2000, seed=12, drift=8e-5))
    n = compute_vpin_from_fx_quotes(
        noise_q, bucket_n_ticks=20, window_n_buckets=10, bvc_sigma_lookback=200
    )
    t = compute_vpin_from_fx_quotes(
        trend_q, bucket_n_ticks=20, window_n_buckets=10, bvc_sigma_lookback=200
    )
    assert n.latest is not None and t.latest is not None
    assert t.latest > n.latest
