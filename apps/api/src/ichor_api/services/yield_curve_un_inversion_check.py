"""YIELD_CURVE_UN_INVERSION_EVENT alert wiring (Phase E innovation).

Sister alert to YIELD_CURVE_INVERSION_DEEP (ADR-046). Where the deep-
inversion alert flags WHEN the curve is inverted, this companion flags
the **un-inversion event** — the moment when T10Y2Y crosses back from
negative (inverted) to positive (normal) territory.

**Why this is the more important signal** (per Cleveland Fed +
NY Fed research) :

  - Every yield curve inversion since 1976 preceded a US recession
    (median lag 14 months).
  - But recessions don't START during inversion — they typically begin
    AFTER the spread has un-inverted (re-steepened to positive).
  - The un-inversion signals the market expects the Fed to ease
    aggressively, which historically coincides with recession onset
    or early recovery.
  - Counterintuitive timing : the longer-watched "inversion" is the
    early warning ; the un-inversion is the imminent-recession trigger.

Example timeline (2022-2025) :
  - Jul 2022 : T10Y2Y first inverts (warning fired by sister alert)
  - Aug 2024 : T10Y2Y un-inverts back to 0+ (THIS alert would fire)
  - The 2022-2024 inversion lasted 25 months — longest in FRED series.
  - April 2026 : T10Y2Y +49 bps confirmed normalized (current state).

The 2022-2024 episode is the SECOND-deepest inversion since the 1980s
(-108 bps trough). Its un-inversion in mid-2024 has not been followed
by recession yet — anomaly under debate ("this time is different",
fiscal impulse + AI productivity gains argument).

Alert mechanics (cross_up event detection) :

  1. Fetch last N days of T10Y2Y observations.
  2. Detect if today's spread > 0.0 AND any day in the prior 60d window
     had spread <= -0.30 (deep enough inversion to qualify).
  3. Detect cross-up event : previous < 0 AND current > 0 (yesterday
     vs today direct comparison).
  4. Fire YIELD_CURVE_UN_INVERSION_EVENT with both signals.

Source-stamping (ADR-017) :
  - extra_payload.source = "FRED:T10Y2Y"
  - extra_payload includes current spread, previous spread, max
    inversion depth in 60d window, days since deepest

ROADMAP E innovations. ADR-047.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import FredObservation
from .alerts_runner import check_metric

T10Y2Y_SERIES_ID = "T10Y2Y"

# Catalog threshold semantic : count of confirmation conditions met.
# = 1 if cross-up event happened today (yesterday ≤ 0, today > 0)
# = 2 if cross-up + 60d window had deep inversion <= -0.30
# Threshold = 1 fires on any cross-up ; threshold = 2 (used here) fires
# only on confirmed post-inversion un-inversion.
ALERT_CONDITIONS_FLOOR: int = 2

# Window to look back for "was deeply inverted" confirmation.
LOOKBACK_DAYS = 60

# Depth required for confirmation. -0.30 (= -30 bps) ensures the prior
# inversion was meaningful, not a transient zero-crossing.
DEEP_INVERSION_DEPTH_PCT: float = -0.30


@dataclass(frozen=True)
class UnInversionResult:
    """One run summary."""

    current_spread_pct: float | None
    previous_spread_pct: float | None
    """Yesterday's spread for cross_up detection."""

    max_inversion_depth_60d: float | None
    """Most negative T10Y2Y reading in last 60d. None if no data."""

    days_since_deepest: int | None
    """Days between deepest 60d inversion and today."""

    cross_up_today: bool
    deep_inversion_in_window: bool
    n_conditions_met: int
    alert_fired: bool
    note: str = ""


