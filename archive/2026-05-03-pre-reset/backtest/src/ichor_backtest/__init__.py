"""Ichor backtest framework — walk-forward + leakage guard + fee/slippage.

PAPER-ONLY by ADR-016. No code path in this package may submit real orders
to a broker. The `Broker` interface used by `BacktestRun` is the in-memory
paper broker only.
"""

from .types import (
    BacktestConfig,
    BacktestResult,
    EquityPoint,
    Fold,
    Signal,
)
from .data import SyntheticDataGenerator, load_market_data_from_db
from .leakage import LeakageGuard, LeakageViolation
from .fees import FlatFeeSlippageModel, FeeSlippageModel
from .walkforward import walk_forward_splits, WalkForwardSplitter
from .runner import run_backtest

__all__ = [
    "BacktestConfig",
    "BacktestResult",
    "EquityPoint",
    "Fold",
    "Signal",
    "SyntheticDataGenerator",
    "load_market_data_from_db",
    "LeakageGuard",
    "LeakageViolation",
    "FlatFeeSlippageModel",
    "FeeSlippageModel",
    "walk_forward_splits",
    "WalkForwardSplitter",
    "run_backtest",
]
