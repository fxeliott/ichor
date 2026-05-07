"""QUAD_WITCHING + OPEX_GAMMA_PEAK alerts (Phase D.5.e).

Two date-driven alerts that don't depend on any data source — they
just compute upcoming option-expiry calendar events and flag
proximity (next session through to today) :

- **QUAD_WITCHING** : the four annual Fridays when stock-index
  futures, single-stock futures, stock-index options, and
  single-stock options ALL expire simultaneously. These are the
  3rd Friday of March / June / September / December. Volume
  doubles or triples ; gamma re-pricing risks; intraday volatility
  pops. SPX gamma exposure pivots particularly in the AM session.
  Cadence : 4 times per year.

- **OPEX_GAMMA_PEAK** : monthly options expiration on the 3rd
  Friday of EVERY month. Less violent than quad witching but the
  same gamma-unwind dynamics on a smaller scale. Worth flagging
  T-1 so Eliot anticipates the dealer-positioning shift on
  Friday morning.

Both are pure Python date math — no DB query, no external API.
Idempotent : running the check twice on the same day produces the
same alert state.

Source-stamping (ADR-017) : `extra_payload.source = "calendar:third_friday"`
+ explicit `event_date` and `days_to_event` so Eliot can re-derive.

Threshold semantics :
  - QUAD_WITCHING : fires when 0 <= days_to_event <= 5 (T-5 through T-0)
  - OPEX_GAMMA_PEAK : fires when 0 <= days_to_event <= 2 (T-2 through T-0)
  - Outside those windows, no-op.

ADR-035.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from .alerts_runner import check_metric

# Catalog floor (kept in sync with AlertDef.default_threshold).
QUAD_WITCHING_FLOOR_DAYS: int = 5
OPEX_FLOOR_DAYS: int = 2

# Quad-witching months (3rd Friday of these).
_QUAD_MONTHS: tuple[int, ...] = (3, 6, 9, 12)


def _third_friday(year: int, month: int) -> date:
    """Return the 3rd Friday of (year, month).

    Walks from day 1 forward to the first Friday, then adds 14 days.
    Friday = weekday() == 4.
    """
    d = date(year, month, 1)
    # Move forward to the first Friday in that month.
    while d.weekday() != 4:
        d += timedelta(days=1)
    # First Friday + 14 = third Friday.
    return d + timedelta(days=14)


def next_quad_witching(today: date) -> date:
    """The next quad-witching date >= `today`.

    Scans the current and next year (8 dates) and returns the earliest
    one not yet past.
    """
    candidates: list[date] = []
    for y in (today.year, today.year + 1):
        for m in _QUAD_MONTHS:
            qw = _third_friday(y, m)
            if qw >= today:
                candidates.append(qw)
    candidates.sort()
    if not candidates:  # pragma: no cover — only happens on year overflow
        raise RuntimeError(f"No quad-witching date found for year {today.year}")
    return candidates[0]


def next_opex(today: date) -> date:
    """The next monthly OPEX (3rd Friday of any month) >= `today`.

    If today's month's 3rd Friday is already past, returns next
    month's 3rd Friday.
    """
    qw = _third_friday(today.year, today.month)
    if qw >= today:
        return qw
    # Roll into next month.
    next_year = today.year + (1 if today.month == 12 else 0)
    next_month = 1 if today.month == 12 else today.month + 1
    return _third_friday(next_year, next_month)


@dataclass(frozen=True)
class WitchingProximityResult:
    today: date
    next_quad_date: date
    days_to_quad: int
    next_opex_date: date
    days_to_opex: int
    is_quad_witching_window: bool
    is_opex_window: bool
    quad_witching_alert_fired: bool
    opex_alert_fired: bool


async def evaluate_quad_witching_proximity(
    session: AsyncSession,
    *,
    persist: bool = True,
    today: date | None = None,
) -> WitchingProximityResult:
    """Compute days-to-quad-witching and days-to-monthly-OPEX, fire the
    catalog alerts when within the proximity windows.

    `today` is overridable for testability — defaults to UTC now().date().
    """
    today = today or datetime.now(UTC).date()

    qw = next_quad_witching(today)
    opex = next_opex(today)
    days_to_qw = (qw - today).days
    days_to_opex = (opex - today).days

    in_qw_window = 0 <= days_to_qw <= QUAD_WITCHING_FLOOR_DAYS
    in_opex_window = 0 <= days_to_opex <= OPEX_FLOOR_DAYS

    qw_fired = False
    opex_fired = False

    if persist and in_qw_window:
        await check_metric(
            session,
            metric_name="quad_witching_t_minus",
            current_value=float(days_to_qw),
            asset="SPX500_USD",  # quad-witching is most material on US index futures
            extra_payload={
                "event_date": qw.isoformat(),
                "days_to_event": days_to_qw,
                "event_type": "quad_witching",
                "source": "calendar:third_friday",
            },
        )
        qw_fired = True

    if persist and in_opex_window:
        await check_metric(
            session,
            metric_name="opex_t_minus",
            current_value=float(days_to_opex),
            asset="SPX500_USD",
            extra_payload={
                "event_date": opex.isoformat(),
                "days_to_event": days_to_opex,
                "event_type": "monthly_opex",
                "source": "calendar:third_friday",
            },
        )
        opex_fired = True

    return WitchingProximityResult(
        today=today,
        next_quad_date=qw,
        days_to_quad=days_to_qw,
        next_opex_date=opex,
        days_to_opex=days_to_opex,
        is_quad_witching_window=in_qw_window,
        is_opex_window=in_opex_window,
        quad_witching_alert_fired=qw_fired,
        opex_alert_fired=opex_fired,
    )
