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
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from ..collectors.aaii import fetch_latest_aaii
from ..collectors.ai_gpr import fetch_latest as fetch_ai_gpr
from ..collectors.arxiv_qfin import fetch_qfin_recent
from ..collectors.binance_funding import poll_all as poll_binance_funding
from ..collectors.bls import SERIES_TO_POLL as _BLS_SERIES
from ..collectors.bls import fetch_series as fetch_bls_series
from ..collectors.bluesky import poll_watchlist as poll_bluesky
from ..collectors.boe_iadb import SERIES_TO_POLL as _BOE_SERIES
from ..collectors.boe_iadb import fetch_series as fetch_boe_series
from ..collectors.central_bank_speeches import poll_all as poll_cb_speeches
from ..collectors.cot import poll_all_assets as poll_cot
from ..collectors.crypto_fear_greed import fetch_fng_history
from ..collectors.defillama import poll_all as poll_defillama
from ..collectors.dts_treasury import fetch_operating_cash, latest_tga_close
from ..collectors.ecb_sdmx import SERIES_TO_POLL as _ECB_SERIES
from ..collectors.ecb_sdmx import fetch_series as fetch_ecb_series
from ..collectors.eia_petroleum import fetch_steo, fetch_weekly_petroleum_stocks
from ..collectors.finra_short import fetch_daily_short_volume
from ..collectors.flashalpha import poll_all as poll_flashalpha
from ..collectors.forex_factory import (
    fetch_ff_calendar,
)
from ..collectors.forex_factory import (
    persist_events as persist_forex_events,
)
from ..collectors.fred import poll_all as poll_fred
from ..collectors.fred_extended import merged_series as fred_merged_series
from ..collectors.gdelt import poll_all as poll_gdelt
from ..collectors.gex_yfinance import poll_all as poll_gex_yfinance
from ..collectors.kalshi import poll_all as poll_kalshi
from ..collectors.manifold import poll_all as poll_manifold
from ..collectors.market_data import poll_all as poll_market_data
from ..collectors.polygon import fetch_aggs
from ..collectors.polygon import supported_assets as polygon_assets
from ..collectors.polygon_news import fetch_news as fetch_polygon_news
from ..collectors.polygon_news import relevant_to_ichor_universe
from ..collectors.polymarket import poll_all as poll_polymarket
from ..collectors.reddit import fetch_subreddit
from ..collectors.reddit import persist_to_news_items as persist_reddit_news
from ..collectors.rss import poll_all as poll_rss
from ..collectors.treasury_auction import AuctionResult, fetch_recent_auctions
from ..collectors.vix_live import fetch_vix
from ..collectors.wikipedia_pageviews import poll_all as poll_wikipedia_pageviews
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
        from datetime import UTC as _UTC
        from datetime import timedelta as _td

        from sqlalchemy import desc, select

        from ..collectors.persistence import persist_polymarket_snapshots
        from ..models import PolymarketSnapshot
        from ..services.alerts_runner import check_metric

        sm = get_sessionmaker()
        async with sm() as session:
            inserted = await persist_polymarket_snapshots(session, snaps)

            # POLYMARKET_PROBABILITY_SHIFT : compute 24h delta in
            # probability points (yes_price × 100). Catalog metric_name=
            # 'poly_chg_24h', threshold 10pp above. We compare the
            # current snapshot's yes_price to the closest snapshot
            # ~24h ago for the same slug.
            cutoff_24h = datetime.now(_UTC) - _td(hours=24)
            cutoff_window = cutoff_24h - _td(hours=2)  # 22-26h ago window
            n_alerts = 0
            for s in snaps:
                cur_yes = s.yes_price
                if cur_yes is None:
                    continue
                hist_stmt = (
                    select(PolymarketSnapshot.last_prices)
                    .where(
                        PolymarketSnapshot.slug == s.slug,
                        PolymarketSnapshot.fetched_at >= cutoff_window,
                        PolymarketSnapshot.fetched_at <= cutoff_24h + _td(hours=2),
                    )
                    .order_by(desc(PolymarketSnapshot.fetched_at))
                    .limit(1)
                )
                hist_prices = (await session.execute(hist_stmt)).scalar_one_or_none()
                if not hist_prices or not isinstance(hist_prices, list):
                    continue
                hist_yes = hist_prices[0] if hist_prices else None
                if hist_yes is None:
                    continue
                # Delta in pp (percentage points)
                delta_pp = (float(cur_yes) - float(hist_yes)) * 100.0
                hits = await check_metric(
                    session,
                    metric_name="poly_chg_24h",
                    current_value=abs(delta_pp),
                    asset=None,
                    extra_payload={
                        "slug": s.slug,
                        "question": s.question[:200],
                        "current_yes": float(cur_yes),
                        "yes_24h_ago": float(hist_yes),
                        "delta_pp_signed": delta_pp,
                    },
                )
                n_alerts += len(hits)
            if n_alerts:
                await session.commit()
        print(f"Polymarket · persisted {inserted} snapshots, {n_alerts} shift alerts")
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
        from ..services.alerts_runner import check_fred_alerts

        # Series the catalog tracks (level + delta thresholds). Adding
        # a new alert for an additional series only requires extending
        # this set ; the runner walks the catalog itself.
        ALERT_TRIGGER_SERIES = {
            "BAMLH0A0HYM2",  # HY_OAS_WIDEN, HY_OAS_CRISIS
            "BAMLC0A0CMTRIV",  # IG_OAS_WIDEN (delta)
            "VIXCLS",  # VIX_SPIKE, VIX_PANIC (also fired by VIX_LIVE intraday)
            "SOFR",  # SOFR_SPIKE (delta)
            "DFF",  # FED_FUNDS_REPRICE
            "MOVE",  # MOVE_SPIKE
        }

        sm = get_sessionmaker()
        async with sm() as session:
            inserted = await persist_fred_observations(session, obs)

            # Run the alert evaluator on the latest value per
            # alert-tracked series. We use the most recent obs per
            # series (collector returns a list — the iteration order
            # may include older bars from a backfill window).
            latest_by_sid: dict[str, float] = {}
            for o in obs:
                if o.series_id in ALERT_TRIGGER_SERIES and o.value is not None:
                    latest_by_sid[o.series_id] = float(o.value)

            n_alerts = 0
            for sid, val in latest_by_sid.items():
                hits = await check_fred_alerts(session, series_id=sid, current_value=val)
                n_alerts += len(hits)
            if n_alerts:
                await session.commit()
        print(
            f"FRED · persisted {inserted} new rows ({len(obs) - inserted} dedup), "
            f"{n_alerts} alerts triggered"
        )
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


