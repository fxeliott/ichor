"""Tests for the data_pool real-time-reactivity section `_section_recent_actuals`.

Wires the existing `recent_actuals` service into the LLM prompt so the card can
react to a published economic result (§6.4 mission centrale). The DB path is
exercised live on card regen; here we pin the pure rendering + the honest empty
state + ADR-017 cleanliness via a monkeypatched service.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ichor_api.services import data_pool
from ichor_api.services.adr017_filter import is_adr017_clean
from ichor_api.services.economic_event_surprise import SurpriseClassification
from ichor_api.services.recent_actuals import RecentActualRow

_PATH = "ichor_api.services.recent_actuals.fetch_recent_actuals"


@pytest.mark.asyncio
async def test_recent_actuals_empty_is_honest(monkeypatch) -> None:
    async def _fake(session, **kw):  # noqa: ANN001, ANN002, ANN003
        return []

    monkeypatch.setattr(_PATH, _fake)
    md, src = await data_pool._section_recent_actuals(None)
    assert "aucun résultat" in md
    assert src == []
    assert is_adr017_clean(md)


@pytest.mark.asyncio
async def test_recent_actuals_renders_surprise(monkeypatch) -> None:
    row = RecentActualRow(
        event_id="e1",
        currency="USD",
        scheduled_at=datetime(2026, 5, 29, 12, 30, tzinfo=UTC),
        title="CPI y/y",
        impact="high",
        actual="3.1%",
        forecast="3.3%",
        forecast_min=None,
        forecast_max=None,
        previous="3.2%",
        url=None,
        classification=SurpriseClassification(
            state="unavailable",
            actual=3.1,
            consensus=3.3,
            forecast_min=None,
            forecast_max=None,
            magnitude_pct=(3.1 - 3.3) / 3.3 * 100.0,
            range_breach=None,
            parse_failures=frozenset(),
        ),
    )

    async def _fake(session, **kw):  # noqa: ANN001, ANN002, ANN003
        return [row]

    monkeypatch.setattr(_PATH, _fake)
    md, src = await data_pool._section_recent_actuals(None)
    assert "CPI y/y" in md
    assert "actual 3.1%" in md
    assert "cons. 3.3%" in md
    assert "surprise -6.1%" in md  # (3.1-3.3)/3.3*100 = -6.06 → -6.1
    assert "ForexFactory:economic_events" in src
    assert is_adr017_clean(md)


@pytest.mark.asyncio
async def test_recent_actuals_filters_low_impact_and_offshore_ccy(monkeypatch) -> None:
    def _row(ccy: str, impact: str) -> RecentActualRow:
        return RecentActualRow(
            event_id=ccy + impact,
            currency=ccy,
            scheduled_at=datetime(2026, 5, 29, 9, 0, tzinfo=UTC),
            title="Some print",
            impact=impact,
            actual="1.0",
            forecast=None,
            forecast_min=None,
            forecast_max=None,
            previous=None,
            url=None,
            classification=SurpriseClassification(
                state="unavailable",
                actual=1.0,
                consensus=None,
                forecast_min=None,
                forecast_max=None,
                magnitude_pct=None,
                range_breach=None,
                parse_failures=frozenset(),
            ),
        )

    async def _fake(session, **kw):  # noqa: ANN001, ANN002, ANN003
        return [
            _row("JPY", "high"),
            _row("USD", "low"),
            _row("EUR", "high"),
            _row("CAD", "high"),
        ]

    monkeypatch.setattr(_PATH, _fake)
    md, _ = await data_pool._section_recent_actuals(None)
    # JPY (offshore) + USD-low filtered out; EUR-high kept.
    assert "EUR [high]" in md
    assert "JPY" not in md
    assert "[low]" not in md
    # CAD is a traded currency (USD_CAD) → its high-impact print must surface
    # (regression guard for the recent-actuals CAD gap, S03 audit 2026-06-19).
    assert "CAD [high]" in md
