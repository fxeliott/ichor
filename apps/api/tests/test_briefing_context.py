"""Tests for the Wave 1.3 briefing-context expansion.

Asserts that the legacy assembler in `cli/run_briefing.py` :
  - No longer prints the "## TODO Phase 0 W2 — context expansion"
    placeholder section (the user-visible scar removed in this audit)
  - Emits the 4 new sections (calendar, news-NLP, COT shifts, vol surface)
  - Each section renders an honest empty-state message when no data
    is in the underlying tables

Uses an in-memory stub session that returns empty result sets so the
function exercises the empty-state branches without needing Postgres.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest


class _ScalarsAll:
    def all(self) -> list[Any]:
        return []


class _Result:
    def scalars(self) -> _ScalarsAll:
        return _ScalarsAll()

    def all(self) -> list[Any]:
        return []

    def first(self) -> None:
        return None


class _StubSession:
    """Fake AsyncSession : every execute() returns an empty result."""

    async def execute(self, stmt: Any) -> _Result:
        return _Result()

    async def __aenter__(self) -> _StubSession:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None


def _stub_session_factory() -> _StubSession:
    return _StubSession()


@pytest.mark.asyncio
async def test_assemble_context_drops_todo_phase_0_w2_section() -> None:
    """The placeholder section must be GONE from the markdown output."""
    from ichor_api.cli.run_briefing import _assemble_context

    with patch(
        "ichor_api.cli.run_briefing.get_sessionmaker",
        return_value=_stub_session_factory,
    ):
        text, _tokens = await _assemble_context("pre_londres", ["EUR_USD"])
    assert "TODO Phase 0 W2" not in text
    assert "context expansion" not in text


@pytest.mark.asyncio
async def test_assemble_context_emits_four_new_sections() -> None:
    """Calendar / News-NLP / COT / Vol surface sections must all appear."""
    from ichor_api.cli.run_briefing import _assemble_context

    with patch(
        "ichor_api.cli.run_briefing.get_sessionmaker",
        return_value=_stub_session_factory,
    ):
        text, _ = await _assemble_context("pre_londres", ["EUR_USD"])
    assert "## Macro calendar" in text
    assert "## News-NLP aggregate" in text
    assert "## COT positioning shifts" in text
    assert "## Vol surface anomalies" in text


@pytest.mark.asyncio
async def test_assemble_context_empty_state_messages_present() -> None:
    """When tables are empty, each section must say so honestly."""
    from ichor_api.cli.run_briefing import _assemble_context

    with patch(
        "ichor_api.cli.run_briefing.get_sessionmaker",
        return_value=_stub_session_factory,
    ):
        text, _ = await _assemble_context("pre_londres", ["EUR_USD"])
    # Calendar : "no high/medium-impact events scheduled in the next 6h"
    assert "no high/medium-impact events" in text
    # News-NLP : "no tone-tagged news in the last 24h"
    assert "no tone-tagged news" in text
    # COT : "no COT report in the last 7 days"
    assert "no COT report" in text
    # Vol : "VIX series not available"
    assert "VIX series not available" in text


@pytest.mark.asyncio
async def test_assemble_context_token_estimate_positive() -> None:
    """The token estimate must be positive (the markdown is non-empty
    even with all empty-state branches)."""
    from ichor_api.cli.run_briefing import _assemble_context

    with patch(
        "ichor_api.cli.run_briefing.get_sessionmaker",
        return_value=_stub_session_factory,
    ):
        text, tokens = await _assemble_context("pre_londres", ["EUR_USD"])
    assert tokens > 0
    assert len(text) > 200  # at least the section headers