async def _run_cboe_skew(*, persist: bool) -> int:
    """Pull daily CBOE SKEW Index from Yahoo Finance public chart endpoint."""
    from ..collectors.cboe_skew import poll_all as poll_cboe_skew

    obs = await poll_cboe_skew()
    print(f"CBOE SKEW · {len(obs)} daily observations fetched")
    if obs:
        latest = max(obs, key=lambda o: o.observation_date)
        print(f"  latest: {latest.observation_date} = {latest.skew_value:.2f}")
    if persist:
        from ..collectors.persistence import persist_cboe_skew_observations

        sm = get_sessionmaker()
        async with sm() as session:
            inserted = await persist_cboe_skew_observations(session, obs)
        print(f"CBOE SKEW · persisted {inserted} new rows")
    return 0 if obs else 1


async def _run_cboe_vvix(*, persist: bool) -> int:
    """Pull daily CBOE VVIX (vol of VIX) from Yahoo Finance public chart endpoint."""
    from ..collectors.cboe_vvix import poll_all as poll_cboe_vvix

    obs = await poll_cboe_vvix()
    print(f"CBOE VVIX · {len(obs)} daily observations fetched")
    if obs:
        latest = max(obs, key=lambda o: o.observation_date)
        print(f"  latest: {latest.observation_date} = {latest.vvix_value:.2f}")
    if persist:
        from ..collectors.persistence import persist_cboe_vvix_observations

        sm = get_sessionmaker()
        async with sm() as session:
            inserted = await persist_cboe_vvix_observations(session, obs)
        print(f"CBOE VVIX · persisted {inserted} new rows")
    return 0 if obs else 1


async def _run_cme_zq(*, persist: bool) -> int:
    """Pull CME ZQ Fed Funds futures — front-month + 9-month forward curve.

    Wave 47: front-month only (`ZQ=F`).
    Wave 48: + 9-month forward sweep (ZQK26..ZQF27) for FedWatch DIY
    forward EFFR curve. Persists each contract under synthetic series:
        ZQ_<MONTHCODE>_PRICE
        ZQ_<MONTHCODE>_IMPLIED_EFFR
    Plus the historical front-month time-series:
        ZQ_FRONT_PRICE
        ZQ_FRONT_IMPLIED_EFFR
    """
    from datetime import UTC as _UTC
    from datetime import datetime as _dt

    from ..collectors.cme_zq_futures import (
        fetch_multi_month,
    )
    from ..collectors.cme_zq_futures import (
        poll_all as poll_cme_zq,
    )

    rows = await poll_cme_zq()
    print(f"CME ZQ · {len(rows)} front-month daily observations fetched")
    if rows:
        latest = max(rows, key=lambda r: r.observation_date)
        print(
            f"  latest front: {latest.observation_date} ZQ={latest.zq_price:.3f} "
            f"→ implied EFFR={latest.implied_effr:.3f}%"
        )
    # Wave 48 — multi-month forward curve
    multi_rows = await fetch_multi_month()
    print(f"CME ZQ · {len(multi_rows)} forward contracts fetched")
    for m in multi_rows:
        print(
            f"  {m.month_code} ({m.month_label}): ZQ={m.zq_price:.3f} "
            f"→ implied EFFR={m.implied_effr:.3f}%"
        )
    if persist and rows:
        from sqlalchemy import select as sa_select

        from ..models import FredObservation

        sm = get_sessionmaker()
        n = 0
        async with sm() as session:
            existing_dates = {
                d
                for (d,) in (
                    await session.execute(
                        sa_select(FredObservation.observation_date).where(
                            FredObservation.series_id == "ZQ_FRONT_IMPLIED_EFFR"
                        )
                    )
                ).all()
            }
            for r in rows:
                if r.observation_date in existing_dates:
                    continue
                for series_id, value in (
                    ("ZQ_FRONT_PRICE", r.zq_price),
                    ("ZQ_FRONT_IMPLIED_EFFR", r.implied_effr),
                ):
                    session.add(
                        FredObservation(
                            observation_date=r.observation_date,
                            created_at=_dt.now(_UTC),
                            series_id=series_id,
                            value=float(value),
                            fetched_at=r.fetched_at,
                        )
                    )
                n += 1
            # Wave 48 — persist forward curve. Always over-write today's
            # snapshot for each contract month (1 row per contract per day).
            multi_n = 0
            for m in multi_rows:
                price_sid = f"ZQ_{m.month_code}_PRICE"
                effr_sid = f"ZQ_{m.month_code}_IMPLIED_EFFR"
                # Dedup on (series_id, observation_date)
                existing = (
                    await session.execute(
                        sa_select(FredObservation.series_id).where(
                            FredObservation.observation_date == m.observation_date,
                            FredObservation.series_id.in_([price_sid, effr_sid]),
                        )
                    )
                ).all()
                existing_set = {row[0] for row in existing}
                for series_id, value in (
                    (price_sid, m.zq_price),
                    (effr_sid, m.implied_effr),
                ):
                    if series_id in existing_set:
                        continue
                    session.add(
                        FredObservation(
                            observation_date=m.observation_date,
                            created_at=_dt.now(_UTC),
                            series_id=series_id,
                            value=float(value),
                            fetched_at=m.fetched_at,
                        )
                    )
                    multi_n += 1
            if n or multi_n:
                await session.commit()
        print(f"CME ZQ · persisted {n} front-month dated rows + {multi_n} forward-curve rows")
    return 0 if rows else 1


