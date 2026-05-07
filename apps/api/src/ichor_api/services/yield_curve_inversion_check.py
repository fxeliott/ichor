"""YIELD_CURVE_INVERSION_DEEP alert wiring (Phase E innovation).

Detects deep inversion of the 10y - 2y Treasury yield spread (T10Y2Y),
the most-watched recession leading indicator since 1976.

Mechanics :
  - T10Y2Y > 0  : normal upward-sloping curve (growth expected)
  - T10Y2Y ~ 0  : flat curve (transition)
  - T10Y2Y < 0  : INVERTED — bond market prices near-term Fed tightening
                  followed by economic weakness
  - T10Y2Y < -0.50 (-50 bps) : DEEP inversion threshold (this alert)

Historical track record (since 1976) :
  - 7 inversions preceded 6 US recessions (1998 false signal)
  - Median lag inversion → recession peak: ~14 months (range 6-24)
  - Magnitude irrelevant to recession severity : -19 bps in 2006 → GFC ;
    -240 bps in 1980 → brief 6-month recession.
  - 2022-2024 inversion (-108 bps trough, 25 months) is the SECOND
    deepest in the FRED series — has not been followed by recession yet
    (anomaly, "this time is different" debate).

Counterintuitive pattern : recessions tend to begin AFTER the spread
returns to positive ("un-inversion") rather than during inversion. The
un-inversion itself is historically the warning. This alert flags the
DEEP INVERSION level as a leading regime tag ; a future v2 sister alert
could detect the un-inversion event (cross_up from negative to zero).

Current state (April 2026) : T10Y2Y +0.21 pp = re-steepened after the
25-month inversion ended. NY Fed assigns 25% recession probability for
Nov 2026.

Per Cleveland Fed + NY Fed Capital Markets methodology + multiple
academic studies (Estrella-Mishkin 1998, Wright 2006). FRED:T10Y2Y is
the canonical free data source.

Source-stamping (ADR-017) :
  - extra_payload.source = "FRED:T10Y2Y"
  - extra_payload includes spread value (pct + bps), regime tag,
    historical context

ROADMAP E (innovations). ADR-046.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import FredObservation
from .alerts_runner import check_metric

# FRED series id : 10y - 2y constant-maturity Treasury spread.
# Unit is percentage points (e.g. -0.50 = -50 bps inverted).
T10Y2Y_SERIES_ID = "T10Y2Y"

# Threshold mirrors catalog default. -0.50 (= -50 bps) is the "deep
# inversion" floor — historically meaningful (recessions associated
# with -19 bps to -240 bps range, but -50 is the doctrinal "deep" cut-off
# used by NY Fed + most academic literature).
DEEP_INVERSION_FLOOR_PCT: float = -0.50

# Secondary thresholds (informational only, exposed in regime tag) :
SHALLOW_INVERSION_FLOOR_PCT: float = 0.0    # any inversion
SEVERE_INVERSION_FLOOR_PCT: float = -1.00   # -100 bps "severe"


@dataclass(frozen=True)
class YieldCurveInversionResult:
    """One run summary."""

    spread_pct: float | None
    """Latest T10Y2Y reading in % (FRED units). -0.50 = -50 bps."""

    spread_bps: float | None
    """Same in bps (= pct * 100)."""

    observation_date: date | None
    regime: str
    """'severe_inversion' (<= -1.0) | 'deep_inversion' (-1.0 to -0.5) |
    'shallow_inversion' (-0.5 to 0) | 'flat' (0-0.25) |
    'normal' (>= 0.25) | '' if degenerate."""

    alert_fired: bool
    """True only when spread <= DEEP_INVERSION_FLOOR_PCT."""

    note: str = ""


def _classify_regime(spread_pct: float | None) -> str:
    """Map raw T10Y2Y spread to regime tag per academic / NY Fed convention."""
    if spread_pct is None:
        return ""
    if spread_pct <= SEVERE_INVERSION_FLOOR_PCT:
        return "severe_inversion"
    if spread_pct <= DEEP_INVERSION_FLOOR_PCT:
        return "deep_inversion"
    if spread_pct < SHALLOW_INVERSION_FLOOR_PCT:
        return "shallow_inversion"
    if spread_pct < 0.25:
        return "flat"
    return "normal"


async def _fetch_latest_spread(
    session: AsyncSession,
) -> tuple[date, float] | None:
    """Latest non-null T10Y2Y observation. None if no rows."""
    cutoff = datetime.now(UTC).date() - timedelta(days=14)
    stmt = (
        select(FredObservation.observation_date, FredObservation.value)
        .where(
            FredObservation.series_id == T10Y2Y_SERIES_ID,
            FredObservation.observation_date >= cutoff,
            FredObservation.value.is_not(None),
        )
        .order_by(desc(FredObservation.observation_date))
        .limit(1)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        return None
    d, v = row
    return (d, float(v)) if v is not None else None


async def evaluate_yield_curve_inversion(
    session: AsyncSession,
    *,
    persist: bool = True,
) -> YieldCurveInversionResult:
    """Evaluate latest T10Y2Y, fire YIELD_CURVE_INVERSION_DEEP when
    spread <= -0.50 pp (= -50 bps).

    Returns a structured result so the CLI can print a one-liner.
    """
    row = await _fetch_latest_spread(session)
    if row is None:
        return YieldCurveInversionResult(
            spread_pct=None,
            spread_bps=None,
            observation_date=None,
            regime="",
            alert_fired=False,
            note=(
                "no T10Y2Y observations in last 14d — verify "
                "ichor-collector-fred_extended.timer is active"
            ),
        )

    obs_date, spread_pct = row
    spread_bps = spread_pct * 100
    regime = _classify_regime(spread_pct)

    note = (
        f"yield_curve · T10Y2Y={spread_pct:+.4f}% (= {spread_bps:+.1f} bps) "
        f"on {obs_date.isoformat()} regime={regime}"
    )

    fired = False
    if spread_pct <= DEEP_INVERSION_FLOOR_PCT and persist:
        await check_metric(
            session,
            metric_name="t10y2y_spread_pct",
            current_value=spread_pct,
            asset=None,  # macro-broad recession signal
            extra_payload={
                "spread_pct": spread_pct,
                "spread_bps": spread_bps,
                "observation_date": obs_date.isoformat(),
                "regime": regime,
                "is_severe": spread_pct <= SEVERE_INVERSION_FLOOR_PCT,
                "source": f"FRED:{T10Y2Y_SERIES_ID}",
            },
        )
        fired = True

    return YieldCurveInversionResult(
        spread_pct=round(spread_pct, 4),
        spread_bps=round(spread_bps, 2),
        observation_date=obs_date,
        regime=regime,
        alert_fired=fired,
        note=note,
    )
