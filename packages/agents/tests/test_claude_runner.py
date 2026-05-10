"""Tests for the Claude path of FallbackChain (ADR-021).

Covers:
  - ClaudeRunnerConfig.from_env: returns None when env incomplete,
    returns config when all 3 vars set
  - _strip_json_fence: handles plain JSON, ```json``` fence, and ``` fence
  - call_agent_task: parses success body, validates Pydantic, raises
    on HTTP error / status!=success / invalid JSON
  - FallbackChain integration: tries Claude first, falls back on
    ClaudeRunnerError

No network calls — httpx is mocked via httpx.MockTransport.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import httpx
import pytest
from ichor_agents.claude_runner import (
    ClaudeRunnerConfig,
    ClaudeRunnerError,
    ClaudeRunnerOutputError,
    _strip_json_fence,
    call_agent_task,
)
from ichor_agents.fallback import AllProvidersFailed, FallbackChain
from pydantic import BaseModel, Field


class _Out(BaseModel):
    answer: str = Field(min_length=1)
    score: float = Field(ge=0.0, le=1.0)


# ── ClaudeRunnerConfig.from_env ────────────────────────────────────


def test_from_env_returns_none_when_url_missing() -> None:
    with patch.dict(
        os.environ,
        {
            "ICHOR_API_CLAUDE_RUNNER_URL": "",
            "ICHOR_API_CF_ACCESS_CLIENT_ID": "id",
            "ICHOR_API_CF_ACCESS_CLIENT_SECRET": "secret",
        },
        clear=True,
    ):
        assert ClaudeRunnerConfig.from_env() is None


def test_from_env_returns_config_without_cf_creds_when_url_set() -> None:
    """Runner can be deployed in dev mode (no CF Access). When the URL
    is set, we route through Claude even without service-token creds —
    the runner itself decides whether to enforce auth."""
    with patch.dict(
        os.environ,
        {
            "ICHOR_API_CLAUDE_RUNNER_URL": "https://runner.example.com",
            "ICHOR_API_CF_ACCESS_CLIENT_ID": "",
            "ICHOR_API_CF_ACCESS_CLIENT_SECRET": "",
        },
        clear=True,
    ):
        cfg = ClaudeRunnerConfig.from_env()
    assert cfg is not None
    assert cfg.runner_url == "https://runner.example.com"
    assert cfg.cf_access_client_id is None
    assert cfg.cf_access_client_secret is None


def test_from_env_returns_config_when_all_set() -> None:
    with patch.dict(
        os.environ,
        {
            "ICHOR_API_CLAUDE_RUNNER_URL": "https://runner.example.com/",
            "ICHOR_API_CF_ACCESS_CLIENT_ID": "id123",
            "ICHOR_API_CF_ACCESS_CLIENT_SECRET": "secret456",
        },
        clear=True,
    ):
        cfg = ClaudeRunnerConfig.from_env(model="haiku", effort="low")
    assert cfg is not None
    assert cfg.runner_url == "https://runner.example.com"  # trailing slash stripped
    assert cfg.cf_access_client_id == "id123"
    assert cfg.cf_access_client_secret == "secret456"
    assert cfg.model == "haiku"
    assert cfg.effort == "low"


# ── _strip_json_fence ────────────────────────────────────────────────


def test_strip_fence_plain_json() -> None:
    assert _strip_json_fence('{"a": 1}') == '{"a": 1}'


def test_strip_fence_with_json_label() -> None:
    text = '```json\n{"a": 1}\n```'
    assert _strip_json_fence(text) == '{"a": 1}'


def test_strip_fence_without_label() -> None:
    text = '```\n{"a": 1}\n```'
    assert _strip_json_fence(text) == '{"a": 1}'


def test_strip_fence_handles_leading_trailing_whitespace() -> None:
    text = '  \n```json\n{"x": "y"}\n```  \n'
    assert _strip_json_fence(text) == '{"x": "y"}'


# ── call_agent_task ─────────────────────────────────────────────────


async def _no_op() -> None:
    """Awaitable no-op for monkey-patching asyncio.sleep in retry tests."""
    return None


def _cfg() -> ClaudeRunnerConfig:
    return ClaudeRunnerConfig(
        runner_url="https://runner.example.com",
        cf_access_client_id="id",
        cf_access_client_secret="secret",
        model="sonnet",
        effort="medium",
        timeout_sec=5.0,
    )


@pytest.mark.asyncio
async def test_call_agent_task_returns_validated_pydantic() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        assert b'"system":"sys"' in body
        # Prompt is enriched with the JSON schema when output_type is set,
        # so we just check the original user text appears at the start.
        assert b'"prompt":"user-prompt' in body
        assert b"validates against the following schema" in body  # schema hint appended
        assert request.headers["CF-Access-Client-Id"] == "id"
        return httpx.Response(
            200,
            json={
                "task_id": "00000000-0000-0000-0000-000000000000",
                "status": "success",
                "output_text": '{"answer": "ok", "score": 0.42}',
                "duration_ms": 1234,
            },
        )

    transport = httpx.MockTransport(handler)
    real_client_cls = httpx.AsyncClient

    def _factory(**kw):
        kw["transport"] = transport
        return real_client_cls(**kw)

    with patch("ichor_agents.claude_runner.httpx.AsyncClient", _factory):
        out = await call_agent_task(_cfg(), system="sys", prompt="user-prompt", output_type=_Out)

    assert isinstance(out, _Out)
    assert out.answer == "ok"
    assert out.score == 0.42


@pytest.mark.asyncio
async def test_call_agent_task_returns_text_when_no_output_type() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "task_id": "00000000-0000-0000-0000-000000000000",
                "status": "success",
                "output_text": "free-form markdown",
                "duration_ms": 50,
            },
        )

    transport = httpx.MockTransport(handler)
    real_client_cls = httpx.AsyncClient

    def _factory(**kw):
        kw["transport"] = transport
        return real_client_cls(**kw)

    with patch("ichor_agents.claude_runner.httpx.AsyncClient", _factory):
        out = await call_agent_task(_cfg(), system="sys", prompt="p", output_type=None)
    assert out == "free-form markdown"


@pytest.mark.asyncio
async def test_call_agent_task_raises_on_http_error() -> None:
    """Non-retryable HTTP errors (anything ≥ 400 except 429/503) fail fast."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    transport = httpx.MockTransport(handler)
    real_client_cls = httpx.AsyncClient

    def _factory(**kw):
        kw["transport"] = transport
        return real_client_cls(**kw)

    with patch("ichor_agents.claude_runner.httpx.AsyncClient", _factory):
        with pytest.raises(ClaudeRunnerError, match="HTTP 500"):
            await call_agent_task(_cfg(), system="s", prompt="p", output_type=_Out)


