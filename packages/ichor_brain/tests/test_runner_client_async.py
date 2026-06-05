"""Tests for HttpRunnerClient async+polling path (added 2026-06-02).

The async path (`use_async_endpoint=True`, the production default) submits
a task with POST /v1/briefing-task/async then polls
GET /v1/briefing-task/async/{id} until done. These tests pin the happy
path plus the poll-loop resilience added 2026-06-02: a single transient
tunnel blip on a poll (502/52x/dropped connection) must NOT abort a
running card — the runner is up, cloudflared just briefly couldn't reach
it. Root cause witnessed: a uvicorn keep-alive/poll-interval race produced
`EOF`/502 on polls right after a runner restart and killed full Opus cards.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
from ichor_brain.runner_client import (
    _MAX_CONSECUTIVE_POLL_ERRORS,
    HttpRunnerClient,
    RunnerCall,
    RunnerResultError,
)


async def _no_op() -> None:
    return None


def _make_client() -> HttpRunnerClient:
    return HttpRunnerClient(
        base_url="https://runner.example.com",
        cf_access_client_id="id",
        cf_access_client_secret="secret",
        timeout_sec=5.0,
        use_async_endpoint=True,
        poll_interval_sec=0.01,
        poll_max_total_sec=600.0,
    )


_TASK_ID = "00000000-0000-0000-0000-000000000000"


def _accepted() -> httpx.Response:
    return httpx.Response(
        202,
        json={"task_id": _TASK_ID, "poll_url": f"/v1/briefing-task/async/{_TASK_ID}"},
    )


def _done() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "status": "done",
            "result": {"briefing_markdown": "ok briefing", "duration_ms": 1234},
        },
    )


def _running() -> httpx.Response:
    return httpx.Response(200, json={"status": "running", "result": None})


def _run_with_handler(handler) -> object:
    """Drive client.run() through a MockTransport handler. Returns the coroutine
    result via a fresh event loop (pytest-asyncio supplies one)."""
    transport = httpx.MockTransport(handler)
    real_client_cls = httpx.AsyncClient

    def _factory(**kw):
        kw["transport"] = transport
        return real_client_cls(**kw)

    return _factory


@pytest.mark.asyncio
async def test_async_happy_path(monkeypatch) -> None:
    monkeypatch.setattr("ichor_brain.runner_client.asyncio.sleep", lambda *a, **kw: _no_op())
    state = {"polls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return _accepted()
        state["polls"] += 1
        return _running() if state["polls"] < 2 else _done()

    with patch("ichor_brain.runner_client.httpx.AsyncClient", _run_with_handler(handler)):
        resp = await _make_client().run(RunnerCall(prompt="p", system="s"))
    assert resp.text == "ok briefing"
    assert resp.duration_ms == 1234
    assert state["polls"] == 2  # one running + one done


@pytest.mark.asyncio
async def test_async_poll_tolerates_transient_502(monkeypatch) -> None:
    """A 502 on a poll must NOT abort — keep polling until the task finishes."""
    monkeypatch.setattr("ichor_brain.runner_client.asyncio.sleep", lambda *a, **kw: _no_op())
    state = {"polls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return _accepted()
        state["polls"] += 1
        # poll 1 running, polls 2-3 transient 502, poll 4 done
        if state["polls"] == 1:
            return _running()
        if state["polls"] in (2, 3):
            return httpx.Response(502, text="cloudflared: EOF")
        return _done()

    with patch("ichor_brain.runner_client.httpx.AsyncClient", _run_with_handler(handler)):
        resp = await _make_client().run(RunnerCall(prompt="p", system="s"))
    assert resp.text == "ok briefing"
    assert state["polls"] == 4  # the two 502s were tolerated


@pytest.mark.asyncio
async def test_async_poll_tolerates_dropped_connection(monkeypatch) -> None:
    """A dropped origin connection (httpx.TransportError) is transient too."""
    monkeypatch.setattr("ichor_brain.runner_client.asyncio.sleep", lambda *a, **kw: _no_op())
    state = {"polls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return _accepted()
        state["polls"] += 1
        if state["polls"] == 1:
            raise httpx.ReadError("simulated connection drop")
        return _done()

    with patch("ichor_brain.runner_client.httpx.AsyncClient", _run_with_handler(handler)):
        resp = await _make_client().run(RunnerCall(prompt="p", system="s"))
    assert resp.text == "ok briefing"
    assert state["polls"] == 2


@pytest.mark.asyncio
async def test_async_poll_gives_up_after_max_consecutive(monkeypatch) -> None:
    """Persistent 502s (runner truly unreachable) eventually raise."""
    monkeypatch.setattr("ichor_brain.runner_client.asyncio.sleep", lambda *a, **kw: _no_op())
    state = {"polls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return _accepted()
        state["polls"] += 1
        return httpx.Response(502, text="origin down")

    with patch("ichor_brain.runner_client.httpx.AsyncClient", _run_with_handler(handler)):
        with pytest.raises(httpx.HTTPStatusError):
            await _make_client().run(RunnerCall(prompt="p", system="s"))
    # tolerated _MAX_CONSECUTIVE_POLL_ERRORS, then raised on the next one
    assert state["polls"] == _MAX_CONSECUTIVE_POLL_ERRORS + 1


@pytest.mark.asyncio
async def test_async_poll_404_aborts_immediately(monkeypatch) -> None:
    """404 = task expired/GC'd = a real failure, not a transient blip."""
    monkeypatch.setattr("ichor_brain.runner_client.asyncio.sleep", lambda *a, **kw: _no_op())
    state = {"polls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return _accepted()
        state["polls"] += 1
        return httpx.Response(404, text="task_id unknown")

    with patch("ichor_brain.runner_client.httpx.AsyncClient", _run_with_handler(handler)):
        with pytest.raises(httpx.HTTPStatusError):
            await _make_client().run(RunnerCall(prompt="p", system="s"))
    assert state["polls"] == 1  # no retry on 404


@pytest.mark.asyncio
async def test_async_poll_recovers_then_succeeds_resets_counter(monkeypatch) -> None:
    """A transient burst followed by a success must reset the error counter,
    so a later second burst is also tolerated (not cumulative)."""
    monkeypatch.setattr("ichor_brain.runner_client.asyncio.sleep", lambda *a, **kw: _no_op())
    state = {"polls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return _accepted()
        state["polls"] += 1
        # burst of 8 (<=12), a running success (reset), burst of 8 again, then done
        if 1 <= state["polls"] <= 8:
            return httpx.Response(503, text="blip A")
        if state["polls"] == 9:
            return _running()
        if 10 <= state["polls"] <= 17:
            return httpx.Response(502, text="blip B")
        return _done()

    with patch("ichor_brain.runner_client.httpx.AsyncClient", _run_with_handler(handler)):
        resp = await _make_client().run(RunnerCall(prompt="p", system="s"))
    assert resp.text == "ok briefing"
    assert state["polls"] == 18


# ─────────────────────────────────────────────────────────────────────────
# Session 02 (2026-06-05) — classify-and-raise on a FAILED inner result.
# Before this, the async path returned RunnerResponse(text="") for a runner
# status=timeout/subprocess_error or an empty briefing, disguising a failed
# generation as an empty-but-"successful" card. Now it raises so the
# orchestrator surfaces the TRUE cause.
# ─────────────────────────────────────────────────────────────────────────


def _done_failed(status: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "status": "done",
            "result": {"status": status, "error_message": "boom", "duration_ms": 5},
        },
    )


def _done_empty() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "status": "done",
            "result": {"status": "success", "briefing_markdown": "", "duration_ms": 5},
        },
    )


