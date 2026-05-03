"""Walk-forward fold generator.

Two contracts :
  1. Folds never overlap on the test window — each timestep appears in
     at-most-one out-of-sample evaluation.
  2. Train and test are contiguous — test starts the day after train ends.
     The leakage guard would refuse otherwise.

`step_days` controls advance between fold start dates. Equal to
`test_days` = no overlap (typical). Less = walk-forward with overlap
(uncommon, useful for high-frequency).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterator

from .types import Fold


@dataclass
class WalkForwardSplitter:
    train_days: int = 365 * 2
    test_days: int = 90
    step_days: int = 90
    min_train_days: int = 252

    def split(self, start: date, end: date) -> Iterator[Fold]:
        """Yield folds across [start, end].

        First fold's train_start = `start`. Train rolls forward by
        `step_days` each iteration. Stops when test_end would exceed `end`.
        """
        if (end - start).days < self.min_train_days + self.test_days:
            return

        cursor_train_start = start
        while True:
            train_end = cursor_train_start + timedelta(days=self.train_days - 1)
            test_start = train_end + timedelta(days=1)
            test_end = test_start + timedelta(days=self.test_days - 1)
            if test_end > end:
                return
            if (train_end - cursor_train_start).days + 1 < self.min_train_days:
                return
            yield Fold(
                train_start=cursor_train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
            )
            cursor_train_start = cursor_train_start + timedelta(days=self.step_days)


def walk_forward_splits(
    start: date,
    end: date,
    *,
    train_days: int = 365 * 2,
    test_days: int = 90,
    step_days: int = 90,
    min_train_days: int = 252,
) -> list[Fold]:
    """One-shot helper. Returns all folds as a list."""
    splitter = WalkForwardSplitter(
        train_days=train_days,
        test_days=test_days,
        step_days=step_days,
        min_train_days=min_train_days,
    )
    return list(splitter.split(start, end))
