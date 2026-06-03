"""ClaudeRunnerProvider — adapter that routes a Pydantic-AI-style call
through the local Win11 claude-runner HTTP endpoint.

Per ADR-021, Claude (Opus/Sonnet/Haiku via the Max 20x runner) is the
**primary** brain for all Couche-2 agents; Cerebras + Groq remain wired
as transparent fallback only. This adapter is the missing piece that
made the ADR a no-op until 2026-05-06.

Wire contract: POST {runner_url}/v1/agent-task with a JSON body
    { "system": ..., "prompt": ..., "model": ..., "effort": ... }
Headers: CF-Access-Client-Id / CF-Access-Client-Secret (Cloudflare
service token — same pattern HttpRunnerClient already uses for the
Couche-1 briefing endpoint).

Output handling:
  - When `output_type` is None, returns the raw text.
  - When `output_type` is a Pydantic BaseModel subclass, strips
    ```json fences if present, then `model_validate_json`. Failures
    re-raise as `ClaudeRunnerOutputError` so the caller can decide
    whether to fall back.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass

import httpx
import structlog

from .observability import observe

log = structlog.get_logger(__name__)


class ClaudeRunnerError(RuntimeError):
    """Any failure in the Claude path — HTTP, status!=success, parse, validation."""


class ClaudeRunnerOutputError(ClaudeRunnerError):
    """Runner replied success but the output didn't match output_type."""


@dataclass(frozen=True)
class ClaudeRunnerConfig:
    """Runtime config for the Claude path of FallbackChain.

    `from_env()` reads ICHOR_API_CLAUDE_RUNNER_URL plus the matching CF
    Access service token vars (same names the API service uses, cf
    apps/api/src/ichor_api/config.py).

    The CF Access creds are *optional*: if the runner sits behind
    Cloudflare Access the headers must be sent, but the runner can also
    be configured (via ICHOR_RUNNER_REQUIRE_CF_ACCESS=false) to skip
    auth — in which case posting without those headers is fine. We send
    the headers when both are present, and omit them otherwise.

    Returns None only when the runner URL itself is unset, since that
    is the unambiguous "no Claude routing in this environment" signal.
    """

    runner_url: str
    cf_access_client_id: str | None = None
    cf_access_client_secret: str | None = None
    model: str = "opus"
    """§11 full-Opus (ADR-108, 2026-06-02, supersedes ADR-023): Opus 4.8
    effort=low for the 5 Couche-2 agents (CB-NLP, News-NLP, Macro, Sentiment,
    Positioning). ADR-023 pinned Haiku because Sonnet medium exceeded the
    Cloudflare Free tunnel 100 s edge cap on the LEGACY SYNC endpoint — but
    Wave 67 moved Couche-2 to the async-polling path (`call_agent_task_async`,
    FallbackChain.use_async_endpoint=True), which is CF-edge-immune, so the
    longer Opus wall-time no longer trips the cap. effort stays `low` because
    these are structured-extraction agents (tone/themes/positioning JSON),
    not deep reasoning. Voie D unchanged (Max 20x, no API spend)."""

    effort: str = "medium"
    timeout_sec: float = 300.0

    @classmethod
    def from_env(
        cls,
        *,
        model: str = "sonnet",
        effort: str = "medium",
        timeout_sec: float = 300.0,
    ) -> ClaudeRunnerConfig | None:
        url = (os.environ.get("ICHOR_API_CLAUDE_RUNNER_URL") or "").strip()
        if not url:
            return None
        cf_id = (os.environ.get("ICHOR_API_CF_ACCESS_CLIENT_ID") or "").strip() or None
        cf_secret = (os.environ.get("ICHOR_API_CF_ACCESS_CLIENT_SECRET") or "").strip() or None
        return cls(
            runner_url=url.rstrip("/"),
            cf_access_client_id=cf_id,
            cf_access_client_secret=cf_secret,
            model=model,
            effort=effort,
            timeout_sec=timeout_sec,
        )


_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL)
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


