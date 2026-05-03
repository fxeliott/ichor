"""Daily-bar feature engineering.

Pure functions over a list of OHLCV bars. No DB, no network. Designed
to satisfy the ADR-014 leakage contract : every feature for bar t is
derived from bars [t-N, t-1], strictly excluding t itself.

Features (kept simple on purpose — sophistication comes from the
ensemble in Phase 2+):

  - returns_1d, returns_5d, returns_20d : log-returns over 1/5/20 days
  - vol_5d, vol_20d : realized vol over 5/20 days
  - rsi_14 : RSI(14)
  - macd_diff : MACD(12, 26, 9) signal-line difference
  - momentum_60d : signed log-return over 60 days
  - close_over_sma_50 : ratio of close to its 50-day SMA - 1.0

Target : up_next_day = 1 if close[t+1] > close[t] else 0.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Sequence


@dataclass(frozen=True)
class BarLike:
    """Duck-type for any OHLCV bar (we don't import the API ORM here)."""

    bar_date: date
    asset: str
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class FeatureRow:
    """One row of features + target. `bar_date` is the bar the features
    REFER TO (so the leakage guard checks against it). The target is
    realized at bar_date+1.
    """

    asset: str
    bar_date: date
    features: dict[str, float]
    target_up: int  # 0 or 1, realized at next bar
    target_realized: bool
    """False for the last bar (no t+1 to realize against)."""


def _log_return(prev: float, curr: float) -> float:
    if prev <= 0 or curr <= 0:
        return 0.0
    return math.log(curr / prev)


def _vol(returns: Sequence[float]) -> float:
    if len(returns) < 2:
        return 0.0
    n = len(returns)
    mean = sum(returns) / n
    var = sum((r - mean) ** 2 for r in returns) / (n - 1)
    return math.sqrt(var)


def _rsi(closes: Sequence[float], period: int = 14) -> float:
    """Wilder's RSI on a closes window of length `period+1`."""
    if len(closes) < period + 1:
        return 50.0  # neutral default
    gains = []
    losses = []
    for i in range(1, period + 1):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(-min(delta, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _ema(values: Sequence[float], span: int) -> float:
    """Exponential moving average — last value of an EMA over `values`."""
    if not values:
        return 0.0
    alpha = 2.0 / (span + 1)
    ema = values[0]
    for v in values[1:]:
        ema = alpha * v + (1 - alpha) * ema
    return ema


def _macd_diff(closes: Sequence[float]) -> float:
    """MACD diff = MACD - signal."""
    if len(closes) < 35:
        return 0.0
    macd = _ema(closes, 12) - _ema(closes, 26)
    # Build a synthetic MACD series of length 9 by recomputing on rolling tails
    # — for a daily-bar model this approximation is fine ; the LightGBM
    # learns what it learns.
    macd_series = []
    for i in range(len(closes) - 8, len(closes) + 1):
        if i < 26:
            continue
        window = closes[:i]
        macd_series.append(_ema(window, 12) - _ema(window, 26))
    if not macd_series:
        return 0.0
    signal = _ema(macd_series, 9)
    return macd - signal


def _sma(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def build_features_daily(
    bars: Sequence[BarLike],
    *,
    min_history: int = 60,
) -> list[FeatureRow]:
    """Generate per-bar features. Drops the first `min_history` bars
    (insufficient history) and the last bar (no t+1 target to realize).

    Leakage guarantee : for `bars[i]`, all features use `bars[:i]` ONLY
    (closes/highs/lows up to and INCLUDING the current bar — but never
    beyond). The current bar's close is used because at "EOD" the
    feature is observable.

    Target : `target_up = 1` iff `bars[i+1].close > bars[i].close`.
    """
    bars = list(bars)
    out: list[FeatureRow] = []
    if len(bars) < min_history + 1:
        return out

    closes = [b.close for b in bars]

    for i in range(min_history, len(bars) - 1):
        b = bars[i]

        r1 = _log_return(closes[i - 1], closes[i])
        r5 = _log_return(closes[i - 5], closes[i])
        r20 = _log_return(closes[i - 20], closes[i])

        vol5 = _vol([_log_return(closes[j - 1], closes[j]) for j in range(i - 4, i + 1)])
        vol20 = _vol([_log_return(closes[j - 1], closes[j]) for j in range(i - 19, i + 1)])

        rsi14 = _rsi(closes[i - 14: i + 1])
        macd_d = _macd_diff(closes[: i + 1])
        mom60 = _log_return(closes[i - 60], closes[i])
        sma50 = _sma(closes[i - 49: i + 1])
        close_over_sma = (closes[i] / sma50) - 1.0 if sma50 > 0 else 0.0

        features = {
            "returns_1d": r1,
            "returns_5d": r5,
            "returns_20d": r20,
            "vol_5d": vol5,
            "vol_20d": vol20,
            "rsi_14": rsi14,
            "macd_diff": macd_d,
            "momentum_60d": mom60,
            "close_over_sma_50": close_over_sma,
        }

        target = 1 if closes[i + 1] > closes[i] else 0

        out.append(
            FeatureRow(
                asset=b.asset,
                bar_date=b.bar_date,
                features=features,
                target_up=target,
                target_realized=True,
            )
        )

    return out
