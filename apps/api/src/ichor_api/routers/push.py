"""POST /v1/push/subscribe + GET /v1/push/public-key + test send.

Powers the PWA push notification flow.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..config import get_settings
from ..services.push import (
    PushSubscription,
    list_subscriptions,
    remove_subscription,
    send_to_all,
    store_subscription,
)

router = APIRouter(prefix="/v1/push", tags=["push"])


class PublicKeyOut(BaseModel):
    public_key: str
    contact: str


class SubscribeIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2048)
    keys: dict[str, str]


class SubscribeOut(BaseModel):
    added: bool
    endpoint: str
    total_subscriptions: int


class UnsubscribeIn(BaseModel):
    endpoint: str


class TestSendIn(BaseModel):
    title: str = "Ichor · test"
    body: str = "Notification de test envoyée par le service push."
    url: str = "/"


@router.get("/public-key", response_model=PublicKeyOut)
async def get_public_key() -> PublicKeyOut:
    """Browser fetches this on activation to register its subscription."""
    settings = get_settings()
    if not settings.vapid_public_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="VAPID public key not configured",
        )
    return PublicKeyOut(
        public_key=settings.vapid_public_key,
        contact=settings.vapid_contact,
    )


@router.post("/subscribe", response_model=SubscribeOut)
async def subscribe(body: SubscribeIn) -> SubscribeOut:
    sub = PushSubscription.from_browser_payload(body.model_dump())
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="missing endpoint / keys.p256dh / keys.auth",
        )
    added = await store_subscription(sub)
    total = len(await list_subscriptions())
    return SubscribeOut(added=added, endpoint=sub.endpoint, total_subscriptions=total)


@router.post("/unsubscribe", response_model=dict[str, Any])
async def unsubscribe(body: UnsubscribeIn) -> dict[str, Any]:
    n = await remove_subscription(body.endpoint)
    return {"removed": n, "endpoint": body.endpoint}


@router.post("/test", response_model=dict[str, Any])
async def test_send(body: TestSendIn) -> dict[str, Any]:
    """Deliver a test notification to every stored subscription."""
    delivered = await send_to_all(body.title, body.body, url=body.url)
    return {"delivered": delivered}
