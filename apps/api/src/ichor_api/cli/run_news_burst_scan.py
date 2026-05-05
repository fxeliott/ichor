"""News-negative-burst scanner — fires NEWS_NEGATIVE_BURST alert.

Wires news_items.tone_label/tone_score (populated asynchronously by
the FinBERT-tone worker — services/news_tone_worker if present, else
NULL — see news_item.py:42-44) into the alert catalog.

Algorithm :
  1. Window = last 5 minutes
  2. Count headlines with tone_label='negative' AND tone_score < -0.5
     fetched in the window
  3. Compare to baseline = mean negative-burst count over trailing
     24h (in 5-min slices) + 2 × std
  4. Fire NEWS_NEGATIVE_BURST (catalog metric_name='news_neg_5min',
     threshold 0.7 above) if window_z ≥ 0.7 AND raw_count ≥ 5

This is a contrarian-friendly burst detector : a pure count
threshold misses news-light periods where 2 negative headlines in
5 min is already extreme. The 24h baseline z-score normalizes.

Cadence : every 5 min via systemd timer.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy import text as sa_text

from ..db import get_engine, get_sessionmaker
from ..models import NewsItem

log = structlog.get_logger(__name__)

_BURST_WINDOW_MIN = 5
_BASELINE_HOURS = 24
_NEG_TONE_FLOOR = -0.5
_MIN_RAW_COUNT = 5  # absolute floor — avoid alerting on 1-2 outliers


async def _count_negatives_in_window(
    session, *, start: datetime, end: datetime
) -> int:
    stmt = (
        select(sa_text("count(*)"))
        .select_from(NewsItem)
        .where(
            NewsItem.fetched_at >= start,
            NewsItem.fetched_at < end,
            NewsItem.tone_label == "negative",
            NewsItem.tone_score < _NEG_TONE_FLOOR,
        )
    )
    return int((await session.execute(stmt)).scalar_one_or_none() or 0)


async def _baseline_stats(
    session, *, now: datetime, slice_minutes: int = _BURST_WINDOW_MIN
) -> tuple[float, float, int]:
    """Compute mean + std of negative-news counts per `slice_minutes`
    over the trailing _BASELINE_HOURS.

    Implementation : bucket each event by floor((event - start) / slice)
    in a single GROUP BY pass, then back-fill empty buckets in Python.
    Faster than generate_series + correlated subquery, and avoids the
    make_interval(mins => :slc) parameter-typing quirk that broke the
    initial smoke run.
    """
    baseline_start = now - timedelta(hours=_BASELINE_HOURS)
    slice_seconds = slice_minutes * 60
    sql = sa_text(
        """
        SELECT bucket, count(*)::bigint AS n
        FROM (
          SELECT floor(extract(epoch from fetched_at - :bs) / :secs)::int AS bucket
          FROM news_items
          WHERE tone_label = 'negative'
            AND tone_score < :floor
            AND fetched_at >= :bs
            AND fetched_at < :now
        ) sub
        GROUP BY bucket
        ORDER BY bucket
        """
    )
    rows = (
        await session.execute(
            sql,
            {
                "bs": baseline_start,
                "now": now,
                "secs": slice_seconds,
                "floor": _NEG_TONE_FLOOR,
            },
        )
    ).all()
    total_slices = max(1, (_BASELINE_HOURS * 60) // slice_minutes)
    counts: list[int] = [0] * total_slices
    for bucket, n in rows:
        if 0 <= int(bucket) < total_slices:
            counts[int(bucket)] = int(n)

    mean = sum(counts) / len(counts)
    var = sum((c - mean) ** 2 for c in counts) / max(1, len(counts) - 1)
    std = var**0.5
    return mean, std, len(counts)


async def run(*, persist: bool) -> int:
    sm = get_sessionmaker()
    now = datetime.now(UTC)
    window_start = now - timedelta(minutes=_BURST_WINDOW_MIN)

    async with sm() as session:
        cur_count = await _count_negatives_in_window(
            session, start=window_start, end=now
        )
        mean, std, n_slices = await _baseline_stats(session, now=now)

    # Burst score : (cur - mean) / std, normalized to roughly [0, 1] by
    # mapping a 3-sigma move to z=1. This puts the catalog threshold
    # 0.7 ≈ 2.1-sigma which is the conventional burst threshold.
    z = 0.0
    if std > 0:
        z = (cur_count - mean) / std
    burst_score = max(0.0, min(1.0, z / 3.0))

    print(
        f"News burst · cur_5min={cur_count} baseline_mean={mean:.2f} "
        f"std={std:.2f} z={z:+.2f} score={burst_score:.2f} "
        f"({n_slices} baseline slices)"
    )

    if persist and cur_count >= _MIN_RAW_COUNT:
        async with sm() as session:
            from ..services.alerts_runner import check_metric

            hits = await check_metric(
                session,
                metric_name="news_neg_5min",
                current_value=burst_score,
                asset=None,
                extra_payload={
                    "current_count": cur_count,
                    "baseline_mean": mean,
                    "baseline_std": std,
                    "z_score": z,
                    "window_minutes": _BURST_WINDOW_MIN,
                },
            )
            if hits:
                await session.commit()
            print(f"News burst · {len(hits)} alerts triggered")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_news_burst_scan")
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args(argv[1:])
    try:
        return asyncio.run(run(persist=args.persist))
    finally:
        if args.persist:
            asyncio.run(get_engine().dispose())


if __name__ == "__main__":
    sys.exit(main(sys.argv))
