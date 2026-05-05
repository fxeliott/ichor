"""ForexFactory economic calendar collector.

Pulls the weekly FX/macro economic events feed (NFP, CPI, FOMC, ECB,
PMI, retail sales, ...) with consensus forecast + previous value.

Source : the public XML feed published by FairEconomy at
  https://nfs.faireconomy.media/ff_calendar_thisweek.xml
  (FairEconomy mirrors ForexFactory's calendar as a free no-API-key XML
  feed, stable since 2014. ForexFactory's own /calendar.php is dynamic
  HTML and requires JS rendering — not used here.)

Schema (per <event> :
  <title>      free-text label, e.g. "Non-Farm Employment Change"
  <country>    ISO currency code, e.g. "USD" / "EUR" / "GBP"
  <date>       MM-DD-YYYY (US ordering — the feed is American-published)
  <time>       "8:30am" / "All Day" / "Tentative"
  <impact>     "Low" / "Medium" / "High" / "Holiday"
  <forecast>   consensus, may be empty
  <previous>   previous reading, may be empty
  <url>        deep link back to forexfactory.com event page

Uses defusedxml to neutralize XML-bomb / entity-expansion attacks before
the body flows into the brain prompt context.

PERSISTENCE — `economic_events` table provisioned by migration 0019
(natural key on currency + scheduled_at + title). `persist_events`
performs ON CONFLICT DO UPDATE so consensus revisions land idempotently.
Cron registered in `scripts/hetzner/register-cron-collectors-extended.sh`
at 03/09/15/21h Paris (4×/day to catch forecast updates).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time
from typing import Literal

import httpx
from defusedxml.ElementTree import fromstring as defused_fromstring

FF_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"

ImpactLevel = Literal["low", "medium", "high", "holiday"]


@dataclass(frozen=True)
class EconomicEvent:
    """One row of the FF weekly calendar, normalized to UTC."""

    title: str
    currency: str
    impact: ImpactLevel
    scheduled_at: datetime | None
    """None if the event is `All Day` or has no time component."""
    is_all_day: bool
    forecast: str | None
    previous: str | None
    url: str | None


_IMPACT_MAP: dict[str, ImpactLevel] = {
    "low": "low",
    "medium": "medium",
    "high": "high",
    "holiday": "holiday",
    "non-economic": "holiday",
}


def _parse_impact(raw: str | None) -> ImpactLevel:
    s = (raw or "").strip().lower()
    return _IMPACT_MAP.get(s, "low")


def _parse_time(raw: str | None) -> tuple[time | None, bool]:
    """Returns (parsed_time, is_all_day).

    The feed uses "8:30am", "12:00pm", "All Day", "Tentative", or empty.
    Returns `(None, True)` for "All Day", `(None, False)` for tentative
    or empty.
    """
    s = (raw or "").strip().lower()
    if not s:
        return None, False
    if "all day" in s or "tentative" in s:
        return None, "all day" in s
    # Strict 12-hour format, e.g. "8:30am" or "12:05pm".
    try:
        return (
            datetime.strptime(s.replace(" ", ""), "%I:%M%p").replace(tzinfo=UTC).time(),
            False,
        )
    except ValueError:
        return None, False


def _parse_date(raw: str | None) -> datetime | None:
    """FF feed uses MM-DD-YYYY (US ordering)."""
    s = (raw or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%m-%d-%Y").replace(tzinfo=UTC)
    except ValueError:
        return None


def parse_ff_calendar(xml_body: str) -> list[EconomicEvent]:
    """Parse the FairEconomy/ForexFactory weekly XML feed.

    Args:
        xml_body: Raw XML text. Parsed with defusedxml.

    Returns:
        Newest-first list of normalized EconomicEvent. Rows whose date
        cannot be parsed are dropped (logged upstream by the caller).
    """
    root = defused_fromstring(xml_body)
    out: list[EconomicEvent] = []
    for ev in root.findall("event"):
        date_el = ev.find("date")
        time_el = ev.find("time")
        date_part = _parse_date(date_el.text if date_el is not None else None)
        time_part, is_all_day = _parse_time(time_el.text if time_el is not None else None)
        scheduled: datetime | None = None
        if date_part is not None and time_part is not None:
            scheduled = datetime.combine(date_part.date(), time_part, tzinfo=UTC)
        elif date_part is not None and is_all_day:
            scheduled = date_part  # 00:00 UTC of the day

        title = (ev.findtext("title") or "").strip()
        country = (ev.findtext("country") or "").strip().upper()
        if not title or not country:
            continue
        out.append(
            EconomicEvent(
                title=title,
                currency=country,
                impact=_parse_impact(ev.findtext("impact")),
                scheduled_at=scheduled,
                is_all_day=is_all_day,
                forecast=(ev.findtext("forecast") or "").strip() or None,
                previous=(ev.findtext("previous") or "").strip() or None,
                url=(ev.findtext("url") or "").strip() or None,
            )
        )
    out.sort(key=lambda e: (e.scheduled_at or datetime.max.replace(tzinfo=UTC), e.title))
    return out


async def fetch_ff_calendar(
    client: httpx.AsyncClient | None = None,
    *,
    url: str = FF_CALENDAR_URL,
    timeout_s: float = 20.0,
) -> list[EconomicEvent]:
    """Async fetch + parse the weekly calendar.

    Caller-owned client supports test mocking + connection pooling. If
    not provided, a one-shot client is created with `timeout_s`.
    """
    if client is None:
        async with httpx.AsyncClient(timeout=timeout_s) as c:
            resp = await c.get(url)
    else:
        resp = await client.get(url, timeout=timeout_s)
    resp.raise_for_status()
    return parse_ff_calendar(resp.text)


async def persist_events(
    session,  # type: ignore[no-untyped-def]  # AsyncSession (avoid heavy import at module scope)
    events: list[EconomicEvent],
) -> int:
    """Upsert events into `economic_events` via PostgreSQL ON CONFLICT.

    Dedup key is (currency, scheduled_at, title) — see migration 0019.
    Returns the number of rows touched (insert + update). The session is
    flushed but not committed ; callers (cron runners, tests) own the
    transaction boundary.

    Behavior on conflict : forecast / previous / url / fetched_at are
    refreshed (ForexFactory revises consensus through the week). The
    immutable fields (currency, scheduled_at, title) are part of the
    natural key so they are never touched by an UPDATE.
    """
    if not events:
        return 0
    from datetime import UTC, datetime

    from sqlalchemy.dialects.postgresql import insert

    from ..models import EconomicEvent as Row

    now = datetime.now(UTC)
    payload = [
        {
            "currency": e.currency,
            "scheduled_at": e.scheduled_at,
            "is_all_day": e.is_all_day,
            "title": e.title,
            "impact": e.impact,
            "forecast": e.forecast,
            "previous": e.previous,
            "url": e.url,
            "source": "forex_factory",
            "fetched_at": now,
        }
        for e in events
    ]
    stmt = insert(Row).values(payload)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_economic_events_natural_key",
        set_={
            "is_all_day": stmt.excluded.is_all_day,
            "impact": stmt.excluded.impact,
            "forecast": stmt.excluded.forecast,
            "previous": stmt.excluded.previous,
            "url": stmt.excluded.url,
            "fetched_at": stmt.excluded.fetched_at,
        },
    )
    result = await session.execute(stmt)
    await session.flush()
    return int(result.rowcount or 0)
