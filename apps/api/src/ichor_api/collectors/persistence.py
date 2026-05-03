"""Persistence helpers for the no-API-key collectors.

Both helpers are idempotent on the (source, guid_hash) and (slug, fetched_at)
natural keys: re-running the same collector poll never duplicates rows.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Sequence

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import MarketDataBar, NewsItem, PolymarketSnapshot
from .market_data import MarketDataPoint
from .polymarket import PolymarketSnapshot as PolymarketSnapshotData
from .rss import NewsItem as NewsItemData

log = structlog.get_logger(__name__)


async def persist_news_items(
    session: AsyncSession, items: Iterable[NewsItemData]
) -> int:
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

    now = datetime.now(timezone.utc)
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

    now = datetime.now(timezone.utc)
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


async def persist_market_data(
    session: AsyncSession, bars: Iterable[MarketDataPoint]
) -> int:
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

    now = datetime.now(timezone.utc)
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
