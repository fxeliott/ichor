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

from ichor_agents.predictions.consensus import ConsensusEstimate, compute_consensus
from ichor_agents.predictions.divergence import (
    DivergenceAlert,
    PredictionMarket,
    detect_divergences,
    match_across_venues,
)
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import KalshiMarket, ManifoldMarket, PolymarketSnapshot

# Fail-closed flag gating the deterministic event-key matcher layer. Read once
# at the live assembly point (``data_pool.build_data_pool``) via
# ``feature_flags.is_enabled``: absent in the DB → False → the matcher runs
# Jaccard-only, byte-identical to the pre-event-key behavior. Flipped on only
# after a prod witness confirms the matched/consensus sets improve.
EVENT_KEY_MATCHER_FLAG = "prediction_event_key_matcher_enabled"


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
    use_event_key: bool = False,
) -> list[dict[str, Any]]:
    """Run a full cross-venue divergence scan.

    Returns alerts sorted by gap descending. Empty list if no divergence
    above gap_threshold. ``use_event_key`` (default off → Jaccard-only,
    byte-identical) is read from the fail-closed feature flag once at the live
    assembly point and threaded down.
    """
    since = datetime.now(UTC) - timedelta(hours=since_hours)
    poly = await _latest_polymarket(session, since)
    kal = await _latest_kalshi(session, since)
    man = await _latest_manifold(session, since)

    matched = match_across_venues(
        poly, kal, man, threshold=match_threshold, use_event_key=use_event_key
    )
    alerts = detect_divergences(matched, gap_threshold=gap_threshold)
    return [_alert_to_dict(a) for a in alerts[:limit]]


async def render_divergence_block(
    session: AsyncSession,
    *,
    since_hours: int = 6,
    gap_threshold: float = 0.05,
    top: int = 5,
    use_event_key: bool = False,
) -> tuple[str, list[str]]:
    """Markdown block for the data_pool `divergence` section.

    Returns (markdown, source_ids).
    """
    alerts = await scan_divergences(
        session,
        since_hours=since_hours,
        gap_threshold=gap_threshold,
        limit=top,
        use_event_key=use_event_key,
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


# ─────────────────────── Cross-venue consensus ─────────────────────────
# Companion to divergence: divergence shows the *spread*, consensus fuses
# the venues into one reliability-weighted probability per matched event
# (real-money Polymarket/Kalshi carry it, play-money Manifold discounted).
# S03 Chantier D — "structuration propre pour les moteurs d'analyse".


def _consensus_to_dict(c: ConsensusEstimate) -> dict[str, Any]:
    return {
        "question": c.representative_question,
        "consensus_prob": round(c.consensus_prob, 4),
        "n_venues": c.n_venues,
        "dispersion": round(c.dispersion, 4),
        "confidence": c.confidence,
        "by_venue": {v: round(p, 4) for v, p in c.by_venue.items()},
        "market_ids": dict(c.market_ids),
    }


async def scan_consensus(
    session: AsyncSession,
    *,
    since_hours: int = 24,
    match_threshold: float = 0.55,
    min_venues: int = 2,
    limit: int = 25,
    use_event_key: bool = False,
) -> list[dict[str, Any]]:
    """Run a full cross-venue consensus scan.

    One reliability-weighted probability per macro event matched across
    venues. Empty list if no event has >= ``min_venues`` priced venues.
    Sorted by confidence (high→low) then dispersion ascending. ``use_event_key``
    (default off → Jaccard-only, byte-identical) is read from the fail-closed
    feature flag once at the live assembly point and threaded down.
    """
    since = datetime.now(UTC) - timedelta(hours=since_hours)
    poly = await _latest_polymarket(session, since)
    kal = await _latest_kalshi(session, since)
    man = await _latest_manifold(session, since)

    matched = match_across_venues(
        poly, kal, man, threshold=match_threshold, use_event_key=use_event_key
    )
    estimates = compute_consensus(matched, min_venues=min_venues)
    return [_consensus_to_dict(c) for c in estimates[:limit]]


async def render_consensus_block(
    session: AsyncSession,
    *,
    since_hours: int = 24,
    top: int = 6,
    use_event_key: bool = False,
) -> tuple[str, list[str]]:
    """Markdown block for the data_pool ``prediction_consensus`` section.

    Returns (markdown, source_ids). Honest-absence prose when no event
    matched across >= 2 venues. ADR-017 — descriptive macro prior only,
    never a trade signal.

    The 24h window (vs the divergence block's 6h) reflects that
    prediction-market probabilities move on the timescale of hours-to-days
    and that cross-venue *matches* are sparse in any 6h slice — a daily NY
    card wants the last day of prediction-market state, not the last 6h
    (witnessed 2026-06-19 on prod: 6h → 0 matches, 24h → matches surface).
    """
    estimates = await scan_consensus(
        session, since_hours=since_hours, limit=top, use_event_key=use_event_key
    )
    title = "## Cross-venue consensus (Polymarket / Kalshi / Manifold — reliability-weighted)"
    if not estimates:
        return (
            f"{title}\n- (no event matched across ≥ 2 venues in the last {since_hours}h)",
            [],
        )
    lines = [title]
    sources: list[str] = []
    for e in estimates:
        # Tag Manifold as play-money so a discordant Manifold price is
        # transparently explained (it carries 0.15 weight and is excluded
        # from the real-money spread that drives confidence).
        venue_str = ", ".join(
            f"{v} {p * 100:.0f}%" + (" (play)" if v == "manifold" else "")
            for v, p in e["by_venue"].items()
        )
        lines.append(
            f"- **{e['question'][:80]}** → consensus {e['consensus_prob'] * 100:.0f}% "
            f"[{e['confidence']}, {e['n_venues']} venues, spread "
            f"{e['dispersion'] * 100:.0f}pp] ({venue_str})"
        )
        for v, mid in e["market_ids"].items():
            sources.append(f"{v}:{mid}")
    return "\n".join(lines), sources
