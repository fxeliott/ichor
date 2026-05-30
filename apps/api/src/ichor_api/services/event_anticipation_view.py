"""event_anticipation_view — r152 thin view-model wrapper composing
Engine 8's `assess_event_proximity()` (ENGAGED mode) + an upcoming-events
fallback (STANDBY mode) for the `/v1/event-anticipation/{asset}` route.

r152 ADR-099 §Impl (Mission centrale axis-4 +1 LEVEL surface). The Engine 8
backend has shipped since r147 + extended via r149 (AUD/CAD/JPY title
fragments) + r150 (single-source RBA/BoC disclosure + Employment class) +
r152 (PCE/GDP class extension) — but its drift expectation is INVISIBLE on
the user surface (currently mixed with other drivers on the
`<ConvictionGroundingPanel>` 4th tile). r152 ships a DEDICATED panel that
shows the engine's forward-looking output OR the next upcoming events when
the engine is silent.

Three modes :

- "engaged" : `assess_event_proximity()` returns a non-None
  `EventProximityFactor` (event in 48h window, mapped class). Renders the
  full forward-looking drift expectation : countdown + magnitude + direction
  + confidence + caveat + literature anchor.

- "standby" : `assess_event_proximity()` returns None (no event in 48h
  window) BUT `economic_events` has next-3 upcoming high/medium-impact
  events for the asset's relevant currencies. Renders mini-calendar with
  countdowns ; T-48h is when Engine 8 will engage.

- "silent" : no upcoming events in the next 14 days for any of the asset's
  relevant currencies. Empty state with honest disclosure.

ADR-017 boundary preserved : output is DESCRIPTIVE (event title +
magnitude_bp + direction up/down/unknown) ; NEVER imperative ; sign-strip
at UI boundary delegated to frontend view-model.

Pure compute + ORM read, no I/O beyond `AsyncSession`. Voie D (no LLM call).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import EconomicEvent
from .event_proximity_engine import (
    EventProximityFactor,
    _currencies_for_asset,
    _map_title_to_event_class,
    assess_event_proximity,
)

__all__ = [
    "EventAnticipationView",
    "UpcomingEventView",
    "assess_event_anticipation_view",
]


EventAnticipationMode = Literal["engaged", "standby", "silent"]


@dataclass(frozen=True)
class UpcomingEventView:
    """Lightweight per-event projection for STANDBY mode display.

    Subset of `economic_events` columns + computed `minutes_until` + optional
    mapped `event_class`. Pure data shape ; no behaviour.
    """

    event_id: str
    currency: str
    scheduled_at_utc: datetime
    title: str
    impact: Literal["high", "medium"]
    event_class: str | None
    minutes_until: int


@dataclass(frozen=True)
class EventAnticipationView:
    """Composed view : ENGAGED engine output + STANDBY upcoming list + mode.

    Frontend consumes the same shape regardless of mode (engaged/standby/
    silent). The `mode` field is the truth-source ; UI dispatches off it.
    """

    generated_at: datetime
    asset: str
    mode: EventAnticipationMode
    engaged: EventProximityFactor | None
    standby_events: tuple[UpcomingEventView, ...]
    parse_failures: frozenset[str]


_STANDBY_HORIZON_DAYS = 14  # mirrors `/v1/calendar/upcoming` default
_STANDBY_MAX_EVENTS = 3  # cap for panel chrome
_STANDBY_IMPACT_TIERS: tuple[str, ...] = ("high", "medium")  # filter


async def _fetch_standby_events(
    session: AsyncSession,
    *,
    currencies: tuple[str, ...],
    now: datetime,
) -> list[UpcomingEventView]:
    """Query `economic_events` for next N high/medium-impact events for the
    asset's relevant currencies. Used when Engine 8 is silent (no event in
    48h window) — the panel can still surface "next event in N days" instead
    of going blank.

    Sort by `scheduled_at` ascending ; cap N=3 ; honest mapping via
    `_map_title_to_event_class()` so frontend can show event class label.
    """
    if not currencies:
        return []
    horizon_end = now + timedelta(days=_STANDBY_HORIZON_DAYS)
    stmt = (
        select(EconomicEvent)
        .where(EconomicEvent.currency.in_(currencies))
        .where(EconomicEvent.impact.in_(_STANDBY_IMPACT_TIERS))
        .where(EconomicEvent.scheduled_at > now)
        .where(EconomicEvent.scheduled_at < horizon_end)
        .order_by(EconomicEvent.scheduled_at.asc())
        .limit(_STANDBY_MAX_EVENTS)
    )
    rows = (await session.execute(stmt)).scalars().all()
    views: list[UpcomingEventView] = []
    for row in rows:
        # r152 — preserve honest unmapped surface ; frontend renders
        # "Catalyseur non-classé" when event_class is None per r149 honest scope.
        cls = _map_title_to_event_class(row.title)
        scheduled_utc = row.scheduled_at
        if scheduled_utc.tzinfo is None:
            scheduled_utc = scheduled_utc.replace(tzinfo=UTC)
        delta = scheduled_utc - now
        minutes_until = max(0, int(delta.total_seconds() / 60))
        # r150 sentinel discipline : impact must be in {high, medium} per the
        # filter clause above. If a malformed row slipped through (DB CHECK
        # constraint guards this), skip rather than fabricate a value.
        if row.impact not in _STANDBY_IMPACT_TIERS:
            continue
        views.append(
            UpcomingEventView(
                event_id=str(row.id),
                currency=row.currency,
                scheduled_at_utc=scheduled_utc,
                title=row.title,
                impact=row.impact,  # type: ignore[arg-type]
                event_class=cls,
                minutes_until=minutes_until,
            )
        )
    return views


async def assess_event_anticipation_view(
    session: AsyncSession,
    *,
    asset: str,
    now: datetime | None = None,
    business_cycle_sign: int | None = None,
) -> EventAnticipationView:
    """Compose `EventProximityFactor` (ENGAGED) + upcoming-events list
    (STANDBY) into a single shape for the `/v1/event-anticipation/{asset}`
    router.

    Args:
        session: AsyncSession to `ichor` Postgres.
        asset: Ichor asset code, e.g. "EUR_USD" / "USD_CAD" / "XAU_USD".
        now: Optional now-override for testing. Defaults to `datetime.now(UTC)`.
        business_cycle_sign: Forwarded to `assess_event_proximity()`. None
            → engine default +1 expansion with honest caveat.

    Returns:
        EventAnticipationView with `mode` set to "engaged" | "standby" |
        "silent" based on the engine state + DB query.

    Honest scope :
        - "engaged" path uses Engine 8 SINGLE SOURCE (re-runs the engine,
          does NOT read pre-computed Driver from `session_card_audit`).
          Rationale : `Driver.evidence` is a digested string that loses
          the rich `EventProximityFactor` fields needed for the dedicated
          panel (vix_regime_gate, confidence ladder, literature_anchor,
          parse_failures sentinel set).
        - "standby" path queries `economic_events` directly (NOT through
          the r140 `<FreshDataBanner>` polling endpoint, which has
          backward-window semantics distinct from STANDBY's forward-window
          design).
        - "silent" path returns an empty view (NOT a 404) so frontend can
          render an honest empty state with explanatory chrome.
    """
    if now is None:
        now = datetime.now(UTC)

    # Phase 1 — ENGAGED probe : ask Engine 8 if it has anything in 48h window.
    engaged_factor = await assess_event_proximity(
        session,
        asset=asset,
        now=now,
        business_cycle_sign=business_cycle_sign,
    )

    if engaged_factor is not None:
        return EventAnticipationView(
            generated_at=now,
            asset=asset,
            mode="engaged",
            engaged=engaged_factor,
            standby_events=(),
            parse_failures=engaged_factor.parse_failures,
        )

    # Phase 2 — STANDBY probe : engine silent (no event in 48h) but next 14d
    # might have events the user wants to anticipate.
    currencies = _currencies_for_asset(asset)
    standby = await _fetch_standby_events(session, currencies=currencies, now=now)

    if standby:
        return EventAnticipationView(
            generated_at=now,
            asset=asset,
            mode="standby",
            engaged=None,
            standby_events=tuple(standby),
            parse_failures=frozenset(),
        )

    # Phase 3 — SILENT path : nothing in 14d window for this asset's
    # currencies. Genuine quiet period (rare per empirical 9 high+med events
    # per 14d for USD/EUR/GBP in May 2026 — but possible during summer lull
    # or holiday clusters).
    return EventAnticipationView(
        generated_at=now,
        asset=asset,
        mode="silent",
        engaged=None,
        standby_events=(),
        parse_failures=frozenset(),
    )
