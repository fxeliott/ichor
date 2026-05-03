"""Run collectors on demand — for manual smoke tests AND scheduled cron jobs.

Run:
  python -m ichor_api.cli.run_collectors rss              # dry-run, print only
  python -m ichor_api.cli.run_collectors polymarket
  python -m ichor_api.cli.run_collectors market_data
  python -m ichor_api.cli.run_collectors all
  python -m ichor_api.cli.run_collectors rss --persist    # write to Postgres
  python -m ichor_api.cli.run_collectors all --persist

The dry-run mode is the safe default; --persist must be opt-in. Cron units
should always pass --persist.
"""

from __future__ import annotations

import asyncio
import sys

from datetime import date, timedelta

import httpx

from ..collectors.ai_gpr import fetch_latest as fetch_ai_gpr
from ..collectors.central_bank_speeches import poll_all as poll_cb_speeches
from ..collectors.cot import poll_all_assets as poll_cot
from ..collectors.fred import poll_all as poll_fred
from ..collectors.fred_extended import merged_series as fred_merged_series
from ..collectors.gdelt import poll_all as poll_gdelt
from ..collectors.kalshi import poll_all as poll_kalshi
from ..collectors.manifold import poll_all as poll_manifold
from ..collectors.market_data import poll_all as poll_market_data
from ..collectors.polygon import fetch_aggs, supported_assets as polygon_assets
from ..collectors.polymarket import poll_all as poll_polymarket
from ..collectors.rss import poll_all as poll_rss
from ..config import get_settings
from ..db import get_engine, get_sessionmaker


async def _run_rss(*, persist: bool) -> int:
    items = await poll_rss()
    print(f"RSS  · {len(items)} items pulled")
    for it in items[:5]:
        ts = it.published_at.isoformat(timespec="minutes")
        print(f"  [{it.source:20s}] {ts}  {it.title[:90]}")
    if len(items) > 5:
        print(f"  ... and {len(items) - 5} more")
    if persist:
        from ..collectors.persistence import persist_news_items

        sm = get_sessionmaker()
        async with sm() as session:
            inserted = await persist_news_items(session, items)
        print(f"RSS  · persisted {inserted} new rows ({len(items) - inserted} dedup)")
    return 0 if items else 1


async def _run_polymarket(*, persist: bool) -> int:
    snaps = await poll_polymarket()
    print(f"Polymarket · {len(snaps)} markets pulled")
    for s in snaps:
        yes = f"{s.yes_price:.2f}" if s.yes_price is not None else "n/a"
        vol = f"${s.volume_usd:,.0f}" if s.volume_usd is not None else "n/a"
        print(f"  [{s.slug[:40]:40s}] yes={yes}  vol={vol}  {s.question[:60]}")
    if persist:
        from ..collectors.persistence import persist_polymarket_snapshots

        sm = get_sessionmaker()
        async with sm() as session:
            inserted = await persist_polymarket_snapshots(session, snaps)
        print(f"Polymarket · persisted {inserted} snapshots")
    return 0 if snaps else 1


async def _run_market_data(*, persist: bool) -> int:
    bars_by_asset = await poll_market_data()
    total = sum(len(v) for v in bars_by_asset.values())
    print(f"Market data · {total} bars across {len(bars_by_asset)} assets")
    for asset, bars in bars_by_asset.items():
        if not bars:
            print(f"  [{asset:12s}] (empty)")
            continue
        first = min(b.bar_date for b in bars)
        last = max(b.bar_date for b in bars)
        last_bar = max(bars, key=lambda b: b.bar_date)
        print(
            f"  [{asset:12s}] {len(bars):>5d} bars  {first} → {last}  "
            f"close={last_bar.close:.4f}  src={last_bar.source}"
        )
    if persist:
        from ..collectors.persistence import persist_market_data

        sm = get_sessionmaker()
        async with sm() as session:
            flat = [b for bars in bars_by_asset.values() for b in bars]
            inserted = await persist_market_data(session, flat)
        print(f"Market data · persisted {inserted} new rows")
    return 0 if total else 1