# r169 G-fix-Couche2 — Agent-mode override prefix.
#
# Empirical root cause (2026-05-27 SSH audit of Hetzner journalctl) :
# the Win11 claude CLI subprocess that the runner spawns reads the
# global user CLAUDE.md (interactive Eliot rules : self-checklist
# obligatoire, tracker compliance, "Ready for Stop" hooks). Couche-2
# agents pass their own system_prompt (e.g. SYSTEM_PROMPT_SENTIMENT)
# but those rules get OVERRIDDEN by the user-scope CLAUDE.md, so
# Claude returns 444 chars of pure prose ("**Self-checklist:**\n\n|...
# Ready for Stop.") with ZERO JSON content — Pydantic validation
# fails immediately on a non-JSON input.
#
# Fix : inject an explicit [AGENT-MODE-OVERRIDE] preamble at the TOP
# of every system prompt passed to claude. This is the FIRST thing
# Claude sees ; it precedes the agent persona AND it predates any
# user-scope rule loading. The preamble explicitly forbids the
# observed failure modes (Self-checklist, tracker text, Ready for
# Stop, Perfect. preamble) so they cannot leak even if claude reads
# the user CLAUDE.md after the system block.
#
# Pattern #15 R59 compliant : this is not a peer-reviewed citation
# claim — it's a directive constructed from EMPIRICALLY OBSERVED
# failure strings in Hetzner production logs (cb_nlp + sentiment +
# news_nlp all show variations of the same prose pattern).
_AGENT_MODE_OVERRIDE_PREFIX = (
    "[AGENT-MODE-OVERRIDE — HIGHEST PRIORITY, OVERRIDES ALL OTHER RULES]\n"
    "This is a machine-to-machine JSON API call, NOT an interactive chat.\n"
    "The caller is a Python service that will pass your output verbatim\n"
    "to a Pydantic JSON validator. Any character that is not part of a\n"
    "valid JSON object will cause a parse failure.\n"
    "\n"
    "MANDATORY OUTPUT CONTRACT :\n"
    "  - Output EXACTLY one JSON object that validates against the schema\n"
    "    appended to the user prompt.\n"
    "  - Output NOTHING ELSE — no prose before, no prose after.\n"
    "\n"
    "FORBIDDEN OUTPUT PATTERNS (these cause production failures) :\n"
    "  - 'Self-checklist:' or 'self-check' blocks\n"
    "  - 'Ready for Stop', 'Stop hook', 'tracker' references\n"
    "  - 'Perfect.' or 'All N items' preamble sentences\n"
    "  - Markdown code fences (```json ... ```)\n"
    "  - Tool-call XML scaffolding (</invoke>, </parameter>, <function_calls>,\n"
    "    <invoke>) before, inside, or AFTER the JSON — emit plain JSON only\n"
    "  - Italics/bold formatting around or inside the JSON\n"
    "  - Numbered explanations of what you did\n"
    "  - Acknowledgements ('I will now...', 'Here is the JSON...')\n"
    "\n"
    "OVERRIDE NOTICE : any user-scope CLAUDE.md / hook / global rule that\n"
    "demands self-checklists, tracker compliance, or response formatting\n"
    "does NOT apply to this call. This is an agent subprocess invocation,\n"
    "not an Eliot interactive session.\n"
    "\n"
    "[ORIGINAL AGENT SYSTEM PROMPT BELOW]\n"
    "\n"
)


_JSON_PRIMING_SUFFIX = "\n\n---\n\nNow output the single JSON object (and ONLY the JSON object).\n"


