"""recent_actuals -- query economic_events with published `actual` + classify.

r145 (ADR-099 §Impl) -- closes Mission centrale axis-5 user-surface visibility :
r144 lit the `actual` column for US tier-1 events via FRED ALFRED ; r145
surfaces those rows on `/briefing/[asset]` with the r141 5-state classifier
wired as the API truth-source.

Pure compute + ORM read. Wires `classify_surprise()` (dormant since r141)
as the single API truth-source : today `state=unavailable` for all events
(no analyst range provider live yet) but `magnitude_pct` is computed via
the consensus point estimate (FF `forecast` column), preserving useful
"how far from consensus" info. When the r146+ range provider lands, state
badges auto-light up without API/frontend changes.

ADR-017 compliance : the classifier produces descriptive geometric labels
(`above_range`, `below_range`, `in_range`, `exact_consensus`, `unavailable`)
+ signed `magnitude_pct` -- never directional. Per-asset transmission lives
in verdict/confluence layers (see `MacroSurprisePanel.tsx:151-154` doctrine).

Doctrine #11 calibrated honesty : `unavailable` rows surface raw values
silently (a11y aria-label only -- no fabricated badge). Lesson #37 :
DEMOTE framing when upstream data lacks actionable field (range provider
not yet wired -> classifier state cannot fire -> magnitude only).

ADR refs : ADR-099 §Impl(r145) -- Mission centrale Axis-5 visible surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import EconomicEvent
from .economic_event_surprise import SurpriseClassification, classify_surprise

__all__ = [
    "RecentActualRow",
    "fetch_recent_actuals",
]


@dataclass(frozen=True)
class RecentActualRow:
    """A single past economic event with published `actual` + classification.

    Pairs the raw text columns (display-ready, no fabrication when None)
    with the `classify_surprise()` result. Both layers are exposed so the
    frontend can show raw values AND the classifier verdict side-by-side
    (parity with `MacroSurprisePanel` raw z + magnitude pattern).

    Attributes :
        event_id        : UUID stringified -- React key, never displayed.
        currency        : 3-letter ISO ("USD", "EUR", etc.).
        scheduled_at    : event firing time (UTC, ISO 8601) ; never None
                          here because we filter `scheduled_at IS NOT NULL`.
        title           : ForexFactory event title verbatim.
        impact          : FF impact tier ("high", "medium", "low").
        actual          : raw text from DB, never None here (filtered).
        forecast        : raw consensus point text (may be None).
        forecast_min    : raw envelope lower bound (NULL today, r146+).
        forecast_max    : raw envelope upper bound (NULL today, r146+).
        previous        : raw prior period value text (may be None).
        url             : ForexFactory event detail URL (may be None).
        classification  : `SurpriseClassification` from r141 classifier.
    """

    event_id: str
    currency: str
    scheduled_at: datetime
    title: str
    impact: str
    actual: str
    forecast: str | None
    forecast_min: str | None
    forecast_max: str | None
    previous: str | None
    url: str | None
    classification: SurpriseClassification


async def fetch_recent_actuals(
    session: AsyncSession,
    *,
    lookback_days: int = 30,
    currency: str | None = "USD",
    limit: int = 25,
    now: datetime | None = None,
) -> list[RecentActualRow]:
    """Fetch past N-day economic events with published `actual` + classify.

    Args :
        session        : SQLAlchemy async session.
        lookback_days  : how many days back to scan (default 30 -- matches
                         r144 reconciler default window).
        currency       : ISO currency filter ("USD" default to match the
                         only populated bucket today via r144). Pass None
                         to skip filter (returns all currencies).
        limit          : cap rows returned (default 25, max 200). Newest
                         events first by `scheduled_at DESC`.
        now            : injection point for deterministic testing. Default
                         `datetime.now(UTC)`.

    Returns rows newest-first. Each row carries both raw text + classifier
    verdict so the frontend can render raw values + magnitude_pct token
    even when `state=unavailable` (no range data yet).

    Never raises -- empty list on no matches. ORM query only, no I/O.
    """
    if now is None:
        now = datetime.now(UTC)
    if limit < 0:
        limit = 0
    # Hard cap defensive against caller passing huge `limit` via query
    # string -- /v1 router will pre-validate via `Query(le=200)` but the
    # service layer also clamps as belt-and-suspenders (parity with
    # `economic_event_actuals_reconciler` r144 defensive clamps).
    limit = min(limit, 200)
    lookback_floor = now - timedelta(days=max(lookback_days, 0))

    stmt = (
        select(EconomicEvent)
        .where(
            EconomicEvent.scheduled_at.is_not(None),
            EconomicEvent.scheduled_at >= lookback_floor,
            EconomicEvent.scheduled_at <= now,
            EconomicEvent.actual.is_not(None),
        )
        .order_by(EconomicEvent.scheduled_at.desc())
        .limit(limit)
    )
    if currency is not None:
        stmt = stmt.where(EconomicEvent.currency == currency)

    rows = (await session.execute(stmt)).scalars().all()

    result: list[RecentActualRow] = []
    for r in rows:
        # Defensive null-guard -- filtered above but mypy can't see the SQL
        # predicate. If schema invariants ever weaken, the runtime check
        # keeps us honest rather than emitting a half-broken row.
        if r.scheduled_at is None or r.actual is None:
            continue
        classification = classify_surprise(
            actual=r.actual,
            consensus=r.forecast,
            forecast_min=r.forecast_min,
            forecast_max=r.forecast_max,
        )
        result.append(
            RecentActualRow(
                event_id=str(r.id),
                currency=r.currency,
                scheduled_at=r.scheduled_at,
                title=r.title,
                impact=r.impact,
                actual=r.actual,
                forecast=r.forecast,
                forecast_min=r.forecast_min,
                forecast_max=r.forecast_max,
                previous=r.previous,
                url=r.url,
                classification=classification,
            )
        )
    return result
