"""Manifold collector — community-priced prediction markets.

Manifold is play-money but well-calibrated on niche topics. Free REST API
with no auth needed for reads. Rate limit : 500 req/min/IP.

Use case for Ichor : 3rd opinion alongside Polymarket + Kalshi. Sometimes
Manifold prices niche events (e.g. "Will the Fed mention 'transitory' in
the May statement?") that the real-money markets don't bother with.

Docs : https://docs.manifold.markets/api
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
import structlog

log = structlog.get_logger(__name__)

MANIFOLD_API_BASE = "https://api.manifold.markets/v0"


# Phase 1 : a curated list of Manifold market slugs we follow. These come
# from the user creating them or from their public catalog. Slugs change
# rarely on Manifold (vs Polymarket).
WATCHED_SLUGS: tuple[str, ...] = (
    "will-the-fed-cut-rates-at-its-may",
    "will-the-fed-cut-rates-at-its-june",
    "will-the-us-enter-recession-in-2026",
    "will-china-pmi-be-above-50-in-may",
)


@dataclass
class ManifoldSnapshot:
    slug: str
    market_id: str
    question: str
    probability: float | None
    """Last probability for the YES outcome (0-1)."""
    volume: float | None
    """All-time volume in mana."""
    closed: bool
    creator_username: str | None
    fetched_at: datetime


async def fetch_market(
    slug: str, *, client: httpx.AsyncClient, timeout: float = 15.0
) -> ManifoldSnapshot | None:
    try:
        r = await client.get(
            f"{MANIFOLD_API_BASE}/slug/{slug}",
            timeout=timeout,
            headers={"User-Agent": "IchorManifoldCollector/0.1"},
        )
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPError as e:
        log.warning("manifold.fetch_failed", slug=slug, error=str(e))
        return None

    try:
        return ManifoldSnapshot(
            slug=slug[:128],
            market_id=str(data.get("id", "")),
            question=str(data.get("question", ""))[:512],
            probability=float(data["probability"]) if "probability" in data else None,
            volume=float(data["volume"]) if "volume" in data else None,
            closed=bool(data.get("isResolved", False) or data.get("closed", False)),
            creator_username=data.get("creatorUsername"),
            fetched_at=datetime.now(timezone.utc),
        )
    except (TypeError, ValueError, KeyError) as e:
        log.warning("manifold.parse_failed", slug=slug, error=str(e))
        return None


async def poll_all(
    slugs: tuple[str, ...] = WATCHED_SLUGS,
    *,
    concurrency: int = 4,
) -> list[ManifoldSnapshot]:
    sem = asyncio.Semaphore(concurrency)

    async def _one(slug: str, client: httpx.AsyncClient) -> ManifoldSnapshot | None:
        async with sem:
            return await fetch_market(slug, client=client)

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*(_one(s, client) for s in slugs))

    return [r for r in results if r is not None]
