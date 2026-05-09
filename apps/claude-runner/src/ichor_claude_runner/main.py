"""FastAPI entrypoint for the local Win11 Claude runner.

Endpoint surface (small on purpose — this is plumbing, not business logic):
  GET  /healthz              — liveness + readiness, no auth
  POST /v1/briefing-task     — accepts a BriefingTaskRequest, runs claude -p,
                                returns BriefingTaskResponse. Auth required.
  GET  /v1/usage             — read-only stats for monitoring (auth required)
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from uuid import UUID

import structlog
from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel

from . import __version__
from .auth import verify_cf_access
from .config import Settings, get_settings
from .models import (
    AgentTaskRequest,
    AgentTaskResponse,
    BriefingTaskRequest,
    BriefingTaskResponse,
    HealthResponse,
)
from .rate_limiter import HourlyRateLimiter
from .subprocess_runner import ClaudeSubprocessError, run_claude

log = structlog.get_logger(__name__)


# Module-global state initialized in lifespan
_subprocess_semaphore: asyncio.Semaphore
_rate_limiter: HourlyRateLimiter
_in_flight = 0

# Async task store : task_id -> {"status": "pending"|"running"|"done"|"error",
# "result": BriefingTaskResponse | None, "error": str | None,
# "started_at": float, "kind": "briefing"|"agent"}
# In-memory only — restart loses pending tasks (acceptable, polling client
# will time out and re-queue). MAX size enforced via _async_task_gc().
_async_tasks: dict[str, dict] = {}
_ASYNC_TASK_TTL_SEC = 1800  # 30 min : task results purged after that
_ASYNC_TASK_MAX = 100  # keep last 100 max


def _async_task_gc() -> None:
    """Garbage-collect old async task results.

    Runs O(n) on every new task — fine since n <= MAX. Removes entries
    older than TTL or beyond MAX (oldest first).
    """
    now = time.monotonic()
    # Remove TTL-expired
    expired = [
        tid for tid, t in _async_tasks.items()
        if t["status"] in ("done", "error") and now - t["started_at"] > _ASYNC_TASK_TTL_SEC
    ]
    for tid in expired:
        _async_tasks.pop(tid, None)
    # Cap MAX
    if len(_async_tasks) > _ASYNC_TASK_MAX:
        # sort by started_at, drop oldest
        sorted_tids = sorted(_async_tasks.items(), key=lambda kv: kv[1]["started_at"])
        for tid, _ in sorted_tids[: len(_async_tasks) - _ASYNC_TASK_MAX]:
            _async_tasks.pop(tid, None)


class AsyncTaskAccepted(BaseModel):
    """Returned from POST /v1/briefing-task/async — 202 Accepted."""

    task_id: UUID
    status: str = "pending"
    poll_url: str
    poll_interval_sec: int = 5


class AsyncTaskStatus(BaseModel):
    """Returned from GET /v1/briefing-task/async/{task_id}."""

    task_id: UUID
    status: str
    """'pending' (queued), 'running' (subprocess in flight),
    'done' (result available), 'error' (failed), 'unknown' (not found)."""
    elapsed_sec: float | None = None
    # Wave 67 — accept BriefingTaskResponse (briefing async) OR
    # AgentTaskResponse (agent async). Union avoids Pydantic 500 on serialize.
    result: BriefingTaskResponse | AgentTaskResponse | None = None
    error: str | None = None


_PERSONAS_ROOT = __import__("pathlib").Path(__file__).resolve().parent / "personas"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize global state at startup, cleanup on shutdown."""
    global _subprocess_semaphore, _rate_limiter

    settings = get_settings()
    _subprocess_semaphore = asyncio.Semaphore(settings.max_concurrent_subprocess)
    _rate_limiter = HourlyRateLimiter(settings.rate_limit_per_hour)

    settings.workdir.mkdir(parents=True, exist_ok=True)

    # SECURITY: refuse to start when persona_file is outside the package
    # personas/ directory. Defends against env-var override pointing at
    # arbitrary files on the host (e.g. ~/.aws/credentials). See MED-4 in
    # docs/audits/security-2026-05-03.md.
    persona_resolved = settings.persona_file.resolve()
    try:
        persona_resolved.relative_to(_PERSONAS_ROOT.resolve())
    except ValueError as e:
        raise RuntimeError(
            f"persona_file ({persona_resolved}) is outside the package "
            f"personas/ root ({_PERSONAS_ROOT}); refusing to start"
        ) from e

    # SECURITY: in production, refuse to start without CF Access enforcement.
    # See CRT-1 in docs/audits/security-2026-05-03.md.
    if settings.environment == "production" and not settings.require_cf_access:
        raise RuntimeError(
            "claude-runner refuses to start in production with "
            "ICHOR_RUNNER_REQUIRE_CF_ACCESS=false. The runner is reachable "
            "from the internet via the Cloudflare Tunnel; running without "
            "JWT verification means anyone can drain the Max 20x quota."
        )

    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            {
                "DEBUG": 10,
                "INFO": 20,
                "WARNING": 30,
                "ERROR": 40,
            }[settings.log_level]
        ),
    )

    log.info(
        "claude_runner.startup",
        version=__version__,
        host=settings.host,
        port=settings.port,
        require_cf_access=settings.require_cf_access,
        rate_limit_per_hour=settings.rate_limit_per_hour,
    )

    yield

    log.info("claude_runner.shutdown")


