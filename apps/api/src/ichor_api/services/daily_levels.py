"""Daily levels computed from polygon_intraday — the SMC/ICT toolbox.

For Eliot's session-momentum strategy, the macro bias is necessary
but insufficient. He also needs the **price levels** that mark order-flow
inflection points : the highs/lows that institutional algorithms watch.

This service pre-computes :
  - PDH / PDL  — Previous Day High / Low (the most-watched levels in
                  intraday FX trading, often act as magnets)
  - Asian range high/low (00:00-07:00 UTC) — Tokyo session footprint
  - Weekly high/low (last 7 calendar days)
  - Classic Pivot Points (PP / R1-R3 / S1-S3) — Camarilla-free version
                  computed from prior day OHLC
  - Round numbers near current spot (psychological levels)

VISION_2026 — answers Eliot's strategy : he trades the momentum away
from these levels (or the rejection at them) on H1/M30/M15/M5.

Pure-stdlib, no pandas dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import PolygonIntradayBar


def _pip_size(asset: str) -> float:
    """Pip multiplier in *price units* — used to round near-by levels.

    For JPY pairs : 1 pip = 0.01.
    For XAU : 1 pip ~= $0.10 (informal trader convention).
    For indices : 1 point = 1 (raw).
    For standard FX : 1 pip = 0.0001.
    """
    a = asset.upper()
    if a.endswith("JPY"):
        return 0.01
    if a == "XAU_USD":
        return 0.10
    if a in ("NAS100_USD", "SPX500_USD", "US100", "US30"):
        return 1.0
    return 0.0001


def _round_levels_near(spot: float, asset: str, count: int = 4) -> list[float]:
    """Round-number psychological levels above + below spot.

    For EUR/USD 1.0734 → returns 1.0700, 1.0750, 1.0800, 1.0850
    (50-pip increments). For USD/JPY 152.34 → 152.00, 152.50, 153.00, 153.50.
    """
    a = asset.upper()
    if a.endswith("JPY"):
        step = 0.50
    elif a == "XAU_USD":
        step = 5.0
    elif a in ("NAS100_USD", "SPX500_USD", "US100", "US30"):
        step = 25.0
    else:
        step = 0.0050  # 50 pips on standard FX
    base = round(spot / step) * step
    return sorted({round(base + step * i, 5) for i in range(-count, count + 1)})


@dataclass(frozen=True)
class DailyLevels:
    """All key levels Eliot watches before/during a session."""

    asset: str
    spot: float | None
    """Last known close from polygon_intraday."""

    pdh: float | None
    pdl: float | None
    pd_close: float | None
    """Previous-day close (used for pivot calc)."""

    asian_high: float | None
    asian_low: float | None

    weekly_high: float | None
    weekly_low: float | None

    pivot: float | None
    r1: float | None
    r2: float | None
    r3: float | None
    s1: float | None
    s2: float | None
    s3: float | None

    round_levels: list[float]


def _classic_pivots(
    pd_high: float | None, pd_low: float | None, pd_close: float | None
) -> tuple[float | None, ...]:
    """Floor-trader pivot formula (most-watched on FX desks).

    PP = (H + L + C) / 3
    R1 = 2*PP - L     S1 = 2*PP - H
    R2 = PP + (H - L) S2 = PP - (H - L)
    R3 = H + 2*(PP-L) S3 = L - 2*(H-PP)
    """
    if pd_high is None or pd_low is None or pd_close is None:
        return (None, None, None, None, None, None, None)
    pp = (pd_high + pd_low + pd_close) / 3.0
    r1 = 2 * pp - pd_low
    s1 = 2 * pp - pd_high
    range_ = pd_high - pd_low
    r2 = pp + range_
    s2 = pp - range_
    r3 = pd_high + 2 * (pp - pd_low)
    s3 = pd_low - 2 * (pd_high - pp)
    return (
        round(pp, 5),
        round(r1, 5),
        round(r2, 5),
        round(r3, 5),
        round(s1, 5),
        round(s2, 5),
        round(s3, 5),
    )


async def assess_daily_levels(session: AsyncSession, asset: str) -> DailyLevels:
    """Pull last 8d of bars and assemble all levels."""
    cutoff = datetime.now(UTC) - timedelta(days=8)
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
        )
        .scalars()
        .all()
    )
    if not rows:
        return DailyLevels(
            asset=asset,
            spot=None,
            pdh=None,
            pdl=None,
            pd_close=None,
            asian_high=None,
            asian_low=None,
            weekly_high=None,
            weekly_low=None,
            pivot=None,
            r1=None,
            r2=None,
            r3=None,
            s1=None,
            s2=None,
            s3=None,
            round_levels=[],
        )

    spot = float(rows[-1].close)
    today_utc = datetime.now(UTC).date()

    # Group bars by UTC date
    by_date: dict[str, list[PolygonIntradayBar]] = {}
    for r in rows:
        d = r.bar_ts.date().isoformat()
        by_date.setdefault(d, []).append(r)

    # Previous trading day = the most-recent date < today that has bars
    sorted_dates = sorted(by_date.keys(), reverse=True)
    pd_date = next(
        (d for d in sorted_dates if d != today_utc.isoformat()),
        None,
    )
    if pd_date is None:
        pd_high = pd_low = pd_close = None
    else:
        pd_bars = by_date[pd_date]
        pd_high = max(float(b.high) for b in pd_bars)
        pd_low = min(float(b.low) for b in pd_bars)
        pd_close = float(pd_bars[-1].close)

    # Today's Asian range : bars with timestamp between 00:00 and 07:00 UTC
    today_str = today_utc.isoformat()
    today_bars = by_date.get(today_str, [])
    asian_bars = [b for b in today_bars if b.bar_ts.hour < 7]
    if asian_bars:
        asian_high = max(float(b.high) for b in asian_bars)
        asian_low = min(float(b.low) for b in asian_bars)
    else:
        asian_high = asian_low = None

    # Weekly = last 7 days from cutoff
    weekly_bars = [r for r in rows if r.bar_ts.date() >= today_utc - timedelta(days=7)]
    if weekly_bars:
        weekly_high = max(float(b.high) for b in weekly_bars)
        weekly_low = min(float(b.low) for b in weekly_bars)
    else:
        weekly_high = weekly_low = None

    pp, r1, r2, r3, s1, s2, s3 = _classic_pivots(pd_high, pd_low, pd_close)
    round_levels = _round_levels_near(spot, asset)

    return DailyLevels(
        asset=asset,
        spot=spot,
        pdh=pd_high,
        pdl=pd_low,
        pd_close=pd_close,
        asian_high=asian_high,
        asian_low=asian_low,
        weekly_high=weekly_high,
        weekly_low=weekly_low,
        pivot=pp,
        r1=r1,
        r2=r2,
        r3=r3,
        s1=s1,
        s2=s2,
        s3=s3,
        round_levels=round_levels,
    )


def render_daily_levels_block(r: DailyLevels) -> tuple[str, list[str]]:
    """Markdown block for data_pool.py — concise but exhaustive."""
    if r.spot is None:
        return (
            f"## Daily levels ({r.asset})\n- (no intraday bars yet)",
            [],
        )

    def fmt(v: float | None) -> str:
        return "n/a" if v is None else f"{v:.5f}".rstrip("0").rstrip(".")

    lines = [f"## Daily levels ({r.asset})"]
    lines.append(f"- Spot              = {fmt(r.spot)}")
    lines.append(f"- Previous day H/L  = {fmt(r.pdh)} / {fmt(r.pdl)} (close {fmt(r.pd_close)})")
    if r.asian_high is not None or r.asian_low is not None:
        lines.append(
            f"- Asian range H/L   = {fmt(r.asian_high)} / {fmt(r.asian_low)} (00:00-07:00 UTC)"
        )
    lines.append(f"- Weekly H/L (7d)   = {fmt(r.weekly_high)} / {fmt(r.weekly_low)}")
    if r.pivot is not None:
        lines.append(
            f"- Pivots PP / R1-R3 / S1-S3 = "
            f"{fmt(r.pivot)} / {fmt(r.r1)} {fmt(r.r2)} {fmt(r.r3)} / "
            f"{fmt(r.s1)} {fmt(r.s2)} {fmt(r.s3)}"
        )
    if r.round_levels:
        lines.append(f"- Round-number levels nearby : {', '.join(fmt(x) for x in r.round_levels)}")
    sources = [f"polygon_intraday:{r.asset}@daily_levels"]
    return "\n".join(lines), sources
