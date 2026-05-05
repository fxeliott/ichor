"""Asian session signals — Tokyo fix proximity + intra-session delta.

For pairs that route their primary order flow through Asia (USD/JPY,
AUD/USD, NZD/USD), the Asian session (~00:00-07:00 UTC) gives the
first read on positioning before Londres/NY take over.

Key timestamps (per BoJ + JBA conventions) :
  - Tokyo opens   : 00:00 UTC (09:00 JST)
  - Tokyo fix     : 00:55 UTC (09:55 JST) — BoJ publishes daily fixing
  - Tokyo lunch   : 02:30-03:30 UTC
  - Tokyo close   : 06:00 UTC (15:00 JST)
  - Sydney close  : 06:30 UTC (16:30 AEST)

VISION_2026 delta F — Asian session liquidity. Pure-stdlib, no extra
dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import PolygonIntradayBar

# Pairs where the Asian session is informative (JPY routed through
# Tokyo, AUD/NZD through Sydney/Tokyo overlap).
_ASIAN_RELEVANT: frozenset[str] = frozenset(
    {"USD_JPY", "AUD_USD", "NZD_USD", "AUD_JPY", "NZD_JPY", "EUR_JPY", "GBP_JPY"}
)


@dataclass(frozen=True)
class AsianSessionReading:
    asset: str
    session_date_utc: str
    """ISO date 'YYYY-MM-DD' of the Asian session under analysis."""

    n_bars: int

    open_price: float | None
    """First Polygon bar of the session (≈ 00:00 UTC)."""
    fix_price: float | None
    """Bar at 00:55 UTC ± 2min (Tokyo daily fix proxy)."""
    close_price: float | None
    """Last bar of the session (≤ 07:00 UTC)."""

    high: float | None
    low: float | None
    range_pips: float | None
    """High-Low expressed in pips (FX) or points (indices). Pip size
    inferred from the asset code."""

    open_to_fix_pips: float | None
    fix_to_close_pips: float | None
    open_to_close_pips: float | None

    direction: str
    """'asian_bid' / 'asian_offered' / 'asian_range' — narrative tag."""

    volume_total: float
    note: str = ""


def _pip_size(asset: str) -> float:
    """Pip multiplier for converting price diff → pips/points."""
    a = asset.upper()
    if a.endswith("JPY"):
        return 100.0  # 0.01 = 1 pip on JPY pairs
    if a in ("XAU_USD",):
        return 10.0  # 0.10 = 1 pip on XAU (rough)
    if a in ("NAS100_USD", "SPX500_USD", "US30", "US100"):
        return 1.0  # raw points
    return 10_000.0  # 0.0001 = 1 pip on standard FX


def _utc_today_midnight() -> datetime:
    now = datetime.now(UTC)
    return datetime(now.year, now.month, now.day, 0, 0, tzinfo=UTC)


async def assess_asian_session(
    session: AsyncSession,
    asset: str,
    *,
    reference_day: datetime | None = None,
) -> AsianSessionReading | None:
    """Pull bars for the Asian session (00:00-07:00 UTC of `reference_day`).

    Returns None when the asset isn't Asian-relevant or no bars sit in
    the window.
    """
    if asset.upper() not in _ASIAN_RELEVANT:
        return None

    base = reference_day or _utc_today_midnight()
    window_start = base
    window_end = base + timedelta(hours=7)
    fix_anchor = base + timedelta(minutes=55)
    fix_lo = fix_anchor - timedelta(minutes=2)
    fix_hi = fix_anchor + timedelta(minutes=2)

    rows = list(
        (
            await session.execute(
                select(PolygonIntradayBar)
                .where(
                    PolygonIntradayBar.asset == asset,
                    PolygonIntradayBar.bar_ts >= window_start,
                    PolygonIntradayBar.bar_ts < window_end,
                )
                .order_by(PolygonIntradayBar.bar_ts.asc())
            )
        )
        .scalars()
        .all()
    )

    if not rows:
        return AsianSessionReading(
            asset=asset,
            session_date_utc=base.date().isoformat(),
            n_bars=0,
            open_price=None,
            fix_price=None,
            close_price=None,
            high=None,
            low=None,
            range_pips=None,
            open_to_fix_pips=None,
            fix_to_close_pips=None,
            open_to_close_pips=None,
            direction="asian_range",
            volume_total=0.0,
            note="no bars in Asian session window",
        )

    open_price = float(rows[0].close)
    close_price = float(rows[-1].close)
    high_v = max(float(r.high) for r in rows)
    low_v = min(float(r.low) for r in rows)
    volume = sum(float(r.volume or 0) for r in rows)

    # Tokyo fix proxy : pick the bar inside ±2min of 00:55 UTC
    fix_bar = next(
        (r for r in rows if fix_lo <= r.bar_ts <= fix_hi),
        None,
    )
    fix_price = float(fix_bar.close) if fix_bar else None

    pip = _pip_size(asset)
    range_pips = round((high_v - low_v) * pip, 1)
    o2c_pips = round((close_price - open_price) * pip, 1)
    o2f_pips = round((fix_price - open_price) * pip, 1) if fix_price is not None else None
    f2c_pips = round((close_price - fix_price) * pip, 1) if fix_price is not None else None

    direction = (
        "asian_bid"
        if o2c_pips > range_pips * 0.4
        else "asian_offered"
        if o2c_pips < -range_pips * 0.4
        else "asian_range"
    )

    note_parts: list[str] = []
    if fix_bar is None:
        note_parts.append("no fix bar (market may be closed)")
    if range_pips and range_pips < 5:
        note_parts.append("compressed range")

    return AsianSessionReading(
        asset=asset,
        session_date_utc=base.date().isoformat(),
        n_bars=len(rows),
        open_price=open_price,
        fix_price=fix_price,
        close_price=close_price,
        high=high_v,
        low=low_v,
        range_pips=range_pips,
        open_to_fix_pips=o2f_pips,
        fix_to_close_pips=f2c_pips,
        open_to_close_pips=o2c_pips,
        direction=direction,
        volume_total=volume,
        note="; ".join(note_parts) if note_parts else "",
    )


def render_asian_session_block(
    r: AsianSessionReading | None,
) -> tuple[str, list[str]]:
    """Markdown block + sources. Returns ('', []) when r is None."""
    if r is None:
        return "", []
    if r.n_bars == 0:
        md = (
            f"## Asian session ({r.asset}, {r.session_date_utc})\n"
            "- (no bars in 00:00-07:00 UTC window — market closed or data missing)"
        )
        return md, []

    def fmt(v: float | None, suffix: str = "") -> str:
        return "n/a" if v is None else f"{v:.5f}{suffix}"

    def fmt_pips(v: float | None) -> str:
        return "n/a" if v is None else f"{v:+.1f}p"

    lines = [
        f"## Asian session ({r.asset}, {r.session_date_utc}, {r.n_bars} bars)",
        f"- Open (00:00 UTC)   = {fmt(r.open_price)}",
        f"- Tokyo fix (00:55)  = {fmt(r.fix_price)}",
        f"- Close (≤07:00 UTC) = {fmt(r.close_price)}",
        f"- High / Low         = {fmt(r.high)} / {fmt(r.low)}",
        f"- Range              = {fmt_pips(r.range_pips)}",
        f"- Open→Fix           = {fmt_pips(r.open_to_fix_pips)}",
        f"- Fix→Close          = {fmt_pips(r.fix_to_close_pips)}",
        f"- Open→Close         = {fmt_pips(r.open_to_close_pips)}",
        f"- Direction tag      = **{r.direction}**",
        f"- Volume total       = {r.volume_total:.0f}",
    ]
    if r.note:
        lines.append(f"- Note: {r.note}")
    sources = [f"polygon_intraday:{r.asset}@asian_session:{r.session_date_utc}"]
    return "\n".join(lines), sources


def supported_pairs() -> tuple[str, ...]:
    return tuple(sorted(_ASIAN_RELEVANT))