async def _fetch_recent_history(
    session: AsyncSession, *, days: int
) -> list[tuple[date, float]]:
    """Last `days` non-null T10Y2Y observations, oldest-first."""
    cutoff = datetime.now(UTC).date() - timedelta(days=days)
    stmt = (
        select(FredObservation.observation_date, FredObservation.value)
        .where(
            FredObservation.series_id == T10Y2Y_SERIES_ID,
            FredObservation.observation_date >= cutoff,
            FredObservation.value.is_not(None),
        )
        .order_by(desc(FredObservation.observation_date))
    )
    rows = list((await session.execute(stmt)).all())
    rows.reverse()
    return [(r[0], float(r[1])) for r in rows if r[1] is not None]


async def evaluate_yield_curve_un_inversion(
    session: AsyncSession,
    *,
    persist: bool = True,
) -> UnInversionResult:
    """Detect cross-up un-inversion event with deep-inversion confirmation
    in 60d window. Fire YIELD_CURVE_UN_INVERSION_EVENT when both
    conditions met.
    """
    rows = await _fetch_recent_history(session, days=LOOKBACK_DAYS + 5)

    if len(rows) < 2:
        return UnInversionResult(
            current_spread_pct=None,
            previous_spread_pct=None,
            max_inversion_depth_60d=None,
            days_since_deepest=None,
            cross_up_today=False,
            deep_inversion_in_window=False,
            n_conditions_met=0,
            alert_fired=False,
            note=(
                f"insufficient T10Y2Y data ({len(rows)} rows) — verify "
                f"ichor-collector-fred_extended.timer is active"
            ),
        )

    today_date, current_spread = rows[-1]
    yesterday_date, previous_spread = rows[-2]

    # Find deepest inversion in last 60d (excluding today)
    history_60d = rows[:-1][-LOOKBACK_DAYS:]
    if history_60d:
        max_inv_idx = min(range(len(history_60d)), key=lambda i: history_60d[i][1])
        max_inv_date, max_inv_value = history_60d[max_inv_idx]
        days_since_deepest = (today_date - max_inv_date).days
    else:
        max_inv_value = None
        days_since_deepest = None

    cross_up_today = (previous_spread <= 0.0) and (current_spread > 0.0)
    deep_inversion_in_window = (
        max_inv_value is not None and max_inv_value <= DEEP_INVERSION_DEPTH_PCT
    )
    n_conditions = (1 if cross_up_today else 0) + (
        1 if deep_inversion_in_window else 0
    )

    note = (
        f"yield_curve_un_inv · today={current_spread:+.4f}% (yesterday "
        f"{previous_spread:+.4f}%) max_inv_60d={max_inv_value} "
        f"cross_up={cross_up_today} deep_in_window={deep_inversion_in_window} "
        f"conditions={n_conditions}/2"
    )

    fired = False
    if n_conditions >= ALERT_CONDITIONS_FLOOR and persist:
        await check_metric(
            session,
            metric_name="yield_curve_un_inversion_conditions",
            current_value=float(n_conditions),
            asset=None,
            extra_payload={
                "current_spread_pct": current_spread,
                "current_spread_bps": current_spread * 100,
                "previous_spread_pct": previous_spread,
                "max_inversion_depth_60d_pct": max_inv_value,
                "max_inversion_depth_60d_bps": (
                    max_inv_value * 100 if max_inv_value is not None else None
                ),
                "days_since_deepest_in_window": days_since_deepest,
                "cross_up_today": cross_up_today,
                "deep_inversion_in_window": deep_inversion_in_window,
                "today_date": today_date.isoformat(),
                "source": f"FRED:{T10Y2Y_SERIES_ID}",
            },
        )
        fired = True

    return UnInversionResult(
        current_spread_pct=round(current_spread, 4),
        previous_spread_pct=round(previous_spread, 4),
        max_inversion_depth_60d=(
            round(max_inv_value, 4) if max_inv_value is not None else None
        ),
        days_since_deepest=days_since_deepest,
        cross_up_today=cross_up_today,
        deep_inversion_in_window=deep_inversion_in_window,
        n_conditions_met=n_conditions,
        alert_fired=fired,
        note=note,
    )
