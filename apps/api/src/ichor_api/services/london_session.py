"""London-morning session read — calibrate the upcoming NY session (§6.2).

The owner's CAPITAL point : read how the asset traded during the LONDON
MORNING (the session that runs before / into the NY open) to inform the
NY-session view. This is DISTINCT from `previous_session_origin_zone` (which
answers "which of the 3 UTC zones drove the prior 24h"): here we summarise the
London-morning window specifically — its range, direction, and whether it was
unusually active vs the typical London morning.

The core `compute_london_session` is pure (no I/O) so it is fully unit-testable
with synthetic bars; `compute_london_session_for_asset` is the thin async DB
wrapper — the single source of truth shared by the data_pool Pass-2 section AND
the `/v1/london-session` endpoint, so the two can never drift on which bars feed
the read. Timezone is handled with `ZoneInfo("Europe/London")` so the London
local window maps to the correct UTC bounds across DST (London is UTC+1 in
summer / BST, UTC in winter) — more correct than a fixed UTC-hour band.

Reuses `_classify_direction` (body/range ≥ 0.3) from the origin-zone module so
the directional read is consistent across the codebase (no duplicate logic).
ADR-017 : descriptive price-action read, never BUY/SELL.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Final
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .previous_session_origin_zone import _classify_direction

_LONDON_TZ = ZoneInfo("Europe/London")
# London-morning window (local) most predictive of the NY open : cash open
# 08:00 through the late-morning 12:00, before the NY pre-open overlap.
_LONDON_OPEN = time(8, 0)
_LONDON_MORNING_CLOSE = time(12, 0)
# Minimum 1-minute bars for a window to count (mirror origin-zone _MIN_BAR_COUNT).
_MIN_BARS = 30
# Prior London windows averaged for the "today vs typical" activity ratio.
_BASELINE_DAYS = 5
# Lookback for the polygon_intraday fetch — 7 days covers the latest
# London-morning window plus up to `_BASELINE_DAYS` prior windows for the
# activity ratio (weekends / holidays are naturally skipped by the date scan).
_LONDON_LOOKBACK_DAYS: Final[int] = 7


@dataclass(frozen=True)
class Bar:
    """A 1-minute OHLC bar (tz-aware UTC timestamp)."""

    ts: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class LondonSessionRead:
    """Summary of the most-recent complete-enough London-morning window."""

    session_date: date
    open_price: float
    high: float
    low: float
    close: float
    range_abs: float
    net_change: float
    direction: str  # "up" | "down" | "range"
    bar_count: int
    avg_range: float | None
    range_ratio: float | None  # this window's range / avg of prior windows
    is_today: bool  # window date == today (London) → "this morning, live"


def london_window_utc(d: date) -> tuple[datetime, datetime]:
    """UTC bounds of the London-morning window for London-local date `d`.

    DST-correct via ZoneInfo : the same 08:00-12:00 London local maps to
    07:00-11:00 UTC in summer (BST) and 08:00-12:00 UTC in winter.
    """
    start_local = datetime.combine(d, _LONDON_OPEN, tzinfo=_LONDON_TZ)
    end_local = datetime.combine(d, _LONDON_MORNING_CLOSE, tzinfo=_LONDON_TZ)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def _window_ohlc(win: list[Bar]) -> tuple[float, float, float, float, int] | None:
    """(open, high, low, close, n) for a window, or None if too few bars."""
    if len(win) < _MIN_BARS:
        return None
    high = max(b.high for b in win)
    low = min(b.low for b in win)
    return win[0].open, high, low, win[-1].close, len(win)


def compute_london_session(bars: list[Bar], *, now_utc: datetime) -> LondonSessionRead | None:
    """Most-recent complete-enough London-morning window + activity baseline.

    Scans the London-local dates present in `bars` (newest first), takes the
    most recent date whose London-morning window clears `_MIN_BARS`, and
    computes its OHLC/range/direction. Averages the range of up to
    `_BASELINE_DAYS` prior London windows for a "today vs typical" ratio.
    Returns None on no usable window (honest absence, doctrine #11).
    """
    if not bars:
        return None
    today_london = now_utc.astimezone(_LONDON_TZ).date()
    dates = sorted({b.ts.astimezone(_LONDON_TZ).date() for b in bars}, reverse=True)

    reads: list[tuple[date, tuple[float, float, float, float, int]]] = []
    for d in dates:
        start, end = london_window_utc(d)
        win = [b for b in bars if start <= b.ts < end]
        ohlc = _window_ohlc(win)
        if ohlc is not None:
            reads.append((d, ohlc))

    if not reads:
        return None

    latest_date, (op, high, low, close, n) = reads[0]
    rng = high - low
    prior = [r[1] for r in reads[1 : 1 + _BASELINE_DAYS]]
    avg_range = (sum(p[1] - p[2] for p in prior) / len(prior)) if prior else None
    ratio = (rng / avg_range) if (avg_range and avg_range > 0) else None
    return LondonSessionRead(
        session_date=latest_date,
        open_price=op,
        high=high,
        low=low,
        close=close,
        range_abs=rng,
        net_change=close - op,
        direction=_classify_direction(op, close, high, low),
        bar_count=n,
        avg_range=avg_range,
        range_ratio=ratio,
        is_today=(latest_date == today_london),
    )


async def compute_london_session_for_asset(
    session: AsyncSession, asset: str, *, now_utc: datetime
) -> LondonSessionRead | None:
    """Async DB wrapper around the pure `compute_london_session`.

    Fetches the last `_LONDON_LOOKBACK_DAYS` of `polygon_intraday` 1-min bars
    for `asset` (ascending so `bars[0]` is the oldest), maps the NULL-safe rows
    to `Bar`, and computes the most-recent London-morning read. This is the
    single source of truth shared by the data_pool Pass-2 section AND the
    `/v1/london-session/{asset}` endpoint, so neither can drift on the bar set.
    Returns None on honest absence (no usable London window) — doctrine #11.
    """
    # Lazy import: avoid a circular dep with the ORM models package and keep
    # the pure helpers importable without the ORM at test-collection time.
    from ..models import PolygonIntradayBar

    rows = (
        await session.execute(
            select(
                PolygonIntradayBar.bar_ts,
                PolygonIntradayBar.open,
                PolygonIntradayBar.high,
                PolygonIntradayBar.low,
                PolygonIntradayBar.close,
            )
            .where(PolygonIntradayBar.asset == asset)
            .where(PolygonIntradayBar.bar_ts >= now_utc - timedelta(days=_LONDON_LOOKBACK_DAYS))
            .order_by(PolygonIntradayBar.bar_ts.asc())
        )
    ).all()
    bars = [
        Bar(ts=r[0], open=float(r[1]), high=float(r[2]), low=float(r[3]), close=float(r[4]))
        for r in rows
        if r[1] is not None and r[4] is not None
    ]
    return compute_london_session(bars, now_utc=now_utc)
