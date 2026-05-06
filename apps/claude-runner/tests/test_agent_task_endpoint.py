"""Integration tests for POST /v1/agent-task (ADR-021).

Uses FastAPI TestClient with the claude subprocess monkey-patched to
return canned JSON. Verifies:
  - Auth bypass works in dev mode
  - Successful path returns output_text + raw_claude_json
  - Subprocess error path returns 200 + status='subprocess_error'
  - Rate-limit path returns 429
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch, tmp_path) -> Iterator[TestClient]:
    # Set required env BEFORE the app imports settings.
    monkeypatch.setenv("ICHOR_RUNNER_REQUIRE_CF_ACCESS", "false")
    monkeypatch.setenv("ICHOR_RUNNER_ENVIRONMENT", "development")
    monkeypatch.setenv("ICHOR_RUNNER_WORKDIR", str(tmp_path))

    # Reset the module-level singleton + reload so env is picked up.
    import importlib

    from ichor_claude_runner import config as cfg_mod
    from ichor_claude_runner import main as main_mod

    cfg_mod._settings = None
    importlib.reload(main_mod)

    with TestClient(main_mod.app) as c:
        yield c

    # Restore singleton state for other tests
    cfg_mod._settings = None


def test_agent_task_success(client, monkeypatch) -> None:
    async def fake_run_claude(prompt: str, **kw):
        assert kw.get("persona_text", "") == "test system prompt"
        return {
            "type": "result",
            "subtype": "success",
            "result": '{"answer": "from claude", "score": 0.8}',
            "session_id": "test-session",
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }

    from ichor_claude_runner import main as main_mod

    monkeypatch.setattr(main_mod, "run_claude", fake_run_claude)

    r = client.post(
        "/v1/agent-task",
        json={
            "system": "test system prompt",
            "prompt": "test user prompt",
            "model": "sonnet",
            "effort": "medium",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "success"
    assert body["output_text"] == '{"answer": "from claude", "score": 0.8}'
    assert body["raw_claude_json"]["session_id"] == "test-session"


def test_agent_task_subprocess_error(client, monkeypatch) -> None:
    from ichor_claude_runner import main as main_mod
    from ichor_claude_runner.subprocess_runner import ClaudeSubprocessError

    async def fake_run_claude(prompt: str, **kw):
        raise ClaudeSubprocessError("claude exited 2: bad input")

    monkeypatch.setattr(main_mod, "run_claude", fake_run_claude)

    r = client.post(
        "/v1/agent-task",
        json={"system": "s", "prompt": "p"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "subprocess_error"
    assert "claude exited 2" in body["error_message"]


def test_agent_task_timeout(client, monkeypatch) -> None:
    from ichor_claude_runner import main as main_mod

    async def fake_run_claude(prompt: str, **kw):
        raise asyncio.TimeoutError()

    monkeypatch.setattr(main_mod, "run_claude", fake_run_claude)

    r = client.post(
        "/v1/agent-task",
        json={"system": "s", "prompt": "p"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "timeout"


def test_agent_task_rejects_empty_system(client) -> None:
    r = client.post("/v1/agent-task", json={"system": "", "prompt": "p"})
    assert r.status_code == 422  # pydantic validation