async def _run_treasury_tic(*, persist: bool) -> int:
    """Pull Treasury TIC Major Foreign Holders monthly snapshot."""
    from ..collectors.treasury_tic import poll_all as poll_treasury_tic

    holdings = await poll_treasury_tic()
    n_countries = len({h.country for h in holdings})
    n_months = len({h.observation_month for h in holdings})
    print(
        f"Treasury TIC · {len(holdings)} holdings rows fetched "
        f"({n_countries} countries × {n_months} months)"
    )
    if holdings:
        latest = max(h.observation_month for h in holdings)
        recent = [h for h in holdings if h.observation_month == latest]
        print(f"  latest period: {latest}")
        for h in sorted(recent, key=lambda x: -x.holdings_bn_usd)[:5]:
            print(f"    {h.country:30s}  {h.holdings_bn_usd:>8.1f}  bn USD")
    if persist:
        from ..collectors.persistence import persist_treasury_tic_holdings

        sm = get_sessionmaker()
        async with sm() as session:
            inserted = await persist_treasury_tic_holdings(session, holdings)
        print(f"Treasury TIC · persisted {inserted} new rows")
    return 0 if holdings else 1


async def _run_cleveland_fed_nowcast(*, persist: bool) -> int:
    """Pull Cleveland Fed inflation nowcast (W72) — 4 measures × 3 horizons."""
    from ..collectors.cleveland_fed_nowcast import poll_all as poll_cleveland

    obs = await poll_cleveland()
    print(f"Cleveland Fed nowcast · {len(obs)} rows fetched")
    for r in sorted(obs, key=lambda x: (x.horizon, x.measure)):
        print(
            f"  {r.horizon}  {r.measure:8s}  target={r.target_period}  "
            f"rev={r.revision_date}  value={r.nowcast_value:.3f}%"
        )
    if persist:
        from ..collectors.persistence import persist_cleveland_fed_nowcasts

        sm = get_sessionmaker()
        async with sm() as session:
            inserted = await persist_cleveland_fed_nowcasts(session, obs)
        print(f"Cleveland Fed nowcast · persisted {inserted} new rows")
    return 0 if obs else 1


async def _run_nyfed_mct(*, persist: bool) -> int:
    """Pull NY Fed Multivariate Core Trend monthly inflation (W71)."""
    from ..collectors.nyfed_mct import poll_all as poll_nyfed_mct

    obs = await poll_nyfed_mct()
    print(f"NY Fed MCT · {len(obs)} monthly observations fetched")
    if obs:
        latest = max(obs, key=lambda o: o.observation_month)
        print(
            f"  latest = {latest.observation_month} : "
            f"MCT={latest.mct_trend_pct:.2f}%  "
            f"headlinePCE={latest.headline_pce_yoy}%  "
            f"corePCE={latest.core_pce_yoy}%"
        )
    if persist:
        from ..collectors.persistence import persist_nyfed_mct

        sm = get_sessionmaker()
        async with sm() as session:
            inserted = await persist_nyfed_mct(session, obs)
        print(f"NY Fed MCT · persisted {inserted} new rows")
    return 0 if obs else 1


