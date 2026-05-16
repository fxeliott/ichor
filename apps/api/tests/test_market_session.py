"""ADR-099 Tier 1.3 — market session + US holiday engine tests.

Pins exact, independently-checkable 2026 dates (no self-referential
asserts) : Western Easter 2026 = Sun 5 Apr → Good Friday Fri 3 Apr ;
MLK = 3rd Mon Jan = 19 Jan ; Thanksgiving = 4th Thu Nov = 26 Nov ;
Christmas 25 Dec 2026 = Friday ; 2026-05-16 = Saturday.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from ichor_api.services.market_session import (
    _easter,
    compute_session_status,
    us_market_holidays,
)

PARIS = ZoneInfo("Europe/Paris")


def test_easter_2026_is_april_5():
    assert _easter(2026) == date(2026, 4, 5)


def test_us_holidays_2026_known_dates():
    h = us_market_holidays(2026)
    assert h[date(2026, 1, 1)] == "New Year's Day"
    assert h[date(2026, 1, 19)] == "Martin Luther King Jr. Day"
    assert h[date(2026, 4, 3)] == "Good Friday"  # Easter 5 Apr − 2
    assert h[date(2026, 11, 26)] == "Thanksgiving"
    assert h[date(2026, 12, 25)] == "Christmas Day"
    # A plain Wednesday is NOT a holiday
    assert date(2026, 3, 4) not in h


def test_observed_shift_sat_to_fri_and_sun_to_mon():
    # 2027: Jul 4 = Sunday → observed Mon Jul 5 ; Dec 25 = Saturday →
    # observed Fri Dec 24 ; New Year Jan 1 2027 = Friday (no shift).
    h = us_market_holidays(2027)
    assert date(2027, 7, 5) in h and date(2027, 7, 4) not in h
    assert date(2027, 12, 24) in h and date(2027, 12, 25) not in h


def test_saturday_is_weekend_fx_closed():
    s = compute_session_status(datetime(2026, 5, 16, 12, 0, tzinfo=PARIS))  # Saturday
    assert s.state == "weekend"
    assert s.market_closed_fx is True
    assert s.market_closed_us_equity is True
    assert s.holiday_name is None
    assert s.minutes_until_next_open >= 0


def test_us_holiday_weekday_fx_open_equity_closed():
    # 2026-12-25 = Friday (a weekday) → US equities closed, FX open.
    s = compute_session_status(datetime(2026, 12, 25, 10, 0, tzinfo=PARIS))
    assert s.state == "us_holiday"
    assert s.market_closed_us_equity is True
    assert s.market_closed_fx is False
    assert s.holiday_name == "Christmas Day"


def test_normal_weekday_pre_londres_window():
    # 2026-05-13 = Wednesday, 07:00 Paris → pre-Londres.
    s = compute_session_status(datetime(2026, 5, 13, 7, 0, tzinfo=PARIS))
    assert s.state == "pre_londres"
    assert s.market_closed_fx is False


def test_normal_weekday_ny_active_afternoon():
    # 2026-05-13 Wed 17:00 Paris → NY session active (NY opens ~15:30).
    s = compute_session_status(datetime(2026, 5, 13, 17, 0, tzinfo=PARIS))
    assert s.state == "ny_active"
