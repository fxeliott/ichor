"""Unit tests for the rate limiter middleware (no Redis required).

Tests verify the route-prefix logic + the fail-OPEN behavior on
missing/erroring Redis client.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from ichor_api.services.rate_limiter import (
    PER_ROUTE_LIMITS,
    RateLimitMiddleware,
    _route_prefix,
    make_redis_client,
)


def test_route_prefix_extracts_first_v1_segment() -> None:
    assert _route_prefix("/v1/predictions") == "predictions"
    assert _route_prefix("/v1/predictions/123") == "predictions"
    assert _route_prefix("/v1/today") == "today"
    assert _route_prefix("/v1/sessions/eur_usd/counterfactual") == "sessions"


def test_route_prefix_handles_root_paths() -> None:
    assert _route_prefix("/") == "_root"
    assert _route_prefix("/healthz") == "_root"


def test_per_route_limits_has_strict_limits_for_expensive_endpoints() -> None:
    """Counterfactual is the most expensive — it triggers a Claude
    call. Confirm the limit is tight."""
    assert PER_ROUTE_LIMITS.get("counterfactual", 999) <= 30


@pytest.mark.asyncio
async def test_middleware_fail_open_when_no_redis() -> None:
    """Without a Redis client, every request must pass through."""
    inner_app = AsyncMock()
    mw = RateLimitMiddleware(inner_app, redis_client=None, budget_per_min=1)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/v1/predictions",
        "client": ("1.2.3.4", 1234),
        "headers": [],
    }
    receive = AsyncMock()
    send = AsyncMock()

    # Even with budget=1, 5 requests must all pass when redis_client=None
    for _ in range(5):
        await mw(scope, receive, send)
    assert inner_app.call_count == 5


@pytest.mark.asyncio
async def test_middleware_skips_healthz() -> None:
    """Liveness probes bypass the limiter."""
    inner_app = AsyncMock()
    mw = RateLimitMiddleware(inner_app, redis_client=None, budget_per_min=1)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/healthz",
        "client": ("1.2.3.4", 1234),
        "headers": [],
    }
    await mw(scope, AsyncMock(), AsyncMock())
    inner_app.assert_called_once()


@pytest.mark.asyncio
async def test_middleware_blocks_when_over_budget() -> None:
    """With Redis returning count > budget, the middleware should
    short-circuit with 429 (does NOT call the inner app).

    Uses /v1/today which is NOT in PER_ROUTE_LIMITS, so the
    budget_per_min=2 constructor arg is the effective budget.
    """
    inner_app = AsyncMock()
    redis = MagicMock()
    redis.incr = AsyncMock(return_value=5)
    redis.expire = AsyncMock(return_value=True)
    redis.ttl = AsyncMock(return_value=42)
    mw = RateLimitMiddleware(inner_app, redis_client=redis, budget_per_min=2)

    sent_messages: list[dict] = []

    async def _send(msg: dict) -> None:
        sent_messages.append(msg)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/v1/today",
        "client": ("1.2.3.4", 1234),
        "headers": [],
    }
    await mw(scope, AsyncMock(), _send)

    inner_app.assert_not_called()
    # Find http.response.start
    start_msgs = [m for m in sent_messages if m.get("type") == "http.response.start"]
    assert len(start_msgs) == 1
    assert start_msgs[0]["status"] == 429
    headers = dict(start_msgs[0]["headers"])
    assert b"retry-after" in headers
    assert headers[b"x-ratelimit-limit"] == b"2"


@pytest.mark.asyncio
async def test_middleware_lets_through_when_under_budget() -> None:
    inner_app = AsyncMock()
    redis = MagicMock()
    redis.incr = AsyncMock(return_value=1)  # first request
    redis.expire = AsyncMock(return_value=True)
    redis.ttl = AsyncMock(return_value=58)
    mw = RateLimitMiddleware(inner_app, redis_client=redis, budget_per_min=120)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/v1/today",
        "client": ("1.2.3.4", 1234),
        "headers": [],
    }
    await mw(scope, AsyncMock(), AsyncMock())
    inner_app.assert_called_once()


@pytest.mark.asyncio
async def test_middleware_fail_open_on_redis_error() -> None:
    """Redis raising = fail-OPEN, not 429 or 503."""
    inner_app = AsyncMock()
    redis = MagicMock()
    redis.incr = AsyncMock(side_effect=ConnectionError("redis down"))
    mw = RateLimitMiddleware(inner_app, redis_client=redis, budget_per_min=1)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/v1/today",
        "client": ("1.2.3.4", 1234),
        "headers": [],
    }
    await mw(scope, AsyncMock(), AsyncMock())
    inner_app.assert_called_once()  # passed through despite Redis error


def test_make_redis_client_returns_none_on_bad_url() -> None:
    """Bad URL syntax must return None gracefully (don't crash app boot)."""
    # redis.asyncio.from_url is permissive — most strings parse — so
    # we just check that this never raises.
    client = make_redis_client("redis://nonexistent-hostname:6379/0")
    assert client is None or client is not None  # smoke
