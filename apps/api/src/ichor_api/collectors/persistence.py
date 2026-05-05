"""Persistence helpers for the no-API-key collectors.

Both helpers are idempotent on the (source, guid_hash) and (slug, fetched_at)
natural keys: re-running the same collector poll never duplicates rows.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from datetime import date as date_type

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    CbSpeech,
    CotPosition,
    FredObservation,
    GdeltEvent,
    GprObservation,
    KalshiMarket,
    ManifoldMarket,
    MarketDataBar,
    NewsItem,
    PolygonIntradayBar,
    PolymarketSnapshot,
)
from .ai_gpr import AiGprObservation
from .central_bank_speeches import CentralBankSpeech
from .cot import CotPosition as CotPositionData
from .fred import FredObservation as FredObservationData
from .gdelt import GdeltArticle
from .kalshi import KalshiMarketSnapshot
from .manifold import ManifoldSnapshot
from .market_data import MarketDataPoint
from .polygon import PolygonBar
from .polymarket import PolymarketSnapshot as PolymarketSnapshotData
from .rss import NewsItem as NewsItemData

log = structlog.get_logger(__name__)


async def persist_news_items(session: AsyncSession, items: Iterable[NewsItemData]) -> int:
    """Insert RSS news items, skipping ones already stored for the same source.

    De-dup is on `(source, guid_hash)`: a given headline is stored at most once
    even if the cron polls every minute. Returns the number of NEW rows
    inserted.
    """
    items = list(items)
    if not items:
        return 0

    # Look up existing (source, guid_hash) tuples in one query
    sources = {it.source for it in items}
    hashes = {it.guid_hash for it in items}
    existing_rows = (
        await session.execute(
            select(NewsItem.source, NewsItem.guid_hash).where(
                NewsItem.source.in_(sources), NewsItem.guid_hash.in_(hashes)
            )
        )
    ).all()
    existing: set[tuple[str, str]] = {(r[0], r[1]) for r in existing_rows}

    now = datetime.now(UTC)
    inserted = 0
    for it in items:
        if (it.source, it.guid_hash) in existing:
            continue
        session.add(
            NewsItem(
                fetched_at=it.fetched_at,
                created_at=now,
                source=it.source,
                source_kind=it.source_kind,
                title=it.title[:512],
                summary=it.summary or None,
                url=it.url[:1024],
                published_at=it.published_at,
                guid_hash=it.guid_hash,
                raw_categories=list(it.raw_categories) or None,
            )
        )
        inserted += 1

    if inserted:
        await session.commit()
    log.info("rss.persisted", total=len(items), inserted=inserted, skipped=len(items) - inserted)
    return inserted


async def persist_polymarket_snapshots(
    session: AsyncSession, snapshots: Sequence[PolymarketSnapshotData]
) -> int:
    """Always inserts every snapshot — historical view is the goal.

    No de-dup — even if two polls happen in the same second, both rows are
    kept (composite PK is `(uuid, fetched_at)` so they never collide).
    Returns total inserted.
    """
    if not snapshots:
        return 0

    now = datetime.now(UTC)
    for s in snapshots:
        session.add(
            PolymarketSnapshot(
                fetched_at=s.fetched_at,
                created_at=now,
                slug=s.slug[:128],
                market_id=s.market_id[:128],
                question=s.question[:512],
                closed=s.closed,
                outcomes=list(s.outcomes),
                last_prices=list(s.last_prices),
                volume_usd=s.volume_usd,
            )
        )

    await session.commit()
    log.info("polymarket.persisted", count=len(snapshots))
    return len(snapshots)


async def persist_market_data(session: AsyncSession, bars: Iterable[MarketDataPoint]) -> int:
    """Insert daily OHLCV bars, skipping ones already stored for the same
    (asset, bar_date, source) tuple.

    Commits per-asset so a single bad asset (e.g. OHLC constraint trip,
    encoding) cannot rollback the rest of the batch.
    """
    bars = list(bars)
    if not bars:
        return 0

    by_asset: dict[str, list[MarketDataPoint]] = {}
    for b in bars:
        by_asset.setdefault(b.asset, []).append(b)

    now = datetime.now(UTC)
    total_inserted = 0
    total_skipped = 0

    for asset, asset_bars in by_asset.items():
        dates = {b.bar_date for b in asset_bars}
        sources = {b.source for b in asset_bars}
        existing_rows = (
            await session.execute(
                select(MarketDataBar.bar_date, MarketDataBar.source).where(
                    MarketDataBar.asset == asset,
                    MarketDataBar.bar_date.in_(dates),
                    MarketDataBar.source.in_(sources),
                )
            )
        ).all()
        existing: set[tuple[object, str]] = {(r[0], r[1]) for r in existing_rows}

        new_rows = 0
        for b in asset_bars:
            if (b.bar_date, b.source) in existing:
                total_skipped += 1
                continue
            session.add(
                MarketDataBar(
                    bar_date=b.bar_date,
                    created_at=now,
                    asset=b.asset,
                    source=b.source,
                    open=b.open,
                    high=b.high,
                    low=b.low,
                    close=b.close,
                    volume=b.volume,
                    fetched_at=b.fetched_at,
                )
            )
            new_rows += 1

        if new_rows:
            try:
                await session.commit()
                total_inserted += new_rows
            except Exception as e:
                await session.rollback()
                log.error(
                    "market_data.persist_asset_failed",
                    asset=asset,
                    rows=new_rows,
                    error=str(e),
                )

    log.info(
        "market_data.persisted",
        total=len(bars),
        inserted=total_inserted,
        skipped=total_skipped,
    )
    return total_inserted


async def persist_fred_observations(
    session: AsyncSession, obs: Iterable[FredObservationData]
) -> int:
    """Insert FRED observations, skipping (series_id, observation_date)
    pairs already in the table.

    The collector emits dataclasses with `observation_date: str` (ISO
    "YYYY-MM-DD") — we parse to date here for the DB column.
    """
    obs = list(obs)
    if not obs:
        return 0

    # Build the (series_id, parsed_date) set we'll need to check for dupes
    parsed: list[tuple[FredObservationData, date_type]] = []
    series_ids: set[str] = set()
    dates: set[date_type] = set()
    for o in obs:
        try:
            d = date_type.fromisoformat(o.observation_date)
        except (TypeError, ValueError):
            log.warning("fred.skip_bad_date", series=o.series_id, date=o.observation_date)
            continue
        parsed.append((o, d))
        series_ids.add(o.series_id)
        dates.add(d)

    if not parsed:
        return 0

    existing_rows = (
        await session.execute(
            select(FredObservation.series_id, FredObservation.observation_date).where(
                FredObservation.series_id.in_(series_ids),
                FredObservation.observation_date.in_(dates),
            )
        )
    ).all()
    existing: set[tuple[str, date_type]] = {(r[0], r[1]) for r in existing_rows}

    now = datetime.now(UTC)
    inserted = 0
    for o, d in parsed:
        if (o.series_id, d) in existing:
            continue
        session.add(
            FredObservation(
                observation_date=d,
                created_at=now,
                series_id=o.series_id,
                value=o.value,
                fetched_at=o.fetched_at,
            )
        )
        inserted += 1

    if inserted:
        await session.commit()
    log.info(
        "fred.persisted",
        total=len(obs),
        inserted=inserted,
        skipped=len(obs) - inserted,
    )
    return inserted


async def persist_polygon_bars(session: AsyncSession, bars: Iterable[PolygonBar]) -> int:
    """Insert 1-min Polygon bars, skipping existing (asset, bar_ts) pairs.

    Commits per-asset to keep the failure blast-radius small (a single
    asset that violates an OHLC envelope check shouldn't roll back the
    whole 8-asset poll).
    """
    bars = list(bars)
    if not bars:
        return 0

    by_asset: dict[str, list[PolygonBar]] = {}
    for b in bars:
        by_asset.setdefault(b.asset, []).append(b)

    now = datetime.now(UTC)
    total_inserted = 0
    total_skipped = 0

    for asset, asset_bars in by_asset.items():
        ts_set = {b.bar_ts for b in asset_bars}
        existing_rows = (
            await session.execute(
                select(PolygonIntradayBar.bar_ts).where(
                    PolygonIntradayBar.asset == asset,
                    PolygonIntradayBar.bar_ts.in_(ts_set),
                )
            )
        ).all()
        existing: set = {r[0] for r in existing_rows}

        new_rows = 0
        for b in asset_bars:
            if b.bar_ts in existing:
                total_skipped += 1
                continue
            session.add(
                PolygonIntradayBar(
                    bar_ts=b.bar_ts,
                    created_at=now,
                    asset=b.asset,
                    ticker=b.ticker,
                    open=b.open,
                    high=b.high,
                    low=b.low,
                    close=b.close,
                    volume=b.volume,
                    vwap=b.vwap,
                    transactions=b.transactions,
                    fetched_at=now,
                )
            )
            new_rows += 1

        if new_rows:
            try:
                await session.commit()
                total_inserted += new_rows
            except Exception as e:
                await session.rollback()
                log.error(
                    "polygon_intraday.persist_asset_failed",
                    asset=asset,
                    rows=new_rows,
                    error=str(e),
                )

    log.info(
        "polygon_intraday.persisted",
        total=len(bars),
        inserted=total_inserted,
        skipped=total_skipped,
    )
    return total_inserted


async def persist_gdelt_articles(session: AsyncSession, articles: Iterable[GdeltArticle]) -> int:
    """Insert GDELT articles, skipping (url, query_label, seendate) dupes."""
    articles = list(articles)
    if not articles:
        return 0
    urls = {a.url for a in articles}
    existing_rows = (
        await session.execute(
            select(GdeltEvent.url, GdeltEvent.query_label, GdeltEvent.seendate).where(
                GdeltEvent.url.in_(urls)
            )
        )
    ).all()
    existing: set[tuple[str, str, datetime]] = {(r[0], r[1], r[2]) for r in existing_rows}
    now = datetime.now(UTC)
    inserted = 0
    for a in articles:
        if (a.url, a.query_label, a.seendate) in existing:
            continue
        session.add(
            GdeltEvent(
                seendate=a.seendate,
                created_at=now,
                query_label=a.query_label[:64],
                url=a.url[:1024],
                title=a.title[:512],
                domain=(a.domain or None) and a.domain[:128],
                language=(a.language or None) and a.language[:32],
                sourcecountry=(a.sourcecountry or None) and a.sourcecountry[:32],
                tone=a.tone,
                image_url=(a.image_url or None) and a.image_url[:1024],
                fetched_at=a.fetched_at,
            )
        )
        inserted += 1
    if inserted:
        await session.commit()
    log.info("gdelt.persisted", total=len(articles), inserted=inserted)
    return inserted


async def persist_gpr_observations(session: AsyncSession, obs: Iterable[AiGprObservation]) -> int:
    """Insert AI-GPR daily observations, skipping existing dates."""
    obs = list(obs)
    if not obs:
        return 0
    dates = {o.observation_date for o in obs}
    existing_rows = (
        await session.execute(
            select(GprObservation.observation_date).where(
                GprObservation.observation_date.in_(dates)
            )
        )
    ).all()
    existing: set[date_type] = {r[0] for r in existing_rows}
    now = datetime.now(UTC)
    inserted = 0
    for o in obs:
        if o.observation_date in existing:
            continue
        session.add(
            GprObservation(
                observation_date=o.observation_date,
                created_at=now,
                ai_gpr=o.ai_gpr,
                fetched_at=o.fetched_at,
            )
        )
        inserted += 1
    if inserted:
        await session.commit()
    log.info("gpr.persisted", total=len(obs), inserted=inserted)
    return inserted


async def persist_cot_positions(
    session: AsyncSession,
    positions: Iterable[CotPositionData | None],
) -> int:
    """Insert COT weekly positions, skipping (market_code, report_date) dupes."""
    positions = [p for p in positions if p is not None]
    if not positions:
        return 0
    codes = {p.market_code for p in positions}
    dates = {p.report_date for p in positions}
    existing_rows = (
        await session.execute(
            select(CotPosition.market_code, CotPosition.report_date).where(
                CotPosition.market_code.in_(codes),
                CotPosition.report_date.in_(dates),
            )
        )
    ).all()
    existing: set[tuple[str, date_type]] = {(r[0], r[1]) for r in existing_rows}
    now = datetime.now(UTC)
    inserted = 0
    for p in positions:
        if (p.market_code, p.report_date) in existing:
            continue
        session.add(
            CotPosition(
                report_date=p.report_date,
                created_at=now,
                market_code=p.market_code[:16],
                market_name=(p.market_name or None) and p.market_name[:128],
                producer_net=p.producer_net,
                swap_dealer_net=p.swap_dealer_net,
                managed_money_net=p.managed_money_net,
                other_reportable_net=p.other_reportable_net,
                non_reportable_net=p.non_reportable_net,
                open_interest=p.open_interest,
                fetched_at=p.fetched_at or now,
            )
        )
        inserted += 1
    if inserted:
        await session.commit()
    log.info("cot.persisted", total=len(positions), inserted=inserted)
    return inserted


async def persist_cb_speeches(session: AsyncSession, speeches: Iterable[CentralBankSpeech]) -> int:
    """Insert central-bank speeches, skipping URLs already known."""
    speeches = list(speeches)
    if not speeches:
        return 0
    urls = {s.url for s in speeches}
    existing_rows = (
        await session.execute(select(CbSpeech.url).where(CbSpeech.url.in_(urls)))
    ).all()
    existing: set[str] = {r[0] for r in existing_rows}
    now = datetime.now(UTC)
    inserted = 0
    for s in speeches:
        if s.url in existing:
            continue
        session.add(
            CbSpeech(
                published_at=s.published_at,
                created_at=now,
                central_bank=s.central_bank[:32],
                speaker=(s.speaker or None) and s.speaker[:128],
                title=s.title[:512],
                summary=s.summary or None,
                url=s.url[:1024],
                source_feed=s.central_bank[:64],
                fetched_at=s.fetched_at,
            )
        )
        inserted += 1
    if inserted:
        await session.commit()
    log.info("cb_speeches.persisted", total=len(speeches), inserted=inserted)
    return inserted


async def persist_kalshi_snapshots(
    session: AsyncSession, snaps: Iterable[KalshiMarketSnapshot]
) -> int:
    """Always insert (composite PK protects ; historical view is the goal)."""
    snaps = list(snaps)
    if not snaps:
        return 0
    now = datetime.now(UTC)
    for s in snaps:
        session.add(
            KalshiMarket(
                fetched_at=s.fetched_at,
                created_at=now,
                ticker=s.ticker[:128],
                title=s.title[:512],
                yes_price=s.yes_price,
                no_price=s.no_price,
                volume_24h=s.volume_24h,
                open_interest=s.open_interest,
                expiration_time=s.expiration_time,
                status=(s.status or None) and s.status[:32],
            )
        )
    await session.commit()
    log.info("kalshi.persisted", count=len(snaps))
    return len(snaps)


async def persist_manifold_snapshots(
    session: AsyncSession, snaps: Iterable[ManifoldSnapshot]
) -> int:
    """Always insert ; composite PK + slug history."""
    snaps = list(snaps)
    if not snaps:
        return 0
    now = datetime.now(UTC)
    for s in snaps:
        session.add(
            ManifoldMarket(
                fetched_at=s.fetched_at,
                created_at=now,
                slug=s.slug[:128],
                market_id=s.market_id[:128],
                question=s.question[:512],
                probability=s.probability,
                volume=s.volume,
                closed=s.closed,
                creator_username=(s.creator_username or None) and s.creator_username[:128],
            )
        )
    await session.commit()
    log.info("manifold.persisted", count=len(snaps))
    return len(snaps)
