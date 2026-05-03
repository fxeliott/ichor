"""The backtest executor.

`run_backtest(bars, predict_fn, config)`:
  - Splits the bar history into walk-forward folds.
  - For each fold : train period is presented to `predict_fn(train_bars)`
    which must return a (asset, bar_date) → Signal mapping for the test
    window.
  - Walks the test window bar-by-bar : applies the signal at next-bar-open,
    accumulates equity using fee/slippage model, and records the equity curve.
  - Computes metrics : Sharpe, max DD, hit rate, Brier.

ALL paper. ADR-016 forbids any code path here from talking to a real broker.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import date, datetime, timezone

import structlog

from .data import Bar
from .fees import FlatFeeSlippageModel
from .leakage import LeakageGuard
from .types import (
    BacktestConfig,
    BacktestResult,
    EquityPoint,
    Fold,
    Signal,
)
from .walkforward import WalkForwardSplitter

log = structlog.get_logger(__name__)


PredictFn = Callable[[list[Bar], Fold], dict[date, Signal]]
"""Caller-supplied predictor.

Args :
  - train_bars : the bars in the fold's training window. Predictor must
    fit on these and ONLY these.
  - fold : the fold being evaluated (gives test window bounds).

Returns :
  - dict mapping `bar_date` (∈ fold.test window) → `Signal`. Missing
    dates are interpreted as "flat / no trade today".