@pytest.mark.asyncio
async def test_call_agent_task_retries_on_503_then_succeeds(monkeypatch) -> None:
    """503 = runner busy; we should retry transparently."""
    monkeypatch.setattr("ichor_agents.claude_runner.asyncio.sleep", lambda *a, **kw: _no_op())

    state = {"calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        if state["calls"] == 1:
            return httpx.Response(503, text='{"detail":"Another task in flight"}')
        return httpx.Response(
            200,
            json={
                "task_id": "00000000-0000-0000-0000-000000000000",
                "status": "success",
                "output_text": '{"answer": "ok-after-retry", "score": 0.5}',
                "duration_ms": 50,
            },
        )

    transport = httpx.MockTransport(handler)
    real_client_cls = httpx.AsyncClient

    def _factory(**kw):
        kw["transport"] = transport
        return real_client_cls(**kw)

    with patch("ichor_agents.claude_runner.httpx.AsyncClient", _factory):
        out = await call_agent_task(_cfg(), system="s", prompt="p", output_type=_Out)
    assert out.answer == "ok-after-retry"
    assert state["calls"] == 2  # one 503 + one success


@pytest.mark.asyncio
async def test_call_agent_task_raises_when_status_not_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "task_id": "00000000-0000-0000-0000-000000000000",
                "status": "subprocess_error",
                "error_message": "claude CLI exited 2",
                "duration_ms": 12,
            },
        )

    transport = httpx.MockTransport(handler)
    real_client_cls = httpx.AsyncClient

    def _factory(**kw):
        kw["transport"] = transport
        return real_client_cls(**kw)

    with patch("ichor_agents.claude_runner.httpx.AsyncClient", _factory):
        with pytest.raises(ClaudeRunnerError, match="subprocess_error"):
            await call_agent_task(_cfg(), system="s", prompt="p", output_type=_Out)


@pytest.mark.asyncio
async def test_call_agent_task_raises_when_output_invalid_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "task_id": "00000000-0000-0000-0000-000000000000",
                "status": "success",
                "output_text": "this is not json at all",
                "duration_ms": 10,
            },
        )

    transport = httpx.MockTransport(handler)
    real_client_cls = httpx.AsyncClient

    def _factory(**kw):
        kw["transport"] = transport
        return real_client_cls(**kw)

    with patch("ichor_agents.claude_runner.httpx.AsyncClient", _factory):
        with pytest.raises(ClaudeRunnerOutputError):
            await call_agent_task(_cfg(), system="s", prompt="p", output_type=_Out)


# ── FallbackChain integration ──────────────────────────────────────


@pytest.mark.asyncio
async def test_fallback_tries_claude_first_when_configured() -> None:
    """Given Claude succeeds, the chain returns the Claude output and
    never invokes any fallback provider."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "task_id": "00000000-0000-0000-0000-000000000000",
                "status": "success",
                "output_text": '{"answer": "via-claude", "score": 0.9}',
                "duration_ms": 100,
            },
        )

    transport = httpx.MockTransport(handler)
    chain = FallbackChain(
        providers=(),  # no fallback providers — proves Claude is used
        system_prompt="test system prompt over 100 chars " * 5,
        output_type=_Out,
        claude=_cfg(),
        # W67 default is async polling ; the mock above returns the
        # sync-shaped immediate-success body. Force sync path so the
        # mock and the code under test agree on the wire format.
        use_async_endpoint=False,
    )

    real_client_cls = httpx.AsyncClient

    def _factory(**kw):
        kw["transport"] = transport
        return real_client_cls(**kw)

    with patch("ichor_agents.claude_runner.httpx.AsyncClient", _factory):
        out = await chain.run("user prompt")

    assert isinstance(out, _Out)
    assert out.answer == "via-claude"


@pytest.mark.asyncio
async def test_fallback_raises_when_claude_fails_and_no_providers() -> None:
    """When Claude fails and there's nothing to fall back on, the chain
    raises AllProvidersFailed and includes 'claude' in the attempts."""

    # 500 = non-retryable; fails fast so the test doesn't burn the
    # 65 s retry budget set up for transient 503/429.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="runner down")

    transport = httpx.MockTransport(handler)
    chain = FallbackChain(
        providers=(),
        system_prompt="test system prompt over 100 chars " * 5,
        output_type=_Out,
        claude=_cfg(),
    )

    real_client_cls = httpx.AsyncClient

    def _factory(**kw):
        kw["transport"] = transport
        return real_client_cls(**kw)

    with patch("ichor_agents.claude_runner.httpx.AsyncClient", _factory):
        with pytest.raises(AllProvidersFailed) as exc:
            await chain.run("user prompt")

    names = [name for name, _err in exc.value.attempts]
    assert "claude" in names
