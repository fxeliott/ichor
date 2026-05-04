"""US Treasury yield curve — full term structure with inversion analytics.

Pulls 8 standard maturities from FRED daily-yields and exposes :
  - Each tenor's latest yield + observation date
  - Curve slopes : 3M-10Y, 2Y-10Y, 5Y-30Y
  - Inversion strength : how many segments are inverted
  - Real yield (TIPS) : DFII10 if available, else nominal-CPI proxy

Why this matters for FX/index trading :
  - 10Y-2Y inversion ≥ 6 months → recession proxy → USD haven flows
  - Bear-steepening (10Y > 2Y rising) → inflation premium → gold up
  - Bull-flattening (2Y > 10Y falling) → growth fear → equity short
  - 3M-10Y inverted ≥ 1 quarter → NY Fed recession-prob model fires

Pure stdlib computation, no fancy curve fitting (just linear interp
between known tenors when needed).

VISION_2026 — closes the "we have DGS10 but not the full curve" gap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import FredObservation


# Tenors in years × series_id
_TENORS: list[tuple[float, str, str]] = [
    # tenor_years, series_id, label
    (0.083, "DTB3", "3M"),     # 13-week T-bill
    (0.5,   "DGS6MO", "6M"),
    (1.0,   "DGS1", "1Y"),
    (2.0,   "DGS2", "2Y"),
    (3.0,   "DGS3", "3Y"),
    (5.0,   "DGS5", "5Y"),
    (7.0,   "DGS7", "7Y"),
    (10.0,  "DGS10", "10Y"),
    (20.0,  "DGS20", "20Y"),
    (30.0,  "DGS30", "30Y"),
]


CurveShape = Literal[
    "normal", "steep", "flat", "inverted_short", "inverted_full"
]


@dataclass(frozen=True)
class TenorPoint:
    tenor_years: float
    label: str
    series_id: str
    yield_pct: float | None
    observation_date: datetime | None


@dataclass(frozen=True)
class YieldCurveReading:
    points: list[TenorPoint]
    slope_3m_10y: float | None
    """10Y - 3M, in pp. Negative = inverted (recession proxy)."""
    slope_2y_10y: float | None
    """10Y - 2Y, in pp. Negative = inverted."""
    slope_5y_30y: float | None
    real_yield_10y: float | None
    """DFII10 (TIPS real yield)."""
    inverted_segments: int
    """Count of consecutive-tenor pairs where shorter > longer."""
    shape: CurveShape
    note: str = ""
    sources: list[str] = field(default_factory=list)


async def _latest_value(
    session: AsyncSession, series_id: str, max_age_days: int = 14
) -> tuple[float, datetime] | None:
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=max_age_days)
    row = (
        await session.execute(
            select(FredObservation)
            .where(
                FredObservation.series_id == series_id,
                FredObservation.observation_date >= cutoff,
                FredObservation.value.is_not(None),
            )
            .order_by(desc(FredObservation.observation_date))
            .limit(1)
        )
    ).scalars().first()
    if row is None or row.value is None:
        return None
    return (
        float(row.value),
        datetime.combine(
            row.observation_date, datetime.min.time(), tzinfo=timezone.utc
        ),
    )


def _shape(
    points: list[TenorPoint], slope_2y_10y: float | None
) -> CurveShape:
    yields = [p.yield_pct for p in points if p.yield_pct is not None]
    if len(yields) < 4:
        return "flat"
    inverted = sum(
        1 for i in range(len(yields) - 1) if yields[i] > yields[i + 1]
    )
    if inverted >= len(yields) - 2:
        return "inverted_full"
    if slope_2y_10y is not None and slope_2y_10y < 0:
        return "inverted_short"
    if slope_2y_10y is not None and slope_2y_10y > 1.5:
        return "steep"
    if slope_2y_10y is not None and abs(slope_2y_10y) < 0.3:
        return "flat"
    return "normal"


async def assess_yield_curve(session: AsyncSession) -> YieldCurveReading:
    points: list[TenorPoint] = []
    sources: list[str] = []
    for tenor, sid, label in _TENORS:
        v = await _latest_value(session, sid)
        if v is None:
            points.append(
                TenorPoint(
                    tenor_years=tenor,
                    label=label,
                    series_id=sid,
                    yield_pct=None,
                    observation_date=None,
                )
            )
            continue
        sources.append(f"FRED:{sid}")
        points.append(
            TenorPoint(
                tenor_years=tenor,
                label=label,
                series_id=sid,
                yield_pct=v[0],
                observation_date=v[1],
            )
        )

    by_label: dict[str, float | None] = {p.label: p.yield_pct for p in points}

    def slope(short: str, long: str) -> float | None:
        s, l = by_label.get(short), by_label.get(long)
        if s is None or l is None:
            return None
        return l - s

    slope_3m_10y = slope("3M", "10Y")
    slope_2y_10y = slope("2Y", "10Y")
    slope_5y_30y = slope("5Y", "30Y")

    # TIPS real yield (already a separate FRED series, not in tenors above)
    real_v = await _latest_value(session, "DFII10")
    if real_v is not None:
        sources.append("FRED:DFII10")

    # Inverted segments
    inverted_count = 0
    for i in range(len(points) - 1):
        a, b = points[i].yield_pct, points[i + 1].yield_pct
        if a is not None and b is not None and a > b:
            inverted_count += 1

    shape = _shape(points, slope_2y_10y)
    note_parts: list[str] = []
    if slope_3m_10y is not None and slope_3m_10y < 0:
        note_parts.append(
            "3M-10Y inverted → NY Fed recession proxy fires (≥ 1 quarter "
            "inversion has preceded every recession since 1960)"
        )
    if slope_2y_10y is not None and slope_2y_10y < 0:
        note_parts.append(
            "2Y-10Y inverted → growth premium compressed, USD haven flows expected"
        )
    if shape == "steep":
        note_parts.append(
            "Steep curve → growth + inflation premium pricing in, gold-friendly"
        )
    if shape == "inverted_full":
        note_parts.append("Curve fully inverted — late-cycle, mean-revert friendly")

    return YieldCurveReading(
        points=points,
        slope_3m_10y=slope_3m_10y,
        slope_2y_10y=slope_2y_10y,
        slope_5y_30y=slope_5y_30y,
        real_yield_10y=real_v[0] if real_v else None,
        inverted_segments=inverted_count,
        shape=shape,
        note=" ; ".join(note_parts),
        sources=sources,
    )


def render_yield_curve_block(r: YieldCurveReading) -> tuple[str, list[str]]:
    """## US Treasury yield curve — full term structure."""
    pts = [p for p in r.points if p.yield_pct is not None]
    if not pts:
        return ("## US Treasury yield curve\n- (no FRED yields available)", [])

    lines = [f"## US Treasury yield curve (shape: {r.shape})"]

    # One line with all tenors compactly
    parts = [
        f"{p.label}={p.yield_pct:.2f}%"
        for p in r.points
        if p.yield_pct is not None
    ]
    lines.append(f"- Curve : {' · '.join(parts)}")

    if r.slope_3m_10y is not None:
        lines.append(
            f"- Slope 3M-10Y = {r.slope_3m_10y:+.2f}pp "
            f"({'inverted' if r.slope_3m_10y < 0 else 'normal'})"
        )
    if r.slope_2y_10y is not None:
        lines.append(
            f"- Slope 2Y-10Y = {r.slope_2y_10y:+.2f}pp "
            f"({'inverted' if r.slope_2y_10y < 0 else 'normal'})"
        )
    if r.slope_5y_30y is not None:
        lines.append(f"- Slope 5Y-30Y = {r.slope_5y_30y:+.2f}pp")
    if r.real_yield_10y is not None:
        lines.append(
            f"- Real yield 10Y (TIPS DFII10) = {r.real_yield_10y:.2f}%"
        )
    lines.append(f"- Inverted segments : {r.inverted_segments}")
    if r.note:
        lines.append(f"- Reading : {r.note}")
    return "\n".join(lines), list(r.sources)
