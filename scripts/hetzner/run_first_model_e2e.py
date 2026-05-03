"""End-to-end first-model run on real Hetzner market_data.

Trains a LightGBM bias model per fold on EUR/USD 10y, runs walk-forward
backtest via packages/backtest, persists predictions to predictions_audit
table, prints a summary report against a buy-and-hold baseline.

Run on Hetzner:
  sudo -u ichor bash -c '
    cd /opt/ichor && source api/.venv/bin/activate &&
    PYTHONPATH="api/src/src:packages/backtest/src:packages/risk/src:packages/trading/src:packages/ml/src" \
    set -a && source /etc/ichor/api.env && set +a && \
    python /tmp/run_first_model_e2e.py EUR_USD
  '
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import sys
from datetime import datetime, timezone
from uuid import uuid4

# Lazy imports inside functions to keep the script-print-help path light.


async def _load_bars_from_db(asset: str):
    """Pull the asset's full daily history from the BLOC A hypertable."""
    from sqlalchemy import select
    from ichor_api.db import get_engine, get_sessionmaker
    from ichor_api.models import MarketDataBar

    sm = get_sessionmaker()
    async with sm() as session:
        stmt = (
            select(MarketDataBar)
            .where(MarketDataBar.asset == asset)
            .order_by(MarketDataBar.bar_date)
        )
        rows = (await session.execute(stmt)).scalars().all()
    return rows


def _bars_to_features_input(rows):
    """Adapter: ORM rows → `BarLike` for the feature builder + backtest."""
    from ichor_ml.training.features import BarLike

    seen = set()
    out = []
    for r in rows:
        if r.bar_date in seen:
            continue
        seen.add(r.bar_date)
        out.append(BarLike(
            bar_date=r.bar_date,
            asset=r.asset,
            open=float(r.open), high=float(r.high),
            low=float(r.low), close=float(r.close),
        ))
    return out


def _backtest_bars(rows):
    from ichor_backtest.data import Bar
    seen = set()
    out = []
    for r in rows:
        if r.bar_date in seen:
            continue
        seen.add(r.bar_date)
        out.append(Bar(
            bar_date=r.bar_date,
            asset=r.asset,
            open=float(r.open), high=float(r.high),
            low=float(r.low), close=float(r.close),
        ))
    return out


def _hash_features(feature_dict: dict[str, float]) -> str:
    parts = sorted(f"{k}={v:.6f}" for k, v in feature_dict.items())
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]


async def _persist_predictions(predictions, model_id: str, asset: str):
    """Append per-prediction rows to predictions_audit.

    `predictions` is a list of (bar_date, probability, direction,
    raw_score, feature_hash).
    """
    from ichor_api.db import get_engine, get_sessionmaker
    from ichor_api.models import Prediction

    sm = get_sessionmaker()
    now = datetime.now(timezone.utc)
    inserted = 0
    async with sm() as session:
        for bar_date, prob, direction, raw, fhash in predictions:
            session.add(Prediction(
                id=uuid4(),
                generated_at=datetime.combine(bar_date, datetime.min.time(),
                                              tzinfo=timezone.utc),
                model_id=model_id,
                model_family="lightgbm",
                asset=asset,
                horizon_hours=24,
                direction=direction,
                raw_score=raw,
                calibrated_probability=prob,
                feature_snapshot_hash=fhash,
            ))
            inserted += 1
        await session.commit()
    return inserted


