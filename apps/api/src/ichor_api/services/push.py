"""PWA Web Push service — VAPID + Redis-backed subscription store.

V1 keeps subscriptions in Redis (set `ichor:push:subs`) instead of a
SQL table to skip an alembic migration. When the volume justifies it,
we'll move to a `push_subscriptions` hypertable.

VISION_2026 — sprint R, mobile push notifications.

Flow :
  1. Browser service worker registers Push subscription
  2. Browser POSTs subscription JSON to /v1/push/subscribe
  3. Service stores it in Redis (deduped by endpoint URL)
  4. Whenever a notable event lands (session_card approved,
     critical alert, …), `send_to_all()` is called and pywebpush
     signs + delivers each notification.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import structlog

from ..config import get_settings

log = structlog.get_logger(__name__)

_REDIS_KEY = "ichor:push:subs"


@dataclass(frozen=True)
class PushSubscription:
    endpoint: str
    p256dh: str
    auth: str

    def to_json_dict(self) -> dict:
        return {
            "endpoint": self.endpoint,
            "keys": {"p256dh": self.p256dh, "auth": self.auth},
        }

    @classmethod
    def from_browser_payload(cls, payload: dict) -> PushSubscription | None:
        endpoint = payload.get("endpoint")
        keys = payload.get("keys") or {}
        p256dh = keys.get("p256dh")
        auth = keys.get("auth")
        if not (endpoint and p256dh and auth):
            return None
        return cls(endpoint=endpoint, p256dh=p256dh, auth=auth)


async def _redis():
    from redis import asyncio as aioredis  # type: ignore[import]

    settings = get_settings()
    return aioredis.from_url(settings.redis_url, decode_responses=True)


async def store_subscription(sub: PushSubscription) -> bool:
    """Add a subscription to the Redis set. Returns True if newly added."""
    r = await _redis()
    try:
        added = await r.sadd(_REDIS_KEY, json.dumps(sub.to_json_dict()))
        return bool(added)
    finally:
        await r.aclose()


async def list_subscriptions() -> list[PushSubscription]:
    r = await _redis()
    try:
        members = await r.smembers(_REDIS_KEY)
        out: list[PushSubscription] = []
        for raw in members:
            try:
                d = json.loads(raw)
                sub = PushSubscription.from_browser_payload(d)
                if sub:
                    out.append(sub)
            except json.JSONDecodeError:
                continue
        return out
    finally:
        await r.aclose()


async def remove_subscription(endpoint: str) -> int:
    """Remove all subscription entries matching the endpoint URL."""
    r = await _redis()
    try:
        members = await r.smembers(_REDIS_KEY)
        removed = 0
        for raw in members:
            try:
                d = json.loads(raw)
                if d.get("endpoint") == endpoint:
                    await r.srem(_REDIS_KEY, raw)
                    removed += 1
            except json.JSONDecodeError:
                continue
        return removed
    finally:
        await r.aclose()


async def send_to_all(title: str, body: str, *, url: str = "/") -> int:
    """Sign + deliver a notification to every stored subscription.

    Returns the number of successful deliveries. Failed endpoints
    (410 Gone) are evicted from the Redis set automatically.
    """
    settings = get_settings()
    if not (settings.vapid_public_key and settings.vapid_private_key):
        log.warning("push.no_vapid_keys")
        return 0

    try:
        from pywebpush import WebPushException, webpush  # type: ignore[import-untyped]
    except ImportError:
        log.warning("push.pywebpush_unavailable")
        return 0

    subs = await list_subscriptions()
    if not subs:
        return 0

    # Service worker (apps/web/public/sw.js) reads payload.title +
    # payload.body + payload.data.url. Match that shape here.
    payload = json.dumps({"title": title, "body": body, "data": {"url": url}})
    delivered = 0
    for sub in subs:
        try:
            webpush(
                subscription_info=sub.to_json_dict(),
                data=payload,
                vapid_private_key=settings.vapid_private_key,
                vapid_claims={
                    "sub": settings.vapid_contact,
                    "aud": _origin_of(sub.endpoint),
                },
            )
            delivered += 1
        except WebPushException as e:
            status_code = (getattr(e, "response", None) and e.response.status_code) or 0
            log.warning(
                "push.delivery_failed",
                endpoint=sub.endpoint[:80],
                status=status_code,
                error=str(e)[:200],
            )
            if status_code in (404, 410):
                await remove_subscription(sub.endpoint)
        except Exception as e:
            log.warning(
                "push.delivery_unexpected",
                endpoint=sub.endpoint[:80],
                error=str(e)[:200],
            )
    return delivered


def _origin_of(endpoint: str) -> str:
    """Extract scheme://host[:port] from a subscription endpoint URL.

    pywebpush expects the `aud` claim to match the push service origin
    (e.g. https://fcm.googleapis.com).
    """
    try:
        from urllib.parse import urlparse

        u = urlparse(endpoint)
        netloc = u.netloc
        return f"{u.scheme}://{netloc}"
    except Exception:
        return endpoint