async def _run_cftc_tff(*, persist: bool) -> int:
    """Pull weekly CFTC TFF (Traders in Financial Futures) from Socrata."""
    from ..collectors.cftc_tff import poll_all as poll_cftc_tff

    obs = await poll_cftc_tff()
    n_markets = len({o.market_code for o in obs})
    n_dates = len({o.report_date for o in obs})
    print(f"CFTC TFF · {len(obs)} rows fetched ({n_markets} markets × {n_dates} dates)")
    if obs:
        latest = max(obs, key=lambda o: (o.report_date, o.market_code))
        lev_net = latest.lev_money_long - latest.lev_money_short
        print(
            f"  latest: {latest.report_date} {latest.market_name[:50]}  "
            f"OI={latest.open_interest:,} LevFunds_net={lev_net:+,}"
        )
    if persist:
        from ..collectors.persistence import persist_cftc_tff_observations

        sm = get_sessionmaker()
        async with sm() as session:
            inserted = await persist_cftc_tff_observations(session, obs)
        print(f"CFTC TFF · persisted {inserted} new rows")
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
        from datetime import timedelta as _td

        from sqlalchemy import select

        from ..collectors.persistence import persist_cot_positions
        from ..models import CotPosition
        from ..services.alerts_runner import check_metric

        sm = get_sessionmaker()
        async with sm() as session:
            inserted = await persist_cot_positions(session, by_code.values())

            # COT_NET_FLIP : z-score on managed_money_net over rolling
            # 5y window. Catalog metric_name='cot_net_z', threshold 2.0
            # above. Asset-scoped — fired per market_code.
            cutoff_5y = (datetime.now(UTC) - _td(weeks=260)).date() if False else None
            # Use date.today() to avoid the datetime/date mismatch in the
            # prior line. The cutoff is genuinely date-typed (Postgres Date col).
            from datetime import date as _date

            cutoff_5y = _date.today() - _td(weeks=260)

            n_alerts = 0
            FX_COT_TO_ASSET = {
                "099741": "EUR_USD",
                "096742": "GBP_USD",
                "097741": "USD_JPY",
                "232741": "AUD_USD",
                "090741": "USD_CAD",
                "088691": "XAU_USD",
            }
            for code, pos in by_code.items():
                if pos is None or pos.managed_money_net is None:
                    continue
                hist_stmt = (
                    select(CotPosition.managed_money_net)
                    .where(
                        CotPosition.market_code == code,
                        CotPosition.report_date >= cutoff_5y,
                    )
                    .order_by(CotPosition.report_date.asc())
                )
                hist = [r[0] for r in (await session.execute(hist_stmt)).all()]
                if len(hist) < 30:  # <30 weeks = noise
                    continue
                # Z-score on the latest value vs the historical mean/std
                hist_arr = [float(x) for x in hist if x is not None]
                if not hist_arr:
                    continue
                mean = sum(hist_arr) / len(hist_arr)
                var = sum((x - mean) ** 2 for x in hist_arr) / max(1, len(hist_arr) - 1)
                std = var**0.5
                if std <= 0:
                    continue
                z = (float(pos.managed_money_net) - mean) / std
                hits = await check_metric(
                    session,
                    metric_name="cot_net_z",
                    current_value=abs(z),
                    asset=FX_COT_TO_ASSET.get(code, code),
                    extra_payload={
                        "z_signed": z,
                        "managed_money_net": pos.managed_money_net,
                        "n_history_weeks": len(hist_arr),
                        "report_date": pos.report_date.isoformat(),
                    },
                )
                n_alerts += len(hits)
            if n_alerts:
                await session.commit()
        print(f"COT · persisted {inserted} new rows, {n_alerts} z-flip alerts")
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
        from sqlalchemy import desc, select

        from ..models import FredObservation
        from ..services.alerts_runner import check_metric

        sm = get_sessionmaker()
        async with sm() as session:
            # Fetch previous VIX_LIVE BEFORE inserting the new row, so
            # the cross detection in evaluate_metric has clean prev.
            prev_stmt = (
                select(FredObservation.value)
                .where(FredObservation.series_id == "VIX_LIVE")
                .order_by(desc(FredObservation.created_at))
                .limit(1)
            )
            prev = (await session.execute(prev_stmt)).scalar_one_or_none()
            session.add(
                FredObservation(
                    observation_date=snap.fetched_at.astimezone(_UTC).date(),
                    created_at=_dt.now(_UTC),
                    series_id="VIX_LIVE",
                    value=float(snap.value),
                    fetched_at=snap.fetched_at,
                )
            )
            # The alert catalog uses metric_name='VIXCLS' (standard FRED
            # series id). VIX_LIVE intraday is semantically the same
            # measurement, just lower-latency. Feed it as VIXCLS so
            # VIX_SPIKE/VIX_PANIC fire on intraday spikes.
            hits = await check_metric(
                session,
                metric_name="VIXCLS",
                current_value=float(snap.value),
                previous_value=float(prev) if prev is not None else None,
                asset=None,
            )
            await session.commit()
        print(
            f"VIX live · persisted 1 observation row (series_id=VIX_LIVE), "
            f"{len(hits)} alerts triggered"
        )
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
    if persist and rows:
        from datetime import UTC as _UTC
        from datetime import datetime as _dt

        from sqlalchemy import select

        from ..models import FinraShortVolume

        sm = get_sessionmaker()
        n_inserted = 0
        async with sm() as session:
            # Idempotency : the (symbol, trade_date) UNIQUE constraint
            # prevents duplicate rows on cron retries. Pre-filter here
            # for cleaner counts + to avoid swallowing IntegrityErrors.
            existing_stmt = select(FinraShortVolume.symbol, FinraShortVolume.trade_date).where(
                FinraShortVolume.symbol.in_({r.symbol for r in rows}),
                FinraShortVolume.trade_date.in_({r.trade_date for r in rows}),
            )
            existing = {(s, d) for s, d in (await session.execute(existing_stmt)).all()}
            for r in rows:
                if (r.symbol, r.trade_date) in existing:
                    continue
                session.add(
                    FinraShortVolume(
                        trade_date=r.trade_date,
                        created_at=_dt.now(_UTC),
                        symbol=r.symbol[:16],
                        short_volume=r.short_volume,
                        short_exempt_volume=r.short_exempt_volume,
                        total_volume=r.total_volume,
                        short_pct=r.short_pct,
                        fetched_at=r.fetched_at,
                    )
                )
                n_inserted += 1
            await session.commit()
        print(f"FINRA short · persisted {n_inserted} new rows ({len(rows) - n_inserted} dedup)")
    return 0 if rows else 1


async def _run_aaii(*, persist: bool) -> int:
    """AAII Sentiment Survey weekly. Persists 4 series per week into
    fred_observations : AAII_BULLISH/BEARISH/NEUTRAL/SPREAD. Couche-2
    sentiment agent reads these via services/couche2_context."""
    from datetime import UTC as _UTC
    from datetime import datetime as _dt

    rows = await fetch_latest_aaii(weeks=12)
    print(f"AAII · {len(rows)} weekly readings pulled")
    for r in rows[:3]:
        print(
            f"  {r.week_ending.date().isoformat()} bull={r.bullish_pct:.0%} "
            f"bear={r.bearish_pct:.0%} spread={r.spread:+.2f}"
        )
    if persist and rows:
        from ..models import FredObservation

        sm = get_sessionmaker()
        n = 0
        async with sm() as session:
            for r in rows:
                obs_date = r.week_ending.astimezone(_UTC).date()
                for series_id, value in (
                    ("AAII_BULLISH", r.bullish_pct),
                    ("AAII_BEARISH", r.bearish_pct),
                    ("AAII_NEUTRAL", r.neutral_pct),
                    ("AAII_SPREAD", r.spread),
                ):
                    if value is None:
                        continue
                    session.add(
                        FredObservation(
                            observation_date=obs_date,
                            created_at=_dt.now(_UTC),
                            series_id=series_id,
                            value=float(value),
                            fetched_at=_dt.now(_UTC),
                        )
                    )
                    n += 1
            await session.commit()
        print(f"AAII · persisted {n} observations (4 series × {len(rows)} weeks)")
    return 0 if rows else 1


async def _run_bluesky(*, persist: bool) -> int:
    """Bluesky AT Protocol — pulls watchlist authors' feeds and persists
    as news_items (source_kind=social) for the news_nlp agent."""
    from datetime import UTC as _UTC
    from datetime import datetime as _dt
    from hashlib import sha256

    posts = await poll_bluesky()
    print(f"Bluesky · {len(posts)} posts pulled across watchlist")
    for p in posts[:3]:
        print(f"  [{p.author_handle}] {p.text[:80]!r}")
    if persist and posts:
        from ..models import NewsItem

        sm = get_sessionmaker()
        n = 0
        async with sm() as session:
            for p in posts:
                # Idempotency : guid_hash on uri
                guid_hash = sha256(p.uri.encode("utf-8")).hexdigest()[:32]
                session.add(
                    NewsItem(
                        fetched_at=p.fetched_at,
                        created_at=_dt.now(_UTC),
                        source=f"bluesky:{p.author_handle[:54]}",
                        source_kind="social",
                        title=(p.text[:200] or "(no text)"),
                        summary=p.text or None,
                        url=f"https://bsky.app/profile/{p.author_handle}/post/{p.uri.split('/')[-1]}"[
                            :1024
                        ],
                        published_at=p.created_at,
                        guid_hash=guid_hash,
                        raw_categories=None,
                    )
                )
                n += 1
            await session.commit()
        print(f"Bluesky · persisted {n} news_items rows (source_kind=social)")
    return 0 if posts else 1


