"""Shared cron exit-code contract for the alert-heartbeat ``_check`` CLIs.

S02 socle audit (2026-06-18) — honest failure signalling. The zero-exception
``_check`` heartbeat CLIs (e.g. ``run_liquidity_check``, ``run_vix_term_check``)
emit only via ``check_metric`` and write NO destination table, so the
data-freshness monitor cannot see them die. They also had NO try/except around
their async DB work : a transient asyncpg error escaped as an uncaught traceback
(exit 1), which the unit's ``SuccessExitStatus=0 1`` then masked → the heartbeat
silently stopped and nobody was paged.

This module centralises the exit-code semantics already inlined in
``run_crisis_check`` / ``run_streaming_refresh`` so those CLIs can delegate to a
single wrapper. Importing it is ADDITIVE — it changes nothing until a CLI calls
``cron_main``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from enum import IntEnum

import structlog

log = structlog.get_logger(__name__)


class ExitCode(IntEnum):
    """Cron exit-code contract shared across the ``_check`` heartbeat CLIs.

    Mirrors the inlined codes in ``run_crisis_check`` / ``run_streaming_refresh``
    and the systemd units' ``SuccessExitStatus=0 1`` (0 and 1 are tolerated as
    success ; 2 and 3 fire the ``OnFailure`` notify path).
    """

    OK = 0
    """Success — the check ran and reported (zero or more alerts fired)."""

    SKIP = 1
    """Clean skip — not a failure (e.g. no usable data, feature flag OFF).

    Tolerated by the unit's ``SuccessExitStatus`` exactly like OK.
    """

    WORK_FAILED = 2
    """The work itself failed honestly (e.g. a regen that should have produced
    output did not). Distinct from a transient blip ; fires ``OnFailure``."""

    TRANSIENT = 3
    """DB connection / runtime failure — cron retries next tick. Fires
    ``OnFailure`` so the dying heartbeat is visible instead of swallowed."""


def cron_main(coro_factory: Callable[[], Awaitable[int]]) -> int:
    """Run a cron entrypoint coroutine with the shared transient-error barrier.

    ``coro_factory`` is a zero-arg callable returning the CLI's async entrypoint
    coroutine (typically the existing ``_main(...)``, which already disposes the
    engine in its own ``finally`` so disposal stays in the same event loop —
    ADR-024). This wrapper runs it via ``asyncio.run`` and converts an otherwise
    uncaught exception into a distinct honest exit 3 (``ExitCode.TRANSIENT``)
    with the canonical "Cron will retry next tick" message, instead of letting a
    transient asyncpg error escape as an exit-1 traceback that the unit masks.

    The inner coroutine's int return value (0 / 1 / 2 / ...) is PROPAGATED
    unchanged on success.
    """
    try:
        return asyncio.run(coro_factory())
    except Exception as exc:
        print(f"check failed : {exc!s}. Cron will retry next tick.")
        return ExitCode.TRANSIENT