"""


def _annualized_sharpe(daily_returns: list[float]) -> float:
    if len(daily_returns) < 2:
        return 0.0
    mean = sum(daily_returns) / len(daily_returns)
    var = sum((r - mean) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
    std = math.sqrt(var)
    if std == 0:
        return 0.0
    return mean / std * math.sqrt(252)


def _max_drawdown(equity: list[float]) -> float:
    if not equity:
        return 0.0
    peak = equity[0]
    max_dd = 0.0
    for v in equity:
        peak = max(peak, v)
        dd = (peak - v) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)
    return max_dd


def _brier(signals: list[Signal], realized_up: list[bool]) -> float:
    """Brier score for binary direction. Lower is better.

    Per-signal: (probability - realized_outcome)^2 where outcome ∈ {0, 1}.
    For "long" signals, outcome = 1 if next bar closed higher.
    For "short" signals, outcome = 1 if next bar closed lower.
    """
    if len(signals) != len(realized_up) or not signals:
        return 0.0
    total = 0.0
    for s, up in zip(signals, realized_up):
        if s.direction == "flat":
            continue
        outcome = 1.0 if (
            (s.direction == "long" and up) or (s.direction == "short" and not up)
        ) else 0.0
        total += (s.probability - outcome) ** 2
    n = sum(1 for s in signals if s.direction != "flat")
    return total / n if n > 0 else 0.0


def run_backtest(
    bars: list[Bar],
    predict_fn: PredictFn,
    config: BacktestConfig | None = None,
    *,
    fee_model: FlatFeeSlippageModel | None = None,
    leakage_guard: LeakageGuard | None = None,
) -> BacktestResult:
    """Execute a walk-forward backtest. PAPER ONLY.

    `bars` must be sorted by `bar_date` and contain a SINGLE asset.
    Multi-asset backtests = run once per asset and aggregate downstream.
    """
    if not bars:
        raise ValueError("Cannot backtest on empty bars")
    cfg = config or BacktestConfig()
    fees = fee_model or FlatFeeSlippageModel(
        fee_bps=cfg.fee_bps, slippage_bps=cfg.slippage_bps,
    )
    guard = leakage_guard or LeakageGuard()

    bars_by_date = {b.bar_date: b for b in bars}
    asset = bars[0].asset
    assert all(b.asset == asset for b in bars), "Backtest is single-asset"

    splitter = WalkForwardSplitter(
        train_days=cfg.walk_forward_train_days,
        test_days=cfg.walk_forward_test_days,
        step_days=cfg.walk_forward_step_days,
        min_train_days=cfg.min_train_days,
    )
    folds = list(splitter.split(bars[0].bar_date, bars[-1].bar_date))
    if not folds:
        raise ValueError(
            f"No folds : history {bars[0].bar_date} → {bars[-1].bar_date} "
            "shorter than train_days + test_days"
        )

    started = datetime.now(timezone.utc)
    equity = cfg.initial_equity
    equity_curve: list[EquityPoint] = []
    all_signals: list[Signal] = []
    realized_up: list[bool] = []
    n_trades = 0
    notes: list[str] = []

    for fold in folds:
        guard.assert_train_test_disjoint(fold.train_end, fold.test_start)
        train_bars = [
            b for b in bars
            if fold.train_start <= b.bar_date <= fold.train_end
        ]
        if len(train_bars) < cfg.min_train_days:
            notes.append(
                f"skipped fold {fold.train_start}/{fold.test_start} : "
                f"only {len(train_bars)} train bars"
            )
            continue

        try:
            signals_by_date = predict_fn(train_bars, fold)
        except Exception as e:
            log.error("backtest.predict_failed", fold_start=str(fold.train_start), error=str(e))
            notes.append(f"predict_fn failed on fold {fold.train_start}: {e}")
            continue

        # Walk the test window
        test_dates = sorted(d for d in bars_by_date if fold.test_start <= d <= fold.test_end)
        position = 0.0  # signed quantity
        last_close = bars_by_date[test_dates[0]].close if test_dates else 0.0

        for i, d in enumerate(test_dates):
            bar = bars_by_date[d]
            sig = signals_by_date.get(d)

            # Mark to market with previous position
            realized_pnl = position * (bar.close - last_close)
            equity += realized_pnl

            # Decide new desired position based on signal
            desired = 0.0
            if sig is not None:
                guard.check(sig.timestamp, latest_observed_date=fold.train_end)
                if sig.direction == "long":
                    desired = (cfg.position_size_pct * equity) / bar.close
                elif sig.direction == "short":
                    desired = -(cfg.position_size_pct * equity) / bar.close
                all_signals.append(sig)
                # Realized "up" outcome = next bar close > this bar close
                next_d = test_dates[i + 1] if i + 1 < len(test_dates) else None
                if next_d is not None:
                    realized_up.append(bars_by_date[next_d].close > bar.close)
                else:
                    # Drop the trailing signal — no next-bar realization
                    all_signals.pop()

            # Trade if needed
            delta = desired - position
            if abs(delta) > 1e-9:
                side = "buy" if delta > 0 else "sell"
                fill = fees.fill_price(side, bar.close, asset)
                cost = abs(delta) * (fill - bar.close)
                equity -= cost
                position = desired
                n_trades += 1

            equity_curve.append(
                EquityPoint(
                    timestamp=d,
                    asset=asset,
                    equity=equity,
                    position=position,
                    bar_close=bar.close,
                    realized_pnl_bar=realized_pnl,
                )
            )
            last_close = bar.close

    # Compute metrics
    daily_returns: list[float] = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1].equity
        cur = equity_curve[i].equity
        if prev > 0:
            daily_returns.append((cur - prev) / prev)

    metrics = {
        "sharpe_ann": _annualized_sharpe(daily_returns),
        "max_drawdown": _max_drawdown([p.equity for p in equity_curve]),
        "total_return_pct": (
            (equity_curve[-1].equity / cfg.initial_equity - 1) * 100
            if equity_curve else 0.0
        ),
        "brier": _brier(all_signals, realized_up),
        "hit_rate": (
            sum(1 for s, up in zip(all_signals, realized_up)
                if (s.direction == "long" and up)
                or (s.direction == "short" and not up))
            / len(all_signals) if all_signals else 0.0
        ),
        "n_signals": float(len(all_signals)),
        "n_trades": float(n_trades),
    }

    return BacktestResult(
        config=cfg,
        folds=folds,
        equity_curve=equity_curve,
        n_signals=len(all_signals),
        n_trades=n_trades,
        metrics=metrics,
        notes=notes,
        paper_only=True,
        started_at=started,
        finished_at=datetime.now(timezone.utc),
    )
