"""Kalshi collector — US-regulated prediction market.

Kalshi exposes a public read REST endpoint for market metadata + last
trade prices. No auth required for public market data.

Docs : https://trading-api.readme.io/

Phase 1 use case : track US-specific events that complement Polymarket
(Fed rate cuts, US elections, NFP outcomes, recession declared, etc.).
Kalshi sometimes prices events that Polymarket doesn't or vice versa —
divergence is informative.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import structlog

log = structlog.get_logger(__name__)

KALSHI_API_BASE = "https://api.elections.kalshi.com/trade-api/v2"


# Legacy hardcoded event tickers — left empty by default ; the new
# discovery path queries /markets?status=open with category filters.
# Override via the `event_tickers=...` kwarg of poll_all() if needed.
WATCHED_TICKERS: tuple[str, ...] = ()

# Categories Kalshi exposes — we keep the macro-relevant ones.
DISCOVERY_CATEGORIES: tuple[str, ...] = (
    "Economics",
    "Politics",
    "World",
)


@dataclass
class KalshiMarketSnapshot:
    """One snapshot of one Kalshi market."""

    ticker: str
    title: str
    yes_price: float | None
    """Last trade YES price in cents (0-100), normalized to 0-1 here."""
    no_price: float | None
    volume_24h: int | None
    open_interest: int | None
    expiration_time: datetime | None
    status: str
    fetched_at: datetime


def _cents_to_prob(cents: float | None) -> float | None:
    if cents is None:
        return None
    try:
        return float(cents) / 100.0
    except (TypeError, ValueError):
        return None


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


async def fetch_event(
    event_ticker: str, *, client: httpx.AsyncClient, timeout: float = 15.0
) -> list[KalshiMarketSnapshot]:
    """Fetch all markets in an event. Kalshi events contain 1-N markets."""
    try:
        r = await client.get(
            f"{KALSHI_API_BASE}/events/{event_ticker}",
            params={"with_nested_markets": "true"},
            timeout=timeout,
            headers={"User-Agent": "IchorKalshiCollector/0.1"},
        )
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPError as e:
        log.warning("kalshi.fetch_failed", ticker=event_ticker, error=str(e))
        return []

    fetched = datetime.now(UTC)
    markets = data.get("markets") or data.get("event", {}).get("markets") or []
    out: list[KalshiMarketSnapshot] = []
    for m in markets:
        try:
            out.append(
                KalshiMarketSnapshot(
                    ticker=m.get("ticker", "")[:128],
                    title=m.get("title", "")[:512],
                    yes_price=_cents_to_prob(m.get("yes_bid") or m.get("last_price")),
                    no_price=_cents_to_prob(m.get("no_bid")),
                    volume_24h=m.get("volume_24h"),
                    open_interest=m.get("open_interest"),
                    expiration_time=_parse_iso(m.get("expiration_time")),
                    status=m.get("status", "")[:32],
                    fetched_at=fetched,
                )
            )
        except (TypeError, ValueError, KeyError) as e:
            log.warning("kalshi.parse_market_failed", ticker=event_ticker, error=str(e))
            continue
    return out


async def discover_markets(
    *,
    client: httpx.AsyncClient,
    top_k: int = 50,
    timeout: float = 20.0,
) -> list[KalshiMarketSnapshot]:
    """Pull recent open markets via /markets endpoint, no auth needed.

    Replaces hardcoded ticker list which was 100% 404 (events resolved
    or renamed). Filters to status=open and trims to top_k by volume.
    """
    try:
        r = await client.get(
            f"{KALSHI_API_BASE}/markets",
            params={"status": "open", "limit": str(min(1000, top_k * 4))},
            timeout=timeout,
            headers={"User-Agent": "IchorKalshiCollector/0.2"},
        )
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPError as e:
        log.warning("kalshi.discover_failed", error=str(e))
        return []

    fetched = datetime.now(UTC)
    markets = data.get("markets") or []
    out: list[KalshiMarketSnapshot] = []
    for m in markets:
        try:
            out.append(
                KalshiMarketSnapshot(
                    ticker=str(m.get("ticker", ""))[:128],
                    title=str(m.get("title", ""))[:512],
                    yes_price=_cents_to_prob(m.get("yes_bid") or m.get("last_price")),
                    no_price=_cents_to_prob(m.get("no_bid")),
                    volume_24h=m.get("volume_24h"),
                    open_interest=m.get("open_interest"),
                    expiration_time=_parse_iso(m.get("expiration_time")),
                    status=str(m.get("status", ""))[:32],
                    fetched_at=fetched,
                )
            )
        except (TypeError, ValueError, KeyError) as e:
            log.warning("kalshi.discover_parse_failed", error=str(e))
            continue
    # Sort by volume_24h desc, top_k
    out.sort(key=lambda x: x.volume_24h or 0, reverse=True)
    return out[:top_k]


async def poll_all(
    event_tickers: tuple[str, ...] = WATCHED_TICKERS,
    *,
    concurrency: int = 3,
    top_k_discovery: int = 30,
) -> list[KalshiMarketSnapshot]:
    """Discovery-first polling : if no event tickers provided, hit
    /markets?status=open and harvest the top-volume markets.
    """
    async with httpx.AsyncClient() as client:
        if event_tickers:
            sem = asyncio.Semaphore(concurrency)

            async def _one(t: str) -> list[KalshiMarketSnapshot]:
                async with sem:
                    return await fetch_event(t, client=client)

            results = await asyncio.gather(*(_one(t) for t in event_tickers))
            flat = [m for batch in results for m in batch]
            if flat:
                return flat
        # Discovery fallback / default
        return await discover_markets(client=client, top_k=top_k_discovery)
