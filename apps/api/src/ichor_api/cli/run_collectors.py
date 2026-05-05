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
from ..collectors.bls import SERIES_TO_POLL as _BLS_SERIES
from ..collectors.bls import fetch_series as fetch_bls_series
from ..collectors.dts_treasury import fetch_operating_cash, latest_tga_close
from ..collectors.ecb_sdmx import SERIES_TO_POLL as _ECB_SERIES
from ..collectors.ecb_sdmx import fetch_series as fetch_ecb_series
from ..collectors.finra_short import fetch_daily_short_volume
from ..collectors.flashalpha import poll_all as poll_flashalpha
from ..collectors.gex_yfinance import poll_all as poll_gex_yfinance
from ..collectors.vix_live import fetch_vix
from ..collectors.forex_factory import (
    fetch_ff_calendar,
)
from ..collectors.forex_factory import (
    persist_events as persist_forex_events,
)
from ..collectors.fred import poll_all as poll_fred
from ..collectors.fred_extended import merged_series as fred_merged_series
from ..collectors.gdelt import poll_all as poll_gdelt
from ..collectors.kalshi import poll_all as poll_kalshi
from ..collectors.manifold import poll_all as poll_manifold
from ..collectors.market_data import poll_all as poll_market_data
from ..collectors.polygon import fetch_aggs
from ..collectors.polygon import supported_assets as polygon_assets
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
        print(f"  [{s.central_bank:6s}] {s.published_at:%Y-%m-%d} {s.title[:80]}")
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


async def _run_flashalpha(*, persist: bool) -> int:
    """Pull dealer GEX snapshots for SPX + NDX from FlashAlpha free tier."""
    settings = get_settings()
    if not settings.flashalpha_api_key:
        print(
            "FlashAlpha · ICHOR_API_FLASHALPHA_API_KEY is empty — skipping. "
            "Free tier registration at flashalphalive.com (5 req/day).",
            file=sys.stderr,
        )
        return 0
    snaps = await poll_flashalpha(api_key=settings.flashalpha_api_key)
    print(f"FlashAlpha · {len(snaps)} GEX snapshots fetched")
    for s in snaps:
        gex_str = f"{s.total_gex_usd / 1e9:+.2f}bn$" if s.total_gex_usd is not None else "n/a"
        flip_str = f"{s.gamma_flip:.0f}" if s.gamma_flip is not None else "n/a"
        print(
            f"  [{s.ticker:6s}] spot={s.spot} gex={gex_str} flip={flip_str} "
            f"call_wall={s.call_wall} put_wall={s.put_wall}"
        )
    if persist:
        # 2026-05-05 : table gex_snapshots exists (migration 0008) and
        # persist_gex_snapshots is wired in collectors/persistence.py.
        # Convert FlashAlpha's GexSnapshot → DealerGexSnapshot then persist.
        from ..collectors.gex_yfinance import DealerGexSnapshot
        from ..collectors.persistence import persist_gex_snapshots

        adapted = [
            DealerGexSnapshot(
                asset=s.ticker,
                captured_at=s.fetched_at,
                spot=s.spot or 0.0,
                dealer_gex_total=s.total_gex_usd or 0.0,
                gamma_flip=s.gamma_flip,
                call_wall=s.call_wall,
                put_wall=s.put_wall,
                source="flashalpha",
                raw=s.raw,
            )
            for s in snaps
        ]
        sm = get_sessionmaker()
        async with sm() as session:
            inserted = await persist_gex_snapshots(session, adapted)
        print(f"FlashAlpha · persisted {inserted} GEX rows")
    return 0 if snaps else 1


async def _run_vix_live(*, persist: bool) -> int:
    """Fetch the current ^VIX value from yfinance and persist as a
    fred_observations row with series_id='VIX_LIVE' so the brain's
    Crisis-mode detector can compare current vs prior tick.
    """
    from datetime import UTC as _UTC
    from datetime import datetime as _dt

    snap = await fetch_vix()
    if snap is None:
        print("VIX live · fetch failed (yahoo unreachable or rate-limited) — skipping")
        return 1
    print(
        f"VIX live · {snap.value:.2f} (Δ {snap.change_pct:+.2%} state={snap.market_state} "
        f"at {snap.fetched_at.isoformat()})"
    )
    if persist:
        from ..models import FredObservation

        sm = get_sessionmaker()
        async with sm() as session:
            session.add(
                FredObservation(
                    observation_date=snap.fetched_at.astimezone(_UTC).date(),
                    created_at=_dt.now(_UTC),
                    series_id="VIX_LIVE",
                    value=float(snap.value),
                    fetched_at=snap.fetched_at,
                )
            )
            await session.commit()
        print("VIX live · persisted 1 observation row (series_id=VIX_LIVE)")
    return 0


