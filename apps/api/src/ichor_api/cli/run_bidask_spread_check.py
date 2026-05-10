"""CLI runner for FX bid-ask spread z-score monitor.

Wires fx_ticks (live, from ichor-fx-stream) → spread compute →
fred_observations.BA_SPREAD_{asset} + LIQUIDITY_BIDASK_WIDEN alert.

Algorithm :
  1. For each tracked FX asset, load last 4h of fx_ticks
  2. Compute spread = ask - bid in pips per tick
  3. Latest 5-min mean spread vs 4h baseline mean+std → z-score
  4. Catalog metric_name='ba_spread_z' threshold 2.5 above
  5. crisis_mode=True for this code (composite Crisis Mode trigger)

Cadence : every 10 min (faster than VPIN ; spread widening is the
most actionable real-time liquidity stress signal).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select

from ..db import get_engine, get_sessionmaker
from ..models import FxTick

log = structlog.get_logger(__name__)

_BASELINE_HOURS = 4
_RECENT_MINUTES = 5
# Pip multipliers : JPY pairs use 0.01 increment, others use 0.0001.
_PIP_MULTIPLIER = {
    "EURUSD": 1e4,
    "GBPUSD": 1e4,
    "AUDUSD": 1e4,
    "USDCAD": 1e4,
    "USDJPY": 1e2,
    "EURJPY": 1e2,
    "GBPJPY": 1e2,
    "XAUUSD": 1e1,  # Gold quoted in $/oz, 1 pip = $0.10
}


def _spread_pips(asset: str, bid: float, ask: float) -> float | None:
    """Return spread in pips, or None on bad inputs."""
    if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
        return None
    multiplier = _PIP_MULTIPLIER.get(asset, 1e4)
    return float(ask - bid) * multiplier


async def _process_asset(session, *, asset: str, baseline_start: datetime, recent_start: datetime):
    """Returns (recent_mean, baseline_mean, baseline_std, z, n_recent, n_baseline) or None."""
    # Pull spreads for the entire baseline window in a single round-trip.
    stmt = (
        select(FxTick.ts, FxTick.bid, FxTick.ask)
        .where(FxTick.asset == asset, FxTick.ts >= baseline_start)
        .order_by(FxTick.ts.asc())
    )
    rows = (await session.execute(stmt)).all()
    if len(rows) < 50:  # need a meaningful baseline
        return None

    baseline_spreads: list[float] = []
    recent_spreads: list[float] = []
    for ts, bid, ask in rows:
        spread = _spread_pips(asset, float(bid) if bid else 0.0, float(ask) if ask else 0.0)
        if spread is None or spread <= 0:
            continue
        baseline_spreads.append(spread)
        if ts >= recent_start:
            recent_spreads.append(spread)

    if not baseline_spreads or not recent_spreads:
        return None

    bmean = sum(baseline_spreads) / len(baseline_spreads)
    bvar = sum((s - bmean) ** 2 for s in baseline_spreads) / max(1, len(baseline_spreads) - 1)
    bstd = bvar**0.5
    rmean = sum(recent_spreads) / len(recent_spreads)
    z = 0.0
    if bstd > 0:
        z = (rmean - bmean) / bstd
    return rmean, bmean, bstd, z, len(recent_spreads), len(baseline_spreads)


async def run(*, persist: bool) -> int:
    sm = get_sessionmaker()
    now = datetime.now(UTC)
    baseline_start = now - timedelta(hours=_BASELINE_HOURS)
    recent_start = now - timedelta(minutes=_RECENT_MINUTES)

    async with sm() as session:
        distinct_stmt = select(FxTick.asset).where(FxTick.ts >= baseline_start).distinct()
        assets = [r[0] for r in (await session.execute(distinct_stmt)).all()]

    print(f"Bid-ask spread · {len(assets)} assets active in last {_BASELINE_HOURS}h")

    if not assets:
        return 0

    n_persisted = 0
    n_alerts = 0
    async with sm() as session:
        for asset in assets:
            outcome = await _process_asset(
                session, asset=asset, baseline_start=baseline_start, recent_start=recent_start
            )
            if outcome is None:
                continue
            rmean, bmean, bstd, z, n_recent, n_baseline = outcome
            print(
                f"  [{asset:8s}] recent_mean={rmean:.3f}p baseline={bmean:.3f}±{bstd:.3f}p "
                f"z={z:+.2f} ({n_recent}/{n_baseline} ticks)"
            )

            if persist:
                from sqlalchemy.dialects.postgresql import insert as pg_insert

                from ..models import FredObservation

                # Persist recent mean spread + the z-score for the dashboard.
                for sid, val in (
                    (f"BA_SPREAD_{asset}_PIPS"[:64], rmean),
                    (f"BA_SPREAD_{asset}_Z"[:64], z),
                ):
                    stmt = (
                        pg_insert(FredObservation)
                        .values(
                            id=__import__("uuid").uuid4(),
                            observation_date=now.date(),
                            created_at=now,
                            series_id=sid,
                            value=float(val),
                            fetched_at=now,
                        )
                        .on_conflict_do_update(
                            constraint="uq_fred_series_date",
                            set_={"value": val, "fetched_at": now},
                        )
                    )
                    await session.execute(stmt)
                    n_persisted += 1

                # LIQUIDITY_BIDASK_WIDEN — catalog metric='ba_spread_z',
                # threshold 2.5 above. crisis_mode=True. Asset-scoped.
                from ..services.alerts_runner import check_metric

                hits = await check_metric(
                    session,
                    metric_name="ba_spread_z",
                    current_value=z,
                    asset=asset,
                    extra_payload={
                        "recent_mean_pips": rmean,
                        "baseline_mean_pips": bmean,
                        "baseline_std_pips": bstd,
                        "n_recent_ticks": n_recent,
                        "n_baseline_ticks": n_baseline,
                    },
                )
                n_alerts += len(hits)
        if persist:
            await session.commit()

    if persist:
        print(f"Bid-ask spread · upserted {n_persisted} rows, {n_alerts} alerts triggered")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_bidask_spread_check")
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args(argv[1:])
    try:
        return asyncio.run(run(persist=args.persist))
    finally:
        if args.persist:
            asyncio.run(get_engine().dispose())


if __name__ == "__main__":
    sys.exit(main(sys.argv))
