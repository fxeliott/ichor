"""Leakage guard — refuse to ship a backtest where features peeked into
the future.

The simplest, hardest invariant we can enforce :
  any feature used to produce a Signal at time t must be derived from
  bars with bar_date ≤ t.

`LeakageGuard.check(signal, latest_observed_date)` raises
`LeakageViolation` if `latest_observed_date > signal.timestamp`. Models
must call this in their feature-extraction step.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


class LeakageViolation(AssertionError):
    """Raised when a backtest signal was produced using future data."""


@dataclass
class LeakageGuard:
    """Enforce feature_t ⊥ data > t.

    Usage at training-time : pass `latest_observed_date` of every feature
    snapshot you used. The guard refuses to record the signal if the
    feature window peeked into the future.
    """

    enabled: bool = True

    def check(self, signal_timestamp: date, latest_observed_date: date) -> None:
        if not self.enabled:
            return
        if latest_observed_date > signal_timestamp:
            raise LeakageViolation(
                f"Feature snapshot uses data through {latest_observed_date} "
                f"but signal is timestamped {signal_timestamp}. "
                "Backtest results would be unreliable."
            )

    def assert_train_test_disjoint(
        self, train_end: date, test_start: date
    ) -> None:
        if not self.enabled:
            return
        if test_start <= train_end:
            raise LeakageViolation(
                f"Train window ends {train_end} but test starts {test_start} — "
                "must be strictly after."
            )
