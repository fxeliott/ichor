"""CLI runner for HMM regime detection per asset.

Wires polygon_intraday_bars (1-min OHLCV) →
packages/ml/regime/hmm.HMMRegimeDetector → fred_observations
HMM_REGIME_{asset} (state 0/1/2) + REGIME_CHANGE_HMM alert when
the latest state differs from the previous run.

Algorithm :
  1. For each asset, load 60d of 1-min bars
  2. Aggregate to daily : log_return = log(close_d / close_{d-1}),
     realized_vol_5d = std of last 5 daily returns
  3. Fit HMM with 2 features (skip ADX to avoid feature-engineering
     drift ; the audit says F=3 is "typically" but the API accepts any F)
  4. Predict states. Take the latest state.
  5. Compare to the prior persisted HMM_REGIME_{asset} value. If the
     state changed, fire REGIME_CHANGE_HMM (catalog metric_name=
     'hmm_state_change', threshold 1 above).

Cadence : daily 23:45 Europe/Paris (after HAR-RV at 23:30 — both
consume the day's bars, but they don't share state).

Usage:
    python -m ichor_api.cli.run_hmm_regime          # dry-run
    python -m ichor_api.cli.run_hmm_regime --persist
"""

from __future__ import annotations

import argparse
import asyncio
import math
import sys
from datetime import UTC, date, datetime, timedelta

import structlog
from sqlalchemy import desc, select

from ..db import get_engine, get_sessionmaker
from ..models import FredObservation, PolygonIntradayBar

log = structlog.get_logger(__name__)

# Same Phase 1 universe as run_har_rv.
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

_LOOKBACK_DAYS = 60
_MIN_DAYS_FOR_FIT = 30
# State labels per hmm.py docstring : 0=low-vol trending,
# 1=high-vol trending, 2=mean-reverting noise.
_STATE_LABELS = {0: "low_vol_trend", 1: "high_vol_trend", 2: "mean_revert"}


async def _load_daily_closes(session, *, asset: str, since: datetime):
    """Aggregate 1-min bars → list of (date, daily_close).

    We use the last bar of each UTC day as the daily close.
    """
    stmt = (
        select(PolygonIntradayBar.bar_ts, PolygonIntradayBar.close)
        .where(
            PolygonIntradayBar.asset == asset,
            PolygonIntradayBar.bar_ts >= since,
        )
        .order_by(PolygonIntradayBar.bar_ts.asc())
    )
    rows = (await session.execute(stmt)).all()
    if not rows:
        return []

    by_day: dict[date, float] = {}
    for ts, close in rows:
        if close is None or close <= 0:
            continue
        d = ts.astimezone(UTC).date() if ts.tzinfo else ts.date()
        by_day[d] = float(close)  # last write wins → last bar of day

    return sorted(by_day.items())


async def _previous_state(session, *, asset: str) -> int | None:
    stmt = (
        select(FredObservation.value)
        .where(FredObservation.series_id == f"HMM_REGIME_{asset}"[:64])
        .order_by(desc(FredObservation.observation_date))
        .limit(1)
    )
    val = (await session.execute(stmt)).scalar_one_or_none()
    return int(val) if val is not None else None


async def _process_asset(session, *, asset: str, since: datetime):
    """Returns (latest_state, prev_state, n_obs) or None if not enough data."""
    daily = await _load_daily_closes(session, asset=asset, since=since)
    if len(daily) < _MIN_DAYS_FOR_FIT + 1:  # +1 because we lose 1 to the diff
        log.info("hmm.skipped_insufficient_days", asset=asset, n=len(daily))
        return None

    import numpy as np
    from ichor_ml.regime.hmm import HMMRegimeDetector

    closes = [c for _, c in daily]
    # log returns
    log_rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    if len(log_rets) < _MIN_DAYS_FOR_FIT:
        return None

    # realized_vol_5d : rolling std of last 5 returns. For the first
    # 4 we just repeat the first available std.
    rv5 = []
    for i in range(len(log_rets)):
        window = log_rets[max(0, i - 4) : i + 1]
        if len(window) >= 2:
            mean = sum(window) / len(window)
            var = sum((x - mean) ** 2 for x in window) / max(1, len(window) - 1)
            rv5.append(var**0.5)
        else:
            rv5.append(abs(window[0]))

    features = np.array(list(zip(log_rets, rv5, strict=False)), dtype=np.float64)
    if features.shape[0] < _MIN_DAYS_FOR_FIT or features.shape[1] != 2:
        return None

    try:
        det = HMMRegimeDetector(n_states=3, n_iter=200)
        det.fit(features)
        result = det.predict(features)
    except Exception as exc:
        log.warning("hmm.fit_failed", asset=asset, error=str(exc)[:200])
        return None

    latest_state = int(result.states[-1])
    prev_state = await _previous_state(session, asset=asset)
    return latest_state, prev_state, int(features.shape[0])


async def run(*, persist: bool, lookback_days: int = _LOOKBACK_DAYS) -> int:
    sm = get_sessionmaker()
    since = datetime.now(UTC) - timedelta(days=lookback_days)

    print(f"HMM regime · scanning {len(WATCHED_ASSETS)} assets, lookback {lookback_days}d")

    n_alerts = 0
    n_persisted = 0
    async with sm() as session:
        for asset in WATCHED_ASSETS:
            outcome = await _process_asset(session, asset=asset, since=since)
            if outcome is None:
                continue
            latest_state, prev_state, n_obs = outcome
            label = _STATE_LABELS.get(latest_state, str(latest_state))
            change_indicator = (
                "(no change)"
                if prev_state == latest_state
                else f"(was state={prev_state} '{_STATE_LABELS.get(prev_state or -1, '?')}')"
            )
            print(
                f"  [{asset:10s}] state={latest_state} '{label}' n_obs={n_obs} {change_indicator}"
            )

            if persist:
                from sqlalchemy.dialects.postgresql import insert as pg_insert

                now = datetime.now(UTC)
                stmt = (
                    pg_insert(FredObservation)
                    .values(
                        id=__import__("uuid").uuid4(),
                        observation_date=now.date(),
                        created_at=now,
                        series_id=f"HMM_REGIME_{asset}"[:64],
                        value=float(latest_state),
                        fetched_at=now,
                    )
                    .on_conflict_do_update(
                        constraint="uq_fred_series_date",
                        set_={"value": float(latest_state), "fetched_at": now},
                    )
                )
                await session.execute(stmt)
                n_persisted += 1

                # REGIME_CHANGE_HMM : catalog metric='hmm_state_change',
                # threshold 1 above. Asset-scoped. Fires only on transition.
                if prev_state is not None and prev_state != latest_state:
                    from ..services.alerts_runner import check_metric

                    hits = await check_metric(
                        session,
                        metric_name="hmm_state_change",
                        # Use abs(diff) ≥ 1 → triggers `above` direction.
                        current_value=float(abs(latest_state - prev_state)),
                        asset=asset,
                        extra_payload={
                            "prev_state": prev_state,
                            "new_state": latest_state,
                            "prev_label": _STATE_LABELS.get(prev_state, "?"),
                            "new_label": label,
                        },
                    )
                    n_alerts += len(hits)
        if persist:
            await session.commit()

    if persist:
        print(f"HMM regime · upserted {n_persisted} states, {n_alerts} regime-change alerts")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_hmm_regime")
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
