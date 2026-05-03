"""Build the consolidated 24h data pool fed to the brain orchestrator.

Replaces the static placeholder string used in `cli/run_session_card.py`
with a real DB-backed assembly of every Phase-1 data source. Every
numeric claim emitted into the pool is **source-stamped** (series_id,
URL, or table+timestamp) so the Critic Agent can verify and the Pass-2
schema's `mechanisms[].sources[]` field can cite back.

Why a service rather than inline in the CLI :
  - the same builder will be reused by the cron CLI when we move from
    on-demand --live runs to systemd-driven 06:00 / 12:30 Paris cards
  - testable in isolation (each section has a pure formatter)
  - cacheable per session (the pool is identical across the 4 passes,
    so it only hits Postgres once)

VISION_2026.md delta — closes the "Critic blocks because no sources"
gap surfaced by the first --live run on 2026-05-04 (id 93903a14).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    CbSpeech,
    CotPosition,
    FredObservation,
    GdeltEvent,
    GprObservation,
    KalshiMarket,
    ManifoldMarket,
    NewsItem,
    PolygonIntradayBar,
    PolymarketSnapshot,
)


# ────────────────────────── Configuration ──────────────────────────────


# FRED series we surface in the macro trinity + dollar smile blocks.
# series_id : (display_label, format_spec)
_MACRO_TRINITY_SERIES: dict[str, tuple[str, str]] = {
    "DTWEXBGS": ("DXY (broad)", "{:.2f}"),
    "DGS10": ("US10Y nominal", "{:.2f}%"),
    "VIXCLS": ("VIX", "{:.2f}"),
}

_DOLLAR_SMILE_SERIES: dict[str, tuple[str, str]] = {
    "DFII10": ("10Y TIPS real yield", "{:.2f}%"),
    "BAMLH0A0HYM2": ("HY OAS", "{:.2f}%"),
    "BAMLC0A0CM": ("IG OAS", "{:.2f}%"),
    "T10Y2Y": ("10Y-2Y curve", "{:+.2f}%"),
    "DGS2": ("US 2Y", "{:.2f}%"),
}

# Foreign rate differentials we compute as DGS10 - <foreign 10Y>
_RATE_DIFF_PAIRS: dict[str, tuple[str, str]] = {
    "EUR_USD": ("IRLTLT01DEM156N", "DE10Y"),
    "GBP_USD": ("IRLTLT01GBM156N", "UK10Y"),
    "USD_JPY": ("IRLTLT01JPM156N", "JP10Y"),
    "AUD_USD": ("IRLTLT01AUM156N", "AU10Y"),
    "USD_CAD": ("IRLTLT01CAM156N", "CA10Y"),
}

# COT market codes per Phase-1 asset (CFTC Disaggregated Futures Only).
_COT_MARKET_BY_ASSET: dict[str, str] = {
    "EUR_USD": "EU",
    "GBP_USD": "BP",
    "USD_JPY": "JY",
    "AUD_USD": "AD",
    "USD_CAD": "CD",
    "XAU_USD": "GC",
    "NAS100_USD": "NQ",
    "SPX500_USD": "ES",
}

# Polygon ticker per asset (mirrors collectors/polygon.py).
_ASSET_TO_POLYGON: dict[str, str] = {
    "EUR_USD": "C:EURUSD",
    "GBP_USD": "C:GBPUSD",
    "USD_JPY": "C:USDJPY",
    "AUD_USD": "C:AUDUSD",
    "USD_CAD": "C:USDCAD",
    "XAU_USD": "C:XAUUSD",
    "NAS100_USD": "I:NDX",
    "SPX500_USD": "I:SPX",
}


# ────────────────────────── Output container ──────────────────────────


@dataclass(frozen=True)
class DataPool:
    """Output of `build_data_pool` — markdown sections + provenance hash.

    `markdown` is what's passed to the brain. `sources` is a flat list
    of every (series_id | url | table:row_id) cited so the Critic can
    verify nothing was hallucinated. Pass-2 schema requires every
    mechanism to cite a source from this list.
    """

    asset: str
    generated_at: datetime
    markdown: str
    sources: list[str] = field(default_factory=list)
    sections_emitted: list[str] = field(default_factory=list)


# ────────────────────────── Section builders ──────────────────────────


async def _latest_fred(
    session: AsyncSession, series_id: str, max_age_days: int = 14
) -> tuple[float, datetime] | None:
    """Latest observation for `series_id` if at most `max_age_days` old."""
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=max_age_days)
    stmt = (
        select(FredObservation)
        .where(
            FredObservation.series_id == series_id,
            FredObservation.observation_date >= cutoff,
            FredObservation.value.is_not(None),
        )
        .order_by(desc(FredObservation.observation_date))
        .limit(1)
    )
    row = (await session.execute(stmt)).scalars().first()
    if row is None or row.value is None:
        return None
    return (
        float(row.value),
        datetime.combine(row.observation_date, datetime.min.time(), tzinfo=timezone.utc),
    )


async def _section_macro_trinity(session: AsyncSession) -> tuple[str, list[str]]:
    """## Macro trinity — DXY / US10Y / VIX, last value with date."""
    lines = ["## Macro trinity (FRED, latest)"]
    sources: list[str] = []
    any_data = False
    for series_id, (label, fmt) in _MACRO_TRINITY_SERIES.items():
        v = await _latest_fred(session, series_id)
        if v is None:
            lines.append(f"- {label}: n/a (FRED:{series_id})")
            continue
        any_data = True
        val, when = v
        lines.append(
            f"- {label} = {fmt.format(val)} (FRED:{series_id}, {when:%Y-%m-%d})"
        )
        sources.append(f"FRED:{series_id}")
    if not any_data:
        lines.append("  _(no FRED data yet — collector hasn't filled the table)_")
    return "\n".join(lines), sources


