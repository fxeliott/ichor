"""Kalshi collector — US-regulated prediction market.

Kalshi exposes a public read REST endpoint for market metadata + prices.
No auth required for public market data.

Docs : https://docs.kalshi.com/ (Trade API v2)

Phase 1 use case : track US macro events that complement Polymarket
(Fed rate decisions, CPI, unemployment, recession, GDP, etc.). Kalshi is
real-money + CFTC-regulated, so its prices are a high-quality cross-venue
anchor for the divergence + consensus layers.

2026-06 schema migration (verified live)
----------------------------------------
Kalshi moved its price/size fields to ``*_dollars`` (already in [0,1],
NOT cents) and ``*_fp`` (volume / open interest). The legacy ``yes_bid``
/ ``last_price`` / ``volume`` keys are gone from the response → the old
parser silently read ``None`` for every market (128k rows persisted with
``yes_price=None``). We now read the new fields first, falling back to the
legacy cents fields for resilience.

Macro targeting
---------------
``/markets?status=open`` sorted by volume is ~100 % sports parlays
(``KXMVESPORTSMULTIGAME``, multi-outcome, no single YES price) — useless
for macro. We instead pull explicit macro ``series_ticker``s (verified
live to carry priced binary markets: KXFED, KXCPIYOY, KXU3, KXWRECSS…).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)

KALSHI_API_BASE = "https://api.elections.kalshi.com/trade-api/v2"


# Legacy hardcoded event tickers — left empty by default ; the discovery
# path queries macro series. Override via the `event_tickers=...` kwarg.
WATCHED_TICKERS: tuple[str, ...] = ()

# Macro-relevant Kalshi series tickers (verified live 2026-06-19). These
# carry priced binary markets directly relevant to the 6 tracked assets
# (FX majors + XAU + indices) via monetary-policy / inflation / labor /
# growth surprises. Series with no open markets resolve to an empty pull
# (harmless). Replaces the sports-dominated `/markets?status=open` scan.
MACRO_SERIES: tuple[str, ...] = (
    # Monetary policy (Fed) — top impact on EUR/USD, indices, XAU
    "KXFED",
    "KXDOTPLOT",
    "KXFTAPER",
    "FEDRATEMIN",
    "RATEHIKE",
    # Inflation
    "KXCPIYOY",
    "CPICORE",
    "LCPIMAX",
    # Labor market
    "KXU3",
    "KXUE",
    "KXJOBLESS",
    "U3MIN",
    # Growth / recession
    "KXWRECSS",
    "GDPUSMIN",
    "KXNGDPQ",
)


@dataclass
class KalshiMarketSnapshot:
    """One snapshot of one Kalshi market."""

    ticker: str
    title: str
    yes_price: float | None
    """YES probability in [0, 1] (mid-of-book preferred, last-trade fallback)."""
    no_price: float | None
    volume_24h: int | None
    open_interest: int | None
    expiration_time: datetime | None
    status: str
    fetched_at: datetime


def _cents_to_prob(cents: float | None) -> float | None:
    """Legacy (pre-2026) cents→prob. Kept for the field fallback + tests."""
    if cents is None:
        return None
    try:
        return float(cents) / 100.0
    except (TypeError, ValueError):
        return None


def _dollars_to_prob(v: object) -> float | None:
    """Parse a Kalshi ``*_dollars`` price (already in [0,1], e.g. "0.2500")
    to a probability. None / unparseable / out-of-range → None."""
    if v is None:
        return None
    try:
        p = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return p if 0.0 <= p <= 1.0 else None


def _fp_to_int(v: object) -> int | None:
    """Parse a Kalshi ``*_fp`` numeric (e.g. volume "9371.26") to int."""
    if v is None:
        return None
    try:
        return round(float(v))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _yes_price(m: dict[str, Any]) -> float | None:
    """Best YES-probability estimate for a market.

    Mid-of-book (``yes_bid_dollars``/``yes_ask_dollars``) is the
    conventional fair-value proxy; last trade is a fallback for one-sided
    books; legacy cents fields are the final fallback. All in [0, 1]."""
    bid = _dollars_to_prob(m.get("yes_bid_dollars"))
    ask = _dollars_to_prob(m.get("yes_ask_dollars"))
    if bid is not None and ask is not None:
        return (bid + ask) / 2.0
    last = _dollars_to_prob(m.get("last_price_dollars"))
    if last is not None:
        return last
    if bid is not None:
        return bid
    if ask is not None:
        return ask
    # Legacy (pre-2026) cents schema fallback
    legacy = m.get("yes_bid") if m.get("yes_bid") is not None else m.get("last_price")
    return _cents_to_prob(legacy)


def _parse_market(m: dict[str, Any], fetched: datetime) -> KalshiMarketSnapshot | None:
    """Parse one Kalshi market dict (list- or event-endpoint shape) into a
    snapshot. Returns None on a malformed row."""
    try:
        return KalshiMarketSnapshot(
            ticker=str(m.get("ticker", ""))[:128],
            # `title`/`expiration_time` are the fields Kalshi currently serves but
            # are marked deprecated in the v2 OpenAPI; keep them PRIMARY (zero
            # behavior change today) with the modern replacements as fallback so
            # the parse survives the field's eventual removal instead of silently
            # emitting empty titles / NULL expirations (resilience, no flag).
            title=str(m.get("title") or m.get("yes_sub_title") or "")[:512],
            yes_price=_yes_price(m),
            no_price=_dollars_to_prob(m.get("no_bid_dollars")),
            volume_24h=_fp_to_int(m.get("volume_24h_fp") or m.get("volume_fp"))
            if m.get("volume_24h_fp") is not None or m.get("volume_fp") is not None
            else m.get("volume_24h"),
            open_interest=_fp_to_int(m.get("open_interest_fp"))
            if m.get("open_interest_fp") is not None
            else m.get("open_interest"),
            expiration_time=_parse_iso(m.get("expiration_time") or m.get("latest_expiration_time")),
            status=str(m.get("status", ""))[:32],
            fetched_at=fetched,
        )
    except (TypeError, ValueError, KeyError) as e:
        log.warning("kalshi.parse_market_failed", ticker=m.get("ticker"), error=str(e))
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
            headers={"User-Agent": "IchorKalshiCollector/0.3"},
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
        snap = _parse_market(m, fetched)
        if snap is not None:
            out.append(snap)
    return out


async def _fetch_series_markets(
    series_ticker: str, *, client: httpx.AsyncClient, timeout: float, limit: int
) -> list[KalshiMarketSnapshot]:
    """Pull open markets for one macro series via `/markets?series_ticker=`."""
    try:
        r = await client.get(
            f"{KALSHI_API_BASE}/markets",
            params={
                "series_ticker": series_ticker,
                "status": "open",
                "limit": str(min(1000, limit)),
            },
            timeout=timeout,
            headers={"User-Agent": "IchorKalshiCollector/0.3"},
        )
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPError as e:
        log.warning("kalshi.series_fetch_failed", series=series_ticker, error=str(e))
        return []

    fetched = datetime.now(UTC)
    out: list[KalshiMarketSnapshot] = []
    for m in data.get("markets") or []:
        snap = _parse_market(m, fetched)
        if snap is not None:
            out.append(snap)
    return out


async def discover_markets(
    *,
    client: httpx.AsyncClient,
    top_k: int = 50,
    timeout: float = 20.0,
    series: tuple[str, ...] = MACRO_SERIES,
    concurrency: int = 3,
) -> list[KalshiMarketSnapshot]:
    """Pull open markets from the curated macro series (no auth needed).

    Replaces the previous `/markets?status=open` scan, which returned
    ~100 % sports parlays (multi-outcome, no YES price) — verified live
    2026-06-19. We query each macro `series_ticker` and keep the markets
    that carry a YES price, ranked by 24h volume.
    """
    sem = asyncio.Semaphore(concurrency)

    async def _one(s: str) -> list[KalshiMarketSnapshot]:
        async with sem:
            return await _fetch_series_markets(
                s, client=client, timeout=timeout, limit=max(50, top_k)
            )

    batches = await asyncio.gather(*(_one(s) for s in series))
    flat = [m for batch in batches for m in batch]
    # Keep only priced markets (a macro market with no YES price is noise
    # to the divergence/consensus layers) and rank by 24h volume.
    priced = [m for m in flat if m.yes_price is not None]
    priced.sort(key=lambda x: x.volume_24h or 0, reverse=True)
    return priced[:top_k]


async def poll_all(
    event_tickers: tuple[str, ...] = WATCHED_TICKERS,
    *,
    concurrency: int = 3,
    top_k_discovery: int = 30,
) -> list[KalshiMarketSnapshot]:
    """Discovery-first polling : if no event tickers provided, harvest the
    curated macro series. Explicit `event_tickers` (if set) take priority.
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
        return await discover_markets(client=client, top_k=top_k_discovery, concurrency=concurrency)
