"""End-to-end + unit tests for the backtest framework.

Uses synthetic data only — no DB, no network. Validates :
- Walk-forward fold contracts (no overlap, train < test)
- Leakage guard refuses signals derived from future data
- Fee/slippage model is symmetric and rounds correctly
- Runner produces a non-empty equity curve + sane metrics on a
  always-long predictor against a zero-EV synthetic series
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from ichor_backtest import (
    BacktestConfig,
    FlatFeeSlippageModel,
    Fold,
    LeakageGuard,
    LeakageViolation,
    Signal,
    SyntheticDataGenerator,
    WalkForwardSplitter,
    run_backtest,
    walk_forward_splits,
)


# ───────────────────────── leakage guard ─────────────────────────


def test_leakage_guard_passes_when_observed_at_or_before_signal() -> None:
    g = LeakageGuard()
    g.check(date(2026, 5, 1), latest_observed_date=date(2026, 5, 1))  # OK
    g.check(date(2026, 5, 1), latest_observed_date=date(2026, 4, 30))  # OK


def test_leakage_guard_raises_on_future_data() -> None:
    g = LeakageGuard()
    with pytest.raises(LeakageViolation):
        g.check(date(2026, 5, 1), latest_observed_date=date(2026, 5, 2))


def test_leakage_guard_disabled_lets_through() -> None:
    g = LeakageGuard(enabled=False)
    g.check(date(2026, 5, 1), latest_observed_date=date(2026, 12, 31))


def test_leakage_guard_train_test_disjoint_raises() -> None:
    g = LeakageGuard()
    with pytest.raises(LeakageViolation):
        g.assert_train_test_disjoint(
            train_end=date(2026, 5, 31), test_start=date(2026, 5, 31),
        )


# ───────────────────────── walkforward ─────────────────────────


def test_walkforward_no_overlap() -> None:
    folds = walk_forward_splits(
        date(2020, 1, 1), date(2026, 1, 1),
        train_days=730, test_days=90, step_days=90,
    )
    assert len(folds) > 5
    test_dates = []
    for f in folds:
        d = f.test_start
        while d <= f.test_end:
            assert d not in test_dates, f"Duplicate test date {d} across folds"
            test_dates.append(d)
            d += timedelta(days=1)


def test_walkforward_train_strictly_before_test() -> None:
    folds = walk_forward_splits(date(2020, 1, 1), date(2026, 1, 1))
    for f in folds:
        assert f.train_end < f.test_start


def test_walkforward_returns_empty_when_history_too_short() -> None:
    folds = walk_forward_splits(
        date(2026, 1, 1), date(2026, 2, 1),
        train_days=730, test_days=90,
    )
    assert folds == []


# ───────────────────────── fees ─────────────────────────


def test_fee_model_buy_above_sell_below_reference() -> None:
    fees = FlatFeeSlippageModel(fee_bps=1.0, slippage_bps=1.0)
    ref = 100.0
    buy = fees.fill_price("buy", ref, "EUR_USD")
    sell = fees.fill_price("sell", ref, "EUR_USD")
    assert buy > ref > sell
    # 2 bps total impact each side
    assert abs(buy - 100.02) < 1e-6
    assert abs(sell - 99.98) < 1e-6


def test_fee_model_per_asset_override() -> None:
    fees = FlatFeeSlippageModel(
        fee_bps=1.0,
        slippage_bps=1.0,
        per_asset_overrides={"XAU_USD": (3.0, 5.0)},  # wider
    )
    eur_buy = fees.fill_price("buy", 100.0, "EUR_USD")
    xau_buy = fees.fill_price("buy", 100.0, "XAU_USD")
    assert xau_buy > eur_buy


def test_fee_model_round_trip_cost_bps() -> None:
    fees = FlatFeeSlippageModel(fee_bps=1.5, slippage_bps=2.0)
    assert fees.round_trip_cost_bps("EUR_USD") == 7.0  # 2 * (1.5 + 2)


# ───────────────────────── synthetic data ─────────────────────────


def test_synthetic_generator_produces_n_business_days() -> None:
    gen = SyntheticDataGenerator(seed=1)
    bars = gen.generate("EUR_USD", date(2024, 1, 1), n_days=100, initial_price=1.10)
    assert 99 <= len(bars) <= 101  # rounding on weekend skip
    assert all(b.asset == "EUR_USD" for b in bars)
    assert all(b.high >= b.low for b in bars)
    assert all(b.high >= b.open for b in bars)
    assert all(b.high >= b.close for b in bars)
    assert all(b.low <= b.open for b in bars)
    assert all(b.low <= b.close for b in bars)


def test_synthetic_generator_reproducible_with_seed() -> None:
    a = SyntheticDataGenerator(seed=7).generate("EUR_USD", date(2024, 1, 1), 50)
    b = SyntheticDataGenerator(seed=7).generate("EUR_USD", date(2024, 1, 1), 50)
    assert [x.close for x in a] == [x.close for x in b]


# ───────────────────────── runner ─────────────────────────


def _always_long_predictor(train_bars, fold):
    """Always predict long with p=0.55 — used to verify the runner exec path."""
    out: dict[date, Signal] = {}
    cursor = fold.test_start
    while cursor <= fold.test_end:
        if cursor.weekday() < 5:
            out[cursor] = Signal(
                asset=train_bars[0].asset,
                timestamp=cursor,
                direction="long",
                probability=0.55,
            )
        cursor += timedelta(days=1)
    return out


def _always_flat_predictor(train_bars, fold):
    return {}


def test_runner_smoke_end_to_end() -> None:
    gen = SyntheticDataGenerator(seed=42)
    bars = gen.generate("EUR_USD", date(2018, 1, 1), n_days=2200, initial_price=1.10)
    cfg = BacktestConfig(
        walk_forward_train_days=500,
        walk_forward_test_days=120,
        walk_forward_step_days=120,
        min_train_days=200,
    )
    res = run_backtest(bars, _always_long_predictor, cfg)

    assert res.paper_only is True
    assert len(res.folds) >= 3
    assert res.n_signals > 0
    assert res.n_trades > 0
    assert "sharpe_ann" in res.metrics
    assert "max_drawdown" in res.metrics
    assert "brier" in res.metrics
    assert "hit_rate" in res.metrics
    # Brier on a coin-flip GBM with constant p=0.55 is in a reasonable range
    assert 0.0 <= res.metrics["brier"] <= 0.5
    # Equity curve is non-empty
    assert len(res.equity_curve) > 0


def test_runner_zero_trades_on_flat_predictor() -> None:
    gen = SyntheticDataGenerator(seed=99)
    bars = gen.generate("EUR_USD", date(2020, 1, 1), n_days=1500)
    cfg = BacktestConfig(
        walk_forward_train_days=400,
        walk_forward_test_days=90,
        walk_forward_step_days=90,
        min_train_days=200,
    )
    res = run_backtest(bars, _always_flat_predictor, cfg)
    assert res.n_trades == 0
    assert res.n_signals == 0


def test_runner_refuses_empty_bars() -> None:
    with pytest.raises(ValueError):
        run_backtest([], _always_flat_predictor)


def test_runner_paper_only_invariant() -> None:
    """ADR-016: BacktestResult.paper_only must always be True."""
    gen = SyntheticDataGenerator(seed=1)
    bars = gen.generate("EUR_USD", date(2022, 1, 1), n_days=900)
    cfg = BacktestConfig(
        walk_forward_train_days=400, walk_forward_test_days=90,
        walk_forward_step_days=90, min_train_days=200,
    )
    res = run_backtest(bars, _always_flat_predictor, cfg)
    assert res.paper_only is True


def test_runner_fees_reduce_pnl_vs_zero_fees() -> None:
    """A trade-heavy strategy under fees must underperform same strategy
    under zero fees (sanity check the fee model actually bites)."""
    gen = SyntheticDataGenerator(seed=7)
    bars = gen.generate("EUR_USD", date(2020, 1, 1), n_days=1500)

    cfg_with_fees = BacktestConfig(
        walk_forward_train_days=400, walk_forward_test_days=90,
        walk_forward_step_days=90, min_train_days=200,
        fee_bps=10, slippage_bps=10,  # exaggerated
    )
    cfg_no_fees = BacktestConfig(
        walk_forward_train_days=400, walk_forward_test_days=90,
        walk_forward_step_days=90, min_train_days=200,
        fee_bps=0, slippage_bps=0,
    )

    with_fees = run_backtest(bars, _always_long_predictor, cfg_with_fees)
    no_fees = run_backtest(bars, _always_long_predictor, cfg_no_fees)

    # Same predictor, same data → fees can only subtract
    assert with_fees.metrics["total_return_pct"] <= no_fees.metrics["total_return_pct"]
