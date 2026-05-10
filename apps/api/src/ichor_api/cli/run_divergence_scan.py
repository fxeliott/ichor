"""CLI runner for the cross-venue prediction-market divergence scanner.

Wires `ichor_agents.predictions.divergence` into Postgres :
  1. Pulls latest snapshot per market from polymarket_snapshots,
     kalshi_markets, manifold_markets (DISTINCT ON, last 24h).
  2. Drops closed markets and rows without prices.
  3. Runs match_across_venues + detect_divergences.
  4. Persists divergences ≥ gap_threshold as `alerts` rows
     (alert_code = "PRED_MARKET_DIVERGENCE").

Usage:
    python -m ichor_api.cli.run_divergence_scan          # dry-run
    python -m ichor_api.cli.run_divergence_scan --persist

Cron-driven from `scripts/hetzner/register-cron-divergence.sh`
(every 30 min — divergences are stable on the timescale of hours).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import structlog
from ichor_agents.predictions.divergence import (
    DivergenceAlert,
    PredictionMarket,
    detect_divergences,
    match_across_venues,
)
from sqlalchemy import select

from ..db import get_engine, get_sessionmaker
from ..models import Alert, KalshiMarket, ManifoldMarket, PolymarketSnapshot

log = structlog.get_logger(__name__)


# Default thresholds — conservative ; can be overridden via env later.
_MATCH_THRESHOLD = 0.55
_GAP_THRESHOLD = 0.05
_LOOKBACK_HOURS = 24


async def _fetch_polymarket(session: Any, *, hours: int) -> list[PredictionMarket]:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    # SELECT DISTINCT ON (slug) — latest row per market in window
    stmt = (
        select(PolymarketSnapshot)
        .where(
            PolymarketSnapshot.fetched_at >= cutoff,
            PolymarketSnapshot.closed.is_(False),
        )
        .order_by(PolymarketSnapshot.slug, PolymarketSnapshot.fetched_at.desc())
        .distinct(PolymarketSnapshot.slug)
    )
    rows = (await session.execute(stmt)).scalars().all()
    out: list[PredictionMarket] = []
    for r in rows:
        yes = r.last_prices[0] if r.last_prices else None
        if yes is None:
            continue
        out.append(
            PredictionMarket(
                venue="polymarket",
                market_id=r.slug,
                question=r.question,
                yes_price=float(yes),
            )
        )
    return out


async def _fetch_kalshi(session: Any, *, hours: int) -> list[PredictionMarket]:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    stmt = (
        select(KalshiMarket)
        .where(KalshiMarket.fetched_at >= cutoff)
        .order_by(KalshiMarket.ticker, KalshiMarket.fetched_at.desc())
        .distinct(KalshiMarket.ticker)
    )
    rows = (await session.execute(stmt)).scalars().all()
    out: list[PredictionMarket] = []
    for r in rows:
        if r.status and r.status.lower() in ("settled", "expired", "closed"):
            continue
        if r.yes_price is None:
            continue
        out.append(
            PredictionMarket(
                venue="kalshi",
                market_id=r.ticker,
                question=r.title,
                yes_price=float(r.yes_price),
            )
        )
    return out


async def _fetch_manifold(session: Any, *, hours: int) -> list[PredictionMarket]:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    stmt = (
        select(ManifoldMarket)
        .where(
            ManifoldMarket.fetched_at >= cutoff,
            ManifoldMarket.closed.is_(False),
        )
        .order_by(ManifoldMarket.slug, ManifoldMarket.fetched_at.desc())
        .distinct(ManifoldMarket.slug)
    )
    rows = (await session.execute(stmt)).scalars().all()
    out: list[PredictionMarket] = []
    for r in rows:
        if r.probability is None:
            continue
        out.append(
            PredictionMarket(
                venue="manifold",
                market_id=r.slug,
                question=r.question,
                yes_price=float(r.probability),
            )
        )
    return out


def _alert_severity(gap: float) -> str:
    """Map gap size → alert severity."""
    if gap >= 0.20:
        return "critical"
    if gap >= 0.10:
        return "warning"
    return "info"


def _alert_title(div: DivergenceAlert) -> str:
    high_v, high_p = div.high
    low_v, low_p = div.low
    return (
        f"Pred-market divergence: {high_v} {high_p:.0%} vs {low_v} {low_p:.0%} (gap {div.gap:+.0%})"
    )


async def _persist_divergences(session: Any, divs: list[DivergenceAlert]) -> int:
    """Insert each divergence as a fresh `alerts` row.

    De-dup is handled at the alert-rendering layer (UI groups by
    alert_code + question). The composite PK (id) makes inserts safe.
    """
    if not divs:
        return 0
    now = datetime.now(UTC)
    n = 0
    for d in divs:
        title = _alert_title(d)
        payload = {
            "question": d.representative_question,
            "gap": d.gap,
            "high": {"venue": d.high[0], "price": d.high[1]},
            "low": {"venue": d.low[0], "price": d.low[1]},
            "matched": {
                "similarity": d.matched.similarity,
                "venues": list(d.matched.by_venue.keys()),
                "market_ids": {v: m.market_id for v, m in d.matched.by_venue.items()},
            },
        }
        session.add(
            Alert(
                id=uuid4(),
                created_at=now,
                updated_at=now,
                alert_code="PRED_MARKET_DIVERGENCE",
                severity=_alert_severity(d.gap),
                asset=None,
                triggered_at=now,
                metric_name="prediction_market_yes_price_gap",
                metric_value=float(d.gap),
                threshold=float(_GAP_THRESHOLD),
                direction="above",
                source_payload=payload,
                title=title[:256],
                description=d.representative_question[:1000],
            )
        )
        n += 1
    await session.commit()
    return n


async def run_scan(
    *,
    persist: bool,
    hours: int = _LOOKBACK_HOURS,
    match_threshold: float = _MATCH_THRESHOLD,
    gap_threshold: float = _GAP_THRESHOLD,
) -> int:
    """End-to-end scan + optional persist. Returns exit code."""
    sm = get_sessionmaker()
    async with sm() as session:
        poly = await _fetch_polymarket(session, hours=hours)
        kal = await _fetch_kalshi(session, hours=hours)
        man = await _fetch_manifold(session, hours=hours)

    print(
        f"Divergence scan · poly={len(poly)} kalshi={len(kal)} manifold={len(man)} "
        f"(window {hours}h)"
    )

    matched = match_across_venues(poly, kal, man, threshold=match_threshold)
    print(f"  matched cross-venue: {len(matched)}")

    divs = detect_divergences(matched, gap_threshold=gap_threshold)
    print(f"  divergences ≥ {gap_threshold:.0%}: {len(divs)}")

    for d in divs[:10]:
        venues = ",".join(d.matched.by_venue.keys())
        print(
            f"  · gap={d.gap:+.0%} [{venues}] _{d.representative_question[:90]}_ "
            f"(high={d.high[0]} {d.high[1]:.0%}, low={d.low[0]} {d.low[1]:.0%})"
        )

    if persist and divs:
        async with sm() as session:
            n = await _persist_divergences(session, divs)
        print(f"  persisted {n} divergence alerts")

    return 0 if matched else 1


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_divergence_scan")
    parser.add_argument("--persist", action="store_true")
    parser.add_argument("--hours", type=int, default=_LOOKBACK_HOURS)
    parser.add_argument("--match-threshold", type=float, default=_MATCH_THRESHOLD)
    parser.add_argument("--gap-threshold", type=float, default=_GAP_THRESHOLD)
    args = parser.parse_args(argv[1:])

    try:
        return asyncio.run(
            run_scan(
                persist=args.persist,
                hours=args.hours,
                match_threshold=args.match_threshold,
                gap_threshold=args.gap_threshold,
            )
        )
    finally:
        # Dispose engine if we opened persistence connections
        if args.persist:
            asyncio.run(get_engine().dispose())


if __name__ == "__main__":
    sys.exit(main(sys.argv))
