"""Feature flags — DB-backed + 60s in-process cache + Redis pub/sub.

Schema: `feature_flags(key, enabled, rollout_pct, description, created_at,
updated_at, created_by, updated_by)` — migration 0018.

**Cache scope**: the cache is a process-local dict (`_LOCAL_CACHE`)
**plus** a Redis pub/sub bus for cross-worker invalidation. On `set_flag`,
the new value is published to `ichor:ff:invalidate` ; every worker that
called `start_invalidation_subscriber()` (lifespan startup) listens and
clears its local entry. Result : kill-switches propagate in milliseconds
across uvicorn workers, not TTL × N seconds.

Read API (`is_enabled`) reads from cache, falls through to Postgres on
miss. Write API (`set_flag`) writes DB + invalidates local + publishes
to Redis. Subscribers invalidate on receipt.

Phase 3 multi-tenant: rollout_pct deterministic by hash(user_id) % 100,
SHA256 (cohort hashing — fast, deterministic, no crypto requirement but
modern default).

Cf docs/SPEC_V2_HARDENING.md §3.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

CACHE_KEY_PREFIX = "ichor:ff:"
CACHE_TTL_SECONDS = 60

# Redis pub/sub channel used for cross-worker invalidation. Workers
# subscribe in lifespan startup ; on each message body = flag key, the
# worker drops its local cache entry. Uses Redis even when a single
# worker is running (the subscriber is a no-op pass-through then).
INVALIDATION_CHANNEL = "ichor:ff:invalidate"

# Background subscriber state (one per process / event loop).
_SUBSCRIBER_TASK: asyncio.Task[None] | None = None
_SUBSCRIBER_REDIS_URL: str | None = None


@dataclass(frozen=True)
class FeatureFlag:
    key: str
    enabled: bool
    rollout_pct: int  # 0..100
    description: str | None
    updated_at: datetime


def _user_in_rollout(user_id: str | None, rollout_pct: int) -> bool:
    """Stable hash-based rollout cohort. None user → False unless 100%.

    SHA256 — overkill for cohort hashing but the modern default and
    avoids the legacy SHA1 lint flags. Deterministic so the same user
    always lands in the same bucket.
    """
    if rollout_pct >= 100:
        return True
    if rollout_pct <= 0 or user_id is None:
        return False
    h = hashlib.sha256(user_id.encode("utf-8")).digest()
    bucket = int.from_bytes(h[:4], "big") % 100
    return bucket < rollout_pct


async def _read_from_db(session: AsyncSession, key: str) -> FeatureFlag | None:
    row = (await session.execute(
        text(
            """
            SELECT key, enabled, rollout_pct, description, updated_at
            FROM feature_flags
            WHERE key = :key
            """
        ),
        {"key": key},
    )).mappings().first()
    if row is None:
        return None
    return FeatureFlag(
        key=str(row["key"]),
        enabled=bool(row["enabled"]),
        rollout_pct=int(row["rollout_pct"]),
        description=(str(row["description"]) if row["description"] is not None else None),
        updated_at=row["updated_at"],
    )


# Naive in-process cache: key → (value, expires_at). For multi-process
# this should move to Redis; the API surface is identical.
_LOCAL_CACHE: dict[str, tuple[dict[str, Any], float]] = {}


def _cache_get(key: str) -> dict[str, Any] | None:
    entry = _LOCAL_CACHE.get(CACHE_KEY_PREFIX + key)
    if entry is None:
        return None
    value, expires = entry
    if expires < time.monotonic():
        _LOCAL_CACHE.pop(CACHE_KEY_PREFIX + key, None)
        return None
    return value


def _cache_set(key: str, value: dict[str, Any]) -> None:
    _LOCAL_CACHE[CACHE_KEY_PREFIX + key] = (value, time.monotonic() + CACHE_TTL_SECONDS)


def _cache_invalidate(key: str) -> None:
    _LOCAL_CACHE.pop(CACHE_KEY_PREFIX + key, None)


async def is_enabled(
    session: AsyncSession,
    key: str,
    *,
    user_id: str | None = None,
) -> bool:
    """Hot path. Returns False if the flag doesn't exist (fail-closed).

    Order:
      1. Check process-local 60s cache
      2. Read DB on miss
      3. Apply rollout_pct cohort check
    """
    cached = _cache_get(key)
    if cached is None:
        flag = await _read_from_db(session, key)
        if flag is None:
            _cache_set(key, {"enabled": False, "rollout_pct": 0})
            return False
        cached = {"enabled": flag.enabled, "rollout_pct": flag.rollout_pct}
        _cache_set(key, cached)
    if not cached.get("enabled", False):
        return False
    return _user_in_rollout(user_id, int(cached.get("rollout_pct", 0)))


async def _publish_invalidation(redis_url: str | None, key: str) -> None:
    """Best-effort publish to the cross-worker invalidation channel.

    No-ops when redis is not reachable / not configured — the local
    invalidation already happened in the calling worker, so the only
    effect of a publish failure is "other workers wait up to 60s for
    their own TTL to expire", which is the previous behavior.
    """
    if not redis_url:
        return
    try:
        from redis import asyncio as aioredis

        r = aioredis.from_url(redis_url)
        try:
            await r.publish(INVALIDATION_CHANNEL, key)
        finally:
            await r.close()
    except Exception as exc:  # noqa: BLE001 — best-effort
        log.debug("feature_flags: invalidation publish failed (%s)", exc)


async def set_flag(
    session: AsyncSession,
    key: str,
    *,
    enabled: bool,
    rollout_pct: int = 100,
    description: str | None = None,
    actor: str = "system",
    redis_url: str | None = None,
) -> FeatureFlag:
    """Upsert a flag and invalidate cache. Write path.

    `redis_url` (optional) lets callers override the URL ; when omitted
    the value is read from `get_settings().redis_url`. Cross-worker
    invalidation is best-effort : DB + local-cache invalidation always
    happen ; the publish is silenced on Redis errors.
    """
    if not 0 <= rollout_pct <= 100:
        raise ValueError("rollout_pct must be in [0, 100]")
    now = datetime.now(timezone.utc)
    await session.execute(
        text(
            """
            INSERT INTO feature_flags
                (key, enabled, rollout_pct, description, created_at, updated_at,
                 created_by, updated_by)
            VALUES
                (:key, :enabled, :pct, :desc, :now, :now, :actor, :actor)
            ON CONFLICT (key) DO UPDATE SET
                enabled = EXCLUDED.enabled,
                rollout_pct = EXCLUDED.rollout_pct,
                description = COALESCE(EXCLUDED.description, feature_flags.description),
                updated_at = EXCLUDED.updated_at,
                updated_by = EXCLUDED.updated_by
            """
        ),
        {
            "key": key,
            "enabled": enabled,
            "pct": rollout_pct,
            "desc": description,
            "now": now,
            "actor": actor,
        },
    )
    _cache_invalidate(key)
    if redis_url is None:
        try:
            from ..config import get_settings

            redis_url = get_settings().redis_url
        except Exception:
            redis_url = None
    await _publish_invalidation(redis_url, key)
    return FeatureFlag(
        key=key,
        enabled=enabled,
        rollout_pct=rollout_pct,
        description=description,
        updated_at=now,
    )


async def _invalidation_loop(redis_url: str) -> None:
    """Background coroutine : subscribe to the invalidation channel.

    On each message, the body is the flag key — drop it from the local
    cache. Reconnects with backoff on Redis errors so a transient drop
    doesn't take the worker out of the cluster permanently.
    """
    backoff = 1.0
    while True:
        try:
            from redis import asyncio as aioredis

            r = aioredis.from_url(redis_url)
            pubsub = r.pubsub()
            await pubsub.subscribe(INVALIDATION_CHANNEL)
            log.info(
                "feature_flags: subscribed to %s for cross-worker invalidation",
                INVALIDATION_CHANNEL,
            )
            backoff = 1.0
            try:
                async for msg in pubsub.listen():
                    if msg.get("type") != "message":
                        continue
                    raw = msg.get("data")
                    key = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
                    if key:
                        _cache_invalidate(key)
            finally:
                with contextlib.suppress(Exception):
                    await pubsub.unsubscribe(INVALIDATION_CHANNEL)
                    await pubsub.close()
                    await r.close()
        except asyncio.CancelledError:
            return
        except Exception as exc:  # noqa: BLE001 — long-running supervisor
            log.warning(
                "feature_flags: invalidation subscriber error (retry in %.1fs): %s",
                backoff,
                exc,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)


def start_invalidation_subscriber(redis_url: str) -> asyncio.Task[None]:
    """Start (or reuse) the background invalidation subscriber.

    Idempotent : if already started for this process, returns the
    existing Task. Wired in `main.lifespan`.
    """
    global _SUBSCRIBER_TASK, _SUBSCRIBER_REDIS_URL
    if _SUBSCRIBER_TASK is not None and not _SUBSCRIBER_TASK.done():
        return _SUBSCRIBER_TASK
    _SUBSCRIBER_REDIS_URL = redis_url
    _SUBSCRIBER_TASK = asyncio.create_task(
        _invalidation_loop(redis_url),
        name="feature_flags-invalidation",
    )
    return _SUBSCRIBER_TASK


async def stop_invalidation_subscriber() -> None:
    """Cancel the subscriber task. Safe to call multiple times / when not started."""
    global _SUBSCRIBER_TASK
    if _SUBSCRIBER_TASK is None:
        return
    _SUBSCRIBER_TASK.cancel()
    with contextlib.suppress(asyncio.CancelledError, Exception):
        await _SUBSCRIBER_TASK
    _SUBSCRIBER_TASK = None


async def list_all(session: AsyncSession) -> list[FeatureFlag]:
    """Used by /admin UI to surface all flags."""
    rows = (await session.execute(
        text(
            """
            SELECT key, enabled, rollout_pct, description, updated_at
            FROM feature_flags
            ORDER BY key
            """
        )
    )).mappings().all()
    return [
        FeatureFlag(
            key=str(r["key"]),
            enabled=bool(r["enabled"]),
            rollout_pct=int(r["rollout_pct"]),
            description=(str(r["description"]) if r["description"] is not None else None),
            updated_at=r["updated_at"],
        )
        for r in rows
    ]