async def _section_dollar_smile(session: AsyncSession) -> tuple[str, list[str]]:
    """## Dollar smile inputs — TIPS real yields, OAS spreads, term structure."""
    lines = ["## Dollar smile inputs (FRED)"]
    sources: list[str] = []
    for series_id, (label, fmt) in _DOLLAR_SMILE_SERIES.items():
        v = await _latest_fred(session, series_id)
        if v is None:
            lines.append(f"- {label}: n/a (FRED:{series_id})")
            continue
        val, when = v
        lines.append(
            f"- {label} = {fmt.format(val)} (FRED:{series_id}, {when:%Y-%m-%d})"
        )
        sources.append(f"FRED:{series_id}")
    return "\n".join(lines), sources


async def _section_rate_diff(
    session: AsyncSession, asset: str
) -> tuple[str, list[str]]:
    """## Rate differential — US 10Y minus the relevant foreign 10Y for FX pairs."""
    pair = _RATE_DIFF_PAIRS.get(asset)
    if pair is None:
        return "", []
    foreign_series, foreign_label = pair
    us = await _latest_fred(session, "DGS10")
    fr = await _latest_fred(session, foreign_series)
    sources = ["FRED:DGS10"]
    lines = [f"## Rate differential ({asset})"]
    if us is None or fr is None:
        lines.append(f"- US10Y - {foreign_label}: n/a (one of the series unavailable)")
        return "\n".join(lines), sources
    diff = us[0] - fr[0]
    lines.append(
        f"- US10Y - {foreign_label} = {diff:+.2f}% "
        f"(US {us[0]:.2f}% on {us[1]:%Y-%m-%d}, "
        f"{foreign_label} {fr[0]:.2f}% on {fr[1]:%Y-%m-%d})"
    )
    sources.append(f"FRED:{foreign_series}")
    return "\n".join(lines), sources


async def _section_polygon_intraday(
    session: AsyncSession, asset: str
) -> tuple[str, list[str]]:
    """## Polygon intraday — last 1-min bar for every asset (cross-asset context)."""
    lines = ["## Polygon intraday (last 1-min bar per asset, last 6h)"]
    sources: list[str] = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
    for ast in _ASSET_TO_POLYGON:
        stmt = (
            select(PolygonIntradayBar)
            .where(
                PolygonIntradayBar.asset == ast,
                PolygonIntradayBar.bar_ts >= cutoff,
            )
            .order_by(desc(PolygonIntradayBar.bar_ts))
            .limit(1)
        )
        row = (await session.execute(stmt)).scalars().first()
        marker = " ← target" if ast == asset else ""
        if row is None:
            lines.append(f"- {ast}: no recent bar (market closed or no data){marker}")
            continue
        lines.append(
            f"- {ast} = {row.close:.5f} "
            f"(o={row.open:.5f} h={row.high:.5f} l={row.low:.5f} "
            f"vol={row.volume or 0} @ {row.bar_ts:%Y-%m-%d %H:%M UTC}, "
            f"polygon:{row.ticker}){marker}"
        )
        sources.append(f"polygon:{row.ticker}@{row.bar_ts.isoformat()}")
    return "\n".join(lines), sources


