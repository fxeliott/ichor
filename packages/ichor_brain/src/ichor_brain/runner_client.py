"""Abstract gateway to the LLM runner.

Production path : `HttpRunnerClient` posts to the Win11 claude-runner
through the Cloudflare Tunnel (Voie D, ADR-009). Tests use
`InMemoryRunnerClient` to script the per-pass responses without touching
a real subprocess.

Retry envelope : the runner enforces max_concurrent_subprocess=1 to
protect the Max 20x quota, so when the briefing timer (HH:00) and the
session-cards batch timer (HH:01) overlap, the second hit gets HTTP
503 "Another briefing in flight". We retry transparently with
exponential backoff (5/15/45 s) before failing the card.

Retryable statuses (`_TRANSIENT_STATUSES`) — origin- or tunnel-side
transient errors where a fresh call has a fair chance to succeed :

* 429 — hourly rate-limit (runner Max 20x quota).
* 502 — bad gateway (cloudflared lost the upstream socket briefly).
* 503 — runner busy concurrency lock.
* 504 — gateway timeout (upstream took too long but didn't fail).
* 520-523, 525 — Cloudflare origin error family (origin DNS, SSL
  handshake, connection-reset, web-server-down, SSL-cert).
* 530 — Cloudflare "no origin" (cloudflared tunnel cannot reach the
  Win11 origin transiently — typically a cloudflared restart on the
  Windows side ; observed empirically in the 2026-05-12 06:00 batch
  where all 8 cards failed inside 41 s because the prior retry
  envelope only covered {429, 503}).

NOT retried :

* 524 — Cloudflare edge 100 s wall. A second call would hit the same
  wall (the subprocess is genuinely too slow for the legacy sync
  path). Async polling path doesn't see 524 on the body — only on
  the polling GETs which are <1 s.
"""

from __future__ import annotations

import asyncio
import random
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from .observability import observe

log = structlog.get_logger(__name__)


class RunnerResultError(RuntimeError):
    """The runner replied 200/done but the INNER result is a failure.

    Session 02 (2026-06-05) silent-failure guard. The async-polling path
    used to return ``RunnerResponse(text=briefing_markdown or "")`` for ANY
    completed task — so a runner ``status="timeout"`` / ``"subprocess_error"``
    or an empty briefing came back as an empty-but-"successful" response.
    The orchestrator then saw a confusing parse failure (PassError on "")
    instead of the TRUE cause, and a live product risks disguising a failed
    generation as a fresh empty card. We now raise this so the cause is
    logged/classified and the orchestrator's retry-then-fail surfaces it
    honestly (mirrors the Couche-2 client, which already raised).
    """


class RunnerTaskLost(RunnerResultError):
    """The async task is unknown to the runner (HTTP 404 on a poll) — the runner
    restarted mid-flight (its in-memory task table reset) or garbage-collected
    the task. UNRECOVERABLE within this attempt (a retry submits a brand-new
    task, it cannot recover the lost one), so a consumer should fail FAST rather
    than burn a jittered backoff sleep before re-submitting. A subclass of
    RunnerResultError so existing ``except RunnerResultError`` paths still catch
    it; the orchestrator adds a dedicated non-retryable arm (S02 round 6)."""


# Runner-side result statuses that mean the generation FAILED even though
# the async task itself completed (HTTP 200, task_status="done"). Mirrors
# BriefingTaskResponse.status / AgentTaskResponse.status literals.
_RUNNER_FAILURE_STATUSES = frozenset({"timeout", "subprocess_error", "throttled", "auth_failed"})


def _unwrap_runner_result(body: dict[str, Any]) -> str:
    """Extract the briefing text from a completed runner result, or raise.

    Raises ``RunnerResultError`` when the runner reported a failure status
    or returned empty text — instead of silently yielding ``""``. A missing
    ``status`` key (older runner builds / tests) is treated as success so
    long as the text is non-empty (back-compat).
    """
    status = body.get("status")
    if status in _RUNNER_FAILURE_STATUSES:
        raise RunnerResultError(
            f"runner result status={status}: {body.get('error_message') or 'no detail'}"
        )
    text = body.get("briefing_markdown") or ""
    if not text.strip():
        raise RunnerResultError(
            f"runner reported status={status!r} but returned empty "
            "briefing_markdown (silent-failure guard, Session 02)"
        )
    return text


