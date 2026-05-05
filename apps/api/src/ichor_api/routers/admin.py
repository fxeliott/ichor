"""GET /v1/admin/status — operational status snapshot.

Live counts of every Phase-1 collector table + recent session cards
stats + claude-runner reachability check. Powers /admin page.

This route is intentionally read-only and zero-cost (no expensive
joins, just COUNT(*) per table — TimescaleDB hypertables make these
near-instant).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import get_session
from ..models import (
    CbSpeech,
    CotPosition,
    EconomicEvent,
    FredObservation,
    FxTick,
    GdeltEvent,
    GprObservation,
    KalshiMarket,
    ManifoldMarket,
    NewsItem,
    PolygonIntradayBar,
    PolymarketSnapshot,
    PostMortem,
    SessionCardAudit,
)

router = APIRouter(prefix="/v1/admin", tags=["admin"])


class TableCount(BaseModel):
    table: str
    rows: int
    most_recent_at: datetime | None


class CardStat(BaseModel):
    asset: str
    n_total: int
    n_approved: int
    n_amendments: int
    n_blocked: int
    avg_duration_ms: int
    avg_conviction_pct: float
    last_at: datetime | None


class StatusOut(BaseModel):
    generated_at: datetime
    tables: list[TableCount]
    cards: list[CardStat]
    n_cards_24h: int
    n_cards_total: int
    last_card_at: datetime | None
    claude_runner_url: str | None


async def _table_count(
    session: AsyncSession,
    name: str,
    model: type,
    timestamp_col: str,
) -> TableCount:
    n = (await session.execute(select(func.count()).select_from(model))).scalar_one()
    last = (
        await session.execute(
            select(getattr(model, timestamp_col))
            .order_by(desc(getattr(model, timestamp_col)))
            .limit(1)
        )
    ).scalar_one_or_none()
    return TableCount(table=name, rows=int(n), most_recent_at=last)


@router.get("/status", response_model=StatusOut)
async def status(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StatusOut:
    """Operational health snapshot — table counts + card stats."""
    settings = get_settings()

    tables = [
        await _table_count(session, "polygon_intraday", PolygonIntradayBar, "bar_ts"),
        await _table_count(session, "news_items", NewsItem, "published_at"),
        await _table_count(session, "cb_speeches", CbSpeech, "published_at"),
        await _table_count(session, "polymarket_snapshots", PolymarketSnapshot, "fetched_at"),
        await _table_count(session, "gdelt_events", GdeltEvent, "seendate"),
        await _table_count(session, "gpr_observations", GprObservation, "observation_date"),
        await _table_count(session, "manifold_markets", ManifoldMarket, "fetched_at"),
        await _table_count(session, "fred_observations", FredObservation, "observation_date"),
        await _table_count(session, "kalshi_markets", KalshiMarket, "fetched_at"),
        await _table_count(session, "cot_positions", CotPosition, "report_date"),
        await _table_count(session, "session_card_audit", SessionCardAudit, "generated_at"),
        # Phase 2 additions
        await _table_count(session, "economic_events", EconomicEvent, "fetched_at"),
        await _table_count(session, "post_mortems", PostMortem, "generated_at"),
        await _table_count(session, "fx_ticks", FxTick, "ts"),
    ]

    # Card stats per asset
    cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)
    n_cards_24h = (
        await session.execute(
            select(func.count())
            .select_from(SessionCardAudit)
            .where(SessionCardAudit.generated_at >= cutoff_24h)
        )
    ).scalar_one()
    n_cards_total = (
        await session.execute(select(func.count()).select_from(SessionCardAudit))
    ).scalar_one()

    last_card_at = (
        await session.execute(
            select(SessionCardAudit.generated_at)
            .order_by(desc(SessionCardAudit.generated_at))
            .limit(1)
        )
    ).scalar_one_or_none()

    # Per-asset card breakdown
    rows = (
        await session.execute(
            select(
                SessionCardAudit.asset,
                func.count().label("n_total"),
                func.sum(
                    case(
                        (SessionCardAudit.critic_verdict == "approved", 1),
                        else_=0,
                    )
                ).label("n_approved"),
                func.sum(
                    case(
                        (SessionCardAudit.critic_verdict == "amendments", 1),
                        else_=0,
                    )
                ).label("n_amendments"),
                func.sum(
                    case(
                        (SessionCardAudit.critic_verdict == "blocked", 1),
                        else_=0,
                    )
                ).label("n_blocked"),
                func.avg(SessionCardAudit.claude_duration_ms).label("avg_dur"),
                func.avg(SessionCardAudit.conviction_pct).label("avg_conv"),
                func.max(SessionCardAudit.generated_at).label("last_at"),
            ).group_by(SessionCardAudit.asset)
        )
    ).all()

    cards = sorted(
        [
            CardStat(
                asset=str(r.asset),
                n_total=int(r.n_total or 0),
                n_approved=int(r.n_approved or 0),
                n_amendments=int(r.n_amendments or 0),
                n_blocked=int(r.n_blocked or 0),
                avg_duration_ms=int(r.avg_dur or 0),
                avg_conviction_pct=round(float(r.avg_conv or 0), 2),
                last_at=r.last_at,
            )
            for r in rows
        ],
        key=lambda c: c.n_total,
        reverse=True,
    )

    return StatusOut(
        generated_at=datetime.now(timezone.utc),
        tables=tables,
        cards=cards,
        n_cards_24h=int(n_cards_24h or 0),
        n_cards_total=int(n_cards_total or 0),
        last_card_at=last_card_at,
        claude_runner_url=settings.claude_runner_url or None,
    )
