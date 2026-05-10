"""CLI runner for the Brier-degradation monitor.

Wires session_card_audit.brier_contribution → trailing 7d vs prior 7d
delta → BIAS_BRIER_DEGRADATION alert.

Algorithm :
  1. Load session_card_audit rows where brier_contribution IS NOT NULL
     for the trailing 14 days, grouped by (asset, model_id).
  2. Split into "current week" (last 7d) and "prior week" (8-14d ago).
  3. Compute mean Brier in each window. Need ≥ 5 obs per window.
  4. Δ = current_mean - prior_mean. If Δ ≥ 0.10, fire
     BIAS_BRIER_DEGRADATION (catalog metric='brier_change_7d',
     threshold 0.10 above). Higher Brier = worse calibration.

Cadence : daily 04:00 Europe/Paris (after the Brier optimizer at
03:30 has digested the latest reconciler output).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select

from ..db import get_engine, get_sessionmaker
from ..models import SessionCardAudit

log = structlog.get_logger(__name__)

_MIN_OBS_PER_WEEK = 5


async def _load_briers(session, *, since: datetime):
    """Return rows of (asset, model_id, generated_at, brier_contribution)
    for the lookback window."""
    stmt = select(
        SessionCardAudit.asset,
        SessionCardAudit.model_id,
        SessionCardAudit.generated_at,
        SessionCardAudit.brier_contribution,
    ).where(
        SessionCardAudit.generated_at >= since,
        SessionCardAudit.brier_contribution.is_not(None),
    )
    return (await session.execute(stmt)).all()


async def run(*, persist: bool, lookback_days: int = 14) -> int:
    sm = get_sessionmaker()
    now = datetime.now(UTC)
    since = now - timedelta(days=lookback_days)
    midpoint = now - timedelta(days=lookback_days // 2)

    async with sm() as session:
        rows = await _load_briers(session, since=since)

    print(f"Brier drift · {len(rows)} brier-scored cards in last {lookback_days}d")

    if not rows:
        return 0

    # Group by (asset, model_id). Split each into prior + current week.
    grouped: dict[tuple[str, str], dict[str, list[float]]] = {}
    for asset, model_id, ts, brier in rows:
        key = (asset, model_id or "unknown")
        bucket = "current" if ts >= midpoint else "prior"
        grouped.setdefault(key, {"current": [], "prior": []})[bucket].append(float(brier))

    n_alerts = 0
    n_persisted = 0
    async with sm() as session:
        for (asset, model_id), buckets in grouped.items():
            cur = buckets["current"]
            pri = buckets["prior"]
            if len(cur) < _MIN_OBS_PER_WEEK or len(pri) < _MIN_OBS_PER_WEEK:
                continue
            cur_mean = sum(cur) / len(cur)
            pri_mean = sum(pri) / len(pri)
            delta = cur_mean - pri_mean
            print(
                f"  [{asset:10s} / {model_id:24s}] "
                f"prior={pri_mean:.4f} cur={cur_mean:.4f} Δ={delta:+.4f} "
                f"(n={len(pri)}/{len(cur)})"
            )

            if persist:
                from sqlalchemy.dialects.postgresql import insert as pg_insert

                from ..models import FredObservation

                # Persist the current Brier mean per (asset, model). One
                # value per (series_id, date) — fred UNIQUE-friendly.
                # series_id format : BRIER_{asset}_{short_model_id}.
                short_model = model_id.split("-")[0] if "-" in model_id else model_id
                sid = f"BRIER_{asset}_{short_model}"[:64]
                stmt = (
                    pg_insert(FredObservation)
                    .values(
                        id=__import__("uuid").uuid4(),
                        observation_date=now.date(),
                        created_at=now,
                        series_id=sid,
                        value=float(cur_mean),
                        fetched_at=now,
                    )
                    .on_conflict_do_update(
                        constraint="uq_fred_series_date",
                        set_={"value": cur_mean, "fetched_at": now},
                    )
                )
                await session.execute(stmt)
                n_persisted += 1

                # BIAS_BRIER_DEGRADATION — catalog metric='brier_change_7d',
                # threshold 0.10 above.
                from ..services.alerts_runner import check_metric

                hits = await check_metric(
                    session,
                    metric_name="brier_change_7d",
                    current_value=delta,
                    asset=asset,
                    extra_payload={
                        "model_id": model_id,
                        "prior_week_mean": pri_mean,
                        "current_week_mean": cur_mean,
                        "n_prior": len(pri),
                        "n_current": len(cur),
                    },
                )
                n_alerts += len(hits)
        if persist:
            await session.commit()

    if persist:
        print(f"Brier drift · upserted {n_persisted} rows, {n_alerts} alerts")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_brier_drift_check")
    parser.add_argument("--persist", action="store_true")
    parser.add_argument("--lookback-days", type=int, default=14)
    args = parser.parse_args(argv[1:])
    try:
        return asyncio.run(run(persist=args.persist, lookback_days=args.lookback_days))
    finally:
        if args.persist:
            asyncio.run(get_engine().dispose())


if __name__ == "__main__":
    sys.exit(main(sys.argv))