async def _run_fred(*, persist: bool, extended: bool = True) -> int:
    """Pull FRED observations (latest per series) and optionally persist.

    `extended=True` polls the full set defined by `fred.SERIES_TO_POLL`
    + `fred_extended.EXTENDED_SERIES_TO_POLL` deduped (~40 series). The
    macro trinity (DXY broad, US10Y, VIX) and dollar smile inputs
    (DFII10, HY OAS, IG OAS) are guaranteed to land in this set, which
    is what `services/data_pool.py` queries for Pass 1 régime.
    """
    settings = get_settings()
    if not settings.fred_api_key:
        print(
            "FRED · ICHOR_API_FRED_API_KEY is empty — skipping. "
            "Set it in /etc/ichor/api.env to enable.",
            file=sys.stderr,
        )
        return 0

    series = fred_merged_series() if extended else None
    obs = (
        await poll_fred(settings.fred_api_key, series=series)
        if series is not None
        else await poll_fred(settings.fred_api_key)
    )
    print(f"FRED · {len(obs)} series fetched")
    for o in obs[:5]:
        v = f"{o.value:.4f}" if o.value is not None else "n/a"
        print(f"  [{o.series_id:18s}] {o.observation_date} = {v}")
    if len(obs) > 5:
        print(f"  ... and {len(obs) - 5} more")

    if persist:
        from ..collectors.persistence import persist_fred_observations

        sm = get_sessionmaker()
        async with sm() as session:
            inserted = await persist_fred_observations(session, obs)
        print(f"FRED · persisted {inserted} new rows ({len(obs) - inserted} dedup)")
    return 0 if obs else 1


async def _run_gdelt(*, persist: bool) -> int:
    """Pull GDELT 2.0 articles for all configured queries."""
    articles = await poll_gdelt()
    print(f"GDELT · {len(articles)} articles fetched across queries")
    by_query: dict[str, int] = {}
    for a in articles:
        by_query[a.query_label] = by_query.get(a.query_label, 0) + 1
    for label, n in sorted(by_query.items()):
        print(f"  [{label:30s}] {n:>3d} articles")
    if persist:
        from ..collectors.persistence import persist_gdelt_articles
        sm = get_sessionmaker()
        async with sm() as session:
            inserted = await persist_gdelt_articles(session, articles)
        print(f"GDELT · persisted {inserted} new rows ({len(articles) - inserted} dedup)")
    return 0 if articles else 1


async def _run_ai_gpr(*, persist: bool) -> int:
    """Pull the AI-GPR daily series."""
    obs = await fetch_ai_gpr()
    print(f"AI-GPR · {len(obs)} daily observations fetched")
    if obs:
        latest = max(obs, key=lambda o: o.observation_date)
        print(f"  latest: {latest.observation_date} = {latest.ai_gpr:.2f}")
    if persist:
        from ..collectors.persistence import persist_gpr_observations
        sm = get_sessionmaker()
        async with sm() as session:
            inserted = await persist_gpr_observations(session, obs)
        print(f"AI-GPR · persisted {inserted} new rows")
    return 0 if obs else 1


async def _run_cot(*, persist: bool) -> int:
    """Pull weekly CFTC Disaggregated Futures Only for tracked markets."""
    by_code = await poll_cot()
    print(f"COT · {sum(1 for v in by_code.values() if v)} markets resolved")
    for code, pos in by_code.items():
        if pos is None:
            print(f"  [{code:8s}] (not in this week's report)")
            continue
        print(
            f"  [{code:8s}] {pos.report_date} mm_net={pos.managed_money_net:+,} "
            f"oi={pos.open_interest:,}"
        )
    if persist:
        from ..collectors.persistence import persist_cot_positions
        sm = get_sessionmaker()
        async with sm() as session:
            inserted = await persist_cot_positions(session, by_code.values())
        print(f"COT · persisted {inserted} new rows")
    has_any = any(pos is not None for pos in by_code.values())
    return 0 if has_any else 1


async def _run_cb_speeches(*, persist: bool) -> int:
    """Pull central-bank speech feeds (Fed/ECB/BoE/BoJ + BIS aggregator)."""
    speeches = await poll_cb_speeches()
    print(f"CB speeches · {len(speeches)} items pulled")
    for s in speeches[:5]:
        print(
            f"  [{s.central_bank:6s}] {s.published_at:%Y-%m-%d} {s.title[:80]}"
        )
    if len(speeches) > 5:
        print(f"  ... and {len(speeches) - 5} more")
    if persist:
        from ..collectors.persistence import persist_cb_speeches
        sm = get_sessionmaker()
        async with sm() as session:
            inserted = await persist_cb_speeches(session, speeches)
        print(f"CB speeches · persisted {inserted} new rows")
    return 0 if speeches else 1


