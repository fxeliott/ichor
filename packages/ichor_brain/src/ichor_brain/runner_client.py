"""Abstract gateway to the LLM runner.

Production path : `HttpRunnerClient` posts to the Win11 claude-runner
through the Cloudflare Tunnel (Voie D, ADR-009). Tests use
`InMemoryRunnerClient` to script the per-pass responses without touching
a real subprocess.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx


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
        async with httpx.AsyncClient(timeout=self._timeout_sec) as client:
            r = await client.post(url, headers=self._headers, json=payload)
            r.raise_for_status()
            body = r.json()
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
