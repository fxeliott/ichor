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
    BundYieldObservation,
    CboeSkewObservation,
    CboeVvixObservation,
    CbSpeech,
    CftcTffObservation,
    ClevelandFedNowcast,
    CotPosition,
    EstrObservation,
    FredObservation,
    GdeltEvent,
    GprObservation,
    KalshiMarket,
    ManifoldMarket,
    MyfxbookOutlook,
    NewsItem,
    NfibSbetObservation,
    NyfedMctObservation,
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
from .regime_classifier import RegimeInputs, classify_master_regime
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
# Round-27 ADR-089 (PROPOSED) : SPX500_USD aliased to SPY (NYSE Arca
# ETF, $0 incremental cost) until Polygon Indices Starter $49/mo is
# budgeted. Tracking error <0.1% MTD invisible for qualitative Pass-2.
_ASSET_TO_POLYGON: dict[str, str] = {
    "EUR_USD": "C:EURUSD",
    "GBP_USD": "C:GBPUSD",
    "USD_JPY": "C:USDJPY",
    "AUD_USD": "C:AUDUSD",
    "USD_CAD": "C:USDCAD",
    "XAU_USD": "C:XAUUSD",
    "NAS100_USD": "I:NDX",
    "SPX500_USD": "SPY",  # was "I:SPX" — ADR-089 SPY proxy
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


# Per-series max-age-days registry — round-37 r35-audit-gap closure.
# FRED series have different publication cadences (daily / weekly /
# monthly / quarterly). The default 14-day max-age was calibrated for
# DAILY series and silently rejected MONTHLY OECD observations (e.g.
# IRLTLT01ITM156N which is ~100 days old at read time per r35
# empirical discovery). The registry below maps each series_id to its
# appropriate max-age ceiling. Adding a new monthly/quarterly series
# WITHOUT a registry entry will fall back to the conservative default
# AND log a structlog warning so the operator notices.
_FRED_SERIES_MAX_AGE_DAYS: dict[str, int] = {
    # ─── MONTHLY OECD / FRED series (1-month publication lag standard) ───
    "IRLTLT01DEM156N": 120,  # Germany 10y monthly (legacy, replaced by Bund daily r29 but kept for fallback)
    "IRLTLT01ITM156N": 120,  # Italy 10y monthly (BTP-Bund spread, ADR-090 step-4 r34+r35)
    "IRLTLT01JPM156N": 120,  # Japan 10y monthly
    "IRLTLT01GBM156N": 120,  # UK 10y monthly
    "USALOLITOAASTSAM": 120,  # US CLI monthly
    "G7LOLITOAASTSAM": 120,  # G7 aggregate CLI
    "JPNLOLITOAASTSAM": 120,
    "DEULOLITOAASTSAM": 120,
    "GBRLOLITOAASTSAM": 120,
    "CHNLOLITOAASTSAM": 120,
    "EA19LOLITOAASTSAM": 120,
    "UMCSENT": 60,  # U Michigan Consumer Sentiment monthly (preliminary mid-month + final end-of-month)
    "CSCICP03USM665S": 90,  # OECD Consumer Confidence monthly
    "DRTSCILM": 120,  # Senior Loan Officer Survey quarterly
    "USREC": 365,  # NBER Recession Indicator (typically updated at recession turning points only)
    "CIVPART": 45,  # Labor Force Participation monthly
    "AHETPI": 45,  # Average Hourly Earnings monthly
    "ATLSBUSRGEP": 60,  # Atlanta Fed Business Inflation Expectations
    "PSAVERT": 45,  # Personal Saving Rate monthly
    "FEDFUNDS": 45,  # Fed Funds monthly average
    "EXPINF1YR": 60,  # Cleveland Fed expected inflation monthly
    "M2SL": 45,  # M2 monthly
    "WSHOSHO": 30,  # Fed H.4.1 Treasuries weekly
    "WSHOMCB": 30,  # Fed H.4.1 MBS weekly
    "WRESBAL": 30,  # Fed reserve balances weekly
    "GDPC1": 120,  # Real GDP quarterly
    "INDPRO": 45,  # Industrial Production monthly
    "MCUMFN": 45,  # Manufacturing Capacity Utilization monthly
    "CFNAI": 45,  # Chicago Fed National Activity Index monthly
    "CFNAIDIFF": 45,
    "DFEDTARU": 45,  # Fed Funds Target Range Upper (announcement-driven)
    "DFEDTARL": 45,
    "GDPNOW": 14,  # Atlanta Fed GDP nowcast (updated 6-7x/month, but 14d is conservative)
    "PCENOW": 14,
}

# Conservative default for any FRED series NOT in the registry above.
# Suits DAILY series (DGS10, DXY, VIXCLS, etc.). Monthly/quarterly
# series MUST be added to the registry — falling back to 14 silently
# would reintroduce the r35 bug class.
_FRED_DEFAULT_MAX_AGE_DAYS: int = 14


def _max_age_days_for(series_id: str, override: int | None = None) -> int:
    """Resolve max-age-days for a FRED series.

    Order of precedence :
      1. Explicit `override` kwarg (caller knows best — e.g. force a
         very wide window for cold-start backfill diagnostics).
      2. Per-series registry `_FRED_SERIES_MAX_AGE_DAYS`.
      3. Conservative default 14 days (DAILY-series calibrated).
    """
    if override is not None:
        return override
    return _FRED_SERIES_MAX_AGE_DAYS.get(series_id, _FRED_DEFAULT_MAX_AGE_DAYS)


async def _latest_fred(
    session: AsyncSession, series_id: str, max_age_days: int | None = None
) -> tuple[float, datetime] | None:
    """Latest observation for `series_id`, respecting per-series-frequency
    max-age-days from the registry above.

    Round-37 refactor (r35-audit-gap closure) :
      - `max_age_days` is now Optional ; if None, looks up the
        per-series registry, falls back to 14d default for unknown
        series.
      - Backward-compat : callers passing explicit `max_age_days=N`
        keep working — the override wins (precedence rule 1 in
        `_max_age_days_for`).
    """
    resolved_max_age = _max_age_days_for(series_id, override=max_age_days)
    cutoff = datetime.now(UTC).date() - timedelta(days=resolved_max_age)
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


async def _section_executive_summary(session: AsyncSession) -> tuple[str, list[str]]:
    """## Executive summary (Waves 50+51) — regime label + 5-bullet synthesis at top.

    Wave 51 adds a master regime classifier as bullet 0:
      - crisis        : VIX panic / SKEW > 150 / HY-OAS spike (flight to quality)
      - broken_smile  : DXY weak + term premium up + VIX modest + HY calm
                        (Stephen Jen US-driven instability)
      - stagflation   : US CLI < 100 + EXPINF1YR > 2.5 + jobless rising
      - risk_off      : VIX elevated + HY-OAS elevated (classic LEFT smile)
      - goldilocks    : US CLI > 100 + NFCI loose + EXPINF1YR near target
      - risk_on       : NFCI < 0 + SKEW low + VIX low
      - transitional  : doesn't match clear regime template

    Wave 50 5-bullet synthesis follows for detail.
    """
    sources: list[str] = []
    lines: list[str] = ["## Executive summary"]

    # ── 0. Master regime classifier (Wave 51) ──
    # Pull snapshot of canonical signals; bucket into 7-regime taxonomy.
    skew_latest_row = (
        (
            await session.execute(
                select(CboeSkewObservation)
                .order_by(desc(CboeSkewObservation.observation_date))
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    vix_v = await _latest_fred(session, "VIXCLS", max_age_days=7)
    hy_oas_v = await _latest_fred(session, "BAMLH0A0HYM2", max_age_days=14)
    nfci_v = await _latest_fred(session, "NFCI", max_age_days=14)
    cli_us_v = await _latest_fred(session, "USALOLITOAASTSAM", max_age_days=90)
    expinf_v = await _latest_fred(session, "EXPINF1YR", max_age_days=45)
    term_v = await _latest_fred(session, "THREEFYTP10", max_age_days=30)

    skew = skew_latest_row.skew_value if skew_latest_row else None
    vix = vix_v[0] if vix_v else None
    hy_oas = hy_oas_v[0] if hy_oas_v else None
    nfci = nfci_v[0] if nfci_v else None
    cli_us = cli_us_v[0] if cli_us_v else None
    expinf = expinf_v[0] if expinf_v else None
    term_prem = term_v[0] if term_v else None

    # Wave 51 master regime classifier — extracted W104c into pure service
    # `services.regime_classifier.classify_master_regime` for reuse +
    # unit-testability. Logic + thresholds unchanged ; %% normalised to %
    # in rationale strings (cosmetic, was inconsistent crisis vs others).
    classification = classify_master_regime(
        RegimeInputs(
            skew=skew,
            vix=vix,
            hy_oas=hy_oas,
            nfci=nfci,
            cli_us=cli_us,
            expinf=expinf,
            term_prem=term_prem,
        )
    )
    regime = classification.regime
    lines.append(
        f"- 🎯 **REGIME : {regime.upper().replace('_', ' ')}** — {classification.rationale}"
    )
    lines.append(
        f"  └─ confidence ≈ {classification.confidence:.2f} (heuristic margin vs threshold)"
    )
    if classification.bias_hints:
        bias_md = " | ".join(f"{k}: {v}" for k, v in classification.bias_hints.items())
        lines.append(f"  └─ asset-class bias hints (ADR-017 priming, not signals): {bias_md}")

    # ── 1. Macro régime ──
    g7 = await _latest_fred(session, "G7LOLITOAASTSAM", max_age_days=90)
    chn = await _latest_fred(session, "CHNLOLITOAASTSAM", max_age_days=90)
    nfci = await _latest_fred(session, "NFCI", max_age_days=14)
    macro_pieces: list[str] = []
    if g7 and chn:
        if g7[0] >= 100 and chn[0] < 100:
            macro_pieces.append(
                f"OECD G7 {g7[0]:.2f}▲ vs China {chn[0]:.2f}▼ = ⚠ China divergence "
                "(bearish AUD/CAD copper)"
            )
            sources.extend(["FRED:G7LOLITOAASTSAM", "FRED:CHNLOLITOAASTSAM"])
        elif g7[0] >= 100 and chn[0] >= 100:
            macro_pieces.append(
                f"OECD G7 {g7[0]:.2f}▲ + China {chn[0]:.2f}▲ = synchronized expansion"
            )
            sources.extend(["FRED:G7LOLITOAASTSAM", "FRED:CHNLOLITOAASTSAM"])
        elif g7[0] < 100 and chn[0] < 100:
            macro_pieces.append(f"OECD G7 {g7[0]:.2f}▼ + China {chn[0]:.2f}▼ = global slowdown")
            sources.extend(["FRED:G7LOLITOAASTSAM", "FRED:CHNLOLITOAASTSAM"])
    if nfci:
        flag = "TIGHTER" if nfci[0] > 0 else "looser-than-avg"
        macro_pieces.append(f"NFCI {nfci[0]:+.2f} ({flag})")
        sources.append("FRED:NFCI")
    if macro_pieces:
        lines.append(f"- 📊 Macro régime : {' · '.join(macro_pieces)}")

    # ── 2. Vol surface ──
    skew_stmt = (
        select(CboeSkewObservation).order_by(desc(CboeSkewObservation.observation_date)).limit(1)
    )
    skew_row = (await session.execute(skew_stmt)).scalars().first()
    vvix_stmt = (
        select(CboeVvixObservation).order_by(desc(CboeVvixObservation.observation_date)).limit(1)
    )
    vvix_row = (await session.execute(vvix_stmt)).scalars().first()
    vol_pieces: list[str] = []
    if skew_row:
        band = (
            "PANIC>150"
            if skew_row.skew_value >= 150
            else "elevated 130-150"
            if skew_row.skew_value >= 130
            else "modest 115-130"
            if skew_row.skew_value >= 115
            else "neutral <115"
        )
        vol_pieces.append(f"SKEW {skew_row.skew_value:.0f} ({band})")
        sources.append(f"CBOE:SKEW@{skew_row.observation_date.isoformat()}")
    if vvix_row:
        v_band = (
            "BLOWUP>140"
            if vvix_row.vvix_value >= 140
            else "elevated >100"
            if vvix_row.vvix_value >= 100
            else "modest 85-100"
            if vvix_row.vvix_value >= 85
            else "calm <85"
        )
        vol_pieces.append(f"VVIX {vvix_row.vvix_value:.0f} ({v_band})")
        sources.append(f"CBOE:VVIX@{vvix_row.observation_date.isoformat()}")
    if vol_pieces:
        lines.append(f"- 🌋 Vol surface : {' · '.join(vol_pieces)}")

    # ── 3. Smart-money positioning (TFF divergence count across assets) ──
    # Latest report_date
    latest_tff_dt = (
        await session.execute(
            select(CftcTffObservation.report_date)
            .order_by(desc(CftcTffObservation.report_date))
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest_tff_dt is not None:
        tff_rows = list(
            (
                await session.execute(
                    select(CftcTffObservation).where(
                        CftcTffObservation.report_date == latest_tff_dt
                    )
                )
            )
            .scalars()
            .all()
        )
        divergent: list[str] = []
        for r in tff_rows:
            am_net = r.asset_mgr_long - r.asset_mgr_short
            lev_net = r.lev_money_long - r.lev_money_short
            if am_net != 0 and lev_net != 0 and (am_net > 0) != (lev_net > 0):
                divergent.append(r.market_code)
        if divergent:
            lines.append(
                f"- 💰 Smart-money divergence : {len(divergent)}/{len(tff_rows)} markets "
                f"({', '.join(divergent[:5])}{'...' if len(divergent) > 5 else ''}, "
                f"week {latest_tff_dt:%Y-%m-%d})"
            )
            sources.append(f"CFTC:TFF:WEEK@{latest_tff_dt.isoformat()}")

    # ── 4. Foreign demand (TIC China trend) ──
    china_now = (
        (
            await session.execute(
                select(TreasuryTicHolding)
                .where(TreasuryTicHolding.country == "China, Mainland")
                .order_by(desc(TreasuryTicHolding.observation_month))
                .limit(36)
            )
        )
        .scalars()
        .all()
    )
    china_now_list = list(china_now)
    if len(china_now_list) >= 2:
        cur = china_now_list[0]
        old = china_now_list[-1]
        delta = cur.holdings_bn_usd - old.holdings_bn_usd
        pct = delta / old.holdings_bn_usd * 100 if old.holdings_bn_usd else 0
        arrow = "↓" if delta < 0 else "↑"
        lines.append(
            f"- 🌏 Foreign demand : China Treasury {arrow} ${delta:+.0f}b "
            f"({pct:+.1f}%) from ${old.holdings_bn_usd:.0f}b "
            f"({old.observation_month:%b%y}) to ${cur.holdings_bn_usd:.0f}b "
            f"({cur.observation_month:%b%y})"
        )
        sources.append(f"TIC:MFH:CHN@{cur.observation_month.isoformat()}")

    # ── 5. Forward Fed path (ZQ curve direction) ──
    front = await _latest_fred(session, "ZQ_FRONT_IMPLIED_EFFR", max_age_days=14)
    far = await _latest_fred(session, "ZQ_F27_IMPLIED_EFFR", max_age_days=14)
    if front and far:
        delta_bps = (far[0] - front[0]) * 100
        if delta_bps < -10:
            tone = f"DOVISH curve (front={front[0]:.2f}% → Jan27={far[0]:.2f}%, {delta_bps:+.0f}bp)"
        elif delta_bps > 10:
            tone = (
                f"HAWKISH curve (front={front[0]:.2f}% → Jan27={far[0]:.2f}%, {delta_bps:+.0f}bp)"
            )
        else:
            tone = f"FLAT curve (front={front[0]:.2f}% → Jan27={far[0]:.2f}%, {delta_bps:+.0f}bp = no net move)"
        lines.append(f"- 🏛️ Forward Fed : {tone}")
        sources.append("CME:ZQ_curve")

    return "\n".join(lines), sources


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


async def _section_eur_specific(session: AsyncSession, asset: str) -> tuple[str, list[str]]:
    """## EUR-specific signals — Bund 10Y + €STR + BTP-Bund spread (ADR-090 P0 step-3 + step-4).

    Renders the EUR-side macro signals for EUR_USD Pass-2 :
      1. **Bund 10Y daily** (long-end rate, German benchmark) — round-32 P0 step-3.
         Source : Bundesbank SDMX `BBSIS/D.I.ZAR.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A`.
      2. **€STR daily** (front-end EUR funding rate, ECB-published) — round-34 P0 step-4.
         Source : ECB Data Portal SDMX `EST/B.EU000A2X2A25.WT`.
      3. **BTP-Bund 10Y spread monthly** (peripheral fragmentation proxy, OECD via FRED) — round-34.
         Source : FRED `IRLTLT01ITM156N` (OECD Italy 10Y monthly) minus the same-day Bund.
         NB : BTP series is MONTHLY (1-month lag) — frequency mismatch with daily Bund.
         Surfaced as a regime indicator, not intraday signal.

    Gated on `asset == "EUR_USD"` — early-return ("", []) otherwise.
    `build_data_pool` appends only when `sources` is non-empty so a
    non-EUR asset (or empty Bund table pre-deploy) silently skips.

    SYMMETRIC LANGUAGE discipline (ichor-trader r32 review) :
    each signal emits BOTH interpretive branches (calm regime + funding
    stress) and lets the Pass-2 LLM pick consistent with Pass-1 regime.
    """
    if asset != "EUR_USD":
        return "", []

    # ─── Bund 10Y (round-32 P0 step-3) ─────────────────────────────
    bund_stmt = (
        select(BundYieldObservation.observation_date, BundYieldObservation.yield_pct)
        .order_by(desc(BundYieldObservation.observation_date))
        .limit(6)
    )
    bund_rows = (await session.execute(bund_stmt)).all()
    if not bund_rows:
        return "", []  # Bund collector dormant or pre-deploy — silent skip

    bund_latest_date, bund_latest_pct = bund_rows[0]
    bund_latest_f = float(bund_latest_pct)
    sources = [f"Bundesbank:BBSIS/Bund10Y@{bund_latest_date:%Y-%m-%d}"]

    lines = [
        "## EUR-specific signals",
        "### Bund 10Y yield",
        f"- Bund 10Y = {bund_latest_f:.3f}% (Bundesbank SDMX BBSIS, {bund_latest_date:%Y-%m-%d})",
    ]

    # 5-day delta + symmetric interpretation
    if len(bund_rows) >= 6:
        prior_date, prior_pct = bund_rows[5]
        delta_bp = (bund_latest_f - float(prior_pct)) * 100.0  # % → bp
        sign = "+" if delta_bp >= 0 else "−"
        lines.append(
            f"- 5-trading-day change : {sign}{abs(delta_bp):.1f} bp "
            f"(from {float(prior_pct):.3f}% on {prior_date:%Y-%m-%d})"
        )
        lines.append(
            "- Interpretation depends on the Pass-1 regime label : "
            "in a calm regime, a rise narrows the US/EUR rate "
            "differential (EUR pulls toward USD funding parity) ; "
            "under funding stress or usd_complacency, the same rise "
            "can widen the Bund/Treasury spread and signal "
            "convertibility risk (EUR pulls the OPPOSITE direction). "
            "A fall is the symmetric reverse. The Pass-2 LLM should "
            "select the branch matching the regime context above."
        )

    # ─── €STR (round-34 P0 step-4) ─────────────────────────────────
    # Front-end EUR funding rate. Together with Bund 10Y, covers the
    # 0-10y EUR rate curve fresh-daily. Silent skip if empty table.
    estr_stmt = (
        select(EstrObservation.observation_date, EstrObservation.rate_pct)
        .order_by(desc(EstrObservation.observation_date))
        .limit(6)
    )
    estr_rows = (await session.execute(estr_stmt)).all()
    if estr_rows:
        estr_latest_date, estr_latest_pct = estr_rows[0]
        estr_latest_f = float(estr_latest_pct)
        sources.append(f"ECB:EST/ESTR@{estr_latest_date:%Y-%m-%d}")
        lines.append("### €STR (Euro Short-Term Rate)")
        lines.append(
            f"- €STR = {estr_latest_f:.3f}% (ECB Data Portal SDMX EST, {estr_latest_date:%Y-%m-%d})"
        )
        if len(estr_rows) >= 6:
            estr_prior_date, estr_prior_pct = estr_rows[5]
            estr_delta_bp = (estr_latest_f - float(estr_prior_pct)) * 100.0
            estr_sign = "+" if estr_delta_bp >= 0 else "−"
            lines.append(
                f"- 5-trading-day change : {estr_sign}{abs(estr_delta_bp):.1f} bp "
                f"(from {float(estr_prior_pct):.3f}% on {estr_prior_date:%Y-%m-%d})"
            )
            # Symmetric interpretation : €STR rise = ECB hawkish proxy.
            lines.append(
                "- Interpretation : €STR rise reflects ECB tightening "
                "stance OR front-end stress repricing. In a calm regime, "
                "rise narrows the policy-rate gap with the Fed (EUR-positive) ; "
                "under funding stress, rise can reflect euro-area money-market "
                "fragmentation (EUR-negative). The Pass-2 LLM picks the "
                "branch matching the Pass-1 regime."
            )

    # ─── BTP-Bund spread (round-34 P0 step-4, via FRED inline) ─────
    # Italy 10Y benchmark yield (OECD monthly via FRED). Direct BdI
    # SDMX is blocked by Cloudflare bot-mitigation, FRED fallback per
    # round-33 subagent #2 web research. Compute spread = BTP - Bund
    # at the LATEST common date (Bund daily / BTP monthly — surface
    # the frequency mismatch in the text so the LLM stays honest).
    # FRED IRLTLT01ITM156N is OECD MONTHLY with 1-month publication
    # lag. Round-37 r35-audit-gap closure : `_latest_fred` now consults
    # `_FRED_SERIES_MAX_AGE_DAYS` registry which sets this series to
    # 120 days automatically — no explicit override needed here.
    btp_latest = await _latest_fred(session, "IRLTLT01ITM156N")
    if btp_latest is not None:
        btp_value, btp_date = btp_latest
        spread_pp = btp_value - bund_latest_f
        sources.append(f"FRED:IRLTLT01ITM156N@{btp_date:%Y-%m-%d}")
        lines.append("### BTP-Bund 10Y spread (peripheral fragmentation)")
        lines.append(
            f"- Italy 10Y = {btp_value:.2f}% (FRED IRLTLT01ITM156N, "
            f"{btp_date:%Y-%m-%d} — OECD monthly, 1-month lag)"
        )
        lines.append(f"- BTP-Bund spread = {spread_pp:+.2f} pp (Italy 10Y minus Bund 10Y)")
        lines.append(
            "- Frequency mismatch : Bund is DAILY (above), BTP is "
            "MONTHLY. Treat this spread as a REGIME indicator, NOT "
            "an intraday signal. Spread widening (>2.0 pp) historically "
            "co-incides with eurozone fragmentation episodes (2011-12 "
            "sovereign crisis, 2018 Italy populist budget) — EUR-negative. "
            "Spread tightening (<1.0 pp) reflects ECB credibility + "
            "convergence trades — EUR-positive."
        )

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
    # else branch removed wave 52 (was emitting duplicate 'SKEW: n/a' even
    # when SKEW had a valid reading right above — bug cosmetic)

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
        lines.append(f"- {label} = {val:.2f} (FRED:{series_id}, {when:%Y-%m-%d})")
        sources.append(f"FRED:{series_id}")

    return "\n".join(lines), sources


async def _section_fed_financial(session: AsyncSession) -> tuple[str, list[str]]:
    """## Fed monetary stance + financial conditions composite (Wave 43).

    Surfaces 8 of the 27 wave-42 FRED additions that are most trader-
    actionable for Pass 1 régime + Pass 2 mechanism citations.

    Pillar A: Fed Funds target band + EFFR position within range.
    Pillar B: Financial conditions composites (Chicago NFCI / ANFCI,
              St Louis FSI4) — negative = looser than average, positive
              = tighter (régime-flagging).
    Pillar C: Credit cycle gauge (BAA-AAA spread).
    Pillar D: Forward inflation expectations (1y) vs 2% target.
    """
    sources: list[str] = []
    lines: list[str] = ["## Fed monetary stance + financial conditions"]

    # ── Pillar A: Fed Funds target range + EFFR position ──
    upper = await _latest_fred(session, "DFEDTARU", max_age_days=30)
    lower = await _latest_fred(session, "DFEDTARL", max_age_days=30)
    effr = await _latest_fred(session, "EFFR", max_age_days=14)
    if upper and lower and effr:
        lo, hi, e = lower[0], upper[0], effr[0]
        # Position within range : 0 = at lower bound, 1 = at upper bound
        pos = (e - lo) / (hi - lo) if hi > lo else 0.5
        if pos < 0.25:
            band = "near lower bound (dovish drift)"
        elif pos > 0.75:
            band = "near upper bound (pressure to hike)"
        else:
            band = "mid-range (stable)"
        lines.append(
            f"- Fed Funds target = [{lo:.2f} %, {hi:.2f} %] — EFFR = {e:.2f} % "
            f"({pos * 100:.0f}%% in range, {band}, FRED:DFEDTARU+L+EFFR, "
            f"{effr[1]:%Y-%m-%d})"
        )
        sources.extend(["FRED:DFEDTARU", "FRED:DFEDTARL", "FRED:EFFR"])

    # ── Pillar B: Financial conditions composites ──
    nfci = await _latest_fred(session, "NFCI", max_age_days=14)
    anfci = await _latest_fred(session, "ANFCI", max_age_days=14)
    stl = await _latest_fred(session, "STLFSI4", max_age_days=14)
    if nfci or anfci or stl:
        lines.append("### Financial conditions composites")
        if nfci is not None:
            v = nfci[0]
            flag = "TIGHTER than avg" if v > 0 else "looser than avg"
            lines.append(f"- Chicago NFCI = {v:+.3f} — {flag} (FRED:NFCI, {nfci[1]:%Y-%m-%d})")
            sources.append("FRED:NFCI")
        if anfci is not None:
            v = anfci[0]
            flag = "TIGHTER" if v > 0 else "looser"
            lines.append(
                f"- Chicago ANFCI (macro-adjusted) = {v:+.3f} — {flag}"
                f" (FRED:ANFCI, {anfci[1]:%Y-%m-%d})"
            )
            sources.append("FRED:ANFCI")
        if stl is not None:
            v = stl[0]
            flag = "STRESS" if v > 1 else ("elevated" if v > 0 else "calm")
            lines.append(f"- St Louis FSI4 = {v:+.2f} — {flag} (FRED:STLFSI4, {stl[1]:%Y-%m-%d})")
            sources.append("FRED:STLFSI4")

    # ── Pillar C: Credit cycle gauge (BAA-AAA spread) ──
    aaa = await _latest_fred(session, "AAA", max_age_days=14)
    baa = await _latest_fred(session, "BAA", max_age_days=14)
    if aaa and baa:
        spread = baa[0] - aaa[0]
        if spread >= 1.5:
            band = "credit STRESS (>150 bp)"
        elif spread >= 1.0:
            band = "elevated (100-150 bp)"
        elif spread >= 0.7:
            band = "normal (70-100 bp)"
        else:
            band = "compressed (<70 bp, complacency)"
        lines.append(
            f"- BAA-AAA spread = {spread * 100:.0f} bp "
            f"(BAA={baa[0]:.2f} % vs AAA={aaa[0]:.2f} %) — {band}"
            f" (FRED:BAA+AAA, {baa[1]:%Y-%m})"
        )
        sources.extend(["FRED:BAA", "FRED:AAA"])

    # ── Pillar C-bis : ZQ implied EFFR vs current EFFR (Wave 47) ──
    zq = await _latest_fred(session, "ZQ_FRONT_IMPLIED_EFFR", max_age_days=14)
    if zq is not None and effr is not None:
        spread_bps = (zq[0] - effr[0]) * 100
        if spread_bps < -10:
            move = f"CUT priced ({spread_bps:.0f}bp dovish)"
        elif spread_bps > 10:
            move = f"HIKE priced ({spread_bps:+.0f}bp hawkish)"
        else:
            move = f"no move ({spread_bps:+.0f}bp, status quo)"
        lines.append(
            f"- ZQ front-month implied EFFR = {zq[0]:.3f} % vs actual EFFR "
            f"{effr[0]:.3f} % — {move} (CBOT ZQ=F via Yahoo, {zq[1]:%Y-%m-%d})"
        )
        sources.append("CME:ZQ_FRONT_IMPLIED_EFFR")

    # ── Pillar C-ter : ZQ forward EFFR curve (Wave 48 multi-month) ──
    # Pull each forward contract's implied EFFR; surface compactly.
    forward_codes = ("K26", "M26", "N26", "Q26", "U26", "V26", "X26", "Z26", "F27")
    forward_labels = (
        "May26",
        "Jun26",
        "Jul26",
        "Aug26",
        "Sep26",
        "Oct26",
        "Nov26",
        "Dec26",
        "Jan27",
    )
    forward_pts: list[tuple[str, float]] = []
    for code, label in zip(forward_codes, forward_labels, strict=False):
        fv = await _latest_fred(session, f"ZQ_{code}_IMPLIED_EFFR", max_age_days=7)
        if fv is None:
            continue
        forward_pts.append((label, fv[0]))
        sources.append(f"CME:ZQ_{code}_IMPLIED_EFFR")
    if forward_pts:
        curve_str = " · ".join(f"{lbl}={v:.3f}%" for lbl, v in forward_pts)
        lines.append(f"- ZQ forward EFFR curve : {curve_str}")
        # Min/max + range = market expectation amplitude
        if len(forward_pts) >= 3:
            mn = min(v for _, v in forward_pts)
            mx = max(v for _, v in forward_pts)
            mn_lbl = next(lbl for lbl, v in forward_pts if v == mn)
            mx_lbl = next(lbl for lbl, v in forward_pts if v == mx)
            range_bps = (mx - mn) * 100
            if range_bps > 5:
                lines.append(
                    f"- ZQ curve range = {range_bps:.0f} bp "
                    f"(low {mn_lbl}={mn:.3f}%, high {mx_lbl}={mx:.3f}%)"
                )

        # ── Pillar C-quater (Wave 49) : per-meeting CME-style probabilities ──
        # CME FedWatch methodology approximates probability of a 25-bp move
        # at meeting M from the spread between pre-meeting and post-meeting
        # contract month implied EFFR. Simple linear formula:
        #     P(cut) ≈ max(0, (pre_meeting - post_meeting) / 0.25) capped 1.0
        #     P(hike) ≈ max(0, (post_meeting - pre_meeting) / 0.25) capped 1.0
        # FOMC 2026 calendar : Jun 16-17 / Jul 28-29 / Sep 15-16 /
        # Oct 27-28 / Dec 8-9. Map each to (pre_month_code, post_month_code).
        fomc_meetings_2026 = (
            ("Jun FOMC", "M26", "N26"),  # Jun 16-17 → use M26 pre, N26 post
            ("Jul FOMC", "N26", "Q26"),  # Jul 28-29 → N26 pre, Q26 post
            ("Sep FOMC", "U26", "V26"),  # Sep 15-16 → U26 pre, V26 post
            ("Oct FOMC", "V26", "X26"),  # Oct 27-28 → V26 pre, X26 post
            ("Dec FOMC", "Z26", "F27"),  # Dec 8-9 → Z26 pre, F27 post
        )
        pts_dict = dict(forward_pts)
        # Map month-code → forward_pts label (e.g. "M26" → "Jun26")
        code_to_label = {
            "K26": "May26",
            "M26": "Jun26",
            "N26": "Jul26",
            "Q26": "Aug26",
            "U26": "Sep26",
            "V26": "Oct26",
            "X26": "Nov26",
            "Z26": "Dec26",
            "F27": "Jan27",
        }
        prob_lines: list[str] = []
        for fomc_label, pre_code, post_code in fomc_meetings_2026:
            pre_lbl = code_to_label.get(pre_code)
            post_lbl = code_to_label.get(post_code)
            if pre_lbl is None or post_lbl is None:
                continue
            pre_v = pts_dict.get(pre_lbl)
            post_v = pts_dict.get(post_lbl)
            if pre_v is None or post_v is None:
                continue
            spread_bp = (post_v - pre_v) * 100
            if spread_bp < -5:  # 5bp threshold for noise
                p_cut = min(1.0, max(0.0, -spread_bp / 25.0))
                prob_lines.append(
                    f"  {fomc_label} : ~{p_cut * 100:.0f}% probability of 25bp cut "
                    f"(spread {spread_bp:+.1f}bp pre→post)"
                )
            elif spread_bp > 5:
                p_hike = min(1.0, max(0.0, spread_bp / 25.0))
                prob_lines.append(
                    f"  {fomc_label} : ~{p_hike * 100:.0f}% probability of 25bp hike "
                    f"(spread {spread_bp:+.1f}bp pre→post)"
                )
            # else: no_move dominant, skip line
        if prob_lines:
            lines.append("- FedWatch DIY per-meeting probabilities (CME formula):")
            lines.extend(prob_lines)

    # ── Pillar D: Forward inflation expectations vs 2% target ──
    exp = await _latest_fred(session, "EXPINF1YR", max_age_days=45)
    if exp is not None:
        v = exp[0]
        target_gap = v - 2.0
        flag = (
            "above target"
            if target_gap > 0.5
            else ("near target" if abs(target_gap) <= 0.5 else "below target")
        )
        lines.append(
            f"- 1y expected inflation (Cleveland model) = {v:.2f} % "
            f"(target gap {target_gap:+.2f}, {flag}) (FRED:EXPINF1YR, {exp[1]:%Y-%m})"
        )
        sources.append("FRED:EXPINF1YR")

    return "\n".join(lines), sources


async def _section_labor_uncertainty(session: AsyncSession) -> tuple[str, list[str]]:
    """## Labor + uncertainty + recession régime (Wave 41).

    Surfaces 7 FRED indicators:
      - ICSA + IC4WSA: weekly jobless claims (5-day lead on NFP cycle)
      - USREC: NBER recession indicator (binary 0/1)
      - USEPUINDXD: Baker-Bloom-Davis Economic Policy Uncertainty daily
      - CIVPART: labor force participation rate
      - AHETPI: average hourly earnings (wage-inflation gauge)
      - ATLSBUSRGEP: Atlanta Fed business inflation expectations (1y)

    Pass 1 régime + Pass 2 mechanism citation for labor cycle / wage
    inflation / policy-uncertainty narrative.
    """
    sources: list[str] = []
    lines: list[str] = ["## Labor + uncertainty régime (FRED)"]

    # Recession flag
    rec = await _latest_fred(session, "USREC", max_age_days=60)
    if rec is not None:
        flag = "RECESSION" if rec[0] >= 0.5 else "no recession"
        lines.append(f"- NBER recession (USREC) = {rec[0]:.0f} — {flag} ({rec[1]:%Y-%m})")
        sources.append("FRED:USREC")

    # Jobless claims with band
    icsa = await _latest_fred(session, "ICSA", max_age_days=21)
    ic4 = await _latest_fred(session, "IC4WSA", max_age_days=21)
    if icsa is not None:
        v = icsa[0]
        if v < 200_000:
            band = "very tight labor (<200k)"
        elif v < 250_000:
            band = "healthy (200-250k)"
        elif v < 350_000:
            band = "softening (250-350k)"
        else:
            band = "recession-territory (>350k)"
        ic4_str = f", 4w MA = {ic4[0]:,.0f}" if ic4 else ""
        lines.append(
            f"- Initial claims = {v:,.0f}{ic4_str} — {band} (FRED:ICSA, {icsa[1]:%Y-%m-%d})"
        )
        sources.append("FRED:ICSA")
        if ic4:
            sources.append("FRED:IC4WSA")

    # Policy uncertainty
    epu = await _latest_fred(session, "USEPUINDXD", max_age_days=14)
    if epu is not None:
        v = epu[0]
        if v >= 300:
            band = "extreme (>300)"
        elif v >= 200:
            band = "elevated (200-300)"
        elif v >= 100:
            band = "modest (100-200)"
        else:
            band = "low (<100)"
        lines.append(
            f"- US Economic Policy Uncertainty (Baker-Bloom-Davis) = {v:.1f} — {band}"
            f" (FRED:USEPUINDXD, {epu[1]:%Y-%m-%d})"
        )
        sources.append("FRED:USEPUINDXD")

    # Wage-inflation
    ahe = await _latest_fred(session, "AHETPI", max_age_days=60)
    biz = await _latest_fred(session, "ATLSBUSRGEP", max_age_days=60)
    if ahe is not None:
        lines.append(
            f"- Avg hourly earnings (production) = ${ahe[0]:.2f} (FRED:AHETPI, {ahe[1]:%Y-%m})"
        )
        sources.append("FRED:AHETPI")
    if biz is not None:
        v = biz[0]
        flag = "above 2 % target" if v > 2 else "at/below target"
        lines.append(
            f"- Atlanta Fed business inflation expectations 1y = {v:.2f} %"
            f" — {flag} (FRED:ATLSBUSRGEP, {biz[1]:%Y-%m})"
        )
        sources.append("FRED:ATLSBUSRGEP")

    # Labor force participation
    civ = await _latest_fred(session, "CIVPART", max_age_days=60)
    if civ is not None:
        lines.append(
            f"- Labor force participation rate = {civ[0]:.1f} % (FRED:CIVPART, {civ[1]:%Y-%m})"
        )
        sources.append("FRED:CIVPART")

    return "\n".join(lines), sources


async def _section_oecd_cli(session: AsyncSession) -> tuple[str, list[str]]:
    """## OECD Composite Leading Indicators — global cycle régime.

    CLI > 100 = above trend (expansion); < 100 = below trend (slowdown).
    Turning points lead GDP by 6-9 months. Surfaces 7 CLIs in DB
    (Wave 34): US / G7 / Japan / Germany / UK / China / EA19.

    Critical signal — China-vs-rest divergence: when global G7 > 100
    but China < 100, commodity demand impulse weakens unilaterally
    (bearish AUD/CAD via copper, mining proxy).
    """
    cli_series: tuple[tuple[str, str], ...] = (
        ("USALOLITOAASTSAM", "USA"),
        ("G7LOLITOAASTSAM", "G7"),
        ("JPNLOLITOAASTSAM", "Japan"),
        ("DEULOLITOAASTSAM", "Germany"),
        ("GBRLOLITOAASTSAM", "UK"),
        ("CHNLOLITOAASTSAM", "China"),
        # NB: EA19LOLITOAASTSAM was here — last data Nov 2022 on FRED
        # (likely discontinued). Removed wave 52 to avoid 'n/a' clutter.
    )

    sources: list[str] = []
    lines: list[str] = ["## OECD CLI (composite leading indicators)"]

    readings: dict[str, tuple[float, datetime]] = {}
    # Wave 45: pull last 14 monthly observations (slightly more than 1y)
    # to compute 3m + 12m direction deltas.
    cutoff = datetime.now(UTC).date() - timedelta(days=500)
    for series_id, label in cli_series:
        stmt = (
            select(FredObservation.observation_date, FredObservation.value)
            .where(
                FredObservation.series_id == series_id,
                FredObservation.observation_date >= cutoff,
                FredObservation.value.is_not(None),
            )
            .order_by(desc(FredObservation.observation_date))
            .limit(14)
        )
        hist = list((await session.execute(stmt)).all())
        if not hist:
            lines.append(f"- {label}: n/a (FRED:{series_id})")
            continue
        cur_obs, cur_val = hist[0]
        readings[label] = (
            float(cur_val),
            datetime.combine(cur_obs, datetime.min.time(), tzinfo=UTC),
        )
        regime = "expansion" if float(cur_val) >= 100 else "slowdown"
        arrow = "▲" if float(cur_val) >= 100 else "▼"
        # 3m + 12m deltas
        deltas: list[str] = []
        if len(hist) > 3:
            d3 = float(cur_val) - float(hist[3][1])
            d3_dir = "↗" if d3 > 0.1 else ("↘" if d3 < -0.1 else "→")
            deltas.append(f"Δ3m {d3:+.2f} {d3_dir}")
        if len(hist) > 12:
            d12 = float(cur_val) - float(hist[12][1])
            d12_dir = "↗" if d12 > 0.5 else ("↘" if d12 < -0.5 else "→")
            deltas.append(f"Δ12m {d12:+.2f} {d12_dir}")
        delta_str = f", {', '.join(deltas)}" if deltas else ""
        lines.append(
            f"- {label:8s} = {float(cur_val):.2f} {arrow} ({regime}{delta_str}, "
            f"FRED:{series_id}, {cur_obs:%Y-%m})"
        )
        sources.append(f"FRED:{series_id}")

    # China-vs-rest divergence flag (trader-actionable signal)
    if "China" in readings and ("G7" in readings or "USA" in readings):
        china_val = readings["China"][0]
        anchor = readings.get("G7") or readings["USA"]
        anchor_val = anchor[0]
        gap = anchor_val - china_val
        if china_val < 100 and anchor_val > 100 and gap > 1.0:
            lines.append(
                f"- ⚠ China divergence: G7/US > 100 (expansion) "
                f"while China < 100 (slowdown), gap = {gap:+.2f}"
                f" — bearish commodity demand impulse (AUD/CAD copper risk)"
            )

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
        lines.append(f"- Grand Total foreign-held = ${grand_total.holdings_bn_usd:,.1f} bn")
    country_rows = [
        r
        for r in rows
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


async def _section_cleveland_fed_nowcast(
    session: AsyncSession,
) -> tuple[str, list[str]]:
    """## Cleveland Fed inflation nowcast — daily CPI/PCE forecast.

    Surfaces the latest 4-measure × 3-horizon nowcast plus Δ vs the
    most recent prior revision (>=3 calendar days back).
    Useful for Pass 2 surprise-vs-consensus thesis.

    Cadence : daily ~16:00 Paris.
    """
    # Latest revision date.
    latest_rev_row = (
        await session.execute(
            select(ClevelandFedNowcast.revision_date)
            .order_by(desc(ClevelandFedNowcast.revision_date))
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest_rev_row is None:
        return ("## Cleveland Fed nowcast\n- n/a (collector empty)", [])

    rows = list(
        (
            await session.execute(
                select(ClevelandFedNowcast).where(
                    ClevelandFedNowcast.revision_date == latest_rev_row
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return ("## Cleveland Fed nowcast\n- n/a (collector empty)", [])

    sources = [f"CLEVELAND_FED:NOWCAST@{latest_rev_row.isoformat()}"]
    lines = [f"## Cleveland Fed nowcast (revised {latest_rev_row:%Y-%m-%d})"]

    # Group by horizon, sort canonically.
    by_horizon: dict[str, list[ClevelandFedNowcast]] = {}
    for r in rows:
        by_horizon.setdefault(r.horizon, []).append(r)

    measure_order = ("CPI", "CoreCPI", "PCE", "CorePCE")
    for horizon_label in ("yoy", "qoq", "mom"):
        if horizon_label not in by_horizon:
            continue
        h_rows = {r.measure: r for r in by_horizon[horizon_label]}
        target = next(iter(by_horizon[horizon_label])).target_period
        suffix = " (annualised)" if horizon_label in {"qoq", "mom"} else ""
        lines.append(f"### {horizon_label.upper()} target {target:%b %Y}{suffix}")
        line_parts: list[str] = []
        for m in measure_order:
            r = h_rows.get(m)
            if r is None:
                continue
            line_parts.append(f"{m}={r.nowcast_value:.2f}%")
        if line_parts:
            lines.append("- " + " · ".join(line_parts))

    # Δ vs prior revision (look at the previous distinct revision date).
    prior_rev_row = (
        await session.execute(
            select(ClevelandFedNowcast.revision_date)
            .where(ClevelandFedNowcast.revision_date < latest_rev_row)
            .order_by(desc(ClevelandFedNowcast.revision_date))
            .limit(1)
        )
    ).scalar_one_or_none()
    if prior_rev_row is not None:
        prior_rows = list(
            (
                await session.execute(
                    select(ClevelandFedNowcast).where(
                        ClevelandFedNowcast.revision_date == prior_rev_row
                    )
                )
            )
            .scalars()
            .all()
        )
        prior_map = {(r.measure, r.horizon, r.target_period): r for r in prior_rows}
        delta_lines: list[str] = []
        # Focus the delta narrative on YoY which is the headline-print metric.
        yoy_rows = [r for r in rows if r.horizon == "yoy"]
        for r in sorted(
            yoy_rows,
            key=lambda x: measure_order.index(x.measure) if x.measure in measure_order else 99,
        ):
            prior = prior_map.get((r.measure, r.horizon, r.target_period))
            if prior is None:
                continue
            delta = r.nowcast_value - prior.nowcast_value
            arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
            delta_lines.append(f"{r.measure}{arrow}{delta:+.2f}")
        if delta_lines:
            lines.append(
                f"### Δ YoY vs prior rev {prior_rev_row:%Y-%m-%d}: " + " · ".join(delta_lines)
            )

    return "\n".join(lines), sources


def _band(value: float | None, thresholds: tuple[float, ...], labels: tuple[str, ...]) -> str:
    """Classify `value` into a band given (sorted ascending) thresholds.

    `len(labels) == len(thresholds) + 1`. Returns "n/a" for None input.
    """
    if value is None:
        return "n/a"
    for threshold, label in zip(thresholds, labels[:-1], strict=False):
        if value < threshold:
            return label
    return labels[-1]


async def _section_cross_asset_matrix(
    session: AsyncSession,
) -> tuple[str, list[str]]:
    """## Cross-asset matrix v2 — 6 macro dimensions + per-asset bias guide.

    Aggregates the macro-research surface into a single structured
    section that Pass 1 régime classifier + Pass 2 mechanism citation
    can both consume directly. Six dimensions, each normalized into a
    qualitative band:

      1. Inflation persistence (NY Fed MCT trend, W71)
      2. Inflation surprise (Cleveland nowcast Core PCE YoY vs MCT, W72)
      3. Liquidity / financial conditions (FRED NFCI, W42)
      4. Tail-risk regime (CBOE SKEW, W24)
      5. Volatility regime (VIX, FRED VIXCLS)
      6. Small-business sentiment (NFIB SBOI, W74)

    Followed by a per-asset directional-bias guide (8 Ichor pairs) that
    summarizes how each dimension typically pressures the asset in the
    current band. Bias is a qualitative tag (`+`/`-`/`?`) anchored on
    macro theory, not curve-fitting — the orchestrator's Critic
    re-weights it. ADR-017 boundary: this is research framing, never
    a trade signal.
    """
    sources: list[str] = []
    lines: list[str] = ["## Cross-asset matrix (W79)"]

    # ── 1. Inflation persistence (MCT trend) ──
    mct_row = (
        await session.execute(
            select(NyfedMctObservation)
            .order_by(desc(NyfedMctObservation.observation_month))
            .limit(1)
        )
    ).scalar_one_or_none()
    mct_value = mct_row.mct_trend_pct if mct_row else None
    mct_band = _band(
        mct_value,
        (2.25, 2.75, 3.25),
        ("anchored", "near-target", "above-target", "unanchored"),
    )
    if mct_row is not None:
        sources.append(f"NYFED:MCT@{mct_row.observation_month.isoformat()}")

    # ── 2. Inflation surprise (Cleveland Core PCE YoY vs MCT) ──
    nowcast_row = (
        await session.execute(
            select(ClevelandFedNowcast)
            .where(
                ClevelandFedNowcast.measure == "CorePCE",
                ClevelandFedNowcast.horizon == "yoy",
            )
            .order_by(desc(ClevelandFedNowcast.revision_date))
            .limit(1)
        )
    ).scalar_one_or_none()
    nowcast_value: float | None = nowcast_row.nowcast_value if nowcast_row else None
    surprise_pts = (
        nowcast_value - mct_value if (nowcast_value is not None and mct_value is not None) else None
    )
    surprise_band = _band(
        surprise_pts,
        (-0.50, -0.10, 0.10, 0.50),
        ("downside-strong", "downside", "neutral", "upside", "upside-strong"),
    )
    if nowcast_row is not None:
        sources.append(f"CLEVELAND_FED:NOWCAST@{nowcast_row.revision_date.isoformat()}")

    # ── 3. Liquidity / financial conditions (NFCI) ──
    nfci_v = await _latest_fred(session, "NFCI", max_age_days=14)
    nfci_value = nfci_v[0] if nfci_v else None
    nfci_band = _band(
        nfci_value,
        (-0.5, 0.0, 0.5),
        ("loose", "mild-loose", "mild-tight", "tight"),
    )
    if nfci_v:
        sources.append("FRED:NFCI")

    # ── 4. Tail-risk regime (CBOE SKEW) ──
    skew_row = (
        await session.execute(
            select(CboeSkewObservation)
            .order_by(desc(CboeSkewObservation.observation_date))
            .limit(1)
        )
    ).scalar_one_or_none()
    skew_value = skew_row.skew_value if skew_row else None
    skew_band = _band(
        skew_value, (135.0, 145.0, 155.0), ("calm", "normal", "elevated", "tail-fear")
    )
    if skew_row is not None:
        sources.append(f"CBOE:SKEW@{skew_row.observation_date.isoformat()}")

    # ── 5. Volatility regime (VIX) ──
    vix_v = await _latest_fred(session, "VIXCLS", max_age_days=7)
    vix_value = vix_v[0] if vix_v else None
    vix_band = _band(vix_value, (15.0, 22.0, 30.0), ("complacent", "normal", "elevated", "panic"))
    if vix_v:
        sources.append("FRED:VIXCLS")

    # ── 6. Small-business sentiment (NFIB SBOI) ──
    sbet_row = (
        await session.execute(
            select(NfibSbetObservation).order_by(desc(NfibSbetObservation.report_month)).limit(1)
        )
    ).scalar_one_or_none()
    sbet_value = sbet_row.sboi if sbet_row else None
    sbet_band = _band(
        sbet_value, (95.0, 98.0, 102.0), ("recession-pre", "below-avg", "soft", "expansionary")
    )
    if sbet_row is not None:
        sources.append(f"NFIB:SBET@{sbet_row.report_month.isoformat()}")

    if not sources:
        return ("", [])  # nothing to surface — caller skips append

    # ── Dimension table ──
    lines.append("")
    lines.append("| # | Dimension | Value | Band |")
    lines.append("|---|---|---|---|")
    rows = [
        ("1", "Inflation persistence (MCT)", mct_value, mct_band, "%"),
        ("2", "Inflation surprise (CorePCE - MCT)", surprise_pts, surprise_band, " pts"),
        ("3", "Liquidity (NFCI)", nfci_value, nfci_band, ""),
        ("4", "Tail risk (SKEW)", skew_value, skew_band, ""),
        ("5", "Volatility (VIX)", vix_value, vix_band, ""),
        ("6", "Small-biz sentiment (SBOI)", sbet_value, sbet_band, ""),
    ]
    for n, name, val, band, unit in rows:
        v = "n/a" if val is None else f"{val:.2f}{unit}"
        lines.append(f"| {n} | {name} | {v} | {band} |")

    # ── Per-asset directional-bias guide ──
    # Heuristic mapping (NOT a trade signal — ADR-017 research framing).
    # Reads the 6 dimensions and projects qualitative pressure per asset.
    inflation_pressure_up = mct_value is not None and mct_value >= 2.75
    liquidity_tight = nfci_value is not None and nfci_value >= 0.0
    tail_fear = skew_band in {"elevated", "tail-fear"}
    vol_elevated = vix_band in {"elevated", "panic"}
    sentiment_weak = sbet_band in {"recession-pre", "below-avg"}
    # ── Inverse conditions (round-38 r37-audit-gap #2 partial closure :
    # EUR-bullish symmetry mirror).
    # The 3 USD-positive triggers above (liquidity_tight, vol_elevated,
    # inflation_pressure_up) have NO symmetric EUR-bullish counterparts
    # → EUR_USD hints surface "balanced" in usd_complacency regimes
    # even though the macro structure favours EUR_USD upside via
    # broad-USD-weakness flow + carry-friendly calm regime + Fed-easing
    # rate-differential narrowing. Round-32b ratification of ADR-090
    # documented the gap in `_section_eur_specific` (Bund + €STR + BTP
    # symmetric language) but cross_asset_matrix was left asymmetric.
    # This round closes that asymmetry for the n=13 anti-skill pocket.
    liquidity_loose = nfci_band in {"loose", "mild-loose"}
    vol_complacent = vix_band == "complacent"
    tail_calm = skew_band == "calm"
    sentiment_strong = sbet_band == "expansionary"
    inflation_anchored = mct_band in {"anchored", "near-target"}

    lines.append("")
    lines.append("### Per-asset macro-pressure tags (research only, ADR-017)")
    asset_hints: list[tuple[str, list[str]]] = []

    def asset(name: str, hints: list[str]) -> tuple[str, list[str]]:
        return name, hints

    eur_usd: list[str] = []
    # ── USD-positive scenarios (asymmetric pre-round-38) ──
    if liquidity_tight:
        eur_usd.append("USD-bid (NFCI tight)")
    if vol_elevated:
        eur_usd.append("USD-bid (vol regime)")
    if inflation_pressure_up:
        eur_usd.append("Fed-on-hold supports USD")
    # ── EUR-bullish scenarios (round-38 symmetric mirror, audit-gap #2
    # partial closure ; ADR-017 research framing — Pass-2 LLM weighs
    # both sides against the active regime).
    # Round-39 Tetlock-invalidation discipline (ichor-trader audit
    # GAP-C closure) : each EUR-bid hint carries a TESTABLE INVALIDATION
    # threshold so the Pass-2 LLM cannot adopt the directional thesis
    # without an explicit "if X then thesis dead" exit. Mirrors
    # `_section_eur_specific` symmetric language doctrine (line 644). ──
    if liquidity_loose:
        eur_usd.append(
            "EUR-bid (NFCI loose, broad USD-weakness flow ; "
            "invalidated if NFCI ≥ 0.0 within 5 sessions)"
        )
    if vol_complacent and tail_calm:
        eur_usd.append(
            "EUR-bid (carry-friendly calm regime ; invalidated if VIX > 22 OR SKEW > 145)"
        )
    if inflation_anchored and sentiment_strong:
        eur_usd.append(
            "EUR-bid (Fed easing path, rate-differential narrowing ; "
            "invalidated if MCT > 2.75 OR SBOI < 98)"
        )
    asset_hints.append(asset("EUR_USD", eur_usd or ["balanced"]))

    gbp_usd: list[str] = list(eur_usd)
    if sentiment_weak:
        gbp_usd.append("UK growth-tail downside")
    asset_hints.append(asset("GBP_USD", gbp_usd or ["balanced"]))

    usd_jpy: list[str] = []
    if vol_elevated or tail_fear:
        usd_jpy.append("JPY-bid (safe haven)")
    if inflation_pressure_up:
        usd_jpy.append("UST yield up → USD-bid")
    asset_hints.append(asset("USD_JPY", usd_jpy or ["balanced"]))

    aud_usd: list[str] = []
    if liquidity_tight or tail_fear:
        aud_usd.append("AUD-soft (risk-off)")
    if inflation_pressure_up:
        aud_usd.append("commodity tail-up support")
    asset_hints.append(asset("AUD_USD", aud_usd or ["balanced"]))

    usd_cad: list[str] = []
    if vol_elevated:
        usd_cad.append("USD-bid (vol regime)")
    asset_hints.append(asset("USD_CAD", usd_cad or ["balanced"]))

    xau_usd: list[str] = []
    if inflation_pressure_up:
        xau_usd.append("real-yield support (++)")
    if tail_fear or vol_elevated:
        xau_usd.append("safe-haven flow (++)")
    if liquidity_tight:
        xau_usd.append("USD-strength counter-pressure (-)")
    asset_hints.append(asset("XAU_USD", xau_usd or ["balanced"]))

    nas: list[str] = []
    if inflation_pressure_up:
        nas.append("duration headwind (-)")
    if liquidity_tight:
        nas.append("multiple-compression risk (-)")
    if vol_elevated:
        nas.append("vol-of-vol drag (-)")
    asset_hints.append(asset("NAS100_USD", nas or ["balanced"]))

    spx: list[str] = []
    if liquidity_tight or tail_fear:
        spx.append("risk-off pressure (-)")
    if sentiment_weak:
        spx.append("earnings-tail downside (-)")
    asset_hints.append(asset("SPX500_USD", spx or ["balanced"]))

    for asset_name, hints in asset_hints:
        lines.append(f"- **{asset_name}** : {' · '.join(hints)}")

    return "\n".join(lines), sources


async def _section_myfxbook_outlook(
    session: AsyncSession,
) -> tuple[str, list[str]]:
    """## MyFXBook Community Outlook — retail FX positioning.

    Contrarian sentiment indicator. Reports the latest snapshot per
    Ichor pair plus a contrarian flag (>=75 % one-side). Empty (no
    sources) when collector is dormant — caller skips append.
    """
    # Latest fetch_at (single point representing one outlook snapshot
    # across all pairs). All pairs in a fetch share the same fetched_at.
    latest_at = (
        await session.execute(
            select(MyfxbookOutlook.fetched_at).order_by(desc(MyfxbookOutlook.fetched_at)).limit(1)
        )
    ).scalar_one_or_none()
    if latest_at is None:
        return ("", [])  # dormant — caller skips

    rows = list(
        (
            await session.execute(
                select(MyfxbookOutlook).where(MyfxbookOutlook.fetched_at == latest_at)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return ("", [])

    sources = [f"MYFXBOOK:OUTLOOK@{latest_at.isoformat()}"]
    lines = [f"## MyFXBook Community Outlook ({latest_at:%Y-%m-%d %H:%M UTC})"]
    lines.append(
        "_Contrarian retail FX positioning. Self-selection bias — MyFXBook-linked traders only._"
    )
    for r in sorted(rows, key=lambda x: x.pair):
        flag = ""
        if r.long_pct >= 75:
            flag = " ⚠ retail-long-extreme"
        elif r.short_pct >= 75:
            flag = " ⚠ retail-short-extreme"
        lines.append(f"- {r.pair:8s}  long={r.long_pct:5.1f}%  short={r.short_pct:5.1f}%{flag}")

    return "\n".join(lines), sources


async def _section_nfib_sbet(session: AsyncSession) -> tuple[str, list[str]]:
    """## NFIB SBET — small business sentiment leading indicator.

    Surfaces the latest SBOI + Uncertainty Index + a régime classifier
    based on the historical (1986-) base. SBOI < 95 + Uncertainty > 95
    is the recession-precursor signature seen in 2007 and 2019.
    """
    rows = list(
        (
            await session.execute(
                select(NfibSbetObservation)
                .order_by(desc(NfibSbetObservation.report_month))
                .limit(13)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return ("## NFIB SBET\n- n/a (collector empty)", [])

    cur = rows[0]
    sources = [f"NFIB:SBET@{cur.report_month.isoformat()}"]
    lines = [f"## NFIB SBET ({cur.report_month:%b %Y})"]
    lines.append(f"- SBOI = {cur.sboi:.1f} (52y avg ≈ 98.0)")
    if cur.uncertainty_index is not None:
        lines.append(f"- Uncertainty Index = {cur.uncertainty_index:.0f}")

    # Régime classifier — anchored on 52y average + recession signature.
    if cur.sboi < 95 and (cur.uncertainty_index is not None and cur.uncertainty_index > 95):
        regime = "recession-precursor (SBOI <95 + Uncertainty >95)"
    elif cur.sboi < 95:
        regime = "below-average sentiment"
    elif cur.sboi < 100:
        regime = "soft (below 1986 base)"
    else:
        regime = "expansionary"
    lines.append(f"- Régime = {regime}")

    # Δ MoM and Δ 12m
    if len(rows) >= 2:
        d1 = cur.sboi - rows[1].sboi
        lines.append(f"- Δ SBOI 1m = {d1:+.1f} pts (vs {rows[1].report_month:%b%y})")
    if len(rows) >= 13:
        d12 = cur.sboi - rows[12].sboi
        lines.append(f"- Δ SBOI 12m = {d12:+.1f} pts (vs {rows[12].report_month:%b%y})")

    return "\n".join(lines), sources


async def _section_aaii(session: AsyncSession) -> tuple[str, list[str]]:
    """## AAII Sentiment Survey weekly — retail equity sentiment contrarian.

    Surfaces the latest bullish / bearish / neutral split + the bull-bear
    spread. Historical contrarian indicator: extreme bullish > 50% precedes
    weak forward S&P returns; extreme bearish < 20% precedes strong ones.
    The 0.40 |spread| threshold (`collectors/aaii.py:is_extreme`) marks the
    contrarian-flag boundary. Persisted by `run_collectors aaii` into
    fred_observations as AAII_BULLISH / AAII_BEARISH / AAII_NEUTRAL /
    AAII_SPREAD (bull/bear/neutral in [0, 1], spread in [-1, 1]). Couche-2
    sentiment agent (ADR-023 Haiku low) also consumes these — surfacing
    them in the 4-pass data_pool here (W104b) lets Pass-2 NAS100/SPX500
    frameworks cite the mechanism explicitly instead of citing empty.
    """
    bull = await _latest_fred(session, "AAII_BULLISH", max_age_days=14)
    bear = await _latest_fred(session, "AAII_BEARISH", max_age_days=14)
    neut = await _latest_fred(session, "AAII_NEUTRAL", max_age_days=14)
    spread = await _latest_fred(session, "AAII_SPREAD", max_age_days=14)

    if not (bull and bear and spread):
        return ("## AAII Sentiment Survey\n- n/a (collector empty or stale)", [])

    obs_date = bull[1].date()
    sources = [
        f"FRED:AAII_BULLISH@{obs_date.isoformat()}",
        f"FRED:AAII_BEARISH@{obs_date.isoformat()}",
        f"FRED:AAII_SPREAD@{obs_date.isoformat()}",
    ]
    if neut:
        sources.append(f"FRED:AAII_NEUTRAL@{obs_date.isoformat()}")

    bull_pct = bull[0]
    bear_pct = bear[0]
    neut_pct = neut[0] if neut else None
    spread_val = spread[0]

    lines = [f"## AAII Sentiment Survey ({obs_date:%b %d %Y})"]
    lines.append(f"- Bullish  = {bull_pct:5.1%}")
    lines.append(f"- Bearish  = {bear_pct:5.1%}")
    if neut_pct is not None:
        lines.append(f"- Neutral  = {neut_pct:5.1%}")
    lines.append(f"- Spread   = {spread_val:+.2f} (bull - bear)")

    # Contrarian régime classifier — anchored on AAII's 0.40 extreme threshold
    # (collectors/aaii.py:is_extreme) + standard 0.20 "moderate tilt" band.
    if abs(spread_val) > 0.40:
        if spread_val > 0:
            regime = "extreme retail-bull contrarian (⚠ historically caps forward returns)"
        else:
            regime = (
                "extreme retail-bear contrarian (⚠ historically precedes strong forward returns)"
            )
    elif abs(spread_val) > 0.20:
        regime = f"moderate retail-{'bull' if spread_val > 0 else 'bear'} tilt"
    else:
        regime = "neutral retail sentiment"
    lines.append(f"- Régime   = {regime}")

    # Δ 1-week spread delta (if we have at least 2 weekly observations).
    prior_row = (
        await session.execute(
            select(FredObservation.value, FredObservation.observation_date)
            .where(
                FredObservation.series_id == "AAII_SPREAD",
                FredObservation.observation_date < obs_date,
                FredObservation.value.is_not(None),
            )
            .order_by(desc(FredObservation.observation_date))
            .limit(1)
        )
    ).first()
    if prior_row is not None:
        d1 = spread_val - float(prior_row[0])
        lines.append(f"- Δ spread 1w = {d1:+.2f} (vs {prior_row[1]:%b%d})")

    return "\n".join(lines), sources


async def _section_nyfed_mct(session: AsyncSession) -> tuple[str, list[str]]:
    """## NY Fed Multivariate Core Trend — persistent inflation trend.

    Replaces the discontinued FRED UIGFULL series. Surfaces the most
    recent MCT trend value + 6-month and 12-month deltas + the 3-sector
    decomposition (Goods / Services ex housing / Housing) so Pass 1 can
    classify the inflation régime (anchored vs unanchored) and Pass 2
    can cite the mechanism (which sector is driving persistence).

    Cadence : monthly with ~4-week lag (released 1st business day of the
    month following the BEA PCE print, ~10:00 ET).
    """
    rows = list(
        (
            await session.execute(
                select(NyfedMctObservation)
                .order_by(desc(NyfedMctObservation.observation_month))
                .limit(13)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return ("## NY Fed MCT (PCE trend)\n- n/a (collector empty)", [])

    cur = rows[0]
    sources = [f"NYFED:MCT@{cur.observation_month.isoformat()}"]
    lines = [f"## NY Fed MCT (PCE trend, {cur.observation_month:%b %Y})"]

    # Headline
    lines.append(f"- MCT trend = {cur.mct_trend_pct:.2f}%")
    if cur.headline_pce_yoy is not None:
        lines.append(f"- Headline PCE YoY = {cur.headline_pce_yoy:.2f}%")
    if cur.core_pce_yoy is not None:
        lines.append(f"- Core PCE YoY     = {cur.core_pce_yoy:.2f}%")

    # Deltas — m6 vs m12
    if len(rows) >= 7:
        d6 = cur.mct_trend_pct - rows[6].mct_trend_pct
        lines.append(f"- Δ MCT 6m = {d6:+.2f} pts (vs {rows[6].observation_month:%b%y})")
    if len(rows) >= 13:
        d12 = cur.mct_trend_pct - rows[12].mct_trend_pct
        lines.append(f"- Δ MCT 12m = {d12:+.2f} pts (vs {rows[12].observation_month:%b%y})")

    # Régime classifier — qualitative anchored / unanchored bands.
    # Fed 2 % target, 2.5 % is the "above target tolerable" upper band cited
    # by Powell 2024-Q3, 3 % is the "uncomfortable persistence" threshold.
    regime: str
    if cur.mct_trend_pct < 2.25:
        regime = "anchored (below target tolerance)"
    elif cur.mct_trend_pct < 2.75:
        regime = "near target (cuts-tolerable band)"
    elif cur.mct_trend_pct < 3.25:
        regime = "above target (cuts-on-hold band)"
    else:
        regime = "unanchored (hike-pressure band)"
    lines.append(f"- Régime = {regime}")

    # 3-sector decomposition (where is the trend coming from?)
    sector_parts: list[str] = []
    if cur.goods_pct is not None:
        sector_parts.append(f"Goods {cur.goods_pct:+.2f}")
    if cur.services_ex_housing_pct is not None:
        sector_parts.append(f"Svc-ex-H {cur.services_ex_housing_pct:+.2f}")
    if cur.housing_pct is not None:
        sector_parts.append(f"Housing {cur.housing_pct:+.2f}")
    if sector_parts:
        lines.append("### Sector contribution")
        lines.append("- " + " · ".join(sector_parts))

    return "\n".join(lines), sources


async def _section_tff_positioning(session: AsyncSession, asset: str) -> tuple[str, list[str]]:
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
        delta_str = f", Δw/w (Dealer {dealer_dw:+,}, AM {am_dw:+,}, LevFunds {lev_dw:+,})"
    else:
        delta_str = ""

    # Smart-money divergence flag : LevFunds and AssetMgr on opposite sides.
    divergence = ""
    if lev_net != 0 and am_net != 0 and (lev_net > 0) != (am_net > 0):
        divergence = "\n- ⚠ smart-money divergence: LevFunds and AssetMgr opposite sides"

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
    """## COT positioning — latest weekly Disaggregated row for the asset.

    Wave 45 enriched: Δw/w + Δ4w + Δ12w trend deltas on managed_money_net
    to surface positioning regime shifts (acceleration / deceleration /
    reversal) rather than just a static snapshot.
    """
    market = _COT_MARKET_BY_ASSET.get(asset)
    if market is None:
        return "", []
    stmt = (
        select(CotPosition)
        .where(CotPosition.market_code == market)
        .order_by(desc(CotPosition.report_date))
        .limit(13)  # ~3 months of weekly data for Δ12w computation
    )
    rows = list((await session.execute(stmt)).scalars().all())
    if not rows:
        return f"## COT positioning ({asset}, market={market})\n- n/a", []
    cur = rows[0]
    deltas: list[str] = []
    if len(rows) > 1:
        d1 = cur.managed_money_net - rows[1].managed_money_net
        deltas.append(f"Δw/w {d1:+,}")
    if len(rows) > 4:
        d4 = cur.managed_money_net - rows[4].managed_money_net
        deltas.append(f"Δ4w {d4:+,}")
    if len(rows) > 12:
        d12 = cur.managed_money_net - rows[12].managed_money_net
        deltas.append(f"Δ12w {d12:+,}")
    delta_str = f", {', '.join(deltas)}" if deltas else ""

    # Detect acceleration / reversal patterns
    pattern = ""
    if len(rows) > 4:
        d1w = cur.managed_money_net - rows[1].managed_money_net if len(rows) > 1 else 0
        d4w = cur.managed_money_net - rows[4].managed_money_net
        if d1w * d4w < 0 and abs(d4w) > 5000:
            pattern = " — ⚠ trend reversal w/w"
        elif abs(d1w) > 0.3 * abs(d4w) and abs(d4w) > 10_000:
            pattern = " — accelerating"

    sources = [f"CFTC:COT:{market}@{cur.report_date.isoformat()}"]
    md = (
        f"## COT positioning ({asset}, market={market})\n"
        f"- managed_money_net = {cur.managed_money_net:+,}{delta_str}{pattern} "
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

    # Wave 39 — categorize macro markets for clearer Pass 2 mechanism
    # citations. Buckets cover the 5 dominant trader-relevant themes.
    def _category(question: str) -> str:
        q = question.lower()
        if any(
            kw in q
            for kw in (
                "fed",
                "fomc",
                "rate cut",
                "rate hike",
                "basis point",
                "ecb",
                "boj",
                "boe ",
                "rba",
            )
        ):
            return "Monetary policy"
        if any(
            kw in q
            for kw in (
                "recession",
                "gdp",
                "cpi",
                "inflation",
                "pce",
                "unemployment",
                "nfp",
                "payroll",
                "jobless",
                "ppi",
            )
        ):
            return "Macro indicators"
        if any(
            kw in q
            for kw in (
                "russia",
                "ukraine",
                "iran",
                "israel",
                "china",
                "taiwan",
                "war",
                "ceasefire",
                "sanctions",
                "tariff",
            )
        ):
            return "Geopolitics"
        if any(
            kw in q
            for kw in (
                "trump",
                "biden",
                "harris",
                "election",
                "congress",
                "debt ceiling",
                "shutdown",
                "fiscal",
            )
        ):
            return "US politics"
        if any(kw in q for kw in ("bitcoin", "btc", "ethereum", "eth", "crypto", "etf approval")):
            return "Crypto-macro"
        return "Other"

    by_cat: dict[str, list[PolymarketSnapshot]] = {}
    for r in poly_top:
        by_cat.setdefault(_category(r.question), []).append(r)

    sections.append(f"### Polymarket (top 15 by 24h volume, of {len(poly_unique)} fresh)")
    if not poly_top:
        sections.append("- (no fresh snapshots)")
    else:
        # Render in priority order so Pass 1/2 see the most-relevant theme first
        cat_order = (
            "Monetary policy",
            "Macro indicators",
            "Geopolitics",
            "US politics",
            "Crypto-macro",
            "Other",
        )
        for cat in cat_order:
            cat_rows = by_cat.get(cat) or []
            if not cat_rows:
                continue
            sections.append(f"#### {cat}")
            for r in cat_rows:
                yes = r.last_prices[0] if (r.last_prices and len(r.last_prices) > 0) else None
                yes_str = f"YES={yes:.2f}" if yes is not None else "YES=n/a"
                vol_str = f"${(r.volume_usd or 0) / 1e6:.1f}M" if r.volume_usd else "$?"
                sections.append(f"- {r.question[:80]} → {yes_str} vol={vol_str} (slug:{r.slug})")
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

    # Wave 50 — Executive summary (insert AT TOP via re-prepend below).
    # Rationale: Pass 1 brain reads top-down for régime classification,
    # so 5-bullet synthesis at top primes the model with the highest-
    # conviction signals before details. Sources included for citation.
    exec_md, exec_src = await _section_executive_summary(session)
    sections.insert(0, ("executive_summary", exec_md, exec_src))

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

    # Wave 35 — OECD CLI cycle régime (US / G7 / Japan / Germany / UK /
    # China / EA19). Above/below 100 classifier + China divergence flag.
    cli_md, cli_src = await _section_oecd_cli(session)
    sections.append(("oecd_cli", cli_md, cli_src))

    # Wave 71 — NY Fed Multivariate Core Trend (PCE inflation trend).
    # Replaces discontinued UIGFULL. Pass 1 régime (anchored vs un-anchored)
    # + Pass 2 mechanism citation for Fed reaction-function thesis.
    mct_md, mct_src = await _section_nyfed_mct(session)
    sections.append(("nyfed_mct", mct_md, mct_src))

    # Wave 72 — Cleveland Fed daily inflation nowcast (CPI / Core CPI / PCE
    # / Core PCE × MoM / QoQ / YoY). Higher-frequency point-in-time forecast
    # complementing MCT trend. Pass 2 cites for surprise-vs-consensus thesis.
    cln_md, cln_src = await _section_cleveland_fed_nowcast(session)
    sections.append(("cleveland_fed_nowcast", cln_md, cln_src))

    # Wave 74 — NFIB Small Business Economic Trends monthly. Leading
    # indicator of small-business hiring + capex + sentiment. Pass 1
    # régime (recession-precursor when SBOI < 95 + Uncertainty > 95).
    nfib_md, nfib_src = await _section_nfib_sbet(session)
    sections.append(("nfib_sbet", nfib_md, nfib_src))

    # Wave 104b — AAII Sentiment Survey weekly (collector wired since
    # 2026-05-08, surfaced into 4-pass here 2026-05-11 — audit gap G4
    # closed). Retail equity sentiment contrarian indicator. Pass-2
    # NAS100/SPX500 cites mechanism for "extreme retail bull → cap
    # forward returns". Skipped silently if collector dormant.
    aaii_md, aaii_src = await _section_aaii(session)
    if aaii_src:
        sections.append(("aaii", aaii_md, aaii_src))

    # Wave 77 — MyFXBook Community Outlook retail FX positioning.
    # Contrarian sentiment indicator. Skipped silently if collector
    # dormant (env vars unset).
    fxb_md, fxb_src = await _section_myfxbook_outlook(session)
    if fxb_src:  # only append if we actually have data
        sections.append(("myfxbook_outlook", fxb_md, fxb_src))

    # Wave 79 — Cross-asset matrix v2: 6 macro dimensions normalized to
    # qualitative bands + per-asset directional-bias guide. Aggregates
    # the inflation pillar (W71/W72), liquidity (FRED W42), tail risk
    # (CBOE SKEW), sentiment (NFIB W74) into one structured surface.
    cam_md, cam_src = await _section_cross_asset_matrix(session)
    if cam_src:
        sections.append(("cross_asset_matrix", cam_md, cam_src))

    # Wave 41 — Labor + uncertainty + recession régime (7 FRED series).
    # Jobless claims band + EPU band + wage-inflation + USREC flag.
    lab_md, lab_src = await _section_labor_uncertainty(session)
    sections.append(("labor_uncertainty", lab_md, lab_src))

    # Wave 43 — Fed monetary stance + financial conditions (8 FRED series
    # from wave 42 batch). Fed Funds target band + EFFR position +
    # NFCI/ANFCI/FSI4 + BAA-AAA credit spread + 1y inflation expectations.
    fed_md, fed_src = await _section_fed_financial(session)
    sections.append(("fed_financial", fed_md, fed_src))

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

    # ADR-090 P0 step-3 (round-32) — EUR-specific Bund 10Y yield.
    # Asset-gated to EUR_USD ; silent skip otherwise OR if the
    # Bundesbank collector is dormant / pre-deploy. Symmetric
    # interpretive language : the Pass-2 LLM picks the right framing
    # based on Pass-1's regime label.
    eur_md, eur_src = await _section_eur_specific(session, asset)
    if eur_src:
        sections.append(("eur_specific", eur_md, eur_src))

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
