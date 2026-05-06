"""Tests for HttpRunnerClient retry envelope (added 2026-05-06).

Covers the 503/429 transparent retry that prevents the briefing-tick →
session-cards-tick collision from killing every batch since
2026-05-04. See SESSION_LOG_2026-05-06.md root-cause analysis.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
from ichor_brain.runner_client import HttpRunnerClient, RunnerCall


async def _no_op() -> None:
    return None


def _make_client(transport: httpx.MockTransport) -> HttpRunnerClient:
    return HttpRunnerClient(
        base_url="https://runner.example.com",
        cf_access_client_id="id",
        cf_access_client_secret="secret",
        timeout_sec=5.0,
    )


def _success_body() -> dict:
    return {
        "task_id": "00000000-0000-0000-0000-000000000000",
        "status": "success",
        "briefing_markdown": "ok briefing",
        "duration_ms": 1234,
    }


@pytest.mark.asyncio
async def test_first_call_success(monkeypatch) -> None:
    monkeypatch.setattr("ichor_brain.runner_client.asyncio.sleep", lambda *a, **kw: _no_op())
    state = {"calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        return httpx.Response(200, json=_success_body())

    transport = httpx.MockTransport(handler)
    real_client_cls = httpx.AsyncClient

    def _factory(**kw):
        kw["transport"] = transport
        return real_client_cls(**kw)

    with patch("ichor_brain.runner_client.httpx.AsyncClient", _factory):
        client = _make_client(transport)
        resp = await client.run(RunnerCall(prompt="p", system="s"))
    assert resp.text == "ok briefing"
    assert state["calls"] == 1  # no retry needed


@pytest.mark.asyncio
async def test_retries_on_503_then_succeeds(monkeypatch) -> None:
    """503 'Another briefing in flight' should trigger a transparent retry."""
    monkeypatch.setattr("ichor_brain.runner_client.asyncio.sleep", lambda *a, **kw: _no_op())
    state = {"calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        if state["calls"] <= 2:
            return httpx.Response(503, text='{"detail":"Another briefing in flight"}')
        return httpx.Response(200, json=_success_body())

    transport = httpx.MockTransport(handler)
    real_client_cls = httpx.AsyncClient

    def _factory(**kw):
        kw["transport"] = transport
        return real_client_cls(**kw)

    with patch("ichor_brain.runner_client.httpx.AsyncClient", _factory):
        client = _make_client(transport)
        resp = await client.run(RunnerCall(prompt="p", system="s"))
    assert resp.text == "ok briefing"
    assert state["calls"] == 3  # two 503s + one success


@pytest.mark.asyncio
async def test_retries_on_429_then_succeeds(monkeypatch) -> None:
    """429 'rate-limited' should trigger the same retry envelope."""
    monkeypatch.setattr("ichor_brain.runner_client.asyncio.sleep", lambda *a, **kw: _no_op())
    state = {"calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        if state["calls"] == 1:
            return httpx.Response(429, text='{"detail":"rate limited"}')
        return httpx.Response(200, json=_success_body())

    transport = httpx.MockTransport(handler)
    real_client_cls = httpx.AsyncClient

    def _factory(**kw):
        kw["transport"] = transport
        return real_client_cls(**kw)

    with patch("ichor_brain.runner_client.httpx.AsyncClient", _factory):
        client = _make_client(transport)
        resp = await client.run(RunnerCall(prompt="p", system="s"))
    assert state["calls"] == 2


@pytest.mark.asyncio
async def test_no_retry_on_524_cloudflare_timeout(monkeypatch) -> None:
    """524 = Cloudflare 100s edge timeout. Retrying would hit the same
    wall — fail fast so caller can fallback / escalate."""
    monkeypatch.setattr("ichor_brain.runner_client.asyncio.sleep", lambda *a, **kw: _no_op())
    state = {"calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        return httpx.Response(524, text="cloudflare timeout")

    transport = httpx.MockTransport(handler)
    real_client_cls = httpx.AsyncClient

    def _factory(**kw):
        kw["transport"] = transport
        return real_client_cls(**kw)

    with patch("ichor_brain.runner_client.httpx.AsyncClient", _factory):
        client = _make_client(transport)
        with pytest.raises(httpx.HTTPStatusError):
            await client.run(RunnerCall(prompt="p", system="s"))
    assert state["calls"] == 1  # no retry on 524


@pytest.mark.asyncio
async def test_raises_after_retries_exhausted(monkeypatch) -> None:
    """If 503 keeps coming, we should exhaust the budget and raise."""
    monkeypatch.setattr("ichor_brain.runner_client.asyncio.sleep", lambda *a, **kw: _no_op())
    state = {"calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        return httpx.Response(503, text="busy")

    transport = httpx.MockTransport(handler)
    real_client_cls = httpx.AsyncClient

    def _factory(**kw):
        kw["transport"] = transport
        return real_client_cls(**kw)

    with patch("ichor_brain.runner_client.httpx.AsyncClient", _factory):
        client = _make_client(transport)
        with pytest.raises(httpx.HTTPStatusError):
            await client.run(RunnerCall(prompt="p", system="s"))
    assert state["calls"] == 4  # initial + 3 retries
