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
import subprocess
import time
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
    max_tokens: int = 4_000,
    temperature: float = 0.5,
    persona_text: str | None = None,
) -> dict[str, Any]:
    """Run `claude -p <prompt>` and return the parsed JSON envelope.

    Args:
        prompt: User-side prompt (the request).
        settings: runtime config.
        model: opus / sonnet / haiku.
        max_tokens: output budget.
        temperature: sampling temp.
        persona_text: if provided, written to a temp file and passed via
            --append-system. Falls back to settings.persona_file.

    Returns:
        Parsed JSON dict. Typical shape:
            {
              "type": "message",
              "role": "assistant",
              "content": [{"type": "text", "text": "..."}],
              "stop_reason": "end_turn",
              "usage": {"input_tokens": ..., "output_tokens": ...},
              ...
            }

    Raises:
        ClaudeSubprocessError on any failure.
        asyncio.TimeoutError if the subprocess exceeds claude_timeout_sec.
    """
    workdir = settings.workdir
    workdir.mkdir(parents=True, exist_ok=True)

    persona_path = settings.persona_file
    if persona_text is not None:
        persona_path = workdir / f"persona-{int(time.time() * 1000)}.md"
        persona_path.write_text(persona_text, encoding="utf-8")

    if not persona_path.exists():
        raise ClaudeSubprocessError(
            f"Persona file not found at {persona_path} — cannot proceed"
        )

    cmd = [
        settings.claude_binary,
        "-p",
        prompt,
        "--output-format", "json",
        "--model", model,
        "--max-tokens", str(max_tokens),
        "--temperature", str(temperature),
        "--append-system", f"@{persona_path}",
    ]

    log.info("claude.subprocess.start", model=model, max_tokens=max_tokens, prompt_len=len(prompt))
    start = time.monotonic()

    try:
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
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise

    finally:
        # Cleanup temp persona if we wrote one
        if persona_text is not None and persona_path.exists():
            persona_path.unlink(missing_ok=True)

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
        stop_reason=result.get("stop_reason"),
    )
    return result
