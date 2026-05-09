"""Wrapper around `claude -p` — handles subprocess lifecycle, timeout,
JSON parsing, error recovery.

Why subprocess instead of Anthropic SDK:
  Eliot uses Claude Max 20x (flat $200/mo). The Max subscription gates access
  via OAuth tokens stored locally by `claude login`. There's no programmatic
  way to use this auth from the Anthropic SDK — we must shell out to the same
  `claude` binary that he uses interactively.

  This is a deliberate Voie D choice (see docs/decisions/ADR-009).

W86 STEP-4 (Capability 5 wiring, ADR-077) — when `mcp_config` is
provided, the wrapper writes it to a temp JSON and adds
`--mcp-config <path> --strict-mcp-config --allowedTools ... --max-turns N`
to the Claude CLI invocation. The agentic tool_use loop is driven
entirely by Claude CLI itself ; the orchestrator stays single-shot
(see ADR-077 §"Loop ownership").
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import structlog

from .config import Settings

log = structlog.get_logger(__name__)


class ClaudeSubprocessError(RuntimeError):
    """Raised on non-zero exit, JSON parse error, or empty output."""


async def run_claude(
    prompt: str,
    settings: Settings,
    *,
    model: str = "opus",
    effort: str = "medium",
    persona_text: str | None = None,
    mcp_config: dict[str, Any] | None = None,
    allowed_tools: Sequence[str] | None = None,
    max_turns: int = 0,
) -> dict[str, Any]:
    """Run `claude -p <prompt>` and return the parsed JSON envelope.

    Args:
        prompt: User-side prompt (the request).
        settings: runtime config.
        model: opus / sonnet / haiku (or full name like 'claude-sonnet-4-6').
        effort: low / medium / high / xhigh / max — quality vs latency knob.
            Voie D (ADR-009) uses Max 20x flat — Anthropic-side weekly caps
            are the only quota. We don't pass --max-tokens or --temperature
            (the Claude Code CLI doesn't accept them; those are SDK-only).
        persona_text: optional override for the system prompt. Defaults to
            settings.persona_file content.

    Returns:
        Parsed JSON dict. Claude Code -p --output-format=json shape:
            {
              "type": "result",
              "subtype": "success",
              "result": "<the model's text>",
              "session_id": "...",
              "usage": {"input_tokens": ..., "output_tokens": ...},
              "total_cost_usd": ...,
              ...
            }

    Raises:
        ClaudeSubprocessError on any failure.
        asyncio.TimeoutError if the subprocess exceeds claude_timeout_sec.
    """
    workdir = settings.workdir
    workdir.mkdir(parents=True, exist_ok=True)

    if persona_text is None:
        if not settings.persona_file.exists():
            raise ClaudeSubprocessError(
                f"Persona file not found at {settings.persona_file} — cannot proceed"
            )
        persona_text = settings.persona_file.read_text(encoding="utf-8")

    # ADR-054 — pipe `prompt` via stdin instead of argv to bypass the
    # Windows CreateProcessW 32 768-char `lpCommandLine` limit. Persona
    # (~7 KB) stays in argv via --append-system-prompt; the data_pool
    # prompt (up to 200 KB by Pydantic contract, typical 15-30 KB) goes
    # through stdin. Without this, briefings + Couche-2 calls on assets
    # with rich data_pool (≥17 KB) crash with `WinError 206`.
    cmd = [
        settings.claude_binary,
        "-p",
        # Short task wrapper kept in argv so claude has a non-empty
        # `-p` argument; the actual content arrives via stdin.
        "Read the task and full context piped via stdin, then respond per the system prompt.",
        "--output-format",
        "json",
        "--model",
        model,
        "--effort",
        effort,
        "--no-session-persistence",
        "--append-system-prompt",
        persona_text,
    ]

    # ADR-077 / W86 STEP-4 — Capability 5 tool wiring. When mcp_config
    # is provided, materialise it to a tempfile (Windows requires
    # delete=False because the spawned subprocess holds the file lock)
    # and append the flag set. tempfile is cleaned up in `finally` after
    # `proc.communicate()` returns.
    mcp_config_path: Path | None = None
    if mcp_config is not None:
        fd, raw_path = tempfile.mkstemp(suffix=".json", prefix="ichor-mcp-")
        os.close(fd)
        mcp_config_path = Path(raw_path)
        mcp_config_path.write_text(json.dumps(mcp_config), encoding="utf-8")
        cmd.extend(
            [
                "--mcp-config",
                str(mcp_config_path),
                "--strict-mcp-config",
            ]
        )
        if allowed_tools:
            cmd.extend(["--allowedTools", ",".join(allowed_tools)])
        if max_turns > 0:
            cmd.extend(["--max-turns", str(max_turns)])

    log.info(
        "claude.subprocess.start",
        model=model,
        effort=effort,
        prompt_len=len(prompt),
        stdin_pipe=True,
        mcp_wired=mcp_config_path is not None,
        allowed_tools=list(allowed_tools) if allowed_tools else None,
        max_turns=max_turns,
    )
    start = time.monotonic()

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(workdir),
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=prompt.encode("utf-8")),
                timeout=settings.claude_timeout_sec,
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise
    finally:
        if mcp_config_path is not None:
            mcp_config_path.unlink(missing_ok=True)

    duration = time.monotonic() - start

    if proc.returncode != 0:
        log.error(
            "claude.subprocess.nonzero_exit",
            returncode=proc.returncode,
            stderr=stderr.decode(errors="replace")[:500],
            duration=duration,
        )
        raise ClaudeSubprocessError(
            f"claude exited {proc.returncode}: {stderr.decode(errors='replace')[:500]}"
        )

    try:
        result = json.loads(stdout)
    except json.JSONDecodeError as e:
        log.error(
            "claude.subprocess.json_parse_failed",
            error=str(e),
            stdout_preview=stdout.decode(errors="replace")[:300],
        )
        raise ClaudeSubprocessError(f"failed to parse claude JSON output: {e}") from e

    log.info(
        "claude.subprocess.ok",
        duration=duration,
        usage=result.get("usage"),
        subtype=result.get("subtype"),
    )
    return result