@pytest.mark.asyncio
async def test_async_raises_on_runner_timeout_status(monkeypatch) -> None:
    """Runner inner status=timeout → RunnerResultError, not empty success."""
    monkeypatch.setattr("ichor_brain.runner_client.asyncio.sleep", lambda *a, **kw: _no_op())
    state = {"polls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return _accepted()
        state["polls"] += 1
        return _running() if state["polls"] < 2 else _done_failed("timeout")

    with patch("ichor_brain.runner_client.httpx.AsyncClient", _run_with_handler(handler)):
        with pytest.raises(RunnerResultError):
            await _make_client().run(RunnerCall(prompt="p", system="s"))


@pytest.mark.asyncio
async def test_async_raises_on_subprocess_error_status(monkeypatch) -> None:
    """Runner inner status=subprocess_error → RunnerResultError."""
    monkeypatch.setattr("ichor_brain.runner_client.asyncio.sleep", lambda *a, **kw: _no_op())

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return _accepted()
        return _done_failed("subprocess_error")

    with patch("ichor_brain.runner_client.httpx.AsyncClient", _run_with_handler(handler)):
        with pytest.raises(RunnerResultError):
            await _make_client().run(RunnerCall(prompt="p", system="s"))


@pytest.mark.asyncio
async def test_async_raises_on_empty_markdown(monkeypatch) -> None:
    """Runner status=success but empty briefing_markdown → RunnerResultError
    (silent-failure guard — a fresh-but-empty card is the worst case)."""
    monkeypatch.setattr("ichor_brain.runner_client.asyncio.sleep", lambda *a, **kw: _no_op())

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return _accepted()
        return _done_empty()

    with patch("ichor_brain.runner_client.httpx.AsyncClient", _run_with_handler(handler)):
        with pytest.raises(RunnerResultError):
            await _make_client().run(RunnerCall(prompt="p", system="s"))
