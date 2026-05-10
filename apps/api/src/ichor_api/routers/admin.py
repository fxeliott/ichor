"""GET /v1/admin/status — operational status snapshot.

Live counts of every Phase-1 collector table + recent session cards
stats + claude-runner reachability check. Powers /admin page.

This route is intentionally read-only and zero-cost (no expensive
joins, just COUNT(*) per table — TimescaleDB hypertables make these
near-instant).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
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
    cutoff_24h = datetime.now(UTC) - timedelta(hours=24)
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
        generated_at=datetime.now(UTC),
        tables=tables,
        cards=cards,
        n_cards_24h=int(n_cards_24h or 0),
        n_cards_total=int(n_cards_total or 0),
        last_card_at=last_card_at,
        claude_runner_url=settings.claude_runner_url or None,
    )


# ── Pipeline health snapshot (Sprint 17) ────────────────────────────


class PipelineHealth(BaseModel):
    pipeline: str
    """Symbolic name : 'fred', 'vpin_fx', 'binance_funding', etc."""

    series_count: int
    """Distinct series_id rows currently observed."""

    last_observation_at: datetime | None
    minutes_since_last: int | None
    """Stale = > 1500min (25h) for daily pipelines, > 60min for live."""

    is_stale: bool


class AlertSummary(BaseModel):
    alert_code: str
    severity: str
    count_24h: int
    count_7d: int
    last_triggered_at: datetime


class PipelineHealthOut(BaseModel):
    generated_at: datetime
    pipelines: list[PipelineHealth]
    alerts_24h: list[AlertSummary]
    n_session_cards_7d: int
    n_couche2_outputs_7d: int
    crisis_mode_active: bool
    """True when an unacknowledged CRISIS_MODE_ACTIVE row exists in
    the trailing 60min — same logic as the dashboard banner."""


# series_id pattern → pipeline label + freshness expectation (minutes)
_PIPELINE_PATTERNS: tuple[tuple[str, str, int], ...] = (
    ("VPIN_FX_%", "vpin_fx", 90),  # 30min cron + buffer
    ("BA_SPREAD_%", "bidask_spread", 30),  # 10min cron
    ("VIX_LIVE", "vix_live", 30),  # 5min cron
    ("CRYPTO_FNG", "crypto_fng", 1500),  # daily
    ("BINANCE_FUNDING_%", "binance_funding", 1500),
    ("DEFILLAMA_%", "defillama", 1500),
    ("WIKI_PV_%", "wikipedia_pageviews", 1500),
    ("HAR_RV_%", "har_rv_forecast", 1500),
    ("HMM_REGIME_%", "hmm_regime", 1500),
    ("DTW_DIST_MIN", "dtw_analogue", 1500),
    ("AAII_%", "aaii", 10080),  # weekly
    ("BOE_%", "boe_iadb", 1500),
    ("ECB_%", "ecb_sdmx", 1500),
    ("BLS_%", "bls", 10080),
    ("EIA_%", "eia_petroleum", 1500),
    ("DTS_TGA_CLOSE", "dts_treasury", 1500),
    ("TREASURY_AUC_%", "treasury_auction", 1500),
    ("BRIER_%", "brier_drift", 1500),
)


@router.get("/pipeline-health", response_model=PipelineHealthOut)
async def pipeline_health(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PipelineHealthOut:
    """One-shot snapshot of every running pipeline + alerts + Crisis state.

    Designed as the dashboard's "is the system alive" probe : a single
    GET returns enough to color-code each pipeline pill (live / stale)
    + the recent alerts breakdown + the Crisis Mode banner state.
    """
    from sqlalchemy import text as sa_text

    from ..models import Alert, Couche2Output

    now = datetime.now(UTC)

    # Pipelines
    pipelines: list[PipelineHealth] = []
    for like_pattern, label, stale_min in _PIPELINE_PATTERNS:
        sql = sa_text(
            "SELECT count(distinct series_id) AS n, max(fetched_at) AS last "
            "FROM fred_observations WHERE series_id LIKE :pat"
        )
        row = (await session.execute(sql, {"pat": like_pattern})).first()
        n = int(row[0] or 0) if row else 0
        last = row[1] if row else None
        mins = None
        if isinstance(last, datetime):
            mins = max(0, int((now - last).total_seconds() / 60))
        pipelines.append(
            PipelineHealth(
                pipeline=label,
                series_count=n,
                last_observation_at=last if isinstance(last, datetime) else None,
                minutes_since_last=mins,
                is_stale=(mins is None) if n == 0 else (mins > stale_min),
            )
        )

    # Alerts breakdown — last 7d, grouped by code
    alerts_stmt = sa_text(
        """
        SELECT alert_code, severity,
               count(*) FILTER (WHERE triggered_at >= :h24) AS c24,
               count(*) AS c7,
               max(triggered_at) AS last_at
        FROM alerts
        WHERE triggered_at >= :h7d
        GROUP BY alert_code, severity
        ORDER BY c24 DESC, c7 DESC
        LIMIT 30
        """
    )
    alert_rows = (
        await session.execute(
            alerts_stmt, {"h24": now - timedelta(hours=24), "h7d": now - timedelta(days=7)}
        )
    ).all()
    alerts_24h = [
        AlertSummary(
            alert_code=str(r[0]),
            severity=str(r[1]),
            count_24h=int(r[2] or 0),
            count_7d=int(r[3] or 0),
            last_triggered_at=r[4],
        )
        for r in alert_rows
    ]

    # Session cards / Couche-2 outputs counts
    n_cards_7d = (
        await session.execute(
            select(func.count())
            .select_from(SessionCardAudit)
            .where(SessionCardAudit.generated_at >= now - timedelta(days=7))
        )
    ).scalar_one()
    n_couche2_7d = (
        await session.execute(
            select(func.count())
            .select_from(Couche2Output)
            .where(Couche2Output.ran_at >= now - timedelta(days=7))
        )
    ).scalar_one()

    # Crisis Mode active : unacknowledged CRISIS_MODE_ACTIVE in last 60min
    crisis_stmt = (
        select(func.count())
        .select_from(Alert)
        .where(
            Alert.alert_code == "CRISIS_MODE_ACTIVE",
            Alert.acknowledged_at.is_(None),
            Alert.triggered_at >= now - timedelta(minutes=60),
        )
    )
    crisis_active = bool((await session.execute(crisis_stmt)).scalar_one() or 0)

    return PipelineHealthOut(
        generated_at=now,
        pipelines=pipelines,
        alerts_24h=alerts_24h,
        n_session_cards_7d=int(n_cards_7d or 0),
        n_couche2_outputs_7d=int(n_couche2_7d or 0),
        crisis_mode_active=crisis_active,
    )
