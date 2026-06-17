"""CLI honest-exit-code guards — S02 socle audit (2026-06-18).

Two silent-failure holes closed:

  * ``run_streaming_refresh`` returned 0 even when ``result.failed > 0`` (a
    stale verdict whose regen failed) — now exits 2 so the systemd OnFailure
    path fires.
  * ``run_crisis_check`` let a DB/assessment failure escape as an uncaught
    traceback (exit 1) which the unit's ``SuccessExitStatus=0 1`` masked — now
    ``_main`` catches and returns a distinct honest exit 3.

These tests pin the exit codes so the regression can't silently come back.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import ichor_api.cli.run_crisis_check as crisis_cli
import ichor_api.cli.run_streaming_refresh as sr_cli
import pytest


class _FakeSession:
    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


def _fake_sessionmaker():
    return lambda: _FakeSession()


class _FakeResult:
    def __init__(self, *, failed: int) -> None:
        self.regenerated = 0
        self.pushed = 0
        self.dropped = 0
        self.failed = failed
        self.outcomes: list[object] = []


# ── streaming-refresh exit codes ──────────────────────────────────────


@pytest.mark.asyncio
async def test_streaming_refresh_exit_2_when_regen_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sr_cli, "get_sessionmaker", _fake_sessionmaker)
    monkeypatch.setattr(sr_cli, "is_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr(
        sr_cli, "run_streaming_refresh", AsyncMock(return_value=_FakeResult(failed=2))
    )
    code = await sr_cli._run(
        dry_run=False,
        cooldown_minutes=45,
        max_per_fire=3,
        only_asset=None,
        enable_rag=False,
        enable_tools=False,
    )
    assert code == 2, "a failed regen (stale verdict not refreshed) must exit 2, not 0"


@pytest.mark.asyncio
async def test_streaming_refresh_exit_0_when_no_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sr_cli, "get_sessionmaker", _fake_sessionmaker)
    monkeypatch.setattr(sr_cli, "is_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr(
        sr_cli, "run_streaming_refresh", AsyncMock(return_value=_FakeResult(failed=0))
    )
    code = await sr_cli._run(
        dry_run=False,
        cooldown_minutes=45,
        max_per_fire=3,
        only_asset=None,
        enable_rag=False,
        enable_tools=False,
    )
    assert code == 0


@pytest.mark.asyncio
async def test_streaming_refresh_exit_1_when_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sr_cli, "get_sessionmaker", _fake_sessionmaker)
    monkeypatch.setattr(sr_cli, "is_enabled", AsyncMock(return_value=False))
    # run_streaming_refresh must NOT be reached when the flag is off.
    monkeypatch.setattr(
        sr_cli, "run_streaming_refresh", AsyncMock(side_effect=AssertionError("should not run"))
    )
    code = await sr_cli._run(
        dry_run=False,
        cooldown_minutes=45,
        max_per_fire=3,
        only_asset=None,
        enable_rag=False,
        enable_tools=False,
    )
    assert code == 1


# ── crisis-check exit codes ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_crisis_check_exit_3_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        crisis_cli, "run", AsyncMock(side_effect=RuntimeError("db blip during assess_crisis"))
    )
    # persist=False → the finally branch never calls get_engine().dispose().
    code = await crisis_cli._main(persist=False, min_concurrent=2, lookback_min=60)
    assert code == 3, "a crisis-detector failure must surface as exit 3, not a masked exit 1"


@pytest.mark.asyncio
async def test_crisis_check_exit_0_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(crisis_cli, "run", AsyncMock(return_value=0))
    code = await crisis_cli._main(persist=False, min_concurrent=2, lookback_min=60)
    assert code == 0