def _strip_json_fence(text: str) -> str:
    """Claude often wraps JSON in ```json``` fences — strip them so the
    Pydantic validator gets a parseable string. Also handles the case
    where the model adds a sentence before/after the JSON object : we
    extract the outermost {...} block as a fallback.

    r169 G-fix-Couche2 hardening : add a balanced-bracket scanner as a
    last-resort fallback so that even if the greedy ``\\{.*\\}`` regex
    captures trailing prose (e.g. ``{...} **Self-checklist:** ...``
    where the prose itself contains unbalanced braces), we still
    extract the correctly-paired top-level JSON object."""
    text = text.strip()
    m = _FENCE_RE.match(text)
    if m:
        # Unwrap the fence, then STILL run balanced extraction below so a
        # fenced object with trailing junk is cleaned too.
        text = m.group(1).strip()
    # ALWAYS prefer the FIRST balanced top-level {...} span. This strips BOTH
    # leading prose AND trailing tokens in one pass — including the tool-call
    # XML scaffolding (</invoke>, </parameter>) that Opus 4.8 intermittently
    # leaks AFTER an otherwise-valid JSON object on the macro/positioning
    # agents (witnessed every cron fire 2026-06-03 : "Invalid JSON: trailing
    # characters at column N"). The pre-fix guard only ran this when the text
    # did NOT start with `{`, so a `{...}</invoke>` payload was returned
    # verbatim and failed model_validate_json. The extractor respects string
    # literals so a brace inside a value never confuses the match.
    balanced = _extract_first_balanced_json(text)
    if balanced is not None:
        return balanced
    # Greedy fallback for the legacy case where no balanced object is found
    # (e.g. prose with a single stray `{`); preserves the original behaviour.
    m2 = _JSON_OBJECT_RE.search(text)
    if m2:
        return m2.group(0).strip()
    return text


def _extract_first_balanced_json(text: str) -> str | None:
    """Return the first top-level JSON object in ``text`` extracted via
    a simple stack-based bracket matcher that respects string literals.
    Returns ``None`` if no balanced ``{...}`` span exists.

    r169 G-fix-Couche2 : more robust than the greedy regex when claude
    wraps JSON in prose that also contains stray braces (markdown lists,
    code snippets in the explanation, etc.). Single linear pass over
    the text ; O(n) time, O(depth) memory.
    """
    start: int | None = None
    depth = 0
    in_string = False
    escape = False
    for i, ch in enumerate(text):
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            if start is None:
                start = i
            depth += 1
        elif ch == "}" and start is not None:
            depth -= 1
            if depth == 0:
                return text[start : i + 1].strip()
            if depth < 0:
                # Malformed — stray closing brace outside any object ;
                # reset and continue searching.
                start = None
                depth = 0
    return None


def _wrap_system_prompt_with_agent_override(system: str) -> str:
    """r169 G-fix-Couche2 — prepend the agent-mode override prefix to
    the agent's persona system_prompt. This is the canonical SSOT for
    every Couche-2 call. Future agents added to the registry inherit
    the override automatically by routing through ``call_agent_task``
    or ``call_agent_task_async``."""
    return _AGENT_MODE_OVERRIDE_PREFIX + system


def _schema_hint(output_type: type) -> str:
    """Produce a tail block to append to the user prompt that pins down
    the expected JSON shape + primes the model into JSON-only mode.
    Without this Claude regularly invents enum values that fail Pydantic
    validation (e.g. localised theme labels for the macro agent) AND
    leaks user-scope CLAUDE.md prose patterns (r168 production root
    cause).

    r169 G-fix-Couche2 : strengthened the instruction to enumerate the
    EMPIRICALLY OBSERVED forbidden patterns + appended a "Now output
    the single JSON object" primer that gives claude a clean handoff
    from prompt to output."""
    try:
        schema = output_type.model_json_schema()
    except AttributeError:
        return _JSON_PRIMING_SUFFIX  # output_type isn't a Pydantic v2 BaseModel
    return (
        "\n\n---\n\n"
        "**OUTPUT CONTRACT (enforced by Pydantic validator on the receiving\n"
        "side ; ANY non-JSON character causes the entire response to be\n"
        "discarded)** :\n"
        "\n"
        "Reply with a single JSON object that validates against the schema\n"
        "below. Output ONLY the JSON object — no prose, no code fences, no\n"
        "commentary. Use EXACTLY the enum values shown.\n"
        "\n"
        "Specifically FORBIDDEN (observed production failures) :\n"
        "  - 'Self-checklist:' or 'self-check' blocks\n"
        "  - 'Ready for Stop' / 'Stop hook' / tracker references\n"
        "  - 'Perfect.' / 'All N items' preamble sentences\n"
        "  - Numbered explanations or acknowledgements\n"
        "  - Markdown formatting around the JSON\n"
        "\n"
        f"Schema:\n{json.dumps(schema, indent=2, ensure_ascii=False)}" + _JSON_PRIMING_SUFFIX
    )