async def _run_boe_iadb(*, persist: bool) -> int:
    """Bank of England IADB series → fred_observations BOE_<code>."""
    from datetime import UTC as _UTC
    from datetime import datetime as _dt

    obs = await fetch_boe_series()
    print(f"BoE IADB · {len(obs)} observations across {len(_BOE_SERIES)} series")
    if persist and obs:
        from ..models import FredObservation

        sm = get_sessionmaker()
        async with sm() as session:
            for o in obs:
                if o.value is None or o.observation_date is None:
                    continue
                session.add(
                    FredObservation(
                        observation_date=o.observation_date,
                        created_at=_dt.now(_UTC),
                        series_id=f"BOE_{o.series_code}"[:64],
                        value=float(o.value),
                        fetched_at=o.fetched_at,
                    )
                )
            await session.commit()
        print(f"BoE IADB · persisted {len(obs)} rows")
    return 0 if obs else 1


async def _run_eia_petroleum(*, persist: bool) -> int:
    """EIA OpenData v2 — weekly petroleum stocks + STEO oil prices.
    Persists into fred_observations EIA_<id>. Requires EIA_API_KEY."""
    from datetime import UTC as _UTC
    from datetime import date as _date
    from datetime import datetime as _dt

    settings = get_settings()
    eia_key = getattr(settings, "eia_api_key", "") or ""
    if not eia_key:
        print(
            "EIA · ICHOR_API_EIA_API_KEY is empty — skipping. "
            "Free registration at https://www.eia.gov/opendata/register.php",
            file=sys.stderr,
        )
        return 0

    weekly = await fetch_weekly_petroleum_stocks(api_key=eia_key)
    steo = await fetch_steo(api_key=eia_key)
    obs = list(weekly) + list(steo)
    print(f"EIA · weekly={len(weekly)} steo={len(steo)} total={len(obs)} obs")
    if persist and obs:
        from ..models import FredObservation

        sm = get_sessionmaker()
        n = 0
        async with sm() as session:
            for o in obs:
                if o.value is None:
                    continue
                # Period parse : "2026-04" or "2026-04-25"
                try:
                    parts = o.period.split("-")
                    if len(parts) == 3:
                        obs_date = _date(int(parts[0]), int(parts[1]), int(parts[2]))
                    elif len(parts) == 2:
                        obs_date = _date(int(parts[0]), int(parts[1]), 1)
                    else:
                        continue
                except (ValueError, AttributeError):
                    continue
                session.add(
                    FredObservation(
                        observation_date=obs_date,
                        created_at=_dt.now(_UTC),
                        series_id=f"EIA_{o.series_id}"[:64],
                        value=float(o.value),
                        fetched_at=_dt.now(_UTC),
                    )
                )
                n += 1
            await session.commit()

            # OIL_INVENTORY_SHOCK : crude inventory week-over-week change
            # in million barrels. The catalog metric_name='EIA_crude_chg'
            # threshold=-5 below. We compute it from the latest 2 WCESTUS1
            # observations.
            from ..services.alerts_runner import check_metric

            crude_obs = sorted(
                [o for o in obs if o.series_id == "WCESTUS1" and o.value is not None],
                key=lambda o: o.period,
            )
            n_alerts = 0
            if len(crude_obs) >= 2:
                wow = (float(crude_obs[-1].value) - float(crude_obs[-2].value)) / 1000.0
                hits = await check_metric(
                    session,
                    metric_name="EIA_crude_chg",
                    current_value=wow,
                    asset=None,
                    extra_payload={
                        "current_kbbl": float(crude_obs[-1].value),
                        "previous_kbbl": float(crude_obs[-2].value),
                    },
                )
                n_alerts = len(hits)
                if n_alerts:
                    await session.commit()
        print(f"EIA · persisted {n} rows, {n_alerts} alerts triggered")
    return 0 if obs else 1


async def _run_polygon_news(*, persist: bool) -> int:
    """Polygon news endpoint — filters to Ichor universe, persists as
    news_items (source_kind=news, source=polygon_news)."""
    from datetime import UTC as _UTC
    from datetime import datetime as _dt
    from datetime import timedelta as _td
    from hashlib import sha256

    settings = get_settings()
    api_key = settings.polygon_api_key
    if not api_key:
        print("Polygon news · ICHOR_API_POLYGON_API_KEY is empty — skipping", file=sys.stderr)
        return 0
    cutoff = _dt.now(_UTC) - _td(hours=6)
    items = await fetch_polygon_news(api_key=api_key, limit=100, published_after=cutoff)
    relevant = [it for it in items if relevant_to_ichor_universe(it)]
    print(f"Polygon news · pulled={len(items)} relevant={len(relevant)}")
    if persist and relevant:
        from ..models import NewsItem

        sm = get_sessionmaker()
        n = 0
        async with sm() as session:
            for it in relevant:
                guid_hash = sha256(it.id.encode("utf-8")).hexdigest()[:32]
                session.add(
                    NewsItem(
                        fetched_at=_dt.now(_UTC),
                        created_at=_dt.now(_UTC),
                        source=(it.publisher_name or "polygon_news")[:64],
                        source_kind="news",
                        title=it.title[:512],
                        summary=it.description or None,
                        url=it.url[:1024],
                        published_at=it.published_at,
                        guid_hash=guid_hash,
                        raw_categories=list(it.keywords)[:8] if it.keywords else None,
                    )
                )
                n += 1
            await session.commit()
        print(f"Polygon news · persisted {n} news_items rows")
    return 0 if items else 1


