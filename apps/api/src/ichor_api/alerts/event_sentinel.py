"""S03 Chantier D — pre-announcement sentinel for high-impact calendar events.

The spec's "être prévenu de TOUTES les annonces susceptibles d'influencer
les trades" was REACTIVE-only as-built: `streaming_refresh` reacts AFTER
a result lands, `recent_actuals` feeds the LLM AFTER publication, but
nothing warned the trader BEFORE a high-impact print. This module closes
the proactive half: a 10-min cron scans `economic_events` for high-impact
events inside the next horizon (default 60 min) on the currencies that
drive the traded universe, and emits one `ECO_EVENT_IMMINENT` alert per
(currency, time-slot) cluster through the canonical pipeline.

Severity is `critical` deliberately: a high-impact announcement < 60 min
away is exactly the "must not miss" class, and `critical` is the tier the
web-push channel forwards (`alerts_runner._NOTIFY_SEVERITIES`). ADR-017
boundary: the alert DESCRIBES the calendar (what / when / consensus),
never a direction or an order.

Dedup is EVENT-level, not the generic 2h (code, asset) window: a
14:30 USD cluster must not mask a 16:00 USD event. Each alert's
`source_payload.event_key` records the cluster it covered; the query
side skips clusters already alerted (lookback 26h covers the horizon).

Timezone note (verified against prod 2026-06-11): `scheduled_at` is
tz-aware and CORRECT — US CPI stored `14:30+02` = 08:30 ET, BoC
`15:45+02` = 09:45 ET. The minutes_until arithmetic is safe.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Alert, EconomicEvent
from .catalog import get_alert_def
from .evaluator import AlertHit

log = structlog.get_logger(__name__)

# Currencies whose prints move the traded universe (EURUSD, GBPUSD,
# USDCAD, XAUUSD, NAS100, SPX500 — Eliot's 6). USD drives all six; CHF/JPY
# left out: USD_JPY is deprioritised and CHF prints are second-order here.
RELEVANT_CURRENCIES: frozenset[str] = frozenset({"USD", "EUR", "GBP", "CAD"})

DEFAULT_HORIZON_MINUTES = 60


def _event_cluster_key(currency: str, scheduled_at: datetime) -> str:
    """Stable id for one (currency, time-slot) cluster — e.g.
    ``USD@2026-06-11T12:30Z``. Several prints at the same minute (CPI m/m
    + y/y + core) are ONE warning."""
    return f"{currency}@{scheduled_at.astimezone(UTC):%Y-%m-%dT%H:%MZ}"


async def _already_alerted_keys(session: AsyncSession, *, now_utc: datetime) -> set[str]:
    cutoff = now_utc - timedelta(hours=26)
    stmt = select(Alert.source_payload).where(
        Alert.alert_code == "ECO_EVENT_IMMINENT",
        Alert.triggered_at >= cutoff,
    )
    keys: set[str] = set()
    for (payload,) in (await session.execute(stmt)).all():
        if payload and payload.get("event_key"):
            keys.add(str(payload["event_key"]))
    return keys


async def evaluate_upcoming_event_hits(
    session: AsyncSession,
    *,
    now_utc: datetime | None = None,
    horizon_minutes: int = DEFAULT_HORIZON_MINUTES,
) -> list[tuple[AlertHit, str]]:
    """Return ``(hit, asset)`` pairs for un-alerted high-impact clusters
    inside ``[now, now + horizon]``. ``asset`` carries the currency (the
    catalog precedent for non-instrument asset tags: COT market codes).

    Calibrated honesty: returns ``[]`` when the window is empty — no
    fabricated "calendar quiet" noise.
    """
    now = (now_utc or datetime.now(UTC)).astimezone(UTC)
    horizon_end = now + timedelta(minutes=horizon_minutes)

    stmt = (
        select(EconomicEvent)
        .where(
            EconomicEvent.impact == "high",
            EconomicEvent.currency.in_(sorted(RELEVANT_CURRENCIES)),
            EconomicEvent.scheduled_at.is_not(None),
            EconomicEvent.scheduled_at > now,
            EconomicEvent.scheduled_at <= horizon_end,
        )
        .order_by(EconomicEvent.scheduled_at.asc())
    )
    events = list((await session.execute(stmt)).scalars().all())
    if not events:
        return []

    alerted = await _already_alerted_keys(session, now_utc=now)

    # Cluster by (currency, minute slot).
    clusters: dict[str, list[EconomicEvent]] = {}
    for ev in events:
        key = _event_cluster_key(ev.currency, ev.scheduled_at)
        clusters.setdefault(key, []).append(ev)

    alert_def = get_alert_def("ECO_EVENT_IMMINENT")
    hits: list[tuple[AlertHit, str]] = []
    for key, evs in clusters.items():
        if key in alerted:
            continue
        first = evs[0]
        minutes_until = max(0.0, (first.scheduled_at - now).total_seconds() / 60.0)
        titles = "; ".join(e.title for e in evs[:4]) + (" …" if len(evs) > 4 else "")
        consensus = next((e.forecast for e in evs if e.forecast), None)
        hits.append(
            (
                AlertHit(
                    alert_def=alert_def,
                    metric_value=round(minutes_until, 0),
                    threshold=float(horizon_minutes),
                    direction_observed="below",
                    source_payload={
                        "event_key": key,
                        "currency": first.currency,
                        "titles": titles,
                        "scheduled_at_utc": first.scheduled_at.astimezone(UTC).isoformat(),
                        "n_events": len(evs),
                        "consensus": consensus,
                        "local_paris": first.scheduled_at.astimezone(UTC)
                        .astimezone(_paris())
                        .strftime("%H:%M"),
                    },
                ),
                first.currency,
            )
        )
    return hits


def _paris():
    from zoneinfo import ZoneInfo

    return ZoneInfo("Europe/Paris")
