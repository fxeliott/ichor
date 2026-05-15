"""Polymarket decision key levels — ADR-083 D3 phase 5 (r58).

Final phase of ADR-083 D3 contract delivery. Binary prediction markets
on Polymarket act as crowd-aggregated probability signals for macro
events (Fed decisions, elections, BTC price thresholds, recession
odds, government shutdown, geopolitical outcomes).

The "decision imminent" KeyLevel fires when a high-conviction (price
near 0 or 1) macro market is approaching resolution — these are the
binary thresholds ADR-083 D3 wanted to surface as decision-driven
macro switches.

Source : `polymarket_snapshots` table populated by polymarket cron
every 5 min (ADR-066, captured every 5min from Polymarket Gamma API).
148 757+ rows accumulated since collector inception.

Doctrine :
- Filter to MACRO-relevant markets (keyword whitelist on slug/question)
  — exclude sport noise (ATP/NBA/soccer) which is the bulk of volume
- Exclude closed markets
- Take top-N by volume_usd (N=3 strict per anti-accumulation discipline)
- Fire KeyLevel when extreme price (>0.85 or <0.15) :
  - >0.85 = strong YES conviction (95%+ market consensus)
  - <0.15 = strong NO conviction
- Mid-range (0.15-0.85) = no signal (market uncertain, not actionable
  as decision-imminent threshold)

Pass 2 should weigh polymarket KeyLevels as crowd-aggregated event
probability anchors, NOT as primary directional signals (markets can
be wrong + post-resolution correlations are weak). Useful as cross-
check vs other macro signals.

Reference : Wolfers-Zitzewitz 2004 (prediction market accuracy bands),
ADR-066 polymarket collector, ADR-085 Pass-6 scenario taxonomy.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .types import KeyLevel

# Macro relevance : whitelist on slug or question substrings.
# Lowercase compare. Order doesn't matter, list extensible.
_MACRO_SLUG_KEYWORDS = (
    "bitcoin",
    "btc",
    "ethereum",
    "eth",
    "fed",
    "fomc",
    "rate-cut",
    "rate-hike",
    "rate-decision",
    "recession",
    "election",
    "trump",
    "biden",
    "harris",
    "vance",
    "shutdown",
    "debt-ceiling",
    "war",
    "ceasefire",
    "ukraine",
    "russia",
    "china",
    "tariff",
    "inflation",
    "cpi",
    "unemployment",
    "gdp",
    "putin",
    "powell",
)

# Extreme price thresholds (decision-imminent doctrine).
POLYMARKET_STRONG_YES_THRESHOLD = 0.85
POLYMARKET_STRONG_NO_THRESHOLD = 0.15

# Anti-accumulation : strict top-N rendered.
POLYMARKET_TOP_N = 3

# Recency filter : only markets snapshotted within last 48h
# (Polymarket cron is every 5 min so anything older = collector issue).
POLYMARKET_MAX_STALENESS_HOURS = 48

# Volume filter : skip low-volume markets (< $50k = noise).
POLYMARKET_MIN_VOLUME_USD = 50_000.0


def _is_macro_relevant(slug: str, question: str) -> bool:
    """True if slug or question contains any macro keyword."""
    s = (slug + " " + question).lower()
    return any(kw in s for kw in _MACRO_SLUG_KEYWORDS)


async def compute_polymarket_decision_levels(session: AsyncSession) -> list[KeyLevel]:
    """Compute KeyLevels for top macro Polymarket markets in extreme zones.

    Returns 0 to POLYMARKET_TOP_N KeyLevels (strict). Only fires when
    market is :
      - macro-relevant (keyword filter)
      - NOT closed
      - recently snapshotted (within MAX_STALENESS_HOURS)
      - volume_usd >= MIN_VOLUME_USD
      - in extreme price zone (>STRONG_YES OR <STRONG_NO)

    Sorted by volume_usd DESC, capped at TOP_N.
    """
    cutoff = datetime.now(UTC) - timedelta(hours=POLYMARKET_MAX_STALENESS_HOURS)

    # Latest snapshot per slug, with non-NULL volume + not closed + recent.
    stmt = text(
        """
        SELECT DISTINCT ON (slug)
               slug, question, last_prices, volume_usd, fetched_at
        FROM polymarket_snapshots
        WHERE NOT closed
          AND volume_usd IS NOT NULL
          AND volume_usd >= :min_vol
          AND fetched_at >= :cutoff
        ORDER BY slug, fetched_at DESC
        """
    )
    rows = (
        await session.execute(stmt, {"min_vol": POLYMARKET_MIN_VOLUME_USD, "cutoff": cutoff})
    ).all()

    candidates: list[tuple[float, KeyLevel]] = []
    for slug, question, last_prices, volume_usd, fetched_at in rows:
        if not _is_macro_relevant(slug, question):
            continue
        # last_prices is JSONB list[float] e.g. [0.9995, 0.0005]
        if not isinstance(last_prices, list) or not last_prices:
            continue
        try:
            yes_price = float(last_prices[0])
        except (TypeError, ValueError):
            continue

        if yes_price > POLYMARKET_STRONG_YES_THRESHOLD:
            side = "above_risk_off_below_risk_on"  # generic ; market-specific
            note = (
                f"YES @ {yes_price:.4f} (strong YES, market consensus "
                f'{yes_price * 100:.1f}%) on "{question[:120]}". '
                f"Volume ${volume_usd:,.0f}. Decision-imminent zone "
                "— treat as crowd-aggregated probability anchor."
            )
            level = yes_price
        elif yes_price < POLYMARKET_STRONG_NO_THRESHOLD:
            side = "above_risk_on_below_risk_off"
            no_price = 1.0 - yes_price
            note = (
                f"NO @ {no_price:.4f} (strong NO on YES, market consensus "
                f'{no_price * 100:.1f}% NO) on "{question[:120]}". '
                f"Volume ${volume_usd:,.0f}. Decision-imminent zone."
            )
            level = yes_price
        else:
            continue  # mid-range, not actionable

        kl = KeyLevel(
            asset="USD",  # macro markets are mostly USD-relevant
            level=level,
            kind="polymarket_decision",
            side=side,  # type: ignore[arg-type]
            source=f"polymarket:{slug} {fetched_at:%Y-%m-%d %H:%M}",
            note=note,
        )
        candidates.append((float(volume_usd), kl))

    # Sort by volume DESC, take top N.
    candidates.sort(key=lambda t: t[0], reverse=True)
    return [kl for _, kl in candidates[:POLYMARKET_TOP_N]]
