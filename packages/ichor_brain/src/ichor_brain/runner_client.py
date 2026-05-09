"""Abstract gateway to the LLM runner.

Production path : `HttpRunnerClient` posts to the Win11 claude-runner
through the Cloudflare Tunnel (Voie D, ADR-009). Tests use
`InMemoryRunnerClient` to script the per-pass responses without touching
a real subprocess.

Retry envelope : the runner enforces max_concurrent_subprocess=1 to
protect the Max 20x quota, so when the briefing timer (HH:00) and the
session-cards batch timer (HH:01) overlap, the second hit gets HTTP
503 "Another briefing in flight". We retry transparently with
exponential backoff before failing the card. 429 (hourly rate limit)
is also retried for the same reason. 524 (Cloudflare edge timeout
after 100 s) is NOT retried — the second call would just hit the
same wall.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from .observability import observe

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class RunnerCall:
    """One LLM request : prompt + persona + model/effort knobs.

    Capability 5 fields (W86 STEP-4, ADR-077) — when `mcp_config` is
    non-None the claude-runner spawns `claude -p --mcp-config <temp>
    --strict-mcp-config --allowedTools <list> --max-turns N`. The
    agentic tool_use→tool_result loop is then driven entirely by the
    Claude CLI (the orchestrator stays single-shot). When None the
    runner falls back to the pre-W86 prompt-only invocation.
    """

    prompt: str
    system: str
    model: str = "opus"
    effort: str = "high"
    cache_key: str | None = None
    """Optional opaque cache key (anthropic prompt-cache breakpoint)."""
    mcp_config: dict[str, Any] | None = None
    """Optional MCP servers spec — `{"mcpServers": {...}}`. When set,
    claude-runner writes it to a temp JSON and passes
    `--mcp-config <path> --strict-mcp-config`. None = no tool use."""
    allowed_tools: tuple[str, ...] | None = None
    """Optional tool allowlist — passed verbatim to `--allowedTools`.
    Frozen as a tuple so RunnerCall stays hashable. None = no
    restriction (still bounded by `--strict-mcp-config`)."""
    max_turns: int = 0
    """Max agentic loop iterations. 0 = do not pass `--max-turns`
    (CLI default). Recommended 5-10 for Ichor 4-pass briefings."""


@dataclass(frozen=True)
class RunnerResponse:
    """One LLM response."""

    text: str
    raw: dict[str, Any]
    duration_ms: int


class RunnerClient(ABC):
    """Async LLM gateway. One call per pass; the orchestrator chains them."""

    @abstractmethod
    async def run(self, call: RunnerCall) -> RunnerResponse: ...


class InMemoryRunnerClient(RunnerClient):
    """Test double — returns scripted responses in FIFO order.

    Pass either a list of `RunnerResponse` objects or a callable
    `(RunnerCall) -> RunnerResponse` for per-call decision logic.
    """

    def __init__(
        self,
        responses: list[RunnerResponse] | Callable[[RunnerCall], RunnerResponse],
    ):
        self._responses = responses
        self._calls: list[RunnerCall] = []

    @property
    def calls(self) -> list[RunnerCall]:
        return list(self._calls)

    async def run(self, call: RunnerCall) -> RunnerResponse:
        self._calls.append(call)
        if callable(self._responses):
            return self._responses(call)
        if not self._responses:
            raise RuntimeError("InMemoryRunnerClient exhausted: more calls than scripted responses")
        return self._responses.pop(0)


class HttpRunnerClient(RunnerClient):
    """Posts to the Win11 claude-runner through the Cloudflare Tunnel.

    Reuses the existing `/v1/briefing-task` endpoint by setting
    `briefing_type='event_driven'` and packaging the per-pass prompt as
    `context_markdown`. The CHUNK 7 follow-up will replace this with a
    dedicated `/v1/structured-prompt` endpoint that exposes `system` and
    cache controls explicitly.
    """

    def __init__(
        self,
        base_url: str,
        cf_access_client_id: str,
        cf_access_client_secret: str,
        timeout_sec: float = 420.0,
        default_assets: tuple[str, ...] = ("EUR_USD",),
        use_async_endpoint: bool = True,
        poll_interval_sec: float = 5.0,
        poll_max_total_sec: float = 600.0,
    ):
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "Content-Type": "application/json",
            "CF-Access-Client-Id": cf_access_client_id,
            "CF-Access-Client-Secret": cf_access_client_secret,
        }
        self._timeout_sec = timeout_sec
        self._default_assets = default_assets
        self._use_async_endpoint = use_async_endpoint
        self._poll_interval_sec = poll_interval_sec
        self._poll_max_total_sec = poll_max_total_sec

    @observe(as_type="generation", name="couche1_runner_call")
    async def run(self, call: RunnerCall) -> RunnerResponse:
        """Submit a briefing task. Uses async+polling pattern by default
        to bypass Cloudflare's 100s edge timeout (claude CLI processing
        can exceed this on large data_pool prompts)."""
        if self._use_async_endpoint:
            return await self._run_async_polling(call)
        return await self._run_legacy_sync(call)

    async def _run_async_polling(self, call: RunnerCall) -> RunnerResponse:
        """Async + polling pattern (recommended).

        1. POST /v1/briefing-task/async → 202 + task_id (fast, <2s)
        2. GET /v1/briefing-task/async/{task_id} every poll_interval_sec
           until status == 'done' or 'error'
        3. Each poll completes in <1s so Cloudflare 100s edge cap doesn't
           apply to the briefing's actual subprocess wall-time.

        Total wall-time bounded by poll_max_total_sec (default 600s = 10min),
        which is the upper bound on claude CLI processing for the largest
        briefings (typical: 60-180s).
        """
        submit_url = f"{self._base_url}/v1/briefing-task/async"
        payload: dict[str, Any] = {
            "briefing_type": "crisis",
            "assets": list(self._default_assets),
            "context_markdown": _wrap_with_system(call.system, call.prompt),
            "model": call.model,
            "effort": call.effort,
        }
        # W86 STEP-4 — Capability 5 tool fields (only sent when set,
        # so pre-W86 callers without tools wired stay byte-compatible
        # with the existing claude-runner request shape).
        if call.mcp_config is not None:
            payload["mcp_config"] = call.mcp_config
        if call.allowed_tools is not None:
            payload["allowed_tools"] = list(call.allowed_tools)
        if call.max_turns > 0:
            payload["max_turns"] = call.max_turns
        # Submission backoff for 503/429 (rate-limit, busy concurrency).
        backoff = (5.0, 15.0, 45.0)
        last_status: int | None = None
        accepted_body: dict | None = None
        # Keep one HTTP client open for both submit + poll (connection reuse).
        async with httpx.AsyncClient(timeout=30.0) as client:
            for attempt, delay in enumerate((0.0,) + backoff):
                if delay > 0:
                    await asyncio.sleep(delay)
                r = await client.post(submit_url, headers=self._headers, json=payload)
                last_status = r.status_code
                if r.status_code in (429, 503):
                    log.info(
                        "runner_client.async.submit_retry",
                        status=r.status_code,
                        attempt=attempt + 1,
                    )
                    if attempt < len(backoff):
                        continue
                if r.status_code == 202:
                    accepted_body = r.json()
                    break
                r.raise_for_status()
            if accepted_body is None:
                raise httpx.HTTPStatusError(
                    f"runner busy after retries (last status={last_status})",
                    request=httpx.Request("POST", submit_url),
                    response=httpx.Response(last_status or 503),
                )

            task_id = accepted_body["task_id"]
            poll_path = accepted_body.get("poll_url") or f"/v1/briefing-task/async/{task_id}"
            poll_url = f"{self._base_url}{poll_path}"
            log.info("runner_client.async.submitted", task_id=task_id)

            # Poll loop — short interval, bounded by poll_max_total_sec.
            poll_started = asyncio.get_event_loop().time()
            poll_count = 0
            while True:
                poll_count += 1
                if asyncio.get_event_loop().time() - poll_started > self._poll_max_total_sec:
                    raise TimeoutError(
                        f"async briefing task {task_id} did not complete within "
                        f"{self._poll_max_total_sec}s (poll_count={poll_count})"
                    )
                await asyncio.sleep(self._poll_interval_sec)
                pr = await client.get(poll_url, headers=self._headers)
                pr.raise_for_status()
                status_body = pr.json()
                task_status = status_body.get("status")
                if task_status in ("done", "error"):
                    log.info(
                        "runner_client.async.completed",
                        task_id=task_id,
                        status=task_status,
                        elapsed_sec=status_body.get("elapsed_sec"),
                        poll_count=poll_count,
                    )
                    if task_status == "error":
                        raise RuntimeError(
                            f"async briefing task {task_id} crashed: {status_body.get('error')}"
                        )
                    body = status_body.get("result") or {}
                    return RunnerResponse(
                        text=body.get("briefing_markdown") or "",
                        raw=body,
                        duration_ms=int(body.get("duration_ms") or 0),
                    )
                # status in ("pending", "running") — keep polling

    async def _run_legacy_sync(self, call: RunnerCall) -> RunnerResponse:
        """Legacy synchronous path — kept for back-compat. Subject to
        Cloudflare 100s edge timeout (524 errors on large prompts)."""
        url = f"{self._base_url}/v1/briefing-task"
        payload: dict[str, Any] = {
            "briefing_type": "crisis",
            "assets": list(self._default_assets),
            "context_markdown": _wrap_with_system(call.system, call.prompt),
            "model": call.model,
            "effort": call.effort,
        }
        # W86 STEP-4 — Capability 5 tool fields, see _run_async_polling.
        if call.mcp_config is not None:
            payload["mcp_config"] = call.mcp_config
        if call.allowed_tools is not None:
            payload["allowed_tools"] = list(call.allowed_tools)
        if call.max_turns > 0:
            payload["max_turns"] = call.max_turns
        backoff = (5.0, 15.0, 45.0)
        last_status: int | None = None
        body: dict | None = None
        async with httpx.AsyncClient(timeout=self._timeout_sec) as client:
            for attempt, delay in enumerate((0.0,) + backoff):
                if delay > 0:
                    await asyncio.sleep(delay)
                r = await client.post(url, headers=self._headers, json=payload)
                last_status = r.status_code
                if r.status_code in (429, 503):
                    log.info(
                        "runner_client.retry",
                        status=r.status_code,
                        attempt=attempt + 1,
                    )
                    if attempt < len(backoff):
                        continue
                r.raise_for_status()
                body = r.json()
                break
        if body is None:
            raise httpx.HTTPStatusError(
                f"runner busy after retries (last status={last_status})",
                request=httpx.Request("POST", url),
                response=httpx.Response(last_status or 503),
            )
        return RunnerResponse(
            text=body.get("briefing_markdown") or "",
            raw=body,
            duration_ms=int(body.get("duration_ms") or 0),
        )


def _wrap_with_system(system: str, prompt: str) -> str:
    """Inline the system instructions into the context_markdown payload.

    Once the dedicated `/v1/structured-prompt` endpoint lands, this
    helper goes away and the system text is sent in its own field
    (with a cache breakpoint).
    """
    if not system.strip():
        return prompt
    return f"# System instructions\n\n{system}\n\n---\n\n# Task\n\n{prompt}"