# CF tunnel + runner transient errors that warrant a transparent retry.
# 524 is deliberately excluded (see module docstring).
_TRANSIENT_STATUSES = frozenset({429, 502, 503, 504, 520, 521, 522, 523, 525, 530})

# Poll-loop resilience (2026-06-02) — while a task runs, the orchestrator
# polls GET /v1/.../async/{id} every poll_interval_sec. A single transient
# tunnel blip on a poll (cloudflared keep-alive race after an origin
# restart, DNS resolver refresh, CF edge hiccup, or a dropped connection)
# must NOT abort a 200s card mid-generation. The poll loop tolerates these
# (and httpx.TransportError) up to _MAX_CONSECUTIVE_POLL_ERRORS in a row —
# a successful poll resets the counter, and poll_max_total_sec still bounds
# the total wait. 524 (edge timeout on one poll) is retryable here, unlike
# on submit, because the task keeps running on the runner regardless.
_POLL_RETRY_STATUSES = _TRANSIENT_STATUSES | frozenset({524})
_MAX_CONSECUTIVE_POLL_ERRORS = 12

# Submission/retry backoff jitter (S02 socle round 4, 2026-06-18). The fixed
# (5, 15, 45) s submit backoff is the CLIENT layer of the very thundering-herd
# the module docstring names: when the HH:00 briefing timer and the HH:01
# session-cards batch overlap, all 6 per-asset RunnerClients collide on the
# runner's single-subprocess 503 lock and, on a fixed cadence, re-hit in
# lock-step. ±25 % jitter de-synchronises them (the orchestrator-level jitter
# only fires AFTER the client has already exhausted this backoff). random.uniform
# is the patchable seam for deterministic tests.
_BACKOFF_JITTER_FRAC = 0.25


def _jittered(delay: float) -> float:
    """Return ``delay`` scaled by ``1 ± _BACKOFF_JITTER_FRAC`` (uniform)."""
    return delay * (1.0 + random.uniform(-_BACKOFF_JITTER_FRAC, _BACKOFF_JITTER_FRAC))


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
    effort: str = "xhigh"
    cache_key: str | None = None
    """Optional opaque cache key (anthropic prompt-cache breakpoint)."""
    mcp_config: dict[str, Any] | None = None
    """Optional MCP servers spec — `{"mcpServers": {...}}`. When set,
    claude-runner writes it to a temp JSON and passes
    `--mcp-config <path> --strict-mcp-config`. None = no tool use."""
    allowed_tools: tuple[str, ...] | None = None
    """Optional tool allowlist — passed verbatim to `--allowedTools`.
    Tuple (not list) for shallow immutability ; the dataclass is
    `frozen=True` so the field itself can't be reassigned. **Note** :
    `mcp_config: dict` makes the dataclass NON-hashable in practice
    (a frozen dataclass with a mutable field raises `TypeError` on
    `hash()`). Treat RunnerCall as a passive value-object, never as
    a dict key or set member. None = no restriction (still bounded
    by `--strict-mcp-config`)."""
    max_turns: int = 0
    """Max agentic loop iterations. 0 = do not pass `--max-turns`
    (CLI default). Recommended 5-10 for Ichor 4-pass briefings."""


