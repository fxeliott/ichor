"""Regression tests for subprocess_runner — guards against re-introducing
the Windows `WinError 206` bug fixed by ADR-054.

The bug : passing the full `prompt` (up to 200 KB) as an `argv` argument
to `claude -p <prompt>` overflows the Windows CreateProcessW 32 768-char
limit on lpCommandLine. The fix : pipe `prompt` via stdin and keep only
a short task description in argv.

These tests verify both halves of the contract :
  1. the prompt is NOT in argv (no large strings on the command line)
  2. the prompt IS sent via stdin to the subprocess
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from ichor_claude_runner.config import Settings
from ichor_claude_runner.subprocess_runner import run_claude


@pytest.fixture()
def fake_settings(tmp_path) -> Settings:
    persona = tmp_path / "ichor.md"
    persona.write_text("# test persona\nbe terse.\n", encoding="utf-8")
    workdir = tmp_path / "work"
    return Settings(
        environment="development",
        require_cf_access=False,
        persona_file=persona,
        workdir=workdir,
        claude_binary="claude",
        claude_timeout_sec=30,
    )


def _capture_subprocess(monkeypatch, *, stdout_json: dict, returncode: int = 0):
    """Patch asyncio.create_subprocess_exec and return a recorder dict
    populated on call so tests can assert on cmd/stdin args."""
    captured: dict[str, Any] = {}

    async def fake_exec(*cmd, stdin=None, stdout=None, stderr=None, cwd=None, **kw):
        captured["cmd"] = list(cmd)
        captured["stdin_kw"] = stdin
        proc = MagicMock()
        proc.returncode = returncode

        async def fake_communicate(input=None):
            captured["stdin_input"] = input
            return (json.dumps(stdout_json).encode("utf-8"), b"")

        proc.communicate = fake_communicate
        proc.kill = MagicMock()
        proc.wait = AsyncMock(return_value=None)
        return proc

    import asyncio

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    return captured


@pytest.mark.asyncio
async def test_run_claude_pipes_prompt_via_stdin_not_argv(monkeypatch, fake_settings) -> None:
    """ADR-054 — large prompt must travel via stdin, not argv.

    Asserts the full prompt is present in `subprocess.communicate(input=...)`
    and absent from the argv list.
    """
    big_prompt = "X" * 30_000  # 30 KB — would overflow Windows 32K argv on its own
    captured = _capture_subprocess(
        monkeypatch,
        stdout_json={"type": "result", "subtype": "success", "result": "ok"},
    )

    await run_claude(prompt=big_prompt, settings=fake_settings)

    cmd = captured["cmd"]
    # Big prompt is NOT anywhere in argv
    assert big_prompt not in cmd
    assert all(big_prompt not in arg for arg in cmd if isinstance(arg, str))
    # argv stays small even with a huge prompt
    assert sum(len(a) for a in cmd if isinstance(a, str)) < 16_000

    # Big prompt IS what reached communicate(input=...)
    assert captured["stdin_input"] == big_prompt.encode("utf-8")


@pytest.mark.asyncio
async def test_run_claude_argv_short_and_persona_inline(monkeypatch, fake_settings) -> None:
    """argv must contain `-p <short task wrapper>` and the persona via
    `--append-system-prompt`. The task wrapper text MUST instruct claude
    to read stdin so the model knows where the context lives."""
    captured = _capture_subprocess(
        monkeypatch,
        stdout_json={"type": "result", "subtype": "success", "result": "ok"},
    )

    await run_claude(prompt="hello", settings=fake_settings)

    cmd = captured["cmd"]
    assert "-p" in cmd
    p_idx = cmd.index("-p")
    p_value = cmd[p_idx + 1]
    assert "stdin" in p_value.lower(), (
        f"-p task wrapper must mention stdin so claude reads it. Got: {p_value!r}"
    )
    assert "--append-system-prompt" in cmd
    sys_idx = cmd.index("--append-system-prompt")
    assert "test persona" in cmd[sys_idx + 1]


@pytest.mark.asyncio
async def test_run_claude_passes_model_and_effort(monkeypatch, fake_settings) -> None:
    """--model and --effort must reach the CLI verbatim."""
    captured = _capture_subprocess(
        monkeypatch,
        stdout_json={"type": "result", "subtype": "success", "result": "ok"},
    )

    await run_claude(prompt="x", settings=fake_settings, model="haiku", effort="low")

    cmd = captured["cmd"]
    assert cmd[cmd.index("--model") + 1] == "haiku"
    assert cmd[cmd.index("--effort") + 1] == "low"


@pytest.mark.asyncio
async def test_run_claude_returns_parsed_json(monkeypatch, fake_settings) -> None:
    expected = {"type": "result", "subtype": "success", "result": "the answer"}
    _capture_subprocess(monkeypatch, stdout_json=expected)

    out = await run_claude(prompt="x", settings=fake_settings)
    assert out == expected


@pytest.mark.asyncio
async def test_run_claude_raises_on_nonzero_exit(monkeypatch, fake_settings) -> None:
    from ichor_claude_runner.subprocess_runner import ClaudeSubprocessError

    _capture_subprocess(
        monkeypatch,
        stdout_json={},
        returncode=2,
    )

    with pytest.raises(ClaudeSubprocessError):
        await run_claude(prompt="x", settings=fake_settings)
