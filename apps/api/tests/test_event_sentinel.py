"""S03 Chantier D — pre-announcement event sentinel tests.

Mock-session based (mirror of test_scenario_invalidation_alerts):
clustering by (currency, minute), event-level dedup via payload
event_key, quiet-calendar honesty, catalog wiring.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from ichor_api.alerts.catalog import BY_CODE
from ichor_api.alerts.event_sentinel import (
    RELEVANT_CURRENCIES,
    _event_cluster_key,
    evaluate_upcoming_event_hits,
)
from ichor_api.models import EconomicEvent

NOW = datetime(2026, 6, 11, 11, 40, tzinfo=UTC)  # 13:40 Paris
ECB_AT = datetime(2026, 6, 11, 12, 15, tzinfo=UTC)  # 14:15 Paris
PPI_AT = datetime(2026, 6, 11, 12, 30, tzinfo=UTC)  # 14:30 Paris


def _event(title: str, currency: str, at: datetime, forecast: str | None = None) -> EconomicEvent:
    return EconomicEvent(
        currency=currency,
        scheduled_at=at,
        is_all_day=False,
        title=title,
        impact="high",
        forecast=forecast,
        previous=None,
        url=None,
        source="forex_factory",
        fetched_at=NOW,
    )


def _session(events: list[EconomicEvent], alerted_payloads: list[dict]) -> MagicMock:
    """Mock the two execute() calls: events select, then alerted-keys select."""
    events_result = MagicMock()
    events_result.scalars.return_value.all.return_value = events
    alerted_result = MagicMock()
    alerted_result.all.return_value = [(p,) for p in alerted_payloads]
    session = MagicMock()
    session.execute = AsyncMock(side_effect=[events_result, alerted_result])
    return session


# ── catalog wiring ────────────────────────────────────────────────────


def test_eco_event_imminent_in_catalog_critical() -> None:
    d = BY_CODE["ECO_EVENT_IMMINENT"]
    assert d.severity == "critical"  # web-push tier
    assert d.crisis_mode is False
    assert d.metric_name == "event_minutes_until"


def test_relevant_currencies_cover_traded_universe() -> None:
    # EURUSD, GBPUSD, USDCAD, XAUUSD, NAS100, SPX500 — USD drives all six.
    assert RELEVANT_CURRENCIES == {"USD", "EUR", "GBP", "CAD"}


def test_cluster_key_minute_stable() -> None:
    assert _event_cluster_key("USD", PPI_AT) == "USD@2026-06-11T12:30Z"


# ── evaluation ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_quiet_calendar_returns_empty() -> None:
    session = _session([], [])
    hits = await evaluate_upcoming_event_hits(session, now_utc=NOW)
    assert hits == []
    # Honesty: no second query when nothing upcoming.
    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_same_minute_cluster_is_one_alert() -> None:
    events = [
        _event("PPI m/m", "USD", PPI_AT, forecast="0.2%"),
        _event("Core PPI m/m", "USD", PPI_AT),
    ]
    session = _session(events, [])
    hits = await evaluate_upcoming_event_hits(session, now_utc=NOW)
    assert len(hits) == 1
    hit, currency = hits[0]
    assert currency == "USD"
    assert hit.source_payload["n_events"] == 2
    assert hit.source_payload["event_key"] == "USD@2026-06-11T12:30Z"
    assert hit.source_payload["consensus"] == "0.2%"
    assert "PPI m/m" in hit.source_payload["titles"]
    assert hit.metric_value == 50.0  # 11:40 → 12:30


@pytest.mark.asyncio
async def test_distinct_clusters_alert_separately() -> None:
    events = [
        _event("Main Refinancing Rate", "EUR", ECB_AT),
        _event("PPI m/m", "USD", PPI_AT),
    ]
    session = _session(events, [])
    hits = await evaluate_upcoming_event_hits(session, now_utc=NOW)
    assert len(hits) == 2
    keys = {h.source_payload["event_key"] for h, _ in hits}
    assert keys == {"EUR@2026-06-11T12:15Z", "USD@2026-06-11T12:30Z"}


@pytest.mark.asyncio
async def test_already_alerted_cluster_skipped() -> None:
    """Event-level dedup: a 14:30 USD alert already persisted must not
    re-fire, but a NEW 16:00 cluster on the same currency MUST (the
    generic 2h (code, asset) window would have masked it)."""
    events = [
        _event("PPI m/m", "USD", PPI_AT),
        _event("Retail Sales", "USD", datetime(2026, 6, 11, 12, 39, tzinfo=UTC)),
    ]
    session = _session(events, [{"event_key": "USD@2026-06-11T12:30Z"}])
    hits = await evaluate_upcoming_event_hits(session, now_utc=NOW)
    assert len(hits) == 1
    assert hits[0][0].source_payload["event_key"] == "USD@2026-06-11T12:39Z"


@pytest.mark.asyncio
async def test_paris_local_time_in_payload() -> None:
    session = _session([_event("ECB Press Conference", "EUR", ECB_AT)], [])
    hits = await evaluate_upcoming_event_hits(session, now_utc=NOW)
    assert hits[0][0].source_payload["local_paris"] == "14:15"


@pytest.mark.asyncio
async def test_all_day_events_excluded_from_query() -> None:
    """All-day high-impact events carry a placeholder 00:00 UTC scheduled_at,
    not a real release time → a T-60 'imminent' pre-announce would fire at the
    wrong moment. The query must carry the is_all_day=False predicate (the DB
    does the filtering; this guards against the predicate being dropped). They
    stay covered by _section_today_schedule. S03 audit 2026-06-19."""
    session = _session([], [])
    await evaluate_upcoming_event_hits(session, now_utc=NOW)
    stmt = session.execute.call_args_list[0].args[0]
    compiled = str(stmt.compile())
    assert "is_all_day" in compiled
