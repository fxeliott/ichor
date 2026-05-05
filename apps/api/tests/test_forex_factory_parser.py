"""Pure-function tests for the ForexFactory weekly calendar parser."""

from __future__ import annotations

from datetime import UTC, datetime

from ichor_api.collectors.forex_factory import (
    EconomicEvent,
    _parse_date,
    _parse_impact,
    _parse_time,
    parse_ff_calendar,
)


def test_parse_impact_known_levels() -> None:
    assert _parse_impact("Low") == "low"
    assert _parse_impact("MEDIUM") == "medium"
    assert _parse_impact("High") == "high"
    assert _parse_impact("Holiday") == "holiday"
    assert _parse_impact("Non-Economic") == "holiday"


def test_parse_impact_unknown_falls_back_to_low() -> None:
    assert _parse_impact("") == "low"
    assert _parse_impact(None) == "low"
    assert _parse_impact("Catastrophic") == "low"


def test_parse_time_typical() -> None:
    t, all_day = _parse_time("8:30am")
    assert t is not None
    assert (t.hour, t.minute) == (8, 30)
    assert all_day is False


def test_parse_time_pm() -> None:
    t, all_day = _parse_time("12:05pm")
    assert t is not None
    assert (t.hour, t.minute) == (12, 5)
    assert all_day is False


def test_parse_time_all_day() -> None:
    t, all_day = _parse_time("All Day")
    assert t is None
    assert all_day is True


def test_parse_time_tentative_or_empty() -> None:
    assert _parse_time("Tentative") == (None, False)
    assert _parse_time("") == (None, False)
    assert _parse_time(None) == (None, False)


def test_parse_date_us_ordering() -> None:
    d = _parse_date("05-04-2026")
    assert d is not None
    assert (d.year, d.month, d.day) == (2026, 5, 4)
    assert d.tzinfo is UTC


def test_parse_date_invalid() -> None:
    assert _parse_date("") is None
    assert _parse_date(None) is None
    assert _parse_date("2026-05-04") is None  # ISO ordering rejected — feed is US-only


_SAMPLE_XML = """<?xml version="1.0" encoding="utf-8"?>
<weeklyevents>
  <event>
    <title>Non-Farm Employment Change</title>
    <country>USD</country>
    <date>05-08-2026</date>
    <time>8:30am</time>
    <impact>High</impact>
    <forecast>180K</forecast>
    <previous>175K</previous>
    <url>https://www.forexfactory.com/calendar?day=may8.2026#fakeevent1</url>
  </event>
  <event>
    <title>ECB Press Conference</title>
    <country>EUR</country>
    <date>05-07-2026</date>
    <time>2:45pm</time>
    <impact>High</impact>
    <forecast></forecast>
    <previous></previous>
  </event>
  <event>
    <title>Bank Holiday</title>
    <country>GBP</country>
    <date>05-04-2026</date>
    <time>All Day</time>
    <impact>Holiday</impact>
  </event>
  <event>
    <title>Empty Country</title>
    <country></country>
    <date>05-04-2026</date>
    <time>9:00am</time>
    <impact>Low</impact>
  </event>
</weeklyevents>
"""


def test_parse_ff_calendar_extracts_typed_events() -> None:
    events = parse_ff_calendar(_SAMPLE_XML)
    # The "Empty Country" row is dropped (no currency code).
    assert len(events) == 3
    titles = {e.title for e in events}
    assert "Non-Farm Employment Change" in titles
    assert "ECB Press Conference" in titles
    assert "Bank Holiday" in titles


def test_parse_ff_calendar_normalizes_nfp_to_utc() -> None:
    events = parse_ff_calendar(_SAMPLE_XML)
    nfp = next(e for e in events if e.title.startswith("Non-Farm"))
    assert nfp.currency == "USD"
    assert nfp.impact == "high"
    assert nfp.forecast == "180K"
    assert nfp.previous == "175K"
    assert nfp.scheduled_at == datetime(2026, 5, 8, 8, 30, tzinfo=UTC)
    assert nfp.is_all_day is False
    assert nfp.url is not None and nfp.url.startswith("https://")


def test_parse_ff_calendar_marks_all_day_holiday() -> None:
    events = parse_ff_calendar(_SAMPLE_XML)
    holiday = next(e for e in events if e.impact == "holiday")
    assert holiday.is_all_day is True
    assert holiday.scheduled_at == datetime(2026, 5, 4, 0, 0, tzinfo=UTC)
    assert holiday.forecast is None
    assert holiday.previous is None


def test_parse_ff_calendar_sorts_chronologically() -> None:
    events = parse_ff_calendar(_SAMPLE_XML)
    times = [e.scheduled_at for e in events if e.scheduled_at is not None]
    assert times == sorted(times)


def test_parse_ff_calendar_returns_immutable_dataclass() -> None:
    from dataclasses import FrozenInstanceError

    import pytest

    events = parse_ff_calendar(_SAMPLE_XML)
    assert all(isinstance(e, EconomicEvent) for e in events)
    with pytest.raises(FrozenInstanceError):
        events[0].title = "modified"  # type: ignore[misc]


def test_parse_ff_calendar_handles_empty_feed() -> None:
    body = "<?xml version='1.0' ?><weeklyevents></weeklyevents>"
    assert parse_ff_calendar(body) == []