@observe(as_type="generation", name="couche2_agent_task")
async def call_agent_task(
    cfg: ClaudeRunnerConfig,
    *,
    system: str,
    prompt: str,
    output_type: type | None = None,
):
    """Single round-trip to the runner's /v1/agent-task endpoint.

    Returns either the raw output text (output_type is None) or a
    validated Pydantic instance.
    """
    url = f"{cfg.runner_url}/v1/agent-task"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if cfg.cf_access_client_id and cfg.cf_access_client_secret:
        headers["CF-Access-Client-Id"] = cfg.cf_access_client_id
        headers["CF-Access-Client-Secret"] = cfg.cf_access_client_secret

    full_prompt = prompt
    if output_type is not None:
        full_prompt = prompt + _schema_hint(output_type)

    # r169 G-fix-Couche2 — wrap system_prompt with the agent-mode override
    # prefix so the Win11 claude CLI does NOT inherit user-scope CLAUDE.md
    # rules (self-checklist / tracker / Ready-for-Stop / Perfect. preamble).
    # See _AGENT_MODE_OVERRIDE_PREFIX docstring for the empirical root cause.
    payload = {
        "system": _wrap_system_prompt_with_agent_override(system),
        "prompt": full_prompt,
        "model": cfg.model,
        "effort": cfg.effort,
    }

    log.info(
        "agents.claude_runner.try",
        model=cfg.model,
        effort=cfg.effort,
        prompt_len=len(prompt),
        system_len=len(system),
    )

    # Retry envelope: the runner enforces max_concurrent_subprocess=1
    # to protect the Max 20x quota. When two Couche-2 timers fire
    # near-simultaneously the second sees 503 "Another task in flight".
    # We retry with exponential backoff before falling back so the
    # ADR-021 primary path is preferred even under traffic bursts.
    # 429 (rate-limit) is also retried — the rate-limit window resets
    # in <60 s so a couple of retries spans the boundary.
    backoff = (5.0, 15.0, 45.0)  # seconds; total worst-case ~65 s
    last_error: str | None = None
    body: dict | None = None
    async with httpx.AsyncClient(timeout=cfg.timeout_sec) as client:
        for attempt, delay in enumerate((0.0,) + backoff):
            if delay > 0:
                await asyncio.sleep(delay)
            try:
                r = await client.post(url, headers=headers, json=payload)
            except httpx.HTTPError as e:
                last_error = f"runner unreachable: {e}"
                # Network errors are also retryable up to backoff budget
                if attempt < len(backoff):
                    continue
                raise ClaudeRunnerError(last_error) from e

            if r.status_code in (429, 503):
                last_error = f"HTTP {r.status_code}: {r.text[:200]}"
                log.info(
                    "agents.claude_runner.retry",
                    attempt=attempt + 1,
                    status=r.status_code,
                    next_delay_s=backoff[attempt] if attempt < len(backoff) else None,
                )
                if attempt < len(backoff):
                    continue
                raise ClaudeRunnerError(f"runner busy after retries: {last_error}")

            if r.status_code >= 400:
                # Non-retryable HTTP errors (404, 5xx other than 503) — fail fast
                raise ClaudeRunnerError(f"runner returned HTTP {r.status_code}: {r.text[:300]}")
            body = r.json()
            break

    if body is None:  # defensive — loop must exit via break or raise
        raise ClaudeRunnerError(last_error or "runner did not respond")

    rstatus = body.get("status")
    if rstatus != "success":
        raise ClaudeRunnerError(
            f"runner status={rstatus}: {body.get('error_message') or 'no message'}"
        )

    text = body.get("output_text") or ""
    if not text:
        raise ClaudeRunnerError("runner returned empty output_text")

    log.info(
        "agents.claude_runner.ok",
        duration_ms=body.get("duration_ms"),
        output_len=len(text),
    )

    if output_type is None:
        return text

    cleaned = _strip_json_fence(text)
    try:
        return output_type.model_validate_json(cleaned)
    except Exception as e:
        raise ClaudeRunnerOutputError(
            f"output failed Pydantic validation: {type(e).__name__}: {str(e)[:300]}"
        ) from e