async def _run_dts_treasury(*, persist: bool) -> int:
    """Treasury DTS daily Operating Cash Balance — TGA close persists as
    fred_observations rows with series_id='DTS_TGA_CLOSE'.
    """
    from datetime import UTC as _UTC
    from datetime import datetime as _dt

    rows = await fetch_operating_cash(days=14)
    print(f"Treasury DTS · {len(rows)} cash-balance rows pulled")
    tga = latest_tga_close(rows)
    if tga and tga.closing_balance_usd_mn is not None:
        print(
            f"  latest TGA close: ${float(tga.closing_balance_usd_mn) / 1000:.1f}bn "
            f"on {tga.record_date.isoformat()}"
        )
    if persist and rows:
        from ..models import FredObservation

        sm = get_sessionmaker()
        # Persist only the TGA close series — that's the load-bearing one.
        # Other account types are stored in raw form via the brain's
        # data_pool tooling.
        n = 0
        async with sm() as session:
            for r in rows:
                if "TGA" not in (r.account_type or "").upper():
                    continue
                if r.closing_balance_usd_mn is None:
                    continue
                session.add(
                    FredObservation(
                        observation_date=r.record_date,
                        created_at=_dt.now(_UTC),
                        series_id="DTS_TGA_CLOSE",
                        value=float(r.closing_balance_usd_mn),
                        fetched_at=_dt.now(_UTC),
                    )
                )
                n += 1
            await session.commit()
        print(f"Treasury DTS · persisted {n} TGA close rows (series_id=DTS_TGA_CLOSE)")
    return 0 if rows else 1


async def _run_bls(*, persist: bool) -> int:
    """BLS public API — pulls each watched series and persists as
    fred_observations with series_id='BLS_<id>'.
    """
    from datetime import UTC as _UTC
    from datetime import date as _date
    from datetime import datetime as _dt

    settings = get_settings()
    bls_key = getattr(settings, "bls_api_key", "") or ""
    total = 0
    persisted = 0
    sm = get_sessionmaker() if persist else None

    for series_id in _BLS_SERIES:
        try:
            obs = await fetch_bls_series(series_id, api_key=bls_key)
        except Exception as e:
            print(f"BLS · [{series_id}] fetch error: {e}")
            continue
        total += len(obs)
        print(f"BLS · [{series_id}] {len(obs)} observations")
        if persist and obs and sm is not None:
            from ..models import FredObservation

            async with sm() as session:
                for o in obs:
                    if o.value is None or o.observation_date is None:
                        continue
                    session.add(
                        FredObservation(
                            observation_date=o.observation_date,
                            created_at=_dt.now(_UTC),
                            series_id=f"BLS_{o.series_id}"[:64],
                            value=float(o.value),
                            fetched_at=o.fetched_at,
                        )
                    )
                    persisted += 1
                await session.commit()
    if persist:
        print(f"BLS · persisted {persisted} rows")
    return 0 if total else 1


