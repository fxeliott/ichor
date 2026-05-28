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

from datetime import datetime
from typing import Final, Literal

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

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


# ─────────────────────────────────── SKELETON COMPUTE ──────────────────


async def classify_dominant_theme(
    session: AsyncSession,
    *,
    now_utc: datetime,
) -> ThemeRanking | None:
    """r181 FOUNDATION skeleton — returns None unconditionally.

    r182+ EXECUTION-phase will implement :

    1. Resolve recent macro state via Pass-1 régime classifier output
       (Master Quadrant) + NFCI + VIX + DXY level + 10Y yield.
    2. Query ``economic_events`` for events fired in last 72h with
       high impact + ``ai_gpr`` daily for geopolitical risk index +
       ``gdelt_events`` for global crisis indicators.
    3. Compute per-driver strength scores via deterministic rules :
       - ``macroeconomic`` : recent regime shift (Pass-1 quadrant
         change) → 0.7+ else 0.2
       - ``monetary_policy`` : FOMC/ECB/BoE/BoJ days +/- 5d → 0.7+
       - ``economic_data`` : major data surprises (|z-score| > 1.5)
         in last 5d → 0.6+
       - ``fiscal_policy`` : tariff_shock_check OR fiscal_event in
         last 7d → 0.6+
       - ``market_interconnexions`` : cross-asset breakouts (DXY +
         10Y + VIX simultaneous shifts) → 0.5+
       - ``geopolitics`` : ai_gpr above threshold OR GDELT crisis
         events spike → 0.7+
       - ``price_action_flow`` : VPIN regime + gamma flip + key levels
         crossed → 0.4+
       - ``supply_demand`` : commodity-specific OPEC/inventory data
         shift → 0.3+ (asset-class-dependent)
    4. Pick ``top_theme = argmax(driver_strengths)`` ; ``secondary_
       themes = top 3 by strength after top, threshold > 0.4``.
    5. Return ``ThemeRanking`` OR None if all driver strengths < 0.3
       (honest absence : no theme dominates clearly).

    r181 FOUNDATION returns None unconditionally. ZERO behavior change
    at r181 deploy. Consumer wiring (Pass-2 data-pool ``_section_
    theme_dominant`` + frontend ``<ThemeRankingPanel>``) lands r182+.

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
    # r181 FOUNDATION : skeleton. r182+ implements the 5-step compute.
    # Function signature is FROZEN by this ship so r182+ wiring consumers
    # (Pass-2 data-pool, frontend, tests) can integrate incrementally.
    _ = (session, now_utc)  # silence ruff unused-arg warning
    return None
