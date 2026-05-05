"""Tests for the macro context loader (added separately to keep the
main test_couche2_context.py focused on the 4 original kinds)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from ichor_api.services.couche2_context import (
    _MACRO_FRED_SERIES,
    build_macro_context,
)


def _mock_session(rows_per_query: list[list]) -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock()

    def _build_result(rows):
        result = MagicMock()
        result.scalars.return_value.all.return_value = rows
        return result

    session.execute.side_effect = [_build_result(r) for r in rows_per_query]
    return session


@pytest.mark.asyncio
async def test_macro_empty_emits_neutral_fallback_instruction() -> None:
    session = _mock_session([[], []])
    ctx = await build_macro_context(session)
    assert "No FRED observations" in ctx.body
    assert "neutral" in ctx.body.lower()
    assert ctx.n_rows == 0


@pytest.mark.asyncio
async def test_macro_renders_fred_series_with_delta() -> None:
    today = date.today()
    yesterday = today - timedelta(days=30)
    rows = [
        SimpleNamespace(series_id="CPIAUCSL", observation_date=today, value=320.5),
        SimpleNamespace(series_id="CPIAUCSL", observation_date=yesterday, value=318.0),
        SimpleNamespace(series_id="DGS10", observation_date=today, value=4.25),
    ]
    session = _mock_session([rows, []])  # FRED rows + empty CB speeches
    ctx = await build_macro_context(session)
    assert "CPIAUCSL" in ctx.body
    assert "DGS10" in ctx.body
    # Delta is rendered for series with 2+ observations
    assert "Δ" in ctx.body or "delta" in ctx.body.lower() or "+2.5" in ctx.body


@pytest.mark.asyncio
async def test_macro_includes_cb_speeches_overlay() -> None:
    rows = []  # Empty FRED
    speeches = [
        SimpleNamespace(
            central_bank="FED",
            speaker="Powell",
            published_at=datetime.now(UTC) - timedelta(days=1),
            title="Restrictive policy stance",
            summary=None,
            url="https://x.com",
        ),
    ]
    session = _mock_session([rows, speeches])
    ctx = await build_macro_context(session)
    assert "CB rhetoric overlay" in ctx.body
    assert "Powell" in ctx.body
    assert "FED" in ctx.body
    assert "cb_speeches" in ctx.sources


def test_macro_fred_series_dict_covers_8_themes() -> None:
    """Smoke check : the macro series dict spans the 8 themes the
    MacroAgentOutput expects (monetary, growth, inflation, labor, etc.)."""
    series_ids = set(_MACRO_FRED_SERIES.keys())
    # Sanity : at least one inflation, labor, growth, rates, market series
    assert any(s.startswith("CPI") or s.startswith("PCE") for s in series_ids)
    assert "PAYEMS" in series_ids
    assert "GDP" in series_ids or "INDPRO" in series_ids
    assert any(s.startswith("DGS") or s == "DFF" for s in series_ids)
    assert "VIXCLS" in series_ids
