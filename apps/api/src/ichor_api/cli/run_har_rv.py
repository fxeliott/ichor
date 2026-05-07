"""CLI runner for daily HAR-RV (realized volatility) forecast.

Wires polygon_intraday_bars (1-min OHLCV) → packages/ml/vol/har_rv
→ fred_observations.HAR_RV_{asset}_H1 + HAR_RV_FORECAST_SPIKE alert.

Algorithm per Corsi 2009 :
  1. For each asset, load 60 trading days of 1-min bars
  2. Compute daily realized volatility = sum of squared 1-min log returns
     per UTC date (Andersen-Bollerslev convention)
  3. Fit HAR-RV regression on the daily RV series (≥ 30 days required)
  4. Predict next_day_rv (h=1), next_week_rv (h=5), next_month_rv (h=22)
  5. Compare next_day_rv to the latest realized RV
  6. If forecast change ≥ 30 % above latest, fire HAR_RV_FORECAST_SPIKE
     alert (catalog metric_name='har_rv_h1_chg', threshold 30 above)

Cadence : daily 23:30 Europe/Paris (after NY close so we have a
full trading day's bars).

Usage:
    python -m ichor_api.cli.run_har_rv          # dry-run
    python -m ichor_api.cli.run_har_rv --persist
"""

from __future__ import annotations

import argparse
import asyncio
import math
import sys
from datetime import UTC, date, datetime, timedelta

import structlog
from sqlalchemy import select

from ..db import get_engine, get_sessionmaker
from ..models import PolygonIntradayBar

log = structlog.get_logger(__name__)

# Phase 1 universe (8 assets per ADR-017).
WATCHED_ASSETS: tuple[str, ...] = (
    "EUR_USD",
    "GBP_USD",
    "USD_JPY",
    "AUD_USD",
    "USD_CAD",
    "XAU_USD",
    "NAS100_USD",
    "SPX500_USD",
)

# Number of trading days of bars we pull. HAR-RV needs ≥ 30 ; 60 gives
# a healthy in-sample to the regression and survives weekends/holidays.
_LOOKBACK_DAYS = 60

# Minimum daily RV observations needed for the HAR-RV regression to fit.
_MIN_DAYS_FOR_FIT = 30


async def _load_bars_for_asset(session, *, asset: str, since: datetime):
    """Pull 1-min bars for asset since `since`, ordered chronologically."""
    stmt = (
        select(PolygonIntradayBar.bar_ts, PolygonIntradayBar.close)
        .where(
            PolygonIntradayBar.asset == asset,
            PolygonIntradayBar.bar_ts >= since,
        )
        .order_by(PolygonIntradayBar.bar_ts.asc())
    )
    return (await session.execute(stmt)).all()


def _daily_rv_from_bars(rows) -> list[tuple[date, float]]:
    """Aggregate (bar_ts, close) → list of (date, realized_vol).

    RV_d = sqrt(sum_{t in d} (log(close_t / close_{t-1}))^2).
    """
    if len(rows) < 2:
        return []

    daily: dict[date, float] = {}
    last_close: float | None = None

    for ts, close in rows:
        if close is None or close <= 0:
            continue
        d = ts.astimezone(UTC).date() if ts.tzinfo else ts.date()
        if last_close is not None and last_close > 0:
            r = math.log(float(close) / last_close)
            daily[d] = daily.get(d, 0.0) + r * r
        last_close = float(close)

    # Take square root for RV (annualized factor not needed — we work
    # with raw realized variance throughout, the HAR regression is
    # scale-invariant on its forecasts vs latest).
    return [(d, math.sqrt(v)) for d, v in sorted(daily.items()) if v > 0]


async def _process_asset(session, *, asset: str, since: datetime):
    """Returns (latest_rv, forecast_h1, pct_change) or None."""
    rows = await _load_bars_for_asset(session, asset=asset, since=since)
    daily = _daily_rv_from_bars(rows)
    if len(daily) < _MIN_DAYS_FOR_FIT:
        log.info("har_rv.skipped_insufficient_days", asset=asset, n=len(daily))
        return None

    import pandas as pd
    from ichor_ml.vol.har_rv import HARRVModel

    dates, vals = zip(*daily, strict=False)
    series = pd.Series(list(vals), index=pd.DatetimeIndex(list(dates)))

    try:
        model = HARRVModel()
        model.fit(series)
        pred = model.predict()
    except Exception as exc:
        log.warning("har_rv.fit_failed", asset=asset, error=str(exc)[:200])
        return None

    latest_rv = float(series.iloc[-1])
    forecast_h1 = float(pred.next_day_rv)
    if latest_rv <= 0:
        return forecast_h1, latest_rv, 0.0
    pct_change = (forecast_h1 - latest_rv) / latest_rv * 100.0
    return latest_rv, forecast_h1, pct_change


async def run(*, persist: bool, lookback_days: int = _LOOKBACK_DAYS) -> int:
    sm = get_sessionmaker()
    since = datetime.now(UTC) - timedelta(days=lookback_days)

    print(f"HAR-RV forecast · running on {len(WATCHED_ASSETS)} assets, lookback {lookback_days}d")

    n_persisted = 0
    n_alerts = 0
    async with sm() as session:
        for asset in WATCHED_ASSETS:
            outcome = await _process_asset(session, asset=asset, since=since)
            if outcome is None:
                continue
            latest_rv, forecast_h1, pct_change = outcome
            print(
                f"  [{asset:10s}] latest_rv={latest_rv:.5f} forecast_h1={forecast_h1:.5f} "
                f"chg={pct_change:+.1f}%"
            )

            if persist:
                from sqlalchemy.dialects.postgresql import insert as pg_insert

                from ..models import FredObservation

                now = datetime.now(UTC)
                for sid, val in (
                    (f"HAR_RV_{asset}_H1"[:64], forecast_h1),
                    (f"HAR_RV_{asset}_LATEST"[:64], latest_rv),
                ):
                    stmt = pg_insert(FredObservation).values(
                        id=__import__("uuid").uuid4(),
                        observation_date=now.date(),
                        created_at=now,
                        series_id=sid,
                        value=float(val),
                        fetched_at=now,
                    ).on_conflict_do_update(
                        constraint="uq_fred_series_date",
                        set_={"value": val, "fetched_at": now},
                    )
                    await session.execute(stmt)
                    n_persisted += 1

                # HAR_RV_FORECAST_SPIKE — catalog metric_name='har_rv_h1_chg',
                # threshold 30 above. Asset-scoped.
                from ..services.alerts_runner import check_metric

                hits = await check_metric(
                    session,
                    metric_name="har_rv_h1_chg",
                    current_value=pct_change,
                    asset=asset,
                    extra_payload={
                        "latest_rv": latest_rv,
                        "forecast_h1": forecast_h1,
                    },
                )
                n_alerts += len(hits)
        if persist:
            await session.commit()

    if persist:
        print(f"HAR-RV · upserted {n_persisted} forecast rows, {n_alerts} alerts")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_har_rv")
    parser.add_argument("--persist", action="store_true")
    parser.add_argument("--lookback-days", type=int, default=_LOOKBACK_DAYS)
    args = parser.parse_args(argv[1:])
    try:
        return asyncio.run(run(persist=args.persist, lookback_days=args.lookback_days))
    finally:
        if args.persist:
            asyncio.run(get_engine().dispose())


if __name__ == "__main__":
    sys.exit(main(sys.argv))