async def _persist_backtest_run(res, model_id: str, asset: str):
    """Persist BacktestResult into backtest_runs for /backtests UI.

    Equity curve compressed to ~100 points to keep JSONB tight.
    """
    from ichor_api.db import get_sessionmaker
    from ichor_api.models import BacktestRun

    sample_step = max(1, len(res.equity_curve) // 100)
    summary = [
        {"date": p.timestamp.isoformat(), "equity": round(p.equity, 4)}
        for p in res.equity_curve[::sample_step]
    ]
    cfg_dict = {
        "initial_equity": res.config.initial_equity,
        "position_size_pct": res.config.position_size_pct,
        "fee_bps": res.config.fee_bps,
        "slippage_bps": res.config.slippage_bps,
        "walk_forward_train_days": res.config.walk_forward_train_days,
        "walk_forward_test_days": res.config.walk_forward_test_days,
        "walk_forward_step_days": res.config.walk_forward_step_days,
        "min_train_days": res.config.min_train_days,
    }

    sm = get_sessionmaker()
    now = datetime.now(timezone.utc)
    async with sm() as session:
        row = BacktestRun(
            id=uuid4(),
            created_at=now,
            model_id=model_id,
            asset=asset,
            started_at=res.started_at or now,
            finished_at=res.finished_at or now,
            config=cfg_dict,
            metrics={k: float(v) for k, v in res.metrics.items()},
            n_folds=len(res.folds),
            n_signals=res.n_signals,
            n_trades=res.n_trades,
            equity_curve_summary=summary,
            notes=res.notes or [],
            paper_only=res.paper_only,
        )
        session.add(row)
        await session.commit()
        return row.id


def _baseline_buy_and_hold(bars):
    """Compute B&H total return for comparison."""
    if not bars:
        return 0.0
    return (bars[-1].close / bars[0].close - 1) * 100


async def main(asset: str = "EUR_USD") -> int:
    print(f"[1/6] Loading bars for {asset} from market_data hypertable…")
    db_rows = await _load_bars_from_db(asset)
    if len(db_rows) < 500:
        print(f"  ✗ only {len(db_rows)} bars — need ≥500. Run market_data --persist first.")
        return 1
    print(f"  ✓ {len(db_rows)} bars loaded ({db_rows[0].bar_date} → {db_rows[-1].bar_date})")

    feature_bars = _bars_to_features_input(db_rows)
    backtest_bars = _backtest_bars(db_rows)

    print("[2/6] Setting up backtest harness…")
    from ichor_backtest import (
        BacktestConfig, FlatFeeSlippageModel, run_backtest, Signal,
    )
    from ichor_ml.training.lightgbm_bias import train_lightgbm_bias
    from ichor_ml.training.features import build_features_daily

    cfg = BacktestConfig(
        walk_forward_train_days=730,
        walk_forward_test_days=180,
        walk_forward_step_days=180,
        min_train_days=400,
        position_size_pct=0.10,
        fee_bps=1.0,
        slippage_bps=1.0,
    )

    model_id = f"lightgbm-bias-{asset.lower()}-1d-v0-{datetime.now().strftime('%Y%m%d')}"
    all_predictions: list = []

    def predict_fn(train_bars_bt, fold):
        # Adapter: BacktestBar → BarLike for our feature builder
        from ichor_ml.training.features import BarLike
        train_blike = [
            BarLike(
                bar_date=b.bar_date, asset=b.asset,
                open=b.open, high=b.high, low=b.low, close=b.close,
            ) for b in train_bars_bt
        ]
        try:
            model = train_lightgbm_bias(train_blike, n_estimators=100)
        except ValueError as e:
            print(f"  ! fold skipped — {e}")
            return {}

        # Predict for every test_date using features computed up-to-but-not-including
        # that test_date (so the leakage guard is satisfied).
        signals: dict = {}
        # Build feature rows over [start of train .. end of test]
        full_blike = [b for b in feature_bars if b.bar_date <= fold.test_end]
        rows = build_features_daily(full_blike)
        for r in rows:
            if not (fold.test_start <= r.bar_date <= fold.test_end):
                continue
            prob = model.predict_proba(r)
            direction = "long" if prob >= 0.5 else "short"
            fhash = _hash_features(r.features)
            signals[r.bar_date] = Signal(
                asset=asset,
                timestamp=r.bar_date,
                direction=direction,
                probability=prob if direction == "long" else 1 - prob,
                feature_snapshot_hash=fhash,
            )
            # Record raw + calibrated for predictions_audit
            raw = prob  # Already calibrated; keep one copy as raw too
            all_predictions.append((r.bar_date, prob, direction, raw, fhash))
        return signals

    print("[3/6] Running walk-forward backtest…")
    res = run_backtest(
        backtest_bars,
        predict_fn,
        cfg,
        fee_model=FlatFeeSlippageModel(fee_bps=cfg.fee_bps, slippage_bps=cfg.slippage_bps),
    )

    print(f"  ✓ {len(res.folds)} folds, {res.n_signals} signals, {res.n_trades} trades")
    print(f"  ✓ paper_only={res.paper_only}")

    print("[4/7] Persisting predictions to predictions_audit…")
    inserted = await _persist_predictions(all_predictions, model_id, asset)
    print(f"  ✓ {inserted} prediction rows persisted under model_id={model_id}")

    print("[5/7] Persisting backtest_run to backtest_runs…")
    run_id = await _persist_backtest_run(res, model_id, asset)
    print(f"  ✓ backtest_run row persisted (id={run_id})")

    print("[6/7] Computing baseline B&H…")
    bh_pct = _baseline_buy_and_hold(backtest_bars)
    print(f"  ✓ B&H total return over full series: {bh_pct:+.2f} %")

    print("[7/7] Summary")
    print("=" * 70)
    print(f"  Model: {model_id}")
    print(f"  Asset: {asset}")
    print(f"  Bars: {len(db_rows)}  Folds: {len(res.folds)}")
    print(f"  Signals: {res.n_signals}  Trades: {res.n_trades}")
    print(f"  Brier (lower better): {res.metrics['brier']:.4f}")
    print(f"  Hit rate: {res.metrics['hit_rate']:.2%}")
    print(f"  Total return strategy: {res.metrics['total_return_pct']:+.2f} %")
    print(f"  Total return B&H:      {bh_pct:+.2f} %")
    print(f"  Sharpe (annualized):   {res.metrics['sharpe_ann']:.3f}")
    print(f"  Max drawdown:          {res.metrics['max_drawdown']:.2%}")
    print(f"  PAPER ONLY: {res.paper_only}")
    print("=" * 70)
    print("HONEST DISCLAIMER: this single-asset, single-model, daily-bar backtest")
    print("on free-tier yfinance data is NOT alpha. It is a smoke run that proves")
    print("the entire pipeline closes loop end-to-end. Before any live discussion,")
    print("require: ensemble + cross-asset + 6-month paper-shadow + post-mortem.")
    return 0


if __name__ == "__main__":
    asset = sys.argv[1] if len(sys.argv) >= 2 else "EUR_USD"
    sys.exit(asyncio.run(main(asset)))
