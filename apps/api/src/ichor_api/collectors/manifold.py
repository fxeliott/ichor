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


# Phase 1 : search terms instead of hardcoded slugs (slugs rotate as
# markets resolve — discovery via /search-markets is more robust).
# Each term harvests up to `top_k` matching open markets.
DISCOVERY_TERMS: tuple[str, ...] = (
    "fed rate",
    "recession",
    "inflation",
    "ecb",
    "boj",
    "election",
    "us cpi",
    "nonfarm payrolls",
    "china pmi",
    "geopolitics",
)

# Legacy slug list — kept for back-compat with anyone calling poll_all
# with explicit slugs. Empty by default ; new behavior uses discovery.
WATCHED_SLUGS: tuple[str, ...] = ()


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


async def search_markets(
    term: str,
    *,
    client: httpx.AsyncClient,
    top_k: int = 5,
    timeout: float = 15.0,
) -> list[ManifoldSnapshot]:
    """Discover live markets matching `term` via /search-markets.

    Replaces hardcoded slug lookup which was rotting as markets
    resolved. Returns only un-closed markets so we don't waste
    DB rows on stale slugs.
    """
    try:
        r = await client.get(
            f"{MANIFOLD_API_BASE}/search-markets",
            params={"term": term, "limit": str(max(1, top_k * 2))},
            timeout=timeout,
            headers={"User-Agent": "IchorManifoldCollector/0.2"},
        )
        r.raise_for_status()
        items = r.json()
    except httpx.HTTPError as e:
        log.warning("manifold.search_failed", term=term, error=str(e))
        return []

    fetched = datetime.now(timezone.utc)
    out: list[ManifoldSnapshot] = []
    for m in items if isinstance(items, list) else []:
        try:
            if m.get("isResolved", False) or m.get("closed", False):
                continue
            out.append(
                ManifoldSnapshot(
                    slug=str(m.get("slug", ""))[:128],
                    market_id=str(m.get("id", "")),
                    question=str(m.get("question", ""))[:512],
                    probability=(
                        float(m["probability"]) if "probability" in m and m["probability"] is not None else None
                    ),
                    volume=float(m["volume"]) if "volume" in m else None,
                    closed=False,
                    creator_username=m.get("creatorUsername"),
                    fetched_at=fetched,
                )
            )
            if len(out) >= top_k:
                break
        except (TypeError, ValueError, KeyError) as e:
            log.warning("manifold.search_parse_failed", term=term, error=str(e))
            continue
    return out


async def poll_all(
    slugs: tuple[str, ...] = WATCHED_SLUGS,
    *,
    concurrency: int = 4,
    discovery_terms: tuple[str, ...] = DISCOVERY_TERMS,
) -> list[ManifoldSnapshot]:
    """Discovery-first polling : harvests markets via /search-markets.

    If `slugs` is provided (back-compat), it falls back to the old
    one-slug-at-a-time path. Otherwise iterates `discovery_terms` and
    de-duplicates by slug.
    """
    async with httpx.AsyncClient() as client:
        if slugs:
            sem = asyncio.Semaphore(concurrency)

            async def _one(slug: str) -> ManifoldSnapshot | None:
                async with sem:
                    return await fetch_market(slug, client=client)

            slug_results = await asyncio.gather(*(_one(s) for s in slugs))
            slug_out = [r for r in slug_results if r is not None]
            if slug_out:
                return slug_out

        # Discovery path
        sem2 = asyncio.Semaphore(concurrency)

        async def _term(t: str) -> list[ManifoldSnapshot]:
            async with sem2:
                return await search_markets(t, client=client, top_k=5)

        batches = await asyncio.gather(*(_term(t) for t in discovery_terms))

    seen: set[str] = set()
    flat: list[ManifoldSnapshot] = []
    for batch in batches:
        for snap in batch:
            if snap.slug in seen:
                continue
            seen.add(snap.slug)
            flat.append(snap)
    return flat
