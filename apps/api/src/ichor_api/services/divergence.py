"""Cross-venue prediction-market divergence — service layer.

Wires `packages/agents/.../predictions/divergence.py` (pure stdlib
matching + detection) into Postgres. Loads the latest snapshot per
market across Polymarket / Kalshi / Manifold, runs the matcher, returns
divergence alerts as plain dicts (router-safe).

Phase 2 fix for SPEC.md §2.2 #8 (divergence cross-venue codée mais aucun
consommateur live).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from ichor_agents.predictions.divergence import (
    DivergenceAlert,
    PredictionMarket,
    detect_divergences,
    match_across_venues,
)
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import KalshiMarket, ManifoldMarket, PolymarketSnapshot


async def _latest_polymarket(session: AsyncSession, since: datetime) -> list[PredictionMarket]:
    # Latest row per slug since cutoff. Subquery picks max fetched_at per slug.
    rows = (
        (
            await session.execute(
                select(PolymarketSnapshot)
                .where(PolymarketSnapshot.fetched_at >= since)
                .order_by(PolymarketSnapshot.slug, desc(PolymarketSnapshot.fetched_at))
            )
        )
        .scalars()
        .all()
    )
    seen: set[str] = set()
    out: list[PredictionMarket] = []
    for r in rows:
        if r.slug in seen:
            continue
        seen.add(r.slug)
        # Polymarket binary markets: outcomes[0]="Yes", last_prices[0]=yes price.
        yes_price: float | None = None
        if r.last_prices and len(r.last_prices) > 0:
            try:
                yes_price = float(r.last_prices[0])
            except (TypeError, ValueError):
                yes_price = None
        out.append(
            PredictionMarket(
                venue="polymarket",
                market_id=r.slug,
                question=r.question,
                yes_price=yes_price,
            )
        )
    return out


async def _latest_kalshi(session: AsyncSession, since: datetime) -> list[PredictionMarket]:
    rows = (
        (
            await session.execute(
                select(KalshiMarket)
                .where(KalshiMarket.fetched_at >= since)
                .order_by(KalshiMarket.ticker, desc(KalshiMarket.fetched_at))
            )
        )
        .scalars()
        .all()
    )
    seen: set[str] = set()
    out: list[PredictionMarket] = []
    for r in rows:
        if r.ticker in seen:
            continue
        seen.add(r.ticker)
        out.append(
            PredictionMarket(
                venue="kalshi",
                market_id=r.ticker,
                question=r.title,
                yes_price=float(r.yes_price) if r.yes_price is not None else None,
            )
        )
    return out


async def _latest_manifold(session: AsyncSession, since: datetime) -> list[PredictionMarket]:
    rows = (
        (
            await session.execute(
                select(ManifoldMarket)
                .where(ManifoldMarket.fetched_at >= since)
                .order_by(ManifoldMarket.slug, desc(ManifoldMarket.fetched_at))
            )
        )
        .scalars()
        .all()
    )
    seen: set[str] = set()
    out: list[PredictionMarket] = []
    for r in rows:
        if r.slug in seen:
            continue
        seen.add(r.slug)
        out.append(
            PredictionMarket(
                venue="manifold",
                market_id=r.slug,
                question=r.question,
                yes_price=float(r.probability) if r.probability is not None else None,
            )
        )
    return out


def _alert_to_dict(a: DivergenceAlert) -> dict[str, Any]:
    return {
        "question": a.representative_question,
        "gap": round(a.gap, 4),
        "high_venue": a.high[0],
        "high_price": round(a.high[1], 4),
        "low_venue": a.low[0],
        "low_price": round(a.low[1], 4),
        "by_venue": {
            v: {
                "market_id": p.market_id,
                "yes_price": p.yes_price,
                "question": p.question,
            }
            for v, p in a.matched.by_venue.items()
        },
        "similarity": round(a.matched.similarity, 3),
    }


async def scan_divergences(
    session: AsyncSession,
    *,
    since_hours: int = 6,
    match_threshold: float = 0.55,
    gap_threshold: float = 0.05,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Run a full cross-venue divergence scan.

    Returns alerts sorted by gap descending. Empty list if no divergence
    above gap_threshold.
    """
    since = datetime.now(UTC) - timedelta(hours=since_hours)
    poly = await _latest_polymarket(session, since)
    kal = await _latest_kalshi(session, since)
    man = await _latest_manifold(session, since)

    matched = match_across_venues(poly, kal, man, threshold=match_threshold)
    alerts = detect_divergences(matched, gap_threshold=gap_threshold)
    return [_alert_to_dict(a) for a in alerts[:limit]]


async def render_divergence_block(
    session: AsyncSession,
    *,
    since_hours: int = 6,
    gap_threshold: float = 0.05,
    top: int = 5,
) -> tuple[str, list[str]]:
    """Markdown block for the data_pool `divergence` section.

    Returns (markdown, source_ids).
    """
    alerts = await scan_divergences(
        session,
        since_hours=since_hours,
        gap_threshold=gap_threshold,
        limit=top,
    )
    if not alerts:
        return (
            "## Cross-venue divergence (Polymarket / Kalshi / Manifold)\n"
            "- (no divergence above threshold in the last "
            f"{since_hours}h)",
            [],
        )
    lines = [f"## Cross-venue divergence (top {len(alerts)}, gap ≥ {int(gap_threshold * 100)}pp)"]
    sources: list[str] = []
    for a in alerts:
        lines.append(
            f"- **{a['question'][:80]}** — gap {a['gap'] * 100:.1f}pp "
            f"({a['high_venue']} {a['high_price'] * 100:.0f}% vs "
            f"{a['low_venue']} {a['low_price'] * 100:.0f}%)"
        )
        for v in a["by_venue"]:
            sources.append(f"{v}:{a['by_venue'][v]['market_id']}")
    return "\n".join(lines), sources
