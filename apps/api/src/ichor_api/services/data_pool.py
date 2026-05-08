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
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    CboeSkewObservation,
    CboeVvixObservation,
    CbSpeech,
    CftcTffObservation,
    CotPosition,
    FredObservation,
    GdeltEvent,
    GprObservation,
    KalshiMarket,
    ManifoldMarket,
    NewsItem,
    PolygonIntradayBar,
    PolymarketSnapshot,
    TreasuryTicHolding,
)
from . import cb_intervention as cb_intervention_svc

# Phase 2 — gisement existant câblé + ML adapters
from .analogues import render_analogues_block
from .asian_session import (
    assess_asian_session,
    render_asian_session_block,
)
from .asian_session import (
    supported_pairs as asian_supported_pairs,
)
from .confluence_engine import (
    assess_confluence,
    render_confluence_block,
)
from .correlations import (
    assess_correlations,
    render_correlations_block,
)
from .couche2_persistence import render_couche2_block
from .currency_strength import (
    assess_currency_strength,
    render_currency_strength_block,
)
from .daily_levels import (
    DailyLevels,
    assess_daily_levels,
    render_daily_levels_block,
)
from .divergence import render_divergence_block
from .economic_calendar import (
    assess_calendar,
    render_calendar_block,
)
from .funding_stress import (
    assess_funding_stress,
    render_funding_stress_block,
)
from .gex_persistence import render_gex_block
from .hourly_volatility import (
    assess_hourly_volatility,
    render_hourly_volatility_block,
)
from .microstructure import (
    assess_microstructure,
    render_microstructure_block,
)
from .ml_signals import render_ml_signals_block
from .narrative_tracker import render_narrative_block, track_narratives
from .polymarket_impact import (
    assess_polymarket_impact,
    render_polymarket_impact_block,
)
from .portfolio_exposure import (
    assess_portfolio_exposure,
    render_portfolio_exposure_block,
)
from .risk_appetite import (
    assess_risk_appetite,
    render_risk_appetite_block,
)
from .session_scenarios import (
    RegimeQuadrant,
    SessionType,
    assess_session_scenarios,
    render_session_scenarios_block,
)
from .surprise_index import (
    assess_surprise_index,
    render_surprise_index_block,
)
from .vix_term_structure import (
    assess_vix_term,
    render_vix_term_block,
)
from .yield_curve import (
    assess_yield_curve,
    render_yield_curve_block,
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

# COT CFTC market codes per Phase-1 asset (Disaggregated Futures Only).
# Codes mirror collectors/cot.py:MARKET_CODE_TO_ASSET — the canonical
# CFTC numeric identifiers, not the human-friendly 2-letter shorthands.
_COT_MARKET_BY_ASSET: dict[str, str] = {
    "EUR_USD": "099741",  # EURO FX
    "GBP_USD": "096742",  # BRITISH POUND STERLING
    "USD_JPY": "097741",  # JAPANESE YEN (reverse polarity for USD/JPY)
    "AUD_USD": "232741",  # AUSTRALIAN DOLLAR
    "USD_CAD": "090741",  # CANADIAN DOLLAR (reverse polarity)
    "XAU_USD": "088691",  # GOLD
    "NAS100_USD": "209742",  # E-MINI NASDAQ-100
    # SPX500 E-Mini code not in collectors/cot.py yet — when added there,
    # mirror it here so the COT section auto-fills.
}

# CFTC TFF (Traders in Financial Futures) market codes per Phase-1 asset.
# Mirrors collectors/cftc_tff.py:MARKET_TO_ASSET — the canonical numeric
# (or alphanumeric) CFTC identifiers. TFF disaggregates open interest
# into 4 trader classes (Dealer / AssetMgr / LevFunds / Other / Nonrept)
# so we can detect smart-money divergence per asset.
_TFF_MARKET_BY_ASSET: dict[str, str] = {
    "EUR_USD": "099741",
    "GBP_USD": "096742",
    "USD_JPY": "097741",  # JPY positioning is inverted vs USD/JPY pair
    "AUD_USD": "232741",
    "USD_CAD": "090741",  # CAD positioning inverted
    "XAU_USD": "088691",
    "NAS100_USD": "209742",
    "SPX500_USD": "13874A",  # E-MINI S&P 500 (TFF covers it; COT collector doesn't yet)
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
    cutoff = datetime.now(UTC).date() - timedelta(days=max_age_days)
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
        datetime.combine(row.observation_date, datetime.min.time(), tzinfo=UTC),
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
        lines.append(f"- {label} = {fmt.format(val)} (FRED:{series_id}, {when:%Y-%m-%d})")
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
        lines.append(f"- {label} = {fmt.format(val)} (FRED:{series_id}, {when:%Y-%m-%d})")
        sources.append(f"FRED:{series_id}")
    return "\n".join(lines), sources


async def _section_rate_diff(session: AsyncSession, asset: str) -> tuple[str, list[str]]:
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


async def _section_polygon_intraday(session: AsyncSession, asset: str) -> tuple[str, list[str]]:
    """## Polygon intraday — last 1-min bar for every asset (cross-asset context)."""
    lines = ["## Polygon intraday (last 1-min bar per asset, last 6h)"]
    sources: list[str] = []
    cutoff = datetime.now(UTC) - timedelta(hours=6)
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


async def _section_tail_risk_skew(session: AsyncSession) -> tuple[str, list[str]]:
    """## Vol surface — CBOE SKEW + sister vol indices (Wave 28).

    Full volatility surface in one section:
      - SKEW    : OOM tail-risk component VIX misses (S&P 500)
      - GVZCLS  : Gold ETF vol (XAU exposure)
      - OVXCLS  : Crude Oil ETF vol (energy exposure)
      - RVXCLS  : Russell 2000 vol (small-cap exposure, completes vs VIX)

    Macro-broad section: Pass 1 reads for régime classification, Pass 2
    for dollar-smile-break correlation + asset-specific vol exposure.
    """
    sources: list[str] = []
    lines: list[str] = ["## Vol surface (CBOE)"]

    # ── SKEW (custom table) ──
    cutoff = datetime.now(UTC).date() - timedelta(days=45)
    skew_stmt = (
        select(CboeSkewObservation)
        .where(CboeSkewObservation.observation_date >= cutoff)
        .order_by(desc(CboeSkewObservation.observation_date))
        .limit(30)
    )
    skew_rows = list((await session.execute(skew_stmt)).scalars().all())
    if skew_rows:
        latest = skew_rows[0]
        if latest.skew_value >= 150:
            band = "panic priced in (>150)"
        elif latest.skew_value >= 130:
            band = "elevated stress (130-150)"
        elif latest.skew_value >= 115:
            band = "modest tail bid (115-130)"
        else:
            band = "neutral / complacent (<115)"
        values = [r.skew_value for r in skew_rows]
        lines.append(
            f"- SKEW (S&P tail) = {latest.skew_value:.2f} on "
            f"{latest.observation_date:%Y-%m-%d} — {band} "
            f"(30d range [{min(values):.2f}, {max(values):.2f}], "
            f"mean {sum(values) / len(values):.2f}, n={len(values)})"
        )
        sources.append(f"CBOE:SKEW@{latest.observation_date.isoformat()}")
        lines.append("- SKEW: n/a (collector hasn't filled the table)")

    # ── VVIX (vol-of-vol) — wave 30 add ──
    vvix_stmt = (
        select(CboeVvixObservation)
        .where(CboeVvixObservation.observation_date >= cutoff)
        .order_by(desc(CboeVvixObservation.observation_date))
        .limit(30)
    )
    vvix_rows = list((await session.execute(vvix_stmt)).scalars().all())
    if vvix_rows:
        v_latest = vvix_rows[0]
        if v_latest.vvix_value >= 140:
            v_band = "vol-surface blowup territory (>140)"
        elif v_latest.vvix_value >= 100:
            v_band = "elevated turbulence (>100)"
        elif v_latest.vvix_value >= 85:
            v_band = "modest bid (~85-100)"
        else:
            v_band = "calm vol-surface (<85)"
        v_vals = [r.vvix_value for r in vvix_rows]
        lines.append(
            f"- VVIX (vol of VIX) = {v_latest.vvix_value:.2f} on "
            f"{v_latest.observation_date:%Y-%m-%d} — {v_band} "
            f"(30d range [{min(v_vals):.2f}, {max(v_vals):.2f}], "
            f"mean {sum(v_vals) / len(v_vals):.2f}, n={len(v_vals)})"
        )
        sources.append(f"CBOE:VVIX@{v_latest.observation_date.isoformat()}")
    else:
        lines.append("- VVIX: n/a (collector hasn't filled the table)")

    # ── Sister vol indices via FRED ──
    for series_id, label in (
        ("GVZCLS", "GVZ (gold vol)"),
        ("OVXCLS", "OVX (oil vol)"),
        ("RVXCLS", "RVX (small-cap vol)"),
    ):
        v = await _latest_fred(session, series_id)
        if v is None:
            lines.append(f"- {label}: n/a (FRED:{series_id})")
            continue
        val, when = v
        lines.append(
            f"- {label} = {val:.2f} (FRED:{series_id}, {when:%Y-%m-%d})"
        )
        sources.append(f"FRED:{series_id}")

    return "\n".join(lines), sources


async def _section_treasury_tic(session: AsyncSession) -> tuple[str, list[str]]:
    """## Treasury TIC — top foreign holders + 12-month trend per major.

    Macro-broad section reading treasury_tic_holdings (Wave 32 collector).
    Surfaces:
      - Top 10 foreign holders at the latest reporting period
      - 3y trend for the 5 largest holders (Japan / China / UK / Belgium /
        Canada) — China decline is the canonical Stephen Jen "broken
        smile" signal of foreign repatriation feeding USD-as-source-of-
        instability regime.

    Cadence : monthly with ~6-week lag. Pass 1 reads for régime, Pass 2
    cites for mechanisms (foreign demand / repatriation).
    """
    # Latest period
    latest_month_row = (
        await session.execute(
            select(TreasuryTicHolding.observation_month)
            .order_by(desc(TreasuryTicHolding.observation_month))
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest_month_row is None:
        return ("## Treasury TIC (foreign holders)\n- n/a (collector empty)", [])

    # Top 10 holders at latest period (skip Grand Total + All Other roll-ups)
    rows = list(
        (
            await session.execute(
                select(TreasuryTicHolding)
                .where(TreasuryTicHolding.observation_month == latest_month_row)
                .order_by(desc(TreasuryTicHolding.holdings_bn_usd))
            )
        )
        .scalars()
        .all()
    )
    sources = [f"TIC:MFH@{latest_month_row.isoformat()}"]
    lines = [f"## Treasury TIC (foreign holders, {latest_month_row:%b %Y})"]

    grand_total = next((r for r in rows if "Grand Total" in r.country), None)
    if grand_total is not None:
        lines.append(
            f"- Grand Total foreign-held = ${grand_total.holdings_bn_usd:,.1f} bn"
        )
    country_rows = [
        r for r in rows
        if r.country not in {"Grand Total", "All Other", "For. Official"}
        and not r.country.startswith(" ")
    ]
    lines.append("### Top 10 holders")
    for r in country_rows[:10]:
        lines.append(f"- {r.country:30s}  ${r.holdings_bn_usd:>8.1f} bn")

    # 3y trend (current vs 36 months earlier) for top 5
    top5 = [r.country for r in country_rows[:5]]
    trend_lines: list[str] = []
    for country in top5:
        hist = list(
            (
                await session.execute(
                    select(TreasuryTicHolding)
                    .where(TreasuryTicHolding.country == country)
                    .order_by(desc(TreasuryTicHolding.observation_month))
                    .limit(36)
                )
            )
            .scalars()
            .all()
        )
        if len(hist) < 24:
            continue  # need at least 24 months for a meaningful 3y compare
        cur = hist[0]
        old = hist[-1]
        delta = cur.holdings_bn_usd - old.holdings_bn_usd
        pct = (delta / old.holdings_bn_usd * 100) if old.holdings_bn_usd else 0
        arrow = "↓" if delta < 0 else ("↑" if delta > 0 else "→")
        trend_lines.append(
            f"- {country:25s} {old.observation_month:%b%y} ${old.holdings_bn_usd:.0f}b "
            f"{arrow} {cur.observation_month:%b%y} ${cur.holdings_bn_usd:.0f}b "
            f"(Δ ${delta:+.0f}b, {pct:+.1f}%)"
        )
    if trend_lines:
        lines.append("### 3y trend top-5")
        lines.extend(trend_lines)

    return "\n".join(lines), sources


async def _section_tff_positioning(
    session: AsyncSession, asset: str
) -> tuple[str, list[str]]:
    """## TFF positioning — latest CFTC TFF 4-class breakdown for the asset.

    Surfaces the smart-money divergence signal (LevFunds vs AssetMgr)
    + dealer absorbing inventory. Per-asset, weekly cadence. Skip if the
    asset is not in the TFF tracked-market whitelist.
    """
    market = _TFF_MARKET_BY_ASSET.get(asset)
    if market is None:
        return "", []
    stmt = (
        select(CftcTffObservation)
        .where(CftcTffObservation.market_code == market)
        .order_by(desc(CftcTffObservation.report_date))
        .limit(2)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    if not rows:
        return f"## TFF positioning ({asset}, market={market})\n- n/a", []
    cur = rows[0]
    prev = rows[1] if len(rows) > 1 else None

    dealer_net = cur.dealer_long - cur.dealer_short
    am_net = cur.asset_mgr_long - cur.asset_mgr_short
    lev_net = cur.lev_money_long - cur.lev_money_short
    other_net = cur.other_rept_long - cur.other_rept_short

    if prev is not None:
        dealer_dw = (prev.dealer_long - prev.dealer_short) - dealer_net
        # Trader convention: Δw/w in the OWN direction (positive = longer this week)
        dealer_dw = -dealer_dw
        am_dw = am_net - (prev.asset_mgr_long - prev.asset_mgr_short)
        lev_dw = lev_net - (prev.lev_money_long - prev.lev_money_short)
        delta_str = (
            f", Δw/w (Dealer {dealer_dw:+,}, AM {am_dw:+,}, LevFunds {lev_dw:+,})"
        )
    else:
        delta_str = ""

    # Smart-money divergence flag : LevFunds and AssetMgr on opposite sides.
    divergence = ""
    if lev_net != 0 and am_net != 0 and (lev_net > 0) != (am_net > 0):
        divergence = (
            "\n- ⚠ smart-money divergence: LevFunds and AssetMgr opposite sides"
        )

    sources = [f"CFTC:TFF:{market}@{cur.report_date.isoformat()}"]
    md = (
        f"## TFF positioning ({asset}, market={market})\n"
        f"- Dealer net = {dealer_net:+,}, AssetMgr net = {am_net:+,}, "
        f"LevFunds net = {lev_net:+,}, Other net = {other_net:+,} "
        f"(open_interest={cur.open_interest:,}, report_date={cur.report_date:%Y-%m-%d})"
        f"{delta_str}{divergence}"
    )
    return md, sources


async def _section_cot(session: AsyncSession, asset: str) -> tuple[str, list[str]]:
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
    cutoff = datetime.now(UTC) - timedelta(hours=12)
    sources: list[str] = []
    sections: list[str] = ["## Prediction markets (last 12h, top 5 per venue)"]

    # Polymarket — wave 33: dedup per slug (latest snapshot only) +
    # rank by volume_usd DESC. With wave 31 top-100 macro discovery,
    # we now have 80+ markets in flight; surface the top 15 by volume.
    poly_raw = list(
        (
            await session.execute(
                select(PolymarketSnapshot)
                .where(PolymarketSnapshot.fetched_at >= cutoff)
                .order_by(desc(PolymarketSnapshot.fetched_at))
                .limit(500)
            )
        )
        .scalars()
        .all()
    )
    # Latest snapshot per slug
    seen_slugs: set[str] = set()
    poly_unique: list[PolymarketSnapshot] = []
    for r in poly_raw:
        if r.slug in seen_slugs:
            continue
        seen_slugs.add(r.slug)
        poly_unique.append(r)
    # Rank by volume desc, top 15
    poly_unique.sort(key=lambda x: -(x.volume_usd or 0))
    poly_top = poly_unique[:15]

    sections.append(f"### Polymarket (top 15 by 24h volume, of {len(poly_unique)} fresh)")
    if not poly_top:
        sections.append("- (no fresh snapshots)")
    else:
        for r in poly_top:
            yes = r.last_prices[0] if (r.last_prices and len(r.last_prices) > 0) else None
            yes_str = f"YES={yes:.2f}" if yes is not None else "YES=n/a"
            vol_str = f"${(r.volume_usd or 0) / 1e6:.1f}M" if r.volume_usd else "$?"
            sections.append(
                f"- {r.question[:80]} → {yes_str} vol={vol_str} (slug:{r.slug})"
            )
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
        )
        .scalars()
        .all()
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
        )
        .scalars()
        .all()
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

    gpr_stmt = select(GprObservation).order_by(desc(GprObservation.observation_date)).limit(1)
    gpr = (await session.execute(gpr_stmt)).scalars().first()
    if gpr is not None:
        lines.append(
            f"- AI-GPR = {gpr.ai_gpr:.1f} "
            f"(Iacoviello, observation_date={gpr.observation_date:%Y-%m-%d})"
        )
        sources.append(f"AI-GPR@{gpr.observation_date.isoformat()}")
    else:
        lines.append("- AI-GPR: n/a")

    cutoff = datetime.now(UTC) - timedelta(hours=24)
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
    cutoff = datetime.now(UTC) - timedelta(days=7)
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


async def _section_microstructure(session: AsyncSession, asset: str) -> tuple[str, list[str]]:
    """## Microstructure — Amihud / Kyle / RV / VWAP / value-area."""
    reading = await assess_microstructure(session, asset, window_minutes=240)
    return render_microstructure_block(reading)


async def _section_asian_session(session: AsyncSession, asset: str) -> tuple[str, list[str]]:
    """## Asian session — Tokyo fix + range + direction (JPY-relevant only).

    Returns ("", []) for pairs not routed through the Asian session.
    """
    if asset not in asian_supported_pairs():
        return "", []
    reading = await assess_asian_session(session, asset)
    return render_asian_session_block(reading)


async def _section_funding_stress(session: AsyncSession) -> tuple[str, list[str]]:
    """## Funding stress — SOFR-IORB / SOFR-EFFR / RRP / HY OAS composite."""
    reading = await assess_funding_stress(session)
    return render_funding_stress_block(reading)


async def _section_surprise_index(session: AsyncSession) -> tuple[str, list[str]]:
    """## Eco Surprise Index — z-score proxy on FRED macro hard data."""
    reading = await assess_surprise_index(session)
    return render_surprise_index_block(reading)


async def _section_narrative(session: AsyncSession) -> tuple[str, list[str]]:
    """## Narrative tracker — top keywords from cb_speeches + news 48h."""
    report = await track_narratives(session, window_hours=48, top_k=10)
    return render_narrative_block(report)


async def _section_cb_intervention(session: AsyncSession, asset: str) -> tuple[str, list[str]]:
    """## CB intervention risk — empirical model on the asset's spot.

    Returns "" if the pair has no documented intervention history
    (most G10 crosses fall here).
    """
    if asset not in cb_intervention_svc.supported_pairs():
        return "", []
    # Pull the last bar to know the spot
    stmt = (
        select(PolygonIntradayBar)
        .where(PolygonIntradayBar.asset == asset)
        .order_by(desc(PolygonIntradayBar.bar_ts))
        .limit(1)
    )
    last = (await session.execute(stmt)).scalars().first()
    if last is None:
        return "", []
    risk = cb_intervention_svc.assess(asset, float(last.close))
    if risk is None:
        return "", []
    return cb_intervention_svc.render_intervention_block(risk)


async def _section_daily_levels(
    session: AsyncSession, asset: str
) -> tuple[str, list[str], DailyLevels]:
    """## Daily levels — PDH/PDL, Asian range, Pivots, round numbers.

    Returns the rendered markdown plus the underlying DailyLevels object
    so a downstream section (session_scenarios) can reuse it without
    re-querying.
    """
    levels = await assess_daily_levels(session, asset)
    md, sources = render_daily_levels_block(levels)
    return md, sources, levels


async def _section_confluence(
    session: AsyncSession, asset: str, levels_obj: DailyLevels
) -> tuple[str, list[str]]:
    """## Confluence engine — multi-factor synthesis."""
    report = await assess_confluence(session, asset, levels=levels_obj)
    return render_confluence_block(report)


async def _section_currency_strength(
    session: AsyncSession,
) -> tuple[str, list[str]]:
    """## Currency strength meter — 24h ranked basket."""
    report = await assess_currency_strength(session, window_hours=24.0)
    return render_currency_strength_block(report)


async def _section_yield_curve(
    session: AsyncSession,
) -> tuple[str, list[str]]:
    """## US Treasury yield curve — full term structure."""
    reading = await assess_yield_curve(session)
    return render_yield_curve_block(reading)


async def _section_calendar(session: AsyncSession, asset: str) -> tuple[str, list[str]]:
    """## Economic calendar — next 14 days affecting `asset`."""
    report = await assess_calendar(session, horizon_days=14)
    return render_calendar_block(report, asset=asset, max_items=10)


async def _section_correlations(
    session: AsyncSession,
) -> tuple[str, list[str]]:
    """## Cross-asset correlation matrix — rolling 30d hourly returns."""
    m = await assess_correlations(session, window_days=30)
    return render_correlations_block(m)


async def _section_vix_term(
    session: AsyncSession,
) -> tuple[str, list[str]]:
    """## VIX term structure — contango / backwardation."""
    r = await assess_vix_term(session)
    return render_vix_term_block(r)


async def _section_risk_appetite(
    session: AsyncSession,
) -> tuple[str, list[str]]:
    """## Risk appetite composite — VIX + OAS + curve + UMCSENT."""
    r = await assess_risk_appetite(session)
    return render_risk_appetite_block(r)


async def _section_polymarket_impact(
    session: AsyncSession,
) -> tuple[str, list[str]]:
    """## Polymarket themed clusters → directional impact per asset."""
    r = await assess_polymarket_impact(session, hours=24, limit=200)
    return render_polymarket_impact_block(r)


async def _section_portfolio_exposure(
    session: AsyncSession,
) -> tuple[str, list[str]]:
    """## Portfolio exposure — net basket aggregate."""
    r = await assess_portfolio_exposure(session, max_age_hours=24)
    return render_portfolio_exposure_block(r)


async def _section_hourly_vol(session: AsyncSession, asset: str) -> tuple[str, list[str]]:
    """## Hourly volatility heatmap — when this asset moves."""
    r = await assess_hourly_volatility(session, asset, window_days=30)
    return render_hourly_volatility_block(r)


async def _section_session_scenarios(
    levels_obj: DailyLevels,
    *,
    session_type: SessionType,
    regime: RegimeQuadrant | None,
    conviction_pct: float,
) -> tuple[str, list[str]]:
    """## Session scenarios — Continuation/Reversal/Sideways probabilities.

    Reuses the DailyLevels already loaded by `_section_daily_levels`.
    """
    s = assess_session_scenarios(
        levels_obj,
        session_type=session_type,
        regime=regime,
        conviction_pct=conviction_pct,
    )
    return render_session_scenarios_block(s)


# Asset → keyword set for news ticker filtering.
# Phase 2 fix for SPEC.md §2.2 #10 (polygon_news non filtré ticker-linked).
# Heuristic until news_items.tickers ARRAY column lands (follow-up migration).
_NEWS_KEYWORDS: dict[str, tuple[str, ...]] = {
    "EUR_USD": ("EUR/USD", "EURUSD", "EUR ", "euro", "ECB", "Lagarde", "eurozone"),
    "GBP_USD": ("GBP/USD", "GBPUSD", "GBP ", "pound sterling", "BoE", "Bailey", "UK economy"),
    "USD_JPY": ("USD/JPY", "USDJPY", "JPY ", "yen", "BoJ", "Ueda", "Japan inflation"),
    "AUD_USD": ("AUD/USD", "AUDUSD", "AUD ", "Aussie", "RBA", "iron ore", "Australia"),
    "USD_CAD": ("USD/CAD", "USDCAD", "CAD ", "loonie", "BoC", "Macklem", "Canadian"),
    "XAU_USD": ("XAU/USD", "XAUUSD", "gold", "bullion", "GLD ", "GDX ", "spot metals"),
    "NAS100_USD": (
        "NAS100",
        "Nasdaq",
        "NASDAQ",
        "QQQ",
        "AAPL",
        "MSFT",
        "GOOGL",
        "AMZN",
        "META",
        "NVDA",
        "TSLA",
        "tech stocks",
    ),
    "SPX500_USD": ("S&P 500", "SPX", "SPY", "S&P500", "broad market", "Fed funds"),
    "US30_USD": ("Dow Jones", "DJIA", "DIA"),
}


def _matches_asset(title: str, url: str, asset: str) -> bool:
    """Heuristic ticker-link: keyword match in title (case-insensitive)
    or in URL path. Returns True if no keywords are configured (fallback)."""
    keys = _NEWS_KEYWORDS.get(asset.upper())
    if not keys:
        return True  # unknown asset: keep all
    blob = f"{title} {url}".lower()
    return any(k.lower() in blob for k in keys)


async def _section_news(
    session: AsyncSession,
    asset: str | None = None,
) -> tuple[str, list[str]]:
    """## News — top 8 most-recent items in last 12h, ticker-filtered.

    When `asset` is set, items are filtered by keyword match against the
    asset's ticker / institutional terms (cf `_NEWS_KEYWORDS`). If too
    few items match, falls back to the unfiltered top-8 with a label.
    """
    cutoff = datetime.now(UTC) - timedelta(hours=12)
    # Pull a wider candidate set (50) so the post-filter still has options.
    stmt = (
        select(NewsItem)
        .where(NewsItem.published_at >= cutoff)
        .order_by(desc(NewsItem.published_at))
        .limit(50)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    if not rows:
        return "## News (last 12h)\n- (no items ingested)", []

    filtered: list[NewsItem]
    if asset:
        filtered = [r for r in rows if _matches_asset(r.title or "", r.url or "", asset)]
        if len(filtered) < 3:
            # Not enough asset-specific news → fallback to wide.
            filtered = rows
            label = f"## News (last 12h, top 8 — wide fallback, {asset} match scarce)"
        else:
            filtered = filtered[:8]
            label = f"## News (last 12h, top {len(filtered)} ticker-linked to {asset})"
    else:
        filtered = rows[:8]
        label = "## News (last 12h, top 8 most recent)"

    lines = [label]
    sources: list[str] = []
    for r in filtered:
        lines.append(f"- {r.published_at:%Y-%m-%d %H:%M} {r.source} · {r.title[:90]} {r.url}")
        sources.append(r.url)
    return "\n".join(lines), sources


# ────────────────────────── Orchestrator ──────────────────────────────


async def build_data_pool(
    session: AsyncSession,
    asset: str,
    *,
    session_type: SessionType | None = None,
    regime: RegimeQuadrant | None = None,
    conviction_pct: float = 50.0,
) -> DataPool:
    """Compose the full data pool markdown for one asset.

    Sections are ordered from "biggest macro context" → "asset-specific"
    so the Pass-1 régime call (which only sees the macro trinity + dollar
    smile + geopolitics) gets clean signal at the top, and Pass-2
    (which sees the full pool) gets the asset-specific blocks at the
    bottom.

    Optional kwargs (`session_type`, `regime`, `conviction_pct`) tune the
    `session_scenarios` preview. When `session_type` is None, that
    section is skipped (caller is in a context where the session window
    isn't known yet, e.g. ad-hoc /v1/data-pool inspection).
    """
    asset = asset.upper()
    sections: list[tuple[str, str, list[str]]] = []

    macro_md, macro_src = await _section_macro_trinity(session)
    sections.append(("macro_trinity", macro_md, macro_src))

    smile_md, smile_src = await _section_dollar_smile(session)
    sections.append(("dollar_smile", smile_md, smile_src))

    vix_md, vix_src = await _section_vix_term(session)
    sections.append(("vix_term", vix_md, vix_src))

    ra_md, ra_src = await _section_risk_appetite(session)
    sections.append(("risk_appetite", ra_md, ra_src))

    # Wave 26 Phase II — surface CBOE SKEW (tail risk regime) into the
    # macro-broad block, alongside vix_term + risk_appetite. Pass 1 reads
    # this for régime classification (panic vs complacent), Pass 2 for
    # dollar-smile-break detection.
    skew_md, skew_src = await _section_tail_risk_skew(session)
    sections.append(("tail_risk", skew_md, skew_src))

    # Wave 33 — Treasury TIC foreign holdings monthly (12-month view).
    # Pass 1 régime + Pass 2 mechanism citation for foreign demand /
    # repatriation narrative.
    tic_md, tic_src = await _section_treasury_tic(session)
    sections.append(("treasury_tic", tic_md, tic_src))

    yc_md, yc_src = await _section_yield_curve(session)
    sections.append(("yield_curve", yc_md, yc_src))

    cs_md, cs_src = await _section_currency_strength(session)
    sections.append(("currency_strength", cs_md, cs_src))

    corr_md, corr_src = await _section_correlations(session)
    sections.append(("correlations", corr_md, corr_src))

    cal_md, cal_src = await _section_calendar(session, asset)
    sections.append(("calendar", cal_md, cal_src))

    diff_md, diff_src = await _section_rate_diff(session, asset)
    if diff_md:
        sections.append(("rate_diff", diff_md, diff_src))

    poly_md, poly_src = await _section_polygon_intraday(session, asset)
    sections.append(("polygon_intraday", poly_md, poly_src))

    # Daily levels first (it loads the DailyLevels object) so session
    # scenarios + confluence can reuse it without a second DB roundtrip.
    daily_md, daily_src, daily_obj = await _section_daily_levels(session, asset)
    sections.append(("daily_levels", daily_md, daily_src))

    conf_md, conf_src = await _section_confluence(session, asset, daily_obj)
    sections.append(("confluence", conf_md, conf_src))

    if session_type is not None:
        scen_md, scen_src = await _section_session_scenarios(
            daily_obj,
            session_type=session_type,
            regime=regime,
            conviction_pct=conviction_pct,
        )
        sections.append(("session_scenarios", scen_md, scen_src))

    hv_md, hv_src = await _section_hourly_vol(session, asset)
    sections.append(("hourly_volatility", hv_md, hv_src))

    micro_md, micro_src = await _section_microstructure(session, asset)
    sections.append(("microstructure", micro_md, micro_src))

    asian_md, asian_src = await _section_asian_session(session, asset)
    if asian_md:
        sections.append(("asian_session", asian_md, asian_src))

    cot_md, cot_src = await _section_cot(session, asset)
    if cot_md:
        sections.append(("cot", cot_md, cot_src))

    # Wave 26 Phase II — surface CFTC TFF 4-class positioning per asset.
    # Asset-conditional via _TFF_MARKET_BY_ASSET (skip if unmapped). Sister
    # to _section_cot (Disaggregated) but TFF is the financial-futures-only
    # report with the AssetMgr / LevFunds split that COT lacks.
    tff_md, tff_src = await _section_tff_positioning(session, asset)
    if tff_md:
        sections.append(("tff_positioning", tff_md, tff_src))

    pm_md, pm_src = await _section_prediction_markets(session)
    sections.append(("prediction_markets", pm_md, pm_src))

    pmi_md, pmi_src = await _section_polymarket_impact(session)
    sections.append(("polymarket_impact", pmi_md, pmi_src))

    pe_md, pe_src = await _section_portfolio_exposure(session)
    sections.append(("portfolio_exposure", pe_md, pe_src))

    fs_md, fs_src = await _section_funding_stress(session)
    sections.append(("funding_stress", fs_md, fs_src))

    si_md, si_src = await _section_surprise_index(session)
    sections.append(("surprise_index", si_md, si_src))

    nar_md, nar_src = await _section_narrative(session)
    sections.append(("narrative", nar_md, nar_src))

    cbi_md, cbi_src = await _section_cb_intervention(session, asset)
    if cbi_md:
        sections.append(("cb_intervention", cbi_md, cbi_src))

    geo_md, geo_src = await _section_geopolitics(session)
    sections.append(("geopolitics", geo_md, geo_src))

    cb_md, cb_src = await _section_cb_speeches(session)
    sections.append(("cb_speeches", cb_md, cb_src))

    # Phase 2 — Couche-2 agents output (CB-NLP, News-NLP, Sentiment, Positioning)
    c2_md, c2_src = await render_couche2_block(session)
    sections.append(("couche2", c2_md, c2_src))

    # Phase 2 — divergence cross-venue (Polymarket vs Kalshi vs Manifold)
    div_md, div_src = await render_divergence_block(session)
    sections.append(("divergence", div_md, div_src))

    # Phase 2 — Dealer GEX (only emits when asset has options coverage)
    gex_md, gex_src = await render_gex_block(session, asset)
    if gex_md:
        sections.append(("gex", gex_md, gex_src))

    # Phase 2 — historical analogues via DTW on Stooq daily bars
    ana_md, ana_src = await render_analogues_block(session, asset)
    sections.append(("analogues", ana_md, ana_src))

    # Phase 2 — ML signals adapter (8 scaffolded models, status-aware)
    ml_md, ml_src = await render_ml_signals_block(session, asset)
    sections.append(("ml_signals", ml_md, ml_src))

    # Phase 2 — news now ticker-filtered
    news_md, news_src = await _section_news(session, asset)
    sections.append(("news", news_md, news_src))

    body = "\n\n".join(md for _, md, _ in sections)
    all_sources: list[str] = []
    for _, _, srcs in sections:
        all_sources.extend(srcs)
    sections_emitted = [name for name, _, _ in sections]

    now = datetime.now(UTC)
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
