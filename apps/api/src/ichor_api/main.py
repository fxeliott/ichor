"""FastAPI app factory + top-level app instance."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from . import __version__
from .config import get_settings
from .db import get_engine, get_session
from .routers import (
    admin_router,
    alerts_router,
    bias_signals_router,
    briefings_router,
    brier_feedback_router,
    calendar_router,
    calibration_router,
    confluence_router,
    correlations_router,
    counterfactual_router,
    currency_strength_router,
    data_pool_router,
    divergence_router,
    economic_events_router,
    geopolitics_router,
    graph_router,
    hourly_volatility_router,
    macro_pulse_router,
    market_router,
    narratives_router,
    news_router,
    polymarket_impact_router,
    portfolio_exposure_router,
    post_mortems_router,
    predictions_router,
    push_router,
    scenarios_router,
    sessions_router,
    sources_router,
    today_router,
    trade_plan_router,
    ws_router,
    yield_curve_router,
)
from .schemas import CollectorLag, HealthDetailedOut, HealthOut

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
    # SECURITY: refuse to start in production with a wildcard CORS list.
    # See MED-5 in docs/audits/security-2026-05-03.md.
    if settings.environment == "production" and "*" in settings.cors_origins:
        raise RuntimeError(
            "Refusing to start: CORS origins contains '*' in production. "
            "Set ICHOR_API_CORS_ORIGINS to an explicit list of allowed origins."
        )
    log.info(
        "api.startup",
        version=__version__,
        environment=settings.environment,
        cors_origins=settings.cors_origins,
    )
    # Start the cross-worker feature_flags invalidation subscriber so
    # kill-switches propagate in ms instead of waiting for the 60s TTL.
    from .services.feature_flags import (
        start_invalidation_subscriber,
        stop_invalidation_subscriber,
    )

    try:
        start_invalidation_subscriber(settings.redis_url)
    except Exception as exc:
        log.warning("api.feature_flags.subscriber_start_failed", error=str(exc))
    yield
    try:
        await stop_invalidation_subscriber()
    except Exception as exc:
        log.warning("api.feature_flags.subscriber_stop_failed", error=str(exc))
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

# SPEC_V2_HARDENING : audit_log on POST/PUT/PATCH/DELETE + rate limiter.
# Both fail-OPEN on backing-store errors (DB / Redis) so the API
# stays up. Audit log path is best-effort — production observability
# falls back to journal logs if the table is unreachable.
from .services.audit_log import AuditLogMiddleware  # noqa: E402
from .services.csp_middleware import CSPSecurityHeadersMiddleware  # noqa: E402
from .services.rate_limiter import RateLimitMiddleware, make_redis_client  # noqa: E402

app.add_middleware(AuditLogMiddleware, get_session=get_session)
app.add_middleware(
    RateLimitMiddleware,
    redis_client=make_redis_client(_settings.redis_url),
    budget_per_min=120,
)
# CSP + security headers — outermost layer so every response (even
# rate-limited 429s) carries the policy.
app.add_middleware(CSPSecurityHeadersMiddleware)

# Routers
app.include_router(briefings_router)
app.include_router(alerts_router)
app.include_router(bias_signals_router)
app.include_router(news_router)
app.include_router(market_router)
app.include_router(predictions_router)
app.include_router(sessions_router)
app.include_router(calibration_router)
app.include_router(narratives_router)
app.include_router(graph_router)
app.include_router(geopolitics_router)
app.include_router(counterfactual_router)
app.include_router(data_pool_router)
app.include_router(divergence_router)
app.include_router(trade_plan_router)
app.include_router(confluence_router)
app.include_router(currency_strength_router)
app.include_router(calendar_router)
app.include_router(economic_events_router)
app.include_router(correlations_router)
app.include_router(hourly_volatility_router)
app.include_router(brier_feedback_router)
app.include_router(macro_pulse_router)
app.include_router(polymarket_impact_router)
app.include_router(portfolio_exposure_router)
app.include_router(post_mortems_router)
app.include_router(scenarios_router)
app.include_router(sources_router)
app.include_router(today_router)
app.include_router(push_router)
app.include_router(admin_router)
app.include_router(yield_curve_router)
app.include_router(ws_router)


# ── Health probes split (HARDENING §3) ─────────────────────────────────
# /livez     — process alive (cheap, no I/O). For Kubernetes-style
#              liveness probe + nginx upstream health check.
# /readyz    — ready to serve traffic (DB + Redis + alembic head).
# /startupz  — boot complete (extensions loaded, e.g. pgvector).
# /healthz   — kept for backward compat; aliases /readyz.


@app.get("/livez", include_in_schema=False)
async def livez() -> dict[str, str]:
    """Process alive — no I/O, always 200 unless event loop is wedged."""
    return {"status": "ok", "version": __version__}


@app.get("/readyz", include_in_schema=False)
async def readyz() -> dict[str, object]:
    """Ready to serve: DB + Redis reachable, alembic up to date.

    Returns 200 with status=ok when fully ready, 503 with structured
    body otherwise. Used by nginx blue-green upstream switch (cf
    HARDENING §3).
    """
    from fastapi import Response

    db_ok = False
    redis_ok = False
    alembic_ok = False
    try:
        async for s in get_session():
            await s.execute(text("SELECT 1"))
            db_ok = True
            try:
                head = (
                    await s.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
                ).scalar()
                alembic_ok = head is not None
            except Exception:
                alembic_ok = False
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

    ready = db_ok and redis_ok and alembic_ok
    body: dict[str, object] = {
        "status": "ok" if ready else "not_ready",
        "checks": {
            "db": db_ok,
            "redis": redis_ok,
            "alembic_head": alembic_ok,
        },
    }
    return Response(  # type: ignore[return-value]
        content=__import__("json").dumps(body),
        media_type="application/json",
        status_code=200 if ready else 503,
    )


@app.get("/startupz", include_in_schema=False)
async def startupz() -> dict[str, object]:
    """Startup complete: pgvector extension installed (Phase 2 RAG)."""
    from fastapi import Response

    pgvector_ok = False
    try:
        async for s in get_session():
            row = (
                await s.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
            ).scalar()
            pgvector_ok = bool(row)
            break
    except Exception:
        pass

    body = {
        "status": "ok" if pgvector_ok else "starting",
        "checks": {"pgvector": pgvector_ok},
    }
    return Response(  # type: ignore[return-value]
        content=__import__("json").dumps(body),
        media_type="application/json",
        status_code=200 if pgvector_ok else 503,
    )


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


@app.get("/healthz/detailed", response_model=HealthDetailedOut)
async def healthz_detailed() -> HealthDetailedOut:
    """Fuller probe used by Grafana + RUNBOOK-011 (collector stalled).

    Adds : last briefing timestamp + lag, unack-alert counts by severity,
    per-collector last-fetch timestamps. All read-only — safe to poll
    every 30 s.
    """
    from datetime import datetime

    # Reuse the cheap probe to get db/redis status
    base = await healthz()

    last_briefing_at: datetime | None = None
    minutes_since_last_briefing: float | None = None
    unack_critical = 0
    unack_warning = 0
    collectors: list[CollectorLag] = []
    now = datetime.now(UTC)

    if base.db_connected:
        try:
            async for session in get_session():
                # Last completed briefing
                row = (
                    await session.execute(
                        text("SELECT max(triggered_at) FROM briefings WHERE status = 'completed'")
                    )
                ).first()
                if row and row[0]:
                    last_briefing_at = row[0]
                    minutes_since_last_briefing = (now - row[0]).total_seconds() / 60

                # Unack alerts by severity
                rows = (
                    await session.execute(
                        text(
                            "SELECT severity, count(*) FROM alerts "
                            "WHERE acknowledged_at IS NULL GROUP BY severity"
                        )
                    )
                ).all()
                for sev, cnt in rows:
                    if sev == "critical":
                        unack_critical = cnt
                    elif sev == "warning":
                        unack_warning = cnt

                # Per-collector lag
                rows = (
                    await session.execute(
                        text(
                            "SELECT source, max(fetched_at) FROM news_items "
                            "GROUP BY source ORDER BY source"
                        )
                    )
                ).all()
                for src, last in rows:
                    minutes_stale = (now - last).total_seconds() / 60 if last else None
                    collectors.append(
                        CollectorLag(source=src, last_fetched_at=last, minutes_stale=minutes_stale)
                    )
                break
        except Exception:
            pass

    return HealthDetailedOut(
        status=base.status,
        version=base.version,
        db_connected=base.db_connected,
        redis_connected=base.redis_connected,
        last_briefing_at=last_briefing_at,
        minutes_since_last_briefing=minutes_since_last_briefing,
        unack_alerts_critical=unack_critical,
        unack_alerts_warning=unack_warning,
        collectors=collectors,
    )