@dataclass(frozen=True)
class ToolConfig:
    """Capability 5 wiring config for the Orchestrator (W87 STEP-5).

    When attached to an Orchestrator, the passes named in
    `enabled_for_passes` receive tool fields in their RunnerCall and
    can issue mcp__ichor__query_db / mcp__ichor__calc invocations
    during their reasoning. Pass-3 stress and Pass-4 invalidation are
    excluded by default because they operate on prior-pass narrative
    output, not raw market data, so tool access provides no marginal
    lift and adds audit cost.

    The allowlist of tables that `query_db` can read lives at the
    `apps/api` layer (`services/tool_query_db.ALLOWED_TABLES`,
    enforced by sqlglot AST parser, ADR-077). The forbidden set
    (`trader_notes`, `audit_log`, `tool_call_audit`, `feature_flags`)
    is documented in ADR-078 and CI-guarded by
    `test_tool_query_db_allowlist_guard.py`.
    """

    mcp_config: dict[str, Any]
    """`{"mcpServers": {...}}` shape. Forwarded verbatim to
    claude-runner, which writes it to a tempfile and passes it to
    `claude -p --mcp-config <path>`."""

    allowed_tools: tuple[str, ...]
    """Tools the model is allowed to invoke. Verbatim
    `--allowedTools` argument. Frozen as tuple so ToolConfig stays
    hashable."""

    max_turns: int = 8
    """Cap on the agentic tool_use loop iterations."""

    enabled_for_passes: frozenset[str] = frozenset({"regime", "asset"})
    """Set of pass kinds eligible for tool wiring. Pass kinds are the
    short strings 'regime', 'asset', 'stress', 'invalidation'
    (matching the orchestrator's internal naming, not the Pass
    class's public `.name` attribute which can be longer / locale-
    specific)."""


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
        poll_max_total_sec: float = 960.0,
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

        Total wall-time bounded by poll_max_total_sec (default 960s = 16min),
        sized ABOVE the runner's per-call kill (claude_timeout_sec, 900 s)
        so a stuck subprocess is classified at the runner (a real
        `status="timeout"`), never as a consumer-side give-up — ADR-110
        timeout hierarchy (effort xhigh lengthens Opus passes).
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
                    await asyncio.sleep(_jittered(delay))
                r = await client.post(submit_url, headers=self._headers, json=payload)
                last_status = r.status_code
                if r.status_code in _TRANSIENT_STATUSES:
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
            # Transient tunnel blips (5xx/52x or a dropped connection) are
            # tolerated: the runner is up, cloudflared just briefly couldn't
            # reach it. Keep polling and only give up after
            # _MAX_CONSECUTIVE_POLL_ERRORS in a row (a successful poll resets
            # the counter). A 4xx (404 expired / 401 auth) is a real failure
            # and still aborts immediately.
            poll_started = asyncio.get_event_loop().time()
            poll_count = 0
            consecutive_poll_errors = 0
            while True:
                poll_count += 1
                if asyncio.get_event_loop().time() - poll_started > self._poll_max_total_sec:
                    raise TimeoutError(
                        f"async briefing task {task_id} did not complete within "
                        f"{self._poll_max_total_sec}s (poll_count={poll_count})"
                    )
                await asyncio.sleep(self._poll_interval_sec)
                try:
                    pr = await client.get(poll_url, headers=self._headers)
                    if pr.status_code in _POLL_RETRY_STATUSES:
                        consecutive_poll_errors += 1
                        if consecutive_poll_errors > _MAX_CONSECUTIVE_POLL_ERRORS:
                            pr.raise_for_status()
                        log.info(
                            "runner_client.async.poll_transient",
                            status=pr.status_code,
                            consecutive=consecutive_poll_errors,
                            task_id=task_id,
                        )
                        continue
                    if pr.status_code == 404:
                        # The runner no longer knows this task_id. Two honest,
                        # unrecoverable causes: it restarted mid-flight (the
                        # in-memory async-task table reset) OR the task was
                        # garbage-collected (too old). Classify it as a clear
                        # runner failure instead of a bare 404 that the
                        # orchestrator surfaces as an opaque HTTPStatusError —
                        # the §10.2 silent-outage class wants honest causes, not
                        # mysteries. The card fails this cycle and regenerates
                        # on the next batch (the watchdog has already restarted
                        # the runner). Mirrors the runner-side failure-status
                        # guard (`_unwrap_runner_result`).
                        log.info(
                            "runner_client.async.task_lost",
                            status=404,
                            task_id=task_id,
                            poll_count=poll_count,
                        )
                        raise RunnerTaskLost(
                            f"async task {task_id} is unknown to the runner (HTTP 404) "
                            "— the runner most likely restarted mid-flight, or the task "
                            "was garbage-collected; the task is lost (regenerate next cycle)."
                        )
                    pr.raise_for_status()
                except httpx.TransportError as exc:
                    consecutive_poll_errors += 1
                    if consecutive_poll_errors > _MAX_CONSECUTIVE_POLL_ERRORS:
                        raise
                    log.info(
                        "runner_client.async.poll_transport_retry",
                        error=type(exc).__name__,
                        consecutive=consecutive_poll_errors,
                        task_id=task_id,
                    )
                    continue
                consecutive_poll_errors = 0
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
                        text=_unwrap_runner_result(body),
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
                    await asyncio.sleep(_jittered(delay))
                r = await client.post(url, headers=self._headers, json=payload)
                last_status = r.status_code
                if r.status_code in _TRANSIENT_STATUSES:
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
            text=_unwrap_runner_result(body),
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