app = FastAPI(
    title="Ichor Claude Runner",
    version=__version__,
    description=(
        "Local Win11 wrapper around `claude -p`. Used by Hetzner cron jobs "
        "(via Cloudflare Tunnel) to run briefings against Eliot's Max 20x "
        "subscription without exposing the auth tokens."
    ),
    lifespan=lifespan,
)


@app.get("/healthz", response_model=HealthResponse)
async def healthz(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Liveness + readiness. Cheap, no subprocess invocation."""
    persona_loaded = settings.persona_file.exists()
    cli_available = True
    try:
        # Try `claude --version` quickly. If the binary isn't on PATH this
        # raises FileNotFoundError — readiness=degraded.
        proc = await asyncio.create_subprocess_exec(
            settings.claude_binary,
            "--version",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=5)
        cli_available = proc.returncode == 0
    except (TimeoutError, FileNotFoundError):
        cli_available = False

    status_str = "ok" if (cli_available and persona_loaded) else "degraded"
    if not cli_available:
        status_str = "down"

    return HealthResponse(
        status=status_str,
        version=__version__,
        claude_cli_available=cli_available,
        persona_loaded=persona_loaded,
        in_flight_subprocess=_in_flight,
        requests_last_hour=_rate_limiter.current_count(),
        rate_limit_remaining=_rate_limiter.remaining(),
    )


@app.post(
    "/v1/briefing-task",
    response_model=BriefingTaskResponse,
    responses={
        401: {"description": "Cloudflare Access JWT invalid"},
        429: {"description": "Rate limit exceeded"},
        503: {"description": "All concurrent slots busy"},
    },
)
async def briefing_task(
    req: BriefingTaskRequest,
    identity: str = Depends(verify_cf_access),
    settings: Settings = Depends(get_settings),
) -> BriefingTaskResponse:
    """Run a Claude briefing on behalf of Hetzner."""
    global _in_flight

    if not _rate_limiter.try_acquire():
        log.warning(
            "claude_runner.rate_limited",
            task_id=str(req.task_id),
            requester=identity,
            window_count=_rate_limiter.current_count(),
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Hourly rate limit exceeded — Max 20x quota self-protection",
        )

    if _subprocess_semaphore.locked():
        log.warning(
            "claude_runner.busy",
            task_id=str(req.task_id),
            requester=identity,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Another briefing in flight — try again in a moment",
        )

    log.info(
        "claude_runner.task.accepted",
        task_id=str(req.task_id),
        briefing_type=req.briefing_type,
        assets=req.assets,
        model=req.model,
        requester=identity,
    )

    started = time.monotonic()
    async with _subprocess_semaphore:
        _in_flight += 1
        try:
            result = await run_claude(
                prompt=req.context_markdown,
                settings=settings,
                model=req.model,
                effort=req.effort,
            )
        except TimeoutError:
            return BriefingTaskResponse(
                task_id=req.task_id,
                status="timeout",
                error_message=f"Claude subprocess exceeded {settings.claude_timeout_sec}s",
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        except ClaudeSubprocessError as e:
            return BriefingTaskResponse(
                task_id=req.task_id,
                status="subprocess_error",
                error_message=str(e),
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        finally:
            _in_flight -= 1

    duration_ms = int((time.monotonic() - started) * 1000)
    # Claude Code -p --output-format json outputs a flattened envelope:
    # top-level "result" is the model's text. (Different from the API SDK
    # which has content[] blocks.) Parse both for forward compat.
    briefing_md = result.get("result")
    if not briefing_md:
        text_blocks = [
            b.get("text", "") for b in result.get("content", []) if b.get("type") == "text"
        ]
        briefing_md = "\n\n".join(text_blocks).strip() or None

    return BriefingTaskResponse(
        task_id=req.task_id,
        status="success",
        briefing_markdown=briefing_md,
        raw_claude_json=result,
        duration_ms=duration_ms,
    )


@app.post(
    "/v1/agent-task",
    response_model=AgentTaskResponse,
    responses={
        401: {"description": "Cloudflare Access JWT invalid"},
        429: {"description": "Rate limit exceeded"},
        503: {"description": "All concurrent slots busy"},
    },
)
async def agent_task(
    req: AgentTaskRequest,
    identity: str = Depends(verify_cf_access),
    settings: Settings = Depends(get_settings),
) -> AgentTaskResponse:
    """Generic Claude single-shot for Couche-2 agents — see ADR-021.

    Reuses the same rate-limit and concurrency guards as /v1/briefing-task
    (one shared `_subprocess_semaphore`, one shared `_rate_limiter`) so
    Couche-2 traffic and briefings draw from the same Max 20x quota
    envelope. The agent's system prompt overrides the default persona —
    each Couche-2 agent ships its own SYSTEM_PROMPT_X.
    """
    global _in_flight

    if not _rate_limiter.try_acquire():
        log.warning(
            "claude_runner.rate_limited",
            task_id=str(req.task_id),
            requester=identity,
            window_count=_rate_limiter.current_count(),
            endpoint="agent-task",
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Hourly rate limit exceeded — Max 20x quota self-protection",
        )

    if _subprocess_semaphore.locked():
        log.warning(
            "claude_runner.busy",
            task_id=str(req.task_id),
            requester=identity,
            endpoint="agent-task",
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Another task in flight — try again in a moment",
        )

    log.info(
        "claude_runner.agent_task.accepted",
        task_id=str(req.task_id),
        model=req.model,
        effort=req.effort,
        prompt_len=len(req.prompt),
        system_len=len(req.system),
        requester=identity,
    )

    started = time.monotonic()
    async with _subprocess_semaphore:
        _in_flight += 1
        try:
            result = await run_claude(
                prompt=req.prompt,
                settings=settings,
                model=req.model,
                effort=req.effort,
                persona_text=req.system,
            )
        except TimeoutError:
            return AgentTaskResponse(
                task_id=req.task_id,
                status="timeout",
                error_message=f"Claude subprocess exceeded {settings.claude_timeout_sec}s",
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        except ClaudeSubprocessError as e:
            return AgentTaskResponse(
                task_id=req.task_id,
                status="subprocess_error",
                error_message=str(e),
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        finally:
            _in_flight -= 1

    duration_ms = int((time.monotonic() - started) * 1000)
    output_text = result.get("result")
    if not output_text:
        text_blocks = [
            b.get("text", "") for b in result.get("content", []) if b.get("type") == "text"
        ]
        output_text = "\n\n".join(text_blocks).strip() or None

    return AgentTaskResponse(
        task_id=req.task_id,
        status="success",
        output_text=output_text,
        raw_claude_json=result,
        duration_ms=duration_ms,
    )


@app.get("/v1/usage")
async def usage(
    identity: str = Depends(verify_cf_access),
) -> dict:
    """Read-only stats — useful for Hetzner observability scrapers."""
    return {
        "in_flight": _in_flight,
        "requests_last_hour": _rate_limiter.current_count(),
        "rate_limit_remaining": _rate_limiter.remaining(),
        "version": __version__,
        "async_tasks_in_store": len(_async_tasks),
    }


# ─────────────────────────────────────────────────────────────────────────
# ASYNC TASK ENDPOINTS — fix for Cloudflare Tunnel 100s edge cap
# ─────────────────────────────────────────────────────────────────────────
# The legacy POST /v1/briefing-task is synchronous : the subprocess takes
# 60-180s typical, occasionally >100s on large data_pool prompts → Cloudflare
# 524 timeout. The async pattern below decouples submit from result :
#   1. POST /v1/briefing-task/async → 202 Accepted + task_id (immediate)
#   2. Background asyncio.create_task() runs claude subprocess
#   3. GET /v1/briefing-task/async/{task_id} → status (each poll < 1s,
#      well under Cloudflare 100s edge cap)
#   4. Hetzner polls every 5s until status == "done" or "error"
# Total wall time : same as before. Per-HTTP-call wall time : << 100s.
# Concurrency / rate-limit guards still enforced on submission.


async def _run_briefing_background(
    task_id: str,
    req: BriefingTaskRequest,
    settings: Settings,
) -> None:
    """Background task that runs the claude subprocess and stores the result."""
    global _in_flight
    started = time.monotonic()
    _async_tasks[task_id]["status"] = "running"
    try:
        async with _subprocess_semaphore:
            _in_flight += 1
            try:
                result = await run_claude(
                    prompt=req.context_markdown,
                    settings=settings,
                    model=req.model,
                    effort=req.effort,
                )
            finally:
                _in_flight -= 1
        duration_ms = int((time.monotonic() - started) * 1000)
        briefing_md = result.get("result")
        if not briefing_md:
            text_blocks = [
                b.get("text", "") for b in result.get("content", []) if b.get("type") == "text"
            ]
            briefing_md = "\n\n".join(text_blocks).strip() or None
        response = BriefingTaskResponse(
            task_id=req.task_id,
            status="success",
            briefing_markdown=briefing_md,
            raw_claude_json=result,
            duration_ms=duration_ms,
        )
        _async_tasks[task_id]["status"] = "done"
        _async_tasks[task_id]["result"] = response
    except TimeoutError:
        _async_tasks[task_id]["status"] = "done"
        _async_tasks[task_id]["result"] = BriefingTaskResponse(
            task_id=req.task_id,
            status="timeout",
            error_message=f"Claude subprocess exceeded {settings.claude_timeout_sec}s",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    except ClaudeSubprocessError as e:
        _async_tasks[task_id]["status"] = "done"
        _async_tasks[task_id]["result"] = BriefingTaskResponse(
            task_id=req.task_id,
            status="subprocess_error",
            error_message=str(e),
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    except Exception as e:
        log.exception("claude_runner.async_task.crashed", task_id=task_id)
        _async_tasks[task_id]["status"] = "error"
        _async_tasks[task_id]["error"] = f"{type(e).__name__}: {e}"


@app.post(
    "/v1/briefing-task/async",
    response_model=AsyncTaskAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        202: {"description": "Task accepted, poll status via /v1/briefing-task/async/{task_id}"},
        401: {"description": "Cloudflare Access JWT invalid"},
        429: {"description": "Rate limit exceeded"},
        503: {"description": "All concurrent slots busy"},
    },
)
async def briefing_task_async(
    req: BriefingTaskRequest,
    identity: str = Depends(verify_cf_access),
    settings: Settings = Depends(get_settings),
) -> AsyncTaskAccepted:
    """Submit a briefing task asynchronously. Returns 202 + task_id immediately.

    Caller polls GET /v1/briefing-task/async/{task_id} every 5s until the
    status field equals 'done' or 'error'. Each poll completes in <100ms,
    so Cloudflare's 100s edge timeout is no longer a hard cap on briefing
    duration.

    Concurrency guards (rate_limiter, subprocess_semaphore) are still
    enforced — the background task acquires the semaphore before launching
    the subprocess. If you submit 5 async tasks back-to-back, only one
    runs at a time (max_concurrent_subprocess=1).
    """
    if not _rate_limiter.try_acquire():
        log.warning(
            "claude_runner.async.rate_limited",
            task_id=str(req.task_id),
            requester=identity,
            window_count=_rate_limiter.current_count(),
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Hourly rate limit exceeded — Max 20x quota self-protection",
        )

    # GC old completed tasks before adding new one
    _async_task_gc()

    task_id = str(req.task_id)
    _async_tasks[task_id] = {
        "status": "pending",
        "result": None,
        "error": None,
        "started_at": time.monotonic(),
        "kind": "briefing",
    }

    log.info(
        "claude_runner.async_task.accepted",
        task_id=task_id,
        briefing_type=req.briefing_type,
        assets=req.assets,
        model=req.model,
        requester=identity,
    )

    # Spawn background task — store reference to prevent GC (RUF006)
    bg_task = asyncio.create_task(_run_briefing_background(task_id, req, settings))
    _async_tasks[task_id]["_bg_task"] = bg_task

    return AsyncTaskAccepted(
        task_id=req.task_id,
        status="pending",
        poll_url=f"/v1/briefing-task/async/{task_id}",
        poll_interval_sec=5,
    )


@app.get(
    "/v1/briefing-task/async/{task_id}",
    response_model=AsyncTaskStatus,
    responses={
        200: {"description": "Task status (poll until status='done' or 'error')"},
        401: {"description": "Cloudflare Access JWT invalid"},
        404: {"description": "task_id unknown (expired or never submitted)"},
    },
)
async def briefing_task_async_status(
    task_id: str,
    identity: str = Depends(verify_cf_access),
) -> AsyncTaskStatus:
    """Poll the status of an async briefing task. Each call is fast (<100ms)."""
    task = _async_tasks.get(task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"task_id {task_id} unknown (expired after {_ASYNC_TASK_TTL_SEC}s, or never submitted)",
        )
    elapsed = time.monotonic() - task["started_at"]
    return AsyncTaskStatus(
        task_id=UUID(task_id),
        status=task["status"],
        elapsed_sec=round(elapsed, 1),
        result=task["result"],
        error=task["error"],
    )


# ─────────────────────────────────────────────────────────────────────────
# WAVE 67 — AGENT-TASK ASYNC ENDPOINTS (Couche-2 5xx CF Tunnel structural fix)
# ─────────────────────────────────────────────────────────────────────────
# Same pattern as briefing-task/async (W20 ADR-053) but for Couche-2
# agents (cb_nlp, news_nlp, sentiment, positioning, macro). The legacy
# /v1/agent-task is synchronous and trips Cloudflare 100s edge cap when
# Haiku takes 100-130s on big prompts (cb_nlp 5KB, news_nlp 12KB).


async def _run_agent_background(
    task_id: str,
    req: AgentTaskRequest,
    settings: Settings,
) -> None:
    """Background task that runs the claude subprocess (agent-task variant)."""
    global _in_flight
    started = time.monotonic()
    _async_tasks[task_id]["status"] = "running"
    try:
        async with _subprocess_semaphore:
            _in_flight += 1
            try:
                result = await run_claude(
                    prompt=req.prompt,
                    settings=settings,
                    model=req.model,
                    effort=req.effort,
                    persona_text=req.system,
                )
            finally:
                _in_flight -= 1
        duration_ms = int((time.monotonic() - started) * 1000)
        output_text = result.get("result")
        if not output_text:
            text_blocks = [
                b.get("text", "") for b in result.get("content", []) if b.get("type") == "text"
            ]
            output_text = "\n\n".join(text_blocks).strip() or None
        response = AgentTaskResponse(
            task_id=req.task_id,
            status="success",
            output_text=output_text,
            raw_claude_json=result,
            duration_ms=duration_ms,
        )
        _async_tasks[task_id]["status"] = "done"
        _async_tasks[task_id]["result"] = response
    except TimeoutError:
        _async_tasks[task_id]["status"] = "done"
        _async_tasks[task_id]["result"] = AgentTaskResponse(
            task_id=req.task_id,
            status="timeout",
            error_message=f"Claude subprocess exceeded {settings.claude_timeout_sec}s",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    except ClaudeSubprocessError as e:
        _async_tasks[task_id]["status"] = "done"
        _async_tasks[task_id]["result"] = AgentTaskResponse(
            task_id=req.task_id,
            status="subprocess_error",
            error_message=str(e),
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    except Exception as e:
        log.exception("claude_runner.agent_async.crashed", task_id=task_id)
        _async_tasks[task_id]["status"] = "error"
        _async_tasks[task_id]["error"] = f"{type(e).__name__}: {e}"


@app.post(
    "/v1/agent-task/async",
    response_model=AsyncTaskAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        202: {"description": "Task accepted, poll status via /v1/agent-task/async/{task_id}"},
        401: {"description": "Cloudflare Access JWT invalid"},
        429: {"description": "Rate limit exceeded"},
    },
)
async def agent_task_async(
    req: AgentTaskRequest,
    identity: str = Depends(verify_cf_access),
    settings: Settings = Depends(get_settings),
) -> AsyncTaskAccepted:
    """Submit an agent task asynchronously. Wave 67 mirror of briefing-task/async.

    Couche-2 agents (cb_nlp, news_nlp, sentiment, positioning, macro) use
    this to bypass the Cloudflare Tunnel 100s edge timeout that hits Haiku
    big-prompt runs.
    """
    if not _rate_limiter.try_acquire():
        log.warning(
            "claude_runner.agent_async.rate_limited",
            task_id=str(req.task_id),
            requester=identity,
            window_count=_rate_limiter.current_count(),
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Hourly rate limit exceeded — Max 20x quota self-protection",
        )

    _async_task_gc()

    task_id = str(req.task_id)
    _async_tasks[task_id] = {
        "status": "pending",
        "result": None,
        "error": None,
        "started_at": time.monotonic(),
        "kind": "agent",
    }

    log.info(
        "claude_runner.agent_async.accepted",
        task_id=task_id,
        model=req.model,
        effort=req.effort,
        prompt_len=len(req.prompt),
        system_len=len(req.system),
        requester=identity,
    )

    bg_task = asyncio.create_task(_run_agent_background(task_id, req, settings))
    _async_tasks[task_id]["_bg_task"] = bg_task

    return AsyncTaskAccepted(
        task_id=req.task_id,
        status="pending",
        poll_url=f"/v1/agent-task/async/{task_id}",
        poll_interval_sec=5,
    )


@app.get(
    "/v1/agent-task/async/{task_id}",
    response_model=AsyncTaskStatus,
    responses={
        200: {"description": "Task status (poll until status='done' or 'error')"},
        401: {"description": "Cloudflare Access JWT invalid"},
        404: {"description": "task_id unknown (expired or never submitted)"},
    },
)
async def agent_task_async_status(
    task_id: str,
    identity: str = Depends(verify_cf_access),
) -> AsyncTaskStatus:
    """Poll the status of an async agent task. Each call <100ms."""
    task = _async_tasks.get(task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"task_id {task_id} unknown (expired after {_ASYNC_TASK_TTL_SEC}s, or never submitted)",
        )
    elapsed = time.monotonic() - task["started_at"]
    return AsyncTaskStatus(
        task_id=UUID(task_id),
        status=task["status"],
        elapsed_sec=round(elapsed, 1),
        result=task["result"],
        error=task["error"],
    )