async def _run_ecb_sdmx(*, persist: bool) -> int:
    """ECB SDMX series — HICP, M3, MRO. Persists as fred_observations
    with series_id='ECB_<flow>_<key_short>'.
    """
    from datetime import UTC as _UTC
    from datetime import date as _date
    from datetime import datetime as _dt

    total = 0
    persisted = 0
    sm = get_sessionmaker() if persist else None

    for flow, series_key in _ECB_SERIES:
        try:
            obs = await fetch_ecb_series(flow, series_key)
        except Exception as e:
            print(f"ECB · [{flow}] fetch error: {e}")
            continue
        total += len(obs)
        print(f"ECB · [{flow}] {len(obs)} observations")
        if persist and obs and sm is not None:
            from ..models import FredObservation

            # Synthetic series_id : flow only (key is too long for our
            # 64-char index). Drop the second-half of the key after the
            # rate type prefix.
            synth_id = f"ECB_{flow}"
            async with sm() as session:
                for o in obs:
                    period = o.observation_period
                    try:
                        if "-" in period:
                            year, mp = period.split("-", 1)
                            if mp.startswith("Q"):
                                month = (int(mp[1:]) - 1) * 3 + 1
                            else:
                                month = int(mp)
                            obs_date = _date(int(year), month, 1)
                        else:
                            obs_date = _date(int(period), 1, 1)
                    except (ValueError, AttributeError):
                        continue
                    if o.value is None:
                        continue
                    session.add(
                        FredObservation(
                            observation_date=obs_date,
                            created_at=_dt.now(_UTC),
                            series_id=synth_id[:64],
                            value=float(o.value),
                            fetched_at=_dt.now(_UTC),
                        )
                    )
                    persisted += 1
                await session.commit()
    if persist:
        print(f"ECB · persisted {persisted} rows")
    return 0 if total else 1


async def _run_finra_short(*, persist: bool) -> int:
    """FINRA daily short volume — dry-run only for now (dedicated table
    not yet shipped ; the schema needs per-symbol per-day rows that
    don't fit fred_observations).

    Pull is rate-limited to a sample of 8 symbols (Ichor's tracked
    universe proxy via SPY/QQQ + 6 mega-caps) so we don't hit the
    public endpoint ceiling.
    """
    settings = get_settings()
    token = getattr(settings, "finra_api_token", "") or None
    sample_symbols: tuple[str, ...] = (
        "SPY",
        "QQQ",
        "AAPL",
        "MSFT",
        "NVDA",
        "TSLA",
        "AMZN",
        "META",
    )
    try:
        rows = await fetch_daily_short_volume(sample_symbols, api_token=token)
    except Exception as e:
        print(f"FINRA short · fetch error: {e}")
        return 1
    print(f"FINRA short · {len(rows)} daily rows for {len(sample_symbols)} symbols")
    for r in rows[:8]:
        sv = r.short_volume or 0
        tv = r.total_volume or 0
        ratio = sv / tv if tv else 0.0
        print(
            f"  [{r.symbol:6s}] {r.trade_date.isoformat()} short={sv:,} "
            f"total={tv:,} ratio={ratio:.1%}"
        )
    if persist:
        # TODO(P3) : add finra_short_volume table + persistence.
        # The shape (per-symbol per-day) doesn't fit fred_observations
        # which is one-value-per-(series_id, date).
        print(
            "FINRA short · persistence DEFERRED (needs dedicated table) — "
            "data printed above for verification only.",
            file=sys.stderr,
        )
    return 0 if rows else 1


async def _run_yfinance_options(*, persist: bool) -> int:
    """Pull dealer GEX from yfinance options chains for SPY + QQQ.

    Free, full-chain replacement for FlashAlpha (whose free tier requires
    Basic+ for index/ETF GEX — single-name only on free, capped at 5/day).
    Convention : SqueezeMetrics dealer net (short calls, long puts).
    """
    from ..collectors.persistence import persist_gex_snapshots

    snaps = await poll_gex_yfinance()
    print(f"yfinance options · {len(snaps)} GEX snapshots computed")
    for s in snaps:
        gex_str = (
            f"{s.dealer_gex_total / 1e9:+.2f}bn$" if s.dealer_gex_total is not None else "n/a"
        )
        flip_str = f"{s.gamma_flip:.0f}" if s.gamma_flip is not None else "n/a"
        print(
            f"  [{s.asset:6s}] spot={s.spot:.2f} gex={gex_str} flip={flip_str} "
            f"call_wall={s.call_wall} put_wall={s.put_wall}"
        )
    if persist and snaps:
        sm = get_sessionmaker()
        async with sm() as session:
            inserted = await persist_gex_snapshots(session, snaps)
        print(f"yfinance options · persisted {inserted} GEX rows")
    return 0 if snaps else 1


