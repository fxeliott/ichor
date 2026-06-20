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
from datetime import UTC, date, datetime, timedelta
from typing import Literal

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
from .asset_news_affinity import (
    NEWS_KEYWORDS as _NEWS_KEYWORDS,
)
from .asset_news_affinity import (
    matches_asset as _matches_asset,
)

# r138 + r139 — back-compat re-exports for doctrine #4 SSOT pin
# (`test_data_pool_back_compat_reexport_present`). The `__all__`
# declaration is the canonical Python way to mark intentional re-exports
# so ruff F401 cannot strip names whose sole consumer migrated away
# (r139 recurrence after the S4 _section_news → filter_rows_by_asset_affinity
# migration left _matches_asset un-referenced ; ruff stripped it twice
# despite per-line noqa).
# r-round8 — the 4 Chantier-C write-side builders moved VERBATIM to
# dimension_vote_builders are re-exported below (cli + C-3 wiring tests) ; pinned
# here so ruff F401 cannot strip the re-export. (RUF022-sorted.)
__all__ = (
    "_NEWS_KEYWORDS",
    "_cot_vote_from_rows",
    "_matches_asset",
    "_tff_vote_from_rows",
    "_volume_vote_from_reading",
    "build_correlations_vote_for_asset",
    "build_cot_vote_for_asset",
    "build_geopolitics_vote_for_asset",
    "build_manipulation_liquidity_vote_for_asset",
    "build_positioning_divergence_vote_for_asset",
    "build_positioning_tff_vote_for_asset",
    "build_real_yield_vote_for_asset",
    "build_sentiment_vote_for_asset",
    "build_vol_regime_vote_for_asset",
    "build_volume_vote_for_asset",
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
from .data_liveness import classify_liveness
from .divergence import render_consensus_block, render_divergence_block
from .economic_calendar import (
    assess_calendar,
    render_calendar_block,
)
from .fred_age_registry import FRED_DEFAULT_MAX_AGE_DAYS, FRED_SERIES_MAX_AGE_DAYS
from .funding_stress import (
    assess_funding_stress,
    render_funding_stress_block,
)
from .gex_persistence import render_gex_block
from .hourly_volatility import (
    assess_hourly_volatility,
    render_hourly_volatility_block,
)
from .liquidity_proxy import (
    assess_liquidity_proxy,
    render_liquidity_proxy_block,
)
from .microstructure import (
    assess_microstructure,
    assess_relative_volume,
    classify_relative_volume,
    render_microstructure_block,
    render_relative_volume_block,
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
from .previous_session_origin_zone import (
    compute_previous_session_origin_zone,
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
from .theme_classifier import (
    classify_dominant_theme,
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
    "DTWEXBGS": ("USD broad index (DTWEXBGS)", "{:.2f}"),
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

# S04 TIER-2 #4 — UST → equity-index rate-sensitivity context (expert call).
# The 10-Year US Treasury is THE benchmark discount rate for equity valuations;
# 10Y-futures positioning (TFF) is a forward read on the rate channel that drives
# index multiples (esp. long-duration tech → Nasdaq). Surfaced as DESCRIPTIVE,
# NON-directional context (ADR-017) for the rate-sensitive indices only. 10Y only
# (the valuation benchmark) — 2Y/5Y/30Y are collected but left out here to keep
# one clean, well-grounded channel (cftc_tff.py:83-86). The collector already
# fetches 043602, so the consumer⊆collector guard stays green.
_UST_10Y_TFF_CODE = "043602"
_RATE_CONTEXT_BY_ASSET: dict[str, str] = {
    "SPX500_USD": _UST_10Y_TFF_CODE,
    "NAS100_USD": _UST_10Y_TFF_CODE,
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
    # ADR-103 (ADR-099 §T3.2) — runtime FRED-liveness degraded-input
    # manifest. Default `[]` so every existing constructor stays valid
    # (additive, frozen-dataclass-safe). Projected into `DataPoolOut`
    # for the operator surface + the r94 end-user badge foundation.
    degraded_inputs: list[DegradedInput] = field(default_factory=list)


@dataclass(frozen=True)
class FredLiveness:
    """Liveness verdict for one FRED series — ADR-103.

    `_latest_fred` folds `observation_date >= cutoff` into SQL so a
    series that is *stale* beyond its registry max-age returns the same
    `None` as one that was *never ingested* (`data_pool.py:285-286`) —
    the stale-vs-absent distinction is destroyed at the query layer.
    This carries it explicitly. `status` semantics:
      - `fresh`  : a non-null obs exists within the registry max-age
                   (⟺ `_latest_fred` would return a row — byte-consistent)
      - `stale`  : a non-null obs exists but is OLDER than max-age
                   (the China-M1-class dead series ; ADR-093 §r49)
      - `absent` : no non-null obs ever ingested for this series
    """

    series_id: str
    status: Literal["fresh", "stale", "absent"]
    latest_date: date | None
    age_days: int | None
    max_age_days: int


@dataclass(frozen=True)
class DegradedInput:
    """A critical FRED anchor that is stale/absent → its dependent
    section or sub-driver silently degrades. Projected onto `DataPool`
    + `DataPoolOut` (ADR-103, ADR-099 §D-2 "never silently absent").
    Never carries `status == "fresh"` (a fresh input is not degraded).
    """

    series_id: str
    status: Literal["stale", "absent"]
    latest_date: date | None
    age_days: int | None
    max_age_days: int
    impacted: str


# ────────────────────────── Section builders ──────────────────────────


# Per-series max-age-days registry + conservative default — EXTRACTED
# r92 to the dependency-free SSOT `services/fred_age_registry.py` so the
# ADR-097 CI guard can import it WITHOUT data_pool's SQLAlchemy + 33-ORM
# graph (latent Defect A — the shipped guard imported it from here and
# the workflow installed only httpx → exit-4 on every run since r61).
# Re-exported below under the historic private names so every runtime
# caller (`_max_age_days_for`, `_latest_fred`) is byte-identical
# (r71/r91 anti-accumulation extract-to-SSOT pattern). The full r35/r37
# rationale + the per-series table now live in `fred_age_registry.py`
# (single source of truth — no duplicate dict here).
_FRED_SERIES_MAX_AGE_DAYS: dict[str, int] = FRED_SERIES_MAX_AGE_DAYS
_FRED_DEFAULT_MAX_AGE_DAYS: int = FRED_DEFAULT_MAX_AGE_DAYS


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


# ─────────────── ADR-103 — runtime FRED-liveness audit ────────────────
# ADR-099 §T3.2 "human-visible degraded-data alert — break the
# silent-skip chain". `_latest_fred` collapses absent vs stale → None ;
# `_fred_liveness` runs the cutoff-FREE latest query (the info that
# collapse destroys) and classifies against the r92 fred_age_registry
# SSOT. `_latest_fred` itself is byte-identical (no contract change).


async def _fred_liveness(
    session: AsyncSession, series_id: str, *, override: int | None = None
) -> FredLiveness:
    """Liveness of `series_id` WITHOUT `_latest_fred`'s absent/stale fold.

    One extra cheap indexed `LIMIT 1` (PK-ordered, value-not-null) with
    NO `>= cutoff` predicate, so the *actual* latest observation_date
    survives. `fresh` ⟺ `age <= max_age` ⟺ `observation_date >=
    today - max_age` ⟺ `_latest_fred` returns a row — provably the same
    boundary (byte-consistency invariant, unit-pinned). Invoked only by
    the always-on integrity audit (≤ a dozen series / card).
    """
    max_age = _max_age_days_for(series_id, override=override)
    stmt = (
        select(FredObservation.observation_date)
        .where(
            FredObservation.series_id == series_id,
            FredObservation.value.is_not(None),
        )
        .order_by(desc(FredObservation.observation_date))
        .limit(1)
    )
    latest = (await session.execute(stmt)).scalars().first()
    if latest is None:
        return FredLiveness(series_id, "absent", None, None, max_age)
    age = (datetime.now(UTC).date() - latest).days
    status: Literal["fresh", "stale", "absent"] = "fresh" if age <= max_age else "stale"
    return FredLiveness(series_id, status, latest, age, max_age)


@dataclass(frozen=True)
class _CriticalAnchor:
    """A FRED series whose `None` causes a SILENT section-skip or
    sub-driver drop. `max_age_override` mirrors the exact override the
    consuming section passes to `_latest_fred` (so the audit's `fresh`
    means precisely "the consumer got its data") ; None ⟹ registry SSOT.
    Derived from VERIFIED `_section_*` reads (r93 R59), not guessed.
    """

    series_id: str
    max_age_override: int | None
    impacted: str


# Pass-1 régime classifier inputs — audited for EVERY asset (régime is
# universal). Overrides verbatim from `_section_executive_summary`
# (`data_pool.py:324-329`, r93-verified).
_MACRO_CORE_ANCHORS: tuple[_CriticalAnchor, ...] = (
    _CriticalAnchor("VIXCLS", 7, "Pass-1 régime classifier (VIX panic input)"),
    _CriticalAnchor("BAMLH0A0HYM2", 14, "Pass-1 régime classifier (HY-OAS credit input)"),
    _CriticalAnchor("NFCI", 14, "Pass-1 régime classifier (financial-conditions input)"),
    _CriticalAnchor("USALOLITOAASTSAM", 90, "Pass-1 régime classifier (US CLI cycle input)"),
    _CriticalAnchor("EXPINF1YR", 45, "Pass-1 régime classifier (1y inflation-expectations input)"),
    _CriticalAnchor("THREEFYTP10", 30, "Pass-1 régime classifier (term-premium input)"),
)

# Per-asset primary anchors whose absence silently kills the per-asset
# section, + the ADR-093 AUD composite sub-drivers that silently drop.
# series_ids verified from the `_section_*` reads (r93 R59) ; max-age
# judged against the registry SSOT (override only where the consuming
# section passes one — VIXCLS@7). EUR_USD's Bund anchor is NON-FRED
# (`BundYieldObservation`, no cutoff) → out of FRED-liveness scope this
# round (documented in ADR-103 §Negative).
_ASSET_CRITICAL_ANCHORS: dict[str, tuple[_CriticalAnchor, ...]] = {
    "XAU_USD": (
        _CriticalAnchor("DFII10", None, "xau_specific section (primary real-yield driver)"),
    ),
    "NAS100_USD": (
        _CriticalAnchor("DGS10", None, "nas_specific section (primary duration driver)"),
    ),
    "SPX500_USD": (
        _CriticalAnchor("VIXCLS", 7, "spx_specific section (primary tail-regime driver)"),
    ),
    "USD_JPY": (
        _CriticalAnchor("IRLTLT01JPM156N", None, "jpy_specific section (primary JP anchor)"),
    ),
    "AUD_USD": (
        _CriticalAnchor(
            "IRLTLT01AUM156N", None, "aud_specific section (primary AU anchor — section skips)"
        ),
        _CriticalAnchor(
            "MYAGM1CNM189N", None, "aud_specific China-credit driver (ADR-093 composite)"
        ),
        _CriticalAnchor("PIORECRUSDM", None, "aud_specific iron-ore driver (ADR-093 composite)"),
        _CriticalAnchor("PCOPPUSDM", None, "aud_specific copper driver (ADR-093 composite)"),
    ),
    "GBP_USD": (
        _CriticalAnchor("IRLTLT01GBM156N", None, "gbp_specific section (primary UK anchor)"),
    ),
}


async def _section_data_integrity(
    session: AsyncSession, asset: str
) -> tuple[str, list[str], list[DegradedInput]]:
    """## Data integrity — runtime FRED critical-anchor liveness (ADR-103).

    ALWAYS rendered (never the `("", [])` sentinel ; appended
    unconditionally near the top of `build_data_pool`, mirroring the
    `_section_key_levels` "explicit state instead of missing data"
    doctrine, `data_pool.py:4260-4261`) so Pass-1 régime + Pass-2 are
    primed with data-health context BEFORE they read the macro blocks.

    Breaks the silent-skip chain (ADR-099 §D-2 "never silently absent"):
    a dead/stale critical anchor (the China-M1 class, ADR-093 §r49) is
    now deterministically + explicitly surfaced every card instead of a
    section vanishing with zero trace. ADR-017-clean — data-provenance
    vocabulary only, explicit boundary note, no directional/signal
    language.

    Returns `(markdown, sources, degraded_inputs)` (3-tuple like
    `_section_daily_levels`). `sources` stamps only the FRESH series
    (legit provenance) ; the section still renders when all degraded
    (unconditional append).
    """
    asset = asset.upper()
    # macro-core (universal) + this asset's per-asset anchors, deduped by
    # series_id (macro-core wins ; VIXCLS appears in both for SPX with the
    # same @7 override → no conflict).
    seen: set[str] = set()
    anchors: list[_CriticalAnchor] = []
    for a in (*_MACRO_CORE_ANCHORS, *_ASSET_CRITICAL_ANCHORS.get(asset, ())):
        if a.series_id in seen:
            continue
        seen.add(a.series_id)
        anchors.append(a)

    livenesses: list[tuple[_CriticalAnchor, FredLiveness]] = []
    for a in anchors:
        lv = await _fred_liveness(session, a.series_id, override=a.max_age_override)
        livenesses.append((a, lv))

    degraded: list[DegradedInput] = [
        DegradedInput(
            series_id=lv.series_id,
            status=lv.status,  # type: ignore[arg-type]  # never "fresh" in this branch
            latest_date=lv.latest_date,
            age_days=lv.age_days,
            max_age_days=lv.max_age_days,
            impacted=a.impacted,
        )
        for a, lv in livenesses
        if lv.status != "fresh"
    ]
    fresh = [(a, lv) for a, lv in livenesses if lv.status == "fresh"]
    sources = [f"FRED:{lv.series_id}@{lv.latest_date:%Y-%m-%d}" for _, lv in fresh]

    n = len(livenesses)
    lines: list[str] = ["## Data integrity — FRED critical-anchor liveness (ADR-103)"]
    if not degraded:
        lines.append(
            f"**Status : ALL FRESH** — {n} critical FRED anchor(s) verified live against "
            "the r92 `fred_age_registry` thresholds (Pass-1 régime core + this asset's "
            "per-asset anchors). No silent degradation this card (ADR-099 §D-2 honored)."
        )
    else:
        k = len(degraded)
        lines.append(
            f"**Status : ⚠️ DEGRADED** — {k} of {n} critical FRED anchor(s) stale or "
            "absent (ADR-103 · ADR-099 §D-2 'never silently absent' · the ADR-093 "
            "'degraded explicit' primitive generalized to a dynamic runtime audit)."
        )
        for d in degraded:
            if d.status == "absent":
                detail = "ABSENT (no observation ever ingested)"
            else:
                detail = (
                    f"STALE (latest obs {d.latest_date:%Y-%m-%d}, "
                    f"age {d.age_days} d > registry threshold {d.max_age_days} d)"
                )
            lines.append(f"- **{d.series_id}** — {detail} → impacted: {d.impacted}.")
        lines.append(
            "- Data-integrity context — the analysis on the impacted axes reads at "
            "reduced reliability where an anchor is stale/absent; this is data-provenance "
            "context, not a signal (ADR-017 boundary)."
        )
    if fresh:
        lines.append(
            "- Fresh anchors: "
            + ", ".join(
                f"{lv.series_id}@{lv.latest_date:%Y-%m-%d} ({lv.age_days} d ≤ {lv.max_age_days} d)"
                for _, lv in fresh
            )
            + "."
        )
    return "\n".join(lines), sources, degraded


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
    # Liveness gate (mirror the tail-risk-skew sibling, data_pool.py ~3661): a
    # stale SKEW must NOT feed the master regime classifier — a weeks-old reading
    # could spuriously flip the regime to 'crisis' (SKEW>150 branch). The sibling
    # tail-risk band already gates this; the TOP regime section bypassed it.
    skew_live = classify_liveness(
        "CBOE:SKEW",
        skew_latest_row.observation_date if skew_latest_row else None,
        now=datetime.now(UTC),
        max_age_days=_SKEW_MAX_AGE_DAYS,
        impacted="Pass-1 master regime classifier (SKEW)",
    )
    vix_v = await _latest_fred(session, "VIXCLS", max_age_days=7)
    hy_oas_v = await _latest_fred(session, "BAMLH0A0HYM2", max_age_days=14)
    nfci_v = await _latest_fred(session, "NFCI", max_age_days=14)
    cli_us_v = await _latest_fred(session, "USALOLITOAASTSAM", max_age_days=90)
    expinf_v = await _latest_fred(session, "EXPINF1YR", max_age_days=45)
    term_v = await _latest_fred(session, "THREEFYTP10", max_age_days=30)

    skew = (
        skew_latest_row.skew_value
        if (skew_latest_row is not None and not skew_live.is_degraded)
        else None
    )
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
        # Honest staleness marker (reuse the regime gate above): a SKEW past its
        # freshness window is shown with the observation date + a STALE tag so the
        # band is never read as the current vol surface (display-side of the same
        # stale-as-fresh class fixed for the regime classifier).
        stale_tag = (
            f", STALE @{skew_row.observation_date.isoformat()}" if skew_live.is_degraded else ""
        )
        vol_pieces.append(f"SKEW {skew_row.skew_value:.0f} ({band}{stale_tag})")
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
    """## Macro trinity — USD broad index / US10Y / VIX, last value with date."""
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
    else:
        # Dollar-index disambiguation : DTWEXBGS is the Fed broad
        # trade-weighted dollar index (scale ~115-125), the ONLY daily
        # free USD index Ichor sources. It is NOT the ICE "DXY" (6-currency
        # basket, scale ~99-105). The LLM must anchor any USD-strength
        # invalidation threshold to the DTWEXBGS level shown above (e.g.
        # "DTWEXBGS > 121"), never to an ICE-DXY level (~99-105) — mixing
        # the two scales is the cross-card inconsistency this note closes.
        lines.append(
            "  _(USD broad index = Fed trade-weighted broad dollar, "
            "DTWEXBGS, échelle ~115-125 — ce n'est PAS l'ICE « DXY » "
            "(~99-105). Ancrez tout seuil de force USD sur le niveau "
            "DTWEXBGS ci-dessus, jamais sur une échelle DXY-ICE.)_"
        )
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


async def _section_key_levels(session: AsyncSession) -> tuple[str, list[str]]:
    """## Key levels (non-technical / fundamental switches) — ADR-083 D3.

    Cross-asset section listing fundamental price thresholds that act as
    macro/microstructure switches. Per ADR-083 D3, these are NOT technical
    analysis levels (Eliot does TA on TradingView himself) — they are
    DATA-DERIVED triggers : TGA balance bands, peg break thresholds,
    gamma flip prices, VIX/SKEW regime switches, HY OAS percentiles,
    Polymarket binary contract resolutions.

    r54 phase 1 ships TGA only as proof of pattern. r55+ extends to
    peg break, gamma flip, VIX threshold, Polymarket per the roadmap.

    Returns ("...md...", []) (no source-stamps if no level fired) instead
    of skipping the section entirely — Pass 2 LLM benefits from the
    explicit "no key level fired this session" signal vs missing section.
    """
    from .key_levels import (
        compute_call_wall_levels,
        compute_gamma_flip_levels,
        compute_hkma_peg_break,
        compute_hy_oas_percentile,
        compute_polymarket_decision_levels,
        compute_put_wall_levels,
        compute_skew_regime_switch,
        compute_tga_key_level,
        compute_vix_regime_switch,
    )

    levels: list = []
    sources: list[str] = []

    tga = await compute_tga_key_level(session)
    if tga is not None:
        levels.append(tga)
        sources.append(tga.source)

    # r55 : HKMA USD/HKD peg break (band [7.75, 7.85] convertibility).
    hkma = await compute_hkma_peg_break(session)
    if hkma is not None:
        levels.append(hkma)
        sources.append(hkma.source)

    # r56 : gamma_flip for SPX500 (SPY proxy) + NAS100 (QQQ proxy)
    # per ADR-089. Returns 0-2 KeyLevels (one per asset with data).
    for kl in await compute_gamma_flip_levels(session):
        levels.append(kl)
        sources.append(kl.source)

    # r60 : gex call_wall + put_wall (gex_snapshots extras), same proxy.
    # Each computer returns 0-2 KeyLevels (only fires in actionable zone).
    for kl in await compute_call_wall_levels(session):
        levels.append(kl)
        sources.append(kl.source)
    for kl in await compute_put_wall_levels(session):
        levels.append(kl)
        sources.append(kl.source)

    # r57 : vol/credit regime switches (VIX + SKEW + HY OAS).
    # Each returns KeyLevel | None ; only fires outside normal bands.
    for computer in (
        compute_vix_regime_switch,
        compute_skew_regime_switch,
        compute_hy_oas_percentile,
    ):
        kl = await computer(session)
        if kl is not None:
            levels.append(kl)
            sources.append(kl.source)

    # r58 : polymarket_decision (top-N macro markets in extreme zones).
    for kl in await compute_polymarket_decision_levels(session):
        levels.append(kl)
        sources.append(kl.source)

    # Future : peg_break_pboc_fix when DEXCHUS history >100 rows + CFETS
    # source ADR. call_wall + put_wall optional from gex_snapshots extras.

    if not levels:
        body = (
            "## Key levels (non-technical, ADR-083 D3)\n"
            "_(no fundamental threshold fired this session — TGA in mid-band, "
            "no peg/gamma/regime switch active. Phase 1 covers TGA only ; "
            "r55+ will add peg_break + gamma_flip + vix_regime + polymarket.)_"
        )
        return body, sources

    lines = ["## Key levels (non-technical, ADR-083 D3)"]
    lines.extend(kl.to_markdown_line() for kl in levels)
    lines.append(
        "_(threshold-driven macro switches ; not technical analysis. "
        "Pass 2 should weigh these as cross-asset modulators, not as "
        "primary entry triggers.)_"
    )
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


async def _section_xau_specific(session: AsyncSession, asset: str) -> tuple[str, list[str]]:
    """## XAU-specific signals — Gold-Real-Yield-Triangle (r41, GAP-A continuation).

    Renders gold-USD specific macro signals for XAU_USD Pass-2 via the
    canonical Erb/Harvey 2013 real-yield + dollar framework :
      1. **DFII10 daily** (US 10Y TIPS real yield) — primary gold driver.
         Source : FRED `DFII10`, daily publication, max-age default 14d.
         Inverse-real-yield law : rising real yields raise the opportunity
         cost of holding non-yielding gold.
      2. **DTWEXBGS daily** (USD broad trade-weighted, DXY proxy) —
         counter-driver. Source : FRED `DTWEXBGS`, daily publication.
         Gold is negotiated in USD, foreign buyers face higher cost as
         USD strengthens. Under safe-haven stress USD and gold can co-bid.

    Gated on `asset == "XAU_USD"` — early-return ("", []) otherwise.
    `build_data_pool` appends only when `sources` is non-empty so a
    pre-FRED-ingestion XAU_USD silently skips.

    SYMMETRIC LANGUAGE discipline (ichor-trader r32+ doctrine) :
    each signal emits BOTH interpretive branches (gold-bid + gold-soft)
    and lets the Pass-2 LLM pick consistent with Pass-1's regime label.

    TETLOCK INVALIDATION discipline (r39+ codified, r40 R23 default-
    round-opener confirmation) : threshold-flip conditions emitted inline
    so a falsified hypothesis is visible immediately rather than waiting
    for the n=13 statistical lag observed on EUR_USD/usd_complacency.

    R24 SUBSET-not-SUPERSET mirror : the gold-real-yield triangle has BOTH
    daily proxies already in `fred_observations` (DFII10 + DTWEXBGS) — no
    monthly OECD staleness trap (cf round-40 GBP rate-differential defer).
    """
    if asset != "XAU_USD":
        return "", []

    # ─── DFII10 (US 10Y TIPS real yield) — primary gold driver ─────
    # Erb/Harvey 2013 "The Golden Dilemma" : gold has a stable long-run
    # inverse relationship with US real yields (TIPS-implied). Empirical
    # correlation -0.5 to -0.7 baseline (catalog.py:181-187 XAU/DFII10
    # divergence alert). FRED DFII10 is DAILY publication ; the default
    # 14-day max-age is sufficient.
    dfii_cutoff = datetime.now(UTC).date() - timedelta(days=_max_age_days_for("DFII10"))
    dfii_stmt = (
        select(FredObservation.observation_date, FredObservation.value)
        .where(
            FredObservation.series_id == "DFII10",
            FredObservation.observation_date >= dfii_cutoff,
            FredObservation.value.is_not(None),
        )
        .order_by(desc(FredObservation.observation_date))
        .limit(6)
    )
    dfii_rows = (await session.execute(dfii_stmt)).all()
    if not dfii_rows:
        return "", []  # DFII10 missing → silent skip (primary driver)

    dfii_latest_date, dfii_latest_value = dfii_rows[0]
    dfii_latest_f = float(dfii_latest_value)
    sources = [f"FRED:DFII10@{dfii_latest_date:%Y-%m-%d}"]

    lines = [
        "## XAU-specific signals",
        "### US 10Y TIPS real yield (DFII10) — primary gold driver",
        f"- DFII10 = {dfii_latest_f:.2f}% (FRED, {dfii_latest_date:%Y-%m-%d})",
    ]

    if len(dfii_rows) >= 6:
        prior_date, prior_value = dfii_rows[5]
        delta_bp = (dfii_latest_f - float(prior_value)) * 100.0
        sign = "+" if delta_bp >= 0 else "−"
        lines.append(
            f"- 5-trading-day change : {sign}{abs(delta_bp):.1f} bp "
            f"(from {float(prior_value):.2f}% on {prior_date:%Y-%m-%d})"
        )
        lines.append(
            "- Interpretation depends on the Pass-1 regime label : "
            "in a calm regime, real-yield rise raises gold's opportunity "
            "cost (XAU-soft, Erb/Harvey law) ; under safe-haven stress "
            "(vol_elevated or tail_fear from Pass-1), the same rise can "
            "be over-ridden by flight demand (XAU-bid). A fall is the "
            "symmetric reverse. The Pass-2 LLM should select the branch "
            "matching the regime context above."
        )
        lines.append(
            "- Tetlock invalidation : Erb/Harvey real-yield support "
            "thesis is invalidated if DFII10 rises > +20 bp over 5 "
            "sessions WHILE Pass-1 regime is calm (no tail_fear or "
            "vol_elevated label). The +20 bp threshold tracks DFII10 "
            "historical 5-session 1.5-2 sigma move (daily sigma ~10-12 bp). "
            "Safe-haven thesis is invalidated if VIX drops below 16 AND "
            "SKEW < 135 concurrent (Whaley 2009 vol-of-vol regime, "
            "normal-tail pricing)."
        )

    # ─── DTWEXBGS (USD broad trade-weighted) — counter-driver ──────
    # Dollar smile : in calm regime USD and gold are inverse ; under
    # left-tail crisis (Brunnermeier-Pedersen 2009 funding-liquidity spiral) USD-bid AND gold-bid
    # co-occur. DTWEXBGS is the broad index FRED publishes daily (scale
    # ~115-125) ; the ICE "DXY" (6-currency basket, ~99-105) is a DIFFERENT
    # index Ichor does NOT source — never conflate the two scales.
    dxy_cutoff = datetime.now(UTC).date() - timedelta(days=_max_age_days_for("DTWEXBGS"))
    dxy_stmt = (
        select(FredObservation.observation_date, FredObservation.value)
        .where(
            FredObservation.series_id == "DTWEXBGS",
            FredObservation.observation_date >= dxy_cutoff,
            FredObservation.value.is_not(None),
        )
        .order_by(desc(FredObservation.observation_date))
        .limit(6)
    )
    dxy_rows = (await session.execute(dxy_stmt)).all()
    if dxy_rows:
        dxy_latest_date, dxy_latest_value = dxy_rows[0]
        dxy_latest_f = float(dxy_latest_value)
        sources.append(f"FRED:DTWEXBGS@{dxy_latest_date:%Y-%m-%d}")
        lines.append("### USD broad trade-weighted (DTWEXBGS) — counter-driver")
        lines.append(f"- DTWEXBGS = {dxy_latest_f:.2f} (FRED, {dxy_latest_date:%Y-%m-%d})")
        if len(dxy_rows) >= 6:
            dxy_prior_date, dxy_prior_value = dxy_rows[5]
            dxy_prior_f = float(dxy_prior_value)
            dxy_pct = ((dxy_latest_f - dxy_prior_f) / dxy_prior_f) * 100.0
            dxy_sign = "+" if dxy_pct >= 0 else "−"
            lines.append(
                f"- 5-trading-day change : {dxy_sign}{abs(dxy_pct):.2f}% "
                f"(from {dxy_prior_f:.2f} on {dxy_prior_date:%Y-%m-%d})"
            )
            lines.append(
                "- Interpretation : USD strength is gold-soft in a "
                "calm regime (foreign buyers face higher cost) ; under "
                "left-tail crisis (Brunnermeier-Pedersen 2009 funding-liquidity spiral), USD and "
                "gold can co-bid as defensive assets. A fall is the "
                "symmetric reverse. The Pass-2 LLM picks the branch "
                "matching the Pass-1 regime."
            )
            lines.append(
                "- Tetlock invalidation : USD-strength gold-soft thesis "
                "is invalidated if DTWEXBGS rises > 1.5% over 5 sessions "
                "WHILE DFII10 simultaneously falls (suggests stagflation "
                "regime, both can co-rise on flight) ; gold-bid co-flight "
                "thesis is invalidated if HY OAS does not widen by more "
                "than +50 bp during the DTWEXBGS up-move (cycle-invariant "
                "delta semantics aligned with the LIQUIDITY_TIGHTENING "
                "alert : no funding-stress delta = calm-regime gold-soft "
                "branch confirmed)."
            )

    # ─── Gold-Real-Yield triangle composite (R24 SUBSET-not-SUPERSET) ──
    # Surface ONLY when BOTH series are fresh — the framework needs the
    # 2-driver pairing to disambiguate stagflation from normal regimes.
    # Single-driver renders above stand alone in their own right.
    if len(dfii_rows) >= 6 and dxy_rows and len(dxy_rows) >= 6:
        lines.append("### Gold-Real-Yield triangle (Erb/Harvey + dollar-smile)")
        lines.append(
            "- The 2-driver gold pricing framework is FULLY available "
            "for this asset (R24 SUBSET-not-SUPERSET clears). When "
            "DFII10 and DTWEXBGS move in OPPOSITE directions the "
            "Pass-2 narrative should emphasise the DOMINANT mover ; "
            "when they CO-MOVE the regime is either flight (both up "
            "under stress, gold-bid co-flight override) or risk-on "
            "(both down, gold-soft with neutral-to-modest conviction)."
        )

    return "\n".join(lines), sources


async def _section_nas_specific(session: AsyncSession, asset: str) -> tuple[str, list[str]]:
    """## NAS-specific signals — duration headwind + vol-of-vol (r42, GAP-A continuation).

    Renders tech-heavy index specific macro signals for NAS100_USD Pass-2 via
    the canonical Hou-Mo-Xue 2015 q-factor duration channel + Whaley 2009
    vol-of-vol VVIX regime + tail-risk CBOE SKEW :
      1. **DGS10 daily** (US 10Y nominal yield) — primary duration headwind
         driver for long-duration tech equities. Source : FRED `DGS10`,
         daily publication, default 14d max-age.
      2. **VVIX daily** (CBOE VIX-of-VIX) — vol-of-vol regime per Whaley
         2009. Source : `cboe_vvix_observations` (migration 0032).
         Bands : <85 = calm tail-pricing ; 85-100 = modest ; 100-140 =
         elevated turbulence ; >140 = vol-surface blowup territory.
      3. **SKEW daily** (CBOE Tail-Risk Index) — tail-skew premium.
         Source : `cboe_skew_observations` (migration 0030).
         Bands : <115 = complacent ; 115-130 = modest tail bid ;
         130-150 = elevated stress ; >150 = panic priced in.

    Gated on `asset == "NAS100_USD"` — early-return ("", []) otherwise.
    `build_data_pool` appends only when `sources` is non-empty so a
    pre-FRED-ingestion NAS100_USD silently skips.

    SYMMETRIC LANGUAGE discipline (ichor-trader r32+ doctrine carried
    through r34/r41) : each interpretive section MUST emit BOTH branches
    (NAS-bid AND NAS-soft) so the Pass-2 LLM picks consistent with
    Pass-1's regime label. The pre-r42 cross_asset_matrix v2 NAS hints
    at `data_pool.py:1747-1754` were UNI-DIRECTIONAL bearish (duration
    headwind + multiple compression + vol-of-vol drag with zero bullish
    mirror). This section adds the missing bullish mirror per
    ichor-trader r41 audit YELLOW finding.

    TETLOCK INVALIDATION discipline (r39+ codified, r40 R23 default-
    round-opener confirmation) : threshold-flip conditions emitted
    inline so a falsified hypothesis is visible immediately.

    R24 SUBSET-not-SUPERSET mirror : all 3 drivers (DGS10 + VVIX + SKEW)
    are daily-FRED OR daily-CBOE — no monthly-OECD staleness trap.
    """
    if asset != "NAS100_USD":
        return "", []

    # ─── DGS10 (US 10Y nominal yield) — primary duration headwind ──
    # Hou-Mo-Xue 2015 q-factor : duration channel impacts long-duration
    # equity multiples through the discount-rate denominator. Tech-heavy
    # NAS-100 has avg duration ~25-30 years (vs SPX ~18-22), so its
    # multiple is most sensitive to long-end rate moves. FRED DGS10 is
    # DAILY publication ; default 14d max-age sufficient.
    dgs_cutoff = datetime.now(UTC).date() - timedelta(days=_max_age_days_for("DGS10"))
    dgs_stmt = (
        select(FredObservation.observation_date, FredObservation.value)
        .where(
            FredObservation.series_id == "DGS10",
            FredObservation.observation_date >= dgs_cutoff,
            FredObservation.value.is_not(None),
        )
        .order_by(desc(FredObservation.observation_date))
        .limit(6)
    )
    dgs_rows = (await session.execute(dgs_stmt)).all()
    if not dgs_rows:
        return "", []  # DGS10 missing → silent skip (primary driver)

    dgs_latest_date, dgs_latest_value = dgs_rows[0]
    dgs_latest_f = float(dgs_latest_value)
    sources = [f"FRED:DGS10@{dgs_latest_date:%Y-%m-%d}"]

    lines = [
        "## NAS-specific signals",
        "### US 10Y nominal yield (DGS10) — duration headwind driver",
        f"- DGS10 = {dgs_latest_f:.2f}% (FRED, {dgs_latest_date:%Y-%m-%d})",
    ]

    if len(dgs_rows) >= 6:
        prior_date, prior_value = dgs_rows[5]
        delta_bp = (dgs_latest_f - float(prior_value)) * 100.0
        sign = "+" if delta_bp >= 0 else "−"
        lines.append(
            f"- 5-trading-day change : {sign}{abs(delta_bp):.1f} bp "
            f"(from {float(prior_value):.2f}% on {prior_date:%Y-%m-%d})"
        )
        lines.append(
            "- Interpretation depends on the Pass-1 regime label : "
            "in a risk-off or vol_elevated regime, rate rise compresses "
            "tech multiples (NAS-soft, Hou-Mo-Xue duration channel) ; "
            "in a goldilocks or risk-on regime with growth-not-inflation "
            "framing, the same rise can be read as cyclical re-acceleration "
            "supportive of high-beta tech earnings (NAS-bid). A fall is "
            "the symmetric reverse — duration relief in calm, growth-scare "
            "in stress. The Pass-2 LLM should select the branch matching "
            "the regime context above."
        )
        lines.append(
            "- Tetlock invalidation : duration-headwind NAS-soft thesis "
            "is invalidated if DGS10 rises > +15 bp over 5 sessions WHILE "
            "Pass-1 regime is goldilocks AND high-beta tech 1m-realized-vol "
            "stays sub-30% (growth-not-inflation framing holds). The "
            "+15 bp threshold approximates a 1-sigma 5-session DGS10 "
            "move per FRED 2010-2024 empirical distribution (daily sigma "
            "~6-8 bp). Growth-acceleration NAS-bid thesis is invalidated "
            "if DGS10 rise co-incides with VVIX > 100 (vol-of-vol regime "
            "says rates are pricing tail-risk not growth)."
        )

    # ─── VVIX (CBOE vol-of-vol) — vol-regime classifier ────────────
    # VVIX is the volatility-of-VIX, i.e. how much the implied-vol
    # *surface* itself is shifting (CBOE 2007 introduction ; academic
    # treatment Park 2015, Bevilacqua-Tunaru 2021). Historically
    # VVIX > 100 coincides with elevated NAS drawdown risk via
    # vol-control fund deleveraging mechanics. VVIX < 85 = calm-tail
    # regime where systematic-vol sellers (CTAs, vol-control funds)
    # accumulate beta inducing NAS-bid pressure mechanically.
    vvix_cutoff = datetime.now(UTC).date() - timedelta(days=30)
    vvix_stmt = (
        select(CboeVvixObservation)
        .where(CboeVvixObservation.observation_date >= vvix_cutoff)
        .order_by(desc(CboeVvixObservation.observation_date))
        .limit(6)
    )
    vvix_rows = list((await session.execute(vvix_stmt)).scalars().all())
    if vvix_rows:
        vvix_latest = vvix_rows[0]
        vvix_v = vvix_latest.vvix_value
        # Band classification per existing _section_vol_surface convention
        if vvix_v >= 140:
            vvix_band = "vol-surface blowup territory (>140)"
        elif vvix_v >= 100:
            vvix_band = "elevated turbulence (100-140)"
        elif vvix_v >= 85:
            vvix_band = "modest bid (85-100)"
        else:
            vvix_band = "calm tail-pricing (<85)"
        sources.append(f"CBOE:VVIX@{vvix_latest.observation_date:%Y-%m-%d}")
        lines.append("### VVIX (CBOE VIX-of-VIX) — vol-of-vol regime")
        lines.append(
            f"- VVIX = {vvix_v:.2f} on {vvix_latest.observation_date:%Y-%m-%d} — {vvix_band}"
        )
        if len(vvix_rows) >= 6:
            vvix_prior = vvix_rows[5]
            vvix_delta = vvix_v - vvix_prior.vvix_value
            vvix_sign = "+" if vvix_delta >= 0 else "−"
            lines.append(
                f"- 5-trading-day change : {vvix_sign}{abs(vvix_delta):.2f} "
                f"(from {vvix_prior.vvix_value:.2f} on "
                f"{vvix_prior.observation_date:%Y-%m-%d})"
            )
            lines.append(
                "- Interpretation : VVIX rise reflects an unstable vol "
                "surface — gamma-flip risk, dispersion-trade unwind, "
                "vol-of-vol regime shift (NAS-soft, mechanical vol-control "
                "deleveraging). VVIX fall in a calm-tail regime mechanically "
                "supports NAS-bid via systematic vol-seller beta "
                "accumulation. The Pass-2 LLM picks the branch matching "
                "the Pass-1 regime."
            )
            lines.append(
                "- Tetlock invalidation : vol-of-vol drag NAS-soft thesis "
                "is invalidated if VVIX falls below 85 within 3 sessions "
                "AND SKEW < 130 concurrent (calm-tail regime confirmed, "
                "vol-control rebuilds beta) ; vol-bid NAS-bid thesis is "
                "invalidated if VVIX exceeds 100 alongside an SKEW move "
                "to 130+ (vol surface re-pricing tail risk in earnest)."
            )

    # ─── SKEW (CBOE tail-risk premium) — tail-bid regime classifier ─
    # CBOE SKEW measures the relative pricing of OTM puts vs calls.
    # 100 = no skew, equal pricing ; >130 = market paying real premium
    # for downside hedges (latent tail-bid). Independent dimension to
    # VVIX : VVIX is HOW much the surface moves, SKEW is WHICH SIDE
    # of the smile is bid.
    skew_cutoff = datetime.now(UTC).date() - timedelta(days=30)
    skew_stmt = (
        select(CboeSkewObservation)
        .where(CboeSkewObservation.observation_date >= skew_cutoff)
        .order_by(desc(CboeSkewObservation.observation_date))
        .limit(6)
    )
    skew_rows = list((await session.execute(skew_stmt)).scalars().all())
    if skew_rows:
        skew_latest = skew_rows[0]
        skew_v = skew_latest.skew_value
        if skew_v >= 150:
            skew_band = "panic priced in (>150)"
        elif skew_v >= 130:
            skew_band = "elevated stress (130-150)"
        elif skew_v >= 115:
            skew_band = "modest tail bid (115-130)"
        else:
            skew_band = "neutral / complacent (<115)"
        sources.append(f"CBOE:SKEW@{skew_latest.observation_date:%Y-%m-%d}")
        lines.append("### SKEW (CBOE tail-risk premium) — tail-bid regime")
        lines.append(
            f"- SKEW = {skew_v:.2f} on {skew_latest.observation_date:%Y-%m-%d} — {skew_band}"
        )
        if len(skew_rows) >= 6:
            skew_prior = skew_rows[5]
            skew_delta = skew_v - skew_prior.skew_value
            skew_sign = "+" if skew_delta >= 0 else "−"
            lines.append(
                f"- 5-trading-day change : {skew_sign}{abs(skew_delta):.2f} "
                f"(from {skew_prior.skew_value:.2f} on "
                f"{skew_prior.observation_date:%Y-%m-%d})"
            )
            lines.append(
                "- Interpretation : SKEW rise reflects rising tail-bid "
                "(hedge demand outpacing call demand) — NAS-soft via "
                "concentrated mega-cap tail-hedging flows. SKEW fall in "
                "a complacent regime reflects under-priced tail risk, "
                "which mechanically allows continued NAS-bid as "
                "downside-hedge unwinds free up risk budget. Pass-2 LLM "
                "picks consistent with Pass-1 regime."
            )
            lines.append(
                "- Tetlock invalidation : SKEW tail-bid NAS-soft thesis "
                "is invalidated if SKEW falls below 115 within 3 sessions "
                "AND VVIX < 85 concurrent (complacent regime fully "
                "confirmed, tail-hedge bid unwound) ; complacent-tail "
                "NAS-bid thesis is invalidated if SKEW rises above 130 "
                "alongside DGS10 widening > +10 bp (tail-pricing + "
                "duration-stress co-rising — pre-drawdown configuration "
                "per the Park 2015 + Bevilacqua-Tunaru 2021 VVIX-SKEW "
                "joint regime literature)."
            )

    # ─── NAS triangle composite (R24 SUBSET-not-SUPERSET clears) ────
    # Surface ONLY when ALL 3 drivers fresh — the framework needs the
    # 3-driver pairing to disambiguate growth-acceleration regimes from
    # tail-stress regimes (which can both feature DGS10 rises).
    if (
        len(dgs_rows) >= 6
        and vvix_rows
        and len(vvix_rows) >= 6
        and skew_rows
        and len(skew_rows) >= 6
    ):
        lines.append("### NAS duration-vol-tail triangle (Hou-Mo-Xue + Whaley)")
        lines.append(
            "- The 3-driver NAS pricing framework is FULLY available "
            "for this asset (R24 SUBSET-not-SUPERSET clears, all 3 "
            "daily). When DGS10 rises CONCURRENT with VVIX < 85 AND "
            "SKEW < 115 the regime is growth-not-inflation (NAS-bid "
            "override) ; DGS10 rising WITH VVIX > 100 OR SKEW > 130 "
            "is the duration-stress-tail-stress 3-corner-bear "
            "configuration (NAS-soft high conviction). The Pass-2 LLM "
            "should triangulate explicitly using all 3 dimensions before "
            "committing to a directional read."
        )

    return "\n".join(lines), sources


async def _section_spx_specific(session: AsyncSession, asset: str) -> tuple[str, list[str]]:
    """## SPX-specific signals — VIX term-structure + funding + uncertainty (r43, GAP-A continuation 3/5).

    Renders broad-market S&P 500 specific macro signals for SPX500_USD
    Pass-2 via 3-driver framework :
      1. **VIX term-structure** (VIXCLS / VXVCLS ratio) — primary
         tail-pricing regime classifier. Source : FRED `VIXCLS`
         (front-month VIX) + `VXVCLS` (3-month VIX), both daily.
         Contango (ratio < 1.0) = calm-regime tail-bid under-priced ;
         backwardation (ratio > 1.0) = stress-regime tail-bid front-
         loaded. Weak-form efficient-market literature : term-structure
         inversion historically precedes 80%+ of VIX-30+ spikes (Whaley
         + Park literature, broad sector tail-bid).
      2. **NFCI weekly** (Chicago Fed National Financial Conditions
         Index) — funding stress complement via the Brunnermeier-
         Pedersen 2009 funding-liquidity-spiral framework (the
         SPX analogue of the Stephen Jen USD broken-smile, applied
         to the equity-vol-funding doom loop rather than dollar
         strength). Source : FRED `NFCI`, weekly publication,
         max-age 14d. Z-score with zero baseline ; negative = loose
         conditions, positive = tight.
      3. **NFIB SBOI** (Small Business Optimism Index monthly) —
         small-business sentiment leading indicator for the broad
         economic regime. Source : `nfib_sbet_observations` (migration
         0036, monthly publication 1986=100 base, max-age ~60d).
         Frequency mismatch with VIXCLS/VXVCLS daily — surface as
         REGIME indicator, NOT intraday signal.

    Gated on `asset == "SPX500_USD"` — early-return ("", []) otherwise.
    `build_data_pool` appends only when `sources` is non-empty so a
    pre-FRED-ingestion SPX500 silently skips.

    SYMMETRIC LANGUAGE discipline (ichor-trader r32/r41/r42 carry-
    forward) : each interpretive section MUST emit BOTH SPX-bid AND
    SPX-soft branches so the Pass-2 LLM picks consistent with Pass-1
    regime. The pre-r43 cross_asset_matrix v2 SPX hints at
    `data_pool.py:1756-1761` were UNI-DIRECTIONAL bearish (risk-off +
    earnings-tail with zero bullish mirror). This section adds the
    missing bullish mirror.

    TETLOCK INVALIDATION discipline on ALL 3 drivers (r42 R28 carry-
    forward, citation-quality discipline applied).

    R24 SUBSET-not-SUPERSET mirror : VIXCLS + VXVCLS daily, NFCI weekly,
    SBOI monthly (frequency-mismatch surfaced inline) — no monthly OECD
    staleness trap.

    SOURCE-PURITY CAVEAT (ADR-089) : SPX500_USD Polygon ticker = `SPY`
    NYSE Arca ETF proxy (not `I:SPX` index, blocked $49/mo subscription).
    Tracking error <0.1% MTD invisible for qualitative Pass-2 framing
    but Critic should be aware of the proxy substitution when validating
    quantitative claims.
    """
    if asset != "SPX500_USD":
        return "", []

    # ─── VIX term-structure (VIXCLS / VXVCLS) — primary regime ─────
    # VIX = 30-day implied vol on SPX, VXVCLS = 3-month implied vol.
    # Ratio VXVCLS/VIXCLS > 1 = contango (calm, longer-vol bid) ;
    # ratio < 1 = backwardation (stress, front-vol bid). FRED daily
    # publication, max_age 7 days conservative (existing convention
    # _section_executive_summary line 363).
    vix_latest = await _latest_fred(session, "VIXCLS", max_age_days=7)
    if vix_latest is None:
        return "", []  # VIX missing → silent skip (primary driver)
    vix_value, vix_date = vix_latest
    sources = [f"FRED:VIXCLS@{vix_date:%Y-%m-%d}"]

    lines = [
        "## SPX-specific signals (Polygon ticker = SPY proxy, ADR-089)",
        "### VIX term-structure (VIXCLS / VXVCLS) — primary tail regime",
        f"- VIXCLS = {vix_value:.2f} (FRED, {vix_date:%Y-%m-%d}, front-month 30-day implied vol)",
    ]

    # 3-month VIX for term-structure
    vxv_latest = await _latest_fred(session, "VXVCLS", max_age_days=7)
    if vxv_latest is not None:
        vxv_value, vxv_date = vxv_latest
        sources.append(f"FRED:VXVCLS@{vxv_date:%Y-%m-%d}")
        ratio = vxv_value / vix_value if vix_value > 0 else 0.0
        if ratio >= 1.10:
            term_band = "deep contango (calm regime, tail under-priced)"
        elif ratio >= 1.00:
            term_band = "modest contango (calm bias)"
        elif ratio >= 0.95:
            term_band = "near-flat (transitional regime)"
        else:
            term_band = "backwardation (stress regime, tail bid front-loaded)"
        lines.append(f"- VXVCLS = {vxv_value:.2f} (FRED, {vxv_date:%Y-%m-%d}, 3-month implied vol)")
        lines.append(f"- Term-structure ratio = {ratio:.3f} — {term_band}")
        lines.append(
            "- Interpretation depends on the Pass-1 regime label : "
            "in a goldilocks or risk-on regime, contango (ratio > 1) "
            "is the calm-tail equilibrium where systematic vol-sellers "
            "extract roll-yield (SPX-bid via mechanical beta accumulation) ; "
            "under risk-off or vol_elevated, backwardation (ratio < 1) "
            "marks a regime where the front-month VIX leads the curve "
            "higher (SPX-soft via dispersion-trade unwind + vol-control "
            "deleveraging). The Pass-2 LLM should select the branch "
            "matching the regime context above."
        )
        lines.append(
            "- Tetlock invalidation : contango SPX-bid thesis is "
            "invalidated if VIX-term-structure flips to backwardation "
            "(ratio drops below 1.00) within 3 sessions WHILE VIX > 22 "
            "concurrent (full-flip regime signal) ; backwardation "
            "SPX-soft thesis is invalidated if ratio rises above 1.05 "
            "AND VIX falls below 18 (mean-reversion to calm-tail "
            "equilibrium confirmed)."
        )

    # ─── NFCI weekly (Chicago Fed funding stress) ──────────────────
    # NFCI z-scored with zero baseline. Negative = loose ; positive =
    # tight. Weekly publication, max-age 14d. Funding stress regime
    # complement to Brunnermeier-Pedersen 2009 funding-liquidity-spiral
    # framework (the SPX-equity analogue of the Stephen Jen USD broken-
    # smile, applied to vol-funding doom loop not dollar strength).
    # Critical for SPX because liquidity provision drives multiple expansion.
    nfci_latest = await _latest_fred(session, "NFCI", max_age_days=14)
    if nfci_latest is not None:
        nfci_value, nfci_date = nfci_latest
        sources.append(f"FRED:NFCI@{nfci_date:%Y-%m-%d}")
        if nfci_value >= 0.5:
            nfci_band = "tight (>+0.5, funding-stress regime)"
        elif nfci_value >= 0.0:
            nfci_band = "modestly tight (0 to +0.5)"
        elif nfci_value >= -0.5:
            nfci_band = "modestly loose (-0.5 to 0)"
        else:
            nfci_band = "very loose (<-0.5, abundant-liquidity regime)"
        lines.append("### NFCI (Chicago Fed funding conditions) — weekly")
        lines.append(f"- NFCI = {nfci_value:+.3f} (FRED, {nfci_date:%Y-%m-%d}) — {nfci_band}")
        lines.append(
            "- Interpretation : NFCI tightening (positive Z, rising) "
            "compresses risk-asset multiples mechanically (SPX-soft via "
            "discount-rate denominator + margin-debt deleveraging) ; "
            "loosening (negative Z, falling) supports multiple expansion "
            "and margin-debt rebuild (SPX-bid). Pass-2 LLM picks "
            "consistent with Pass-1 regime."
        )
        lines.append(
            "- Tetlock invalidation : tight-NFCI SPX-soft thesis is "
            "invalidated if NFCI falls below 0 within 4 sessions AND "
            "VIX-term-structure stays in contango (full-loosening "
            "confirmation) ; loose-NFCI SPX-bid thesis is invalidated "
            "if NFCI rises above +0.3 alongside VIX-term-structure "
            "ratio dropping below 1.00 (liquidity-tightening + tail-"
            "regime co-pricing — the broken-smile crisis configuration)."
        )

    # ─── NFIB SBOI monthly (small business uncertainty) ────────────
    # NFIB Small Business Optimism Index. 1986=100 base. Survey month
    # 1-month lag vs publish month. Leading indicator for hiring and
    # capex plans — captures broad-economy regime that SPX earnings
    # ultimately track. Monthly cadence : surface as REGIME indicator
    # NOT intraday signal (similar treatment to BTP-Italy in EUR r34).
    sboi_stmt = (
        select(NfibSbetObservation).order_by(desc(NfibSbetObservation.report_month)).limit(2)
    )
    sboi_rows = list((await session.execute(sboi_stmt)).scalars().all())
    if sboi_rows:
        sboi_latest = sboi_rows[0]
        sources.append(f"NFIB:SBOI@{sboi_latest.report_month:%Y-%m}")
        if sboi_latest.sboi >= 100.0:
            sboi_band = "expansionary (>=100, above 1986 baseline)"
        elif sboi_latest.sboi >= 95.0:
            sboi_band = "modestly contractionary (95-100)"
        elif sboi_latest.sboi >= 90.0:
            sboi_band = "contractionary (90-95)"
        else:
            sboi_band = "deeply contractionary (<90, recession-class)"
        lines.append("### NFIB SBOI (Small Business Optimism, monthly)")
        lines.append(
            f"- SBOI = {sboi_latest.sboi:.1f} on {sboi_latest.report_month:%Y-%m} — {sboi_band}"
        )
        if sboi_latest.uncertainty_index is not None:
            lines.append(f"- Uncertainty Index sub-component = {sboi_latest.uncertainty_index:.1f}")
        if len(sboi_rows) >= 2:
            sboi_prior = sboi_rows[1]
            sboi_delta = sboi_latest.sboi - sboi_prior.sboi
            sboi_sign = "+" if sboi_delta >= 0 else "−"
            lines.append(
                f"- 1-month change : {sboi_sign}{abs(sboi_delta):.1f} "
                f"(from {sboi_prior.sboi:.1f} on "
                f"{sboi_prior.report_month:%Y-%m})"
            )
        lines.append(
            "- Frequency mismatch : SBOI is MONTHLY (1-month publish "
            "lag), VIX/NFCI are DAILY/WEEKLY. Treat as REGIME indicator "
            "NOT intraday signal. Interpretation : SBOI rising in "
            "calm-NFCI regime is broad-economy reflation (SPX-bid via "
            "earnings-tail expansion + margin-debt rebuild) ; SBOI "
            "falling in tight-NFCI regime is the recession-class "
            "configuration (SPX-soft via earnings-tail compression "
            "+ multiple contraction)."
        )
        lines.append(
            "- Tetlock invalidation : expansionary-SBOI SPX-bid thesis "
            "is invalidated if SBOI falls below 95 within 2 monthly "
            "prints AND NFCI rises above 0 concurrent ; contractionary-"
            "SBOI SPX-soft thesis is invalidated if SBOI rebounds above "
            "100 alongside NFCI falling below -0.3 (full-reflation "
            "confirmation in slow-cadence)."
        )

    # ─── SPX 3-driver composite (R24 SUBSET-not-SUPERSET clears) ────
    # Surface ONLY when ALL 3 drivers fresh — the framework needs the
    # 3-driver pairing to disambiguate broken-smile-crisis from
    # transitional-regime-noise.
    if vxv_latest is not None and nfci_latest is not None and sboi_rows:
        lines.append("### SPX VIX-funding-sentiment triangle composite")
        lines.append(
            "- The 3-driver SPX pricing framework is FULLY available "
            "for this asset (R24 SUBSET-not-SUPERSET clears : VIX/VXV "
            "daily + NFCI weekly + SBOI monthly cadences). When "
            "VIX-term-structure CONTANGO AND NFCI < 0 AND SBOI >= 100 "
            "the regime is broad-risk-on (SPX-bid high conviction) ; "
            "BACKWARDATION combined with NFCI > 0 OR SBOI < 95 is the "
            "tail-stress-funding-stress-or-sentiment-stress 3-corner-"
            "bear configuration (SPX-soft high conviction, Brunnermeier-"
            "Pedersen 2009 funding-liquidity-spiral crisis configuration "
            "— the SPX-equity analogue of the Stephen Jen USD broken-"
            "smile, applied to the vol-funding doom loop). Note the "
            "AND/OR asymmetry between the broad-risk-on (3-of-3 AND) "
            "and 3-corner-bear (1-of-2 OR with VIX-backwardation "
            "anchor) configurations is intentional : empirically "
            "vol-and-funding stress propagates faster than calm-regime "
            "accumulation, so weaker bear evidence justifies higher "
            "conviction than equally-weak bull evidence. The Pass-2 "
            "LLM should triangulate all 3 dimensions before committing "
            "to a directional read. SPY-proxy caveat (ADR-089) applies "
            "to quantitative claims only — directional framing unchanged."
        )

    return "\n".join(lines), sources


async def _section_jpy_specific(session: AsyncSession, asset: str) -> tuple[str, list[str]]:
    """## JPY-specific signals — US-JP rate-differential triangulation (r45, GAP-A continuation 4/5).

    Renders USD/JPY-specific macro signals for USD_JPY Pass-2 via the
    canonical Engel-West 2005 rate-differential channel + Brunnermeier-
    Nagel-Pedersen 2009 carry-crash skew framework. Tier 1 inline-FRED
    ship per ADR-092 PROPOSED round-44 (degraded SUPERSET, BTP r34
    cadence-mismatch precedent) :

      1. **Japan 10Y monthly via FRED `IRLTLT01JPM156N`** — primary
         JPY-specific anchor. Source : OECD MEI monthly with 1-month
         publication lag. Registry max-age 120d (r37 frequency-aware).
         Framework : Engel-West 2005 "Exchange Rates and Fundamentals",
         J.Political Economy 113(3):485-517, DOI:10.1086/429137 — under
         near-unity discount factor, rate-differential proxies USD/JPY
         directional bias even when fundamentals are quasi-martingale.
      2. **US 10Y daily via FRED `DGS10`** — differential anchor. Source :
         FRED `DGS10` daily, default 14d max-age. Computed differential
         (DGS10 - IRLTLT01JPM156N) is the canonical institutional carry
         signal. Framework : Adrian-Etula-Muir 2014 "Financial
         Intermediaries and the Cross-Section of Asset Returns",
         J.Finance 69(6):2557-2596, DOI:10.1111/jofi.12189 — broker-
         dealer leverage factor transmits carry-funding stress.

    Gated on `asset == "USD_JPY"` — early-return ("", []) otherwise.
    `build_data_pool` appends only when `sources` is non-empty so a
    pre-FRED-ingestion USD_JPY silently skips.

    SYMMETRIC LANGUAGE discipline (ichor-trader r32/r41/r42/r43 carry-
    forward) : the rate-differential interpretation emits BOTH USD-bid
    (carry-bid regime) AND JPY-bid (carry-unwind regime) branches so
    the Pass-2 LLM picks consistent with Pass-1 regime. The USD_JPY
    cross-asset matrix stub at `data_pool.py` line ~2878 was 2 lines
    uni-directional pre-r45 (`vol_elevated → JPY-bid safe haven` +
    `inflation_pressure_up → UST yield up → USD-bid`) ; r46-round-2
    extended that stub to a symmetric mirror with Tetlock invalidation.
    This `_section_jpy_specific` section adds the rate-differential
    layer for JPY with regime-conditional symmetry (parametric in the
    DGS10 + IRLTLT01JPM156N FRED data, complementary to the macro-
    state-conditional hints in the cross-asset matrix).

    TETLOCK INVALIDATION discipline on the differential reading (r42 R28 +
    r43 carry-forward) : both regime-conditional branches emit explicit
    invalidation thresholds with VIX-cross-confirmation, derived from
    Brunnermeier-Nagel-Pedersen 2009 NBER Macro Annual 23(1):313-348
    DOI:10.1086/593088 carry-crash cascade configuration.

    R24 SUBSET-not-SUPERSET cleared via cadence-mismatch BTP r34
    precedent : DGS10 daily + IRLTLT01JPM156N monthly. Frequency
    mismatch warning emitted inline ; differential surfaces as REGIME
    indicator, NOT intraday signal.

    Tier 2 BoJ JGB 10Y daily collector deferred to ADR-094 (PROPOSED
    after Eliot UI confirms BoJ Time-Series stat-search.boj.or.jp series
    code per ADR-092 §T2.JPY-Daily). MoF FX intervention monthly via
    e-Stat deferred to ADR-095 (Ito-Yabu 2007 reaction function,
    DOI:10.1016/j.jimonfin.2006.12.001 corrected per round-44 verifier).
    """
    if asset != "USD_JPY":
        return "", []

    # ─── Japan 10Y monthly via FRED IRLTLT01JPM156N (Japan-specific anchor) ──
    # Primary JPY driver. If absent → silent skip (no JPY-specific value
    # without the Japan anchor). Registry max_age 120d auto-resolves per
    # r37 frequency-aware lookup.
    jp10y_latest = await _latest_fred(session, "IRLTLT01JPM156N")
    if jp10y_latest is None:
        return "", []  # JP 10Y missing → silent skip (primary anchor)
    jp10y_value, jp10y_date = jp10y_latest
    sources = [f"FRED:IRLTLT01JPM156N@{jp10y_date:%Y-%m-%d}"]

    lines = [
        "## JPY-specific signals (Engel-West rate-differential channel)",
        "### Japan 10Y yield (IRLTLT01JPM156N) — OECD MEI monthly, Japan-specific anchor",
        f"- JP 10Y = {jp10y_value:.2f}% (FRED IRLTLT01JPM156N, {jp10y_date:%Y-%m-%d} "
        "— OECD monthly, 1-month publication lag)",
    ]

    # ─── US 10Y daily via FRED DGS10 (differential anchor) ──
    # Secondary driver — computes the US-JP 10Y differential, the
    # canonical institutional carry-funding signal per Adrian-Etula-Muir
    # 2014 financial-intermediary-leverage channel.
    dgs10_latest = await _latest_fred(session, "DGS10")
    if dgs10_latest is not None:
        dgs10_value, dgs10_date = dgs10_latest
        sources.append(f"FRED:DGS10@{dgs10_date:%Y-%m-%d}")
        rate_diff = dgs10_value - jp10y_value
        lines.append("### US 10Y nominal yield (DGS10) — daily differential anchor")
        lines.append(f"- DGS10 = {dgs10_value:.2f}% (FRED, {dgs10_date:%Y-%m-%d})")
        lines.append(f"- US-JP 10Y differential = {rate_diff:+.2f} pp (DGS10 minus JP 10Y)")
        lines.append(
            "- Frequency mismatch : DGS10 is DAILY, JP 10Y is MONTHLY "
            "(OECD MEI). Treat the differential as a REGIME indicator, "
            "NOT an intraday signal (BTP r34 precedent for cadence-"
            "mismatch handling)."
        )
        lines.append(
            "- Interpretation depends on the Pass-1 regime label : in a "
            "carry-bid regime (goldilocks, vol_complacent), a wider "
            "differential supports USD/JPY upside via JPY-funded carry "
            "positioning accumulation (Adrian-Etula-Muir 2014 broker-"
            "dealer balance-sheet channel transmits the rate-spread to "
            "FX pricing via intermediary-funding capacity) ; under risk-"
            "off or vol_elevated, the SAME wider differential can flip "
            "to JPY-bid via carry-unwind cascade (Brunnermeier-Nagel-"
            "Pedersen 2009 currency-crash skew — JPY-funded carry-shorts "
            "unwinding amplify the JPY-positive move non-linearly). A "
            "narrower differential is the symmetric reverse (USD-soft "
            "in carry-bid regime, JPY-soft in risk-off as carry "
            "rebuilds). The Pass-2 LLM should select the branch matching "
            "the regime context above."
        )
        lines.append(
            "- Tetlock invalidation : wider-differential USD-bid carry "
            "thesis is invalidated if VIX > 25 AND US-JP 10Y narrows by "
            "> 20 bp within 5 sessions concurrent (full carry-unwind "
            "regime onset, Brunnermeier-Nagel-Pedersen 2009 cascade "
            "configuration) ; carry-unwind JPY-bid thesis is invalidated "
            "if VIX falls below 18 AND DGS10 rises by > 15 bp within 5 "
            "sessions (calm-regime re-anchoring confirmed, carry-bid "
            "framework reasserts ; threshold symmetric vs carry-unwind "
            "20-bp magnitude per ichor-trader r45 review). "
            "Note : BoJ intervention tail-risk (Ito-Yabu 2007 reaction "
            "function, DOI:10.1016/j.jimonfin.2006.12.001) is a separate "
            "signal deferred to ADR-095 (e-Stat MoF FX intervention "
            "monthly collector)."
        )

        # Composite (R24 SUBSET-not-SUPERSET via cadence-mismatch BTP r34 precedent)
        lines.append(
            "### JPY rate-differential triangle (Engel-West + Brunnermeier-Nagel-Pedersen)"
        )
        lines.append(
            "- The 2-driver JPY pricing framework is AVAILABLE for this "
            "asset (R24 SUBSET-not-SUPERSET cleared via cadence-mismatch "
            "BTP r34 precedent : DGS10 daily + JP 10Y monthly). The Engel-"
            "West 2005 fundamentals channel (DOI:10.1086/429137) transmits "
            "rate-differential to USD/JPY directional bias via near-unity "
            "discount factor — the spot rate is quasi-martingale yet "
            "fundamentals still determine the level. Brunnermeier-Nagel-"
            "Pedersen 2009 carry-crash skew (DOI:10.1086/593088) amplifies "
            "the same signal under risk-off via JPY-funded short positions "
            "unwinding non-linearly. Pass-2 LLM should triangulate both "
            "regime-conditional branches before committing to a directional "
            "read. Tetlock invalidation thresholds emit asymmetric regime-"
            "flip conditions consistent with r43 SPX precedent."
        )

    return "\n".join(lines), sources


async def _section_aud_specific(session: AsyncSession, asset: str) -> tuple[str, list[str]]:
    """## AUD-specific signals — commodity-currency triangulation (r46, GAP-A continuation 5/5).

    Renders AUD/USD-specific macro signals for AUD_USD Pass-2 via 3-driver
    framework. Tier 1 inline-FRED ship per ADR-092 PROPOSED round-44 +
    ADR-093 PROPOSED round-46 "degraded explicit" surface pattern. R24
    SUBSET-not-SUPERSET cleared via "degraded explicit" annotation — all
    3 drivers are MONTHLY cadence, ZERO daily-clean signal (iron-ore daily
    DEFER firmly per ADR-093 Voie D cost-benefit) :

      1. **Australia-Fed rate differential** (Engel-West channel) —
         primary AUD anchor. Source : FRED `IRLTLT01AUM156N` (AU 10Y
         monthly, OECD MEI 1-month publication lag, registry max-age 120d)
         paired with `DGS10` (US 10Y daily) for the differential. Framework :
         Engel-West 2005 "Exchange Rates and Fundamentals", J.Political
         Economy 113(3):485-517, DOI:10.1086/429137 — rate-differential
         proxies AUD/USD directional bias under near-unity discount factor.
      2. **China credit-impulse proxy** (Chen-Rogoff commodity-currency
         channel) — secondary AUD driver via China demand transmission.
         Source : FRED `MYAGM1CNM189N` (China M1 monthly = currency +
         demand deposits, IMF-IFS sourced, registry max-age 60d). NB :
         this is a r46-round-2 audit swap from the original `MYAGM2CNM189N`
         (M2 broad-money) which was empirically DISCONTINUED Aug 2019 per
         IMF IFS / FRED. M1 is narrower than M2 but PRESERVES the canonical
         Chen-Rogoff 2003 transmission proxy — M1 YoY surges historically
         lead CFETS commodity demand by ~3-6 months per Barcelona-Cascaldi-
         Garcia-Hoek-Van Leemput 2022 Fed IFDP 1360 "What Happens in China
         Does Not Stay in China". Frameworks : Chen-Rogoff 2003 "Commodity
         currencies", J.Int.Economics 60(1):133-160, DOI:10.1016/S0022-
         1996(02)00072-7 — commodity terms-of-trade transmitted to AUD
         spot in real time via the China-property-construction channel ;
         Barcelona et al. 2022 Fed IFDP 1360 — M1 leading-indicator
         empirics for AUD ; Ferriani-Gazzani 2025 CEPR — China monetary
         policy commodity-channel primary AUD transmission. NB : M1 is a
         PROXY for credit impulse, NOT direct TSF — Total Social Financing
         (TSF) direct collector deferred per ADR-092 §DEFER firmly (PBoC
         HTML scrape, Trading Economics rate-limit blocker).
      3. **Commodity terms-of-trade composite** (Ready-Roussanov-Ward
         carry-commodity channel) — tertiary AUD driver via base-metals
         complex. Source : FRED `PIORECRUSDM` (Global Iron Ore Price Index
         monthly) + `PCOPPUSDM` (Global Copper Price Index monthly), both
         IMF World Bank pinkbook composite, registry max-age 60d each.
         Framework : Ready-Roussanov-Ward 2017 "Commodity Trade and the
         Carry Trade: A Tale of Two Countries", J.Finance 72(6):2629-2684,
         DOI:10.1111/jofi.12546 — commodity-exporter currencies (AUD/CAD)
         co-move with terms-of-trade ; structural carry premium emerges
         from commodity-exporter / final-goods-producer specialization.

    Gated on `asset == "AUD_USD"` — early-return ("", []) otherwise.
    Primary-anchor gate on `IRLTLT01AUM156N` : silent skip if absent (no
    AUD-specific value without the Australia anchor). `build_data_pool`
    appends only when `sources` is non-empty so a pre-FRED-ingestion
    AUD_USD silently skips.

    DEGRADED EXPLICIT surface pattern (ADR-093) : the section header AND
    composite triangle paragraph BOTH cite ADR-093 by number. The
    annotation surfaces that all 3 drivers are monthly, that DGS10 daily
    is the only daily anchor (used solely for the rate-differential
    computation), that the section is a REGIME indicator NOT an intraday
    signal, and that the iron-ore daily feed gap is the empirical reason
    for the degraded posture (deferred per Voie D cost-benefit). Future
    upgrade path : ADR-096 RBA F1.1 CSV daily would shift the daily-clean
    count to 1-of-3 ; AKShare/LME re-vetting would shift to 2-of-3.

    SYMMETRIC LANGUAGE discipline (ichor-trader r32/r41/r42/r43/r45 carry-
    forward) : each driver paragraph emits BOTH AUD-bid (carry-bid regime,
    commodity reflation, China credit expansion) AND AUD-soft (carry-
    unwind, commodity deflation, China credit contraction) regime-
    conditional branches so the Pass-2 LLM picks consistent with Pass-1
    regime. The AUD_USD cross-asset matrix hints at `data_pool.py` line
    ~2885 were pre-r46 a 2-line uni-directional stub ; r46-round-2
    extends to a symmetric mirror with Tetlock invalidation thresholds
    (commodity-currency-first-to-unwind cascade in risk-off, broad
    commodity-reflation in carry-bid regime). This `_section_aud_specific`
    adds the empirical layer parametric in the FRED data (China M1 +
    iron-ore + copper), complementary to the macro-state-conditional
    hints in the cross-asset matrix.

    SIGN CONVENTION : rate-differential is computed as `US - AU` (DGS10
    minus AU 10Y) to match the legacy `_section_rate_diff` convention
    (line ~1832 + `_RATE_DIFF_PAIRS` line ~155) and avoid the dual-sign
    landmine flagged by ichor-trader r46 pre-merge review. JPY r45
    follows the same `US - foreign` convention. WIDER POSITIVE US-AU =
    US fundamentals stronger than AU → USD-bid via Engel-West channel ;
    NARROWING / NEGATIVE US-AU = AU fundamentals catching up to or
    surpassing US → AUD-bid via the same channel.

    TETLOCK INVALIDATION discipline on ALL 3 drivers (r39 codified,
    r42+r43+r45 carry-forward). Magnitudes pinned at the monthly cadence
    (2-month thresholds, NOT n-day — consistent with the degraded-explicit
    REGIME-indicator framing).
    """
    if asset != "AUD_USD":
        return "", []

    # ─── Australia 10Y monthly via FRED IRLTLT01AUM156N (Australia-specific anchor) ──
    # Primary AUD driver. If absent → silent skip (no AUD-specific value
    # without the Australia anchor). Registry max_age 120d auto-resolves
    # per r37 frequency-aware lookup.
    au10y_latest = await _latest_fred(session, "IRLTLT01AUM156N")
    if au10y_latest is None:
        return "", []  # AU 10Y missing → silent skip (primary anchor)
    au10y_value, au10y_date = au10y_latest
    sources = [f"FRED:IRLTLT01AUM156N@{au10y_date:%Y-%m-%d}"]

    lines = [
        "## AUD-specific signals (degraded explicit per ADR-093 — commodity surface gap)",
        "### Australia 10Y yield (IRLTLT01AUM156N) — OECD MEI monthly, Australia-specific anchor",
        f"- AU 10Y = {au10y_value:.2f}% (FRED IRLTLT01AUM156N, {au10y_date:%Y-%m-%d} "
        "— OECD monthly, 1-month publication lag)",
    ]

    # ─── US 10Y daily via FRED DGS10 (rate-differential anchor) ──
    # Computes the AU-Fed 10Y differential. DGS10 daily is the ONLY daily
    # anchor in this section (used solely for the differential computation).
    # The differential itself is a REGIME indicator (cadence mismatch with
    # AU 10Y monthly), NOT an intraday signal.
    dgs10_latest = await _latest_fred(session, "DGS10")
    if dgs10_latest is not None:
        dgs10_value, dgs10_date = dgs10_latest
        sources.append(f"FRED:DGS10@{dgs10_date:%Y-%m-%d}")
        # SIGN convention : US - AU to match _section_rate_diff legacy
        # `US - foreign` pattern (line ~1832, _RATE_DIFF_PAIRS line ~155).
        # JPY r45 follows the same convention. Flipping AUD r46 prevents
        # the dual-sign landmine flagged by ichor-trader pre-merge review.
        rate_diff = dgs10_value - au10y_value
        lines.append("### US 10Y nominal yield (DGS10) — daily differential anchor")
        lines.append(f"- DGS10 = {dgs10_value:.2f}% (FRED, {dgs10_date:%Y-%m-%d})")
        lines.append(f"- US-AU 10Y differential = {rate_diff:+.2f} pp (DGS10 minus AU 10Y)")
        lines.append(
            "- Frequency mismatch : DGS10 is DAILY, AU 10Y is MONTHLY "
            "(OECD MEI). Treat the differential as a REGIME indicator, "
            "NOT an intraday signal (BTP r34 + JPY r45 cadence-mismatch "
            "precedent)."
        )
        lines.append(
            "- Interpretation depends on the Pass-1 regime label : in a "
            "carry-bid regime (goldilocks, vol_complacent), a WIDER "
            "POSITIVE US-AU differential supports USD-bid via Engel-"
            "West 2005 near-unity-discount fundamentals channel "
            "(DOI:10.1086/429137 — higher-yielding currency strengthens "
            "under fundamentals transmission) reinforced by AUD-funded "
            "USD carry positioning accumulation → AUD-soft ; under risk-"
            "off or vol_elevated, the SAME wider POSITIVE US-AU "
            "differential persists USD-bid via flight-to-quality + "
            "commodity collapse (Ready-Roussanov-Ward 2017 commodity-"
            "currency carry-and-commodity-tail double cascade, "
            "DOI:10.1111/jofi.12546) → AUD-soft. A NARROWING POSITIVE "
            "OR NEGATIVE US-AU differential (AU yields catching up to "
            "or surpassing US) is the symmetric reverse : AUD-bid in "
            "carry-bid regime via the same fundamentals channel ; AUD-"
            "bid persists in stress only when commodity reflation co-"
            "confirms (Driver 3 above-baseline). The Pass-2 LLM should "
            "select the branch matching the regime context above."
        )
        lines.append(
            "- Tetlock invalidation : NARROWING-or-NEGATIVE-US-AU AUD-"
            "bid carry thesis is invalidated if US-AU differential "
            "WIDENS POSITIVE by > 30 bp across 2 consecutive monthly "
            "prints AND DXY rises by > 2.0% within 20 sessions "
            "concurrent (US fundamentals re-asserting + broad USD-bid "
            "co-confirmation, full carry-unwind regime onset, commodity-"
            "currency-first-to-unwind cascade) ; WIDER-POSITIVE-US-AU "
            "USD-bid thesis is invalidated if US-AU differential "
            "NARROWS by > 25 bp across 2 monthly prints AND DXY falls "
            "below its trailing 6-month mean within 20 sessions "
            "concurrent (AU fundamentals catching up + USD softening "
            "co-confirmation, calm-regime re-anchoring AUD-bid framework "
            "reasserts ; magnitude symmetric vs the 30-bp WIDEN-positive "
            "threshold per ichor-trader r46 post-sign-flip review). "
            "Pass-2 LLM should reference the trailing 2 FRED prints from "
            "the data_pool context window if visible, else flag the "
            "Tetlock as pending next monthly print."
        )

    # ─── China M1 monthly via FRED MYAGM1CNM189N (credit-impulse proxy) ──
    # Secondary AUD driver via Chen-Rogoff 2003 commodity-currency channel.
    # M1 YoY growth is a documented leading indicator of iron-ore demand
    # via the China-property-construction transmission mechanism (Barcelona-
    # Cascaldi-Garcia-Hoek-Van Leemput 2022 Fed IFDP 1360). r46-round-2 swap
    # from MYAGM2CNM189N (DISCONTINUED Aug 2019, ~6y stale per FRED).
    china_m1_latest = await _latest_fred(session, "MYAGM1CNM189N")
    if china_m1_latest is not None:
        china_m1_value, china_m1_date = china_m1_latest
        sources.append(f"FRED:MYAGM1CNM189N@{china_m1_date:%Y-%m-%d}")
        lines.append(
            "### China M1 (MYAGM1CNM189N) — currency + demand deposits, credit-impulse proxy"
        )
        lines.append(
            f"- China M1 = {china_m1_value:,.0f} CNY-bn (FRED MYAGM1CNM189N, "
            f"{china_m1_date:%Y-%m-%d} — IMF IFS monthly, 1-2 month "
            "publication lag). STOCK measure ; absent trailing 12-month "
            "context in this render (single-print constraint), the Pass-"
            "2 LLM SHOULD NOT extrapolate direction-of-travel from this "
            "single observation. Treat as baseline level marker only. "
            "YoY growth computation at the data-pool layer is deferred "
            "to round-47+ refinement if AUD anti-skill emerges in Vovk "
            "Sunday aggregator (ichor-trader r46 YELLOW-2 review)."
        )
        lines.append(
            "- NB : M1 (currency + demand deposits) is a NARROWER aggregate "
            "than M2 but PRESERVES the Chen-Rogoff 2003 commodity-currency "
            "transmission proxy (Barcelona et al. 2022 Fed IFDP 1360 — M1 "
            "YoY surges historically lead CFETS commodity demand by ~3-6 "
            "months ; Ferriani-Gazzani 2025 CEPR — commodity channel is "
            "PRIMARY China→AUD transmission, M1 is the canonical PBoC-"
            "policy-stance proxy). Original r46 ship targeted MYAGM2CNM189N "
            "which was empirically DISCONTINUED Aug 2019 per IMF IFS / FRED "
            "(r46-round-2 audit caught the dead-series bug). M1 is a PROXY "
            "for credit impulse, NOT direct TSF — Total Social Financing "
            "direct collector deferred per ADR-092 §DEFER firmly (PBoC HTML "
            "scrape + Trading Economics free-tier rate-limit blocker). M1 "
            "captures the narrow-money / transactions-demand side of the "
            "credit cycle ; CRDQCNAPUBIS (BIS Total Credit, quarterly) is a "
            "deferred r47+ complement per the r46-round-2 researcher audit."
        )
        lines.append(
            "- Interpretation depends on the Pass-1 regime label : in a "
            "China-credit-expansion regime (rising M1 YoY + PBoC easing "
            "cycle), commodity demand strengthens and AUD-bid emerges "
            "via Chen-Rogoff 2003 commodity-currency transmission "
            "(DOI:10.1016/S0022-1996(02)00072-7 — terms-of-trade "
            "transmitted to AUD spot in real time) ; in a contraction "
            "regime (M1 YoY decelerating + PBoC tightening or property "
            "deleverage), commodity demand softens and AUD-soft is the "
            "symmetric expectation. The Pass-2 LLM should select the "
            "branch matching the regime context above."
        )
        lines.append(
            "- Tetlock invalidation : China-expansion AUD-bid thesis is "
            "invalidated if M1 prints below its trailing 12-month mean "
            "across 2 consecutive monthly prints AND iron-ore composite "
            "(see Driver 3) prints below its trailing 6-month mean "
            "concurrent (full China-deceleration confirmation) ; "
            "contraction AUD-soft thesis is invalidated if M1 rebounds "
            "above its trailing 12-month mean AND iron-ore composite "
            "prints above the same trailing baseline (full reflation "
            "confirmation in slow-cadence). Pass-2 LLM should reference "
            "the trailing 12 FRED prints from the data_pool context "
            "window if visible, else flag the Tetlock as pending next "
            "monthly print."
        )

    # ─── Commodity terms-of-trade composite (iron ore + copper) ──
    # Tertiary AUD driver via Ready-Roussanov-Ward 2017 carry-commodity
    # channel. Iron-ore is the PRIMARY signal (Australia is the largest
    # global exporter) ; copper is the CROSS-CONFIRMATION via base-metals
    # complex co-move. Both monthly cadence, IMF World Bank pinkbook
    # composite. Outer gate on `iron_latest is not None` per ichor-trader
    # r46 M1/YELLOW-1 review : copper alone (without iron primary) is
    # meaningless for the AUD commodity-currency framing, so the entire
    # Driver 3 silently skips when iron-ore data is absent.
    iron_latest = await _latest_fred(session, "PIORECRUSDM")
    copper_latest = await _latest_fred(session, "PCOPPUSDM")
    if iron_latest is not None:
        iron_value, iron_date = iron_latest
        sources.append(f"FRED:PIORECRUSDM@{iron_date:%Y-%m-%d}")
        lines.append("### Commodity terms-of-trade composite (iron ore + copper)")
        lines.append(
            f"- Iron Ore (PIORECRUSDM) = {iron_value:.2f} index "
            f"(FRED, {iron_date:%Y-%m-%d} — IMF World Bank pinkbook "
            "composite monthly, AUD-positive commodity ToT primary "
            "anchor since Australia is the largest global exporter)"
        )
        if copper_latest is not None:
            copper_value, copper_date = copper_latest
            sources.append(f"FRED:PCOPPUSDM@{copper_date:%Y-%m-%d}")
            lines.append(
                f"- Copper (PCOPPUSDM) = {copper_value:.2f} index "
                f"(FRED, {copper_date:%Y-%m-%d} — same source family, "
                "cross-confirmation via base-metals complex co-move)"
            )
        lines.append(
            "- Staleness caveat (r94, ADR-092 §Round-94) : PIORECRUSDM + "
            "PCOPPUSDM are IMF-PCPS MONTHLY series with a ~2-week-after-"
            "month-end publication lag, so the as-of dates above are "
            "inherently ~2.5-4 months behind spot (registry tolerance "
            "widened 60→120 d after the r93 false-DEGRADED triage). Treat "
            "this composite as a SLOW terms-of-trade REGIME marker only ; "
            "the Pass-2 LLM SHOULD NOT extrapolate near-term direction "
            "from a single stale monthly print, and SHOULD cross-check "
            "the iron/copper as-of dates against the AU-10Y and DGS10 "
            "as-of dates above before triangulating the 3-driver "
            "composite (mirrors the China-M1 single-print constraint)."
        )
        lines.append(
            "- Interpretation : iron-ore rising in a China-expansion "
            "regime is the canonical AUD-bid configuration (Chen-Rogoff "
            "2003 + Ready-Roussanov-Ward 2017 commodity-final-goods "
            "specialization, DOI:10.1111/jofi.12546 — commodity-exporter "
            "currencies co-move with terms-of-trade) ; iron-ore falling "
            "in a tightening or risk-off regime amplifies AUD-soft via "
            "the carry-and-commodity-tail double cascade. Copper "
            "co-moving with iron-ore confirms the base-metals-complex "
            "signal ; copper diverging (e.g. iron-ore down + copper "
            "flat-or-up) suggests an Australia-specific iron-ore demand "
            "shock without broader commodity collapse, which is a "
            "moderate AUD-soft (not the full 3-corner bear). The Pass-2 "
            "LLM should select the branch matching the regime context "
            "above."
        )
        if copper_latest is not None:
            lines.append(
                "- Tetlock invalidation : iron-ore AUD-bid thesis is "
                "invalidated if iron-ore prints below its trailing 6-"
                "month mean across 2 consecutive monthly prints AND "
                "copper co-confirms (below same baseline) AND DXY rises "
                "by > 2.0% within 20 sessions concurrent (full commodity-"
                "collapse + USD-bid double-tightening) ; iron-ore AUD-"
                "soft thesis is invalidated if iron-ore rebounds above "
                "its trailing 6-month mean AND copper co-confirms AND "
                "China M1 prints above its trailing 12-month mean "
                "concurrent (full reflation confirmation across all 3 "
                "drivers). Pass-2 LLM should reference the trailing 6 "
                "FRED prints from the data_pool context window if "
                "visible, else flag the Tetlock as pending next monthly "
                "print."
            )
        else:
            lines.append(
                "- Tetlock invalidation (PARTIAL — copper cross-"
                "confirmation absent this render) : iron-ore AUD-bid "
                "thesis is invalidated if iron-ore prints below its "
                "trailing 6-month mean across 2 consecutive monthly "
                "prints AND DXY rises by > 2.0% within 20 sessions "
                "concurrent (commodity-collapse + USD-bid co-tightening, "
                "iron-only signal) ; iron-ore AUD-soft thesis is "
                "invalidated if iron-ore rebounds above its trailing 6-"
                "month mean AND China M1 prints above its trailing 12-"
                "month mean (reflation confirmation in 2-of-3 drivers, "
                "partial). Conviction reduced vs the full 3-driver "
                "Tetlock (composite triangle absent this render)."
            )

    # ─── AUD 3-driver composite (R24 SUBSET-not-SUPERSET via degraded explicit) ────
    # Surface ONLY when ALL 3 drivers fresh — the framework needs the
    # 3-driver pairing (rate-diff + China credit + commodity ToT) to
    # disambiguate broad-commodity-currency-cycle from idiosyncratic-
    # Australia-shock. DGS10 is REQUIRED for Driver 1 (rate-diff) so
    # gate on dgs10_latest is non-None. Both iron and copper required
    # for Driver 3 composite (Australia primary + base-metals
    # cross-confirmation).
    if (
        dgs10_latest is not None
        and china_m1_latest is not None
        and iron_latest is not None
        and copper_latest is not None
    ):
        lines.append(
            "### AUD commodity-currency triangle composite (Engel-West + Chen-Rogoff + Ready-Roussanov-Ward)"
        )
        lines.append(
            "- The 3-driver AUD pricing framework is FULLY available "
            "for this asset (R24 SUBSET-not-SUPERSET cleared via "
            "DEGRADED EXPLICIT surface per ADR-093 — commodity surface "
            "gap : 3/3 drivers MONTHLY cadence, ZERO daily-clean signal, "
            "DGS10 is the only daily anchor used solely for the rate-"
            "differential computation). The Engel-West 2005 fundamentals "
            "channel (DOI:10.1086/429137) anchors directionality via "
            "rate-differential ; Chen-Rogoff 2003 commodity-currency "
            "channel (DOI:10.1016/S0022-1996(02)00072-7) transmits "
            "China credit impulse to AUD spot via the property-"
            "construction-iron-ore demand chain ; Ready-Roussanov-Ward "
            "2017 commodity-final-goods specialization (DOI:10.1111/"
            "jofi.12546) explains the structural AUD carry premium. "
            "When US-AU differential NARROWING (AU yields catching up "
            "to or surpassing US) AND China M1 EXPANDING AND iron-ore "
            "+ copper BOTH ABOVE trailing-6m baseline, the regime is "
            "full commodity-currency reflation (AUD-bid high conviction "
            "in carry-bid regime) ; US-AU WIDENING POSITIVE (US "
            "fundamentals re-asserting over AU) AND China M1 "
            "CONTRACTING AND iron-ore + copper BOTH BELOW the same "
            "baseline is the symmetric AUD-soft 3-corner-bear "
            "configuration (carry-unwind + China-deceleration + "
            "commodity-collapse, high conviction). Note the AND/AND "
            "symmetric structure across both regimes is intentional — "
            "unlike SPX r43 where tail-stress propagates faster than "
            "calm accumulation (asymmetric AND/OR), AUD's commodity-"
            "currency cycle is slower-cadence on both sides (months-"
            "quarters) and the empirical evidence asymmetry is "
            "negligible, so equally-weak bull and bear evidence "
            "justifies equal conviction (symmetric AND/AND). The "
            "Pass-2 LLM should treat this section as a REGIME indicator "
            "(NOT intraday signal) and triangulate all 3 dimensions "
            "before committing to a directional read. "
            "Future upgrade path per ADR-093 : ADR-096 RBA F1.1 daily "
            "CSV would shift the daily-clean count to 1-of-3 ; AKShare/"
            "LME re-vetting would shift to 2-of-3 (currently DEFER "
            "firmly per Voie D cost-benefit until AUD anti-skill "
            "emerges in Vovk Sunday aggregator)."
        )

    return "\n".join(lines), sources


async def _section_gbp_specific(session: AsyncSession, asset: str) -> tuple[str, list[str]]:
    """## GBP-specific signals — UK-US rate-differential + sterling risk-premium (r90, ADR-101).

    Renders GBP/USD-specific macro signals for GBP_USD Pass-2 via a
    2-driver framework, mirroring the proven JPY r45 inline-FRED pattern.
    Tier 1 inline-FRED ship per ADR-101 (extends Accepted ADR-092 to
    GBP_USD — the only ADR-083 priority asset previously without a
    per-asset section ; r40 only fixed a generic GBP path bug). ZERO new
    FRED ingestion : both series already polled, GBP already in
    `_RATE_DIFF_PAIRS` :

      1. **UK 10Y monthly via FRED `IRLTLT01GBM156N`** — primary
         GBP-specific anchor. Source : OECD MEI monthly, 1-month
         publication lag. Registry max-age 120d (r37 frequency-aware).
         Framework : Engel-West 2005 "Exchange Rates and Fundamentals",
         J.Political Economy 113(3):485-517, DOI:10.1086/429137 — under
         a near-unity discount factor the spot rate is quasi-martingale
         yet the rate-differential still determines its level (currency-
         agnostic ; applies to GBP exactly as to JPY r45).
      2. **US 10Y daily via FRED `DGS10`** — the Engel-West differential
         anchor : `dgs10 - uk10y` (US minus UK, the `_RATE_DIFF_PAIRS`
         sign convention). Layered ON this — an INDEPENDENT structural
         lens, NOT a reinterpretation of the differential — is Della
         Corte-Sarno-Sestieri 2012 "The Predictive Information Content
         of External Imbalances for Exchange Rate Returns",
         Rev.Econ.Stat. 94(1):100-115, DOI:10.1162/REST_a_00157 : a
         country's net-foreign-asset / current-account position carries
         a time-varying currency risk premium. For sterling (a
         structural current-account-deficit currency) this is an
         ADDITIVE GBP-soft risk premium under UK funding stress (the
         2022 LDI/gilt-crisis configuration), separate from the rate
         differential.

    SIGN-CONVENTION DISCIPLINE (R44 ; the r40 GBP bug class) : GBP/USD
    quotes USD per GBP, so USD is the QUOTE currency — same polarity as
    EUR/USD (`IRLTLT01DEM156N`), OPPOSITE to USD/JPY & USD/CAD where USD
    is the base. A WIDER (more positive) US-UK differential ⟹ US carry
    advantage ⟹ USD-bid ⟹ GBP/USD DOWNSIDE (GBP-soft). This is the
    inverse of the JPY r45 template's "wider differential → USD/JPY
    upside" ; the section states the polarity explicitly so the Pass-2
    LLM cannot mis-apply the JPY-class reading to GBP.

    Gated on `asset == "GBP_USD"` — early-return ("", []) otherwise.
    `build_data_pool` appends only when `sources` is non-empty so a
    pre-FRED-ingestion GBP_USD silently skips.

    SYMMETRIC LANGUAGE discipline (ichor-trader r32/r41/r42/r43 carry-
    forward) : the rate-differential interpretation emits BOTH GBP-soft
    (USD-bid carry regime) AND GBP-bid (sterling rate-advantage regime)
    branches so the Pass-2 LLM picks consistent with the Pass-1 regime.

    TETLOCK INVALIDATION discipline (r42 R28 + r43 carry-forward) : both
    regime-conditional branches emit explicit invalidation thresholds
    with VIX cross-confirmation, asymmetric magnitudes per the JPY r45
    ichor-trader precedent.

    R24 SUBSET-not-SUPERSET cleared via cadence-mismatch BTP r34
    precedent : DGS10 daily + IRLTLT01GBM156N monthly. Frequency
    mismatch warning emitted inline ; the differential surfaces as a
    REGIME indicator, NOT an intraday signal.

    Sterling is NOT a USD safe-haven (Ranaldo-Soderlind 2010,
    DOI:10.1093/rof/rfq007) — surfaced as a one-line caveat, not a
    driver.

    FRONT-END TERM-STRUCTURE REFINEMENT (r103, ADR-101
    §Implementation(r103)) : a third block surfaces the US-UK **3M**
    front-end differential (`DGS3MO` US 3M Treasury CMT daily, already
    polled — minus `IR3TIB01GBM156N` UK 3M interbank, OECD-MEI monthly
    family laggard ~137d / registry-180 r102). It is **NOT a standalone
    "Driver 3"** : a US-UK 3M differential is the SAME nominal-rate
    channel as Driver-1's US-UK 10Y, read at the short end — its
    marginal content is the front-end-vs-long-end decomposition (3M =
    current relative policy stance ; 10Y = cumulative expected stance +
    term premium). Clarida-Galí-Gertler-1998-**motivated** (NOT the CGG
    reaction function itself — a structural policy-rate rule, not a rate
    spread), with explicit FRAMEWORK-ATTRIBUTION + INSTRUMENT-BASIS +
    INDEPENDENCE caveats (ichor-trader r103 R28, Option B —
    lowest-blast-radius, zero new ingestion ; the faithful
    `IR3TIB01USM156N` interbank counterpart EXISTS but is deliberately
    NOT ingested). Guarded on BOTH 3M series present so a
    pre-ingestion GBP_USD silently skips it (Driver-1/2 unaffected).
    R44 polarity SAME as Driver-1 (`dgs3mo − uk3m`, US minus UK ; wider
    ⟹ GBP-soft) ; symmetric branches + Tetlock+VIX invalidation ;
    frequency-mismatch flagged SHARPER than Driver-1 (UK 3M is staler
    than the already-monthly UK 10Y leg).
    """
    if asset != "GBP_USD":
        return "", []

    # ─── UK 10Y monthly via FRED IRLTLT01GBM156N (UK-specific anchor) ──
    # Primary GBP driver. If absent → silent skip (no GBP-specific value
    # without the UK anchor). Registry max-age 120d auto-resolves per
    # r37 frequency-aware lookup (OECD MEI 1-month publication lag).
    uk10y_latest = await _latest_fred(session, "IRLTLT01GBM156N")
    if uk10y_latest is None:
        return "", []  # UK 10Y missing → silent skip (primary anchor)
    uk10y_value, uk10y_date = uk10y_latest
    sources = [f"FRED:IRLTLT01GBM156N@{uk10y_date:%Y-%m-%d}"]

    lines = [
        "## GBP-specific signals (Engel-West rate-differential + sterling risk-premium, ADR-101)",
        "### UK 10Y yield (IRLTLT01GBM156N) — OECD MEI monthly, UK-specific anchor",
        f"- UK 10Y = {uk10y_value:.2f}% (FRED IRLTLT01GBM156N, {uk10y_date:%Y-%m-%d} "
        "— OECD monthly, 1-month publication lag)",
    ]

    # ─── US 10Y daily via FRED DGS10 (differential anchor) ──
    # Secondary driver — computes the US-UK 10Y differential. NOTE the
    # GBP/USD polarity is INVERSE to USD/JPY : USD is the QUOTE currency
    # here (as in EUR/USD), so a wider US-UK differential is GBP-soft.
    dgs10_latest = await _latest_fred(session, "DGS10")
    if dgs10_latest is not None:
        dgs10_value, dgs10_date = dgs10_latest
        sources.append(f"FRED:DGS10@{dgs10_date:%Y-%m-%d}")
        rate_diff = dgs10_value - uk10y_value
        lines.append("### US 10Y nominal yield (DGS10) — daily differential anchor")
        lines.append(f"- DGS10 = {dgs10_value:.2f}% (FRED, {dgs10_date:%Y-%m-%d})")
        lines.append(f"- US-UK 10Y differential = {rate_diff:+.2f} pp (DGS10 minus UK 10Y)")
        lines.append(
            "- Polarity (R44 sign-convention) : GBP/USD quotes USD per "
            "GBP — USD is the QUOTE currency (same as EUR/USD, OPPOSITE "
            "to USD/JPY). A WIDER (more positive) US-UK differential is "
            "USD-bid → GBP/USD DOWNSIDE (GBP-soft) ; a NARROWER or "
            "NEGATIVE differential (UK yield ≥ US) is a sterling rate "
            "advantage → GBP-bid."
        )
        lines.append(
            "- Frequency mismatch : DGS10 is DAILY, UK 10Y is MONTHLY "
            "(OECD MEI). Treat the differential as a REGIME indicator, "
            "NOT an intraday signal (BTP r34 precedent for cadence-"
            "mismatch handling)."
        )
        lines.append(
            "- Interpretation depends on the Pass-1 regime label : in a "
            "calm / carry-bid regime, a wider US-UK 10Y differential "
            "supports GBP/USD downside (GBP-soft) via USD-funded carry "
            "advantage (Engel-West 2005 present-value channel — rate "
            "fundamentals determine the level under a near-unity discount "
            "factor). SEPARATELY — an INDEPENDENT additive lens, NOT a "
            "reinterpretation of the differential — the sterling "
            "external-imbalance risk premium (Della Corte-Sarno-Sestieri "
            "2012 : a net-foreign-asset / current-account position "
            "carries a time-varying currency risk premium) adds its own "
            "GBP-soft pressure under UK funding stress (the 2022 LDI/"
            "gilt-crisis configuration), layered on the Engel-West read. "
            "A narrower or negative "
            "differential is the symmetric reverse : GBP-bid in a calm "
            "regime via gilt carry inflows, but it can still be GBP-soft "
            "if it is UK-inflation-surprise-driven and the risk premium "
            "dominates the carry. The Pass-2 LLM should select the "
            "branch matching the regime context above."
        )
        lines.append(
            "- Tetlock invalidation : the wider-differential GBP-soft "
            "thesis is invalidated if VIX > 25 AND US-UK 10Y narrows by "
            "> 20 bp within 5 sessions concurrent (sterling-funding-"
            "stress regime onset, risk premium repricing) ; the narrow/"
            "negative-differential GBP-bid thesis is invalidated if VIX "
            "falls below 18 AND DGS10 rises by > 15 bp within 5 sessions "
            "(US-rate re-anchoring, USD carry reasserts ; threshold "
            "asymmetric vs the 20-bp magnitude per the JPY r45 ichor-"
            "trader precedent). Note : sterling is NOT a USD safe-haven "
            "— in acute risk-off USD is the bid leg of GBP/USD (Ranaldo-"
            "Soderlind 2010, DOI:10.1093/rof/rfq007) ; this is a "
            "qualitative caveat, not a driver."
        )

        # ─── Front-end term-structure refinement of Driver-1 (US-UK 3M) ──
        # r103 ADR-101 §Implementation(r103). NOT a standalone "Driver 3"
        # — a US-UK 3M differential is the SAME nominal-rate channel as
        # Driver-1's US-UK 10Y, read at the short end ; marginal content
        # = the front-end-vs-long-end decomposition. DGS3MO (US 3M
        # Treasury CMT, daily, already polled fred_extended.py:26) minus
        # IR3TIB01GBM156N (UK 3M interbank, OECD-MEI monthly family
        # laggard ~137d / registry-180 r102). Clarida-Galí-Gertler-1998-
        # MOTIVATED (NOT the CGG reaction function itself — a structural
        # policy-rate rule, not a rate spread). Guarded on BOTH series
        # present so a pre-ingestion GBP_USD silently skips it (Driver-1/2
        # unaffected — purely additive, ichor-trader r103 R28 Option B,
        # zero new ingestion, lowest blast-radius).
        uk3m_latest = await _latest_fred(session, "IR3TIB01GBM156N")
        dgs3mo_latest = await _latest_fred(session, "DGS3MO")
        if uk3m_latest is not None and dgs3mo_latest is not None:
            uk3m_value, uk3m_date = uk3m_latest
            dgs3mo_value, dgs3mo_date = dgs3mo_latest
            sources.append(f"FRED:IR3TIB01GBM156N@{uk3m_date:%Y-%m-%d}")
            sources.append(f"FRED:DGS3MO@{dgs3mo_date:%Y-%m-%d}")
            front_diff = dgs3mo_value - uk3m_value
            lines.append(
                "### Front-end policy-rate-proxy differential (US-UK 3M) "
                "— a TERM-STRUCTURE REFINEMENT of Driver-1, "
                "Clarida-Gali-Gertler-1998-motivated"
            )
            lines.append(
                f"- US 3M = {dgs3mo_value:.2f}% (FRED DGS3MO, "
                f"{dgs3mo_date:%Y-%m-%d} — US 3-Month Treasury constant "
                f"maturity, DAILY, ~4d lag) ; UK 3M = {uk3m_value:.2f}% "
                f"(FRED IR3TIB01GBM156N, {uk3m_date:%Y-%m-%d} — UK "
                "3-Month interbank, OECD-MEI MONTHLY, documented family "
                "laggard ~4-6 months stale, max-age 180d per ADR-101 "
                "§Impl(r102))."
            )
            lines.append(
                f"- US-UK 3M front-end differential = {front_diff:+.2f} pp "
                "(DGS3MO minus UK 3M interbank)."
            )
            lines.append(
                "- FRAMEWORK ATTRIBUTION (calibrated honesty) : this is "
                "the front-end (policy-stance) complement to Driver-1's "
                "US-UK 10Y long-rate differential, MOTIVATED BY Clarida, "
                "Gali & Gertler 1998 (EER 42(6):1033-1067, "
                "DOI:10.1016/S0014-2921(98)00016-6 — a forward-looking "
                "central-bank reaction-function paper). It is NOT a "
                "structural estimate of either central bank's reaction "
                "function ; it is a front-end RATE-PROXY differential. "
                "INSTRUMENT-BASIS CAVEAT : the US leg (DGS3MO) is a "
                "risk-free Treasury constant-maturity rate, the UK leg "
                "(IR3TIB01GBM156N) is an interbank rate — a TED-spread-"
                "class interbank-credit / term-premium wedge separates "
                "them ; in the current regime the front-end T-bill tracks "
                "the policy rate closely so the basis is second-order vs "
                "the policy-stance signal, but the pair is NOT a pure "
                "same-instrument 3M-vs-3M interbank pair (a faithful "
                "IR3TIB01USM156N US-3M-interbank counterpart EXISTS at "
                "FRED but is deliberately NOT ingested — lowest-blast-"
                "radius per ADR-101 §Reversibility, recorded ADR-101 "
                "§Implementation(r103))."
            )
            lines.append(
                "- INDEPENDENCE CAVEAT (ichor-trader r90/r103 over-claim "
                "discipline) : this front-end differential is NOT an "
                "independent driver co-equal with Driver-1 — it is the "
                "SAME US-UK nominal-rate-differential channel read at the "
                "SHORT end of the curve. Its genuine marginal content is "
                "the relative-curve-shape / front-end-vs-long-end "
                "decomposition (3M = current relative policy stance ; "
                "10Y = cumulative expected stance + term premium). It "
                "REFINES, it does not duplicate-as-new, the Engel-West "
                "Driver-1 read. (Contrast Driver-2 Della Corte-Sarno-"
                "Sestieri 2012, which IS independent — a different state "
                "variable, the NFA / current-account position.)"
            )
            lines.append(
                "- Polarity (R44) : SAME as Driver-1 — USD is the GBP/USD "
                "QUOTE currency ; a WIDER (more positive) US-UK 3M "
                "differential ⟹ relative US front-end / policy carry "
                "advantage ⟹ USD-bid ⟹ GBP/USD DOWNSIDE (GBP-soft) ; a "
                "NARROWER or NEGATIVE differential ⟹ sterling front-end "
                "advantage ⟹ GBP-bid. Symmetric : the Pass-2 LLM selects "
                "the branch matching the Pass-1 regime label."
            )
            lines.append(
                "- Frequency mismatch (SHARPER than Driver-1) : DGS3MO is "
                "DAILY (~4d) but the UK 3M interbank leg is the documented "
                "OECD-MEI MONTHLY family laggard (~4-6 months stale, "
                "ADR-101 §Impl(r102) max-age 180d). Treat this front-end "
                "differential as a SLOW REGIME indicator — STALER than "
                "Driver-1's already-monthly UK 10Y leg, NOT a fresher "
                "front-end read (Pass-2 must not over-weight it as timely "
                "policy information). BTP r34 cadence-mismatch precedent ; "
                "R24 SUBSET-not-SUPERSET."
            )
            lines.append(
                "- Tetlock invalidation : the wider-3M-differential "
                "GBP-soft refinement is invalidated if VIX > 25 AND the "
                "US-UK 3M differential narrows by > 25 bp within 5 "
                "sessions (front-end policy-convergence repricing) ; the "
                "narrow / negative-3M GBP-bid refinement is invalidated "
                "if VIX falls below 18 AND DGS3MO rises by > 20 bp within "
                "5 sessions (US front-end re-anchoring ; threshold "
                "asymmetric vs the 25-bp magnitude per the JPY r45 "
                "ichor-trader precedent). This REFINES, it does not "
                "override, the Driver-1 10Y read — it decomposes its "
                "front-end component."
            )

        # Composite (R24 SUBSET-not-SUPERSET via cadence-mismatch BTP r34 precedent)
        lines.append("### GBP rate-differential triangle (Engel-West + Della Corte-Sarno-Sestieri)")
        lines.append(
            "- The 2-driver GBP pricing framework is AVAILABLE for this "
            "asset (R24 SUBSET-not-SUPERSET cleared via cadence-mismatch "
            "BTP r34 precedent : DGS10 daily + UK 10Y monthly). The "
            "Engel-West 2005 fundamentals channel (DOI:10.1086/429137) "
            "transmits the rate-differential to GBP/USD directional bias "
            "under a near-unity discount factor — the spot rate is "
            "quasi-martingale yet the differential still determines its "
            "level (GBP/USD polarity : wider US-UK = GBP-soft, USD being "
            "the quote currency). Della Corte-Sarno-Sestieri 2012 "
            "(DOI:10.1162/REST_a_00157) is an INDEPENDENT external-"
            "imbalance predictor — a net-foreign-asset / current-account "
            "position carries a time-varying currency risk premium ; it "
            "does NOT reinterpret the rate differential. For sterling (a "
            "structural current-account-deficit currency) it implies an "
            "ADDITIVE GBP-soft risk premium under UK funding stress (the "
            "2022 LDI/gilt-crisis configuration), layered on — not "
            "derived from — the Engel-West rate-differential read. "
            "When the UK 3M leg is present, the front-end "
            "term-structure refinement above (ADR-101 §Impl(r103)) "
            "DECOMPOSES — it does NOT add a new independent driver — "
            "Driver-1's rate differential into its front-end "
            "(policy-stance) vs long-end (cumulative-expectations + "
            "term-premium) components ; it is a refinement lens on "
            "Driver-1, NOT a co-equal third driver. Pass-2 LLM should "
            "triangulate both regime-conditional branches before "
            "committing to a directional read. Tetlock invalidation "
            "thresholds emit asymmetric regime-flip conditions "
            "consistent with the JPY r45 precedent."
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


async def _section_theme_dominant(session: AsyncSession, asset: str) -> tuple[str, list[str]]:
    """## Theme sous-jacent dominant (r183 N1 CONSUMER WIRING).

    Surfaces the r182 N1 EXECUTION classifier output as plain-FR prose
    for Pass-2 narrative. Eliot Fathom transcript étape 1 verbatim :
    « identifier le thème sous-jacent du marché ».

    Asset-agnostic by design : the theme dominant is a CROSS-ASSET macro
    state read. ADR-017 boundary preserved : pure factual ranking,
    NEVER a directional bias for the CURRENT session. Doctrine #11
    calibrated honesty : honest-absence prose when classifier returns
    None (no driver above _DOMINANCE_THRESHOLD = 0.5).
    """
    ranking = await classify_dominant_theme(session, now_utc=datetime.now(UTC))

    if ranking is None:
        lines = [
            "## Theme sous-jacent dominant (Eliot Fathom transcript étape 1)",
            "",
            "Aucun thème sous-jacent ne domine clairement le marché à cet "
            "instant : aucune force directrice (parmi macroéconomique / "
            "politique monétaire / données économiques / politique fiscale / "
            "interconnexions marché / géopolitique / price action+flux / "
            "offre+demande) n'atteint le seuil de dominance (0.5 sur 1.0). "
            "Doctrine #11 calibrated honesty : aucune fabrication d'un thème "
            "par défaut ; le Pass-2 doit lire l'absence comme un régime "
            "mixte sans driver principal plutôt qu'une lecture neutre.",
            "",
            "Frontière ADR-017 : ranking factuel pur, jamais un signal de "
            "direction pour la session courante.",
        ]
        sources = [f"theme_dominant:{asset}:absent"]
        return "\n".join(lines), sources

    driver_fr = {
        "macroeconomic": "macroéconomique (événements mondiaux, regime-defining)",
        "monetary_policy": "politique monétaire (Fed / BCE / BoE / BoJ)",
        "economic_data": "données économiques (CPI / NFP / PMI / retail / GDP)",
        "fiscal_policy": "politique fiscale (dépenses publiques / tariffs)",
        "market_interconnexions": "interconnexions marché (fixed-income → FX → commodities → equities)",
        "geopolitics": "géopolitique (conflits / guerres / accords commerciaux)",
        "price_action_flow": "price action + flux institutionnel (microstructure)",
        "supply_demand": "offre / demande directe (commodities OPEC etc.)",
    }

    top_fr = driver_fr.get(ranking.top_theme, ranking.top_theme)
    top_strength = ranking.driver_strengths.get(ranking.top_theme, 0.0)
    top_pct = round(top_strength * 100)

    lines = [
        "## Theme sous-jacent dominant (Eliot Fathom transcript étape 1)",
        "",
        f"Le thème dominant actuel est **{top_fr}** "
        f"(force {top_pct}% sur 1.0). Le Pass-2 narrative doit lire les "
        f"autres signaux dans ce contexte : un développement contraire "
        f"au thème dominant a moins de portée qu'un développement aligné, "
        f"toutes choses égales par ailleurs.",
        "",
        f"- **Top theme** : `{ranking.top_theme}` ({top_fr})",
        f"- **Force** : {top_strength:.2f} / 1.00",
    ]

    if ranking.secondary_themes:
        for sec in ranking.secondary_themes:
            sec_strength = ranking.driver_strengths.get(sec, 0.0)
            sec_fr_label = driver_fr.get(sec, sec)
            lines.append(f"- **Secondaire** : `{sec}` ({sec_fr_label}) — force {sec_strength:.2f}")
    else:
        lines.append(
            "- **Secondaires** : aucun driver secondaire au-dessus de "
            "0.40 — un seul thème domine clairement."
        )

    lines.extend(
        [
            "",
            f"Provenance : `{ranking.provenance}` (Eliot Fathom transcript "
            f"page 1 étape 1 — la taxonomie 8-drivers est practitioner-stamp, "
            f"les driver-strength computations citent Bekaert-Hoerova-Lo Duca "
            f"2013 _JME_ + Caldara-Iacoviello 2022 _AER_ + Nakamura-Steinsson "
            f"2018 _QJE_ peer-reviewed backbones).",
            "",
            "Frontière ADR-017 : ranking factuel pur, jamais un signal de "
            "direction pour la session courante.",
        ]
    )
    sources = [f"theme_dominant:{ranking.top_theme}@{ranking.computed_at_utc.isoformat()}"]
    return "\n".join(lines), sources


async def _section_previous_session_context(
    session: AsyncSession, asset: str
) -> tuple[str, list[str]]:
    """## Previous-session origin zone (r180 G5 CONSUMER WIRING).

    Surfaces the r179 G5 EXECUTION classifier output as plain-FR prose
    for Pass-2 narrative. Eliot Fathom §V practitioner methodology :
    « savoir d'où vient le mouvement de la session précédente, son zone
    d'origine, son sens, ses hauts et bas ».

    The origin-zone (Asian / London / NY) + high/low/direction stamps
    inform the « comment se comporte le marché depuis un certain temps »
    read directive (Eliot Fathom §V context input to NY position-taking).

    ADR-017 boundary preserved : pure factual snapshot output (zone +
    high + low + direction + bar_count + window UTC). NEVER a directional
    bias for the CURRENT session. The Pass-2 LLM picks the appropriate
    framing based on Pass-1 régime label + the snapshot's factual content.

    Doctrine #11 calibrated honesty : when ``compute_previous_session_
    origin_zone()`` returns None (no bars OR dominant zone bar_count < 30),
    surface explicit « Contexte session précédente indisponible » prose
    rather than fabricate a read. Always-rendered (1 honest source stamp
    emitted whether snapshot present or None) so Pass-2 sees the explicit
    state instead of a vanishing section.
    """
    snapshot = await compute_previous_session_origin_zone(session, asset, now_utc=datetime.now(UTC))

    if snapshot is None:
        lines = [
            "## Previous-session origin zone (Eliot Fathom §V)",
            "",
            "Contexte session précédente indisponible : données insuffisantes "
            "dans la fenêtre des dernières 24 heures (week-end / jour férié OU "
            "moins de 30 barres 1-min dans la zone dominante per Cohen 1988 "
            "n=30 small-sample threshold). Doctrine #11 calibrated honesty : "
            "aucune fabrication ; le Pass-2 doit lire l'absence comme un "
            "manque réel de contexte plutôt qu'une lecture neutre par défaut.",
        ]
        sources = [f"origin_zone:{asset}:absent"]
        return "\n".join(lines), sources

    # Plain-FR rendering for Pass-2 narrative consumption. The FR copy
    # is intentionally factual + descriptive (per ADR-017 boundary
    # « explains WHAT happened in the previous session, never WHAT to
    # do about it »). Mirror of `_section_polygon_intraday` source-
    # stamping discipline (one source per data point cited).
    direction_fr = {
        "up": "haussier",
        "down": "baissier",
        "range": "range-bound (consolidation / chop)",
    }[snapshot.direction]

    zone_fr = {
        "asian": "asiatique (Tokyo + Sydney + Hong Kong)",
        "london": "londonienne (London cash open + NY pré-open)",
        "ny": "new-yorkaise (NYSE RTH + extended FX / late-NY rollover)",
    }[snapshot.session_zone]

    lines = [
        "## Previous-session origin zone (Eliot Fathom §V)",
        "",
        f"La session précédente a été dominée par la zone {zone_fr} "
        f"avec un mouvement directionnel {direction_fr}.",
        "",
        f"- **Zone dominante** : `{snapshot.session_zone}` ({zone_fr})",
        f"- **Direction** : `{snapshot.direction}` ({direction_fr})",
        f"- **High** : {snapshot.high_price:.5f}",
        f"- **Low** : {snapshot.low_price:.5f}",
        f"- **Range observé** : {snapshot.high_price - snapshot.low_price:.5f}",
        f"- **Barres 1-min** : {snapshot.bar_count} (≥ 30 per Cohen 1988 §3.3)",
        f"- **Fenêtre UTC** : "
        f"{snapshot.start_utc:%Y-%m-%d %H:%M} → {snapshot.end_utc:%Y-%m-%d %H:%M}",
        "",
        "Frontière ADR-017 : snapshot factuel pur, jamais un signal de "
        "direction pour la session courante.",
    ]
    sources = [
        f"origin_zone:polygon_intraday:{asset}"
        f"@{snapshot.start_utc.isoformat()}..{snapshot.end_utc.isoformat()}"
    ]
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


# S04 liveness max-ages for the non-FRED régime inputs (SSOT — shared by
# _section_nyfed_mct + _section_cross_asset_matrix so the SAME MCT data is
# never classified inconsistently across its two consumers).
#   MCT     : observation_month trails publish ~2mo, then ages ~30d to the next
#             monthly print → a FRESH latest row can legitimately be ~95d old;
#             100d never false-flags a normal release yet catches a dead
#             collector (verified at runtime 2026-06-08: latest obs 68d → fresh).
#   NOWCAST : Cleveland nowcast is DAILY (~16:00 Paris) → a fresh revision is
#             ≤2d old; 10d catches a dead daily collector, no false-flag.
#   SKEW    : CBOE SKEW is published every NYSE trading day → mirror the sibling
#             VIX guard (7d) so the two vol-dimension inputs age-out identically.
#   NFIB    : NFIB SBOI is MONTHLY (report_month released ~2nd Tue of M+1) → a
#             FRESH report_month is legitimately ~37-75d old; 80d never
#             false-flags (witnessed 2026-06-08: latest report_month 68d → fresh).
_MCT_MAX_AGE_DAYS = 100
_NOWCAST_MAX_AGE_DAYS = 10
_SKEW_MAX_AGE_DAYS = 7
_NFIB_MAX_AGE_DAYS = 80
_GPR_MAX_AGE_DAYS = 14  # AI-GPR daily but source publishes with ~8j lag (mesuré prod 2026-06-08)
_TFF_MAX_AGE_DAYS = 14  # CFTC TFF weekly (report Tue, published Fri); intra-cycle age 3-10j
_COT_MAX_AGE_DAYS = 14  # CFTC COT weekly (same cadence)
_VOLUME_RVOL_MAX_AGE_DAYS = 5  # market_data daily volume; 5j covers long weekends/holidays

# S04 TIER-2 relative-volume layer — assets carrying real consolidated daily
# volume in `market_data` (source=yfinance, empirically witnessed prod 2026-06-08:
# SPX500/NAS100 share volume + XAU GC=F gold-futures volume). FX pairs carry zero
# venue volume → honest N/A by data property (not a degraded source).
_VOLUME_ASSETS: frozenset[str] = frozenset({"SPX500_USD", "NAS100_USD", "XAU_USD"})


async def _section_cross_asset_matrix(
    session: AsyncSession,
) -> tuple[str, list[str], list[DegradedInput]]:
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
    degraded: list[DegradedInput] = []
    _now = datetime.now(UTC).date()

    # ── 1. Inflation persistence (MCT trend) ──
    mct_row = (
        await session.execute(
            select(NyfedMctObservation)
            .order_by(desc(NyfedMctObservation.observation_month))
            .limit(1)
        )
    ).scalar_one_or_none()
    # S04 liveness gate — a stale MCT must NOT keep voting in the régime band
    # (the systemic stale-as-fresh « zone d'ombre » the depth audit named #1).
    # NYFED:MCT staleness is already surfaced in the integrity header by
    # _section_nyfed_mct, so the value is withheld here WITHOUT re-emitting a
    # duplicate DegradedInput (avoids double-count).
    mct_live = classify_liveness(
        "NYFED:MCT",
        mct_row.observation_month if mct_row else None,
        now=_now,
        max_age_days=_MCT_MAX_AGE_DAYS,
    )
    mct_value = (
        mct_row.mct_trend_pct if (mct_row is not None and not mct_live.is_degraded) else None
    )
    mct_band = _band(
        mct_value,
        (2.25, 2.75, 3.25),
        ("anchored", "near-target", "above-target", "unanchored"),
    )
    if mct_row is not None and not mct_live.is_degraded:
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
    # S04 liveness gate — the Cleveland nowcast is DAILY; a stale revision must
    # not feed the surprise band as current. Unlike MCT it is surfaced nowhere
    # else, so emit a DegradedInput when degraded.
    nowcast_live = classify_liveness(
        "CLEVELAND:NOWCAST",
        nowcast_row.revision_date if nowcast_row else None,
        now=_now,
        max_age_days=_NOWCAST_MAX_AGE_DAYS,
        impacted="Pass-1 régime classifier (inflation-surprise band: CorePCE nowcast vs MCT)",
    )
    if nowcast_live.is_degraded:
        degraded.append(
            DegradedInput(
                series_id=nowcast_live.source_key,
                status=nowcast_live.status,  # type: ignore[arg-type]  # never "fresh" here
                latest_date=nowcast_live.latest_date,
                age_days=nowcast_live.age_days,
                max_age_days=nowcast_live.max_age_days,
                impacted=nowcast_live.impacted,
            )
        )
    nowcast_value: float | None = (
        nowcast_row.nowcast_value
        if (nowcast_row is not None and not nowcast_live.is_degraded)
        else None
    )
    surprise_pts = (
        nowcast_value - mct_value if (nowcast_value is not None and mct_value is not None) else None
    )
    surprise_band = _band(
        surprise_pts,
        (-0.50, -0.10, 0.10, 0.50),
        ("downside-strong", "downside", "neutral", "upside", "upside-strong"),
    )
    if nowcast_row is not None and not nowcast_live.is_degraded:
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
    # S04 liveness gate — a stale SKEW must not feed the tail-risk band. Surfaced
    # nowhere else with a guard → emit a DegradedInput when degraded.
    skew_live = classify_liveness(
        "CBOE:SKEW",
        skew_row.observation_date if skew_row else None,
        now=_now,
        max_age_days=_SKEW_MAX_AGE_DAYS,
        impacted="Pass-1 régime classifier (tail-risk band: CBOE SKEW)",
    )
    if skew_live.is_degraded:
        degraded.append(
            DegradedInput(
                series_id=skew_live.source_key,
                status=skew_live.status,  # type: ignore[arg-type]  # never "fresh" here
                latest_date=skew_live.latest_date,
                age_days=skew_live.age_days,
                max_age_days=skew_live.max_age_days,
                impacted=skew_live.impacted,
            )
        )
    skew_value = (
        skew_row.skew_value if (skew_row is not None and not skew_live.is_degraded) else None
    )
    skew_band = _band(
        skew_value, (135.0, 145.0, 155.0), ("calm", "normal", "elevated", "tail-fear")
    )
    if skew_row is not None and not skew_live.is_degraded:
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
    # S04 liveness gate — a stale NFIB SBOI must not feed the sentiment band.
    # Surfaced by the standalone _section_nfib_sbet (currently unguarded), so the
    # matrix emits the DegradedInput here as the single integrity surface for now.
    sbet_live = classify_liveness(
        "NFIB:SBET",
        sbet_row.report_month if sbet_row else None,
        now=_now,
        max_age_days=_NFIB_MAX_AGE_DAYS,
        impacted="Pass-1 régime classifier (small-business-sentiment band: NFIB SBOI)",
    )
    if sbet_live.is_degraded:
        degraded.append(
            DegradedInput(
                series_id=sbet_live.source_key,
                status=sbet_live.status,  # type: ignore[arg-type]  # never "fresh" here
                latest_date=sbet_live.latest_date,
                age_days=sbet_live.age_days,
                max_age_days=sbet_live.max_age_days,
                impacted=sbet_live.impacted,
            )
        )
    sbet_value = sbet_row.sboi if (sbet_row is not None and not sbet_live.is_degraded) else None
    sbet_band = _band(
        sbet_value, (95.0, 98.0, 102.0), ("recession-pre", "below-avg", "soft", "expansionary")
    )
    if sbet_row is not None and not sbet_live.is_degraded:
        sources.append(f"NFIB:SBET@{sbet_row.report_month.isoformat()}")

    if not sources:
        return (
            "",
            [],
            degraded,
        )  # nothing to surface — caller skips (degraded still threaded) append

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

    # ── GBP_USD : risk-currency with BoE-Fed differential ──
    # Round-40 GAP-A closure (ichor-trader r39+r40 audit) : pre-r40
    # was `list(eur_usd)` — wrong because GBP is NOT EUR (no ECB-Fed
    # mechanic, no peripheral fragmentation, distinct UK gilt + BoE
    # cycle).
    # r40 ichor-trader caveat applied : GBP-mirror is SUBSET of EUR
    # pattern, not SUPERSET. Only the broadest USD-weakness flows
    # propagate (liquidity_loose, vol-calm carry). ECB-specific
    # rate-differential narrative ("Fed easing path") is DROPPED for
    # GBP because BoE-Fed path diverged 2025-2026 (Bailey vs Powell)
    # and would need a gilt-Bund spread signal — deferred r41+ pending
    # gilt-Bund daily-proxy ingestion.
    gbp_usd: list[str] = []
    # USD-positive scenarios for GBP_USD (4 triggers — GBP is
    # risk-currency, distinct from EUR safe-haven dimension) :
    if liquidity_tight:
        gbp_usd.append("USD-bid (NFCI tight, GBP risk-currency soft)")
    if vol_elevated:
        gbp_usd.append("USD-bid (vol regime, GBP risk-currency drawdown)")
    if tail_fear:
        gbp_usd.append("USD-bid (tail-fear, GBP risk-currency aversion)")
    if sentiment_weak:
        gbp_usd.append("USD-bid (UK growth-tail downside ; invalidated if SBOI returns above 98)")
    # GBP-positive scenarios (SUBSET mirror of EUR pattern,
    # Tetlock invalidations) :
    if liquidity_loose:
        gbp_usd.append(
            "GBP-bid (NFCI loose, broad USD-weakness flow ; "
            "invalidated if NFCI ≥ 0.0 within 5 sessions)"
        )
    if vol_complacent and sentiment_strong:
        gbp_usd.append(
            "GBP-bid (risk-on carry regime favors GBP ; invalidated if VIX > 22 OR SBOI < 98)"
        )
    # NOTE r40 deferred to r41+ : `inflation_anchored AND
    # sentiment_strong → GBP-bid (BoE-Fed easing parity)` requires
    # gilt-Bund spread daily signal (IRLTLT01GBM156N is monthly
    # → stale at intraday Pass-2 ; r37 frequency-aware registry
    # sets 120d max-age but the rate-differential narrative still
    # needs a daily proxy).
    asset_hints.append(asset("GBP_USD", gbp_usd or ["balanced"]))

    # ── USD_JPY : safe-haven funding-currency with US-JP differential ──
    # Round-46 r46-round-2 GAP-A symmetric mirror (post-r45 ship of
    # `_section_jpy_specific` Engel-West rate-differential + Brunnermeier-
    # Nagel-Pedersen 2009 carry-crash skew). Pre-r46 had only 2 uni-
    # directional lines ; r46 extends to a symmetric mirror with Tetlock
    # invalidation thresholds consistent with r38 EUR + r40 GBP/CAD
    # patterns.
    usd_jpy: list[str] = []
    # USD-positive scenarios (carry-bid regime, JPY-funded USD-long accum.) :
    if inflation_pressure_up:
        usd_jpy.append(
            "USD-bid (UST yield up → carry-bid US/JPY ; "
            "invalidated if VIX > 25 AND US-JP differential narrows > 20 bp within 5 sessions)"
        )
    if vol_complacent and tail_calm:
        usd_jpy.append(
            "USD-bid (calm carry regime, JPY-funded USD-long accumulation ; "
            "invalidated if SKEW > 145 OR VIX > 22)"
        )
    if liquidity_loose and sentiment_strong:
        usd_jpy.append(
            "USD-bid (broad risk-on flow favors high-yielder over JPY ; "
            "invalidated if NFCI rises above 0 within 5 sessions)"
        )
    # JPY-positive scenarios (safe-haven + carry-crash skew Brunnermeier-Nagel-Pedersen 2009) :
    if vol_elevated or tail_fear:
        usd_jpy.append(
            "JPY-bid (safe-haven flight + carry-crash skew per Brunnermeier-Nagel-Pedersen 2009 ; "
            "invalidated if VIX falls below 18 AND DGS10 rises > 15 bp within 5 sessions)"
        )
    if sentiment_weak and liquidity_tight:
        usd_jpy.append(
            "JPY-bid (US-led risk-off + funding tightness, full carry-unwind ; "
            "invalidated if NFCI eases below 0 AND VIX below 20 concurrent)"
        )
    asset_hints.append(asset("USD_JPY", usd_jpy or ["balanced"]))

    # ── AUD_USD : commodity-currency with China credit + Iron-ore ──
    # Round-46 r46-round-2 GAP-A symmetric mirror (post-r46 ship of
    # `_section_aud_specific` Engel-West rate-differential + Chen-Rogoff
    # commodity-currency + Ready-Roussanov-Ward 2017). Pre-r46 had only
    # 2 uni-directional lines ; r46 extends to a symmetric mirror with
    # Tetlock invalidation thresholds. NB : actual commodity reflation
    # / China credit regime is surfaced empirically via
    # `_section_aud_specific` (Driver 2 China M1 + Driver 3 iron+copper
    # composite) — this macro-state shortlist is a quick-pass overlay.
    aud_usd: list[str] = []
    # USD-positive scenarios (AUD-soft, risk-off, commodity collapse) :
    if liquidity_tight or tail_fear:
        aud_usd.append(
            "AUD-soft (risk-off + commodity-currency-first-to-unwind cascade ; "
            "invalidated if NFCI eases below 0 AND iron-ore rebounds above trailing 6m baseline)"
        )
    if vol_elevated:
        aud_usd.append(
            "AUD-soft (vol regime, commodity-currency drawdown ; "
            "invalidated if VIX falls below 18 within 5 sessions)"
        )
    if sentiment_weak:
        aud_usd.append(
            "AUD-soft (broad slowdown proxy for China-deceleration risk ; "
            "invalidated if SBOI rebounds above 100)"
        )
    # AUD-positive scenarios (commodity reflation, China credit expansion, carry-bid) :
    if inflation_pressure_up:
        aud_usd.append(
            "AUD-bid (commodity tail-up support via terms-of-trade ; "
            "invalidated if iron-ore prints below trailing 6m baseline)"
        )
    if liquidity_loose and sentiment_strong:
        aud_usd.append(
            "AUD-bid (broad commodity reflation regime, China credit-impulse upside ; "
            "invalidated if NFCI rises above 0 OR China M1 prints below trailing 12m mean)"
        )
    if vol_complacent and tail_calm:
        aud_usd.append(
            "AUD-bid (calm carry regime, AUD-receiver carry attractive ; "
            "invalidated if VIX > 22 OR SKEW > 145)"
        )
    asset_hints.append(asset("AUD_USD", aud_usd or ["balanced"]))

    # ── USD_CAD : commodity-currency with BoC-Fed differential ──
    # Round-40 GAP-A closure : pre-r40 had ONLY `vol_elevated → USD-bid`
    # (zero CAD-bullish branch). r40 ichor-trader audit caveat applied :
    # CAD-bullish framings without an empirical oil-price signal are
    # 2-step inferences (inflation/sentiment → oil → CAD) the LLM
    # cannot verify falsifiably. Conservative ship : the broad
    # commodity-reflation flow (liquidity_loose AND sentiment_strong)
    # is defensible as risk-on broad-USD-weakness ; the BoC-hawkish-
    # oil-carry framing is DEFERRED r41+ pending DCOILWTICO empirical
    # surface. Asymmetric (3 USD-bid vs 1 CAD-bid) but Tetlock-honest.
    usd_cad: list[str] = []
    # USD-positive scenarios :
    if vol_elevated:
        usd_cad.append("USD-bid (vol regime, commodity-CAD risk-off)")
    if liquidity_tight:
        usd_cad.append("USD-bid (NFCI tight, commodity-currency soft)")
    if tail_fear:
        usd_cad.append("USD-bid (tail-fear, CAD risk-off)")
    # CAD-positive scenarios (Tetlock-defensible only — broad risk-on
    # flow without oil-price overclaim) :
    if liquidity_loose and sentiment_strong:
        usd_cad.append(
            "CAD-bid (commodity reflation via broad risk-on flow ; "
            "invalidated if NFCI ≥ 0.0 OR SBOI < 98)"
        )
    # NOTE r40 deferred to r41+ :
    #   - `inflation_pressure_up AND vol_complacent → CAD-bid
    #     (BoC-hawkish-oil-carry)` is 2-step (inflation → oil → CAD)
    #     unfalsifiable without DCOILWTICO empirical surface.
    #   - `tail_calm AND sentiment_strong → CAD-bid (oil-positive
    #     backdrop)` triple-counts the broad risk-on signal already
    #     captured by `liquidity_loose AND sentiment_strong` above.
    asset_hints.append(asset("USD_CAD", usd_cad or ["balanced"]))

    # ── XAU_USD : gold-real-yield triangle (Erb/Harvey + dollar-smile) ──
    # Round-46 r46-round-5 GAP-A retroactive symmetric mirror (R47 pattern
    # codified r46-round-2). Pre-r46-r5 XAU had 3 partial-symmetric uni-
    # directional hints with `(++)` / `(-)` notation but NO XAU-soft mirror
    # branch despite `_section_xau_specific` (r41) being fully symmetric
    # with Tetlock invalidation on both branches.
    # R47 retroactive symmetric mirror per cross-asset matrix R47 pattern
    # codified r46-round-2 : extend to a balanced bid/soft mirror with
    # Tetlock invalidation thresholds matching `_section_xau_specific`
    # (Erb-Harvey 2013 real-yield law + Stephen-Jen 2018 dollar-smile).
    xau_usd: list[str] = []
    # XAU-bid scenarios (real-yield support + safe-haven flight) :
    if inflation_pressure_up:
        xau_usd.append(
            "XAU-bid (real-yield support via Erb-Harvey channel ; "
            "invalidated if DFII10 rises > 20 bp within 5 sessions WHILE Pass-1 regime stays calm)"
        )
    if tail_fear or vol_elevated:
        xau_usd.append(
            "XAU-bid (safe-haven flight + dollar-smile co-bid per Brunnermeier-Pedersen 2009 ; "
            "invalidated if VIX falls below 16 AND SKEW < 135 concurrent)"
        )
    if liquidity_tight:
        xau_usd.append(
            "XAU-bid (USD-strength counter-pressure mitigated by funding-stress flight bid ; "
            "invalidated if HY OAS fails to widen > 50 bp during DTWEXBGS up-move)"
        )
    # XAU-soft scenarios (real-yield rise + risk-on carry under-allocation) :
    if inflation_anchored and sentiment_strong:
        xau_usd.append(
            "XAU-soft (real yields rising in goldilocks, gold-yield-headwind via Erb-Harvey ; "
            "invalidated if DFII10 falls > 15 bp within 5 sessions OR VIX rises above 22)"
        )
    if liquidity_loose and vol_complacent:
        xau_usd.append(
            "XAU-soft (risk-on carry-receiving regime, gold under-allocated vs high-yielders ; "
            "invalidated if NFCI rises above 0 OR VIX rises above 22 within 5 sessions)"
        )
    asset_hints.append(asset("XAU_USD", xau_usd or ["balanced"]))

    # ── NAS100_USD : duration-vol-tail triangle (Hou-Mo-Xue + Park 2015) ──
    # Round-46 r46-round-5 GAP-A retroactive symmetric mirror (R47 pattern
    # codified r46-round-2). Pre-r46-r5 NAS had 3 uni-directional NAS-soft
    # hints with `(-)` notation and ZERO NAS-bid mirror despite
    # `_section_nas_specific` (r42) being fully symmetric on all 3 drivers
    # (DGS10 + VVIX + SKEW) with Tetlock invalidation on both branches.
    # R47 retroactive symmetric mirror per cross-asset matrix R47 pattern
    # codified r46-round-2 : extend to a balanced bid/soft mirror with
    # Tetlock invalidation thresholds matching `_section_nas_specific`
    # (Hou-Mo-Xue 2015 q-factor duration + Park 2015 / Bevilacqua-Tunaru
    # 2021 VVIX-SKEW joint regime literature).
    nas: list[str] = []
    # NAS-soft scenarios (duration + multiple compression + vol-of-vol) :
    if inflation_pressure_up:
        nas.append(
            "NAS-soft (duration headwind via Hou-Mo-Xue q-factor discount-rate channel ; "
            "invalidated if DGS10 rises > 15 bp WHILE 1m-realized-vol stays sub-30% in goldilocks)"
        )
    if liquidity_tight:
        nas.append(
            "NAS-soft (multiple-compression via funding-stress discount-rate denominator ; "
            "invalidated if NFCI falls below 0 within 4 sessions AND VVIX stays sub-100)"
        )
    if vol_elevated:
        nas.append(
            "NAS-soft (vol-of-vol drag, mechanical vol-control deleveraging per Park 2015 ; "
            "invalidated if VVIX falls below 85 within 3 sessions AND SKEW < 130 concurrent)"
        )
    # NAS-bid scenarios (calm-tail mechanical bid + reflation + dispersion absorption) :
    if liquidity_loose and vol_complacent:
        nas.append(
            "NAS-bid (carry-bid risk-on regime, multiple-expansion + duration tailwind ; "
            "invalidated if NFCI rises above 0 OR VVIX exceeds 100 within 5 sessions)"
        )
    if inflation_anchored and sentiment_strong:
        nas.append(
            "NAS-bid (real-yield easing + earnings reflation via Hou-Mo-Xue duration relief ; "
            "invalidated if MCT > 2.75 OR SBOI < 98 within 2 monthly prints)"
        )
    if tail_calm and vol_complacent:
        nas.append(
            "NAS-bid (vol-of-vol low + dispersion absorption per Bevilacqua-Tunaru 2021 ; "
            "invalidated if SKEW > 130 alongside DGS10 widening > 10 bp)"
        )
    asset_hints.append(asset("NAS100_USD", nas or ["balanced"]))

    # ── SPX500_USD : VIX-funding-sentiment triangle (Brunnermeier-Pedersen) ──
    # Round-46 r46-round-5 GAP-A retroactive symmetric mirror (R47 pattern
    # codified r46-round-2). Pre-r46-r5 SPX had only 2 uni-directional SPX-
    # soft hints with `(-)` notation and ZERO SPX-bid mirror despite
    # `_section_spx_specific` (r43) being fully symmetric on all 3 drivers
    # (VIX term-structure + NFCI + SBOI) with Tetlock invalidation on both
    # branches.
    # R47 retroactive symmetric mirror per cross-asset matrix R47 pattern
    # codified r46-round-2 : extend to a balanced bid/soft mirror with
    # Tetlock invalidation thresholds matching `_section_spx_specific`
    # (Brunnermeier-Pedersen 2009 funding-liquidity-spiral framework, the
    # SPX-equity analogue of the Stephen-Jen USD broken-smile).
    # SOURCE-PURITY CAVEAT (ADR-089) : SPX500_USD Polygon ticker = `SPY`
    # NYSE Arca ETF proxy (not `I:SPX`, $49/mo subscription blocked). Tracking
    # error <0.1% MTD invisible for qualitative Pass-2 framing.
    spx: list[str] = []
    # SPX-soft scenarios (risk-off + funding stress + earnings-tail) :
    if liquidity_tight or tail_fear:
        spx.append(
            "SPX-soft (risk-off pressure via Brunnermeier-Pedersen funding-liquidity spiral ; "
            "invalidated if NFCI falls below 0 within 4 sessions AND VIX-term-structure stays contango)"
        )
    if sentiment_weak:
        spx.append(
            "SPX-soft (earnings-tail downside via SBOI contractionary regime ; "
            "invalidated if SBOI rebounds above 100 alongside NFCI falling below -0.3)"
        )
    # SPX-bid scenarios (broad reflation + goldilocks mechanical beta + roll-yield) :
    if liquidity_loose and sentiment_strong:
        spx.append(
            "SPX-bid (broad reflation + multiple-expansion via funding-loose + sentiment-strong ; "
            "invalidated if NFCI rises above 0 OR SBOI falls below 95 within 2 monthly prints)"
        )
    if inflation_anchored and vol_complacent:
        spx.append(
            "SPX-bid (goldilocks regime, mechanical beta accumulation via vol-control rebuild ; "
            "invalidated if MCT > 2.75 OR VIX rises above 22 within 5 sessions)"
        )
    if tail_calm and vol_complacent:
        spx.append(
            "SPX-bid (VIX-term-structure contango + vol-seller roll-yield extraction ; "
            "invalidated if VIX-term-structure flips to backwardation OR SKEW > 130 within 3 sessions)"
        )
    asset_hints.append(asset("SPX500_USD", spx or ["balanced"]))

    for asset_name, hints in asset_hints:
        lines.append(f"- **{asset_name}** : {' · '.join(hints)}")

    return "\n".join(lines), sources, degraded


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


async def _section_nyfed_mct(session: AsyncSession) -> tuple[str, list[str], list[DegradedInput]]:
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
    # S04 liveness gate (no silent stale) — _MCT_MAX_AGE_DAYS is the module-level
    # SSOT (shared with _section_cross_asset_matrix; full rationale at its def).
    lv = classify_liveness(
        "NYFED:MCT",
        rows[0].observation_month if rows else None,
        now=datetime.now(UTC).date(),
        max_age_days=_MCT_MAX_AGE_DAYS,
        impacted="NY Fed MCT section + Pass-1 inflation-trend régime classifier",
    )
    degraded: list[DegradedInput] = []
    if lv.is_degraded:
        degraded.append(
            DegradedInput(
                series_id=lv.source_key,
                status=lv.status,  # type: ignore[arg-type]  # never "fresh" here
                latest_date=lv.latest_date,
                age_days=lv.age_days,
                max_age_days=lv.max_age_days,
                impacted=lv.impacted,
            )
        )
        if lv.status == "absent":
            md = (
                "## NY Fed MCT (PCE trend) — ⚠️ ABSENT\n"
                "- ⚠️ ABSENT: no NY Fed MCT observation ingested — inflation-trend "
                "block unavailable (collector never delivered; ADR-099 §D-2 "
                "« never silently absent »)."
            )
        else:
            md = (
                "## NY Fed MCT (PCE trend) — ⚠️ STALE\n"
                f"- ⚠️ STALE: latest obs {lv.latest_date:%b %Y} is {lv.age_days}d old "
                f"(> {lv.max_age_days}d max) — value withheld, NOT presented as current "
                "(NYFED:MCT collector degraded; data-provenance context, not a signal "
                "— ADR-099 §D-2)."
            )
        return md, [], degraded

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

    return "\n".join(lines), sources, degraded


async def _section_tff_positioning(
    session: AsyncSession, asset: str
) -> tuple[str, list[str], list[DegradedInput]]:
    """## TFF positioning — latest CFTC TFF 4-class breakdown for the asset.

    Surfaces the smart-money divergence signal (LevFunds vs AssetMgr)
    + dealer absorbing inventory. Per-asset, weekly cadence. Skip if the
    asset is not in the TFF tracked-market whitelist.
    """
    degraded: list[DegradedInput] = []
    _now = datetime.now(UTC).date()
    market = _TFF_MARKET_BY_ASSET.get(asset)
    if market is None:
        # Asset outside the TFF whitelist → no source expected → NOT degraded.
        return "", [], []
    stmt = (
        select(CftcTffObservation)
        .where(CftcTffObservation.market_code == market)
        .order_by(desc(CftcTffObservation.report_date))
        .limit(2)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    if not rows:
        # S04 liveness gate — a tracked market with zero persisted rows is an
        # ABSENT source (collector never delivered), not a silent n/a.
        live = classify_liveness(
            f"CFTC:TFF:{market}",
            None,
            now=_now,
            max_age_days=_TFF_MAX_AGE_DAYS,
            impacted=f"tff:{asset}",
        )
        degraded.append(
            DegradedInput(
                series_id=live.source_key,
                status=live.status,  # type: ignore[arg-type]  # never "fresh" here
                latest_date=live.latest_date,
                age_days=live.age_days,
                max_age_days=live.max_age_days,
                impacted=live.impacted,
            )
        )
        return (
            f"## TFF positioning ({asset}, market={market})\n"
            f"- ⚠ CFTC:TFF:{market} {live.status.upper()} : no persisted rows",
            [],
            degraded,
        )
    cur = rows[0]
    prev = rows[1] if len(rows) > 1 else None

    # S04 liveness gate — a stale weekly report must not render as the current
    # positioning headline without an explicit STALE band + degraded trace.
    live = classify_liveness(
        f"CFTC:TFF:{market}",
        cur.report_date,
        now=_now,
        max_age_days=_TFF_MAX_AGE_DAYS,
        impacted=f"tff:{asset}",
    )
    stale_band = ""
    if live.is_degraded:
        degraded.append(
            DegradedInput(
                series_id=live.source_key,
                status=live.status,  # type: ignore[arg-type]  # never "fresh" here
                latest_date=live.latest_date,
                age_days=live.age_days,
                max_age_days=live.max_age_days,
                impacted=live.impacted,
            )
        )
        stale_band = (
            f"\n- ⚠ CFTC:TFF:{market} {live.status.upper()} : "
            f"{live.age_days}j (max {live.max_age_days}j)"
        )

    dealer_net = cur.dealer_long - cur.dealer_short
    am_net = cur.asset_mgr_long - cur.asset_mgr_short
    lev_net = cur.lev_money_long - cur.lev_money_short
    other_net = cur.other_rept_long - cur.other_rept_short
    # Non-reportable = small / retail traders (below CFTC reporting threshold).
    # The 5th and final TFF trader class — previously stored but never surfaced,
    # so the LLM saw a 4-of-5 breakdown. Retail is the classic contrarian
    # cohort (often offside at extremes), worth its own descriptive line.
    nonrept_net = cur.nonrept_long - cur.nonrept_short

    if prev is not None:
        dealer_dw = (prev.dealer_long - prev.dealer_short) - dealer_net
        # Trader convention: Δw/w in the OWN direction (positive = longer this week)
        dealer_dw = -dealer_dw
        am_dw = am_net - (prev.asset_mgr_long - prev.asset_mgr_short)
        lev_dw = lev_net - (prev.lev_money_long - prev.lev_money_short)
        nonrept_dw = nonrept_net - (prev.nonrept_long - prev.nonrept_short)
        delta_str = (
            f", Δw/w (Dealer {dealer_dw:+,}, AM {am_dw:+,}, "
            f"LevFunds {lev_dw:+,}, Nonrept {nonrept_dw:+,})"
        )
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
        f"LevFunds net = {lev_net:+,}, Other net = {other_net:+,}, "
        f"Nonrept (small/retail) net = {nonrept_net:+,} "
        f"(open_interest={cur.open_interest:,}, report_date={cur.report_date:%Y-%m-%d})"
        f"{delta_str}{divergence}{stale_band}"
    )
    return md, sources, degraded


async def _section_rate_positioning(
    session: AsyncSession, asset: str
) -> tuple[str, list[str], list[DegradedInput]]:
    """## Rate positioning — UST 10Y futures positioning as the discount-rate
    context for rate-sensitive equity indices (S04 TIER-2 #4).

    The 10-Year Treasury is the benchmark discount rate for equity valuations;
    leveraged-fund / asset-manager positioning in 10Y futures is a forward read
    on the rate channel that drives index multiples (esp. long-duration tech →
    Nasdaq). Index assets only (SPX500 / NAS100). DESCRIPTIVE + NON-directional
    (ADR-017): the positioning is rate-channel context, never a direction on the
    index. Liveness-gated like the sister TFF/COT sections; reuses the same
    CftcTffObservation rows the collector already persists for code 043602.
    """
    degraded: list[DegradedInput] = []
    market = _RATE_CONTEXT_BY_ASSET.get(asset)
    if market is None:
        # Asset is not rate-sensitivity-mapped → no source expected → NOT degraded.
        return "", [], []
    _now = datetime.now(UTC).date()
    stmt = (
        select(CftcTffObservation)
        .where(CftcTffObservation.market_code == market)
        .order_by(desc(CftcTffObservation.report_date))
        .limit(2)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    if not rows:
        live = classify_liveness(
            f"CFTC:TFF:{market}",
            None,
            now=_now,
            max_age_days=_TFF_MAX_AGE_DAYS,
            impacted=f"rate_positioning:{asset}",
        )
        degraded.append(
            DegradedInput(
                series_id=live.source_key,
                status=live.status,  # type: ignore[arg-type]  # never "fresh" here
                latest_date=live.latest_date,
                age_days=live.age_days,
                max_age_days=live.max_age_days,
                impacted=live.impacted,
            )
        )
        return (
            f"## Rate positioning ({asset} ← UST 10Y, market={market})\n"
            f"- ⚠ CFTC:TFF:{market} {live.status.upper()} : no persisted rows",
            [],
            degraded,
        )
    cur = rows[0]
    prev = rows[1] if len(rows) > 1 else None
    live = classify_liveness(
        f"CFTC:TFF:{market}",
        cur.report_date,
        now=_now,
        max_age_days=_TFF_MAX_AGE_DAYS,
        impacted=f"rate_positioning:{asset}",
    )
    stale_band = ""
    if live.is_degraded:
        degraded.append(
            DegradedInput(
                series_id=live.source_key,
                status=live.status,  # type: ignore[arg-type]  # never "fresh" here
                latest_date=live.latest_date,
                age_days=live.age_days,
                max_age_days=live.max_age_days,
                impacted=live.impacted,
            )
        )
        stale_band = (
            f"\n- ⚠ CFTC:TFF:{market} {live.status.upper()} : "
            f"{live.age_days}j (max {live.max_age_days}j)"
        )
    lev_net = cur.lev_money_long - cur.lev_money_short
    am_net = cur.asset_mgr_long - cur.asset_mgr_short
    delta_str = ""
    if prev is not None:
        lev_dw = lev_net - (prev.lev_money_long - prev.lev_money_short)
        am_dw = am_net - (prev.asset_mgr_long - prev.asset_mgr_short)
        delta_str = f", Δw/w (LevFunds {lev_dw:+,}, AM {am_dw:+,})"
    sources = [f"CFTC:TFF:{market}@{cur.report_date.isoformat()}"]
    md = (
        f"## Rate positioning ({asset} ← UST 10Y, the equity discount-rate benchmark)\n"
        f"- UST 10Y futures positioning: LevFunds net = {lev_net:+,}, "
        f"AssetMgr net = {am_net:+,} (open_interest={cur.open_interest:,}, "
        f"report_date={cur.report_date:%Y-%m-%d}){delta_str}\n"
        f"- Rate-channel context for {asset} (discount-rate sensitivity), not a direction."
        f"{stale_band}"
    )
    return md, sources, degraded


async def _section_cot(
    session: AsyncSession, asset: str
) -> tuple[str, list[str], list[DegradedInput]]:
    """## COT positioning — latest weekly Disaggregated row for the asset.

    Wave 45 enriched: Δw/w + Δ4w + Δ12w trend deltas on managed_money_net
    to surface positioning regime shifts (acceleration / deceleration /
    reversal) rather than just a static snapshot.
    """
    degraded: list[DegradedInput] = []
    _now = datetime.now(UTC).date()
    market = _COT_MARKET_BY_ASSET.get(asset)
    if market is None:
        # Asset outside the COT whitelist → no source expected → NOT degraded.
        return "", [], []
    stmt = (
        select(CotPosition)
        .where(CotPosition.market_code == market)
        .order_by(desc(CotPosition.report_date))
        .limit(13)  # ~3 months of weekly data for Δ12w computation
    )
    rows = list((await session.execute(stmt)).scalars().all())
    if not rows:
        # S04 liveness gate — the COT table is EMPTY in prod; this makes the
        # absence explicit (status="absent") instead of a silent n/a.
        live = classify_liveness(
            f"CFTC:COT:{market}",
            None,
            now=_now,
            max_age_days=_COT_MAX_AGE_DAYS,
            impacted=f"cot:{asset}",
        )
        degraded.append(
            DegradedInput(
                series_id=live.source_key,
                status=live.status,  # type: ignore[arg-type]  # never "fresh" here
                latest_date=live.latest_date,
                age_days=live.age_days,
                max_age_days=live.max_age_days,
                impacted=live.impacted,
            )
        )
        return (
            f"## COT positioning ({asset}, market={market})\n"
            f"- ⚠ CFTC:COT:{market} {live.status.upper()} : no persisted rows",
            [],
            degraded,
        )
    cur = rows[0]
    # S04 liveness gate — a stale weekly report must not render as the current
    # positioning headline without an explicit STALE band + degraded trace.
    live = classify_liveness(
        f"CFTC:COT:{market}",
        cur.report_date,
        now=_now,
        max_age_days=_COT_MAX_AGE_DAYS,
        impacted=f"cot:{asset}",
    )
    stale_band = ""
    if live.is_degraded:
        degraded.append(
            DegradedInput(
                series_id=live.source_key,
                status=live.status,  # type: ignore[arg-type]  # never "fresh" here
                latest_date=live.latest_date,
                age_days=live.age_days,
                max_age_days=live.max_age_days,
                impacted=live.impacted,
            )
        )
        stale_band = (
            f"\n- ⚠ CFTC:COT:{market} {live.status.upper()} : "
            f"{live.age_days}j (max {live.max_age_days}j)"
        )
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
        # Commercials (producer/merchant/processor/user) = physical hedgers, the
        # classic COT smart-money anchor ; non-reportable = small/retail traders.
        # Both stored by the parser but previously never surfaced to the LLM.
        f"commercials_producer_net={cur.producer_net:+,}, "
        f"other_reportable_net={cur.other_reportable_net:+,}, "
        f"small_traders_non_reportable_net={cur.non_reportable_net:+,}, "
        f"open_interest={cur.open_interest:,}, "
        f"report_date={cur.report_date:%Y-%m-%d})"
        f"{stale_band}"
    )
    return md, sources, degraded


# r-round8 — Chantier-C DimensionVote write-side builders extracted VERBATIM to
# the sibling ``dimension_vote_builders`` module (pure structural move, zero
# behavior change ; shrinks this god-file). Re-exported here for back-compat so
# every public import path (cli/run_session_card.py + the C-3 wiring tests) stays
# byte-identical. The names are pinned in ``__all__`` (above) so ruff F401 cannot
# strip the re-export. The 3 shared constants (_COT_MARKET_BY_ASSET, _VOLUME_ASSETS,
# _VOLUME_RVOL_MAX_AGE_DAYS) STAY here (the _section_* read-side blocks read them
# too) ; the new module imports them back. This import sits AFTER those constants
# are defined, so the one-way pair (data_pool ← builders for re-export ;
# builders ← data_pool for constants) resolves with NO partial-init cycle.
from .dimension_vote_builders import (  # noqa: E402
    _cot_vote_from_rows,
    _tff_vote_from_rows,
    _volume_vote_from_reading,
    build_correlations_vote_for_asset,
    build_cot_vote_for_asset,
    build_geopolitics_vote_for_asset,
    build_manipulation_liquidity_vote_for_asset,
    build_positioning_divergence_vote_for_asset,
    build_positioning_tff_vote_for_asset,
    build_real_yield_vote_for_asset,
    build_sentiment_vote_for_asset,
    build_vol_regime_vote_for_asset,
    build_volume_vote_for_asset,
)


async def _section_prediction_markets(
    session: AsyncSession,
) -> tuple[str, list[str]]:
    """## Prediction markets — top priced markets per venue, ranked by volume."""
    cutoff = datetime.now(UTC) - timedelta(hours=12)
    sources: list[str] = []
    sections: list[str] = ["## Prediction markets (last 12h, top priced per venue by volume)"]

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
                # Percent format to match Kalshi/Manifold/consensus (was decimal
                # 0.42 vs their 42% — same quantity, two formats in one pool).
                yes_str = f"YES={yes:.0%}" if yes is not None else "YES=n/a"
                vol_str = f"${(r.volume_usd or 0) / 1e6:.1f}M" if r.volume_usd else "$?"
                sections.append(f"- {r.question[:80]} → {yes_str} vol={vol_str} (slug:{r.slug})")
                sources.append(f"polymarket:{r.slug}")

    # Kalshi — S03: the macro-series collector fix unlocked ~270 priced macro
    # markets; dedup latest-per-ticker + rank by 24h volume + group by series so
    # the KXFED rate ladder reads in strike order (was a raw top-5-by-recency
    # that discarded the macro pool + never deduped, unlike Polymarket above).
    # Descriptive only (ADR-017): we render the ladder, we derive no P(cut).
    kal_raw = list(
        (
            await session.execute(
                select(KalshiMarket)
                .where(KalshiMarket.fetched_at >= cutoff)
                .order_by(desc(KalshiMarket.fetched_at))
                .limit(500)
            )
        )
        .scalars()
        .all()
    )
    # Dedup on the LATEST snapshot per ticker (rows arrive fetched_at DESC),
    # then drop tickers whose latest snapshot is unpriced — never fall back to
    # a stale older price (mirrors the Polymarket block's true-latest dedup; a
    # now-unpriced market is dropped, not shown at its last-known value).
    seen_tickers: set[str] = set()
    kal_unique: list[KalshiMarket] = []
    for kr in kal_raw:
        if kr.ticker in seen_tickers:
            continue
        seen_tickers.add(kr.ticker)
        if kr.yes_price is None:
            continue
        kal_unique.append(kr)
    kal_unique.sort(key=lambda x: -(x.volume_24h or 0))
    kal_top = kal_unique[:12]
    sections.append(
        f"### Kalshi (top {len(kal_top)} priced macro by 24h volume, of {len(kal_unique)} fresh)"
    )
    if not kal_top:
        sections.append("- (no fresh priced snapshots)")
    else:
        # Group by series (ticker prefix) so a strike ladder reads coherently.
        kal_by_series: dict[str, list[KalshiMarket]] = {}
        for kr in kal_top:
            kal_by_series.setdefault(kr.ticker.split("-")[0], []).append(kr)
        for series_key, series_rows in kal_by_series.items():
            series_rows.sort(key=lambda x: x.ticker)  # strikes in order within a ladder
            for kr in series_rows:
                yp = f"YES={kr.yes_price:.0%}" if kr.yes_price is not None else "YES=n/a"
                vol = f" vol={kr.volume_24h}" if kr.volume_24h else ""
                sections.append(
                    f"- [{series_key}] {kr.title[:78]} → {yp}{vol} (ticker:{kr.ticker})"
                )
                sources.append(f"kalshi:{kr.ticker}")

    # Manifold (play-money sentiment) — same dedup-per-slug + volume rank + cap
    # as Polymarket/Kalshi for a deterministic surface (was top-5-by-recency,
    # undeduped). Kept smaller (8) as it is the secondary sentiment venue.
    man_raw = list(
        (
            await session.execute(
                select(ManifoldMarket)
                .where(ManifoldMarket.fetched_at >= cutoff)
                .order_by(desc(ManifoldMarket.fetched_at))
                .limit(500)
            )
        )
        .scalars()
        .all()
    )
    # Same true-latest dedup as Kalshi: latest snapshot per slug wins, drop if
    # that latest is unpriced (no stale fallback).
    seen_slugs_man: set[str] = set()
    man_unique: list[ManifoldMarket] = []
    for mr in man_raw:
        if mr.slug in seen_slugs_man:
            continue
        seen_slugs_man.add(mr.slug)
        if mr.probability is None:
            continue
        man_unique.append(mr)
    man_unique.sort(key=lambda x: -(x.volume or 0))
    man_top = man_unique[:8]
    sections.append(f"### Manifold (play-money sentiment — top {len(man_top)} by volume)")
    if not man_top:
        sections.append("- (no fresh priced snapshots)")
    else:
        for mr in man_top:
            p = f"P={mr.probability:.0%}" if mr.probability is not None else "P=n/a"
            sections.append(f"- {mr.question[:90]} → {p} (slug:{mr.slug})")
            sources.append(f"manifold:{mr.slug}")

    return "\n".join(sections), sources


# GDELT candidate pool before the per-asset filter — keep in lockstep with
# routers/geopolitics.py default-top pool (brain↔panel parity, pinned by
# test_geo_candidate_pool_parity_brain_vs_router).
#
# 2026-06-11 widened 40 → 400 (S04 TIER-2 #3 seal). Empirical prod witness:
# the pool is the WHOLE-WINDOW most-negative ranking, so a narrow cap makes
# per-asset differentiation depend on the day's tone mix, not on density —
# with 2,387 events/24h (403 gold rows) the 40-cap matched XAU=0, GBP=0,
# SPX=1 → systematic global fallback, while cap 400 matched XAU=48, GBP=9,
# SPX=11, EUR=38, NAS=74 → 5/5 assets differentiate with margin. 400 rows
# stays a bounded, index-friendly read (ix_gdelt_seendate + in-memory sort).
_GEO_GDELT_POOL = 400
_GEO_MIN_ASSET_MATCHES = 3  # below this, GDELT negatives fall back to the global ranking

# Column-vitality guard (2026-06-11): prod witness showed 13,607/13,607 GDELT
# rows at tone=0.0 over 8 days — the ArtList JSON feed carries no per-article
# tone (parser default 0.0), so a "most-negative" ranking over an all-zero
# pool is fabricated order (recency in disguise) and per-asset filtering of
# that unranked pool surfaces keyword noise. Below this sample size we do NOT
# declare the column dead (a tiny genuinely-neutral pool stays on the normal
# path); at/above it, 100% tone==0.0 → suspend the ranking honestly.
_GEO_TONE_DEAD_MIN_N = 20


async def _section_geopolitics(
    session: AsyncSession, asset: str | None = None
) -> tuple[str, list[str], list[DegradedInput]]:
    """## Geopolitics — AI-GPR latest (global) + GDELT critical cluster, per-asset.

    S04 TIER-2 #3 depth: AI-GPR stays the GLOBAL geopolitical-risk index (single
    index, identical for every asset by construction). The GDELT negative-event
    cluster is narrowed to the asset's conversation via
    ``filter_rows_by_asset_affinity`` (title + query_label + domain + url) with a
    scarce→global fallback, mirroring ``_section_news`` + ``routers/geopolitics.py``
    so the brain's per-asset card no longer reads an identical geopolitics block
    for gold, the euro and the Nasdaq. ADR-017-safe (keywords content-neutral).
    """
    lines = ["## Geopolitics"]
    sources: list[str] = []
    degraded: list[DegradedInput] = []
    _now = datetime.now(UTC).date()

    gpr_stmt = select(GprObservation).order_by(desc(GprObservation.observation_date)).limit(1)
    gpr = (await session.execute(gpr_stmt)).scalars().first()
    # S04 liveness gate — a stale AI-GPR must not render as the current
    # geopolitical-risk headline without an explicit STALE/ABSENT band +
    # degraded trace (the systemic stale-as-fresh « zone d'ombre »).
    live = classify_liveness(
        "AI-GPR",
        gpr.observation_date if gpr else None,
        now=_now,
        max_age_days=_GPR_MAX_AGE_DAYS,
        impacted="geopolitics",
    )
    if live.is_degraded:
        degraded.append(
            DegradedInput(
                series_id=live.source_key,
                status=live.status,  # type: ignore[arg-type]  # never "fresh" here
                latest_date=live.latest_date,
                age_days=live.age_days,
                max_age_days=live.max_age_days,
                impacted=live.impacted,
            )
        )
    if gpr is not None:
        lines.append(
            f"- AI-GPR = {gpr.ai_gpr:.1f} "
            f"(Iacoviello, observation_date={gpr.observation_date:%Y-%m-%d})"
        )
        sources.append(f"AI-GPR@{gpr.observation_date.isoformat()}")
        if live.is_degraded:
            lines.append(
                f"- ⚠ AI-GPR {live.status.upper()} : {live.age_days}j (max {live.max_age_days}j)"
            )
    else:
        lines.append(f"- ⚠ AI-GPR {live.status.upper()} : n/a")

    # GDELT negative-event cluster — per-asset (S04 TIER-2 #3). Pull a wider
    # candidate pool (deterministic tone-asc, seendate-desc on ties) then narrow
    # to the asset's conversation; scarce→global fallback. Mirrors the
    # /v1/geopolitics/briefing router so the panel and the brain agree.
    from .asset_news_affinity import filter_rows_by_asset_affinity

    cutoff = datetime.now(UTC) - timedelta(hours=24)
    # id.asc() tertiary tiebreak: (tone, seendate) is NOT a total order — the
    # same article ingested under several query_labels ties on both, and
    # Postgres gives no intra-tie guarantee (plan-dependent). Pinning the
    # tiebreak keeps the candidate pool deterministic across LIMIT changes.
    gdelt_stmt = (
        select(GdeltEvent)
        .where(GdeltEvent.seendate >= cutoff)
        .order_by(GdeltEvent.tone.asc(), GdeltEvent.seendate.desc(), GdeltEvent.id.asc())
        .limit(_GEO_GDELT_POOL)
    )
    gdelt_rows = list((await session.execute(gdelt_stmt)).scalars().all())
    tone_dead = len(gdelt_rows) >= _GEO_TONE_DEAD_MIN_N and all(r.tone == 0.0 for r in gdelt_rows)
    if tone_dead:
        # Honest absence > fabricated ranking (« sans zone d'ombre ») : with
        # the tone column flat-zero, "most-negative" would silently mean
        # "most-recent + keyword noise". Suspend the cluster, surface the
        # upstream data-quality hole, keep AI-GPR (independent source) above.
        # Pool-scoped wording (reviewer #230 MINOR 1): we measured the
        # candidate pool, not the whole 24h window — say exactly that.
        lines.append(
            f"- ⚠ GDELT tone ABSENT upstream (candidate pool {len(gdelt_rows)} rows, "
            "100% tone=0.0) — negative-event ranking suspended; per-asset headlines "
            "remain covered by the News section"
        )
        # max_age_days=0 convention: no age window applies — this is a
        # column-vitality absence, not a staleness verdict (reviewer #230
        # MINOR 2; consumers are pass-through today, any future ratio
        # consumer must special-case 0).
        degraded.append(
            DegradedInput(
                series_id="GDELT:tone",
                status="absent",
                latest_date=None,
                age_days=None,
                max_age_days=0,
                impacted="geopolitics",
            )
        )
    elif gdelt_rows:

        def _gd_key(r: GdeltEvent) -> tuple[str, str]:
            blob = " ".join([r.title or "", r.query_label or "", r.domain or ""])
            return blob, r.url or ""

        filtered, matched, applied = filter_rows_by_asset_affinity(
            gdelt_rows, asset, key=_gd_key, min_required=_GEO_MIN_ASSET_MATCHES
        )
        top = sorted(filtered, key=lambda r: r.tone)[:5]
        if asset and applied:
            lines.append(f"- GDELT 5 most-negative events last 24h, ticker-linked to {asset}:")
        elif asset:
            lines.append(
                f"- GDELT 5 most-negative events last 24h "
                f"(wide — {asset} match scarce, matched={matched}):"
            )
        else:
            lines.append("- GDELT 5 most-negative events last 24h:")
        for r in top:
            lines.append(
                f"  · tone={r.tone:+.1f} {r.title[:80]} "
                f"({r.domain or 'unknown'}, query={r.query_label}) {r.url}"
            )
            sources.append(r.url)
    else:
        lines.append("- GDELT: no events in the last 24h")

    return "\n".join(lines), sources, degraded


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


async def _section_volume_rvol(
    session: AsyncSession, asset: str
) -> tuple[str, list[str], list[DegradedInput]]:
    """## Relative volume / participation — daily RVOL + z-score + spike bucket.

    S04 TIER-2 depth for the Volume dimension: the microstructure block uses
    volume only as a weight; this answers « is participation light / normal / a
    spike vs its own history ? ». Index/commodity assets (SPX500 / NAS100 / XAU)
    carry real daily volume → RVOL + z-score + bucket. FX pairs carry no
    consolidated venue volume → honest N/A (data property, NOT degraded), emitted
    with ZERO DB I/O. A volume asset whose daily series is empty or stale beyond
    ``_VOLUME_RVOL_MAX_AGE_DAYS`` surfaces an explicit ABSENT/STALE band + degraded
    trace — S04 « sans zone d'ombre », no silent n/a.
    """
    degraded: list[DegradedInput] = []
    if asset not in _VOLUME_ASSETS:
        # FX (no consolidated venue volume) → honest N/A, NOT degraded, zero DB I/O.
        reading = classify_relative_volume(
            [], asset=asset, latest_date=None, volume_available=False
        )
        md, src = render_relative_volume_block(reading)
        return md, src, degraded
    _now = datetime.now(UTC).date()
    reading = await assess_relative_volume(session, asset)
    live = classify_liveness(
        f"market_data:{asset}:volume",
        reading.latest_date,
        now=_now,
        max_age_days=_VOLUME_RVOL_MAX_AGE_DAYS,
        impacted=f"volume_rvol:{asset}",
    )
    md, src = render_relative_volume_block(reading)
    if live.is_degraded:
        degraded.append(
            DegradedInput(
                series_id=live.source_key,
                status=live.status,  # type: ignore[arg-type]  # never "fresh" here
                latest_date=live.latest_date,
                age_days=live.age_days,
                max_age_days=live.max_age_days,
                impacted=live.impacted,
            )
        )
        if live.status == "stale":
            # render already showed the (stale) headline value; add the explicit band.
            md += (
                f"\n- ⚠ market_data:{asset}:volume STALE : "
                f"{live.age_days}j (max {live.max_age_days}j)"
            )
    return md, src, degraded


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


async def _section_manipulation_liquidity(session: AsyncSession) -> tuple[str, list[str]]:
    """## Manipulation & liquidity zones — S04 dimension (macro/structural facet).

    Wires the previously data_pool-orphan ``assess_liquidity_proxy`` (RRP+TGA
    combined drain) into the brain as the explicit « manipulations & zones de
    liquidité » dimension: macro funding-liquidity condition + its manipulation
    propensity implication. Distinct from ``_section_funding_stress`` (rates /
    credit funding) — this is the liquidity-DEPTH / manipulation-risk cross-read.
    Pure price-action liquidity zones (ICT) stay the Session-05 technical read.
    """
    reading = await assess_liquidity_proxy(session)
    return render_liquidity_proxy_block(reading)


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


_RECENT_ACTUAL_STATE_FR: dict[str, str] = {
    "above_range": "au-dessus du consensus",
    "below_range": "sous le consensus",
    "in_range": "dans la fourchette consensus",
    "exact_consensus": "pile sur le consensus",
    "unavailable": "écart vs consensus",
}


async def _section_recent_actuals(session: AsyncSession) -> tuple[str, list[str]]:
    """## Résultats économiques publiés (72h) — réactivité temps réel (§6.4).

    Surfaces the high/medium-impact economic releases of the last 72 h with
    their published `actual` vs consensus + the surprise magnitude, so the
    Pass-2 LLM can REACT when a print beats/misses expectations (e.g. an
    inflation print below consensus → USD-soft into the NY session). This is
    the structural real-time-reactivity layer the card was missing : the
    `recent_actuals` service was computed for the frontend only and never fed
    into the LLM prompt. Descriptive only (ADR-017) — magnitude/direction
    labels, never BUY/SELL. Honest empty state outside publication windows
    (e.g. weekend).
    """
    from .recent_actuals import fetch_recent_actuals

    rows = await fetch_recent_actuals(session, lookback_days=3, currency=None, limit=25)
    # Traded-currency universe = event_sentinel.RELEVANT_CURRENCIES (USD/EUR/GBP/CAD):
    # CAD belongs in here because USD_CAD is a traded asset (session_verdict_builder
    # maps it), so a CAD print (BoC, jobs) must feed the real-time reactivity layer.
    relevant = [
        r
        for r in rows
        if r.currency in {"USD", "EUR", "GBP", "CAD"} and r.impact in {"high", "medium"}
    ]
    lines = ["## Résultats économiques publiés (72h — actual vs consensus + surprise)"]
    if not relevant:
        lines.append(
            "- (aucun résultat à fort/moyen impact publié sur USD/EUR/GBP/CAD dans les 72h — "
            "hors fenêtre de publication, p. ex. week-end ; surveiller le calendrier ci-dessus)"
        )
        return "\n".join(lines), []

    sources: list[str] = []
    for r in relevant[:12]:
        cls = r.classification
        surprise = ""
        if cls.magnitude_pct is not None:
            surprise = (
                f" → surprise {cls.magnitude_pct:+.1f}% "
                f"({_RECENT_ACTUAL_STATE_FR.get(cls.state, cls.state)})"
            )
        cons = f", cons. {r.forecast}" if r.forecast else ""
        prev = f", préc. {r.previous}" if r.previous else ""
        lines.append(
            f"- {r.scheduled_at:%m-%d %H:%M}Z {r.currency} [{r.impact}] "
            f"{r.title[:60]} : actual {r.actual}{cons}{prev}{surprise}"
        )
        sources.append("ForexFactory:economic_events")
    lines.append(
        "- _Réactivité : un actual qui s'écarte nettement du consensus recalibre la lecture "
        "(la surprise, pas le chiffre brut, déplace le marché) — intègre-la dans la direction NY._"
    )
    return "\n".join(lines), list(dict.fromkeys(sources))


def _fmt_px(p: float) -> str:
    """Price formatter : 5 dp for FX (<10), 2 dp for indices/gold."""
    return f"{p:.5f}" if abs(p) < 10 else f"{p:.2f}"


async def _section_london_session(session: AsyncSession, asset: str) -> tuple[str, list[str]]:
    """## Session de Londres — lecture pour calibrer la session NY (§6.2).

    Surfaces how the asset traded during the London MORNING window (the
    session running before/into the NY open) — range, direction, and whether
    it was unusually active vs the typical London morning — so the Pass-2 LLM
    calibrates the NY-session view on the live London behaviour (owner §6.2
    CAPITAL point). Reuses `compute_london_session` (pure, DST-correct via
    ZoneInfo) ; honest empty when no London bars. Descriptive (ADR-017).
    """
    from .london_session import compute_london_session_for_asset

    now = datetime.now(UTC)
    # Shared SSOT async wrapper — same bar fetch + compute the
    # `/v1/london-session/{asset}` endpoint uses, so the Pass-2 prose and the
    # frontend `<LondonSessionPanel>` can never diverge on the read.
    read = await compute_london_session_for_asset(session, asset, now_utc=now)
    lines = ["## Session de Londres — lecture pour calibrer la session NY"]
    if read is None:
        lines.append(
            "- (pas de bars Londres exploitables — fenêtre pas encore ouverte ou intraday indisponible)"
        )
        return "\n".join(lines), []

    freshness = (
        "ce matin (en direct)"
        if read.is_today
        else f"dernière séance du {read.session_date:%Y-%m-%d}"
    )
    dir_fr = {"up": "haussière", "down": "baissière", "range": "en range (indécise)"}[
        read.direction
    ]
    activity = ""
    if read.range_ratio is not None:
        tag = (
            "séance ACTIVE"
            if read.range_ratio >= 1.4
            else "séance CALME"
            if read.range_ratio <= 0.6
            else "normale"
        )
        activity = f" — range {read.range_ratio:.1f}× la moyenne 5 j ({tag})"
    net_sign = "+" if read.net_change >= 0 else "−"
    lines.append(
        f"- {freshness} : ouverture {_fmt_px(read.open_price)} → clôture {_fmt_px(read.close)} "
        f"(var {net_sign}{_fmt_px(abs(read.net_change))} ; H {_fmt_px(read.high)} / "
        f"B {_fmt_px(read.low)}), direction {dir_fr}{activity} ({read.bar_count} min)."
    )
    lines.append(
        "- _Calibration NY : une matinée Londres directionnelle ET active prolonge souvent le "
        "momentum à l'open NY ; une matinée en range/calme suggère l'attente d'un catalyseur NY._"
    )
    return "\n".join(lines), [f"polygon_intraday:{asset}@london_morning"]


async def _section_technical_methodology(
    session: AsyncSession, asset: str
) -> tuple[str, list[str]]:
    """## Lecture technique — la méthodologie du trader exécutée par Ichor (ADR-113).

    S05/Chantier E slice-1 : fills the prose slot reserved by
    ``liquidity_proxy.py`` (« pure price-action liquidity zones … are the
    technical reading (Session 05) »). Renders the H1 élan
    (poussées/corrections, retournement potentiel), the origines
    acheteuses/vendeuses N1/N2 of the previous NY session (3-tier retest
    band, proximity-ranked), the golden zone 0,5-0,618 and the « mèche du
    plongeur » day-open status — per docs/METHODOLOGIE_TECHNIQUE_ELIOT.md,
    the codified SSOT. Always rendered (honest absence prose) ; descriptive
    only, ADR-017 boundary self-affirmed in the closing line.
    """
    from .technical_analysis import assess_technical_reading, render_technical_reading_block

    reading = await assess_technical_reading(session, asset)
    return render_technical_reading_block(reading, asset)


async def _section_calendar(session: AsyncSession, asset: str) -> tuple[str, list[str]]:
    """## Economic calendar — next 14 days affecting `asset`."""
    report = await assess_calendar(session, horizon_days=14)
    return render_calendar_block(report, asset=asset, max_items=10)


async def _section_today_schedule(session: AsyncSession, asset: str) -> tuple[str, list[str]]:
    """## Today's full economic schedule — every release, all impact tiers.

    Where `_section_calendar` answers "what's coming in the next 14 days?"
    (medium/high only, capped at 10), this answers "what is on *today's*
    agenda?" with NO impact filter and NO cap — the complete day's docket
    (S03/D1 completeness). "Today" is Paris-local (Eliot's operating window),
    mirroring the verdict builder, so the docket lines up with the session
    the card is generated for. We query `economic_events` directly because
    `assess_calendar` hard-drops low-impact rows at the SQL layer; here every
    tier is surfaced and source-stamped, with a per-asset relevance flag from
    the same currency→asset map as the upcoming-calendar feed. Descriptive
    only (ADR-017): it states WHAT releases WHEN, never an action.
    """
    from ..models import EconomicEvent
    from .economic_calendar import _FF_CURRENCY_MAP
    from .session_verdict_builder import _today_paris_midnight_utc

    now = datetime.now(UTC)
    start = _today_paris_midnight_utc(now)
    end = start + timedelta(days=1)
    rows = list(
        (
            await session.execute(
                select(EconomicEvent)
                .where(
                    EconomicEvent.scheduled_at.is_not(None),
                    EconomicEvent.scheduled_at >= start,
                    EconomicEvent.scheduled_at < end,
                )
                .order_by(EconomicEvent.scheduled_at.asc())
            )
        )
        .scalars()
        .all()
    )

    header = "## Today's economic schedule — every release, all impact tiers"
    if not rows:
        return (f"{header}\n- (no economic releases scheduled today)", [])

    impact_tag = {"high": "🔴 HIGH", "medium": "🟡 medium", "low": "🟢 low"}
    asset_u = asset.upper()
    lines = [header]
    sources: list[str] = []
    for r in rows:
        region, affected = _FF_CURRENCY_MAP.get(r.currency, (r.currency, []))
        when = "all day" if r.is_all_day else f"{r.scheduled_at:%H:%M} UTC"
        tag = impact_tag.get(r.impact, f"⚪ {r.impact}")
        detail_parts: list[str] = []
        if r.forecast:
            detail_parts.append(f"forecast={r.forecast}")
        if r.previous:
            detail_parts.append(f"previous={r.previous}")
        if r.actual:
            detail_parts.append(f"actual={r.actual}")
        detail = (" · " + " ".join(detail_parts)) if detail_parts else ""
        relevance = "  ← affects this asset" if asset_u in affected else ""
        lines.append(f"- {when} [{region}] {tag} · {r.title}{detail}{relevance}")
        sources.append(f"economic_events:{r.currency}")

    return "\n".join(lines), sources


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
# r138 — `_NEWS_KEYWORDS` + `_matches_asset` extracted to
# `services/asset_news_affinity.py` (doctrine #4 anti-accumulation
# SSOT) so `/v1/news` and `/v1/geopolitics/briefing` can share the
# same affinity logic with this Pass-2 LLM data-pool reader. The
# private re-import aliases at the top of this file preserve the
# pre-r138 internal name pattern — zero behaviour change here.


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

    # r138 code-reviewer S4 — adopt the SSOT helper (the WHOLE POINT of
    # extracting `asset_news_affinity` in r138 was to deduplicate this
    # scarce-fallback dance across data_pool + news.py + geopolitics.py).
    # Behaviour pinned identical to the pre-r138 hand-rolled version
    # (min_required=3, fallback to global, top-8 cap on applied filter).
    if asset:
        from .asset_news_affinity import filter_rows_by_asset_affinity as _filter_helper

        filtered_rows, matched, applied = _filter_helper(
            rows,
            asset,
            # r139 matcher extension — include summary as 3rd field. Mirror
            # of routers/news.py key (parity LLM-pool reasoning vs endpoint
            # render). Empirical 2026-05-22 Hetzner survey: ~70% macro-vocab
            # lives in summary, not title/url.
            key=lambda r: (r.title or "", r.url or "", r.summary or ""),
            min_required=3,
        )
        if applied:
            filtered = filtered_rows[:8]
            label = f"## News (last 12h, top {len(filtered)} ticker-linked to {asset})"
        else:
            filtered = filtered_rows[:8]
            label = (
                f"## News (last 12h, top 8 — wide fallback, "
                f"{asset} match scarce, matched={matched})"
            )
    else:
        filtered = rows[:8]
        label = "## News (last 12h, top 8 most recent)"

    lines = [label]
    sources: list[str] = []
    for r in filtered:
        # S04 depth-audit fix: surface the FinBERT tone (label + signed score)
        # that run_news_tone_scorer already persists per headline — it was
        # computed + stored but dropped at render, so the brain saw headlines
        # with no sentiment polarity. Defensive None-guard (legacy unsccored
        # rows). Descriptive sentiment, not a trade signal (ADR-017 clean).
        tone = ""
        if r.tone_label is not None and r.tone_score is not None:
            tone = f" [tone {r.tone_label} {r.tone_score:+.2f}]"
        lines.append(f"- {r.published_at:%Y-%m-%d %H:%M} {r.source} · {r.title[:90]}{tone} {r.url}")
        sources.append(r.url)
    return "\n".join(lines), sources


# Per-asset live-web-research queries (SSOT). 2-3 targeted queries each,
# asset-relevant, so SearXNG returns the macro/driver headlines that
# matter for that pair / index. Plain search strings — NO directional
# imperatives (the service also ADR-017-DROPs dirty snippets ; this map
# is the framing layer and must stay clean).
_WEB_RESEARCH_QUERIES: dict[str, tuple[str, ...]] = {
    "EUR_USD": (
        "EUR USD ECB Fed monetary policy today",
        "eurozone economic news today",
    ),
    "GBP_USD": (
        "GBP USD BoE UK economy news today",
        "pound sterling drivers today",
    ),
    "USD_CAD": (
        "USD CAD Bank of Canada oil news today",
        "Canadian dollar drivers today",
    ),
    "XAU_USD": (
        "gold price drivers today",
        "XAU USD safe haven real yields news today",
    ),
    "NAS100_USD": (
        "Nasdaq US equity market news today",
        "US tech stocks macro risk sentiment today",
    ),
    "SPX500_USD": (
        "S&P 500 US equity market news today",
        "US macro risk sentiment today",
    ),
    # Tracked-no-card pairs kept for explicit --assets queries.
    "USD_JPY": (
        "USD JPY Bank of Japan intervention news today",
        "Japanese yen drivers today",
    ),
    "AUD_USD": (
        "AUD USD RBA commodity China news today",
        "Australian dollar drivers today",
    ),
}

# Total clean snapshots surfaced into the section (across all queries).
_WEB_RESEARCH_TOTAL_CAP = 10
# Clean results requested per individual query before the merge.
_WEB_RESEARCH_PER_QUERY = 6


async def _section_web_research(session: AsyncSession, asset: str) -> tuple[str, list[str]]:
    """## Recherche web en direct (SearXNG) — actualité live (§6, ADR-084).

    Runs 2-3 asset-targeted web queries against the self-hosted SearXNG
    instance (loopback, ADR-084) and surfaces the deduped, ADR-017-safe
    headlines so the Pass-2 LLM sees what is happening RIGHT NOW (ECB/Fed
    headlines, geopolitical shocks, commodity moves) beyond the ingested
    collectors. The `web_research` service already sanitizes (DROP policy
    on any trade-signal token) ; this section only adds clean factual
    framing. Always-rendered honest-absence when 0 results (SearXNG down
    / no hits) so Pass-2 sees the explicit state, never a missing
    section. `session` is accepted for signature parity with the other
    sections (this read is HTTP-only, no DB). Descriptive only (ADR-017).
    """
    from .web_research import fetch_web_research

    queries = _WEB_RESEARCH_QUERIES.get(asset.upper(), ())
    lines = ["## Recherche web en direct (SearXNG — actualité live, pas un signal)"]
    if not queries:
        lines.append(
            "- (pas de requêtes de recherche définies pour cet actif — section non applicable)"
        )
        return "\n".join(lines), []

    # Merge + dedup across queries (by URL ; keep first-seen).
    seen_urls: set[str] = set()
    merged: list = []
    for q in queries:
        for r in await fetch_web_research(q, limit=_WEB_RESEARCH_PER_QUERY):
            if r.url in seen_urls:
                continue
            seen_urls.add(r.url)
            merged.append(r)
            if len(merged) >= _WEB_RESEARCH_TOTAL_CAP:
                break
        if len(merged) >= _WEB_RESEARCH_TOTAL_CAP:
            break

    if not merged:
        lines.append(
            "- (recherche web indisponible — SearXNG injoignable ou aucun résultat exploitable ; "
            "s'appuyer sur les collecteurs ci-dessus)"
        )
        return "\n".join(lines), []

    sources: list[str] = []
    for r in merged:
        when = f" ({r.published_at})" if r.published_at else ""
        domain = r.source_domain or "web"
        snippet = (r.snippet[:200] + "…") if len(r.snippet) > 200 else r.snippet
        lines.append(f"- [{domain}]{when} {r.title[:120]} — {snippet}")
        sources.append(r.url)
    lines.append(
        "- _Recherche web en direct : contexte d'actualité brut à recouper avec les sources "
        "ci-dessus ; descriptif, pas un signal de trading._"
    )
    stamp = f"web_research:searxng@{datetime.now(UTC):%Y-%m-%dT%H:%M:%SZ}"
    sources.append(stamp)
    return "\n".join(lines), list(dict.fromkeys(sources))


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

    # ADR-103 (ADR-099 §T3.2) — runtime FRED-liveness audit, ALWAYS
    # rendered, inserted at index 1 (right after executive_summary,
    # before macro_trinity) so Pass-1 régime + Pass-2 are primed with
    # data-health context first. Breaks the silent-skip chain — a
    # dead/stale critical anchor (China-M1 class, ADR-093 §r49) is now
    # explicit every card instead of a section vanishing with zero
    # trace. `degraded_inputs` is carried to the deterministic header +
    # the DataPool projection (operator surface / r94 badge foundation).
    integ_md, integ_src, degraded_inputs = await _section_data_integrity(session, asset)
    sections.insert(1, ("data_integrity", integ_md, integ_src))

    smile_md, smile_src = await _section_dollar_smile(session)
    sections.append(("dollar_smile", smile_md, smile_src))

    # Round-54 — Key levels (non-technical, ADR-083 D3 phase 1).
    # Cross-asset section : TGA threshold for liquidity-gate switch.
    # r55+ extends with peg_break, gamma_flip, vix_regime, polymarket.
    # Always-rendered (even when no level fires) so Pass 2 sees the
    # explicit "no switch active" state instead of missing data.
    kl_md, kl_src = await _section_key_levels(session)
    sections.append(("key_levels", kl_md, kl_src))

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
    mct_md, mct_src, mct_degraded = await _section_nyfed_mct(session)
    sections.append(("nyfed_mct", mct_md, mct_src))
    degraded_inputs.extend(mct_degraded)

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
    cam_md, cam_src, cam_degraded = await _section_cross_asset_matrix(session)
    degraded_inputs.extend(cam_degraded)
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

    today_md, today_src = await _section_today_schedule(session, asset)
    sections.append(("today_schedule", today_md, today_src))

    ra_md, ra_src = await _section_recent_actuals(session)
    sections.append(("recent_actuals", ra_md, ra_src))

    london_md, london_src = await _section_london_session(session, asset)
    sections.append(("london_session", london_md, london_src))

    diff_md, diff_src = await _section_rate_diff(session, asset)
    if diff_md:
        sections.append(("rate_diff", diff_md, diff_src))

    # r180 — G5 CONSUMER WIRING : previous-session origin zone (Eliot
    # Fathom §V practitioner context). Surfaces the r179 G5 EXECUTION
    # classifier output as plain-FR prose for Pass-2 narrative.
    # Always-rendered : when the snapshot is None (week-end / holiday /
    # bar_count < 30), the section emits an explicit honest-absence
    # prose so Pass-2 sees the state instead of a vanishing section.
    # ADR-017 boundary preserved (pure factual snapshot, never
    # directional bias for the CURRENT session).
    osz_md, osz_src = await _section_previous_session_context(session, asset)
    sections.append(("previous_session_origin_zone", osz_md, osz_src))

    # S05 / Chantier E slice-1 (ADR-113) — la lecture technique exécutée par
    # Ichor selon la méthodologie codifiée du trader (élan H1 poussées/
    # corrections, origines acheteuses/vendeuses N1-N2 de la session NY
    # précédente, golden zone 0,5-0,618, statut « mèche du plongeur »).
    # Always-rendered : honest-absence prose quand l'intraday est
    # insuffisant. ADR-017 boundary self-affirmed (lecture descriptive,
    # jamais d'instruction d'exécution).
    ta_md, ta_src = await _section_technical_methodology(session, asset)
    sections.append(("technical_methodology", ta_md, ta_src))

    # r183 — N1 THEME CONSUMER WIRING : theme sous-jacent dominant
    # (Eliot Fathom transcript étape 1). Surfaces the r182 N1 EXECUTION
    # classifier output as plain-FR prose for Pass-2 narrative. The
    # 8-driver ranking is a CROSS-ASSET macro state read inserted at
    # ALL 5 priority assets (same ranking ; the asset-specific blocks
    # downstream interpret the same theme through asset-specific lens).
    # Always-rendered : honest-absence prose when classifier returns
    # None. ADR-017 boundary preserved (pure factual ranking).
    theme_md, theme_src = await _section_theme_dominant(session, asset)
    sections.append(("theme_dominant", theme_md, theme_src))

    # ADR-090 P0 step-3 (round-32) — EUR-specific Bund 10Y yield.
    # Asset-gated to EUR_USD ; silent skip otherwise OR if the
    # Bundesbank collector is dormant / pre-deploy. Symmetric
    # interpretive language : the Pass-2 LLM picks the right framing
    # based on Pass-1's regime label.
    eur_md, eur_src = await _section_eur_specific(session, asset)
    if eur_src:
        sections.append(("eur_specific", eur_md, eur_src))

    # Round-41 — XAU-specific Gold-Real-Yield-Triangle (GAP-A continuation,
    # R24 SUBSET-not-SUPERSET clears : both DFII10 + DTWEXBGS are daily-
    # available in fred_observations, no monthly-OECD staleness trap).
    # Asset-gated to XAU_USD ; silent skip otherwise OR if DFII10 absent
    # (primary gold driver — without it, the section refuses to render).
    xau_md, xau_src = await _section_xau_specific(session, asset)
    if xau_src:
        sections.append(("xau_specific", xau_md, xau_src))

    # Round-42 — NAS-specific duration-vol-tail triangle (GAP-A
    # continuation 2/5, R24 SUBSET-not-SUPERSET clears : DGS10 daily
    # FRED + VVIX/SKEW daily CBOE). Asset-gated to NAS100_USD ; silent
    # skip otherwise OR if DGS10 absent (primary duration driver).
    nas_md, nas_src = await _section_nas_specific(session, asset)
    if nas_src:
        sections.append(("nas_specific", nas_md, nas_src))

    # Round-43 — SPX-specific VIX-term-structure + funding + sentiment
    # triangle (GAP-A continuation 3/5, R24 SUBSET-not-SUPERSET clears
    # via VIX/VXV daily + NFCI weekly + SBOI monthly with frequency
    # mismatch warning inline). Asset-gated to SPX500_USD ; silent skip
    # otherwise OR if VIXCLS absent (primary tail-regime driver).
    spx_md, spx_src = await _section_spx_specific(session, asset)
    if spx_src:
        sections.append(("spx_specific", spx_md, spx_src))

    # Round-45 — JPY-specific US-JP rate-differential triangulation
    # (GAP-A continuation 4/5 via ADR-092 PROPOSED Tier 1 inline-FRED ship,
    # BTP r34 cadence-mismatch precedent). Asset-gated to USD_JPY ; silent
    # skip otherwise OR if IRLTLT01JPM156N absent (primary JPY anchor).
    # Frameworks : Engel-West 2005 + Adrian-Etula-Muir 2014 + Brunnermeier-
    # Nagel-Pedersen 2009 carry-crash skew.
    jpy_md, jpy_src = await _section_jpy_specific(session, asset)
    if jpy_src:
        sections.append(("jpy_specific", jpy_md, jpy_src))

    # Round-46 — AUD-specific commodity-currency triangulation (GAP-A
    # continuation 5/5 closure via ADR-092 PROPOSED Tier 1 inline-FRED
    # ship + ADR-093 PROPOSED "degraded explicit" surface pattern).
    # Asset-gated to AUD_USD ; silent skip otherwise OR if IRLTLT01AUM156N
    # absent (primary AUD anchor). 3/3 monthly drivers (rate-diff via AU 10Y
    # + DGS10 + China M1 + iron-ore + copper composite) with degraded
    # explicit annotation — DGS10 is the only daily anchor used solely for
    # the rate-differential computation. Frameworks : Engel-West 2005 +
    # Chen-Rogoff 2003 + Ready-Roussanov-Ward 2017.
    aud_md, aud_src = await _section_aud_specific(session, asset)
    if aud_src:
        sections.append(("aud_specific", aud_md, aud_src))

    # Round-90 — GBP-specific UK-US rate-differential + sterling risk-
    # premium (ADR-099 Tier 2 continuation ; ADR-101 extends Accepted
    # ADR-092 to GBP_USD — the only ADR-083 priority asset previously
    # without a per-asset section). Asset-gated to GBP_USD ; silent skip
    # otherwise OR if IRLTLT01GBM156N absent (primary UK anchor).
    # 2-driver + front-end term-structure refinement, inline-FRED, ZERO
    # new ingestion (IRLTLT01GBM156N + DGS10 + DGS3MO + IR3TIB01GBM156N
    # all already polled, GBP already in _RATE_DIFF_PAIRS). GBP/USD
    # polarity is INVERSE to USD/JPY (USD is the quote currency).
    # Frameworks : Engel-West 2005 + Della Corte-Sarno-Sestieri 2012 ;
    # the BoE-Fed front-end leg (Clarida-Gali-Gertler-1998-motivated) is
    # WIRED r103 as a term-structure REFINEMENT of Driver-1 — NOT a
    # co-equal Driver-3 (ADR-101 §Impl(r103)).
    gbp_md, gbp_src = await _section_gbp_specific(session, asset)
    if gbp_src:
        sections.append(("gbp_specific", gbp_md, gbp_src))

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

    # S04 TIER-2 — relative-volume / participation (RVOL + z-score + spike).
    # Always rendered: a value for volume-bearing assets (SPX500/NAS100/XAU), an
    # explicit honest-N/A for FX. 3-tuple: degraded surfaces empty/stale volume.
    rvol_md, rvol_src, rvol_deg = await _section_volume_rvol(session, asset)
    degraded_inputs.extend(rvol_deg)
    sections.append(("volume_rvol", rvol_md, rvol_src))

    asian_md, asian_src = await _section_asian_session(session, asset)
    if asian_md:
        sections.append(("asian_session", asian_md, asian_src))

    cot_md, cot_src, cot_deg = await _section_cot(session, asset)
    degraded_inputs.extend(cot_deg)
    if cot_md:
        sections.append(("cot", cot_md, cot_src))

    # Wave 26 Phase II — surface CFTC TFF 4-class positioning per asset.
    # Asset-conditional via _TFF_MARKET_BY_ASSET (skip if unmapped). Sister
    # to _section_cot (Disaggregated) but TFF is the financial-futures-only
    # report with the AssetMgr / LevFunds split that COT lacks.
    tff_md, tff_src, tff_deg = await _section_tff_positioning(session, asset)
    degraded_inputs.extend(tff_deg)
    if tff_md:
        sections.append(("tff_positioning", tff_md, tff_src))

    # S04 TIER-2 #4 — UST 10Y rate-sensitivity context for index assets only.
    rate_md, rate_src, rate_deg = await _section_rate_positioning(session, asset)
    degraded_inputs.extend(rate_deg)
    if rate_md:
        sections.append(("rate_positioning", rate_md, rate_src))

    pm_md, pm_src = await _section_prediction_markets(session)
    sections.append(("prediction_markets", pm_md, pm_src))

    pmi_md, pmi_src = await _section_polymarket_impact(session)
    sections.append(("polymarket_impact", pmi_md, pmi_src))

    pe_md, pe_src = await _section_portfolio_exposure(session)
    sections.append(("portfolio_exposure", pe_md, pe_src))

    fs_md, fs_src = await _section_funding_stress(session)
    sections.append(("funding_stress", fs_md, fs_src))

    ml_md, ml_src = await _section_manipulation_liquidity(session)
    sections.append(("manipulation_liquidity", ml_md, ml_src))

    si_md, si_src = await _section_surprise_index(session)
    sections.append(("surprise_index", si_md, si_src))

    nar_md, nar_src = await _section_narrative(session)
    sections.append(("narrative", nar_md, nar_src))

    cbi_md, cbi_src = await _section_cb_intervention(session, asset)
    if cbi_md:
        sections.append(("cb_intervention", cbi_md, cbi_src))

    geo_md, geo_src, geo_deg = await _section_geopolitics(session, asset)
    degraded_inputs.extend(geo_deg)
    sections.append(("geopolitics", geo_md, geo_src))

    cb_md, cb_src = await _section_cb_speeches(session)
    sections.append(("cb_speeches", cb_md, cb_src))

    # Phase 2 — Couche-2 agents output (CB-NLP, News-NLP, Sentiment, Positioning)
    # Pass the asset so News-NLP surfaces this card's per-asset news tone (S04 #4).
    c2_md, c2_src = await render_couche2_block(session, asset)
    sections.append(("couche2", c2_md, c2_src))

    # Phase 2 — divergence cross-venue (Polymarket vs Kalshi vs Manifold).
    # The deterministic event-key matcher layer is read once here (fail-closed:
    # flag absent → False → Jaccard-only, byte-identical) and threaded into both
    # the divergence and consensus blocks so they share one matcher decision.
    from .divergence import EVENT_KEY_MATCHER_FLAG
    from .feature_flags import is_enabled

    pred_event_key = await is_enabled(session, EVENT_KEY_MATCHER_FLAG)
    div_md, div_src = await render_divergence_block(session, use_event_key=pred_event_key)
    sections.append(("divergence", div_md, div_src))

    # S03 Chantier D — cross-venue consensus: one reliability-weighted
    # probability per matched macro event (complements divergence's spread).
    # Real-money venues carry it, play-money Manifold discounted. Descriptive
    # macro prior for Pass-2 (ADR-017 — never a trade signal).
    cons_md, cons_src = await render_consensus_block(session, use_event_key=pred_event_key)
    sections.append(("prediction_consensus", cons_md, cons_src))

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

    # W103 (ADR-084) — live web research via self-hosted SearXNG. Placed
    # next to `news` (both are real-time external-actuality surfaces).
    # Fail-open by construction (the service returns [] on any error) ;
    # wrapped here too so a section-level bug can never break card
    # generation — Pass-2 sees the honest-absence prose instead.
    try:
        web_md, web_src = await _section_web_research(session, asset)
    except Exception:  # noqa: BLE001 — web research must never block a card
        web_md, web_src = (
            "## Recherche web en direct (SearXNG — actualité live, pas un signal)\n"
            "- (recherche web indisponible — erreur interne ; s'appuyer sur les collecteurs ci-dessus)",
            [],
        )
    sections.append(("web_research", web_md, web_src))

    body = "\n\n".join(md for _, md, _ in sections)
    all_sources: list[str] = []
    for _, _, srcs in sections:
        all_sources.extend(srcs)
    sections_emitted = [name for name, _, _ in sections]

    now = datetime.now(UTC)
    # ADR-103 — deterministic, LLM-independent integrity line in the
    # header machine-truth (separate from the LLM-primed section body).
    integrity_line = f"Data integrity : {len(degraded_inputs)} critical anchor(s) degraded" + (
        " — " + ", ".join(f"{d.series_id}({d.status})" for d in degraded_inputs)
        if degraded_inputs
        else " (all fresh)"
    )
    header = (
        f"# Ichor data pool — {asset} — generated {now:%Y-%m-%d %H:%M UTC}\n\n"
        f"Sections : {', '.join(sections_emitted)}\n"
        f"{integrity_line}\n"
        f"Total sources cited : {len(all_sources)}\n\n---"
    )
    markdown = f"{header}\n\n{body}\n"
    return DataPool(
        asset=asset,
        generated_at=now,
        markdown=markdown,
        sources=all_sources,
        sections_emitted=sections_emitted,
        degraded_inputs=degraded_inputs,
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
    # S05 / ADR-113 — la lecture technique (méthodologie du trader) pour le
    # slice asset-specific Pass-2.
    ta_md, _ = await _section_technical_methodology(session, asset)
    if ta_md:
        parts.append(ta_md)
    # S04 TIER-2 — asset-specific relative-volume / participation for Pass-2.
    rvol_md, _, _ = await _section_volume_rvol(session, asset)
    if rvol_md:
        parts.append(rvol_md)
    rate_md, _, _ = await _section_rate_positioning(session, asset)
    if rate_md:
        parts.append(rate_md)
    cot_md, _, _ = await _section_cot(session, asset)
    if cot_md:
        parts.append(cot_md)
    pm_md, _ = await _section_prediction_markets(session)
    parts.append(pm_md)
    return "\n\n".join(parts) if parts else "(no asset-specific data available)"
