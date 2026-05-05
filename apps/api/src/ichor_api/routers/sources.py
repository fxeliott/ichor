"""GET /v1/sources — data source catalog with live freshness.

Replaces the hardcoded SOURCES list in `apps/web2/app/sources/page.tsx`.
Catalog metadata (name, category, monthly cost, api-key flag) lives
server-side ; status, last_fetch_at and rows_24h are computed from the
actual collector tables.

Status thresholds per source kind :
  - intraday (FX bars, news ticker)  : live <30 min, stale <4 h, down ≥ 4 h
  - hourly   (RSS, GDELT, polymarket): live <2 h,   stale <12 h, down ≥ 12 h
  - daily    (FRED, COT, AAII, AI-GPR): live <30 h, stale <72 h, down ≥ 72 h
  - weekly   (CFTC report, AAII, FINRA): live <8 d, stale <16 d, down ≥ 16 d
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

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
    MarketDataBar,
    NewsItem,
    PolygonGexSnapshot,
    PolygonIntradayBar,
    PolymarketSnapshot,
)

router = APIRouter(prefix="/v1/sources", tags=["sources"])


Status = Literal["live", "stale", "down"]
Category = Literal[
    "macro", "fx", "options", "sentiment", "geopolitics", "structure"
]
Cadence = Literal["intraday", "hourly", "daily", "weekly"]


_LIVE_BY_CADENCE: dict[Cadence, tuple[timedelta, timedelta]] = {
    # (live_threshold, stale_threshold) ; everything past stale = down
    "intraday": (timedelta(minutes=30), timedelta(hours=4)),
    "hourly": (timedelta(hours=2), timedelta(hours=12)),
    "daily": (timedelta(hours=30), timedelta(hours=72)),
    "weekly": (timedelta(days=8), timedelta(days=16)),
}


def _classify(now: datetime, last: datetime | None, cadence: Cadence) -> Status:
    if last is None:
        return "down"
    age = now - last
    live_t, stale_t = _LIVE_BY_CADENCE[cadence]
    if age <= live_t:
        return "live"
    if age <= stale_t:
        return "stale"
    return "down"


class SourceOut(BaseModel):
    id: str
    name: str
    category: Category
    cadence: Cadence
    status: Status
    last_fetch_at: datetime | None
    rows_24h: int
    cost_per_month: str
    api_key_required: bool


class SourcesListOut(BaseModel):
    generated_at: datetime
    n_sources: int
    n_live: int
    n_stale: int
    n_down: int
    monthly_cost_total_usd: float
    sources: list[SourceOut]


# ── Static catalog : name + category + cost + api-key + cadence ─────────
# `column` is the timestamp column used to compute freshness ; `model`
# is the SQLAlchemy mapped class. Some sources have no DB table yet
# (e.g. yfinance options chains write to flat files) — they are flagged
# `model=None` and reported as cadence-default with last_fetch=None.

_CATALOG: list[dict[str, object]] = [
    {
        "id": "fred",
        "name": "FRED (St. Louis Fed)",
        "category": "macro",
        "cadence": "daily",
        "cost": "$0",
        "api_key": True,
        "model": FredObservation,
        "ts_col": "observation_date",
    },
    {
        "id": "polygon",
        "name": "Massive Currencies (ex-Polygon)",
        "category": "fx",
        "cadence": "intraday",
        "cost": "$49",
        "api_key": True,
        "model": PolygonIntradayBar,
        "ts_col": "bar_ts",
    },
    {
        "id": "polygon_fx_stream",
        "name": "Massive Currencies WebSocket (FX quote ticks)",
        "category": "fx",
        "cadence": "intraday",
        "cost": "incl. above",
        "api_key": True,
        "model": FxTick,
        "ts_col": "ts",
    },
    {
        "id": "polygon_news",
        "name": "Polygon News (ticker-linked)",
        "category": "sentiment",
        "cadence": "intraday",
        "cost": "incl. above",
        "api_key": True,
        "model": NewsItem,
        "ts_col": "fetched_at",
        "filter": ("source", "polygon_news"),
    },
    {
        "id": "stooq",
        "name": "Stooq daily (yfinance fallback)",
        "category": "fx",
        "cadence": "daily",
        "cost": "$0",
        "api_key": False,
        "model": MarketDataBar,
        "ts_col": "bar_date",
    },
    {
        "id": "polymarket",
        "name": "Polymarket",
        "category": "structure",
        "cadence": "hourly",
        "cost": "$0",
        "api_key": False,
        "model": PolymarketSnapshot,
        "ts_col": "fetched_at",
    },
    {
        "id": "kalshi",
        "name": "Kalshi",
        "category": "structure",
        "cadence": "hourly",
        "cost": "$0",
        "api_key": False,
        "model": KalshiMarket,
        "ts_col": "fetched_at",
    },
    {
        "id": "manifold",
        "name": "Manifold",
        "category": "structure",
        "cadence": "hourly",
        "cost": "$0",
        "api_key": False,
        "model": ManifoldMarket,
        "ts_col": "fetched_at",
    },
    {
        "id": "cot",
        "name": "CFTC COT (weekly)",
        "category": "structure",
        "cadence": "weekly",
        "cost": "$0",
        "api_key": False,
        "model": CotPosition,
        "ts_col": "fetched_at",
    },
    {
        "id": "rss",
        "name": "RSS feeds (FT, Reuters, Bloomberg)",
        "category": "sentiment",
        "cadence": "hourly",
        "cost": "$0",
        "api_key": False,
        "model": NewsItem,
        "ts_col": "fetched_at",
        "filter": ("source_kind", "rss"),
    },
    {
        "id": "gdelt",
        "name": "GDELT 2.0 events",
        "category": "geopolitics",
        "cadence": "hourly",
        "cost": "$0",
        "api_key": False,
        "model": GdeltEvent,
        "ts_col": "seendate",
    },
    {
        "id": "ai_gpr",
        "name": "AI-GPR (Caldara & Iacoviello)",
        "category": "geopolitics",
        "cadence": "daily",
        "cost": "$0",
        "api_key": False,
        "model": GprObservation,
        "ts_col": "observation_date",
    },
    {
        "id": "cb_speeches",
        "name": "CB speeches scraper",
        "category": "macro",
        "cadence": "hourly",
        "cost": "$0",
        "api_key": False,
        "model": CbSpeech,
        "ts_col": "published_at",
    },
    {
        "id": "flashalpha",
        "name": "FlashAlpha GEX (free 5/d)",
        "category": "options",
        "cadence": "daily",
        "cost": "$0",
        "api_key": True,
        "model": PolygonGexSnapshot,
        "ts_col": "captured_at",
    },
    {
        "id": "vix_live",
        "name": "VIX live (FRED + CBOE delayed)",
        "category": "macro",
        "cadence": "daily",
        "cost": "$0",
        "api_key": False,
        "model": FredObservation,
        "ts_col": "observation_date",
        "filter": ("series_id", "VIXCLS"),
    },
    {
        "id": "aaii",
        "name": "AAII Sentiment Survey (weekly)",
        "category": "sentiment",
        "cadence": "weekly",
        "cost": "$0",
        "api_key": False,
        "model": FredObservation,
        "ts_col": "observation_date",
        "filter": ("series_id", "AAIIBULL"),
    },
    {
        "id": "bls",
        "name": "BLS public API",
        "category": "macro",
        "cadence": "daily",
        "cost": "$0",
        "api_key": False,
        "model": FredObservation,
        "ts_col": "observation_date",
        "filter": ("series_id", "PAYEMS"),
    },
    {
        "id": "ecb_sdmx",
        "name": "ECB Data Portal SDMX 2.1",
        "category": "macro",
        "cadence": "daily",
        "cost": "$0",
        "api_key": False,
        "model": FredObservation,
        "ts_col": "observation_date",
        "filter": ("series_id", "ECBESTRVOLWGTTRMDMNRT"),
    },
    {
        "id": "dts_treasury",
        "name": "Treasury DTS (FiscalData)",
        "category": "macro",
        "cadence": "daily",
        "cost": "$0",
        "api_key": False,
        "model": FredObservation,
        "ts_col": "observation_date",
        "filter": ("series_id", "WTREGEN"),
    },
    {
        "id": "boe_iadb",
        "name": "BoE IADB (CSV)",
        "category": "macro",
        "cadence": "daily",
        "cost": "$0",
        "api_key": False,
        "model": FredObservation,
        "ts_col": "observation_date",
        "filter": ("series_id", "IUDSOIA"),
    },
    {
        "id": "eia_petroleum",
        "name": "EIA Petroleum (OpenData v2)",
        "category": "macro",
        "cadence": "weekly",
        "cost": "$0",
        "api_key": True,
        "model": FredObservation,
        "ts_col": "observation_date",
        "filter": ("series_id", "WCESTUS1"),
    },
    {
        "id": "finra_short",
        "name": "FINRA short interest",
        "category": "structure",
        "cadence": "weekly",
        "cost": "$0",
        "api_key": False,
        "model": FredObservation,
        "ts_col": "observation_date",
        "filter": ("series_id", "FINRA_SHORT"),
    },
    {
        "id": "yfinance_options",
        "name": "yfinance options chains",
        "category": "options",
        "cadence": "daily",
        "cost": "$0",
        "api_key": False,
        "model": None,
        "ts_col": None,
    },
    {
        "id": "bluesky",
        "name": "Bluesky AT Protocol",
        "category": "sentiment",
        "cadence": "hourly",
        "cost": "$0",
        "api_key": False,
        "model": NewsItem,
        "ts_col": "fetched_at",
        "filter": ("source", "bluesky"),
    },
    {
        "id": "mastodon",
        "name": "Mastodon followed feeds",
        "category": "sentiment",
        "cadence": "hourly",
        "cost": "$0",
        "api_key": False,
        "model": NewsItem,
        "ts_col": "fetched_at",
        "filter": ("source_kind", "mastodon"),
    },
    {
        "id": "reddit",
        "name": "Reddit OAuth (WSB, forex)",
        "category": "sentiment",
        "cadence": "hourly",
        "cost": "$0",
        "api_key": False,
        "model": NewsItem,
        "ts_col": "fetched_at",
        "filter": ("source_kind", "reddit"),
    },
    {
        "id": "forex_factory",
        "name": "ForexFactory calendar XML",
        "category": "macro",
        "cadence": "hourly",
        "cost": "$0",
        "api_key": False,
        "model": EconomicEvent,
        "ts_col": "fetched_at",
        "filter": ("source", "forex_factory"),
    },
]


@router.get("", response_model=SourcesListOut)
async def list_sources(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SourcesListOut:
    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)
    out: list[SourceOut] = []

    for entry in _CATALOG:
        model = entry["model"]
        ts_col_name = entry["ts_col"]
        last_at: datetime | None = None
        rows_24h = 0

        if model is not None and ts_col_name is not None:
            ts_col = getattr(model, ts_col_name)
            base_filter = entry.get("filter")

            last_stmt = select(ts_col).order_by(desc(ts_col)).limit(1)
            count_stmt = (
                select(func.count())
                .select_from(model)
                .where(ts_col >= cutoff_24h)
            )
            if base_filter:
                col_name, value = base_filter
                col = getattr(model, col_name)
                last_stmt = last_stmt.where(col == value)
                count_stmt = count_stmt.where(col == value)

            try:
                last_raw = (await session.execute(last_stmt)).scalar_one_or_none()
                rows_24h = int(
                    (await session.execute(count_stmt)).scalar_one() or 0
                )
            except Exception:
                last_raw = None
                rows_24h = 0

            if last_raw is None:
                last_at = None
            elif isinstance(last_raw, datetime):
                last_at = last_raw
                if last_at.tzinfo is None:
                    last_at = last_at.replace(tzinfo=timezone.utc)
            else:
                # `Date` from FRED.observation_date — promote to UTC midnight
                from datetime import date as _date

                if isinstance(last_raw, _date):
                    last_at = datetime.combine(
                        last_raw, datetime.min.time(), tzinfo=timezone.utc
                    )

        cadence = entry["cadence"]  # type: ignore[assignment]
        status = _classify(now, last_at, cadence)  # type: ignore[arg-type]

        out.append(
            SourceOut(
                id=str(entry["id"]),
                name=str(entry["name"]),
                category=entry["category"],  # type: ignore[arg-type]
                cadence=cadence,  # type: ignore[arg-type]
                status=status,
                last_fetch_at=last_at,
                rows_24h=rows_24h,
                cost_per_month=str(entry["cost"]),
                api_key_required=bool(entry["api_key"]),
            )
        )

    n_live = sum(1 for s in out if s.status == "live")
    n_stale = sum(1 for s in out if s.status == "stale")
    n_down = sum(1 for s in out if s.status == "down")
    monthly_cost = 0.0
    for s in out:
        # Parse "$49" / "$0" / "incl. above" — non-numeric stays at 0
        m = s.cost_per_month.replace("$", "").strip()
        try:
            monthly_cost += float(m.split()[0])
        except (ValueError, IndexError):
            pass

    return SourcesListOut(
        generated_at=now,
        n_sources=len(out),
        n_live=n_live,
        n_stale=n_stale,
        n_down=n_down,
        monthly_cost_total_usd=monthly_cost,
        sources=out,
    )
