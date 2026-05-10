"""Postgres → markdown context loaders for the 4 Couche-2 agents.

Each `build_*_context()` function loads the latest rows for a given
agent kind and renders a compact markdown brief the LLM can consume
without needing tool calls. Formatting is stable so prompt-engineering
on the agent side stays predictable.

ADR-021 Phase B Sprint 3 wiring : replaces the V0 boilerplate in
`cli/run_couche2_agent._build_context` so the 4 Claude agents reason
on real Postgres rows instead of placeholder strings.

Empty-data is explicit rather than silent : each section emits
"_No rows in window_" so the agent can decide to return empty/null
fields rather than hallucinate.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    CbSpeech,
    CotPosition,
    EconomicEvent,
    FredObservation,
    NewsItem,
    PolygonGexSnapshot,
    PolymarketSnapshot,
)


@dataclass(frozen=True)
class Couche2Context:
    body: str
    """Rendered markdown brief, ready to inject as the user prompt."""

    sources: list[str]
    """Source identifiers used (for couche2_outputs.input_sources audit)."""

    n_rows: int
    """Total rows fetched across all sub-queries — for observability."""


_FX_COT_MARKETS = {
    "099741": "EUR_USD",
    "096742": "GBP_USD",
    "097741": "JPY_USD",
    "232741": "AUD_USD",
    "090741": "CAD_USD",
    "088691": "XAU_USD",
}


def _fmt_dt(dt: datetime | date | None) -> str:
    if dt is None:
        return "n/a"
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    return dt.isoformat()


def _truncate(s: str | None, n: int = 240) -> str:
    if not s:
        return ""
    s = s.strip().replace("\n", " ").replace("\r", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


async def build_cb_nlp_context(
    session: AsyncSession,
    *,
    days: int = 7,
    limit: int = 40,
) -> Couche2Context:
    """CB speeches in the last `days`, grouped by central_bank.

    Latest first. Up to `limit` total rows. Each row renders as one
    markdown bullet : speaker, date, title, summary excerpt, url.
    """
    cutoff = datetime.now(UTC) - timedelta(days=days)
    stmt = (
        select(CbSpeech)
        .where(CbSpeech.published_at >= cutoff)
        .order_by(CbSpeech.published_at.desc())
        .limit(limit)
    )
    rows: Sequence[CbSpeech] = (await session.execute(stmt)).scalars().all()

    if not rows:
        return Couche2Context(
            body=f"# CB Speeches — last {days} days\n\n_No CB speeches in window._\n",
            sources=["cb_speeches"],
            n_rows=0,
        )

    by_cb: dict[str, list[CbSpeech]] = {}
    for r in rows:
        by_cb.setdefault(r.central_bank.upper(), []).append(r)

    parts = [f"# CB Speeches — last {days} days ({len(rows)} rows)\n"]
    for cb in sorted(by_cb.keys()):
        parts.append(f"\n## {cb}")
        for r in by_cb[cb][:8]:  # top 8 per CB to bound prompt size
            parts.append(
                f"- **{_fmt_dt(r.published_at)}** — {r.speaker or 'unknown speaker'}: "
                f"_{_truncate(r.title, 200)}_"
            )
            if r.summary:
                parts.append(f"  > {_truncate(r.summary, 360)}")
            parts.append(f"  ({r.url})")

    return Couche2Context(
        body="\n".join(parts),
        sources=["cb_speeches"],
        n_rows=len(rows),
    )


async def build_news_nlp_context(
    session: AsyncSession,
    *,
    hours: int = 4,
    limit: int = 80,
) -> Couche2Context:
    """News items in the last `hours`, grouped by source_kind."""
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    stmt = (
        select(NewsItem)
        .where(NewsItem.published_at >= cutoff)
        .order_by(NewsItem.published_at.desc())
        .limit(limit)
    )
    rows: Sequence[NewsItem] = (await session.execute(stmt)).scalars().all()

    if not rows:
        return Couche2Context(
            body=f"# News — last {hours}h\n\n_No headlines in window._\n",
            sources=["news_items"],
            n_rows=0,
        )

    by_kind: dict[str, list[NewsItem]] = {}
    for r in rows:
        by_kind.setdefault(r.source_kind, []).append(r)

    parts = [f"# News headlines — last {hours}h ({len(rows)} rows)\n"]
    for kind in sorted(by_kind.keys()):
        items = by_kind[kind]
        parts.append(f"\n## {kind} ({len(items)} headlines)")
        for r in items[:30]:
            tone = ""
            if r.tone_label and r.tone_score is not None:
                tone = f" [tone={r.tone_label} {r.tone_score:+.2f}]"
            parts.append(
                f"- **{_fmt_dt(r.published_at)}** [{r.source}]{tone} _{_truncate(r.title, 200)}_"
            )
            if r.summary:
                parts.append(f"  > {_truncate(r.summary, 280)}")

    return Couche2Context(
        body="\n".join(parts),
        sources=["news_items"],
        n_rows=len(rows),
    )


# AAII series IDs as stored if/when persisted in fred_observations.
# The aaii.py collector currently has no persistence → these queries
# return empty until the AAII pipeline is wired (Wave P2).
_AAII_SERIES = ("AAII_BULLISH", "AAII_BEARISH", "AAII_NEUTRAL", "AAII_SPREAD")

# FRED series IDs for the macro agent context. Each maps to a theme
# the MacroAgent's prompt expects. Empty rows = theme omitted.
_MACRO_FRED_SERIES = {
    "CPIAUCSL": "CPI (US headline)",
    "CPILFESL": "CPI core",
    "PCEPI": "PCE deflator",
    "PCEPILFE": "PCE core",
    "PPIACO": "PPI (US, all commodities)",
    "PAYEMS": "NFP (non-farm payrolls)",
    "UNRATE": "Unemployment rate",
    "ICSA": "Initial jobless claims",
    "GDP": "Real GDP",
    "INDPRO": "Industrial production",
    "DGS10": "10Y Treasury yield",
    "DGS2": "2Y Treasury yield",
    "DFF": "Effective Fed Funds rate",
    "T10Y2Y": "10Y-2Y spread (curve)",
    "DCOILWTICO": "WTI crude oil spot",
    "VIXCLS": "VIX close",
    "DTWEXBGS": "USD nominal trade-weighted index (broad)",
    "BAMLH0A0HYM2": "HY OAS (corporate credit stress)",
}


async def build_sentiment_context(
    session: AsyncSession,
    *,
    days: int = 14,
) -> Couche2Context:
    """Sentiment context — AAII (if persisted) + nothing else for now.

    Reddit / Google Trends are not yet ingested ; the prompt acknowledges
    the gap so the agent emits null fields instead of hallucinating.
    """
    sources = ["fred_observations:AAII"]
    parts = [f"# Sentiment — last {days} days\n"]

    cutoff_date = (datetime.now(UTC) - timedelta(days=days)).date()
    stmt = (
        select(FredObservation)
        .where(
            FredObservation.series_id.in_(_AAII_SERIES),
            FredObservation.observation_date >= cutoff_date,
        )
        .order_by(FredObservation.observation_date.desc())
        .limit(30)
    )
    rows: Sequence[FredObservation] = (await session.execute(stmt)).scalars().all()

    if rows:
        parts.append("\n## AAII Sentiment Survey (weekly)")
        by_date: dict[date, dict[str, float]] = {}
        for r in rows:
            by_date.setdefault(r.observation_date, {})[r.series_id] = r.value or 0.0
        for d in sorted(by_date.keys(), reverse=True)[:6]:
            row = by_date[d]
            parts.append(
                f"- **{d.isoformat()}** — bull={row.get('AAII_BULLISH', 0):.0%} "
                f"bear={row.get('AAII_BEARISH', 0):.0%} "
                f"neutral={row.get('AAII_NEUTRAL', 0):.0%} "
                f"spread={row.get('AAII_SPREAD', 0):+.2f}"
            )
    else:
        parts.append("\n## AAII Sentiment Survey")
        parts.append("_AAII data not yet ingested — return aaii=null in your output._")

    parts.append("\n## Reddit & Google Trends")
    parts.append(
        "_Reddit/Google Trends collectors not yet wired — return reddit=[] and "
        "google_trends_shifts=[] in your output. Set overall_retail_mood from AAII "
        "alone if available, else 'neutral'._"
    )

    return Couche2Context(
        body="\n".join(parts),
        sources=sources,
        n_rows=len(rows),
    )


async def build_positioning_context(
    session: AsyncSession,
    *,
    cot_weeks: int = 6,
    gex_hours: int = 24,
    polymarket_hours: int = 6,
    polymarket_min_volume_usd: float = 10000.0,
) -> Couche2Context:
    """COT (latest report) + GEX snapshots (last 24h) + Polymarket
    high-volume markets (last 6h, > $10K)."""
    sources: list[str] = []
    parts: list[str] = ["# Positioning context\n"]
    n_rows = 0

    # ── COT — last `cot_weeks` weekly reports for the 6 FX markets we track
    cot_cutoff = (datetime.now(UTC) - timedelta(weeks=cot_weeks)).date()
    cot_stmt = (
        select(CotPosition)
        .where(
            CotPosition.market_code.in_(_FX_COT_MARKETS.keys()),
            CotPosition.report_date >= cot_cutoff,
        )
        .order_by(CotPosition.report_date.desc(), CotPosition.market_code)
    )
    cot_rows: Sequence[CotPosition] = (await session.execute(cot_stmt)).scalars().all()
    if cot_rows:
        sources.append("cot_positions")
        n_rows += len(cot_rows)
        # Latest report_date only — that's "the" current positioning
        latest_date = cot_rows[0].report_date
        latest = [r for r in cot_rows if r.report_date == latest_date]
        parts.append(f"\n## COT (CFTC Disaggregated, week ending {latest_date.isoformat()})")
        for r in latest:
            asset = _FX_COT_MARKETS.get(r.market_code, r.market_code)
            specs_net = r.managed_money_net + r.other_reportable_net
            parts.append(
                f"- **{asset}** — managed_money_net={r.managed_money_net:+,d} "
                f"swap_dealer_net={r.swap_dealer_net:+,d} producer_net={r.producer_net:+,d} "
                f"OI={r.open_interest:,d} (specs combined={specs_net:+,d})"
            )
        # Show 3-week change for each market
        if len(cot_rows) > len(latest):
            parts.append("\n_Week-over-week trend (oldest → newest):_")
            by_market: dict[str, list[CotPosition]] = {}
            for r in cot_rows:
                by_market.setdefault(r.market_code, []).append(r)
            for code, series in by_market.items():
                asset = _FX_COT_MARKETS.get(code, code)
                trend = " → ".join(f"{r.managed_money_net:+,d}" for r in reversed(series[:4]))
                parts.append(f"- {asset}: {trend}")
    else:
        parts.append("\n## COT")
        parts.append("_No COT rows in window — return cot=[] in your output._")

    # ── GEX — latest snapshots per asset in the last 24h
    gex_cutoff = datetime.now(UTC) - timedelta(hours=gex_hours)
    gex_stmt = (
        select(PolygonGexSnapshot)
        .where(PolygonGexSnapshot.captured_at >= gex_cutoff)
        .order_by(PolygonGexSnapshot.captured_at.desc())
        .limit(20)
    )
    gex_rows: Sequence[PolygonGexSnapshot] = (await session.execute(gex_stmt)).scalars().all()
    if gex_rows:
        sources.append("gex_snapshots")
        n_rows += len(gex_rows)
        # Group by asset, take latest
        latest_by_asset: dict[str, PolygonGexSnapshot] = {}
        for r in gex_rows:
            if r.asset not in latest_by_asset:
                latest_by_asset[r.asset] = r
        parts.append("\n## Dealer GEX (latest snapshot per asset)")
        for asset, r in sorted(latest_by_asset.items()):
            gex_str = (
                f"{float(r.dealer_gex_total) / 1e9:+.2f}bn$"
                if r.dealer_gex_total is not None
                else "n/a"
            )
            parts.append(
                f"- **{asset}** ({_fmt_dt(r.captured_at)}, src={r.source}): "
                f"net_gex={gex_str} spot={r.spot_at_capture} "
                f"flip={r.gamma_flip} call_wall={r.call_wall} put_wall={r.put_wall}"
            )
    else:
        parts.append("\n## Dealer GEX")
        parts.append("_No GEX snapshots in window — return gex=[] in your output._")

    # ── Polymarket — high-volume markets in last 6h
    pm_cutoff = datetime.now(UTC) - timedelta(hours=polymarket_hours)
    pm_stmt = (
        select(PolymarketSnapshot)
        .where(
            PolymarketSnapshot.fetched_at >= pm_cutoff,
            PolymarketSnapshot.volume_usd >= polymarket_min_volume_usd,
            PolymarketSnapshot.closed.is_(False),
        )
        .order_by(PolymarketSnapshot.volume_usd.desc())
        .limit(15)
    )
    pm_rows: Sequence[PolymarketSnapshot] = (await session.execute(pm_stmt)).scalars().all()
    if pm_rows:
        sources.append("polymarket_snapshots")
        n_rows += len(pm_rows)
        parts.append(
            f"\n## Polymarket — high-volume markets last {polymarket_hours}h "
            f"(volume ≥ ${polymarket_min_volume_usd:,.0f})"
        )
        for r in pm_rows[:10]:
            yes_price = r.last_prices[0] if r.last_prices else None
            yp = f"{yes_price:.2%}" if isinstance(yes_price, (int, float)) else "n/a"
            parts.append(
                f"- _{_truncate(r.question, 180)}_ — yes={yp} "
                f"vol=${r.volume_usd:,.0f} ({_fmt_dt(r.fetched_at)})"
            )
    else:
        parts.append("\n## Polymarket")
        parts.append("_No high-volume markets in window — return polymarket_whales=[]._")

    parts.append("\n## IV skew options chains")
    parts.append("_yfinance options chains not yet wired — return iv_skews=[] in output._")

    return Couche2Context(
        body="\n".join(parts),
        sources=sources or ["empty"],
        n_rows=n_rows,
    )


async def build_macro_context(
    session: AsyncSession,
    *,
    days: int = 14,
    cb_days: int = 3,
) -> Couche2Context:
    """Macro agent context — latest FRED observations across themes +
    recent CB speeches as the rhetoric overlay.

    Theme map : monetary_policy, growth_data, inflation_data,
    labor_market, fiscal_policy, geopolitics, credit_conditions,
    commodity_supply (cf MacroAgentOutput.MacroTheme).
    """
    sources: list[str] = []
    parts = [f"# Macro context — last {days} days\n"]
    n_rows = 0

    # ── FRED prints
    cutoff_date = (datetime.now(UTC) - timedelta(days=days)).date()
    fred_stmt = (
        select(FredObservation)
        .where(
            FredObservation.series_id.in_(_MACRO_FRED_SERIES.keys()),
            FredObservation.observation_date >= cutoff_date,
        )
        .order_by(FredObservation.series_id, FredObservation.observation_date.desc())
    )
    fred_rows: Sequence[FredObservation] = (await session.execute(fred_stmt)).scalars().all()

    if fred_rows:
        sources.append("fred_observations")
        n_rows += len(fred_rows)
        parts.append("\n## FRED — latest observations per series")
        # Keep only the latest 2 prints per series (latest + prior for delta)
        latest_per: dict[str, list[FredObservation]] = {}
        for r in fred_rows:
            latest_per.setdefault(r.series_id, []).append(r)
        for sid in sorted(latest_per.keys()):
            rows = latest_per[sid][:2]
            label = _MACRO_FRED_SERIES.get(sid, sid)
            cur = rows[0]
            prev = rows[1] if len(rows) > 1 else None
            cur_v = f"{cur.value:.4g}" if cur.value is not None else "n/a"
            if prev and prev.value is not None and cur.value is not None:
                delta = cur.value - prev.value
                parts.append(
                    f"- **{sid}** ({label}) — {cur_v} on {cur.observation_date.isoformat()} "
                    f"(prev {prev.value:.4g} on {prev.observation_date.isoformat()}, "
                    f"Δ {delta:+.4g})"
                )
            else:
                parts.append(
                    f"- **{sid}** ({label}) — {cur_v} on {cur.observation_date.isoformat()}"
                )
    else:
        parts.append("\n## FRED")
        parts.append(
            "_No FRED observations in window — return drivers=[] and "
            "overall_bias='neutral' if you can't substantiate a theme._"
        )

    # ── CB speeches overlay (last cb_days) — rhetoric reinforces the macro picture
    cb_cutoff = datetime.now(UTC) - timedelta(days=cb_days)
    cb_stmt = (
        select(CbSpeech)
        .where(CbSpeech.published_at >= cb_cutoff)
        .order_by(CbSpeech.published_at.desc())
        .limit(15)
    )
    cb_rows: Sequence[CbSpeech] = (await session.execute(cb_stmt)).scalars().all()
    if cb_rows:
        sources.append("cb_speeches")
        n_rows += len(cb_rows)
        parts.append(f"\n## CB rhetoric overlay — last {cb_days} days")
        for r in cb_rows[:8]:
            parts.append(
                f"- **{_fmt_dt(r.published_at)}** [{r.central_bank}] "
                f"{r.speaker or 'unknown'}: _{_truncate(r.title, 160)}_"
            )

    return Couche2Context(
        body="\n".join(parts),
        sources=sources or ["empty"],
        n_rows=n_rows,
    )


async def build_economic_calendar_context(
    session: AsyncSession,
    *,
    hours_ahead: int = 24,
) -> str:
    """Bonus block — upcoming economic events. Concatenated to all kinds
    so every agent has macro calendar context.
    """
    now = datetime.now(UTC)
    horizon = now + timedelta(hours=hours_ahead)
    stmt = (
        select(EconomicEvent)
        .where(
            EconomicEvent.scheduled_at.is_not(None),
            EconomicEvent.scheduled_at >= now,
            EconomicEvent.scheduled_at <= horizon,
        )
        .order_by(EconomicEvent.scheduled_at.asc())
        .limit(20)
    )
    rows: Sequence[EconomicEvent] = (await session.execute(stmt)).scalars().all()
    if not rows:
        return ""
    parts = [f"\n# Upcoming economic events — next {hours_ahead}h"]
    for r in rows:
        impact = (r.impact or "").upper()
        parts.append(
            f"- **{_fmt_dt(r.scheduled_at)}** [{r.currency}] {impact} "
            f"_{_truncate(r.title, 160)}_ "
            f"(forecast={r.forecast or 'n/a'}, prev={r.previous or 'n/a'})"
        )
    return "\n".join(parts)


async def build_context_for_kind(
    session: AsyncSession,
    kind: str,
    *,
    hours: int = 6,
) -> Couche2Context:
    """Top-level dispatcher : returns the full markdown context for one
    of the 4 Couche-2 kinds + appends the upcoming economic calendar.
    """
    if kind == "cb_nlp":
        ctx = await build_cb_nlp_context(session, days=7)
    elif kind == "news_nlp":
        ctx = await build_news_nlp_context(session, hours=hours)
    elif kind == "sentiment":
        ctx = await build_sentiment_context(session, days=14)
    elif kind == "positioning":
        ctx = await build_positioning_context(session)
    elif kind == "macro":
        ctx = await build_macro_context(session, days=14, cb_days=3)
    else:
        raise ValueError(f"unknown kind: {kind!r}")

    cal = await build_economic_calendar_context(session, hours_ahead=24)
    if cal:
        ctx = Couche2Context(
            body=ctx.body + cal,
            sources=ctx.sources + ["economic_events"],
            n_rows=ctx.n_rows,
        )
    return ctx