async def _run_defillama(*, persist: bool) -> int:
    """DeFiLlama TVL by chain + aggregate stablecoin supply.

    Persists series_id format :
      DEFILLAMA_TVL_{chain}      (TVL per chain, USD)
      DEFILLAMA_STABLECOIN_TOTAL (aggregate peggedUSD supply, USD)
    Both into fred_observations for unified macro context loading.
    """
    from datetime import UTC as _UTC
    from datetime import datetime as _dt

    tvl_obs, stables = await poll_defillama(last_n_days=60)
    print(
        f"DeFiLlama · {len(tvl_obs)} TVL points across chains, "
        f"{len(stables)} stablecoin supply points"
    )
    if persist and (tvl_obs or stables):
        from ..models import FredObservation

        sm = get_sessionmaker()
        n = 0
        async with sm() as session:
            for o in tvl_obs:
                session.add(
                    FredObservation(
                        observation_date=o.observation_date,
                        created_at=_dt.now(_UTC),
                        series_id=f"DEFILLAMA_TVL_{o.chain.upper()[:42]}"[:64],
                        value=float(o.tvl_usd),
                        fetched_at=o.fetched_at,
                    )
                )
                n += 1
            for s in stables:
                session.add(
                    FredObservation(
                        observation_date=s.observation_date,
                        created_at=_dt.now(_UTC),
                        series_id="DEFILLAMA_STABLECOIN_TOTAL",
                        value=float(s.total_circulating_usd),
                        fetched_at=s.fetched_at,
                    )
                )
                n += 1
            await session.commit()
        print(f"DeFiLlama · persisted {n} rows")
    return 0 if (tvl_obs or stables) else 1


async def _run_binance_funding(*, persist: bool) -> int:
    """Binance USDⓈ-M perpetual funding rates aggregated to one row
    per (symbol, day). Each day has 3 settlements (8h cadence) ; we
    store the daily mean to fit the fred_observations UNIQUE
    (series_id, observation_date) constraint.

    Series stored : BINANCE_FUNDING_{symbol} (raw mean of the 3 ticks),
    BINANCE_FUNDING_ANN_{symbol} (linearly annualized)."""
    from datetime import UTC as _UTC
    from datetime import datetime as _dt

    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from ..collectors.binance_funding import annualize_rate

    records = await poll_binance_funding(limit=200)
    print(f"Binance funding · {len(records)} settlements across symbols")
    for r in records[:3]:
        ann = annualize_rate(r.funding_rate)
        print(
            f"  [{r.symbol:8s}] {r.funding_time.isoformat()} rate={r.funding_rate:+.4%} "
            f"(ann ≈ {ann:+.1%})"
        )
    if persist and records:
        # Aggregate per (symbol, day) — mean funding rate.
        from collections import defaultdict

        from ..models import FredObservation

        bucket: dict[tuple[str, object], list[float]] = defaultdict(list)
        fetched: dict[tuple[str, object], _dt] = {}
        for r in records:
            day = r.funding_time.astimezone(_UTC).date()
            key = (r.symbol, day)
            bucket[key].append(r.funding_rate)
            fetched[key] = r.fetched_at

        sm = get_sessionmaker()
        n_rows = 0
        async with sm() as session:
            for (symbol, day), rates in bucket.items():
                mean_rate = sum(rates) / len(rates)
                ann = annualize_rate(mean_rate)
                # ON CONFLICT DO UPDATE — idempotent on cron retries.
                # The composite uniqueness is on (series_id, observation_date).
                for sid, val in (
                    (f"BINANCE_FUNDING_{symbol}"[:64], float(mean_rate)),
                    (f"BINANCE_FUNDING_ANN_{symbol}"[:64], float(ann)),
                ):
                    stmt = pg_insert(FredObservation).values(
                        id=__import__("uuid").uuid4(),
                        observation_date=day,
                        created_at=_dt.now(_UTC),
                        series_id=sid,
                        value=val,
                        fetched_at=fetched[(symbol, day)],
                    )
                    stmt = stmt.on_conflict_do_update(
                        constraint="uq_fred_series_date",
                        set_={"value": stmt.excluded.value, "fetched_at": stmt.excluded.fetched_at},
                    )
                    await session.execute(stmt)
                    n_rows += 1
            await session.commit()
        print(
            f"Binance funding · upserted {n_rows} rows "
            f"({len(bucket)} (symbol, day) buckets × 2 series)"
        )
    return 0 if records else 1


async def _run_crypto_fng(*, persist: bool) -> int:
    """Crypto Fear & Greed Index (alternative.me) → fred_observations
    series_id=CRYPTO_FNG. The index is 0-100 ; extremes (≤20 or ≥80)
    are conventional contrarian thresholds."""
    from datetime import UTC as _UTC
    from datetime import datetime as _dt

    readings = await fetch_fng_history(limit=30)
    print(f"Crypto F&G · {len(readings)} daily readings")
    for r in readings[:3]:
        print(f"  {r.observation_date.isoformat()} value={r.value} ({r.classification})")
    if persist and readings:
        from ..models import FredObservation

        sm = get_sessionmaker()
        async with sm() as session:
            for r in readings:
                session.add(
                    FredObservation(
                        observation_date=r.observation_date,
                        created_at=_dt.now(_UTC),
                        series_id="CRYPTO_FNG",
                        value=float(r.value),
                        fetched_at=r.fetched_at,
                    )
                )
            await session.commit()
        print(f"Crypto F&G · persisted {len(readings)} rows")
    return 0 if readings else 1


async def _run_wikipedia_pageviews(*, persist: bool) -> int:
    """Wikipedia pageviews on macro/geopolitical articles → fred_observations
    WIKI_PAGEVIEWS_<article>. Public attention proxy."""
    from datetime import UTC as _UTC
    from datetime import datetime as _dt

    from sqlalchemy.dialects.postgresql import insert as pg_insert

    obs = await poll_wikipedia_pageviews(days=30)
    print(f"Wikipedia pageviews · {len(obs)} (article, day) observations")
    if persist and obs:
        from ..models import FredObservation

        sm = get_sessionmaker()
        n = 0
        async with sm() as session:
            for o in obs:
                # Truncate article to fit String(64) series_id
                short_art = o.article.replace(" ", "_")[:48]
                sid = f"WIKI_PV_{short_art}"[:64]
                stmt = (
                    pg_insert(FredObservation)
                    .values(
                        id=__import__("uuid").uuid4(),
                        observation_date=o.observation_date,
                        created_at=_dt.now(_UTC),
                        series_id=sid,
                        value=float(o.views),
                        fetched_at=o.fetched_at,
                    )
                    .on_conflict_do_update(
                        constraint="uq_fred_series_date",
                        set_={"value": float(o.views), "fetched_at": o.fetched_at},
                    )
                )
                await session.execute(stmt)
                n += 1
            await session.commit()
        print(f"Wikipedia pageviews · upserted {n} rows")
    return 0 if obs else 1


