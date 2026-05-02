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

import structlog
from fastapi import Depends, FastAPI, HTTPException, status

from . import __version__
from .auth import verify_cf_access
from .config import Settings, get_settings
from .models import BriefingTaskRequest, BriefingTaskResponse, HealthResponse
from .rate_limiter import HourlyRateLimiter
from .subprocess_runner import ClaudeSubprocessError, run_claude

log = structlog.get_logger(__name__)


# Module-global state initialized in lifespan
_subprocess_semaphore: asyncio.Semaphore
_rate_limiter: HourlyRateLimiter
_in_flight = 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize global state at startup, cleanup on shutdown."""
    global _subprocess_semaphore, _rate_limiter

    settings = get_settings()
    _subprocess_semaphore = asyncio.Semaphore(settings.max_concurrent_subprocess)
    _rate_limiter = HourlyRateLimiter(settings.rate_limit_per_hour)

    settings.workdir.mkdir(parents=True, exist_ok=True)

    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            {
                "DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40,
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
            settings.claude_binary, "--version",
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=5)
        cli_available = proc.returncode == 0
    except (FileNotFoundError, asyncio.TimeoutError):
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
        except asyncio.TimeoutError:
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
        text_blocks = [b.get("text", "") for b in result.get("content", []) if b.get("type") == "text"]
        briefing_md = "\n\n".join(text_blocks).strip() or None

    return BriefingTaskResponse(
        task_id=req.task_id,
        status="success",
        briefing_markdown=briefing_md,
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
    }
