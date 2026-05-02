"""WebSocket router — push briefings + alerts to the dashboard in real-time.

Uses Redis Pub/Sub as the broker. Each FastAPI worker subscribes to channels
on connection; messages from Redis are forwarded to the WS clients.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..config import get_settings

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/v1/ws", tags=["websocket"])


@router.websocket("/dashboard")
async def dashboard_ws(websocket: WebSocket) -> None:
    """One persistent WS per dashboard tab. Streams:
      - new briefings (channel: ichor:briefings:new)
      - new alerts (channel: ichor:alerts:new)
      - bias signal updates (channel: ichor:bias:updated)
    """
    await websocket.accept()
    client_id = uuid.uuid4().hex[:8]
    log.info("ws.connect", client_id=client_id)

    settings = get_settings()
    # Lazy-import to keep redis optional during tests
    from redis import asyncio as aioredis

    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    pubsub = redis.pubsub()
    await pubsub.subscribe("ichor:briefings:new", "ichor:alerts:new", "ichor:bias:updated")

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
                await websocket.send_json({"type": "event", "channel": msg["channel"], "data": payload})

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
