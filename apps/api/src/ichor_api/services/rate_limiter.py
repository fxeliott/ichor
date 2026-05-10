"""Distributed rate limiter middleware — Redis-backed fixed window.

Simpler than slowapi (no external dep, ~80 lines), tuned for Ichor's
API shape :
  - skip /healthz / /metrics / OPTIONS (don't penalize liveness probes)
  - separate buckets per (client IP × route prefix) so /v1/predictions
    abuse doesn't lock the dashboard out of /v1/today
  - fail-OPEN on Redis errors (better to allow than to 503 the whole
    API on a transient Redis hiccup)
  - return X-RateLimit-* headers + Retry-After on 429 (per RFC 6585)

Default budget : 120 req/min per (IP, route prefix). Override via
constructor args. Override per-route by adding the route's first
segment to PER_ROUTE_LIMITS.

Algorithm : fixed window via INCR + EXPIRE on first set. Slightly
less smooth than sliding window but Lua-script-free and atomic
(INCR is atomic ; the race window between INCR and EXPIRE is
acceptable because the very first request just sets a longer TTL
than ideal — never permits more requests than the budget).

Reference (2026 best practice):
  - https://github.com/laurentS/slowapi  (the slowapi pattern we mirror)
  - https://blog.stoplight.io/api-keys-best-practices-to-authenticate-apis
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


_DEFAULT_BUDGET_PER_MIN = 120

# Tighter limits per route prefix. Add entries here to override.
# Match is on the FIRST segment after /v1/ (e.g., /v1/predictions/123 → "predictions").
PER_ROUTE_LIMITS: dict[str, int] = {
    "predictions": 60,  # Couche-2 outputs
    "counterfactual": 20,  # Pass 5 — expensive Claude call per request
    "trade-plan": 30,
    "scenarios": 30,
}

# Liveness / metric paths bypass the limiter entirely.
_SKIP_PATHS = (
    "/healthz",
    "/livez",
    "/readyz",
    "/startupz",
    "/metrics",
    "/openapi.json",
    "/docs",
    "/redoc",
)
_SKIP_METHODS = {"OPTIONS", "HEAD"}


def _route_prefix(path: str) -> str:
    """First segment after /v1/ — used as a budget bucket."""
    if not path.startswith("/v1/"):
        return "_root"
    rest = path[4:]
    seg = rest.split("/", 1)[0]
    return seg or "_root"


class RateLimitMiddleware:
    """ASGI middleware. Plug via:
    app.add_middleware(
        RateLimitMiddleware,
        redis_client=redis_async,
        budget_per_min=120,
    )
    """

    def __init__(
        self,
        app,
        *,
        redis_client: Any | None = None,
        budget_per_min: int = _DEFAULT_BUDGET_PER_MIN,
        per_route_limits: dict[str, int] | None = None,
        window_seconds: int = 60,
    ) -> None:
        self.app = app
        self._redis = redis_client
        self._default_budget = max(1, int(budget_per_min))
        self._limits = dict(PER_ROUTE_LIMITS)
        if per_route_limits:
            self._limits.update(per_route_limits)
        self._window = max(1, int(window_seconds))

    def _budget_for(self, prefix: str) -> int:
        return self._limits.get(prefix, self._default_budget)

    async def _incr_and_check(self, key: str, budget: int) -> tuple[bool, int, int]:
        """Returns (allowed, current_count, ttl_seconds).

        On Redis error returns (True, -1, -1) — fail-OPEN so the API
        stays up under Redis flakiness.
        """
        if self._redis is None:
            return True, -1, -1
        try:
            count = await self._redis.incr(key)
            if count == 1:
                await self._redis.expire(key, self._window)
            ttl = await self._redis.ttl(key)
            return count <= budget, int(count), int(ttl)
        except Exception as exc:
            log.debug("rate_limiter.redis_error key=%s err=%s", key, exc)
            return True, -1, -1

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "")
        path = scope.get("path", "") or ""
        if method in _SKIP_METHODS or any(path.startswith(p) for p in _SKIP_PATHS):
            await self.app(scope, receive, send)
            return

        client = scope.get("client") or (None, None)
        ip = client[0] if client else "unknown"
        prefix = _route_prefix(path)
        budget = self._budget_for(prefix)
        key = f"ichor:rl:{ip}:{prefix}"

        allowed, count, ttl = await self._incr_and_check(key, budget)

        async def _send_with_headers(message: dict[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                new_message = dict(message)
                headers = list(message.get("headers", []))
                # Always include rate-limit observability headers
                if count >= 0:
                    remaining = max(0, budget - count)
                    headers.extend(
                        [
                            (b"x-ratelimit-limit", str(budget).encode()),
                            (b"x-ratelimit-remaining", str(remaining).encode()),
                            (b"x-ratelimit-reset", str(max(0, ttl)).encode()),
                        ]
                    )
                new_message["headers"] = headers
                await send(new_message)
                return
            await send(message)

        if not allowed:
            # 429 Too Many Requests
            retry_after = max(1, ttl if ttl > 0 else self._window)
            body = (
                b'{"detail":"Too Many Requests","retry_after_seconds":'
                + str(retry_after).encode()
                + b"}"
            )
            await send(
                {
                    "type": "http.response.start",
                    "status": 429,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"retry-after", str(retry_after).encode()),
                        (b"x-ratelimit-limit", str(budget).encode()),
                        (b"x-ratelimit-remaining", b"0"),
                        (b"x-ratelimit-reset", str(retry_after).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        await self.app(scope, receive, _send_with_headers)


# ── Convenience factory ─────────────────────────────────────────────


def make_redis_client(redis_url: str) -> Any | None:
    """Return an async Redis client or None if redis lib is missing.

    We use redis.asyncio.Redis from the `redis` package which is
    already pinned in the venv (cf existing redis_url config + caches).
    """
    try:
        import redis.asyncio as redis_async  # type: ignore[import-not-found]
    except ImportError:
        log.warning("rate_limiter.redis_lib_missing — running without rate limit")
        return None
    try:
        return redis_async.from_url(redis_url, decode_responses=False)
    except Exception as exc:
        log.warning("rate_limiter.redis_init_failed err=%s", exc)
        return None
