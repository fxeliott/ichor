"""Permanence guard for the hardcoded central-bank meetings table.

`_CB_MEETINGS_2026` is a static annual table; once all its dates are in the
past, the calendar's CB section goes silently empty and the DB freshness
monitor cannot catch it (it watches DB tables, not Python lists). These
tests pin the pure expiry helper AND act as a CI tripwire that fails loudly
the moment the table is fully expired — forcing a re-seed before prod breaks.
"""

from __future__ import annotations

from datetime import date, timedelta

from ichor_api.services.economic_calendar import (
    _CB_TABLE_EXPIRY_WARN_DAYS,
    _CB_TABLE_MAX_DATE,
    cb_table_status,
)


def test_cb_table_status_ok_well_before_expiry() -> None:
    assert cb_table_status(_CB_TABLE_MAX_DATE - timedelta(days=200)) == "ok"


def test_cb_table_status_expiring_within_window() -> None:
    assert cb_table_status(_CB_TABLE_MAX_DATE - timedelta(days=10)) == "expiring"
    assert cb_table_status(_CB_TABLE_MAX_DATE) == "expiring"  # 0 days left
    # boundary: exactly the warn window is still "expiring"
    assert (
        cb_table_status(_CB_TABLE_MAX_DATE - timedelta(days=_CB_TABLE_EXPIRY_WARN_DAYS))
        == "expiring"
    )
    # one day past the window is "ok"
    assert (
        cb_table_status(_CB_TABLE_MAX_DATE - timedelta(days=_CB_TABLE_EXPIRY_WARN_DAYS + 1)) == "ok"
    )


def test_cb_table_status_expired_after_last_meeting() -> None:
    assert cb_table_status(_CB_TABLE_MAX_DATE + timedelta(days=1)) == "expired"


def test_cb_table_tripwire_not_already_expired() -> None:
    """CI tripwire: when the static CB table is fully in the past this fails,
    forcing a re-seed of _CB_MEETINGS_* before the calendar silently breaks."""
    assert cb_table_status(date.today()) != "expired", (
        "CB meetings table expired — re-seed _CB_MEETINGS_* in services/economic_calendar.py"
    )
