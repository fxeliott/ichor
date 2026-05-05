"""Wrapper around `claude -p` — handles subprocess lifecycle, timeout,
JSON parsing, error recovery.

Why subprocess instead of Anthropic SDK:
  Eliot uses Claude Max 20x (flat $200/mo). The Max subscription gates access
  via OAuth tokens stored locally by `claude login`. There's no programmatic
  way to use this auth from the Anthropic SDK — we must shell out to the same
  `claude` binary that he uses interactively.

  This is a deliberate Voie D choice (see docs/decisions/ADR-009).
"""

from __future__ import annotations

import asyncio
import json
import time
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

    cmd = [
        settings.claude_binary,
        "-p",
        prompt,
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

    log.info("claude.subprocess.start", model=model, effort=effort, prompt_len=len(prompt))
    start = time.monotonic()

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(workdir),
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=settings.claude_timeout_sec
        )
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise

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
