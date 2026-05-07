"""CLI runner for DTW analogue matching against the historical library.

Wires fred_observations.VIXCLS (last 28 days) → DTW vs 8 archetypes
→ ANALOGUE_MATCH_HIGH alert when min distance ≤ 0.15.

Algorithm :
  1. Load last 28 days of VIXCLS observations from fred_observations
     (or VIX_LIVE if available — same metric, intraday vs daily).
  2. Z-score normalize the query pattern.
  3. For each archetype in the library, compute DTW distance.
  4. Persist top match's distance to fred_observations.DTW_DIST_MIN
     for dashboard tracking.
  5. If best distance ≤ 0.15 (catalog metric='dtw_dist' threshold
     0.15 below) → fire ANALOGUE_MATCH_HIGH with the matched
     archetype + its forward-return triple in the payload.

Cadence : daily 05:00 Europe/Paris (after the 4 ML self-monitors :
brier-drift 04:00, concept-drift 04:30, prediction-outlier 04:45).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select

from ..db import get_engine, get_sessionmaker
from ..models import FredObservation

log = structlog.get_logger(__name__)

_LOOKBACK_DAYS = 28
_MIN_OBS_FOR_MATCH = 20  # we need at least 20 of 28 days


async def _load_vix_pattern(session) -> list[float] | None:
    """Pull the last 28 days of VIX (close), padded if missing."""
    cutoff = (datetime.now(UTC) - timedelta(days=_LOOKBACK_DAYS + 5)).date()
    stmt = (
        select(FredObservation.observation_date, FredObservation.value)
        .where(
            FredObservation.series_id == "VIXCLS",
            FredObservation.observation_date >= cutoff,
            FredObservation.value.is_not(None),
        )
        .order_by(FredObservation.observation_date.asc())
    )
    rows = (await session.execute(stmt)).all()
    if len(rows) < _MIN_OBS_FOR_MATCH:
        return None
    # Take the last 28 (drop early days if we have more).
    values = [float(v) for _, v in rows[-_LOOKBACK_DAYS:]]
    if len(values) < _LOOKBACK_DAYS:
        # Pad-front with the first observed value (zero-impact in z-score).
        pad = values[0]
        values = [pad] * (_LOOKBACK_DAYS - len(values)) + values
    return values


async def run(*, persist: bool) -> int:
    sm = get_sessionmaker()

    async with sm() as session:
        pattern = await _load_vix_pattern(session)

    if pattern is None:
        print(
            f"DTW analogue · skipped — insufficient VIXCLS history "
            f"(< {_MIN_OBS_FOR_MATCH} days)"
        )
        return 0

    # Lazy import — the matcher pulls dtaidistance which is heavy.
    import numpy as np
    from ichor_ml.analogues.dtw import DTWAnalogueMatcher

    from ..services.analogue_library import build_archetype_library

    library = build_archetype_library()
    matcher = DTWAnalogueMatcher(library)
    matches = matcher.find_top_k(np.array(pattern, dtype=np.float64), k=3)

    print(f"DTW analogue · {len(matches)} top matches over 28d VIX window :")
    for m in matches:
        print(
            f"  [{m.library_event_id:24s}] dist={m.distance:.4f} "
            f"fwd_d1={m.forward_returns[0]:+.2%} d5={m.forward_returns[1]:+.2%} "
            f"d22={m.forward_returns[2]:+.2%}"
        )

    if persist and matches:
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        sm = get_sessionmaker()
        async with sm() as session:
            now = datetime.now(UTC)
            best = matches[0]
            stmt = pg_insert(FredObservation).values(
                id=__import__("uuid").uuid4(),
                observation_date=now.date(),
                created_at=now,
                series_id="DTW_DIST_MIN",
                value=float(best.distance),
                fetched_at=now,
            ).on_conflict_do_update(
                constraint="uq_fred_series_date",
                set_={"value": float(best.distance), "fetched_at": now},
            )
            await session.execute(stmt)

            # ANALOGUE_MATCH_HIGH — catalog metric='dtw_dist' threshold
            # 0.15 below. Lower distance = closer match = stronger signal.
            from ..services.alerts_runner import check_metric

            hits = await check_metric(
                session,
                metric_name="dtw_dist",
                current_value=float(best.distance),
                asset=None,
                extra_payload={
                    "match_event": best.library_event_id,
                    "distance": best.distance,
                    "forward_d1": best.forward_returns[0],
                    "forward_d5": best.forward_returns[1],
                    "forward_d22": best.forward_returns[2],
                    "n_pattern_obs": len(pattern),
                },
            )
            await session.commit()
            print(
                f"DTW analogue · upserted DTW_DIST_MIN={best.distance:.4f}, "
                f"{len(hits)} alerts"
            )
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_dtw_analogue")
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args(argv[1:])
    try:
        return asyncio.run(run(persist=args.persist))
    finally:
        if args.persist:
            asyncio.run(get_engine().dispose())


if __name__ == "__main__":
    sys.exit(main(sys.argv))