async def _run_arxiv_qfin(*, persist: bool) -> int:
    """arXiv q-fin papers → news_items (source_kind='academic')."""
    from datetime import UTC as _UTC
    from datetime import datetime as _dt
    from hashlib import sha256

    papers = await fetch_qfin_recent(max_results=50)
    print(f"arXiv q-fin · {len(papers)} papers fetched")
    for p in papers[:3]:
        authors = ", ".join(p.authors[:2])
        print(f"  [{p.primary_category:8s}] {p.title[:80]} ({authors})")

    if persist and papers:
        from ..models import NewsItem

        sm = get_sessionmaker()
        n = 0
        async with sm() as session:
            for p in papers:
                guid_hash = sha256(p.arxiv_id.encode("utf-8")).hexdigest()[:32]
                session.add(
                    NewsItem(
                        fetched_at=p.fetched_at,
                        created_at=_dt.now(_UTC),
                        source=f"arxiv:{p.primary_category}"[:64],
                        source_kind="academic",
                        title=p.title[:512],
                        summary=p.summary[:2000] if p.summary else None,
                        url=p.abs_url[:1024],
                        published_at=p.published_at,
                        guid_hash=guid_hash,
                        raw_categories=[p.primary_category],
                    )
                )
                n += 1
            await session.commit()
        print(f"arXiv q-fin · persisted {n} news_items rows (source_kind=academic)")
    return 0 if papers else 1


async def _run_treasury_auction(*, persist: bool) -> int:
    """US Treasury auction results — fires TREASURY_AUCTION_TAIL when
    high-vs-median yield gap ≥ 2 bps for the latest auction.

    Persists per (security_type, term) :
      TREASURY_AUCTION_HIGH_{type}_{term}  (latest high yield, %)
      TREASURY_AUCTION_BTC_{type}_{term}   (latest bid-to-cover)
    """
    from datetime import UTC as _UTC
    from datetime import datetime as _dt

    from sqlalchemy.dialects.postgresql import insert as pg_insert

    rows = await fetch_recent_auctions(days=14)
    print(f"Treasury auctions · {len(rows)} auctions in last 14d")
    for r in rows[:5]:
        tail = r.tail_bps
        tail_str = f"{tail:+.2f}bps" if tail is not None else "n/a"
        btc_str = f"{r.bid_to_cover_ratio:.2f}" if r.bid_to_cover_ratio else "n/a"
        print(
            f"  {r.issue_date.isoformat()} {r.security_type:6s} {r.security_term:10s} "
            f"high={r.high_yield} median={r.median_yield} tail={tail_str} btc={btc_str}"
        )

    if persist and rows:
        from ..models import FredObservation
        from ..services.alerts_runner import check_metric

        sm = get_sessionmaker()
        n_persisted = 0
        n_alerts = 0
        # We alert on the most recent auction per (type, term) only.
        latest_by_kind: dict[tuple[str, str], AuctionResult] = {}
        for r in rows:
            key = (r.security_type, r.security_term)
            cur = latest_by_kind.get(key)
            if cur is None or r.issue_date > cur.issue_date:
                latest_by_kind[key] = r

        async with sm() as session:
            for r in rows:
                short_type = r.security_type.replace(" ", "")[:8]
                short_term = r.security_term.replace(" ", "")[:12]
                if r.high_yield is not None:
                    sid = f"TREASURY_AUC_HIGH_{short_type}_{short_term}"[:64]
                    stmt = (
                        pg_insert(FredObservation)
                        .values(
                            id=__import__("uuid").uuid4(),
                            observation_date=r.issue_date,
                            created_at=_dt.now(_UTC),
                            series_id=sid,
                            value=float(r.high_yield),
                            fetched_at=r.fetched_at,
                        )
                        .on_conflict_do_update(
                            constraint="uq_fred_series_date",
                            set_={"value": float(r.high_yield)},
                        )
                    )
                    await session.execute(stmt)
                    n_persisted += 1
                if r.bid_to_cover_ratio is not None:
                    sid = f"TREASURY_AUC_BTC_{short_type}_{short_term}"[:64]
                    stmt = (
                        pg_insert(FredObservation)
                        .values(
                            id=__import__("uuid").uuid4(),
                            observation_date=r.issue_date,
                            created_at=_dt.now(_UTC),
                            series_id=sid,
                            value=float(r.bid_to_cover_ratio),
                            fetched_at=r.fetched_at,
                        )
                        .on_conflict_do_update(
                            constraint="uq_fred_series_date",
                            set_={"value": float(r.bid_to_cover_ratio)},
                        )
                    )
                    await session.execute(stmt)
                    n_persisted += 1

            # TREASURY_AUCTION_TAIL — only on the freshest auction per kind,
            # to avoid re-firing on backfill of historical rows.
            for r in latest_by_kind.values():
                tail = r.tail_bps
                if tail is None:
                    continue
                hits = await check_metric(
                    session,
                    metric_name="auction_tail_bps",
                    current_value=tail,
                    asset=None,
                    extra_payload={
                        "security_type": r.security_type,
                        "security_term": r.security_term,
                        "issue_date": r.issue_date.isoformat(),
                        "high_yield": r.high_yield,
                        "median_yield": r.median_yield,
                        "bid_to_cover_ratio": r.bid_to_cover_ratio,
                    },
                )
                n_alerts += len(hits)
            await session.commit()
        print(f"Treasury auctions · upserted {n_persisted} rows, {n_alerts} tail alerts")
    return 0 if rows else 1


