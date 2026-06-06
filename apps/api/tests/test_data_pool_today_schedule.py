"""Tests for the data_pool S03/D1 section `_section_today_schedule`.

Unlike `_section_calendar` (next-14-days, medium/high only, capped at 10),
this section is the COMPLETE day's docket: every release, all impact tiers,
no cap. Pins: low-impact inclusion, no truncation, the honest empty state,
the all-day rendering, the per-asset relevance flag, and ADR-017 cleanliness.
The DB date-window is exercised live on card regen; here we mock the session
(the established data_pool unit-test pattern) and assert the rendering.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from ichor_api.services import data_pool
from ichor_api.services.adr017_filter import is_adr017_clean


class _StubResult:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def scalars(self) -> _StubResult:
        return self

    def all(self) -> list:
        return self._rows


class _StubSession:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    async def execute(self, stmt: object) -> _StubResult:
        return _StubResult(self._rows)


def _event(
    title: str,
    impact: str,
    *,
    currency: str = "USD",
    hh: int = 13,
    mm: int = 30,
    is_all_day: bool = False,
    forecast: str | None = None,
    previous: str | None = None,
    actual: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        title=title,
        impact=impact,
        currency=currency,
        scheduled_at=datetime(2026, 6, 6, hh, mm, tzinfo=UTC),
        is_all_day=is_all_day,
        forecast=forecast,
        previous=previous,
        actual=actual,
    )


@pytest.mark.asyncio
async def test_today_schedule_empty_is_honest() -> None:
    md, src = await data_pool._section_today_schedule(_StubSession([]), "EUR_USD")
    assert "no economic releases scheduled today" in md
    assert src == []
    assert is_adr017_clean(md)


@pytest.mark.asyncio
async def test_today_schedule_includes_low_impact_and_is_uncapped() -> None:
    # 15 events, one low-impact. `_section_calendar` would drop the low one
    # and cap at 10; the full day's docket keeps every tier and every row.
    rows = [_event(f"Release {i}", "low" if i == 0 else "medium", mm=i % 60) for i in range(15)]
    md, src = await data_pool._section_today_schedule(_StubSession(rows), "EUR_USD")
    assert "🟢 low" in md  # low-impact NOT dropped
    for i in range(15):
        assert f"Release {i}" in md  # no truncation
    assert len(src) == 15
    assert is_adr017_clean(md)


@pytest.mark.asyncio
async def test_today_schedule_all_day_and_per_asset_relevance() -> None:
    rows = [
        _event("US NFP", "high", currency="USD", is_all_day=True, forecast="180K"),
        _event("Swiss watch exports", "low", currency="CHF", hh=9, mm=0),
    ]
    md, _ = await data_pool._section_today_schedule(_StubSession(rows), "EUR_USD")
    assert "all day" in md
    assert "US NFP" in md and "forecast=180K" in md
    # A USD release moves EUR_USD → flagged; CHF is off the 8-asset universe.
    nfp_line = next(line for line in md.splitlines() if "US NFP" in line)
    chf_line = next(line for line in md.splitlines() if "Swiss watch" in line)
    assert "affects this asset" in nfp_line
    assert "affects this asset" not in chf_line
    assert is_adr017_clean(md)
