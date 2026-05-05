"""CLI runner for FX VPIN (flow toxicity) computation.

Wires the previously-DORMANT pipeline :
  fx_ticks (live, ingested by ichor-fx-stream)
    → packages/ml/microstructure/vpin.compute_vpin_from_fx_quotes
    → fred_observations.VPIN_FX_{asset}
    → check_metric("vpin_p99", value) → VPIN_TOXICITY_HIGH alert

VPIN per Easley/Lopez de Prado/O'Hara 2012 — tick-count bucketing
(FX has no central trade tape, so quote-updates = synthetic volume).
Threshold from catalog : vpin_p99 ≥ 0.35 = warning.

Cadence : every 30 min via systemd timer. Each run computes VPIN
on the trailing 4h of fx_ticks per asset.

Usage:
    python -m ichor_api.cli.run_vpin_compute            # dry-run
    python -m ichor_api.cli.run_vpin_compute --persist
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

# Window over which VPIN is computed. Shorter = more reactive ; longer
# = more stable. 4h matches the Couche-2 News-NLP cadence so the
# brain sees a fresh microstructure signal every cycle.
_LOOKBACK_HOURS = 4

# Minimum tick count to attempt a VPIN compute. Below this, the
# bucket sizing is meaningless and the result is noise.
_MIN_TICKS = 600  # ~ 3 buckets at 200 ticks/bucket


async def _load_fx_ticks(session, *, asset: str, since: datetime):
    """Pull (timestamp, bid, ask) rows for one asset since `since`."""
    stmt = (
        select(FxTick.ts, FxTick.bid, FxTick.ask)
        .where(FxTick.asset == asset, FxTick.ts >= since)
        .order_by(FxTick.ts.asc())
    )
    rows = (await session.execute(stmt)).all()
    return rows


async def _compute_for_asset(session, *, asset: str, since: datetime):
    """Returns (latest_vpin, p99_vpin, n_buckets) or None if not enough data."""
    rows = await _load_fx_ticks(session, asset=asset, since=since)
    if len(rows) < _MIN_TICKS:
        log.info(
            "vpin.skipped_insufficient_ticks", asset=asset, n=len(rows), needed=_MIN_TICKS
        )
        return None

    # Lazy imports — pandas + scipy are heavy ; CLI startup stays fast
    # for the dry-run path.
    import pandas as pd
    from ichor_ml.microstructure.vpin import compute_vpin_from_fx_quotes

    df = pd.DataFrame(rows, columns=["timestamp", "bid", "ask"])
    try:
        result = compute_vpin_from_fx_quotes(df, bucket_n_ticks=200, window_n_buckets=50)
    except Exception as exc:
        log.warning("vpin.compute_failed", asset=asset, error=str(exc)[:200])
        return None

    if result.vpin is None or len(result.vpin) == 0:
        return None

    latest = float(result.vpin.iloc[-1])
    p99 = float(result.vpin.quantile(0.99))
    return latest, p99, int(len(result.vpin))


async def run(*, persist: bool, lookback_hours: int = _LOOKBACK_HOURS) -> int:
    sm = get_sessionmaker()
    since = datetime.now(UTC) - timedelta(hours=lookback_hours)

    # Load distinct assets that have ticks in window — saves us hard-coding
    # the symbol list and keeps in sync with whatever ichor-fx-stream
    # is subscribed to.
    async with sm() as session:
        distinct_stmt = (
            select(FxTick.asset)
            .where(FxTick.ts >= since)
            .distinct()
        )
        assets = [r[0] for r in (await session.execute(distinct_stmt)).all()]

    print(f"VPIN compute · {len(assets)} assets active in last {lookback_hours}h")

    if not assets:
        return 0

    n_persisted = 0
    n_alerts = 0
    async with sm() as session:
        for asset in assets:
            outcome = await _compute_for_asset(session, asset=asset, since=since)
            if outcome is None:
                continue
            latest, p99, n_buckets = outcome
            print(
                f"  [{asset:8s}] vpin={latest:.3f} p99={p99:.3f} "
                f"({n_buckets} buckets)"
            )

            if persist:
                from datetime import UTC as _UTC
                from sqlalchemy.dialects.postgresql import insert as pg_insert

                from ..models import FredObservation

                now = datetime.now(_UTC)
                today = now.date()
                # Persist both the latest VPIN and the p99. ON CONFLICT
                # DO UPDATE so multiple runs per day refresh in place.
                for sid, val in (
                    (f"VPIN_FX_{asset}"[:64], latest),
                    (f"VPIN_FX_{asset}_P99"[:64], p99),
                ):
                    stmt = pg_insert(FredObservation).values(
                        id=__import__("uuid").uuid4(),
                        observation_date=today,
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

                # Trigger VPIN_TOXICITY_HIGH (catalog metric_name='vpin_p99'
                # threshold 0.35 above) on the rolling p99.
                from ..services.alerts_runner import check_metric

                hits = await check_metric(
                    session,
                    metric_name="vpin_p99",
                    current_value=p99,
                    asset=asset,
                    extra_payload={"latest": latest, "n_buckets": n_buckets},
                )
                n_alerts += len(hits)
        if persist:
            await session.commit()

    if persist:
        print(
            f"VPIN compute · upserted {n_persisted} rows, {n_alerts} alerts triggered"
        )

    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_vpin_compute")
    parser.add_argument("--persist", action="store_true")
    parser.add_argument("--lookback-hours", type=int, default=_LOOKBACK_HOURS)
    args = parser.parse_args(argv[1:])
    try:
        return asyncio.run(run(persist=args.persist, lookback_hours=args.lookback_hours))
    finally:
        if args.persist:
            asyncio.run(get_engine().dispose())


if __name__ == "__main__":
    sys.exit(main(sys.argv))
