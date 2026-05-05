"""Tests for the Crisis Mode auto-trigger CLI helpers.

The DB-bound state machine (assess + emit ACTIVE/RESOLVED) is unit-
tested via mocks. Real Postgres integration is exercised in CI.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ichor_api.cli.run_crisis_check import (
    _CRISIS_ACTIVE_CODE,
    _CRISIS_RESOLVED_CODE,
    run,
)


def _mock_sm(*assessments_and_state):
    """Build a fake get_sessionmaker that yields a session whose
    relevant queries return the supplied values in order."""
    session = MagicMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=None)
    return MagicMock(return_value=cm), session


@pytest.mark.asyncio
async def test_run_dry_run_no_persist_no_writes() -> None:
    """Without --persist, no Alert rows are added regardless of state."""
    sm_factory, session = _mock_sm()

    fake_assessment = SimpleNamespace(
        is_active=True, triggering_codes=["VIX_PANIC", "GEX_FLIP"], severity_score=5.0
    )

    with patch(
        "ichor_api.cli.run_crisis_check.get_sessionmaker", return_value=sm_factory
    ), patch(
        "ichor_api.cli.run_crisis_check.assess_crisis", AsyncMock(return_value=fake_assessment)
    ), patch(
        "ichor_api.cli.run_crisis_check._last_crisis_active", AsyncMock(return_value=None)
    ), patch(
        "ichor_api.cli.run_crisis_check._last_crisis_resolved", AsyncMock(return_value=None)
    ):
        rc = await run(persist=False)

    assert rc == 0
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_run_emits_active_on_transition() -> None:
    """assessment ON + db OFF → emit CRISIS_MODE_ACTIVE."""
    sm_factory, session = _mock_sm()

    fake_assessment = SimpleNamespace(
        is_active=True, triggering_codes=["VIX_PANIC", "GEX_FLIP"], severity_score=5.0
    )

    with patch(
        "ichor_api.cli.run_crisis_check.get_sessionmaker", return_value=sm_factory
    ), patch(
        "ichor_api.cli.run_crisis_check.assess_crisis", AsyncMock(return_value=fake_assessment)
    ), patch(
        "ichor_api.cli.run_crisis_check._last_crisis_active", AsyncMock(return_value=None)
    ), patch(
        "ichor_api.cli.run_crisis_check._last_crisis_resolved", AsyncMock(return_value=None)
    ):
        await run(persist=True)

    # Should have added an Alert row
    assert session.add.called
    added = session.add.call_args.args[0]
    assert added.alert_code == _CRISIS_ACTIVE_CODE
    assert added.severity == "critical"


@pytest.mark.asyncio
async def test_run_emits_resolved_on_transition() -> None:
    """assessment OFF + db ON → emit CRISIS_MODE_RESOLVED."""
    sm_factory, session = _mock_sm()

    fake_assessment = SimpleNamespace(
        is_active=False, triggering_codes=[], severity_score=0.0
    )
    last_active = SimpleNamespace(
        triggered_at=datetime.now(UTC),
        source_payload={"triggering_codes": ["VIX_PANIC", "GEX_FLIP"]},
    )

    with patch(
        "ichor_api.cli.run_crisis_check.get_sessionmaker", return_value=sm_factory
    ), patch(
        "ichor_api.cli.run_crisis_check.assess_crisis", AsyncMock(return_value=fake_assessment)
    ), patch(
        "ichor_api.cli.run_crisis_check._last_crisis_active", AsyncMock(return_value=last_active)
    ), patch(
        "ichor_api.cli.run_crisis_check._last_crisis_resolved", AsyncMock(return_value=None)
    ):
        await run(persist=True)

    assert session.add.called
    added = session.add.call_args.args[0]
    assert added.alert_code == _CRISIS_RESOLVED_CODE
    assert added.severity == "info"


@pytest.mark.asyncio
async def test_run_no_op_when_sustained_crisis() -> None:
    """assessment ON + db ON (already active) → no new emission."""
    sm_factory, session = _mock_sm()

    fake_assessment = SimpleNamespace(
        is_active=True, triggering_codes=["VIX_PANIC", "GEX_FLIP"], severity_score=5.0
    )
    last_active = SimpleNamespace(
        triggered_at=datetime.now(UTC),
        source_payload={"triggering_codes": ["VIX_PANIC", "GEX_FLIP"]},
    )

    with patch(
        "ichor_api.cli.run_crisis_check.get_sessionmaker", return_value=sm_factory
    ), patch(
        "ichor_api.cli.run_crisis_check.assess_crisis", AsyncMock(return_value=fake_assessment)
    ), patch(
        "ichor_api.cli.run_crisis_check._last_crisis_active", AsyncMock(return_value=last_active)
    ), patch(
        "ichor_api.cli.run_crisis_check._last_crisis_resolved", AsyncMock(return_value=None)
    ):
        await run(persist=True)

    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_run_no_op_when_quiet() -> None:
    """assessment OFF + db OFF (no prior active) → no emission."""
    sm_factory, session = _mock_sm()

    fake_assessment = SimpleNamespace(
        is_active=False, triggering_codes=[], severity_score=0.0
    )

    with patch(
        "ichor_api.cli.run_crisis_check.get_sessionmaker", return_value=sm_factory
    ), patch(
        "ichor_api.cli.run_crisis_check.assess_crisis", AsyncMock(return_value=fake_assessment)
    ), patch(
        "ichor_api.cli.run_crisis_check._last_crisis_active", AsyncMock(return_value=None)
    ), patch(
        "ichor_api.cli.run_crisis_check._last_crisis_resolved", AsyncMock(return_value=None)
    ):
        await run(persist=True)

    session.add.assert_not_called()
