"""Tests for the shared cron exit-code wrapper (``cli/_exit.py``).

S02 socle audit (2026-06-18). Pins the two behaviours the zero-exception
``_check`` heartbeat family relies on :
  • a transient error escaping the inner coroutine becomes a distinct honest
    exit 3 (``ExitCode.TRANSIENT``) — never an uncaught traceback / exit 1 —
    so the systemd ``OnFailure`` path fires instead of the unit's
    ``SuccessExitStatus=0 1`` silently masking a dead heartbeat ;
  • the inner coroutine's int return value (0 / 2 / ...) is propagated unchanged
    on success.

Plus a smoke test on a migrated CLI (``run_vix_term_check``) proving its
``main()`` now returns 3 when the DB-bound evaluate call raises.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from ichor_api.cli._exit import ExitCode, cron_main


def test_exit_code_values() -> None:
    """The contract matches the inlined codes in run_crisis_check."""
    assert (ExitCode.OK, ExitCode.SKIP, ExitCode.WORK_FAILED, ExitCode.TRANSIENT) == (0, 1, 2, 3)


def test_cron_main_returns_transient_on_exception() -> None:
    """A raising coroutine yields exit 3 (TRANSIENT), not a traceback."""

    async def _boom() -> int:
        raise RuntimeError("asyncpg connection refused")

    rc = cron_main(_boom)
    assert rc == ExitCode.TRANSIENT == 3


def test_cron_main_propagates_ok() -> None:
    """A success return (0) is propagated unchanged."""

    async def _ok() -> int:
        return 0

    assert cron_main(_ok) == ExitCode.OK == 0


def test_cron_main_propagates_inner_nonzero() -> None:
    """A non-zero inner return (e.g. 2 = WORK_FAILED) is propagated unchanged,
    NOT collapsed into the transient code."""

    async def _work_failed() -> int:
        return 2

    assert cron_main(_work_failed) == ExitCode.WORK_FAILED == 2


def test_migrated_cli_returns_transient_on_db_error(monkeypatch) -> None:
    """A migrated zero-exception _check CLI (run_vix_term_check) now returns 3
    when its DB-bound evaluate call raises, instead of an exit-1 traceback."""
    from ichor_api.cli import run_vix_term_check as cli

    monkeypatch.setattr(
        cli,
        "evaluate_vix_term_inversion",
        AsyncMock(side_effect=RuntimeError("db blip")),
    )
    # Dry-run path (no --persist) → no engine disposal needed, isolates the
    # transient barrier. main() runs asyncio.run via cron_main.
    rc = cli.main(["run_vix_term_check"])
    assert rc == ExitCode.TRANSIENT == 3
