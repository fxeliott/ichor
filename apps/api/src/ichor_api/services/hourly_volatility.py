"""Hour-of-day realized-vol heatmap — "when does this asset move?".

For session-momentum trading, knowing the median realized vol per hour
of day matters more than the spot value : the same setup that works at
14:00 UTC (NY open) is dead at 23:00 UTC. This service computes the
median + p75 absolute log-return per hour-of-day over the last 30 days
of polygon_intraday bars.

Output : a 24-row table per asset, with median and 75th-percentile of
|log-return| in basis points (1bp = 0.01%).

Pure-stdlib percentile + median ; no numpy / pandas.

VISION_2026 — closes the "when's the best time to trade this?" gap.
The trader's intuition that "EUR/USD is dead before London" is now
quantified per asset.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import PolygonIntradayBar


@dataclass(frozen=True)
class HourlyVolEntry:
    hour_utc: int
    """0-23."""
    median_bp: float
    p75_bp: float
    n_samples: int


@dataclass(frozen=True)
class HourlyVolReport:
    asset: str
    window_days: int
    entries: list[HourlyVolEntry]
    """Always 24 entries (filled with zeros if no data)."""
    best_hour_utc: int | None
    """Hour with highest median |return|."""
    worst_hour_utc: int | None
    """Hour with lowest median |return|."""
    london_session_avg_bp: float | None
    """Average median bp for hours 07-15 UTC (London + NY overlap)."""
    asian_session_avg_bp: float | None
    """Average median bp for hours 00-06 UTC."""
    generated_at: datetime


def _percentile(sorted_xs: list[float], p: float) -> float:
    """Linear-interp percentile. p in [0, 100]."""
    if not sorted_xs:
        return 0.0
    if len(sorted_xs) == 1:
        return sorted_xs[0]
    k = (len(sorted_xs) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_xs[int(k)]
    d0 = sorted_xs[int(f)] * (c - k)
    d1 = sorted_xs[int(c)] * (k - f)
    return d0 + d1


async def assess_hourly_volatility(
    session: AsyncSession, asset: str, *, window_days: int = 30
) -> HourlyVolReport:
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    rows = list(
        (
            await session.execute(
                select(PolygonIntradayBar)
                .where(
                    PolygonIntradayBar.asset == asset,
                    PolygonIntradayBar.bar_ts >= cutoff,
                )
                .order_by(PolygonIntradayBar.bar_ts.asc())
            )
        ).scalars().all()
    )

    # Group |log-return| samples by hour-of-day
    by_hour: dict[int, list[float]] = {h: [] for h in range(24)}
    prev_close: float | None = None
    for r in rows:
        c = float(r.close)
        if prev_close is not None and prev_close > 0 and c > 0:
            try:
                ret_bp = abs(math.log(c / prev_close)) * 10_000  # bp
                by_hour[r.bar_ts.hour].append(ret_bp)
            except ValueError:
                pass
        prev_close = c

    entries: list[HourlyVolEntry] = []
    for h in range(24):
        samples = sorted(by_hour[h])
        if not samples:
            entries.append(
                HourlyVolEntry(hour_utc=h, median_bp=0.0, p75_bp=0.0, n_samples=0)
            )
            continue
        median = _percentile(samples, 50.0)
        p75 = _percentile(samples, 75.0)
        entries.append(
            HourlyVolEntry(
                hour_utc=h,
                median_bp=round(median, 2),
                p75_bp=round(p75, 2),
                n_samples=len(samples),
            )
        )

    populated = [e for e in entries if e.n_samples > 0]
    if populated:
        best = max(populated, key=lambda e: e.median_bp)
        worst = min(populated, key=lambda e: e.median_bp)
        best_hour = best.hour_utc
        worst_hour = worst.hour_utc
    else:
        best_hour = worst_hour = None

    def avg_for(hours: list[int]) -> float | None:
        slc = [entries[h].median_bp for h in hours if entries[h].n_samples > 0]
        if not slc:
            return None
        return round(sum(slc) / len(slc), 2)

    return HourlyVolReport(
        asset=asset,
        window_days=window_days,
        entries=entries,
        best_hour_utc=best_hour,
        worst_hour_utc=worst_hour,
        london_session_avg_bp=avg_for(list(range(7, 16))),
        asian_session_avg_bp=avg_for(list(range(0, 7))),
        generated_at=datetime.now(timezone.utc),
    )


def render_hourly_volatility_block(
    r: HourlyVolReport,
) -> tuple[str, list[str]]:
    populated = [e for e in r.entries if e.n_samples > 0]
    if not populated:
        return (
            f"## Hourly volatility ({r.asset}, {r.window_days}d)\n"
            f"- (insufficient polygon history)",
            [],
        )

    lines = [f"## Hourly volatility ({r.asset}, {r.window_days}d, median |log-ret| bp)"]

    # ASCII heat-bar : two-row compact view
    bar_chars = " ▁▂▃▄▅▆▇█"
    max_med = max(e.median_bp for e in populated) or 1.0

    def cell(e: HourlyVolEntry) -> str:
        if e.n_samples == 0:
            return "·"
        idx = max(0, min(8, int(round(e.median_bp / max_med * 8))))
        return bar_chars[idx]

    hour_row = "".join(f"{e.hour_utc:>3d}" for e in r.entries)
    bar_row = "".join(f"  {cell(e)}" for e in r.entries)
    lines.append(f"- UTC hour : `{hour_row}`")
    lines.append(f"- Activity : `{bar_row}`")

    if r.best_hour_utc is not None:
        be = r.entries[r.best_hour_utc]
        lines.append(
            f"- Best hour (UTC) : {r.best_hour_utc:02d}:00 — "
            f"median {be.median_bp:.1f}bp · p75 {be.p75_bp:.1f}bp"
        )
    if r.worst_hour_utc is not None:
        we = r.entries[r.worst_hour_utc]
        lines.append(
            f"- Worst hour (UTC) : {r.worst_hour_utc:02d}:00 — median {we.median_bp:.1f}bp"
        )
    if r.london_session_avg_bp is not None:
        lines.append(
            f"- London/NY overlap (07-15 UTC) avg : {r.london_session_avg_bp:.1f}bp"
        )
    if r.asian_session_avg_bp is not None:
        lines.append(
            f"- Asian (00-06 UTC) avg : {r.asian_session_avg_bp:.1f}bp"
        )

    sources = [f"polygon_intraday:{r.asset}@hourly_vol_{r.window_days}d"]
    return "\n".join(lines), sources
