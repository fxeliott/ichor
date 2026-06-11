"""S03 — scenario-invalidation CLI validation-mode contract.

The flag's arming is gated on a ≥3-session empirical validation
(ADR-106 §Carry-forward r166), but before S03 the flag gated the
--dry-run too, so the validation could never start. Pins the fixed
contract: dry-run evaluates flag-OFF (read-only + rollback); persisting
runs stay strictly flag-gated (exit 1 clean skip).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from ichor_api.cli import run_scenario_invalidation_check as cli


def _mock_sessionmaker(session: MagicMock) -> MagicMock:
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=cm)


@pytest.fixture
def session() -> MagicMock:
    s = MagicMock()
    s.rollback = AsyncMock()
    s.commit = AsyncMock()
    return s


@pytest.mark.asyncio
async def test_dry_run_evaluates_even_with_flag_off(monkeypatch, session) -> None:
    monkeypatch.setattr(cli, "get_sessionmaker", lambda: _mock_sessionmaker(session))
    monkeypatch.setattr(cli, "is_enabled", AsyncMock(return_value=False))
    evaluate = AsyncMock(return_value=[])
    monkeypatch.setattr(cli, "check_scenario_invalidations", evaluate)

    rc = await cli._run(dry_run=True, lookback_hours=24)

    assert rc == 0
    evaluate.assert_awaited()  # the validation evidence CAN accumulate
    session.rollback.assert_awaited()  # …read-only, rolled back
    session.commit.assert_not_awaited()
    # A web push is NOT rollbackable — dry-run must pass notify=False
    # (S03 verifier finding #4: flag-OFF validation runs would otherwise
    # re-push the same hard invalidation on every tick).
    assert evaluate.await_args.kwargs.get("notify") is False


@pytest.mark.asyncio
async def test_flag_off_without_dry_run_still_clean_skips(monkeypatch, session) -> None:
    monkeypatch.setattr(cli, "get_sessionmaker", lambda: _mock_sessionmaker(session))
    monkeypatch.setattr(cli, "is_enabled", AsyncMock(return_value=False))
    evaluate = AsyncMock(return_value=[])
    monkeypatch.setattr(cli, "check_scenario_invalidations", evaluate)

    rc = await cli._run(dry_run=False, lookback_hours=24)

    assert rc == 1  # fail-closed contract unchanged for persisting runs
    evaluate.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_flag_on_persisting_run_commits(monkeypatch, session) -> None:
    monkeypatch.setattr(cli, "get_sessionmaker", lambda: _mock_sessionmaker(session))
    monkeypatch.setattr(cli, "is_enabled", AsyncMock(return_value=True))
    evaluate = AsyncMock(return_value=[])
    monkeypatch.setattr(cli, "check_scenario_invalidations", evaluate)

    rc = await cli._run(dry_run=False, lookback_hours=24)

    assert rc == 0
    evaluate.assert_awaited()
    session.commit.assert_awaited()