async def _section_cot(
    session: AsyncSession, asset: str
) -> tuple[str, list[str]]:
    """## COT positioning — latest weekly Disaggregated row for the asset."""
    market = _COT_MARKET_BY_ASSET.get(asset)
    if market is None:
        return "", []
    stmt = (
        select(CotPosition)
        .where(CotPosition.market_code == market)
        .order_by(desc(CotPosition.report_date))
        .limit(2)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    if not rows:
        return f"## COT positioning ({asset}, market={market})\n- n/a", []
    cur = rows[0]
    delta = (cur.managed_money_net - rows[1].managed_money_net) if len(rows) > 1 else None
    delta_str = f", Δw/w {delta:+,}" if delta is not None else ""
    sources = [f"CFTC:COT:{market}@{cur.report_date.isoformat()}"]
    md = (
        f"## COT positioning ({asset}, market={market})\n"
        f"- managed_money_net = {cur.managed_money_net:+,}{delta_str} "
        f"(swap_dealer_net={cur.swap_dealer_net:+,}, "
        f"open_interest={cur.open_interest:,}, "
        f"report_date={cur.report_date:%Y-%m-%d})"
    )
    return md, sources


async def _section_prediction_markets(
    session: AsyncSession,
) -> tuple[str, list[str]]:
    """## Prediction markets — top 5 fresh entries from each venue."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=12)
    sources: list[str] = []
    sections: list[str] = ["## Prediction markets (last 12h, top 5 per venue)"]

    # Polymarket
    poly_rows = list(
        (
            await session.execute(
                select(PolymarketSnapshot)
                .where(PolymarketSnapshot.fetched_at >= cutoff)
                .order_by(desc(PolymarketSnapshot.fetched_at))
                .limit(5)
            )
        ).scalars().all()
    )
    sections.append("### Polymarket")
    if not poly_rows:
        sections.append("- (no fresh snapshots)")
    else:
        for r in poly_rows:
            yes = r.last_prices[0] if (r.last_prices and len(r.last_prices) > 0) else None
            yes_str = f"YES={yes:.2f}" if yes is not None else "YES=n/a"
            sections.append(f"- {r.question[:90]} → {yes_str} (slug:{r.slug})")
            sources.append(f"polymarket:{r.slug}")

    # Kalshi
    kal_rows = list(
        (
            await session.execute(
                select(KalshiMarket)
                .where(KalshiMarket.fetched_at >= cutoff)
                .order_by(desc(KalshiMarket.fetched_at))
                .limit(5)
            )
        ).scalars().all()
    )
    sections.append("### Kalshi")
    if not kal_rows:
        sections.append("- (no fresh snapshots)")
    else:
        for r in kal_rows:
            yp = f"YES={r.yes_price:.2f}" if r.yes_price is not None else "YES=n/a"
            sections.append(f"- {r.title[:90]} → {yp} (ticker:{r.ticker})")
            sources.append(f"kalshi:{r.ticker}")

    # Manifold
    man_rows = list(
        (
            await session.execute(
                select(ManifoldMarket)
                .where(ManifoldMarket.fetched_at >= cutoff)
                .order_by(desc(ManifoldMarket.fetched_at))
                .limit(5)
            )
        ).scalars().all()
    )
    sections.append("### Manifold")
    if not man_rows:
        sections.append("- (no fresh snapshots)")
    else:
        for r in man_rows:
            p = f"P={r.probability:.2f}" if r.probability is not None else "P=n/a"
            sections.append(f"- {r.question[:90]} → {p} (slug:{r.slug})")
            sources.append(f"manifold:{r.slug}")

    return "\n".join(sections), sources


async def _section_geopolitics(session: AsyncSession) -> tuple[str, list[str]]:
    """## Geopolitics — AI-GPR latest + GDELT critical cluster count."""
    lines = ["## Geopolitics"]
    sources: list[str] = []

    gpr_stmt = (
        select(GprObservation)
        .order_by(desc(GprObservation.observation_date))
        .limit(1)
    )
    gpr = (await session.execute(gpr_stmt)).scalars().first()
    if gpr is not None:
        lines.append(
            f"- AI-GPR = {gpr.ai_gpr:.1f} "
            f"(Iacoviello, observation_date={gpr.observation_date:%Y-%m-%d})"
        )
        sources.append(f"AI-GPR@{gpr.observation_date.isoformat()}")
    else:
        lines.append("- AI-GPR: n/a")

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    gdelt_stmt = (
        select(GdeltEvent)
        .where(GdeltEvent.seendate >= cutoff)
        .order_by(GdeltEvent.tone.asc())
        .limit(5)
    )
    gdelt_rows = list((await session.execute(gdelt_stmt)).scalars().all())
    if gdelt_rows:
        lines.append("- GDELT 5 most-negative events last 24h:")
        for r in gdelt_rows:
            lines.append(
                f"  · tone={r.tone:+.1f} {r.title[:80]} "
                f"({r.domain or 'unknown'}, query={r.query_label}) {r.url}"
            )
            sources.append(r.url)
    else:
        lines.append("- GDELT: no events in the last 24h")

    return "\n".join(lines), sources


async def _section_cb_speeches(session: AsyncSession) -> tuple[str, list[str]]:
    """## Central bank speeches — last 5 within 7 days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    stmt = (
        select(CbSpeech)
        .where(CbSpeech.published_at >= cutoff)
        .order_by(desc(CbSpeech.published_at))
        .limit(5)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    sources: list[str] = []
    if not rows:
        return "## Central bank speeches (last 7d)\n- (none ingested)", []
    lines = ["## Central bank speeches (last 7d)"]
    for r in rows:
        speaker = f" {r.speaker}" if r.speaker else ""
        lines.append(
            f"- {r.published_at:%Y-%m-%d} [{r.central_bank}{speaker}] {r.title[:90]} {r.url}"
        )
        sources.append(r.url)
    return "\n".join(lines), sources


async def _section_news(session: AsyncSession) -> tuple[str, list[str]]:
    """## News — top 8 most-recent items in last 12h."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=12)
    stmt = (
        select(NewsItem)
        .where(NewsItem.published_at >= cutoff)
        .order_by(desc(NewsItem.published_at))
        .limit(8)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    if not rows:
        return "## News (last 12h)\n- (no items ingested)", []
    lines = ["## News (last 12h, top 8 most recent)"]
    sources: list[str] = []
    for r in rows:
        lines.append(
            f"- {r.published_at:%Y-%m-%d %H:%M} {r.source} · {r.title[:90]} {r.url}"
        )
        sources.append(r.url)
    return "\n".join(lines), sources


# ────────────────────────── Orchestrator ──────────────────────────────


async def build_data_pool(session: AsyncSession, asset: str) -> DataPool:
    """Compose the full data pool markdown for one asset.

    Sections are ordered from "biggest macro context" → "asset-specific"
    so the Pass-1 régime call (which only sees the macro trinity + dollar
    smile + geopolitics) gets clean signal at the top, and Pass-2
    (which sees the full pool) gets the asset-specific blocks at the
    bottom.
    """
    asset = asset.upper()
    sections: list[tuple[str, str, list[str]]] = []

    macro_md, macro_src = await _section_macro_trinity(session)
    sections.append(("macro_trinity", macro_md, macro_src))

    smile_md, smile_src = await _section_dollar_smile(session)
    sections.append(("dollar_smile", smile_md, smile_src))

    diff_md, diff_src = await _section_rate_diff(session, asset)
    if diff_md:
        sections.append(("rate_diff", diff_md, diff_src))

    poly_md, poly_src = await _section_polygon_intraday(session, asset)
    sections.append(("polygon_intraday", poly_md, poly_src))

    cot_md, cot_src = await _section_cot(session, asset)
    if cot_md:
        sections.append(("cot", cot_md, cot_src))

    pm_md, pm_src = await _section_prediction_markets(session)
    sections.append(("prediction_markets", pm_md, pm_src))

    geo_md, geo_src = await _section_geopolitics(session)
    sections.append(("geopolitics", geo_md, geo_src))

    cb_md, cb_src = await _section_cb_speeches(session)
    sections.append(("cb_speeches", cb_md, cb_src))

    news_md, news_src = await _section_news(session)
    sections.append(("news", news_md, news_src))

    body = "\n\n".join(md for _, md, _ in sections)
    all_sources: list[str] = []
    for _, _, srcs in sections:
        all_sources.extend(srcs)
    sections_emitted = [name for name, _, _ in sections]

    now = datetime.now(timezone.utc)
    header = (
        f"# Ichor data pool — {asset} — generated {now:%Y-%m-%d %H:%M UTC}\n\n"
        f"Sections : {', '.join(sections_emitted)}\n"
        f"Total sources cited : {len(all_sources)}\n\n---"
    )
    markdown = f"{header}\n\n{body}\n"
    return DataPool(
        asset=asset,
        generated_at=now,
        markdown=markdown,
        sources=all_sources,
        sections_emitted=sections_emitted,
    )


async def build_asset_data_only(session: AsyncSession, asset: str) -> str:
    """Subset of the pool restricted to the asset's drivers — Pass 2 input.

    Pass 1 receives the full `markdown` ; Pass 2 wants only the slice
    relevant to the asset to keep the prompt tight (cache breakpoint
    after system prompt + framework, asset_data uncached per call).
    """
    asset = asset.upper()
    parts: list[str] = []
    diff_md, _ = await _section_rate_diff(session, asset)
    if diff_md:
        parts.append(diff_md)
    poly_md, _ = await _section_polygon_intraday(session, asset)
    parts.append(poly_md)
    cot_md, _ = await _section_cot(session, asset)
    if cot_md:
        parts.append(cot_md)
    pm_md, _ = await _section_prediction_markets(session)
    parts.append(pm_md)
    return "\n\n".join(parts) if parts else "(no asset-specific data available)"
