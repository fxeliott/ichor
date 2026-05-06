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

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class RunnerCall:
    """One LLM request : prompt + persona + model/effort knobs."""

    prompt: str
    system: str
    model: str = "opus"
    effort: str = "high"
    cache_key: str | None = None
    """Optional opaque cache key (anthropic prompt-cache breakpoint)."""


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
            raise RuntimeError(
                "InMemoryRunnerClient exhausted: more calls than scripted responses"
            )
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
    ):
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "Content-Type": "application/json",
            "CF-Access-Client-Id": cf_access_client_id,
            "CF-Access-Client-Secret": cf_access_client_secret,
        }
        self._timeout_sec = timeout_sec
        self._default_assets = default_assets

    async def run(self, call: RunnerCall) -> RunnerResponse:
        url = f"{self._base_url}/v1/briefing-task"
        payload = {
            "briefing_type": "crisis",
            "assets": list(self._default_assets),
            "context_markdown": _wrap_with_system(call.system, call.prompt),
            "model": call.model,
            "effort": call.effort,
        }
        # Backoff schedule for transient 503/429: 5s, 15s, 45s. Total
        # worst-case ~65s, well under Cloudflare's 100s edge cap.
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
                        next_delay_s=backoff[attempt] if attempt < len(backoff) else None,
                    )
                    if attempt < len(backoff):
                        continue
                    # Out of retries — let raise_for_status surface the error
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