async def _run_mastodon(*, persist: bool) -> int:
    """Pull configured Mastodon ATOM feeds and optionally persist as news_items.

    Feeds are read from `settings.mastodon_followed_feeds` — a CSV of
    `kind:instance:handle` triples. Empty config = collector no-ops.
    """
    from ..collectors.mastodon import (
        fetch_mastodon_atom,
        persist_to_news_items,
        tag_feed_url,
        user_feed_url,
    )

    settings = get_settings()
    raw = (settings.mastodon_followed_feeds or "").strip()
    if not raw:
        print(
            "Mastodon · ICHOR_API_MASTODON_FOLLOWED_FEEDS is empty — skipping. "
            "Format: 'kind:instance:handle' triples, comma-separated.",
            file=sys.stderr,
        )
        return 0

    triples = [t.strip() for t in raw.split(",") if t.strip()]
    all_statuses: list = []
    async with httpx.AsyncClient(timeout=20.0) as client:
        for triple in triples:
            parts = triple.split(":")
            if len(parts) != 3:
                print(f"Mastodon · skipping malformed triple {triple!r}", file=sys.stderr)
                continue
            kind, instance, handle = parts
            if kind not in ("user", "tag"):
                print(f"Mastodon · skipping unknown kind {kind!r}", file=sys.stderr)
                continue
            url = (
                user_feed_url(instance, handle)
                if kind == "user"
                else tag_feed_url(instance, handle)
            )
            try:
                statuses = await fetch_mastodon_atom(
                    url, instance=instance, feed_kind=kind, client=client
                )
            except Exception as e:
                print(f"Mastodon · [{kind} {instance}/{handle}] error: {e}", file=sys.stderr)
                continue
            print(f"Mastodon · [{kind} {instance}/{handle}] {len(statuses)} statuses")
            all_statuses.extend(statuses)

    if persist and all_statuses:
        sm = get_sessionmaker()
        async with sm() as session:
            inserted = await persist_to_news_items(session, all_statuses)
            await session.commit()
        print(f"Mastodon · persisted {inserted} new rows ({len(all_statuses) - inserted} dedup)")
    return 0 if all_statuses else 1


async def _run_forex_factory(*, persist: bool) -> int:
    """Pull the FairEconomy/ForexFactory weekly XML calendar.

    The feed publishes the *current* week's events with consensus
    forecast and previous values ; ForexFactory revises forecast /
    previous through the week as economists update their numbers, so
    the cron schedules 4 fetches/day (03/09/15/21h Paris). The natural
    key (currency, scheduled_at, title) makes upserts idempotent.
    """
    try:
        events = await fetch_ff_calendar()
    except Exception as e:
        print(f"ForexFactory · error: {e}", file=sys.stderr)
        return 1
    print(f"ForexFactory · {len(events)} events parsed")
    for ev in events[:5]:
        ts = ev.scheduled_at.strftime("%Y-%m-%d %H:%MZ") if ev.scheduled_at else "TBD"
        forecast = ev.forecast or "—"
        previous = ev.previous or "—"
        print(
            f"  [{ev.currency:3s}] {ts}  {ev.impact:8s}  "
            f"{ev.title[:60]}  fcst={forecast} prev={previous}"
        )
    if len(events) > 5:
        print(f"  ... and {len(events) - 5} more")
    if persist:
        sm = get_sessionmaker()
        async with sm() as session:
            touched = await persist_forex_events(session, events)
            await session.commit()
        print(f"ForexFactory · persisted {touched} rows (insert+update)")
    return 0 if events else 1


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
            print(f"Polygon · [{asset:12s}] {len(bars):>5d} bars  {from_date} → {today}")
            all_bars.extend(bars)

    if persist and all_bars:
        from ..collectors.persistence import persist_polygon_bars

        sm = get_sessionmaker()
        async with sm() as session:
            inserted = await persist_polygon_bars(session, all_bars)
        print(f"Polygon · persisted {inserted} new rows")
    return 0 if all_bars else 1


_HANDLERS: dict[str, asyncio.Coroutine] = {}


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
        "flashalpha": _run_flashalpha,
        "yfinance_options": _run_yfinance_options,
        "vix_live": _run_vix_live,
        "dts_treasury": _run_dts_treasury,
        "bls": _run_bls,
        "ecb_sdmx": _run_ecb_sdmx,
        "finra_short": _run_finra_short,
        "forex_factory": _run_forex_factory,
        "mastodon": _run_mastodon,
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
            f"unknown target: {target!r}\nexpected one of: {' | '.join(handlers.keys())} | all",
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
