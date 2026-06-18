"""Async-task admission guard + GC (S02 socle round 5, 2026-06-18).

The async submit endpoints used to accept EVERY request and pile background
tasks behind the single subprocess slot in an unbounded in-process queue (so
the consumer's 503 backoff was dead code), and the GC could evict a still-
running task's bookkeeping (spurious 404 + ghost entry). These unit-test the
new admission guard (409 duplicate / 503 queue-full) and the GC fix (never
evict pending/running).
"""

from __future__ import annotations

import time
from collections.abc import Iterator

import pytest
from fastapi import HTTPException


@pytest.fixture()
def main_mod(monkeypatch: pytest.MonkeyPatch) -> Iterator[object]:
    monkeypatch.setenv("ICHOR_RUNNER_REQUIRE_CF_ACCESS", "false")
    monkeypatch.setenv("ICHOR_RUNNER_ENVIRONMENT", "development")

    import importlib

    from ichor_claude_runner import config as cfg_mod
    from ichor_claude_runner import main as m

    cfg_mod._settings = None
    importlib.reload(m)
    m._async_tasks.clear()
    yield m
    m._async_tasks.clear()
    cfg_mod._settings = None


def _task(status: str, started_at: float = 0.0) -> dict[str, object]:
    return {
        "status": status,
        "result": None,
        "error": None,
        "started_at": started_at,
        "kind": "agent",
    }


def test_active_count_counts_only_pending_and_running(main_mod) -> None:
    main_mod._async_tasks.update(
        {"a": _task("pending"), "b": _task("running"), "c": _task("done"), "d": _task("error")}
    )
    assert main_mod._active_async_task_count() == 2


def test_admit_raises_409_on_duplicate_in_flight(main_mod) -> None:
    main_mod._async_tasks["x"] = _task("running")
    with pytest.raises(HTTPException) as ei:
        main_mod._admit_async_task("x", max_concurrent=1)
    assert ei.value.status_code == 409


def test_admit_allows_reuse_of_terminal_task_id(main_mod) -> None:
    main_mod._async_tasks["x"] = _task("done")
    # A done/error id is not "in flight" — re-submitting it is allowed.
    main_mod._admit_async_task("x", max_concurrent=1)


def test_admit_raises_503_when_queue_full(main_mod) -> None:
    # bound = max_concurrent(1) + _QUEUE_DEPTH(2) = 3 ; 3 active → reject the 4th.
    main_mod._async_tasks.update(
        {"a": _task("running"), "b": _task("pending"), "c": _task("pending")}
    )
    with pytest.raises(HTTPException) as ei:
        main_mod._admit_async_task("new", max_concurrent=1)
    assert ei.value.status_code == 503


def test_admit_allows_under_capacity(main_mod) -> None:
    main_mod._async_tasks.update({"a": _task("running"), "b": _task("pending")})  # 2 < 3
    main_mod._admit_async_task("new", max_concurrent=1)  # no raise


def test_gc_never_evicts_running_over_max(main_mod) -> None:
    # Overfill with terminal + a few running ; the cap must drop only terminal.
    # Use FRESH timestamps (within TTL) so the TTL pass doesn't remove the done
    # tasks first — this isolates the MAX-cap eviction path.
    now = time.monotonic()
    for i in range(main_mod._ASYNC_TASK_MAX + 5):
        main_mod._async_tasks[f"done-{i}"] = _task("done", started_at=now - i * 0.001)
    for i in range(3):
        main_mod._async_tasks[f"run-{i}"] = _task("running", started_at=now)

    main_mod._async_task_gc()

    # every running task survives ; the table is capped by dropping terminal only.
    assert all(f"run-{i}" in main_mod._async_tasks for i in range(3))
    assert len(main_mod._async_tasks) == main_mod._ASYNC_TASK_MAX
