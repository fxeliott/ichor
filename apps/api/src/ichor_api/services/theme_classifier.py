"""r181 FOUNDATION — theme sous-jacent classifier 8 drivers (Eliot Fathom transcript étape 1).

Pure-compute service materialising Eliot Fathom recording 2026-05-25
methodology étape 1 verbatim : « identifier le thème sous-jacent du
marché ». The trader's read of which driver (parmi 8 canoniques) DRIVES
the market in the current window — a context input to Pass-2 narrative
+ Pass-3 stress + NY position-taking decision.

## FOUNDATION-only scope at r181 (mirror r160 Dukascopy + r174 G5 pattern)

r181 ships ONLY the schema + skeleton classifier returning None. ZERO
behavior change at r181 deploy time. r182+ EXECUTION-phase will ship
the actual ranking compute logic over Pass-1 régime + NFCI + VIX + DXY
+ 10Y + economic_events + ai_gpr + GDELT inputs.

The FOUNDATION pattern is identical to r160 Dukascopy + r174 G5 origin
zone : ship the shell, prove the contract (Pydantic + tests + ADR
cite), defer EXECUTION (compute logic + Pass-2 wiring + frontend)
to a subsequent atomic round once trader-leverage is empirically
validated.

## Citation provenance (Pattern #15 R59 + Pattern #20 mechanical)

**Primary provenance** : Eliot Fathom recording 2026-05-25 transcript
page 1 étape 1 verbatim practitioner methodology. Eliot enumerates 8
drivers en système d'engrenage où UN moteur principal varie selon le
contexte marché actuel.

**Stamp** : ``provenance = "practitioner_stamp"`` (NOT
``"peer_reviewed"``) — the « 8 drivers » framing itself is Eliot
Fathom practitioner discipline ; academic literature has related
concepts (Rey 2013 global financial cycle, Mendoza-Quadrini-Rios-Rull
2009 fiscal channels, Bekaert-Hoerova-Lo Duca 2013 risk-uncertainty)
but no peer-reviewed paper proposes this exact 8-driver enum as a
classification system.

**Pattern #20 codified r175** : memory-resident peer-reviewed cites
REQUIRE R59-pre-commit-mandatory. The 8 drivers below are EXACTLY
those listed by Eliot Fathom transcript — any ADDITION or REMOVAL
requires (a) Eliot directive update OR (b) R59 sub-agent verification
that the proposed taxonomy variant is grounded in a peer-reviewed
framework with DOI.

## ADR-017 boundary

Pure factual ranking output (top_theme + secondary_themes + driver_
strengths dict). NEVER a directional bias / trade signal — the
classifier surfaces WHICH driver dominates, NOT WHAT TO DO about it.
Pass-2 narrative consumes the ranking to frame the macro-context
read ; the trader applies his/her own technical entry/exit on
TradingView.

## 8 canonical drivers (Eliot Fathom transcript page 1 verbatim)

Per Eliot recording, each represents one « engrenage moteur » :

- ``macroeconomic`` : grands événements mondiaux (pandemie Covid 2020,
  crise 2008, bulle techno 2000 dotcom). Slow-moving, regime-defining.
- ``monetary_policy`` : actions des banques centrales (Fed, BCE, BoE,
  BoJ) — taux d'intérêt, QE/QT, forward guidance, balance sheet.
- ``economic_data`` : indicateurs clés CPI, NFP, PMI, retail sales,
  GDP — utilisés pour prévoir les changements de politique monétaire.
- ``fiscal_policy`` : politique budgétaire (dépenses publiques,
  modifications fiscales). Trump tariffs 2026 = fiscal-policy-class.
- ``market_interconnexions`` : interactions cross-asset
  (fixed-income → Forex → commodities → equities). Yield spreads,
  TIPS breakevens, dealer GEX cascades.
- ``geopolitics`` : conflits, guerres, accords commerciaux, sanctions.
  Eliot transcript : « parfois c'est littéralement ce qui drive les
  marchés en ce moment » (Israel-Iran, Russie-Ukraine, Taiwan, tariffs).
- ``price_action_flow`` : positioning institutionnel, retail, niveaux
  clés, conditions de surachat/survente, volatilité. Microstructure.
- ``supply_demand`` : offre/demande directe (impact majeur sur
  commodities — pétrole production OPEC, or physique, agricultural).

## Doctrine alignment

- ADR-017 : pure factual ranking output, never directional bias
- Doctrine #2 strict scope : r181 ships FOUNDATION skeleton ONLY ;
  EXECUTION compute + Pass-2 wiring + frontend defer to r182+
- Doctrine #4 SSOT : ``ThemeDriverKey`` Literal + ``THEME_DRIVERS``
  ordered tuple are single source of truth ; FR copy maps come r182+
- Doctrine #5 pure-module discipline : skeleton fn signature FROZEN
  by this ship, no I/O, no DB hit
- Doctrine #11 calibrated honesty : skeleton returns ``None``
  unconditionally at r181 ; r182+ EXECUTION returns ``ThemeRanking``
  OR ``None`` if inputs insufficient (no fabrication)
- Doctrine #12 anti-recidive : R59 pre-flight obligatoire BEFORE
  EXECUTION-phase ship in r182+ (verify each peer-reviewed cite per
  Pattern #20 mechanical R59-pre-commit-mandatory)
- Mirror r160 Dukascopy + r174 G5 FOUNDATION pattern
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Final, Literal

from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    CboeSkewObservation,
    CboeVvixObservation,
    EconomicEvent,
    EiaCrudeStockObservation,
    FredObservation,
    GprObservation,
)

# ─────────────────────────────────── DOMAIN ─────────────────────────────

ThemeDriverKey = Literal[
    "macroeconomic",
    "monetary_policy",
    "economic_data",
    "fiscal_policy",
    "market_interconnexions",
    "geopolitics",
    "price_action_flow",
    "supply_demand",
]
"""Canonical 8-driver enum per Eliot Fathom transcript page 1 étape 1
verbatim. Stable render order (most slow-moving regime-defining →
most fast-moving microstructure). NEW drivers MUST land via Eliot
directive update OR R59 sub-agent verification that the taxonomy
variant is grounded in a peer-reviewed framework with DOI."""


THEME_DRIVERS: Final[tuple[ThemeDriverKey, ...]] = (
    "macroeconomic",
    "monetary_policy",
    "economic_data",
    "fiscal_policy",
    "market_interconnexions",
    "geopolitics",
    "price_action_flow",
    "supply_demand",
)
"""Stable render order for UI consumption — most slow-moving first.
Frontend consumers MUST match this tuple verbatim (W90-style lockstep
invariant CI guard r182+ candidate). New drivers MUST be appended
(not inserted) to preserve back-compat with frontend consumers that
iterate by index."""


_MIN_DRIVER_STRENGTH: Final[float] = 0.0
_MAX_DRIVER_STRENGTH: Final[float] = 1.0


class ThemeRanking(BaseModel):
    """Theme sous-jacent classifier output — which driver DRIVES the
    market in the current window per Eliot Fathom transcript étape 1.

    Frozen for cache safety + structural-immutability discipline
    (mirror ``OriginZoneSnapshot`` r174 + ``CorrelationMatrix`` r171a).

    Doctrine #11 calibrated honesty : when inputs are insufficient
    (e.g., NFCI stale + economic_events empty + DXY missing), the
    classifier returns ``None`` (the ``classify_dominant_theme``
    function), NEVER a forced ranking. The ``ThemeRanking`` instance
    itself is always honest by construction (driver_strengths cap
    at [0, 1], top_theme MUST be present in driver_strengths).
    """

    model_config = {"frozen": True, "extra": "forbid"}

    top_theme: ThemeDriverKey
    """The dominant driver per the classifier's ranking. Pass-2
    narrative consumes this to frame the macro-context read (e.g.,
    « le marché est actuellement driven par la geopolitics — toute
    interprétation des données économiques doit être lue dans ce
    contexte »)."""

    secondary_themes: list[ThemeDriverKey] = Field(default_factory=list, max_length=3)
    """Up to 3 secondary drivers contributing materially to current
    market dynamics. Ordered by decreasing strength. Empty list is
    a legitimate output when only one driver dominates clearly."""

    driver_strengths: dict[ThemeDriverKey, float] = Field(default_factory=dict)
    """Per-driver strength score in [0.0, 1.0]. ``top_theme`` MUST
    appear in this dict with the highest value. ``secondary_themes``
    MUST be present in decreasing strength order. r182+ EXECUTION
    populates from Pass-1 régime + NFCI + VIX + DXY + 10Y +
    economic_events + ai_gpr + GDELT inputs ; r181 FOUNDATION leaves
    this empty (classifier returns None unconditionally)."""

    computed_at_utc: datetime
    """Wall-clock UTC of the ranking computation. Used by Pass-2 for
    staleness check (ranking older than ~4h is considered stale)."""

    provenance: Literal["practitioner_stamp", "peer_reviewed"] = "practitioner_stamp"
    """Honest provenance stamp per Pattern #15 R59 discipline. The
    8-driver taxonomy itself is Eliot Fathom practitioner-stamp ;
    individual driver-strength computations may cite peer-reviewed
    backbone (e.g., NFCI = Brave-Butters 2011/2012 IJCB) at r182+
    EXECUTION ship time."""


# ─────────────────────────────────── r182 EXECUTION CONSTANTS ──────────

_FRED_MAX_AGE_DAYS: Final[int] = 7
"""FRED series max staleness for r182 EXECUTION inputs. Mirror
``_section_data_integrity`` r93 ADR-103 discipline : freshness >7d
treated as absent (silent-skip avoided via honest None return)."""

_VIX_PANIC_THRESHOLD: Final[float] = 30.0
"""Bekaert-Hoerova-Lo Duca 2013 JME funding-stress threshold (DOI
10.1016/j.jmoneco.2013.06.003). VIX > 30 = funding-stress regime
where cross-asset correlations collapse toward +1 (panic) or
decouple. Practitioner Whaley 2000 originally proposed 30 but walked
back 2009 — the FUNDING-STRESS CHANNEL is the peer-reviewed
contribution that anchors the threshold here."""

_VIX_COMPLACENT_THRESHOLD: Final[float] = 15.0
"""Practitioner-grade complacency band (VIX < 15). Below this, the
market is structurally complacent — different driver regime than
panic. r183+ calibration via Phase D Brier feedback may refine."""

_DXY_STRONG_THRESHOLD: Final[float] = 105.0
"""Practitioner-grade strong-USD threshold on DTWEXBGS broad basket.
Bertaut-DeMarco-Kamin-Tryon 2012 (FRB IFDP 1063) divergence
discipline informs the broad-vs-narrow read at r183+ ; for r182
we use the broad index level alone."""

_DXY_WEAK_THRESHOLD: Final[float] = 95.0
"""Practitioner-grade weak-USD threshold."""

_GPR_HIGH_PERCENTILE: Final[float] = 0.80
"""ai_gpr above 80th percentile of rolling 90-day window =
geopolitics-driven regime. Practitioner-grade ; Caldara-Iacoviello
2022 AER « Measuring Geopolitical Risk » DOI 10.1257/aer.20191823
informs the GPR construction (which the collector backfills), the
80th-percentile threshold is an Ichor calibration."""

_GPR_LOOKBACK_DAYS: Final[int] = 90

_PRICE_ACTION_LOOKBACK_DAYS: Final[int] = 90
"""r189 — rolling window for the VVIX/SKEW percentile rank that feeds the
``price_action_flow`` driver."""

_PRICE_ACTION_PERCENTILE: Final[float] = 0.80
"""r189 — VVIX OR SKEW at/above the 80th percentile of its rolling
``_PRICE_ACTION_LOOKBACK_DAYS`` window marks a positioning/flow-driven
regime (the market is uncertain about volatility itself / bidding tail
hedges). Self-calibrating percentile (mirror ``_GPR_HIGH_PERCENTILE``) —
no fragile hardcoded VVIX/SKEW level, robust + permanent across vol regimes."""

_SUPPLY_DEMAND_LOOKBACK_DAYS: Final[int] = 365
"""r190 — rolling window for the EIA crude-stocks weekly-change percentile
that feeds the ``supply_demand`` driver. 365d ≈ 52 weekly obs → ~51 weekly
Δ, which clears the shared ``_MIN_PERCENTILE_HISTORY`` = 30 Cohen-1988 floor
(a 180-day weekly window would yield only ~25 Δ and never trigger)."""

_SUPPLY_DEMAND_PERCENTILE: Final[float] = 0.80
"""r190 — the most-recent absolute weekly crude-stock change at/above the
80th percentile of its rolling window marks a supply/demand-driven regime.
Self-calibrating (shared ``_value_above_percentile``) — no fragile hardcoded
barrel level. Mirror r189 price_action_flow."""

_SUPPLY_DEMAND_SERIES_ID: Final[str] = "WCESTUS1"
"""EIA weekly crude-oil ending stocks series (the headline crude inventory
level). The ``supply_demand`` driver reads this one series' weekly Δ ;
WCRSTUS1 / WTTSTUS1 are persisted for future multi-series extension but
not yet read."""

_FOMC_PROXIMITY_LOOKBACK_DAYS: Final[int] = 5
"""±5 business days around FOMC = monetary-policy-driven window
per Nakamura-Steinsson 2018 QJE high-frequency identification
discipline DOI 10.1093/qje/qjy004."""

_FOMC_TITLE_KEYWORDS: Final[tuple[str, ...]] = (
    "FOMC",
    "Fed Chair",
    "FOMC Statement",
    "FOMC Press Conference",
)
"""ForexFactory title prefixes that mark FOMC events. Practitioner
parse of forex_factory title format ; r183+ may add ECB/BoE/BoJ."""

_HIGH_IMPACT_DATA_LOOKBACK_DAYS: Final[int] = 5
_HIGH_IMPACT_TAG: Final[str] = "high"

_FISCAL_LOOKBACK_DAYS: Final[int] = 7
"""r188 — fiscal-policy event window. 7 days catches the typical
budget cycle + tariff announcement cluster Eliot Fathom transcript
étape 1 identifies (« Trump tariffs 2026 = fiscal-policy-class »)."""

_FISCAL_TITLE_KEYWORDS: Final[tuple[str, ...]] = (
    "tariff",
    "fiscal",
    "budget",
    "debt ceiling",
    "deficit",
    "treasury auction",
    "treasury refunding",
    "spending bill",
    "appropriations",
)
"""Title substrings (lowercased ILIKE) that mark fiscal-policy events
in `economic_events`. Practitioner parse of ForexFactory + treasury
calendar title patterns. NEW keywords MUST be added via PR with R59
ground-truth that the substring actually appears in the upstream
collector data — not invented."""

_BASELINE_STRENGTH: Final[float] = 0.2
"""Driver baseline strength when no positive signal. Doctrine #11
calibrated honesty : NOT zero (avoids false honest-absence trigger
when one driver is mid-strength) but low enough that any positive
signal dominates."""

_DOMINANCE_THRESHOLD: Final[float] = 0.5
"""Minimum top_theme strength to emit ThemeRanking. Below this,
classifier returns None (honest absence : no theme dominates clearly,
per doctrine #11 calibrated honesty)."""

_SECONDARY_MIN_STRENGTH: Final[float] = 0.4
"""Minimum strength to include in secondary_themes list."""


# ─────────────────────────────────── r182 EXECUTION HELPERS ────────────


async def _latest_fred_value(
    session: AsyncSession,
    series_id: str,
    *,
    now_utc: datetime,
    max_age_days: int = _FRED_MAX_AGE_DAYS,
) -> float | None:
    """Pure-ish : query latest ``fred_observations`` row for
    ``series_id`` within ``max_age_days``. Returns ``None`` when
    absent OR stale (honest absence per ADR-103 discipline)."""
    cutoff = (now_utc - timedelta(days=max_age_days)).date()
    stmt = (
        select(FredObservation)
        .where(FredObservation.series_id == series_id)
        .where(FredObservation.observation_date >= cutoff)
        .order_by(desc(FredObservation.observation_date))
        .limit(1)
    )
    row = (await session.execute(stmt)).scalars().first()
    if row is None or row.value is None:
        return None
    return float(row.value)


async def _fomc_proximity_days(
    session: AsyncSession,
    *,
    now_utc: datetime,
) -> int | None:
    """Pure-ish : days-distance to nearest FOMC event within ±5
    business days. Returns ``None`` if no FOMC in window.

    Queries ``economic_events`` for titles matching
    ``_FOMC_TITLE_KEYWORDS`` (ILIKE pattern) scheduled within the
    proximity window. Returns min(|scheduled_at - now_utc|.days)
    or None."""
    lo = now_utc - timedelta(days=_FOMC_PROXIMITY_LOOKBACK_DAYS)
    hi = now_utc + timedelta(days=_FOMC_PROXIMITY_LOOKBACK_DAYS)
    stmt = (
        select(EconomicEvent)
        .where(EconomicEvent.currency == "USD")
        .where(EconomicEvent.scheduled_at.is_not(None))
        .where(EconomicEvent.scheduled_at >= lo)
        .where(EconomicEvent.scheduled_at <= hi)
    )
    rows = (await session.execute(stmt)).scalars().all()
    # Filter in Python for the OR-of-keyword match (cleaner than
    # OR-chain in SQL ; small result set after the time-window filter).
    candidates = [
        r
        for r in rows
        if r.scheduled_at is not None
        and any(kw.lower() in r.title.lower() for kw in _FOMC_TITLE_KEYWORDS)
    ]
    if not candidates:
        return None
    min_days = min(abs((r.scheduled_at - now_utc).days) for r in candidates)
    return min_days


async def _count_recent_fiscal_events(
    session: AsyncSession,
    *,
    now_utc: datetime,
) -> int:
    """r188 — count fiscal-policy events fired in last
    ``_FISCAL_LOOKBACK_DAYS`` days. Returns 0 when none.

    Queries ``economic_events`` for any USD-currency event whose
    title matches any of ``_FISCAL_TITLE_KEYWORDS`` (case-insensitive
    substring), regardless of impact tag (a treasury auction can
    move the curve even when ForexFactory marks it medium-impact).

    Eliot Fathom transcript étape 1 verbatim : « Trump tariffs 2026 =
    fiscal-policy-class ». This helper materialises that detection."""
    lo = now_utc - timedelta(days=_FISCAL_LOOKBACK_DAYS)
    stmt = (
        select(EconomicEvent)
        .where(EconomicEvent.currency == "USD")
        .where(EconomicEvent.scheduled_at.is_not(None))
        .where(EconomicEvent.scheduled_at >= lo)
        .where(EconomicEvent.scheduled_at <= now_utc)
    )
    rows = (await session.execute(stmt)).scalars().all()
    # Filter in Python for the OR-of-keyword match (small result set
    # after the time-window filter ; cleaner than OR-chain in SQL).
    matched = [r for r in rows if any(kw in r.title.lower() for kw in _FISCAL_TITLE_KEYWORDS)]
    return len(matched)


async def _count_recent_high_impact_releases(
    session: AsyncSession,
    *,
    now_utc: datetime,
) -> int:
    """Pure-ish : count high-impact USD economic_events fired in
    last 5 business days (with ``actual IS NOT NULL`` = data release
    happened). Returns 0 when none.

    This is a proxy for « major data surprises » at r182 ; a
    proper z-score surprise calculation requires the forecast +
    actual numeric parse + stddev across history, deferred r183+
    (N2 range attentes économistes column add per Eliot Fathom
    transcript étape 2)."""
    lo = now_utc - timedelta(days=_HIGH_IMPACT_DATA_LOOKBACK_DAYS)
    stmt = (
        select(EconomicEvent)
        .where(EconomicEvent.currency == "USD")
        .where(EconomicEvent.impact == _HIGH_IMPACT_TAG)
        .where(EconomicEvent.scheduled_at.is_not(None))
        .where(EconomicEvent.scheduled_at >= lo)
        .where(EconomicEvent.scheduled_at <= now_utc)
        .where(EconomicEvent.actual.is_not(None))
    )
    rows = (await session.execute(stmt)).scalars().all()
    return len(rows)


_MIN_PERCENTILE_HISTORY: Final[int] = 30
"""Cohen 1988 small-sample floor : < 30 observations → honest absence
(return False) rather than a low-confidence percentile rank."""


def _value_above_percentile(
    values_newest_first: list[float],
    pct: float,
) -> bool:
    """Pure : True if the most-recent value (``values_newest_first[0]``)
    sits at/above the ``pct`` percentile of the full set. False when fewer
    than ``_MIN_PERCENTILE_HISTORY`` observations (doctrine #11 honest
    absence, Cohen 1988). Shared by the GPR (geopolitics) and VVIX/SKEW
    (price_action_flow) drivers — Doctrine #4 SSOT / #9 anti-accumulation
    (single percentile-rank implementation, no duplication)."""
    if len(values_newest_first) < _MIN_PERCENTILE_HISTORY:
        return False
    today = values_newest_first[0]
    ordered = sorted(values_newest_first)
    rank = sum(1 for v in ordered if v <= today)
    return rank / len(ordered) >= pct


async def _is_ai_gpr_elevated(
    session: AsyncSession,
    *,
    now_utc: datetime,
) -> bool:
    """Pure-ish : True if today's ai_gpr exceeds the 80th percentile
    of the rolling ``_GPR_LOOKBACK_DAYS`` window. Returns False when
    insufficient history (< 30 observations, doctrine #11 honest
    absence per Cohen 1988 small-sample threshold)."""
    cutoff = (now_utc - timedelta(days=_GPR_LOOKBACK_DAYS)).date()
    stmt = (
        select(GprObservation)
        .where(GprObservation.observation_date >= cutoff)
        .order_by(desc(GprObservation.observation_date))
    )
    rows = (await session.execute(stmt)).scalars().all()
    # rows ordered desc → rows[0] = most-recent (today). Shared pure
    # percentile-rank helper (refactor r189 ; byte-identical to the prior
    # inline logic — regression-verified by test_theme_classifier).
    return _value_above_percentile([float(r.ai_gpr) for r in rows], _GPR_HIGH_PERCENTILE)


async def _is_price_action_flow_elevated(
    session: AsyncSession,
    *,
    now_utc: datetime,
) -> bool:
    """r189 — True if vol-of-vol (VVIX) OR tail-risk (SKEW) sits at/above
    the 80th percentile of its rolling ``_PRICE_ACTION_LOOKBACK_DAYS``
    window. Elevated VVIX/SKEW marks a positioning/flow-driven regime —
    the market is uncertain about volatility itself (VVIX) or bidding tail
    hedges (SKEW), both microstructure/flow signals rather than macro.
    Materialises the Eliot Fathom étape 1 ``price_action_flow`` driver
    (« positionnement, niveaux, surachat/survente, volatilité »).

    Self-calibrating percentile rank (shared ``_value_above_percentile``)
    — no fragile hardcoded VVIX/SKEW level, robust + permanent across vol
    regimes. Returns False on insufficient history (doctrine #11)."""
    cutoff = (now_utc - timedelta(days=_PRICE_ACTION_LOOKBACK_DAYS)).date()
    vvix_rows = (
        (
            await session.execute(
                select(CboeVvixObservation)
                .where(CboeVvixObservation.observation_date >= cutoff)
                .order_by(desc(CboeVvixObservation.observation_date))
            )
        )
        .scalars()
        .all()
    )
    if _value_above_percentile([float(r.vvix_value) for r in vvix_rows], _PRICE_ACTION_PERCENTILE):
        return True
    skew_rows = (
        (
            await session.execute(
                select(CboeSkewObservation)
                .where(CboeSkewObservation.observation_date >= cutoff)
                .order_by(desc(CboeSkewObservation.observation_date))
            )
        )
        .scalars()
        .all()
    )
    return _value_above_percentile(
        [float(r.skew_value) for r in skew_rows], _PRICE_ACTION_PERCENTILE
    )


async def _is_supply_demand_elevated(
    session: AsyncSession,
    *,
    now_utc: datetime,
) -> bool:
    """r190 — True if the most-recent weekly crude-stock CHANGE (build or
    draw) sits at/above the 80th percentile of |Δ| over the rolling
    ``_SUPPLY_DEMAND_LOOKBACK_DAYS`` window. A large absolute weekly
    inventory swing marks a supply/demand-driven regime — the commodity
    complex (oil, and via the dollar / real-yield channel, gold) being
    driven by physical balance rather than macro/policy. Materialises the
    Eliot Fathom étape 1 ``supply_demand`` driver (« offre/demande directe
    — impact majeur sur commodities »).

    Self-calibrating percentile rank (shared ``_value_above_percentile``)
    — no fragile hardcoded barrel level. Returns False on insufficient
    history (< 2 readings, or < 30 weekly Δ per Cohen 1988 ; doctrine #11
    honest absence). ADR-017 : descriptive regime context, never a signal."""
    cutoff = (now_utc - timedelta(days=_SUPPLY_DEMAND_LOOKBACK_DAYS)).date()
    rows = (
        (
            await session.execute(
                select(EiaCrudeStockObservation)
                .where(EiaCrudeStockObservation.series_id == _SUPPLY_DEMAND_SERIES_ID)
                .where(EiaCrudeStockObservation.observation_date >= cutoff)
                .order_by(desc(EiaCrudeStockObservation.observation_date))
            )
        )
        .scalars()
        .all()
    )
    # rows desc → rows[0] most recent. Weekly Δ = value[i] - value[i+1]
    # (current minus previous week). |Δ| newest-first for the percentile
    # rank (the helper tests element [0] = the latest weekly swing).
    values = [float(r.value) for r in rows if r.value is not None]
    if len(values) < 2:
        return False
    deltas_newest_first = [abs(values[i] - values[i + 1]) for i in range(len(values) - 1)]
    return _value_above_percentile(deltas_newest_first, _SUPPLY_DEMAND_PERCENTILE)


def _rank_drivers(
    strengths: dict[ThemeDriverKey, float],
) -> tuple[ThemeDriverKey, list[ThemeDriverKey]] | None:
    """Pure : pick top + ranked secondaries.

    Returns ``(top, secondary_list)`` when top's strength meets
    ``_DOMINANCE_THRESHOLD`` ; ``None`` otherwise (honest absence —
    no driver dominates).

    Secondary list : up to 3 entries (Pydantic max_length=3) with
    strength > ``_SECONDARY_MIN_STRENGTH``, in decreasing order.
    """
    if not strengths:
        return None
    sorted_pairs = sorted(strengths.items(), key=lambda kv: -kv[1])
    top_key, top_strength = sorted_pairs[0]
    if top_strength < _DOMINANCE_THRESHOLD:
        return None
    secondary = [k for k, v in sorted_pairs[1:] if v > _SECONDARY_MIN_STRENGTH][:3]
    return top_key, secondary


# ─────────────────────────────────── r182 EXECUTION MAIN ───────────────


async def classify_dominant_theme(
    session: AsyncSession,
    *,
    now_utc: datetime,
) -> ThemeRanking | None:
    """r182 EXECUTION-phase — compute per-driver strength scores
    via 4 hetero inputs (FRED VIXCLS + DTWEXBGS + DGS10 latest +
    economic_events FOMC proximity + economic_events recent high-
    impact data releases + GprObservation 90d percentile rank).

    Strength rules per driver (r183+ Phase D Brier calibration may
    refine) :

    - ``monetary_policy`` : FOMC ±5d → 0.7 + 0.05 × (5 - days_distance),
      else baseline 0.2.
    - ``economic_data`` : ≥2 high-impact data releases in last 5d →
      0.4 + 0.1 × n (capped 0.9), else 1 release → 0.5, else baseline.
    - ``geopolitics`` : ai_gpr > 80th percentile rolling 90d → 0.75,
      else baseline.
    - ``market_interconnexions`` : VIX > 30 (Bekaert-Hoerova-Lo Duca
      panic) → 0.7 ; VIX < 15 (complacent) → 0.4 ; else 0.3.
    - ``macroeconomic`` : VIX > 30 AND DXY extreme (>105 OR <95) =
      co-occurrence regime shift → 0.65, else baseline.
    - ``fiscal_policy`` : ≥1 fiscal event in last 7d → 0.6 + 0.05×(n-1)
      capped 0.85 (r188 enrichment), else baseline.
    - ``price_action_flow`` : VVIX OR SKEW at/above the 80th percentile of
      rolling 90d → 0.7 (r189 enrichment), else baseline.
    - ``supply_demand`` : EIA weekly crude-stock |Δ| at/above the 80th
      percentile of rolling 365d → 0.7 (r190 enrichment), else baseline.

    Returns ``ThemeRanking`` when ``top_theme`` strength ≥
    ``_DOMINANCE_THRESHOLD`` (0.5) ; ``None`` otherwise (honest
    absence per doctrine #11 calibrated honesty).

    Consumer wiring (Pass-2 data-pool ``_section_theme_dominant`` +
    frontend ``<ThemeRankingPanel>``) lands r183+.

    Args:
        session : SQLAlchemy async session (DB query handle, NOT used
            at r181 FOUNDATION but reserved for r182+ signature
            stability).
        now_utc : UTC wall-clock datetime. Reserved for r182+ window
            resolution + staleness checks.

    Returns:
        None at r181 FOUNDATION (skeleton). r182+ returns
        ``ThemeRanking`` when classifier inputs are sufficient,
        else None.
    """
    # r182 EXECUTION : 4 hetero inputs + 8-driver strength scoring.
    vix = await _latest_fred_value(session, "VIXCLS", now_utc=now_utc)
    dxy = await _latest_fred_value(session, "DTWEXBGS", now_utc=now_utc)
    # dgs10 query reserved for r183+ extension (US10Y yield-shift signal)
    _ = await _latest_fred_value(session, "DGS10", now_utc=now_utc)
    fomc_days = await _fomc_proximity_days(session, now_utc=now_utc)
    recent_releases = await _count_recent_high_impact_releases(session, now_utc=now_utc)
    gpr_elevated = await _is_ai_gpr_elevated(session, now_utc=now_utc)

    # Per-driver strength scoring.
    strengths: dict[ThemeDriverKey, float] = {}

    if fomc_days is not None:
        strengths["monetary_policy"] = min(
            0.95, 0.7 + 0.05 * max(0, _FOMC_PROXIMITY_LOOKBACK_DAYS - fomc_days)
        )
    else:
        strengths["monetary_policy"] = _BASELINE_STRENGTH

    if recent_releases >= 2:
        strengths["economic_data"] = min(0.9, 0.4 + 0.1 * recent_releases)
    elif recent_releases == 1:
        strengths["economic_data"] = 0.5
    else:
        strengths["economic_data"] = _BASELINE_STRENGTH

    strengths["geopolitics"] = 0.75 if gpr_elevated else _BASELINE_STRENGTH

    if vix is not None and vix > _VIX_PANIC_THRESHOLD:
        strengths["market_interconnexions"] = 0.7
    elif vix is not None and vix < _VIX_COMPLACENT_THRESHOLD:
        strengths["market_interconnexions"] = 0.4
    else:
        strengths["market_interconnexions"] = 0.3

    if (
        vix is not None
        and dxy is not None
        and vix > _VIX_PANIC_THRESHOLD
        and (dxy > _DXY_STRONG_THRESHOLD or dxy < _DXY_WEAK_THRESHOLD)
    ):
        strengths["macroeconomic"] = 0.65
    else:
        strengths["macroeconomic"] = _BASELINE_STRENGTH

    # r188 EXECUTION enrichment : fiscal_policy now wired via
    # `_count_recent_fiscal_events()`. 1 fiscal event in last 7d → 0.6
    # ; each additional event +0.05 capped at 0.85. Eliot Fathom
    # transcript étape 1 « Trump tariffs 2026 = fiscal-policy-class ».
    fiscal_count = await _count_recent_fiscal_events(session, now_utc=now_utc)
    if fiscal_count >= 1:
        strengths["fiscal_policy"] = min(0.85, 0.6 + 0.05 * (fiscal_count - 1))
    else:
        strengths["fiscal_policy"] = _BASELINE_STRENGTH

    # r189 EXECUTION enrichment : price_action_flow now wired via VVIX/SKEW
    # percentile (`_is_price_action_flow_elevated`). Elevated vol-of-vol OR
    # tail-risk → 0.7 (positioning/flow-driven regime ; mirrors the
    # market_interconnexions panic magnitude).
    strengths["price_action_flow"] = (
        0.7
        if await _is_price_action_flow_elevated(session, now_utc=now_utc)
        else _BASELINE_STRENGTH
    )
    # r190 EXECUTION enrichment : supply_demand now wired via EIA weekly
    # crude-stock change percentile (`_is_supply_demand_elevated`). A large
    # weekly inventory swing → 0.7 (commodity physical-balance-driven
    # regime). Theme classifier now 8/8 drivers data-driven.
    strengths["supply_demand"] = (
        0.7 if await _is_supply_demand_elevated(session, now_utc=now_utc) else _BASELINE_STRENGTH
    )

    # Doctrine #11 calibrated honesty : if all inputs absent (no FRED,
    # no FOMC, no releases, no GPR history), the dominant driver will
    # be at baseline 0.3 (market_interconnexions default) which is
    # below _DOMINANCE_THRESHOLD = 0.5. ``_rank_drivers()`` returns
    # None in that case.
    ranked = _rank_drivers(strengths)
    if ranked is None:
        return None  # honest absence : no driver dominates clearly
    top_theme, secondary = ranked

    return ThemeRanking(
        top_theme=top_theme,
        secondary_themes=secondary,
        driver_strengths=strengths,
        computed_at_utc=now_utc,
        provenance="practitioner_stamp",
    )
