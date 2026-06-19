"""Async-task admission guard + GC (S02 socle round 5, 2026-06-18).

The async submit endpoints used to accept EVERY request and pile background
tasks behind the single subprocess slot in an unbounded in-process queue (so
the consumer's 503 backoff was dead code), and the GC could evict a still-
running task's bookkeeping (spurious 404 + ghost entry). These unit-test the
new admission guard (409 duplicate / 503 queue-full) and the GC fix (never
evict pending/running).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


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


# ─────────────────────────────────────────────────────────────────────────
# S02 socle round 8 — admission runs BEFORE the rate-limiter so a submit
# rejected by admission (409 duplicate / 503 queue-full) does NOT burn an
# hour-quota token. HourlyRateLimiter has no refund, so a token taken on a
# rejected submit would leak forever. These drive the real async endpoints
# through TestClient (which runs the lifespan that builds _rate_limiter) and
# assert the rate-limiter count is unchanged on the rejected path.
# ─────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Iterator[TestClient]:
    monkeypatch.setenv("ICHOR_RUNNER_REQUIRE_CF_ACCESS", "false")
    monkeypatch.setenv("ICHOR_RUNNER_ENVIRONMENT", "development")
    monkeypatch.setenv("ICHOR_RUNNER_WORKDIR", str(tmp_path))

    import importlib

    from ichor_claude_runner import config as cfg_mod
    from ichor_claude_runner import main as main_mod

    cfg_mod._settings = None
    importlib.reload(main_mod)

    with TestClient(main_mod.app) as c:
        # The bg task is never spawned on the rejected (409/503) paths under
        # test, so run_claude is not exercised here — but stub it defensively.
        async def _never_called(*a, **kw):  # pragma: no cover - safety net
            raise AssertionError("run_claude must not run on a rejected submit")

        monkeypatch.setattr(main_mod, "run_claude", _never_called)
        yield c

    cfg_mod._settings = None


def _agent_payload() -> dict[str, object]:
    return {"system": "s", "prompt": "p", "model": "sonnet", "effort": "low"}


def test_async_submit_409_duplicate_does_not_burn_rate_limit(client) -> None:
    from ichor_claude_runner import main as main_mod

    dup_id = str(uuid4())
    # Pre-seed a still-in-flight task with this id so the submit collides (409).
    main_mod._async_tasks[dup_id] = _task("running", started_at=time.monotonic())
    before = main_mod._rate_limiter.current_count()

    r = client.post("/v1/agent-task/async", json={"task_id": dup_id, **_agent_payload()})

    assert r.status_code == 409, r.text
    # Admission rejected the submit BEFORE the rate-limiter ran → 0 token burned.
    assert main_mod._rate_limiter.current_count() == before


def test_async_submit_503_queue_full_does_not_burn_rate_limit(client) -> None:
    from ichor_claude_runner import main as main_mod

    # Fill the queue to capacity (max_concurrent 1 + _QUEUE_DEPTH 2 = 3 active).
    now = time.monotonic()
    main_mod._async_tasks.update(
        {
            "q-a": _task("running", started_at=now),
            "q-b": _task("pending", started_at=now),
            "q-c": _task("pending", started_at=now),
        }
    )
    before = main_mod._rate_limiter.current_count()

    r = client.post("/v1/agent-task/async", json={"task_id": str(uuid4()), **_agent_payload()})

    assert r.status_code == 503, r.text
    # 503 raised by admission BEFORE the rate-limiter → 0 token burned.
    assert main_mod._rate_limiter.current_count() == before


def test_async_submit_admitted_does_burn_rate_limit(client, monkeypatch) -> None:
    """Counter-test: an ADMITTED submit (202) MUST consume exactly one token —
    proves the reorder didn't accidentally drop rate-limiting on the happy path."""
    from ichor_claude_runner import main as main_mod

    # Happy path spawns a real bg task; give it a benign canned result.
    async def _ok(*a, **kw):
        return {"type": "result", "subtype": "success", "result": "ok"}

    monkeypatch.setattr(main_mod, "run_claude", _ok)

    before = main_mod._rate_limiter.current_count()
    r = client.post("/v1/agent-task/async", json={"task_id": str(uuid4()), **_agent_payload()})
    assert r.status_code == 202, r.text
    assert main_mod._rate_limiter.current_count() == before + 1


