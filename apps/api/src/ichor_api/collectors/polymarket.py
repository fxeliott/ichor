"""Polymarket public collector — pulls market prices for finance-relevant
prediction markets, no API key required.

Polymarket exposes two surfaces:

  - REST gamma-api.polymarket.com  → market metadata, last prices, volumes.
    Public, no auth, generous rate limit.
  - WSS clob.polymarket.com/ws     → live book updates for a given asset_id.
    Public read.

For Phase 0 we only need polled snapshots: every 5 min, fetch the markets we
care about (Fed rate decisions, recession odds, ECB cuts, etc.), persist last
prices into TimescaleDB. The WS subscription is a Phase 1 enhancement when
we want sub-second alerting on breakout odds moves.

Markets of interest live in `WATCHED_SLUGS` — slug-based selection so we
don't have to maintain UUIDs. The collector resolves slug → market_id at
fetch time.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
import structlog

log = structlog.get_logger(__name__)

GAMMA_BASE = "https://gamma-api.polymarket.com"

# Slugs are stable URL fragments, easy to maintain.
WATCHED_SLUGS: tuple[str, ...] = (
    # Fed
    "fed-decision-in-march-2026",
    "fed-decision-in-may-2026",
    "fed-decision-in-june-2026",
    # Recession
    "us-recession-in-2026",
    # ECB
    "will-the-ecb-cut-rates-at-its-next-meeting",
    # Geopolitics with macro impact
    "russia-x-ukraine-ceasefire-by-june-30-2026",
)


@dataclass
class PolymarketSnapshot:
    """Snapshot of a binary market's outcome prices at one point in time."""

    slug: str
    question: str
    market_id: str
    closed: bool
    outcomes: list[str]
    last_prices: list[float]  # parallel to outcomes; in [0, 1]
    volume_usd: float | None
    fetched_at: datetime

    @property
    def yes_price(self) -> float | None:
        """Convention: outcomes[0] is "Yes" for binary markets."""
        if not self.last_prices:
            return None
        return self.last_prices[0]


def _parse_market(slug: str, payload: dict) -> PolymarketSnapshot | None:
    """Best-effort normalize a /markets/{slug} response.

    Polymarket schema fields evolve; we keep this parser defensive so a
    schema change downgrades cleanly to logging instead of crashing the
    collector.
    """
    try:
        market_id = str(payload.get("id") or payload.get("conditionId") or slug)
        question = (payload.get("question") or payload.get("title") or "").strip()
        closed = bool(payload.get("closed", False))
        # Outcomes can be a JSON-encoded array string OR a real list
        outcomes_raw = payload.get("outcomes") or payload.get("outcomeNames") or []
        if isinstance(outcomes_raw, str):
            import json

            outcomes = json.loads(outcomes_raw)
        else:
            outcomes = list(outcomes_raw)
        prices_raw = payload.get("outcomePrices") or payload.get("lastTradePrices") or []
        if isinstance(prices_raw, str):
            import json

            prices = [float(p) for p in json.loads(prices_raw)]
        else:
            prices = [float(p) for p in prices_raw]
        if not outcomes or not prices or len(outcomes) != len(prices):
            log.warning("polymarket.shape_unexpected", slug=slug)
            return None
        volume = (
            float(payload["volume"])
            if isinstance(payload.get("volume"), (int, float, str))
            else None
        )
    except (ValueError, KeyError, TypeError) as e:
        log.warning("polymarket.parse_failed", slug=slug, error=str(e))
        return None

    return PolymarketSnapshot(
        slug=slug,
        question=question,
        market_id=market_id,
        closed=closed,
        outcomes=outcomes,
        last_prices=prices,
        volume_usd=volume,
        fetched_at=datetime.now(timezone.utc),
    )


async def fetch_market(
    slug: str,
    *,
    client: httpx.AsyncClient,
    timeout: float = 15.0,
) -> PolymarketSnapshot | None:
    """Fetch a single market by slug. None on any error (already logged)."""
    try:
        # Polymarket's gamma API exposes /markets?slug=<slug>
        r = await client.get(
            f"{GAMMA_BASE}/markets",
            params={"slug": slug},
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPError as e:
        log.warning("polymarket.fetch_failed", slug=slug, error=str(e))
        return None

    # API returns either a single dict or a list — normalize.
    if isinstance(data, list):
        if not data:
            return None
        market = data[0]
    elif isinstance(data, dict):
        market = data
    else:
        return None

    return _parse_market(slug, market)


async def poll_all(
    slugs: tuple[str, ...] = WATCHED_SLUGS,
    *,
    concurrency: int = 4,
) -> list[PolymarketSnapshot]:
    """Poll every slug in parallel; bounded by concurrency."""
    sem = asyncio.Semaphore(concurrency)

    async def _one(slug: str, client: httpx.AsyncClient) -> PolymarketSnapshot | None:
        async with sem:
            return await fetch_market(slug, client=client)

    async with httpx.AsyncClient(http2=True) as client:
        results = await asyncio.gather(*(_one(s, client) for s in slugs))

    return [r for r in results if r is not None]
