"""FastAPI app factory + top-level app instance."""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from . import __version__
from .config import get_settings
from .db import get_engine, get_session
from .routers import alerts_router, bias_signals_router, briefings_router, ws_router
from .schemas import HealthOut

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ]
    )
    log.info("api.startup", version=__version__, environment=settings.environment)
    yield
    await get_engine().dispose()
    log.info("api.shutdown")


app = FastAPI(
    title="Ichor API",
    version=__version__,
    description="Hetzner backend — briefings, alerts, bias signals, WebSocket.",
    lifespan=lifespan,
)

# CORS for the Cloudflare Pages dashboard
_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Routers
app.include_router(briefings_router)
app.include_router(alerts_router)
app.include_router(bias_signals_router)
app.include_router(ws_router)


@app.get("/healthz", response_model=HealthOut)
async def healthz() -> HealthOut:
    """Cheap readiness check — Postgres ping + Redis ping (no claude-runner test)."""
    db_ok = False
    redis_ok = False

    try:
        async for session in get_session():
            await session.execute(text("SELECT 1"))
            db_ok = True
            break
    except Exception:
        pass

    try:
        from redis import asyncio as aioredis
        r = aioredis.from_url(_settings.redis_url)
        await r.ping()
        redis_ok = True
        await r.close()
    except Exception:
        pass

    overall = "ok" if (db_ok and redis_ok) else ("degraded" if db_ok or redis_ok else "down")
    return HealthOut(
        status=overall,  # type: ignore[arg-type]
        version=__version__,
        db_connected=db_ok,
        redis_connected=redis_ok,
    )
