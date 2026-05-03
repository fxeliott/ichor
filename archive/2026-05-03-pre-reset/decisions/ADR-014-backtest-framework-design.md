# ADR-014 — Backtest framework design (paper-only walk-forward)

- **Date** : 2026-05-03
- **Status** : Accepted
- **Decider** : autonomous BLOC C1 (Eliot validated v2 plan)

## Context

Phase 1 needs a backtest framework to evaluate the bias models before
they ever influence a real trade. The framework must :

1. Refuse to ship a backtest with **data leakage** (a feature derived
   from data ≥ test timestamp).
2. Use **walk-forward** evaluation, never random k-fold (autocorrelated
   timeseries break i.i.d. assumptions).
3. Model **fees + slippage** so paper P&L is comparable to what a real
   strategy would produce.
4. Be **paper-only by contract** — no code path can submit a real order.
5. Be **fast enough** to run a full 10-year EUR/USD walk-forward in
   < 30 s on the Hetzner CX32 (so iteration is cheap).

## Decision

A new package `packages/backtest/` with five concerns separated :

| File | Concern |
|---|---|
| `types.py` | `BacktestConfig`, `BacktestResult`, `Signal`, `Fold`, `EquityPoint` (frozen dataclasses, `paper_only=True` invariant) |
| `leakage.py` | `LeakageGuard` (raises `LeakageViolation`) — must be called by predictor |
| `fees.py` | `FlatFeeSlippageModel` with per-asset overrides ; `FeeSlippageModel` Protocol for swap |
| `walkforward.py` | `WalkForwardSplitter` enforces non-overlapping, strictly-disjoint train/test |
| `data.py` | `SyntheticDataGenerator` (regime-switching GBM, no DB) + `load_market_data_from_db` (BLOC A hypertable) |
| `runner.py` | `run_backtest(bars, predict_fn, cfg)` = the orchestrator. Single-asset. Multi-asset = run-then-aggregate. |

### Predictor contract

```python
PredictFn = Callable[[list[Bar], Fold], dict[date, Signal]]
```

The caller-supplied predictor receives the **train-window bars only** and
the fold metadata. It must return a `bar_date → Signal` mapping for the
test window. Missing dates = no trade.

This signature was chosen over a class-based `Predictor.fit().predict()`
because :

- Functional API plays nicely with closures + the planned LightGBM /
  XGBoost wrappers.
- Caller controls fitting, holds optimizer state, can warm-start across
  folds if desired (we just don't help with that today).
- Easier to test with `_always_long_predictor` lambdas.

### Position sizing

Fixed-fraction `position_size_pct` of equity per signal (default 10 %).
Real risk-managed sizing comes from `packages/risk/` (BLOC C2) which is
overlaid on top of the raw signals before they reach the runner.

### Fee model

`FlatFeeSlippageModel` : per-side fee + slippage in bps. Buys fill above
reference, sells below. Per-asset overrides for crowded vs exotic.
Default 1 bp + 1 bp = 2 bps round-trip per side, 4 bps round-trip total
— close to retail FX (EUR/USD ~3-5 bps).

### Walk-forward defaults

- `train_days = 730` (2 y)
- `test_days = 90` (1 quarter)
- `step_days = 90` (no overlap)
- `min_train_days = 252` (refuse < 1 y of training)

These are sane defaults for daily-bar models. Overrideable per run.

### Leakage guard

Two assertions :

1. `guard.check(signal_timestamp, latest_observed_date)` — raised when
   features peeked into the future. Predictor must call this for every
   feature snapshot.
2. `guard.assert_train_test_disjoint(train_end, test_start)` — runner
   self-checks per fold.

Disabled-by-default = NEVER. Tests for both raises are mandatory.

## Alternatives considered

- **Use [`backtesting.py`](https://github.com/kernc/backtesting.py)** :
  GPL-3.0 — incompatible with our private commercial-friendly posture.
- **Use [`vectorbt`](https://vectorbt.dev/)** : excellent but ~80 MB of
  deps + non-trivial walk-forward semantics + steep learning curve.
  Worth revisiting Phase 2.
- **Use [`backtrader`](https://www.backtrader.com/)** : abandonware
  since 2020.
- **Pure pandas / numpy custom** (this) : 500 LoC + zero new deps,
  full control, easy to extend.

## Consequences

Positive :

- 17 unit tests cover the whole surface (leakage, walkforward, fees,
  synthetic generator, runner end-to-end).
- Synthetic generator means CI can run a full backtest pipeline test
  without DB dependency.
- DB loader is async + plugs into BLOC A `market_data` hypertable —
  zero impedance with the broader platform.
- Multi-asset = N sequential runs + aggregator. We can parallelize
  later via `asyncio.gather` or process-pool.

Negative :

- Single-asset runner today. Cross-asset features (correlation, basket
  signals) need an aggregation layer not yet built.
- No intraday support — daily bars only. Phase 1 OANDA M1 needs a
  resample step.
- No path-dependent metrics yet (Sortino, Calmar, conditional VaR).
  Easy to add ; deferred until Phase 1 backtests demand them.

## Verification

- 17 unit tests in `packages/backtest/tests/test_backtest.py` :
  - 4 leakage guard scenarios
  - 3 walkforward contract tests
  - 3 fee model tests
  - 2 synthetic generator tests (shape + reproducibility)
  - 5 runner tests (smoke, flat, empty refuse, paper invariant,
    fees-bite sanity)

- Smoke run (synthetic GBM, 2200 days EUR/USD, fixed-long predictor) :
  - 17 folds emitted
  - Equity curve non-empty
  - Sharpe + max DD + Brier + hit rate all populated
  - Paper invariant verified

## Trading rules respected

- `BacktestResult.paper_only = True` is set by the runner ; the field
  has no setter ; tests assert it. ADR-016 contract honored.
- No code path here imports a real-broker SDK.
- Fee + slippage realism = paper P&L is conservative vs zero-cost
  models (test `test_runner_fees_reduce_pnl_vs_zero_fees` asserts).
- Leakage guard is enabled by default ; disabling requires explicit
  `LeakageGuard(enabled=False)` (visible in code review).