async def _run_reddit(*, persist: bool) -> int:
    """Reddit subreddit watchlist — pulls hot posts and persists into
    news_items (source_kind=social). Used by the Couche-2 sentiment
    agent for retail-mood readings.

    Public JSON endpoint (no OAuth) — rate-limited gentle. We poll
    4 subreddits (wallstreetbets, forex, stockmarket, Gold) per
    AUDIT_V3 §sentiment.
    """

    SUBREDDITS: tuple[str, ...] = (
        "wallstreetbets",
        "forex",
        "stockmarket",
        "Gold",
    )
    all_posts = []
    for sub in SUBREDDITS:
        try:
            posts = await fetch_subreddit(sub, sort="hot", limit=25)
        except Exception as e:
            print(f"Reddit · [{sub}] error: {e}", file=sys.stderr)
            continue
        print(f"Reddit · [{sub:20s}] {len(posts)} posts")
        all_posts.extend(posts)

    if persist and all_posts:
        sm = get_sessionmaker()
        async with sm() as session:
            inserted = await persist_reddit_news(session, all_posts)
            await session.commit()
        print(f"Reddit · persisted {inserted} new rows ({len(all_posts) - inserted} dedup)")
    return 0 if all_posts else 1


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
        gex_str = f"{s.dealer_gex_total / 1e9:+.2f}bn$" if s.dealer_gex_total is not None else "n/a"
        flip_str = f"{s.gamma_flip:.0f}" if s.gamma_flip is not None else "n/a"
        print(
            f"  [{s.asset:6s}] spot={s.spot:.2f} gex={gex_str} flip={flip_str} "
            f"call_wall={s.call_wall} put_wall={s.put_wall}"
        )
    if persist and snaps:
        sm = get_sessionmaker()
        async with sm() as session:
            inserted = await persist_gex_snapshots(session, snaps)
            # Trigger GEX_FLIP / DEALER_GAMMA_FLIP alerts on sign cross.
            # We fetch prev INSIDE the session so the just-inserted
            # snapshot is excluded from the previous-value lookup.
            from ..services.alerts_runner import check_gex_alerts

            n_alerts = 0
            for s in snaps:
                hits = await check_gex_alerts(
                    session, asset=s.asset, dealer_gex_total=s.dealer_gex_total
                )
                n_alerts += len(hits)
            if n_alerts:
                await session.commit()
        print(f"yfinance options · persisted {inserted} GEX rows, {n_alerts} alerts triggered")
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
        from ..services.alerts_runner import check_metric

        sm = get_sessionmaker()
        async with sm() as session:
            inserted = await persist_polygon_bars(session, all_bars)

            # Price-based alert wiring : feed the latest close/high per
            # asset to the catalog. The catalog encodes per-asset metric
            # names (USD_JPY_close, XAU_USD_high) so we walk our bars
            # by asset and match.
            latest_by_asset: dict[str, Any] = {}
            for b in all_bars:
                cur = latest_by_asset.get(b.asset)
                if cur is None or b.bar_ts > cur.bar_ts:
                    latest_by_asset[b.asset] = b

            # FX peg references — drive FX_PEG_BREAK (catalog metric=
            # 'fx_peg_dev', threshold 1% above, crisis_mode=True).
            #   USDHKD : HKMA Convertibility Undertaking midpoint 7.80
            #   USDCNH : managed-float around PBOC daily fix — proxied
            #            here by a 30-bar rolling mean (~30 min on 1-min bars).
            FX_PEG_REFS: dict[str, float | str] = {
                "USD_HKD": 7.80,
                "USD_CNH": "rolling30",
            }
            n_alerts = 0
            for asset, bar in latest_by_asset.items():
                close_metric = f"{asset}_close"
                hits_close = await check_metric(
                    session,
                    metric_name=close_metric,
                    current_value=float(bar.close),
                    asset=asset,
                )
                high_metric = f"{asset}_high"
                hits_high = await check_metric(
                    session,
                    metric_name=high_metric,
                    current_value=float(bar.high),
                    asset=asset,
                )
                n_alerts += len(hits_close) + len(hits_high)

                if asset in FX_PEG_REFS:
                    ref = FX_PEG_REFS[asset]
                    if ref == "rolling30":
                        recent = [float(b.close) for b in all_bars if b.asset == asset][-30:]
                        ref_level = sum(recent) / len(recent) if len(recent) >= 5 else None
                    else:
                        ref_level = float(ref)
                    if ref_level is not None and ref_level > 0:
                        peg_dev_pct = abs(float(bar.close) - ref_level) / ref_level * 100.0
                        peg_hits = await check_metric(
                            session,
                            metric_name="fx_peg_dev",
                            current_value=peg_dev_pct,
                            asset=asset,
                            extra_payload={
                                "current_close": float(bar.close),
                                "peg_reference": ref_level,
                                "deviation_pct": peg_dev_pct,
                            },
                        )
                        n_alerts += len(peg_hits)
            if n_alerts:
                await session.commit()
        print(f"Polygon · persisted {inserted} new rows, {n_alerts} alerts triggered")
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
        "cboe_skew": _run_cboe_skew,
        "cboe_vvix": _run_cboe_vvix,
        "cme_zq": _run_cme_zq,
        "treasury_tic": _run_treasury_tic,
        "nyfed_mct": _run_nyfed_mct,
        "cleveland_fed_nowcast": _run_cleveland_fed_nowcast,
        "cftc_tff": _run_cftc_tff,
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
        "aaii": _run_aaii,
        "bluesky": _run_bluesky,
        "boe_iadb": _run_boe_iadb,
        "eia_petroleum": _run_eia_petroleum,
        "polygon_news": _run_polygon_news,
        # fred_extended is a pre-existing cron name. The actual extended
        # series are merged into the main `fred` handler via
        # collectors.fred_extended.merged_series. Aliasing prevents the
        # silent "unknown target" exit.
        "fred_extended": _run_fred,
        # Crypto sources (free-tier, no auth)
        "defillama": _run_defillama,
        "binance_funding": _run_binance_funding,
        "crypto_fng": _run_crypto_fng,
        "reddit": _run_reddit,
        "treasury_auction": _run_treasury_auction,
        "wikipedia_pageviews": _run_wikipedia_pageviews,
        "arxiv_qfin": _run_arxiv_qfin,
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