async def _run_kalshi(*, persist: bool) -> int:
    """Pull Kalshi public REST snapshots."""
    snaps = await poll_kalshi()
    print(f"Kalshi · {len(snaps)} markets pulled")
    for s in snaps[:5]:
        yp = f"{s.yes_price:.2f}" if s.yes_price is not None else "n/a"
        print(f"  [{s.ticker[:30]:30s}] yes={yp}  {s.title[:60]}")
    if len(snaps) > 5:
        print(f"  ... and {len(snaps) - 5} more")
    if persist:
        from ..collectors.persistence import persist_kalshi_snapshots
        sm = get_sessionmaker()
        async with sm() as session:
            inserted = await persist_kalshi_snapshots(session, snaps)
        print(f"Kalshi · persisted {inserted} new rows")
    return 0 if snaps else 1


async def _run_manifold(*, persist: bool) -> int:
    """Pull Manifold REST snapshots."""
    snaps = await poll_manifold()
    print(f"Manifold · {len(snaps)} markets pulled")
    for s in snaps[:5]:
        p = f"{s.probability:.2f}" if s.probability is not None else "n/a"
        print(f"  [{s.slug[:30]:30s}] p={p}  {s.question[:60]}")
    if len(snaps) > 5:
        print(f"  ... and {len(snaps) - 5} more")
    if persist:
        from ..collectors.persistence import persist_manifold_snapshots
        sm = get_sessionmaker()
        async with sm() as session:
            inserted = await persist_manifold_snapshots(session, snaps)
        print(f"Manifold · persisted {inserted} new rows")
    return 0 if snaps else 1


async def _run_polygon(*, persist: bool, lookback_days: int = 1) -> int:
    settings = get_settings()
    if not settings.polygon_api_key:
        print(
            "Polygon · ICHOR_API_POLYGON_API_KEY is empty — skipping. "
            "Set it in /etc/ichor/api.env to enable.",
            file=sys.stderr,
        )
        return 0  # not a failure — just disabled

    today = date.today()
    from_date = today - timedelta(days=lookback_days)

    all_bars = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for asset in polygon_assets():
            try:
                bars = await fetch_aggs(
                    asset,
                    api_key=settings.polygon_api_key,
                    from_date=from_date,
                    to_date=today,
                    client=client,
                )
            except Exception as e:
                print(f"Polygon · [{asset:12s}] error: {e}", file=sys.stderr)
                continue
            print(
                f"Polygon · [{asset:12s}] {len(bars):>5d} bars  "
                f"{from_date} → {today}"
            )
            all_bars.extend(bars)

    if persist and all_bars:
        from ..collectors.persistence import persist_polygon_bars

        sm = get_sessionmaker()
        async with sm() as session:
            inserted = await persist_polygon_bars(session, all_bars)
        print(f"Polygon · persisted {inserted} new rows")
    return 0 if all_bars else 1


_HANDLERS: dict[str, "asyncio.Coroutine"] = {}


async def _main(target: str, *, persist: bool) -> int:
    handlers = {
        "rss": _run_rss,
        "polymarket": _run_polymarket,
        "market_data": _run_market_data,
        "polygon": _run_polygon,
        "fred": _run_fred,
        "gdelt": _run_gdelt,
        "ai_gpr": _run_ai_gpr,
        "cot": _run_cot,
        "cb_speeches": _run_cb_speeches,
        "kalshi": _run_kalshi,
        "manifold": _run_manifold,
    }
    try:
        if target == "all":
            rc = 0
            for name, fn in handlers.items():
                try:
                    rc |= await fn(persist=persist)
                except Exception as e:
                    print(f"\n!! {name} failed: {e}", file=sys.stderr)
                    rc |= 1
                print()
            return rc
        if target in handlers:
            return await handlers[target](persist=persist)
        print(
            f"unknown target: {target!r}\n"
            f"expected one of: {' | '.join(handlers.keys())} | all",
            file=sys.stderr,
        )
        return 2
    finally:
        if persist:
            await get_engine().dispose()


if __name__ == "__main__":
    args = sys.argv[1:]
    persist = "--persist" in args
    args = [a for a in args if a != "--persist"]
    target = args[0] if args else "all"
    sys.exit(asyncio.run(_main(target, persist=persist)))