# ─────────────────────────────────────────────────────────────────────────
# S02 socle residual audit (2026-06-19) — the LEGACY SYNC endpoints
# (/v1/agent-task, /v1/briefing-task) were missing the round-8 reorder: they
# called _rate_limiter.try_acquire() (which consumes a token under quota)
# BEFORE the 503 busy check, so a request rejected with 503 on a busy slot
# burned an hour-quota token with no refund. These mirror the async no-burn
# guards for the sync path.
# ─────────────────────────────────────────────────────────────────────────


class _LockedSem:
    """Stand-in for the subprocess semaphore reporting itself as busy."""

    def locked(self) -> bool:
        return True


def test_sync_agent_task_503_busy_does_not_burn_rate_limit(client, monkeypatch) -> None:
    from ichor_claude_runner import main as main_mod

    monkeypatch.setattr(main_mod, "_subprocess_semaphore", _LockedSem())
    before = main_mod._rate_limiter.current_count()

    r = client.post("/v1/agent-task", json={"task_id": str(uuid4()), **_agent_payload()})

    assert r.status_code == 503, r.text
    # 503 (busy) now raised BEFORE the rate-limiter → 0 token burned.
    assert main_mod._rate_limiter.current_count() == before


def test_sync_agent_task_admitted_burns_one_token(client, monkeypatch) -> None:
    """Counter-test: a non-busy sync agent-task consumes exactly one token —
    proves the reorder didn't drop rate-limiting on the happy path."""
    from ichor_claude_runner import main as main_mod

    async def _ok(*a, **kw):
        return {"type": "result", "subtype": "success", "result": "ok"}

    monkeypatch.setattr(main_mod, "run_claude", _ok)
    before = main_mod._rate_limiter.current_count()

    r = client.post("/v1/agent-task", json={"task_id": str(uuid4()), **_agent_payload()})

    assert r.status_code == 200, r.text
    assert main_mod._rate_limiter.current_count() == before + 1


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


# ─────────────────────────────────────────────────────────────────────────
# S02 socle round 8 — a bg coroutine cancelled on lifespan shutdown must mark
# its task entry terminal ('error'), not leave it stuck at 'running' forever
# (a stuck 'running' entry also wedges admission, since GC never evicts it).
# The CancelledError arm sets status='error' then re-raises to honor the cancel.
# ─────────────────────────────────────────────────────────────────────────


async def _run_bg_and_cancel(main_mod, bg_coro_name: str, req) -> None:
    from ichor_claude_runner import config as cfg_mod

    settings = cfg_mod.get_settings()
    # The main_mod fixture does not run the lifespan, so the module globals the
    # bg coroutine relies on are uninitialized — set up the semaphore the bg
    # task acquires (the rate-limiter is not touched by the bg path).
    main_mod._subprocess_semaphore = asyncio.Semaphore(settings.max_concurrent_subprocess)
    task_id = str(req.task_id)
    main_mod._async_tasks[task_id] = {
        "status": "pending",
        "result": None,
        "error": None,
        "started_at": time.monotonic(),
        "kind": "agent",
    }

    started = asyncio.Event()

    async def _blocking_run(*a, **kw):
        started.set()
        # Block until cancelled — simulates an in-flight subprocess at shutdown.
        await asyncio.sleep(3600)

    main_mod.run_claude = _blocking_run  # patch the symbol the bg coroutine calls
    bg = asyncio.create_task(getattr(main_mod, bg_coro_name)(task_id, req, settings))
    await started.wait()  # ensure status flipped to 'running' and we're in run_claude

    assert main_mod._async_tasks[task_id]["status"] == "running"

    bg.cancel()
    with pytest.raises(asyncio.CancelledError):
        await bg

    # The CancelledError arm marked it terminal so it won't wedge admission/GC.
    assert main_mod._async_tasks[task_id]["status"] == "error"
    assert main_mod._async_tasks[task_id]["error"] == "cancelled (runner shutdown)"


async def test_agent_bg_cancelled_marks_error(main_mod) -> None:
    from ichor_claude_runner.models import AgentTaskRequest

    req = AgentTaskRequest(system="s", prompt="p", model="sonnet", effort="low")
    await _run_bg_and_cancel(main_mod, "_run_agent_background", req)


async def test_briefing_bg_cancelled_marks_error(main_mod) -> None:
    from ichor_claude_runner.models import BriefingTaskRequest

    req = BriefingTaskRequest(briefing_type="crisis", assets=["EUR_USD"], context_markdown="ctx")
    await _run_bg_and_cancel(main_mod, "_run_briefing_background", req)
