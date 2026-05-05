"""Daily feature engineering for FX / index / metal bias models.

Pipeline contract (matches `tests/test_features_and_lightgbm.py`) :
  - Input : ordered list of `BarLike(bar_date, asset, open, high, low, close)`.
  - Output : list of `FeatureRow(bar_date, features, target_up)` covering
    bars `[min_history, N-1)` — the last bar is dropped (no t+1 close to
    compute the target).
  - Features are 9 dimensional, all finite, computed using bars[:t+1] only
    (anti-leakage : the regression test compares full vs truncated runs
    bit-by-bit).

Feature definitions :
  - returns_1d  = (c[t] - c[t-1]) / c[t-1]
  - returns_5d  = (c[t] - c[t-5]) / c[t-5]
  - returns_20d = (c[t] - c[t-20]) / c[t-20]
  - vol_5d  = stddev of last 5 daily simple returns
  - vol_20d = stddev of last 20 daily simple returns
  - rsi_14  = Wilder's RSI on the last 14 closes
  - macd_diff = EMA12(close) - EMA26(close)
  - momentum_60d = (c[t] - c[t-60]) / c[t-60]
  - close_over_sma_50 = c[t] / mean(c[t-49 .. t]) - 1.0

`min_history` defaults to 60 — the widest lookback (momentum_60d) determines
the minimum bars needed before the first feature row.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

DEFAULT_MIN_HISTORY = 60

FEATURE_NAMES: tuple[str, ...] = (
    "returns_1d",
    "returns_5d",
    "returns_20d",
    "vol_5d",
    "vol_20d",
    "rsi_14",
    "macd_diff",
    "momentum_60d",
    "close_over_sma_50",
)


@dataclass(frozen=True)
class BarLike:
    """Minimal OHLC bar — the only protocol the feature pipeline needs."""

    bar_date: date
    asset: str
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class FeatureRow:
    bar_date: date
    asset: str
    features: dict[str, float]
    target_up: int  # 1 if next bar's close > this bar's close, else 0


# ─────────────────────── primitive helpers ───────────────────────


def _safe_pct_change(curr: float, prev: float) -> float:
    """Return (curr - prev) / prev, or 0.0 if prev is zero / NaN-ish."""
    if prev == 0.0 or math.isnan(prev):
        return 0.0
    return (curr - prev) / prev


def _stddev(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / (n - 1)  # sample stddev
    return var**0.5


def _rsi(closes: list[float], period: int = 14) -> float:
    """Wilder's RSI on the last `period+1` closes. Returns 50.0 (neutral)
    if there are fewer than period+1 closes — common in early rows but
    still better than NaN for downstream models."""
    if len(closes) < period + 1:
        return 50.0
    gains = 0.0
    losses = 0.0
    for i in range(len(closes) - period, len(closes)):
        diff = closes[i] - closes[i - 1]
        if diff >= 0:
            gains += diff
        else:
            losses += -diff
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0.0:
        return 100.0 if avg_gain > 0.0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _ema(values: list[float], span: int) -> float:
    """Exponential moving average with smoothing alpha = 2 / (span + 1).
    Returns the FINAL EMA value (the recursive series at index -1)."""
    if not values:
        return 0.0
    if len(values) < span:
        return sum(values) / len(values)  # SMA fallback when too few samples
    alpha = 2.0 / (span + 1)
    # Seed the EMA with the SMA of the first `span` values.
    seed = sum(values[:span]) / span
    ema = seed
    for v in values[span:]:
        ema = alpha * v + (1 - alpha) * ema
    return ema


def _sma(values: list[float], window: int) -> float:
    if not values:
        return 0.0
    tail = values[-window:]
    return sum(tail) / len(tail)


# ─────────────────────── feature row computation ─────────────────


def _compute_features(closes: list[float]) -> dict[str, float]:
    """Compute the 9 features assuming closes[-1] is the target bar.

    Caller guarantees `len(closes) >= 60`. Returns a dict keyed by
    FEATURE_NAMES with all values finite (no NaN, no inf)."""
    c = closes[-1]
    c_1 = closes[-2]
    c_5 = closes[-6]
    c_20 = closes[-21]
    c_60 = closes[-61]

    # Daily returns series for vol windows.
    returns_1d_series = [_safe_pct_change(closes[i], closes[i - 1]) for i in range(1, len(closes))]

    return {
        "returns_1d": _safe_pct_change(c, c_1),
        "returns_5d": _safe_pct_change(c, c_5),
        "returns_20d": _safe_pct_change(c, c_20),
        "vol_5d": _stddev(returns_1d_series[-5:]),
        "vol_20d": _stddev(returns_1d_series[-20:]),
        "rsi_14": _rsi(closes, period=14),
        "macd_diff": _ema(closes, 12) - _ema(closes, 26),
        "momentum_60d": _safe_pct_change(c, c_60),
        "close_over_sma_50": (c / _sma(closes, 50)) - 1.0 if _sma(closes, 50) else 0.0,
    }


def build_features_daily(
    bars: list[BarLike],
    *,
    min_history: int = DEFAULT_MIN_HISTORY,
) -> list[FeatureRow]:
    """Build the feature matrix from an ordered list of daily bars.

    Args:
        bars: chronological order, oldest first. Must all share the same
            asset (we don't cross-asset by design).
        min_history: minimum bars required before the first feature row.
            Defaults to 60 to support `momentum_60d`.

    Returns:
        List of `FeatureRow` covering bars `[min_history, N-1)`. Empty
        list if `len(bars) < min_history + 1` (one extra for the target).
    """
    n = len(bars)
    if n < min_history + 1:
        return []

    closes_full = [float(b.close) for b in bars]
    out: list[FeatureRow] = []

    # Loop over indices that have BOTH enough history AND a t+1 bar.
    for i in range(min_history, n - 1):
        # CRITICAL : feature computation must use only bars[:i+1] — no future
        # leakage. closes_view is bars[0..i] inclusive.
        closes_view = closes_full[: i + 1]
        feats = _compute_features(closes_view)

        # Target_up uses bars[i+1] ; it is the supervised signal, NOT a feature.
        target = 1 if bars[i + 1].close > bars[i].close else 0

        out.append(
            FeatureRow(
                bar_date=bars[i].bar_date,
                asset=bars[i].asset,
                features=feats,
                target_up=target,
            )
        )

    return out
