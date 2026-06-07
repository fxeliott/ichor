"""Pure tests for the generic data-source liveness primitive (S04).

Mirrors the FRED-liveness semantics (data_pool._fred_liveness) for any
non-FRED source so stale/absent data can no longer render as current.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from ichor_api.services.data_liveness import (
    SourceLiveness,
    classify_liveness,
)

_NOW = date(2026, 6, 8)


def test_absent_when_latest_is_none() -> None:
    lv = classify_liveness("CFTC:COT", None, now=_NOW, max_age_days=10)
    assert lv.status == "absent"
    assert lv.latest_date is None
    assert lv.age_days is None
    assert lv.is_degraded is True


def test_fresh_today() -> None:
    lv = classify_liveness("NYFED:MCT", _NOW, now=_NOW, max_age_days=35)
    assert lv.status == "fresh"
    assert lv.age_days == 0
    assert lv.is_degraded is False


def test_fresh_within_window() -> None:
    lv = classify_liveness("GPR", date(2026, 6, 1), now=_NOW, max_age_days=10)
    assert lv.status == "fresh"
    assert lv.age_days == 7


def test_stale_beyond_window() -> None:
    lv = classify_liveness("CLEVELAND:NOWCAST", date(2026, 4, 1), now=_NOW, max_age_days=10)
    assert lv.status == "stale"
    assert lv.age_days == 68
    assert lv.is_degraded is True


def test_boundary_age_equals_max_is_fresh() -> None:
    # age == max_age → fresh (mirror of `_fred_liveness` `age <= max_age`).
    lv = classify_liveness("NFIB:SBET", date(2026, 5, 29), now=_NOW, max_age_days=10)
    assert lv.age_days == 10
    assert lv.status == "fresh"


def test_boundary_age_one_over_max_is_stale() -> None:
    lv = classify_liveness("NFIB:SBET", date(2026, 5, 28), now=_NOW, max_age_days=10)
    assert lv.age_days == 11
    assert lv.status == "stale"


def test_datetime_inputs_normalized_to_date() -> None:
    # A timestamp-keyed table (e.g. CFTC report_date as datetime) classifies
    # identically to its date.
    latest = datetime(2026, 5, 30, 18, 30, tzinfo=UTC)
    now = datetime(2026, 6, 8, 3, 0, tzinfo=UTC)
    lv = classify_liveness("CFTC:TFF", latest, now=now, max_age_days=14)
    assert lv.status == "fresh"
    assert lv.age_days == 9


def test_future_dated_latest_is_fresh() -> None:
    # Forward-stamped release (negative age) → fresh, same as FRED path.
    lv = classify_liveness("WTREGEN", date(2026, 6, 12), now=_NOW, max_age_days=7)
    assert lv.age_days == -4
    assert lv.status == "fresh"


def test_negative_max_age_raises() -> None:
    with pytest.raises(ValueError, match="max_age_days must be >= 0"):
        classify_liveness("X", _NOW, now=_NOW, max_age_days=-1)


def test_mirrors_fred_liveness_boundary() -> None:
    # Byte-consistency invariant: status == "fresh" iff (now - latest).days <= max.
    for delta, max_age, expected in [
        (0, 0, "fresh"),
        (1, 0, "stale"),
        (14, 14, "fresh"),
        (15, 14, "stale"),
        (90, 90, "fresh"),
        (91, 90, "stale"),
    ]:
        latest = date.fromordinal(_NOW.toordinal() - delta)
        lv = classify_liveness("S", latest, now=_NOW, max_age_days=max_age)
        assert lv.status == expected, f"delta={delta} max={max_age}"


def test_source_liveness_is_frozen() -> None:
    lv = SourceLiveness("X", "fresh", _NOW, 0, 10)
    with pytest.raises(Exception):
        lv.status = "stale"  # type: ignore[misc]
