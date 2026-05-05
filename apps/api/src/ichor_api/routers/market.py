"""GET /v1/market — read market_data hypertable for the dashboard."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import MarketDataBar, PolygonIntradayBar

router = APIRouter(prefix="/v1/market", tags=["market"])


class MarketBarOut(BaseModel):
    bar_date: date
    asset: str
    source: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None


@router.get("/{asset}", response_model=list[MarketBarOut])
async def asset_history(
    asset: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    days: int = Query(180, ge=1, le=3650),
    source: str | None = Query(None, regex=r"^[a-z_]{2,32}$"),
) -> list[MarketBarOut]:
    """Daily OHLCV history for one asset, oldest-first."""
    cutoff = (datetime.now(UTC) - timedelta(days=days)).date()
    stmt = (
        select(MarketDataBar)
        .where(
            MarketDataBar.asset == asset,
            MarketDataBar.bar_date >= cutoff,
        )
        .order_by(MarketDataBar.bar_date)
    )
    if source:
        stmt = stmt.where(MarketDataBar.source == source)
    rows = (await session.execute(stmt)).scalars().all()
    # Dedup per bar_date (multi-source may exist)
    seen: set[date] = set()
    out: list[MarketBarOut] = []
    for r in rows:
        if r.bar_date in seen:
            continue
        seen.add(r.bar_date)
        out.append(
            MarketBarOut(
                bar_date=r.bar_date,
                asset=r.asset,
                source=r.source,
                open=float(r.open),
                high=float(r.high),
                low=float(r.low),
                close=float(r.close),
                volume=float(r.volume) if r.volume is not None else None,
            )
        )
    return out


# ─────────────────────────── Intraday (Polygon) ────────────────────────


class IntradayBarOut(BaseModel):
    """One Polygon 1-min bar shaped for lightweight-charts.

    `time` is epoch seconds (UTC) — matches the chart lib's expected
    UTCTimestamp shape so the front-end can call setData() directly.
    """

    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float | None


@router.get("/intraday/{asset}", response_model=list[IntradayBarOut])
async def intraday_history(
    asset: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    hours: int = Query(8, ge=1, le=72),
    limit: int = Query(2000, ge=10, le=10000),
) -> list[IntradayBarOut]:
    """Polygon 1-min OHLCV bars over a recent window (oldest-first).

    Powers the `<LiveChartCard>` in the dashboard. Time-axis uses
    epoch seconds for direct ingest by lightweight-charts.
    """
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    stmt = (
        select(PolygonIntradayBar)
        .where(
            PolygonIntradayBar.asset == asset.upper(),
            PolygonIntradayBar.bar_ts >= cutoff,
        )
        .order_by(PolygonIntradayBar.bar_ts)
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        IntradayBarOut(
            time=int(r.bar_ts.timestamp()),
            open=float(r.open),
            high=float(r.high),
            low=float(r.low),
            close=float(r.close),
            volume=float(r.volume) if r.volume is not None else None,
        )
        for r in rows
    ]
