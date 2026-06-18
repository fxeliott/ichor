"""S02 socle — run_briefing._post_to_claude_runner poll-loop resilience.

run_briefing.py used to hand-roll its OWN async submit+poll loop that, unlike
the hardened HttpRunnerClient, aborted on the FIRST non-2xx (submit or poll)
and never routed the completed result through the silent-failure guard. So a
single cloudflared blip killed a full in-flight Opus xhigh briefing, and an
empty/failed runner result was persisted as a "completed" briefing.

This pins the now-shared resilience contract (the briefing CLI reuses the
same _TRANSIENT_STATUSES / _POLL_RETRY_STATUSES / _MAX_CONSECUTIVE_POLL_ERRORS
/ _unwrap_runner_result primitives as the runner client). Mirrors
packages/ichor_brain/tests/test_runner_client_async.py.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import httpx
import pytest
from ichor_api.cli.run_briefing import _post_to_claude_runner
from ichor_brain.runner_client import _MAX_CONSECUTIVE_POLL_ERRORS, RunnerResultError

_TASK_ID = "11111111-1111-1111-1111-111111111111"


class _Settings:
    claude_runner_url = "https://runner.example.com"
    cf_access_client_id = "id"
    cf_access_client_secret = "secret"


async def _no_op(*_a: Any, **_kw: Any) -> None:
    return None


def _accepted() -> httpx.Response:
    return httpx.Response(
        202,
        json={"task_id": _TASK_ID, "poll_url": f"/v1/briefing-task/async/{_TASK_ID}"},
    )


def _running() -> httpx.Response:
    return httpx.Response(200, json={"status": "running", "result": None})


def _done(markdown: str = "ok briefing") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "status": "done",
            "result": {
                "status": "success",
                "briefing_markdown": markdown,
                "raw_claude_json": {"x": 1},
                "duration_ms": 4242,
                "task_id": _TASK_ID,
            },
        },
    )


def _done_inner(result: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json={"status": "done", "result": result})


def _client_factory(handler):
    transport = httpx.MockTransport(handler)
    real_cls = httpx.AsyncClient

    def _factory(**kw):
        kw["transport"] = transport
        return real_cls(**kw)

    return _factory


async def _call(handler) -> dict[str, Any]:
    with patch("ichor_api.cli.run_briefing.httpx.AsyncClient", _client_factory(handler)):
        return await _post_to_claude_runner(_Settings(), "pre_ny", ["EUR_USD"], "context markdown")


@pytest.fixture(autouse=True)
def _patch_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ichor_api.cli.run_briefing.asyncio.sleep", _no_op)


@pytest.mark.asyncio
async def test_happy_path_returns_full_envelope() -> None:
    """The full inner result envelope (task_id / briefing_markdown /
    raw_claude_json / duration_ms / status) must survive intact so main()'s
    persistence at lines 553-561 is unchanged."""
    state = {"polls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return _accepted()
        state["polls"] += 1
        return _running() if state["polls"] < 2 else _done()

    result = await _call(handler)
    assert result["status"] == "success"
    assert result["briefing_markdown"] == "ok briefing"
    assert result["duration_ms"] == 4242
    assert result["task_id"] == _TASK_ID
    assert result["raw_claude_json"] == {"x": 1}
    assert state["polls"] == 2


@pytest.mark.asyncio
async def test_poll_tolerates_transient_502() -> None:
    state = {"polls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return _accepted()
        state["polls"] += 1
        if state["polls"] == 1:
            return _running()
        if state["polls"] in (2, 3):
            return httpx.Response(502, text="cloudflared: EOF")
        return _done()

    result = await _call(handler)
    assert result["briefing_markdown"] == "ok briefing"
    assert state["polls"] == 4  # the two 502s were tolerated, not fatal


@pytest.mark.asyncio
async def test_poll_tolerates_transport_error() -> None:
    state = {"polls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return _accepted()
        state["polls"] += 1
        if state["polls"] == 1:
            raise httpx.ReadError("simulated connection drop")
        return _done()

    result = await _call(handler)
    assert result["briefing_markdown"] == "ok briefing"
    assert state["polls"] == 2


@pytest.mark.asyncio
async def test_poll_gives_up_after_max_consecutive() -> None:
    state = {"polls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return _accepted()
        state["polls"] += 1
        return httpx.Response(502, text="origin down")

    with pytest.raises(httpx.HTTPStatusError):
        await _call(handler)
    assert state["polls"] == _MAX_CONSECUTIVE_POLL_ERRORS + 1


@pytest.mark.asyncio
async def test_poll_404_raises_classified_runner_result_error() -> None:
    state = {"polls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return _accepted()
        state["polls"] += 1
        return httpx.Response(404, text="task unknown")

    with pytest.raises(RunnerResultError, match="unknown to the runner"):
        await _call(handler)
    assert state["polls"] == 1  # no retry on 404 — fail fast but classified


@pytest.mark.asyncio
async def test_submit_retries_transient_then_succeeds() -> None:
    state = {"posts": 0, "polls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            state["posts"] += 1
            if state["posts"] == 1:
                return httpx.Response(503, text="busy")
            return _accepted()
        state["polls"] += 1
        return _done()

    result = await _call(handler)
    assert result["briefing_markdown"] == "ok briefing"
    assert state["posts"] == 2  # first 503 retried, second accepted


@pytest.mark.asyncio
async def test_done_with_empty_briefing_markdown_raises() -> None:
    """A 'done' task whose inner result has empty briefing_markdown must raise
    (silent-failure guard) so main() records claude_runner_call_failed instead
    of persisting a fresh-but-empty 'completed' briefing."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return _accepted()
        return _done_inner({"status": "success", "briefing_markdown": "   ", "duration_ms": 1})

    with pytest.raises(RunnerResultError):
        await _call(handler)


@pytest.mark.asyncio
async def test_done_with_runner_failure_status_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return _accepted()
        return _done_inner({"status": "timeout", "error_message": "boom", "duration_ms": 1})

    with pytest.raises(RunnerResultError):
        await _call(handler)


@pytest.mark.asyncio
async def test_task_error_status_raises_runtime_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return _accepted()
        return httpx.Response(200, json={"status": "error", "error": "crashed"})

    with pytest.raises(RuntimeError, match="crashed"):
        await _call(handler)


@pytest.mark.asyncio
async def test_submit_gives_up_after_persistent_transient() -> None:
    """A transient 503 on EVERY submit attempt exhausts the 5/15/45s backoff
    and raises (the briefing window does not silently hang)."""
    state = {"posts": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"  # never reaches the poll phase
        state["posts"] += 1
        return httpx.Response(503, text="always busy")

    with pytest.raises(httpx.HTTPStatusError):
        await _call(handler)
    # (0.0,) + (5, 15, 45) = 4 attempts, all 503.
    assert state["posts"] == 4


@pytest.mark.asyncio
async def test_submit_fails_fast_on_non_transient_4xx() -> None:
    """A non-transient 4xx on submit (e.g. 400 bad request) fails immediately
    — no backoff retry on a deterministic client error."""
    state = {"posts": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        state["posts"] += 1
        return httpx.Response(400, text="bad request")

    with pytest.raises(httpx.HTTPStatusError):
        await _call(handler)
    assert state["posts"] == 1  # no retry on a non-transient status
