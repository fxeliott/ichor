"""FastAPI app factory + top-level app instance."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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
    journal_router,
    macro_pulse_router,
    market_router,
    narratives_router,
    news_router,
    phase_d_router,
    polymarket_impact_router,
    portfolio_exposure_router,
    post_mortems_router,
    predictions_router,
    push_router,
    scenarios_router,
    sessions_router,
    sources_router,
    today_router,
    tools_router,
    trade_plan_router,
    well_known_router,
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
    # SECURITY: refuse to start in production without the Capability 5
    # client-tool service token. The /v1/tools/* routes execute SQL on
    # behalf of the Win11 MCP server — without the token, anyone with
    # network reach to apps/api could drive the whitelisted SELECT
    # surface. ADR-077 § Auth.
    if settings.environment == "production" and not settings.tool_service_token.strip():
        raise RuntimeError(
            "Refusing to start: ICHOR_API_TOOL_SERVICE_TOKEN unset in "
            "production. /v1/tools/* would be exposed without "
            "service-token enforcement (ADR-077)."
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

    # Phase A.4.c — Langfuse client lifecycle (ADR-032).
    # Boot-safe: init returns None when keys absent or lib missing; all
    # @observe decorators downstream are fail-soft no-ops in that case.
    from .observability import flush_langfuse, init_langfuse

    init_langfuse()

    yield
    # Drain Langfuse worker queue BEFORE engine dispose so any in-flight
    # session-card trace finishes serialising while the DB pool is still
    # alive (the SDK's worker thread is daemonic and would otherwise be
    # killed on process exit).
    flush_langfuse()
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

# Phase A.4 observability — Prometheus /metrics endpoint.
# Wraps the Instrumentator in a try/except so a missing or broken lib
# never blocks API boot. Without /metrics the Prometheus scrape config
# (`infra/ansible/roles/observability/files/prometheus.yml:18-20`)
# silently fails — but the API itself stays up.
try:
    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_respect_env_var=False,
        excluded_handlers=["/healthz", "/metrics"],
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
    log.info("api.metrics_enabled")
except Exception as _metrics_exc:  # pragma: no cover — fail-soft observability
    log.warning("api.metrics_disabled", error=str(_metrics_exc)[:200])

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

# EU AI Act §50.2 — machine-readable watermark on LLM-derived routes
# (W88, ADR-079). Mounted INSIDE CSP (so CSP cannot strip the headers)
# and OUTSIDE rate-limiter (so 429 paths still carry the watermark
# when their body is LLM-derived). Enforcement date 2026-08-02.
from .middleware import AIWatermarkMiddleware  # noqa: E402

app.add_middleware(
    AIWatermarkMiddleware,
    watermarked_prefixes=_settings.ai_watermarked_route_prefixes,
    provider_tag=_settings.ai_provider_tag,
    disclosure_url=_settings.ai_disclosure_url,
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
app.include_router(journal_router)
app.include_router(brier_feedback_router)
app.include_router(macro_pulse_router)
app.include_router(polymarket_impact_router)
app.include_router(portfolio_exposure_router)
app.include_router(post_mortems_router)
app.include_router(phase_d_router)
app.include_router(scenarios_router)
app.include_router(sources_router)
app.include_router(today_router)
app.include_router(push_router)
app.include_router(admin_router)
app.include_router(yield_curve_router)
app.include_router(tools_router)
app.include_router(well_known_router)
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


@app.get("/healthz/deep", include_in_schema=False)
async def healthz_deep() -> dict[str, object]:
    """End-to-end synthetic probe — Phase A round-9 monitoring closure.

    Tests EVERY maillon of the production pipeline in one request :
      1. Postgres ping + alembic head version
      2. Redis ping
      3. claude-runner reachability (HTTP GET /healthz via CF Tunnel)
      4. scenario_calibration_bins row count (W105b cron health)
      5. session_card_audit last 24h count (briefing cron health)
      6. Most recent push subscribers count (G2 push notif readiness)

    Returns 200 with full JSON status per sub-system when all green,
    503 if any critical sub-system (db, redis, claude-runner) is down.
    Non-critical degradations (e.g. empty calibration rows) return
    200 with `degraded` flag.

    Run from Grafana / external probe / RUNBOOK-018-style checks.
    """
    import time as _time

    from sqlalchemy import text as _sql_text

    started = _time.time()
    body: dict[str, object] = {"timestamp": datetime.now(UTC).isoformat()}

    # 1. Postgres + alembic head
    db_ok = False
    alembic_head: str | None = None
    try:
        async for session in get_session():
            await session.execute(_sql_text("SELECT 1"))
            head_res = await session.execute(
                _sql_text("SELECT version_num FROM alembic_version LIMIT 1")
            )
            alembic_head = head_res.scalar()
            db_ok = True
            break
    except Exception as e:  # noqa: BLE001
        body["db_error"] = str(e)[:200]
    body["db_connected"] = db_ok
    body["alembic_head"] = alembic_head

    # 2. Redis
    redis_ok = False
    try:
        from redis import asyncio as aioredis

        r = aioredis.from_url(_settings.redis_url)
        await r.ping()
        redis_ok = True
        await r.close()
    except Exception as e:  # noqa: BLE001
        body["redis_error"] = str(e)[:200]
    body["redis_connected"] = redis_ok

    # 3. claude-runner reachability (via CF Tunnel + service token).
    runner_ok = False
    runner_url = _settings.claude_runner_url or ""
    if runner_url and _settings.cf_access_client_id and _settings.cf_access_client_secret:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    f"{runner_url}/healthz",
                    headers={
                        "CF-Access-Client-Id": _settings.cf_access_client_id,
                        "CF-Access-Client-Secret": _settings.cf_access_client_secret,
                    },
                )
                if r.status_code == 200 and r.json().get("status") == "ok":
                    runner_ok = True
                else:
                    body["runner_status_code"] = r.status_code
        except Exception as e:  # noqa: BLE001
            body["runner_error"] = str(e)[:200]
    body["claude_runner_reachable"] = runner_ok

    # 4. scenario_calibration_bins row count (W105b cron health).
    calibration_rows = 0
    try:
        async for session in get_session():
            cal_res = await session.execute(
                _sql_text("SELECT COUNT(*) FROM scenario_calibration_bins")
            )
            calibration_rows = int(cal_res.scalar() or 0)
            break
    except Exception:  # noqa: BLE001
        pass
    body["calibration_rows"] = calibration_rows

    # 5. Cards last 24h (briefing cron health).
    cards_24h = 0
    try:
        async for session in get_session():
            c_res = await session.execute(
                _sql_text(
                    "SELECT COUNT(*) FROM session_card_audit "
                    "WHERE generated_at > now() - interval '24 hours'"
                )
            )
            cards_24h = int(c_res.scalar() or 0)
            break
    except Exception:  # noqa: BLE001
        pass
    body["cards_last_24h"] = cards_24h

    # 6. Push subscribers (G2 push notif readiness).
    push_subs = 0
    try:
        from redis import asyncio as aioredis

        r = aioredis.from_url(_settings.redis_url)
        push_subs = int(await r.scard("ichor:push:subs") or 0)
        await r.close()
    except Exception:  # noqa: BLE001
        pass
    body["push_subscribers"] = push_subs

    body["elapsed_ms"] = int((_time.time() - started) * 1000)

    critical_ok = db_ok and redis_ok and runner_ok
    body["status"] = "ok" if critical_ok else "down"
    body["degraded_reasons"] = [
        r
        for r, cond in [
            ("no_calibration_rows", calibration_rows == 0),
            ("no_recent_cards", cards_24h == 0),
            ("no_push_subscribers", push_subs == 0),
        ]
        if cond
    ]

    return JSONResponse(content=body, status_code=200 if critical_ok else 503)


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
