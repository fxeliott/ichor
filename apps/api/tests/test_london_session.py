"""Tests for the London-morning session read (§6.2 NY calibration).

Pure compute pinned with synthetic 1-minute bars; the DB path is verified live
on card regen. Includes a DST check on the London→UTC window mapping.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from ichor_api.services.london_session import (
    Bar,
    compute_london_session,
    london_window_utc,
)


def test_london_window_dst_summer_vs_winter() -> None:
    # Late-May 2026 = BST (UTC+1): London 08:00-12:00 → 07:00-11:00 UTC.
    s, e = london_window_utc(date(2026, 5, 29))
    assert s.hour == 7 and e.hour == 11
    # Mid-Jan 2026 = GMT (UTC+0): London 08:00-12:00 → 08:00-12:00 UTC.
    sw, ew = london_window_utc(date(2026, 1, 15))
    assert sw.hour == 8 and ew.hour == 12


def _win_bars(
    d: date, *, n: int, open_p: float, close_p: float, high_p: float, low_p: float
) -> list[Bar]:
    """Synthetic 1-min bars filling a date's London window, exact O/H/L/C."""
    start, _ = london_window_utc(d)
    step = (close_p - open_p) / (n - 1) if n > 1 else 0.0
    bars: list[Bar] = []
    for i in range(n):
        o = open_p + step * i
        c = close_p if i == n - 1 else open_p + step * (i + 1)
        h, low = max(o, c), min(o, c)
        if i == 1:
            h = high_p  # inject window high
        if i == 2:
            low = low_p  # inject window low
        bars.append(Bar(ts=start + timedelta(minutes=i), open=o, high=h, low=low, close=c))
    b0 = bars[0]
    bars[0] = Bar(ts=b0.ts, open=open_p, high=b0.high, low=b0.low, close=b0.close)
    return bars


def test_compute_london_up_active_vs_calm_baseline() -> None:
    friday = _win_bars(
        date(2026, 5, 29), n=40, open_p=1.1600, close_p=1.1640, high_p=1.1645, low_p=1.1595
    )
    thursday = _win_bars(
        date(2026, 5, 28), n=40, open_p=1.1600, close_p=1.1602, high_p=1.1610, low_p=1.1595
    )
    now = datetime(2026, 5, 30, 9, 0, tzinfo=UTC)  # Saturday → latest window is Friday
    read = compute_london_session(thursday + friday, now_utc=now)
    assert read is not None
    assert read.session_date == date(2026, 5, 29)
    assert read.direction == "up"
    assert round(read.range_abs, 4) == 0.0050  # 1.1645 - 1.1595
    assert round(read.net_change, 4) == 0.0040
    assert read.is_today is False  # Friday window, not Saturday
    # Friday range 50 pips vs Thursday 15 pips → ratio > 1.4 (ACTIVE)
    assert read.range_ratio is not None and read.range_ratio >= 1.4


def test_compute_london_range_direction() -> None:
    calm = _win_bars(
        date(2026, 5, 29), n=40, open_p=1.1600, close_p=1.1602, high_p=1.1612, low_p=1.1592
    )
    read = compute_london_session(calm, now_utc=datetime(2026, 5, 30, 9, 0, tzinfo=UTC))
    assert read is not None
    # body 2 pips / range 20 pips = 0.1 < 0.3 → range
    assert read.direction == "range"


def test_compute_london_is_today_flag() -> None:
    today = date(2026, 5, 29)
    bars = _win_bars(today, n=40, open_p=1.16, close_p=1.163, high_p=1.1635, low_p=1.1598)
    # now AFTER the London window on the same London-local day
    now = datetime(2026, 5, 29, 12, 0, tzinfo=UTC)
    read = compute_london_session(bars, now_utc=now)
    assert read is not None and read.is_today is True


def test_compute_london_empty_and_too_few() -> None:
    assert compute_london_session([], now_utc=datetime(2026, 5, 30, 9, 0, tzinfo=UTC)) is None
    few = _win_bars(date(2026, 5, 29), n=10, open_p=1.16, close_p=1.161, high_p=1.162, low_p=1.159)
    assert compute_london_session(few, now_utc=datetime(2026, 5, 30, 9, 0, tzinfo=UTC)) is None
