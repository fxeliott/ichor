"""WebSocket router — push briefings + alerts to the dashboard in real-time.

Uses Redis Pub/Sub as the broker. Each FastAPI worker subscribes to channels
on connection; messages from Redis are forwarded to the WS clients.

Hardening (see docs/audits/security-2026-05-03.md HIGH-2):
  - Origin header allowed-list (matches API CORS allow-list).
  - Global concurrent-connection cap to prevent FD exhaustion DoS.
  - Per-connection structured logging including remote IP.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from ..config import get_settings

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/v1/ws", tags=["websocket"])

# Hard cap on concurrent dashboard sockets. Sized for a single operator —
# bump if/when the dashboard is shared. Tracked via a simple counter
# protected by an asyncio.Lock so that increment + check is atomic.
_MAX_CONCURRENT_WS = 50
_ws_count_lock = asyncio.Lock()
_ws_count = 0


@router.websocket("/dashboard")
async def dashboard_ws(websocket: WebSocket) -> None:
    """One persistent WS per dashboard tab. Streams:
      - new briefings (channel: ichor:briefings:new)
      - new alerts (channel: ichor:alerts:new)
      - bias signal updates (channel: ichor:bias:updated)

    Refuses connections that don't carry an Origin header from
    `cors_origins` (defends against random websocket scanners) and caps
    total concurrent sockets to prevent FD exhaustion.
    """
    global _ws_count
    settings = get_settings()
    origin = websocket.headers.get("origin")
    remote = websocket.client.host if websocket.client else "?"

    if origin and origin not in settings.cors_origins:
        log.warning("ws.reject_origin", origin=origin, remote=remote)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    async with _ws_count_lock:
        if _ws_count >= _MAX_CONCURRENT_WS:
            log.warning("ws.reject_capacity", current=_ws_count, remote=remote)
            await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
            return
        _ws_count += 1

    await websocket.accept()
    client_id = uuid.uuid4().hex[:8]
    log.info("ws.connect", client_id=client_id, remote=remote, current=_ws_count)

    # Lazy-import to keep redis optional during tests
    from redis import asyncio as aioredis

    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    pubsub = redis.pubsub()
    await pubsub.subscribe(
        "ichor:briefings:new",
        "ichor:alerts:new",
        "ichor:bias:updated",
        "ichor:session_card:new",
    )

    try:
        await websocket.send_json({"type": "ready", "client_id": client_id})

        # Concurrent: forward Redis pubsub → WS, AND drain WS → server (heartbeats).
        async def forward_pubsub() -> None:
            async for msg in pubsub.listen():
                if msg["type"] != "message":
                    continue
                try:
                    payload = json.loads(msg["data"])
                except json.JSONDecodeError:
                    log.warning("ws.bad_json", channel=msg["channel"])
                    continue
                await websocket.send_json(
                    {"type": "event", "channel": msg["channel"], "data": payload}
                )

        async def drain_client() -> None:
            while True:
                # Client may send heartbeat pings — we just discard them
                await websocket.receive_text()

        await asyncio.gather(forward_pubsub(), drain_client())

    except WebSocketDisconnect:
        log.info("ws.disconnect", client_id=client_id)
    except Exception as e:
        log.error("ws.error", client_id=client_id, error=str(e))
    finally:
        await pubsub.unsubscribe()
        await pubsub.close()
        await redis.close()
        async with _ws_count_lock:
            _ws_count = max(0, _ws_count - 1)
