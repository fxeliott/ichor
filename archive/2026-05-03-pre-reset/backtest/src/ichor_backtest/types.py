"""Public dataclasses + type aliases for the backtest framework.

PAPER-ONLY by ADR-016 — `BacktestResult` carries no broker IDs, no real
fills, no live PnL. Equity curve is theoretical.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal


SignalDirection = Literal["long", "short", "flat"]


@dataclass(frozen=True)
class Signal:
    """A single timestep model output for one asset.

    `timestamp` MUST be the bar-close timestamp at which the signal becomes
    actionable. The leakage guard asserts that the underlying features
    were derived from data ≤ `timestamp`.
    """

    asset: str
    timestamp: date
    direction: SignalDirection
    probability: float  # in [0, 1]
    feature_snapshot_hash: str = ""


@dataclass(frozen=True)
class Fold:
    """A walk-forward fold : training window + out-of-sample test window.

    Train and test must be disjoint and contiguous (test starts the day
    after train ends). The runner enforces this.
    """

    train_start: date
    train_end: date
    test_start: date
    test_end: date

    def __post_init__(self) -> None:
        assert self.train_start <= self.train_end, "train_start ≤ train_end"
        assert self.test_start <= self.test_end, "test_start ≤ test_end"
        assert self.train_end < self.test_start, (
            "test must start strictly after train (else leakage)"
        )


@dataclass
class EquityPoint:
    """One point of the equity curve."""

    timestamp: date
    asset: str
    equity: float        # cumulative theoretical PnL in cash units
    position: float      # signed quantity held going into this bar
    bar_close: float
    realized_pnl_bar: float  # PnL realized this bar (mark-to-market move)


@dataclass
class BacktestConfig:
    """Knobs for `run_backtest`."""

    initial_equity: float = 10_000.0
    """Theoretical starting capital. PAPER ONLY."""

    position_size_pct: float = 0.10
    """Per-trade risk fraction of equity (Kelly-cap default 10 %)."""

    fee_bps: float = 1.0
    """Fee in basis points per side (1 bp = 0.01 %)."""

    slippage_bps: float = 1.0
    """One-sided slippage in bps applied to fill price."""

    walk_forward_train_days: int = 365 * 2
    """Training window per fold, calendar days."""

    walk_forward_test_days: int = 90
    """Test window per fold, calendar days."""

    walk_forward_step_days: int = 90
    """Step between fold start dates. Equal to test window = no overlap."""

    min_train_days: int = 252
    """Refuse to fit on < N days of training data."""


@dataclass
class BacktestResult:
    """Output of `run_backtest`. PAPER ONLY."""

    config: BacktestConfig
    folds: list[Fold]
    equity_curve: list[EquityPoint]
    n_signals: int
    n_trades: int
    metrics: dict[str, float] = field(default_factory=dict)
    """Computed metrics : sharpe, max_drawdown, brier, hit_rate, total_return_pct."""

    notes: list[str] = field(default_factory=list)
    """Free-form notes (e.g. dropped folds, leakage warnings — should be empty)."""

    paper_only: bool = True
    """ALWAYS True. ADR-016 forbids any other value."""

    started_at: datetime | None = None
    finished_at: datetime | None = None
