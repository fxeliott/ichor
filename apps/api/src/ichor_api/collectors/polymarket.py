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
from datetime import UTC, datetime

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
        fetched_at=datetime.now(UTC),
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
            follow_redirects=True,
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


# ────────────────────────── Top-100 macro discovery ──────────────────────
#
# Wave 31 add — supplément WATCHED_SLUGS with the most-traded macro markets.
# Polymarket's gamma /markets endpoint supports volume sorting + active
# filter. We pull the top N by 24h volume then filter Python-side to keep
# only macro-relevant questions (the platform also has sports + entertainment
# + crypto-only that we don't care about for pre-trade FX/macro research).

# Keywords used to filter top markets to macro/geopolitics scope. Match is
# case-insensitive substring on the `question` text. List intentionally
# permissive — false-positives (e.g. "fed" in "feeds") are rare in practice
# and noise filtered out at data_pool aggregation level.
_MACRO_KEYWORDS: tuple[str, ...] = (
    # Monetary policy
    "fed", "fomc", "rate cut", "rate hike", "basis point",
    "ecb", "european central bank", "boe", "bank of england",
    "boj", "bank of japan", "rba", "boc", "snb",
    # Macro indicators
    "recession", "gdp", "cpi", "inflation", "pce", "ppi",
    "unemployment", "nfp", "payroll", "jobs report", "jobless",
    # FX / commodities
    "dollar", "usd", "euro", "yen", "yuan", "ruble",
    "gold", "oil", "wti", "brent", "opec", "natural gas",
    # Geopolitics
    "russia", "ukraine", "china", "taiwan", "iran", "israel",
    "war", "ceasefire", "sanctions", "tariff",
    # US politics + fiscal
    "trump", "biden", "harris", "election", "congress",
    "debt ceiling", "shutdown", "fiscal",
    # Crypto-macro overlap
    "bitcoin", "ethereum", "btc", "etf approval",
    # Treasury / yields
    "treasury", "yield", "bond", "auction",
)


def _is_macro_question(question: str) -> bool:
    """Return True if the market question matches at least one macro
    keyword. Case-insensitive substring match."""
    if not question:
        return False
    lowered = question.lower()
    return any(kw in lowered for kw in _MACRO_KEYWORDS)


async def fetch_top_macro_markets(
    *,
    client: httpx.AsyncClient,
    limit: int = 200,
    timeout: float = 30.0,
) -> list[PolymarketSnapshot]:
    """Fetch top `limit` markets by 24h volume, filter to macro-only.

    Polymarket gamma /markets supports:
      - active=true       : not yet resolved
      - closed=false      : trading still open
      - order=volume24hr  : sort by 24h volume desc
      - limit / offset    : pagination

    We pull `limit` (default 200) and Python-side filter via _MACRO_KEYWORDS
    to keep the macro / geopolitics subset. Empirically ~30-50 % match the
    macro filter on a healthy day, giving us ~60-100 macro markets.
    """
    try:
        r = await client.get(
            f"{GAMMA_BASE}/markets",
            params={
                "active": "true",
                "closed": "false",
                "order": "volume24hr",
                "ascending": "false",
                "limit": limit,
            },
            timeout=timeout,
            follow_redirects=True,
        )
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPError as e:
        log.warning("polymarket.top_fetch_failed", error=str(e))
        return []

    if not isinstance(data, list):
        log.warning("polymarket.top_unexpected_shape", type=type(data).__name__)
        return []

    out: list[PolymarketSnapshot] = []
    for market in data:
        if not isinstance(market, dict):
            continue
        question = str(market.get("question") or market.get("title") or "")
        if not _is_macro_question(question):
            continue
        # Synthesize slug if absent from payload
        slug = str(market.get("slug") or market.get("id") or "")
        if not slug:
            continue
        snap = _parse_market(slug, market)
        if snap is not None:
            out.append(snap)
    log.info("polymarket.top_macro_filtered", total=len(data), kept=len(out))
    return out


async def poll_all(
    slugs: tuple[str, ...] = WATCHED_SLUGS,
    *,
    concurrency: int = 4,
    include_top_macro: bool = True,
    top_limit: int = 200,
) -> list[PolymarketSnapshot]:
    """Poll WATCHED_SLUGS + top macro markets by 24h volume.

    Two paths combined:
      - WATCHED_SLUGS : the curated FOMC/ECB/recession baseline (always
        polled regardless of volume — these are the priors we want even
        if the market is thin today).
      - Top macro by volume (Wave 31) : the breadth layer — best-traded
        macro/geopolitics markets globally on Polymarket today.

    Dedup is on (slug). When include_top_macro=False, falls back to
    legacy slug-only behaviour (back-compat).
    """
    sem = asyncio.Semaphore(concurrency)

    async def _one(slug: str, client: httpx.AsyncClient) -> PolymarketSnapshot | None:
        async with sem:
            return await fetch_market(slug, client=client)

    async with httpx.AsyncClient() as client:
        slug_results = await asyncio.gather(*(_one(s, client) for s in slugs))
        slug_snaps = [r for r in slug_results if r is not None]

        if not include_top_macro:
            return slug_snaps

        # Append top-macro discovery, dedup on slug.
        seen_slugs = {s.slug for s in slug_snaps}
        top_snaps = await fetch_top_macro_markets(client=client, limit=top_limit)
        for s in top_snaps:
            if s.slug in seen_slugs:
                continue
            seen_slugs.add(s.slug)
            slug_snaps.append(s)

    return slug_snaps