# ─────────────────────────────────────────────────────────────────────────
# WAVE 67 — async polling client (CF Tunnel 100s edge cap structural fix)
# ─────────────────────────────────────────────────────────────────────────


@observe(as_type="generation", name="couche2_agent_task_async")
async def call_agent_task_async(
    cfg: ClaudeRunnerConfig,
    *,
    system: str,
    prompt: str,
    output_type: type | None = None,
    poll_interval_sec: float = 5.0,
    poll_timeout_sec: float = 600.0,
):
    """Submit a Couche-2 agent task via /v1/agent-task/async + poll until done.

    Wave 67 mirror of HttpRunnerClient async pattern (ADR-053). Bypasses
    Cloudflare Tunnel 100s edge timeout by decoupling submit from result
    fetch. Each HTTP call (submit + each poll) completes in <1s.

    Args:
        cfg: ClaudeRunnerConfig (runner URL + auth + model/effort).
        system: persona text passed to claude as --append-system-prompt.
        prompt: user prompt (data_pool context for Couche-2).
        output_type: optional Pydantic BaseModel subclass for typed return.
        poll_interval_sec: poll cadence (5s default — matches Hetzner cron).
        poll_timeout_sec: total budget before giving up (10 min default).

    Returns: raw text or validated output_type instance.

    Raises: ClaudeRunnerError / ClaudeRunnerOutputError on failure.
    """
    import time
    from uuid import uuid4

    submit_url = f"{cfg.runner_url}/v1/agent-task/async"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if cfg.cf_access_client_id and cfg.cf_access_client_secret:
        headers["CF-Access-Client-Id"] = cfg.cf_access_client_id
        headers["CF-Access-Client-Secret"] = cfg.cf_access_client_secret

    full_prompt = prompt
    if output_type is not None:
        full_prompt = prompt + _schema_hint(output_type)

    task_id = str(uuid4())
    # r169 G-fix-Couche2 — mirror of the sync path : wrap system prompt
    # with [AGENT-MODE-OVERRIDE] prefix so user-scope CLAUDE.md rules
    # (self-checklist, tracker, Ready-for-Stop) cannot leak into the
    # JSON output expected by the Pydantic validator on the agent side.
    payload = {
        "task_id": task_id,
        "system": _wrap_system_prompt_with_agent_override(system),
        "prompt": full_prompt,
        "model": cfg.model,
        "effort": cfg.effort,
    }

    log.info(
        "agents.claude_runner.async.try",
        model=cfg.model,
        effort=cfg.effort,
        prompt_len=len(prompt),
        system_len=len(system),
        task_id=task_id,
    )

    started = time.monotonic()

    # Round-13 fix : retry transient CF / runner errors on the submit
    # path. Without this, every Couche-2 cron tick that hits a Win11
    # standalone-uvicorn brief moment of unavailability (process restart,
    # CF tunnel rewire, transient 530 "no origin") returned
    # AllProvidersFailed and the cron unit went FAILED until the next
    # OnCalendar tick. Round-27 (2026-05-13 08:47 CEST news_nlp 530
    # storm observed ~30 s) extended the envelope from 3 to 4 retries
    # to bridge multi-second QUIC handshake-timeout storms on the
    # cloudflared edge. Total worst-case 5+15+45+90 = 155 s, still
    # under the 10 min poll budget. Ban-risk respected : 4 retries x
    # 5 Couche-2 agents x 4 sessions/day = 80 reqs/day max (rule 16,
    # Max 20x quota >>> 80). Retryable status codes :
    #   429 — rate-limit
    #   502 — bad gateway (CF edge to origin)
    #   503 — service unavailable (runner busy slot 1/1)
    #   504 — gateway timeout
    #   520-525 — Cloudflare origin error family (530 = "no origin")
    _RETRYABLE_SUBMIT_STATUS: frozenset[int] = frozenset(
        {429, 502, 503, 504, 520, 521, 522, 523, 524, 525, 530}
    )
    submit_backoff = (5.0, 15.0, 45.0, 90.0)
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Submit (must respond in <100s; the runner immediately returns 202)
        r = None
        for attempt, delay in enumerate((0.0,) + submit_backoff):
            if delay > 0:
                await asyncio.sleep(delay)
            try:
                r = await client.post(submit_url, headers=headers, json=payload)
            except httpx.HTTPError as e:
                if attempt < len(submit_backoff):
                    log.info(
                        "agents.claude_runner.async.submit_retry",
                        task_id=task_id,
                        attempt=attempt + 1,
                        reason=f"network: {type(e).__name__}",
                    )
                    continue
                raise ClaudeRunnerError(f"async submit unreachable: {e}") from e

            if r.status_code in _RETRYABLE_SUBMIT_STATUS:
                if attempt < len(submit_backoff):
                    log.info(
                        "agents.claude_runner.async.submit_retry",
                        task_id=task_id,
                        attempt=attempt + 1,
                        status=r.status_code,
                        next_delay_s=submit_backoff[attempt],
                    )
                    continue
                # All retries exhausted
                raise ClaudeRunnerError(
                    f"async submit transient {r.status_code} after retries: {r.text[:200]}"
                )

            # Non-retryable status — fail fast (404, 401, 403, 4xx other
            # than 429, 5xx other than the CF transient family above).
            if r.status_code != 202:
                raise ClaudeRunnerError(
                    f"async submit returned HTTP {r.status_code}: {r.text[:300]}"
                )
            break

        if r is None or r.status_code != 202:  # defensive
            raise ClaudeRunnerError("async submit failed without explicit error")

        accepted = r.json()
        poll_url = f"{cfg.runner_url}{accepted.get('poll_url')}"

        # Poll loop
        poll_count = 0
        while True:
            elapsed = time.monotonic() - started
            if elapsed > poll_timeout_sec:
                raise ClaudeRunnerError(
                    f"async poll timeout after {poll_timeout_sec}s (task_id={task_id})"
                )
            await asyncio.sleep(poll_interval_sec)
            poll_count += 1
            try:
                pr = await client.get(poll_url, headers=headers)
            except httpx.HTTPError as e:
                # Transient poll error — try again next iteration
                log.warning(
                    "agents.claude_runner.async.poll_transient",
                    task_id=task_id,
                    poll_count=poll_count,
                    error=str(e)[:80],
                )
                continue

            if pr.status_code == 404:
                raise ClaudeRunnerError(f"async task expired or unknown: {pr.text[:200]}")
            if pr.status_code != 200:
                raise ClaudeRunnerError(f"async poll HTTP {pr.status_code}: {pr.text[:200]}")

            poll = pr.json()
            poll_status = poll.get("status")
            if poll_status in ("done", "error"):
                log.info(
                    "agents.claude_runner.async.completed",
                    task_id=task_id,
                    poll_count=poll_count,
                    elapsed_sec=round(elapsed, 1),
                    status=poll_status,
                )
                if poll_status == "error":
                    raise ClaudeRunnerError(f"async task error: {poll.get('error') or 'unknown'}")
                # done — extract result
                result = poll.get("result") or {}
                rstatus = result.get("status")
                if rstatus != "success":
                    raise ClaudeRunnerError(
                        f"async result status={rstatus}: "
                        f"{result.get('error_message') or 'no message'}"
                    )
                text = result.get("output_text") or ""
                if not text:
                    raise ClaudeRunnerError("async runner returned empty output_text")

                log.info(
                    "agents.claude_runner.ok",
                    duration_ms=result.get("duration_ms"),
                    output_len=len(text),
                    via="async",
                )

                if output_type is None:
                    return text

                cleaned = _strip_json_fence(text)
                try:
                    return output_type.model_validate_json(cleaned)
                except Exception as e:
                    raise ClaudeRunnerOutputError(
                        f"output failed Pydantic validation: {type(e).__name__}: {str(e)[:300]}"
                    ) from e
            # else status pending / running — continue polling
